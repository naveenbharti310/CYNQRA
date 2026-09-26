"""The laptop path: an open model served by Ollama, the file block layout, the CLI.

FakeOllama speaks Ollama's native API on localhost; no model runs here and nothing is a
result. What is proven is the wire format, the settings sent, the failure handling and the
whole journey through the real engine, gateway, verification and deployment.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

from fake_ollama import FakeOllama
from helpers import POC, SCENARIO, TempDir, engine_to_running, no_model_env, restore_env, run_journey

from cynqra import model_adapter
from cynqra.intelligence import IntelligenceError, ModelSource, _file_blocks, _parse_json


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

    def test_json_before_code_with_braces_still_parses(self):
        self.assertEqual(_parse_json('Sure.\n{"a": 1}\n=== FILE: x.py ===\nd = {1: 2}\n=== END FILE ==='), {"a": 1})


class JourneyTests(Base):
    def test_whole_journey_on_a_local_model(self):
        e = engine_to_running(self.tmp.path, mode="live")
        run_journey(e)
        self.assertEqual(e.meta["phase"], "accepted")
        self.assertEqual([t["status"] for t in e.tasks()], ["VERIFIED"] * 6)
        chats = [r for r in self.o.requests if r["path"] == "/api/chat"]
        work = [r["body"] for r in chats if "=== FILE:" in r["body"]["messages"][0]["content"]]
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


class CliTests(Base):
    def cli(self, *args, stdin: str = "") -> subprocess.CompletedProcess:
        env = dict(os.environ, CYNQRA_REPORTS_DIR=str(self.tmp.path / "reports"), CYNQRA_DATA_DIR=str(self.tmp.path / "runs"),
                   PYTHONIOENCODING="utf-8")
        return subprocess.run([sys.executable, str(POC / "cynqra_cli.py"), *args], input=stdin, capture_output=True,
                              text=True, env=env, timeout=600)

    def test_doctor_full_passes_against_a_working_setup(self):
        r = self.cli("doctor", "--full")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for line in ("[PASS] Ollama: version 0.34.4", "[PASS] Model installed: qwen3.6:35b", "[PASS] JSON is valid",
                     "[PASS] Code works: 4 tests, 0 failed", "Ready."):
            self.assertIn(line, r.stdout)

    def test_doctor_warns_about_an_old_ollama(self):
        self.o.version = "0.32.14"
        self.assertIn("[WARN] Ollama: version 0.32.14", self.cli("doctor").stdout)

    def test_doctor_names_the_fix_when_the_model_is_missing(self):
        os.environ["CYNQRA_OLLAMA_MODEL"] = "gpt-oss:20b"
        r = self.cli("doctor")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fix: ollama pull gpt-oss:20b", r.stdout)

    def test_bench_compares_models_on_cynqras_own_tasks(self):
        self.o.models.append("gpt-oss:20b")
        r = self.cli("bench", "qwen3.6:35b", "gpt-oss:20b", "--objectives", "1")
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])
        self.assertIn("plan: valid, 6 tasks", r.stdout)
        rep = json.loads(next((self.tmp.path / "reports").glob("bench_*.json")).read_text())
        self.assertEqual([x["model"] for x in rep["rows"]], ["qwen3.6:35b", "gpt-oss:20b"])
        self.assertTrue(all(x["code"] == "pass" and x["plan"] and x["objectives"] == 1 for x in rep["rows"]))

    def test_tiers_follow_the_research(self):
        import cynqra_cli
        self.assertEqual(cynqra_cli.pick_tier(64)["model"], "qwen3.6:35b")
        self.assertEqual(cynqra_cli.pick_tier(32)["model"], "qwen3.6:35b")
        self.assertEqual(cynqra_cli.pick_tier(24)["model"], "qwen3.5:9b")
        self.assertEqual(cynqra_cli.pick_tier(16)["num_ctx"], 24576)

    def test_setup_writes_the_config_the_adapter_reads(self):
        cfg_path = POC / "local_config.json"
        saved = cfg_path.read_text() if cfg_path.exists() else None
        try:
            r = self.cli("setup", "--model", "gpt-oss:20b", "--host", "http://10.0.0.5:11434", "--print-model")
            self.assertEqual(r.stdout.strip(), "gpt-oss:20b")
            cfg = json.loads(cfg_path.read_text())
            self.assertEqual((cfg["think"], cfg["temperature"], cfg["seed"], cfg["host"]), ("low", 0, 42, "http://10.0.0.5:11434"))
        finally:
            cfg_path.unlink(missing_ok=True)
            if saved is not None:
                cfg_path.write_text(saved)

    def test_unattended_run_reaches_a_live_product(self):
        r = self.cli("run", "--yes", SCENARIO["messy"])
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])
        self.assertIn("PASS: accepted, live, healthy", r.stdout)
        self.assertIn("the engineer's own tests failed; it is fixing them", r.stdout)
        rep = json.loads(next((self.tmp.path / "reports").glob("live_*.json")).read_text())
        self.assertEqual((rep["outcome"], rep["usd"], rep["model"]["kind"]), ("PASS", 0.0, "ollama"))

    def test_interactive_run_with_the_founder_answering(self):
        answers = "c\n" + "a\n" + "a\na\na\na\n" + "\n"
        r = self.cli("run", SCENARIO["messy"], stdin=answers)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])
        self.assertIn("=== Needs you: Product rule for t_02", r.stdout)
        self.assertIn("Stopped by policy:", r.stdout)
        self.assertIn("The product is live at http://127.0.0.1:", r.stdout)


if __name__ == "__main__":
    unittest.main()
