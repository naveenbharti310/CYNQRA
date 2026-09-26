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

from helpers import TempDir, engine_to_running, no_model_env, restore_env, run_journey

import fake_model
from cynqra import model_adapter
from cynqra.intelligence import IntelligenceError, ModelSource, _parse_json

RETIRED = "claude-sonnet-4-20250514"


class FakeProvider:
    def __init__(self):
        self.requests = []
        self.mode = "ok"
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
                prompt = body["messages"][0]["content"]
                if outer.mode == "http500":
                    return self._send(500, {"type": "error", "error": {"type": "api_error", "message": "overloaded"}})
                if body.get("model") == RETIRED:
                    return self._send(404, {"type": "error", "error": {"type": "not_found_error", "message": f"model: {RETIRED}"}})
                if outer.mode == "prose" or (outer.mode == "prose_once" and len(outer.requests) == 1):
                    text = "Here is my thinking in prose, with no object at all."
                else:
                    text = fake_model.answer(prompt)
                tin, tout = max(1, len(prompt) // 4), max(1, len(text) // 4)
                if self.path == "/v1/messages":
                    return self._send(200, {"id": "msg_fake", "type": "message", "role": "assistant",
                                            "content": [{"type": "text", "text": text}],
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
        model_adapter.ANTHROPIC_URL = self.p.base + "/v1/messages"
        model_adapter.OPENAI_URL = self.p.base + "/v1/chat/completions"

    def tearDown(self):
        model_adapter.ANTHROPIC_URL, model_adapter.OPENAI_URL = self.urls
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
        self.assertEqual(r["body"]["temperature"], 0)
        e.close()

    def test_default_is_not_the_retired_model(self):
        self.assertNotEqual(model_adapter.resolve()["label"], RETIRED)

    def test_retired_model_is_an_error_not_a_reply(self):
        os.environ["CYNQRA_MODEL"] = RETIRED
        with self.assertRaises(IntelligenceError) as ctx:
            ModelSource()._call("Convert the founder objective: anything")
        self.assertIn("HTTP 404", str(ctx.exception))

    def test_provider_outage_stops_the_run(self):
        e = engine_to_running(self.tmp.path, mode="live")
        self.p.mode = "http500"
        e._intel = None
        self.assertEqual(e.run_until_idle()[-1]["did"], "error")
        self.assertEqual(e.meta["phase"], "stopped_error")
        self.assertIn("Nothing was invented", e.meta["notice"])
        e.close()

    def test_one_retry_for_prose_then_json(self):
        self.p.mode = "prose_once"
        data, usage = ModelSource()._call("Convert the founder objective: a tracker")
        self.assertEqual(data["product"], "Internal candidate tracker")
        self.assertEqual(len(self.p.requests), 2)
        self.assertTrue(self.p.requests[1]["body"]["messages"][0]["content"].endswith("Reply with only one JSON object."))
        self.assertGreaterEqual(usage["units"], 1)

    def test_prose_twice_is_refused(self):
        self.p.mode = "prose"
        with self.assertRaises(IntelligenceError) as ctx:
            ModelSource()._call("Convert the founder objective: a tracker")
        self.assertIn("did not return a JSON object", str(ctx.exception))


class OpenAIWireTests(ProviderBase):
    def test_openai_format_and_precedence(self):
        os.environ["OPENAI_API_KEY"] = "sk-test-not-real"
        os.environ["ANTHROPIC_API_KEY"] = "test-key-not-real"
        src = ModelSource()
        self.assertEqual(src.label, "gpt-4o-mini", "OpenAI is used first when both keys are present")
        data, usage = src._call("Plan the work for the fixed organization")
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
