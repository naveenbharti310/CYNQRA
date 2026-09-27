"""Local model servers: Ollama's native API, the file block layout, closed schemas.

FakeOllama speaks Ollama's native API on localhost; no model runs here and nothing is a
result. What is proven is the wire format, the settings sent, the failure handling and the
whole journey through the real engine, gateway, verification and deployment.
"""
from __future__ import annotations

import json
import os
import unittest

from fake_ollama import FakeOllama
from helpers import SCENARIO, TempDir, engine_to_running, env_source, no_model_env, restore_env, run_journey

from cynqra import model_adapter
from cynqra.intelligence import _file_blocks, _parse_json


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
            data, usage = env_source()._call("Plan the work for this organization", schema={"type": "object"})
            body = p.requests[-1]["body"]
            self.assertEqual(p.requests[-1]["path"], "/v1/chat/completions")
            self.assertEqual(body["response_format"]["json_schema"]["schema"], {"type": "object"})
            self.assertEqual((body["chat_template_kwargs"], body["seed"]), ({"enable_thinking": False}, 42))
            self.assertIn("tasks", data)
            self.assertFalse(usage["estimated"])
        finally:
            p.close()
            restore_env(saved)

    def test_a_cut_off_local_reply_is_returned_only_to_a_caller_that_can_use_part_of_it(self):
        from test_adapter import FakeProvider
        saved = no_model_env()
        p = FakeProvider()
        p.mode = "length"
        try:
            os.environ.update({"CYNQRA_LOCAL_BASE_URL": p.base + "/v1", "CYNQRA_MODEL": "qwen3.6-35b-a3b-q2"})
            self.assertIn("truncated", model_adapter.complete("write it")["error"])
            out = model_adapter.complete("write it", partial=True)
            self.assertIsNone(out["error"])
            self.assertTrue(out["truncated"])
            self.assertEqual((out["tokens_out"], out["text"][-3:]), (6144, "y ="))
        finally:
            p.close()
            restore_env(saved)

    def test_hugging_face_inference_providers(self):
        from test_adapter import FakeProvider
        from cynqra.registry import WORST_PRICE, Registry
        saved = no_model_env()
        p = FakeProvider()
        try:
            os.environ.update({"HF_TOKEN": "hf_test_not_real", "CYNQRA_HF_MODEL": "openai/gpt-oss-120b:cerebras",
                               "HF_ROUTER_URL": p.base + "/v1", "CYNQRA_EFFORT": "low"})
            self.assertEqual(model_adapter.resolve()["kind"], "hf")
            data, usage = env_source()._call("Plan the work for this organization", schema={"type": "object"})
            r = p.requests[-1]
            self.assertEqual((r["path"], r["headers"]["authorization"]), ("/v1/chat/completions", "Bearer hf_test_not_real"))
            self.assertEqual(r["body"]["model"], "openai/gpt-oss-120b:cerebras")
            self.assertEqual(r["body"]["response_format"]["json_schema"]["schema"], {"type": "object"})
            self.assertEqual((r["body"]["reasoning_effort"], r["body"]["temperature"]), ("low", 0.0))
            self.assertGreaterEqual(r["body"]["max_tokens"], 16000, "room for reasoning before the answer")
            self.assertNotIn("chat_template_kwargs", r["body"], "llama-server only")
            self.assertIn("tasks", data)
            self.assertFalse(usage["estimated"])
            self.assertIsNone(model_adapter.resolve().get("local"), "paid calls, so spend is counted")
            tmp = TempDir()
            reg = Registry(tmp.path / "reg")
            m = reg.register({"runtime": "environment", "ref": "environment", "id": "a"})
            self.assertEqual((m["price_in"], m["price_out"]), WORST_PRICE, "an unlisted hosted model errs on the safe side")
            os.environ["CYNQRA_PRICE_PER_M"] = "0.25,0.69"
            m = reg.register({"runtime": "environment", "ref": "environment", "id": "b"})
            self.assertEqual((m["price_in"], m["price_out"], m["local"]), (0.25, 0.69, False))
            reg.close()
            tmp.cleanup()
            p.mode = "hf_401"
            self.assertIn("refused the token", model_adapter.complete("x")["error"])
            p.mode = "hf_402"
            self.assertIn("no inference credit left", model_adapter.complete("x")["error"])
            os.environ["CYNQRA_LOCAL_BASE_URL"] = "http://127.0.0.1:9/v1"
            self.assertEqual(model_adapter.resolve()["kind"], "local", "a model on this machine comes first")
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
            data, usage = env_source()._call("write a.py", files=True)
        finally:
            intelligence.model_adapter.complete = saved
        self.assertEqual(data["files"], {"a.py": "x = 1\n"})
        self.assertIn("no files in the required layout", seen[1][0])
        self.assertEqual(seen[1][1], 0.4)
        self.assertEqual((usage["tokens_in"], usage["tokens_out"]), (20, 10))

    def test_blank_objective_fields_are_inferred_in_one_short_follow_up(self):
        from cynqra import intelligence
        first = {"product": "Cake order tracker", "target_customer": "Bakery staff", "primary_outcome": "No lost orders",
                 "business_outcome": "Fewer refunds", "success_criteria": "", "constraints": "Internal only",
                 "priorities": "", "inferred_fields": ["business_outcome"], "missing_fields": ["success_criteria"]}
        second = {"success_criteria": "Every custom order is logged and none is missed at pickup",
                  "priorities": "Logging orders first, then the due soon view"}
        seen = []

        def fake(prompt, **kw):
            seen.append((prompt, kw.get("schema")))
            reply = first if len(seen) == 1 else second
            return {"text": json.dumps(reply), "tokens_in": 100, "tokens_out": 50, "estimated": False, "error": None}
        saved = intelligence.model_adapter.complete
        intelligence.model_adapter.complete = fake
        os.environ["CYNQRA_LOCAL_BASE_URL"] = "http://127.0.0.1:9/v1"
        try:
            data, usage = env_source().structure_objective("My staff lose cake orders.")
        finally:
            intelligence.model_adapter.complete = saved
        self.assertEqual(len(seen), 2)
        self.assertIn("success_criteria, priorities", seen[1][0])
        self.assertEqual(sorted(seen[1][1]["required"]), ["priorities", "success_criteria"])
        self.assertFalse(seen[1][1]["additionalProperties"])
        self.assertEqual(data["priorities"], second["priorities"])
        self.assertEqual(data["inferred_fields"], ["business_outcome", "success_criteria", "priorities"])
        self.assertEqual((usage["tokens_in"], usage["tokens_out"]), (200, 100))

    def test_a_prompt_sent_again_gets_temperature_so_the_reply_can_change(self):
        # temperature 0 and a fixed seed give the same reply to the same prompt; the Windows journey's rework loop sent
        # one prompt eight times and got the same failing code each time.
        from cynqra import intelligence
        temps = []

        def fake(prompt, **kw):
            temps.append((prompt, kw.get("temperature")))
            if prompt == "fails":
                return {"text": "", "tokens_in": 0, "tokens_out": 0, "estimated": False, "error": "server gone"}
            return {"text": '{"ok": 1}', "tokens_in": 10, "tokens_out": 5, "estimated": False, "error": None}
        saved = intelligence.model_adapter.complete
        intelligence.model_adapter.complete = fake
        os.environ["CYNQRA_LOCAL_BASE_URL"] = "http://127.0.0.1:9/v1"
        try:
            src = env_source()
            for prompt in ("same", "same", "other", "same", "same", "same"):
                src._call(prompt)
            for _ in range(2):
                with self.assertRaises(intelligence.IntelligenceError):
                    src._call("fails")
        finally:
            intelligence.model_adapter.complete = saved
        self.assertEqual(temps, [("same", None), ("same", 0.3), ("other", None), ("same", 0.6), ("same", 0.9),
                                 ("same", 0.9), ("fails", None), ("fails", None)])

    def test_a_cut_off_reply_drops_only_the_file_being_written(self):
        from cynqra import intelligence
        seen = {}
        text = ('{"result": "done", "summary": "store and tests"}\n=== FILE: store.py ===\ndef add(x):\n    return x\n'
                "=== END FILE ===\n=== FILE: test_store.py ===\nimport unittest\nclass T(unittest.Te")

        def fake(prompt, **kw):
            seen.update(kw)
            return {"text": text, "tokens_in": 900, "tokens_out": 6144, "estimated": False, "error": None,
                    "truncated": True}
        saved = intelligence.model_adapter.complete
        intelligence.model_adapter.complete = fake
        os.environ["CYNQRA_LOCAL_BASE_URL"] = "http://127.0.0.1:9/v1"
        os.environ["CYNQRA_NUM_PREDICT"] = "6144"
        try:
            data, usage = env_source()._call("write the store", files=True)
            with self.assertRaises(intelligence.IntelligenceError):  # a JSON reply cannot be used in part
                fake_json = {"text": '{"a": ', "tokens_in": 1, "tokens_out": 1, "estimated": False,
                             "error": "RuntimeError: reply truncated at max_tokens"}
                intelligence.model_adapter.complete = lambda prompt, **kw: fake_json
                env_source()._call("plan it", schema={"type": "object"})
        finally:
            intelligence.model_adapter.complete = saved
            os.environ.pop("CYNQRA_NUM_PREDICT", None)
        self.assertTrue(seen["partial"])
        self.assertEqual(data["files"], {"store.py": "def add(x):\n    return x\n"})
        self.assertEqual(data["cut_off"], "test_store.py")
        self.assertEqual(usage["tokens_out"], 6144)

    def test_json_before_code_with_braces_still_parses(self):
        self.assertEqual(_parse_json('Sure.\n{"a": 1}\n=== FILE: x.py ===\nd = {1: 2}\n=== END FILE ==='), {"a": 1})


class JourneyTests(Base):
    def test_whole_journey_on_a_local_model(self):
        e = engine_to_running(self.tmp.path, mode="live")
        run_journey(e)
        self.assertEqual(e.meta["phase"], "accepted")
        self.assertEqual([t["status"] for t in e.tasks()], ["VERIFIED"] * 6)
        chats = [r for r in self.o.requests if r["path"] == "/api/chat"]
        work = [r["body"] for r in chats if "Then each file you write, exactly like this" in r["body"]["messages"][0]["content"]]
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

    def test_a_reply_cut_off_at_the_output_limit_keeps_its_finished_files(self):
        # 0.1.1 on GitHub's machines: the 2-bit model's code replies passed its 6,144-token limit, and the whole
        # reply was thrown away four times running. Now the files finished before the cut are saved and only the
        # rest is asked for; the follow-up here sends only the file that was cut, so the journey passes only if the
        # engine kept the others.
        self.o.mode = "cut"
        e = engine_to_running(self.tmp.path, mode="live")
        run_journey(e)
        self.assertEqual(e.meta["phase"], "accepted")
        self.assertEqual([t["status"] for t in e.tasks()], ["VERIFIED"] * 6)
        cuts = [x["payload"] for x in e.store.events() if x["event_type"] == "task.reply_cut_off"]
        self.assertTrue(cuts and all(c["saved"] and c["file"] not in c["saved"] for c in cuts), cuts)
        asks = [r["body"]["messages"][0]["content"] for r in self.o.requests
                if "was cut off while writing" in r["body"]["messages"][-1]["content"]]
        self.assertEqual(len(asks), len(cuts))
        self.assertIn("These files were saved: ", asks[0])
        self.assertIn("They are kept as they are: send only the files you change", asks[0])
        e.close()

    def test_replies_that_keep_overflowing_are_escalated_not_retried_without_end(self):
        from cynqra import execution
        src = env_source()
        real = src.work

        def always_cut(task, **kw):
            data, usage = real(task, **kw)
            if task["kind"] == "code":
                data = dict(data, files={}, cut_off="app.py")
            return data, usage
        e = engine_to_running(self.tmp.path, mode="live")
        e.intel.work = always_cut
        for _ in range(10):  # approve the founder decisions before the first code task, up to its escalation
            e.run_until_idle()
            esc = [d for d in e.pending_decisions() if d["kind"] == "escalation"]
            if esc or not e.pending_decisions():
                break
            e.decide(e.pending_decisions()[0]["id"], "approve")
        self.assertEqual(len(esc), 1)
        self.assertIn(f"{execution.MAX_CUT_OFFS + 1} replies in a row were longer than the model's output limit",
                      esc[0]["problem"])
        cuts = [x for x in e.store.events() if x["event_type"] == "task.reply_cut_off"]
        self.assertEqual(len(cuts), execution.MAX_CUT_OFFS)
        e.decide(esc[0]["id"], "approve")
        self.assertEqual(e.task(esc[0]["task_id"])["cut_offs"], 0, "an approved retry starts counting again")
        e.close()

    def test_a_syntax_error_is_named_back_to_the_engineer(self):
        src = env_source()
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
        e.submit_objective()
        run_journey(e)
        fb = [x for x in e.store.events() if x["event_type"] == "worker.self_checked" and x["aggregate_id"] == "t_04"]
        self.assertFalse(fb[0]["payload"]["passed"])
        self.assertEqual(e.meta["phase"], "accepted")
        e.close()


if __name__ == "__main__":
    unittest.main()
