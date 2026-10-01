"""Live mode over the real provider wire formats (A15).

FakeProvider is a localhost HTTP server that speaks the Anthropic Messages API and the
OpenAI Chat Completions API shapes. The adapter's provider URL is pointed at it, so the
same code that would call api.anthropic.com runs here: headers, body, usage parsing,
HTTP errors and the one JSON retry. No real model is called and nothing here is a result.
"""
from __future__ import annotations

import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from helpers import TempDir, engine_to_running, env_source, no_model_env, restore_env, run_journey

import fake_model
from cynqra import model_adapter
from cynqra.intelligence import IntelligenceError, _parse_json

RETIRED = "claude-sonnet-4-20250514"


class FakeProvider:
    def __init__(self):
        self.requests = []
        self.listings = []
        self.mode = "ok"
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):  # Anthropic's model listing: the key reaches one model. Other formats list nothing.
                if "anthropic-version" not in {k.lower() for k in self.headers}:
                    return self.send_error(501)
                outer.listings.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}})
                if self.path.startswith("/v1/models"):
                    return self._send(200, {"data": [{"type": "model", "id": "claude-sonnet-5",
                                                      "display_name": "Claude Sonnet 5",
                                                      "created_at": "2026-01-01T00:00:00Z"}], "has_more": False})
                return self._send(404, {"type": "error", "error": {"type": "not_found_error", "message": self.path}})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
                prompt = body["messages"][0]["content"]
                if outer.mode == "http500":
                    return self._send(500, {"type": "error", "error": {"type": "api_error", "message": "overloaded"}})
                if outer.mode == "overloaded_once" and len(outer.requests) == 1:
                    return self._send(529, {"type": "error", "error": {"type": "overloaded_error", "message": "busy"}})
                if self.path == "/v1/messages" and "temperature" in body:
                    return self._send(400, {"type": "error", "error": {"type": "invalid_request_error",
                                            "message": "temperature is not supported for this model"}})
                if outer.mode == "refusal":
                    return self._send(200, {"id": "msg_fake", "type": "message", "role": "assistant", "content": [],
                                            "stop_reason": "refusal",
                                            "stop_details": {"type": "refusal", "category": "cyber", "explanation": "x"},
                                            "usage": {"input_tokens": 5, "output_tokens": 0}})
                if outer.mode == "truncated":
                    return self._send(200, {"id": "msg_fake", "type": "message", "role": "assistant",
                                            "content": [{"type": "text", "text": '{"product": "half'}],
                                            "stop_reason": "max_tokens",
                                            "usage": {"input_tokens": 5, "output_tokens": 16000}})
                if outer.mode == "hf_401":
                    return self._send(401, {"error": "Invalid credentials in Authorization header"})
                if outer.mode == "hf_402":
                    return self._send(402, {"error": "You have exceeded your monthly included credits"})
                if outer.mode == "length":  # an OpenAI-compatible local server at its max_tokens
                    return self._send(200, {"choices": [{"finish_reason": "length", "message": {
                        "role": "assistant", "content": "=== FILE: a.py ===\nx = 1\n=== END FILE ===\n=== FILE: b.py ===\ny ="}}],
                        "usage": {"prompt_tokens": 50, "completion_tokens": 6144}})
                if body.get("model") == RETIRED:
                    return self._send(404, {"type": "error", "error": {"type": "not_found_error", "message": f"model: {RETIRED}"}})
                if outer.mode == "prose" or (outer.mode == "prose_once" and len(outer.requests) == 1):
                    text = "Here is my thinking in prose, with no object at all."
                else:
                    text = fake_model.answer(prompt)
                tin, tout = max(1, len(prompt) // 4), max(1, len(text) // 4)
                if self.path == "/v1/messages":
                    return self._send(200, {"id": "msg_fake", "type": "message", "role": "assistant",
                                            "content": [{"type": "thinking", "thinking": "", "signature": "s"},
                                                        {"type": "text", "text": text}],
                                            "stop_reason": "end_turn",
                                            "usage": {"input_tokens": tin, "output_tokens": tout}})
                return self._send(200, {"choices": [{"message": {"role": "assistant", "content": text}}],
                                        "usage": {"prompt_tokens": tin, "completion_tokens": tout}})

            def _send(self, code, obj):
                raw = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class ProviderBase(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()
        self.p = FakeProvider()
        self.urls = (model_adapter.ANTHROPIC_URL, model_adapter.OPENAI_URL)
        self.waits = model_adapter.RETRY_WAITS_S
        model_adapter.RETRY_WAITS_S = (0.0, 0.0)
        model_adapter.ANTHROPIC_URL = self.p.base + "/v1/messages"
        os.environ["CYNQRA_ANTHROPIC_URL"] = self.p.base + "/v1/messages"  # the listing comes from the same server
        model_adapter.OPENAI_URL = self.p.base + "/v1/chat/completions"

    def tearDown(self):
        model_adapter.ANTHROPIC_URL, model_adapter.OPENAI_URL = self.urls
        model_adapter.RETRY_WAITS_S = self.waits
        os.environ.pop("CYNQRA_EFFORT", None)
        self.p.close()
        self.tmp.cleanup()
        restore_env(self.saved)


class AnthropicWireTests(ProviderBase):
    def setUp(self):
        super().setUp()
        os.environ["ANTHROPIC_API_KEY"] = "test-key-not-real"

    def test_whole_journey_over_the_anthropic_format(self):
        e = engine_to_running(self.tmp.path, mode="live")
        run_journey(e)
        self.assertEqual(e.meta["phase"], "accepted")
        self.assertEqual([t["status"] for t in e.tasks()], ["VERIFIED"] * 6)
        calls = e.store.all("call")
        self.assertTrue(calls)
        self.assertTrue(all(c["label"] == "claude-sonnet-5" for c in calls))
        self.assertFalse(any(c["estimated"] for c in calls), "API token counts are measured, not estimated")
        r = self.p.requests[0]
        self.assertEqual(r["path"], "/v1/messages")
        self.assertEqual(r["headers"]["x-api-key"], "test-key-not-real")
        self.assertEqual(r["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(r["body"]["model"], "claude-sonnet-5")
        self.assertNotIn("temperature", r["body"], "claude-sonnet-5 rejects sampling parameters with HTTP 400")
        self.assertGreaterEqual(r["body"]["max_tokens"], model_adapter.ANTHROPIC_MIN_MAX_TOKENS,
                                "room for default thinking, so the answer is not truncated")
        self.assertNotIn("output_config", r["body"])
        listing = self.p.listings[0]  # the model was discovered from the key's listing, not assumed
        self.assertTrue(listing["path"].startswith("/v1/models"))
        self.assertEqual(listing["headers"]["x-api-key"], "test-key-not-real")
        e.close()

    def test_truncated_reply_is_an_error_not_a_short_answer(self):
        self.p.mode = "truncated"
        with self.assertRaises(IntelligenceError) as ctx:
            env_source()._call("Convert the founder objective: anything")
        self.assertIn("truncated", str(ctx.exception))

    def test_refusal_is_an_error_not_an_empty_answer(self):
        self.p.mode = "refusal"
        with self.assertRaises(IntelligenceError) as ctx:
            env_source()._call("Convert the founder objective: anything")
        self.assertIn("refused", str(ctx.exception))

    def test_transient_overload_is_retried(self):
        self.p.mode = "overloaded_once"
        data, _ = env_source()._call("Convert the founder objective: a tracker")
        self.assertEqual(data["product"], "Internal candidate tracker")
        self.assertEqual(len(self.p.requests), 2)

    def test_persistent_outage_gives_up_after_three_attempts(self):
        self.p.mode = "http500"
        out = model_adapter.complete("Convert the founder objective: a tracker")
        self.assertIn("HTTP 500", out["error"])
        self.assertEqual(len(self.p.requests), 3)

    def test_effort_is_passed_through_and_validated(self):
        os.environ["CYNQRA_EFFORT"] = "low"
        env_source()._call("Convert the founder objective: a tracker")
        self.assertEqual(self.p.requests[-1]["body"]["output_config"], {"effort": "low"})
        os.environ["CYNQRA_EFFORT"] = "turbo"
        self.assertIn("CYNQRA_EFFORT", model_adapter.complete("x")["error"])

    def test_default_is_not_the_retired_model(self):
        self.assertNotEqual(model_adapter.resolve()["label"], RETIRED)

    def test_retired_model_is_an_error_not_a_reply(self):
        os.environ["CYNQRA_MODEL"] = RETIRED
        with self.assertRaises(IntelligenceError) as ctx:
            env_source()._call("Convert the founder objective: anything")
        self.assertIn("HTTP 404", str(ctx.exception))

    def test_a_provider_outage_waits_and_the_ceo_is_told_when_no_other_model_can_work(self):
        e = engine_to_running(self.tmp.path, mode="live")
        self.p.mode = "http500"
        steps = [r["did"] for r in e.run_until_idle()]
        self.assertIn("model_error_retry", steps)
        self.assertIn("waiting", steps, "the provider's side: the work waits, nothing is replaced or escalated")
        self.assertFalse(e.pending_decisions(), "nothing for the CEO to decide: no other AI could stand in")
        note = e.store.all("ceo_notice")[-1]
        self.assertEqual(note["kind"], "waiting_for_provider")
        self.assertIn("HTTP 500", note["detail"])
        self.assertEqual(e.task("t_01")["status"], "WAITING")
        self.assertFalse(e.registry.availability(e.registry.get(e.model_of("w_pm")))[0], "the outage is on its record")
        e.close()

    def test_one_retry_for_prose_then_json(self):
        self.p.mode = "prose_once"
        data, usage = env_source()._call("Convert the founder objective: a tracker")
        self.assertEqual(data["product"], "Internal candidate tracker")
        self.assertEqual(len(self.p.requests), 2)
        self.assertTrue(self.p.requests[1]["body"]["messages"][0]["content"].endswith("Reply with only one JSON object."))
        self.assertGreater(usage["tokens_in"], 0)

    def test_prose_twice_is_refused(self):
        self.p.mode = "prose"
        with self.assertRaises(IntelligenceError) as ctx:
            env_source()._call("Convert the founder objective: a tracker")
        self.assertIn("did not return a JSON object", str(ctx.exception))


class LiveCheckRunnerTests(ProviderBase):
    """live_check.py is the real model test. Here it runs over the fake provider only, to prove the
    runner itself; its PASS here is not a model result."""

    def test_runner_drives_the_journey_and_checks_the_product(self):
        import live_check
        os.environ["ANTHROPIC_API_KEY"] = "test-key-not-real"
        rep = live_check.run(live_check.SCENARIO["messy"], 5.0, self.tmp.path / "run", log=lambda *a: None)
        self.assertEqual(rep["outcome"], "PASS", rep.get("reason"))
        self.assertEqual(rep["health"]["status"], 200)
        self.assertTrue(rep["product_tests"]["ran"] and rep["product_tests"]["passed"])
        self.assertGreater(rep["usd"], 0)
        self.assertTrue(all(not c["estimated"] for c in rep["calls"]))

    def test_runner_refuses_without_a_key_and_the_spend_cap_stops_it(self):
        import live_check
        rep = live_check.run("anything", 5.0, self.tmp.path / "a", log=lambda *a: None)
        self.assertEqual(rep["outcome"], "UNRUN")
        os.environ["CYNQRA_S1_MODEL_CMD"] = "echo"
        self.assertEqual(live_check.run("x", 5.0, self.tmp.path / "b", log=lambda *a: None)["outcome"], "UNRUN")
        del os.environ["CYNQRA_S1_MODEL_CMD"]
        os.environ["ANTHROPIC_API_KEY"] = "test-key-not-real"
        rep = live_check.run(live_check.SCENARIO["messy"], 0.0001, self.tmp.path / "c", log=lambda *a: None)
        self.assertEqual(rep["outcome"], "UNRUN")
        self.assertIn("spend cap", rep["reason"])


class OpenAIWireTests(ProviderBase):
    def test_openai_format_and_precedence(self):
        os.environ["OPENAI_API_KEY"] = "sk-test-not-real"
        os.environ["ANTHROPIC_API_KEY"] = "test-key-not-real"
        from cynqra import model_adapter as ma
        self.assertEqual(ma.resolve()["label"], "gpt-4o-mini", "OpenAI is used first when both keys are present")
        data, usage = env_source()._call("Plan the work for this organization")
        self.assertEqual(usage["label"], "gpt-4o-mini")
        self.assertIn("tasks", data)
        self.assertFalse(usage["estimated"])
        r = self.p.requests[0]
        self.assertEqual(r["path"], "/v1/chat/completions")
        self.assertEqual(r["headers"]["authorization"], "Bearer sk-test-not-real")
        self.assertEqual(r["body"]["max_completion_tokens"], 4000)


class ParseTests(unittest.TestCase):
    def test_json_is_found_in_the_usual_wrappings(self):
        self.assertEqual(_parse_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(_parse_json('Sure. {"a": 2} Hope that helps.'), {"a": 2})
        self.assertEqual(_parse_json('{"a": 3}'), {"a": 3})
        self.assertIsNone(_parse_json("no object here"))
        self.assertIsNone(_parse_json("{broken"))
        self.assertIsNone(_parse_json("x {not: json} y"))
        self.assertIsNone(_parse_json(None))


if __name__ == "__main__":
    unittest.main()
