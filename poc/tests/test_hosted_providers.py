"""Hosted OpenAI-compatible providers other than Hugging Face and OpenAI (Google Gemini, NVIDIA Build, Mistral, Z.ai,
OpenRouter): a free tier's "too many requests" is waited out, a provider that refuses a strict JSON Schema is asked
again in plain JSON mode or with no format, and thinking models get room to answer. A laptop's own server keeps its
old behaviour: no resends, the smaller reply floor."""
from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import helpers  # noqa: F401 - puts the app on the path
from cynqra import model_adapter
from cynqra.replacement import diagnose

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}


class _Provider:
    """A scripted provider: each request takes the next (status, body, headers) from the script; the rest answer 200."""

    def __init__(self, script):
        self.script, self.requests = list(script), []
        provider = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                provider.requests.append({"body": body, "auth": self.headers.get("Authorization")})
                status, reply, headers = provider.script.pop(0) if provider.script else (200, None, {})
                if reply is None:
                    reply = {"choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
                             "usage": {"prompt_tokens": 11, "completion_tokens": 3}}
                data = json.dumps(reply).encode()
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class HostedProviderTests(unittest.TestCase):
    def setUp(self):
        self.saved = model_adapter.HOSTED_RETRY_WAITS_S
        model_adapter.HOSTED_RETRY_WAITS_S = (0.01, 0.01, 0.01, 0.01)
        model_adapter._JSON_MODE.clear()
        self.p = None

    def tearDown(self):
        model_adapter.HOSTED_RETRY_WAITS_S = self.saved
        model_adapter._JSON_MODE.clear()
        if self.p:
            self.p.close()

    def _call(self, script, local=False, model="gemini-flash"):
        self.p = self.p or _Provider([])
        self.p.script = list(script)
        route = {"kind": "local", "label": model, "local": local, "CYNQRA_LOCAL_BASE_URL": self.p.url,
                 "CYNQRA_LOCAL_API_KEY": "test-key", "CYNQRA_TIMEOUT": "30"}
        return model_adapter.complete("Answer in JSON.", max_tokens=1500, want_json=True, schema=SCHEMA, route=route)

    def test_a_busy_free_tier_is_waited_out(self):
        out = self._call([(429, {"error": "Too Many Requests"}, {"Retry-After": "0"}),
                          (503, {"error": "overloaded"}, {})])
        self.assertIsNone(out["error"])
        self.assertEqual(json.loads(out["text"]), {"ok": True})
        self.assertEqual(len(self.p.requests), 3, "two refusals, then the answer")
        self.assertEqual(self.p.requests[0]["auth"], "Bearer test-key")

    def test_a_limit_that_does_not_pass_reads_as_the_providers_side(self):
        out = self._call([(429, {"error": "Too Many Requests"}, {})] * 5)
        self.assertEqual(len(self.p.requests), 5, "the first try and four waits")
        self.assertEqual(diagnose(out["error"]), "rate_limit", "the AI is not at fault, so nobody is replaced")

    def test_a_refused_schema_falls_back_to_plain_json_then_to_none(self):
        refusal = (400, {"error": {"message": "Invalid value for response_format: json_schema is not supported"}}, {})
        out = self._call([refusal, (400, {"error": {"message": "response_format json_object is not supported"}}, {})])
        self.assertIsNone(out["error"])
        sent = [r["body"].get("response_format", {}).get("type") for r in self.p.requests]
        self.assertEqual(sent, ["json_schema", "json_object", None])
        self.p.requests.clear()
        self._call([])
        self.assertNotIn("response_format", self.p.requests[0]["body"], "what the provider accepted is remembered")

    def test_a_schema_the_provider_accepts_is_kept(self):
        self._call([])
        body = self.p.requests[0]["body"]
        self.assertEqual(body["response_format"]["json_schema"]["schema"], SCHEMA)

    def test_an_error_about_something_else_is_not_mistaken_for_the_format(self):
        out = self._call([(400, {"error": {"message": "prompt is too long for this model"}}, {})])
        self.assertIn("HTTP 400", out["error"])
        self.assertEqual(len(self.p.requests), 1)

    def test_a_thinking_model_gets_room_to_answer(self):
        self._call([])
        self.assertGreaterEqual(self.p.requests[0]["body"]["max_tokens"], model_adapter.HOSTED_MIN_REPLY)

    def test_a_laptop_server_is_not_resent_and_keeps_its_floor(self):
        out = self._call([(429, {"error": "busy"}, {})], local=True)
        self.assertIn("HTTP 429", out["error"])
        self.assertEqual(len(self.p.requests), 1, "a laptop's request is deterministic: resending costs minutes")
        self.p.requests.clear()
        self._call([], local=True)
        self.assertEqual(self.p.requests[0]["body"]["max_tokens"], 8192)




class GoogleLimitTests(unittest.TestCase):
    """Google's free tier says "check your plan and billing details" for every limit."""

    MSG = ("HTTP 429 from provider: {\"error\": {\"code\": 429, \"message\": \"You exceeded your current quota, please "
           "check your plan and billing details. * Quota exceeded for metric: generate_content_free_tier_requests, "
           "limit: 10, model: gemini-flash%s\"}}")

    def test_the_minute_limit_passes_and_nobody_is_at_fault(self):
        self.assertEqual(diagnose(self.MSG % " Please retry in 23.5s."), "rate_limit")

    def test_the_days_allowance_used_up_is_for_the_founder(self):
        self.assertEqual(diagnose(self.MSG % ", quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier"),
                         "no_credit")


if __name__ == "__main__":
    unittest.main()
