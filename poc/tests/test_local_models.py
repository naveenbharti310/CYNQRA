"""Local model servers: Ollama's native API, the file block layout, closed schemas.

FakeOllama speaks Ollama's native API on localhost; no model runs here and nothing is a
result. What is proven is the wire format, the settings sent, the failure handling and the
whole journey through the real engine, gateway, verification and deployment.
"""
from __future__ import annotations

import os
import unittest

from fake_ollama import FakeOllama
from helpers import SCENARIO, TempDir, engine_to_running, no_model_env, restore_env, run_journey

from cynqra import model_adapter
from cynqra.intelligence import ModelSource, _file_blocks, _parse_json


class Base(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()
        self.o = FakeOllama()
        os.environ.update({"CYNQRA_OLLAMA_MODEL": "qwen3.6:35b", "OLLAMA_HOST": self.o.host})
        self.waits = model_adapter.RETRY_WAITS_S
        model_adapter.RETRY_WAITS_S = (0.0, 0.0)

    def tearDown(self):
        model_adapter.RETRY_WAITS_S = self.waits
        self.o.close()
        self.tmp.cleanup()
        restore_env(self.saved)


class OllamaWireTests(Base):
    def test_request_carries_the_settings_that_matter_locally(self):
        os.environ["CYNQRA_THINK"] = "false"
        out = model_adapter.complete('Return {"ok": true, "sum": 2 + 3}', max_tokens=200, want_json=True)
        self.assertIsNone(out["error"])
        body = self.o.requests[-1]["body"]
        self.assertEqual(self.o.requests[-1]["path"], "/api/chat")
        self.assertEqual((body["model"], body["stream"], body["format"], body["think"]), ("qwen3.6:35b", False, "json", False))
        self.assertEqual(body["options"]["num_ctx"], 32768, "Ollama's small default would truncate silently")
        self.assertGreaterEqual(body["options"]["num_predict"], 8192)
        self.assertNotIn("temperature", body["options"], "the model's own recommended default applies")
        self.assertEqual(body["keep_alive"], "30m")
        self.assertFalse(out["estimated"], "Ollama reports real token counts")
        self.assertEqual(model_adapter.resolve()["local"], True)

    def test_think_levels_and_no_json_mode_for_file_replies(self):
        os.environ["CYNQRA_THINK"] = "low"
        model_adapter.complete("x", want_json=False)
        body = self.o.requests[-1]["body"]
        self.assertEqual(body["think"], "low")
        self.assertNotIn("format", body)

    def test_a_cut_off_reply_is_an_error(self):
        self.o.mode = "length"
        self.assertIn("truncated", model_adapter.complete("x")["error"])

    def test_a_prompt_that_cannot_fit_is_refused_before_sending(self):
        os.environ["CYNQRA_NUM_CTX"] = "16384"
        out = model_adapter.complete("word " * 40000)
        self.assertIn("raise CYNQRA_NUM_CTX", out["error"])
        self.assertEqual(self.o.requests, [])

    def test_missing_model_and_stopped_server_say_what_to_do(self):
        os.environ["CYNQRA_OLLAMA_MODEL"] = "not-pulled:7b"
        self.assertIn("ollama pull not-pulled:7b", model_adapter.complete("x")["error"])
        os.environ["CYNQRA_OLLAMA_MODEL"] = "qwen3.6:35b"
        os.environ["OLLAMA_HOST"] = "127.0.0.1:9"
        self.assertIn("Ollama is not running", model_adapter.complete("x")["error"])

    def test_host_without_scheme_and_bind_all_address(self):
        os.environ["OLLAMA_HOST"] = "0.0.0.0:11434"
        self.assertEqual(model_adapter.ollama_host(), "http://127.0.0.1:11434")


class LocalServerTests(unittest.TestCase):
    """LM Studio and llama-server speak OpenAI's format; FakeProvider in test_adapter answers it."""

    def test_schema_and_thinking_off_are_sent_the_openai_way(self):
        from test_adapter import FakeProvider
        saved = no_model_env()
        p = FakeProvider()
        try:
            os.environ.update({"CYNQRA_LOCAL_BASE_URL": p.base + "/v1", "CYNQRA_MODEL": "qwen3.6-35b-a3b",
                               "CYNQRA_THINK": "false", "CYNQRA_SEED": "42"})
            data, usage = ModelSource()._call("Plan the work for the fixed organization", schema={"type": "object"})
            body = p.requests[-1]["body"]
            self.assertEqual(p.requests[-1]["path"], "/v1/chat/completions")
            self.assertEqual(body["response_format"]["json_schema"]["schema"], {"type": "object"})
            self.assertEqual((body["chat_template_kwargs"], body["seed"]), ({"enable_thinking": False}, 42))
            self.assertIn("tasks", data)
            self.assertFalse(usage["estimated"])
        finally:
            p.close()
            restore_env(saved)

    def test_every_schema_is_closed(self):
        from cynqra.intelligence import SCHEMAS
        def objects(x):
            if isinstance(x, dict):
                if x.get("type") == "object":
                    yield x
                for v in x.values():
                    yield from objects(v)
        self.assertTrue(all(o.get("additionalProperties") is False for s in SCHEMAS.values() for o in objects(s)))


class FileBlockTests(unittest.TestCase):
    def test_blocks_keep_code_exactly_and_json_header_is_found(self):
        code = 'print("a {brace} and \\\\n")\nx = {"k": 1}\n'
        text = '{"result": "done", "summary": "s"}\n=== FILE: app.py ===\n' + code + "=== END FILE ===\n" \
               "=== FILE: docs/spec.md ===\n# Spec\n=== END FILE ===\n"
        self.assertEqual(_parse_json(text), {"result": "done", "summary": "s"})
        self.assertEqual(_file_blocks(text), {"app.py": code, "docs/spec.md": "# Spec\n"})

    def test_the_ways_local_models_drift_from_the_layout_are_still_read(self):
        code, test = "def add(a, b):\n    return a + b\n", "import unittest\nfrom calc import add\n"
        variants = {
            "exact": f"=== FILE: calc.py ===\n{code}=== END FILE ===\n=== FILE: test_calc.py ===\n{test}=== END FILE ===\n",
            "no end lines": f"=== FILE: calc.py ===\n{code}\n=== FILE: test_calc.py ===\n{test}",
            "named end lines": f"=== FILE: calc.py ===\n{code}=== END FILE: calc.py ===\n=== FILE: test_calc.py ===\n{test}=== END FILE: test_calc.py ===\n",
            "fences inside blocks": f"=== FILE: calc.py ===\n```python\n{code}```\n=== END FILE ===\n=== FILE: test_calc.py ===\n```python\n{test}```\n=== END FILE ===\n",
            "markdown headings": f"### calc.py\n```python\n{code}```\n\n### `test_calc.py`\n```python\n{test}```\n",
            "bold names and colons": f"**calc.py**:\n```python\n{code}```\nFile: test_calc.py\n```python\n{test}```\n",
            "name in the first line": f"```python\n# calc.py\n{code}```\n```python\n# test_calc.py\n{test}```\n",
            "more equals and spaces": f"==== FILE:  calc.py ====\n{code}==== END FILE ====\n==== FILE:  test_calc.py ====\n{test}==== END FILE ====\n",
        }
        for label, text in variants.items():
            files = _file_blocks('{"result": "done", "summary": "s"}\n' + text)
            self.assertEqual(sorted(files), ["calc.py", "test_calc.py"], label)
            self.assertIn("return a + b", files["calc.py"], label)
            self.assertNotIn("```", files["calc.py"], label)
            self.assertNotIn("=== ", files["test_calc.py"], label)
        self.assertEqual(_file_blocks('{"result": "blocked", "description": "which date format?"}'), {})

    def test_a_reply_without_files_is_asked_for_once_more_with_the_layout(self):
        from cynqra import intelligence
        replies = ['{"result": "done", "summary": "I wrote the files"}\nHere they are, conceptually.',
                   '{"result": "done"}\n=== FILE: a.py ===\nx = 1\n=== END FILE ===\n']
        seen = []

        def fake(prompt, **kw):
            seen.append((prompt, kw.get("temperature")))
            return {"text": replies[len(seen) - 1], "tokens_in": 10, "tokens_out": 5, "estimated": False, "error": None}
        saved = intelligence.model_adapter.complete
        intelligence.model_adapter.complete = fake
        os.environ["CYNQRA_LOCAL_BASE_URL"] = "http://127.0.0.1:9/v1"
        try:
            data, usage = ModelSource()._call("write a.py", files=True)
        finally:
            intelligence.model_adapter.complete = saved
        self.assertEqual(data["files"], {"a.py": "x = 1\n"})
        self.assertIn("no files in the required layout", seen[1][0])
        self.assertEqual(seen[1][1], 0.4)
        self.assertEqual((usage["tokens_in"], usage["tokens_out"]), (20, 10))

    def test_json_before_code_with_braces_still_parses(self):
        self.assertEqual(_parse_json('Sure.\n{"a": 1}\n=== FILE: x.py ===\nd = {1: 2}\n=== END FILE ==='), {"a": 1})


class JourneyTests(Base):
    def test_whole_journey_on_a_local_model(self):
        e = engine_to_running(self.tmp.path, mode="live")
        run_journey(e)
        self.assertEqual(e.meta["phase"], "accepted")
        self.assertEqual([t["status"] for t in e.tasks()], ["VERIFIED"] * 6)
        chats = [r for r in self.o.requests if r["path"] == "/api/chat"]
        work = [r["body"] for r in chats if "Then every file, each one exactly like this" in r["body"]["messages"][0]["content"]]
        self.assertTrue(work and all("format" not in b for b in work), "file replies are not forced into JSON mode")
        others = [r["body"] for r in chats if r["body"] not in work]
        self.assertTrue(others and all(isinstance(b.get("format"), dict) and b["format"].get("required") for b in others),
                        "every JSON call sends its schema, which Ollama enforces as a grammar")
        self.assertTrue(all(b.get("shift") is False and b.get("truncate") is False for b in (r["body"] for r in chats)),
                        "overflow is an error, not a cut")
        checks = [x["payload"] for x in e.store.events() if x["event_type"] == "worker.self_checked"]
        self.assertIn(False, [c["passed"] for c in checks], "the engineer caught its own failing test")
        self.assertEqual(e.metrics()["fixed_by_workers_own_checks"], 1)
        self.assertFalse(any(c["estimated"] for c in e.store.all("call")))
        e.close()

    def test_a_syntax_error_is_named_back_to_the_engineer(self):
        src = ModelSource()
        calls = []
        real = src.work

        def broken_once(task, **kw):
            data, usage = real(task, **kw)
            if task["id"] == "t_04" and "files" in data and not calls:
                calls.append(1)
                data = dict(data, files=dict(data["files"], **{"app.py": "def broken(:\n"}))
            return data, usage

        src.work = broken_once
        from cynqra.engine import Engine
        e = Engine(self.tmp.path, intelligence=src)
        e.create_company("Harbor Recruiting", "live")
        e.draft_objective(SCENARIO["messy"])
        e.confirm_objective()
        e.decide(e.pending_decisions()[0]["id"], "approve")
        run_journey(e)
        fb = [x for x in e.store.events() if x["event_type"] == "worker.self_checked" and x["aggregate_id"] == "t_04"]
        self.assertFalse(fb[0]["payload"]["passed"])
        self.assertEqual(e.meta["phase"], "accepted")
        e.close()


if __name__ == "__main__":
    unittest.main()
