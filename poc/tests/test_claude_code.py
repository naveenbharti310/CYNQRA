"""Claude through Claude Code on this computer (`claude -p`) as a provider Cynqra can connect, against a test double
of the claude command (fake_claude.py) that is called and answers exactly as the real one: no model is used here."""
import json
import os
import stat
import sys
import unittest
from pathlib import Path
from unittest import mock

from helpers import TempDir, no_model_env, restore_env

from cynqra import model_adapter
from cynqra.intelligence_layer import IntelligenceSupply

FAKE = Path(__file__).resolve().parent / "fake_claude.py"


@unittest.skipUnless(os.name == "posix", "the test double is started through a shell script")
class ClaudeCodeTests(unittest.TestCase):

    def setUp(self):
        self.saved = no_model_env()
        self.addCleanup(restore_env, self.saved)
        self.tmp = TempDir()
        self.addCleanup(self.tmp.cleanup)
        self.cli = self.tmp.path / "claude"
        self.cli.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n', encoding="utf-8")
        self.cli.chmod(self.cli.stat().st_mode | stat.S_IEXEC)
        self.log = self.tmp.path / "calls.jsonl"
        patcher = mock.patch.dict(os.environ, {"CYNQRA_CLAUDE_CLI": str(self.cli), "FAKE_CLAUDE_LOG": str(self.log),
                                               # what links Claude Code to the session it runs beside
                                               "CLAUDE_CODE_TEE_SDK_STDOUT": "1",
                                               "CLAUDE_CODE_POST_FOR_SESSION_INGRESS_V2": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)
        model_adapter._NO_EFFORT.clear()

    def route(self, model="claude-haiku-4-5"):
        return {"kind": "claude_cli", "label": model, "local": False, "CYNQRA_TIMEOUT": "60"}

    def calls(self) -> list[dict]:
        return [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines()]

    def test_a_call_is_the_model_alone_with_its_real_tokens_and_cost(self):
        out = model_adapter.complete("Convert the founder objective", max_tokens=1500, route=self.route(),
                                     effort="low")
        self.assertIsNone(out["error"])
        self.assertIn('"product"', out["text"])
        self.assertEqual((out["tokens_in"], out["tokens_cached"], out["estimated"]), (1400, 400, False))
        self.assertEqual((out["usd_reported"], out["served_model"]), (0.00321, "claude-haiku-4-5-20251001"))
        call = self.calls()[-1]
        argv = call["argv"]
        for flag in ("-p", "--no-session-persistence", "--strict-mcp-config", "--system-prompt"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "", "no tools: the model alone")
        self.assertEqual((argv[argv.index("--model") + 1], argv[argv.index("--effort") + 1]),
                         ("claude-haiku-4-5", "low"))
        self.assertNotIn("CLAUDE_CODE_TEE_SDK_STDOUT", call["env"], "nothing relayed into this session")
        self.assertNotIn("CLAUDE_CODE_POST_FOR_SESSION_INGRESS_V2", call["env"])
        self.assertEqual(os.listdir(call["cwd"]), [], "run from an empty folder: no project file is read")
        self.assertEqual(call["max_output"], str(model_adapter.HOSTED_MIN_REPLY))

    def test_a_model_that_takes_no_effort_setting_is_asked_without_it_and_remembered(self):
        with mock.patch.dict(os.environ, {"FAKE_CLAUDE_NO_EFFORT": "1"}):
            out = model_adapter.complete("Convert the founder objective", max_tokens=100, route=self.route(),
                                         effort="medium")
            self.assertIsNone(out["error"])
            model_adapter.complete("Convert the founder objective", max_tokens=100, route=self.route(),
                                   effort="medium")
        flags = [("--effort" in c["argv"]) for c in self.calls()]
        self.assertEqual(flags, [True, False, False])

    def test_an_error_or_a_cut_off_reply_is_said_as_it_is(self):
        with mock.patch.dict(os.environ, {"FAKE_CLAUDE_ERROR": "Claude AI usage limit reached"}):
            out = model_adapter.complete("hi", max_tokens=100, route=self.route())
        self.assertIn("Claude Code: Claude AI usage limit reached", out["error"])
        with mock.patch.dict(os.environ, {"FAKE_CLAUDE_CUT": "1"}):
            cut = model_adapter.complete("Convert the founder objective", max_tokens=100, route=self.route())
            partial = model_adapter.complete("Convert the founder objective", max_tokens=100, route=self.route(),
                                             partial=True)
        self.assertIn("reply truncated", cut["error"])
        self.assertGreater(cut["tokens_out"], 0, "what a cut-off reply cost is kept")
        self.assertTrue(partial["truncated"])
        with mock.patch.dict(os.environ, {"CYNQRA_CLAUDE_CLI": str(self.tmp.path / "missing")}):
            gone = model_adapter.complete("hi", max_tokens=100, route=self.route())
        self.assertTrue(gone["error"])

    def test_it_is_connected_only_when_asked_for_priced_at_list_and_billed_as_reported(self):
        sup = IntelligenceSupply(self.tmp.path / "control")
        self.addCleanup(sup.close)
        self.assertEqual([c for c in sup.connect_environment() if c], [], "not asked for: not connected")
        with mock.patch.dict(os.environ, {"CYNQRA_CLAUDE_CODE": "1"}):
            sup.connect_environment()
        models = {m["ref"]: m for m in sup.registry.models()}
        self.assertEqual(set(models), {"claude-haiku-4-5", "claude-sonnet-5-5", "claude-opus-5-5"})
        sonnet, opus = models["claude-sonnet-5-5"], models["claude-opus-5-5"]
        # list $2 / $10, with every prompt written to the one-hour cache at twice the input price, read at a tenth
        self.assertEqual((sonnet["price_in"], sonnet["price_out"], sonnet["price_cached_in"]), (4.0, 10.0, 0.2))
        self.assertEqual((opus["price_in"], opus["price_cached_in"]), (8.0, 0.2), "Opus 5.5 reads at a twentieth")
        self.assertAlmostEqual(sup.registry.cost(sonnet, 1257 + 2, 4, 1, 0), 0.005076, places=6,
                               msg="the measured call: $0.005072 reported for 1,257 cached-write + 2 input tokens")
        mid = models["claude-haiku-4-5"]["id"]
        self.assertEqual(sup.gateway.route_kind(mid), "claude_cli")
        c = sup.registry.record_call(mid, role="w", purpose="work", task_kind="code", run_id="r",
                                     usage={"tokens_in": 1000, "tokens_out": 1000, "latency_s": 1,
                                            "usd_reported": 0.00321})
        self.assertEqual(c["usd"], 0.00321, "the provider's own report, not an estimate")
        sup.registry.set_regression(mid, True, "test fixture", by_kind={"objective": "passed", "code": "passed"})
        out = sup.gateway.invoke(mid, {"prompt": "Convert the founder objective", "max_tokens": 1500})
        self.assertIsNone(out["error"])
        with mock.patch.dict(os.environ, {"CYNQRA_CLAUDE_CLI": str(self.tmp.path / "missing")}):
            self.assertEqual(sup.registry.availability(sup.registry.get(mid))[0], False,
                             "without the claude command it cannot be reached")

    def test_an_objective_runs_through_it_end_to_end(self):
        from test_objective_intelligence import live_engine
        sup = IntelligenceSupply(self.tmp.path / "control")
        self.addCleanup(sup.close)
        sup.connect({"type": "claude_code", "name": "Claude Code (this computer)", "auth": {"method": "none"},
                     "models": ["claude-haiku-4-5", "claude-sonnet-5-5"]})
        for m in sup.registry.models():
            sup.registry.set_regression(m["id"], True, "test fixture: qualified test double",
                                        by_kind={"objective": "passed", "code": "passed"})
        e = live_engine(self.tmp.path / "run", sup)
        self.addCleanup(e.close)
        self.assertGreater(len(e.store.all("decision")), 0)
        calls = e.store.all("call")
        self.assertTrue(calls)
        self.assertTrue(all(c.get("usd_reported") == 0.00321 and c["usd"] == 0.00321 for c in calls))
        self.assertTrue(all(not c.get("estimated") for c in calls), "tokens as reported, never estimated")


if __name__ == "__main__":
    unittest.main()
