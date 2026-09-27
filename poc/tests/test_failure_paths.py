"""What happens when things go wrong, and how the founder recovers.

A FaultySource is the demo scenario with chosen answers replaced, so each failure is
produced by a worker exactly as a bad model reply would be, and runs through the real
engine, gateway, verification and deployment code.
"""
from __future__ import annotations

import json
import unittest

from helpers import SCENARIO, TempDir, engine_to_gates, no_model_env, restore_env, run_journey

from cynqra.engine import Engine, EngineError
from cynqra.intelligence import ScriptedSource


class FaultySource(ScriptedSource):
    def __init__(self):
        super().__init__()
        self.faults = {}  # task id -> function(call_index, good_result) -> result

    def work(self, task, call_index=0, **kw):
        res, usage = super().work(task, call_index=call_index, **kw)
        f = self.faults.get(task["id"])
        return (f(call_index, res) if f else res), usage


def start(folder, src, cap=120) -> Engine:
    e = Engine(folder, intelligence=src)
    e.create_company("Harbor Recruiting")
    e.draft_objective(SCENARIO["messy"])
    e.set_guardrails(budget_cap=cap)
    e.submit_objective()
    return engine_to_gates(e)


def approve_until(e: Engine, kind: str) -> dict:
    for _ in range(12):
        e.run_until_idle()
        pend = e.pending_decisions()
        if pend and pend[0]["kind"] == kind:
            return pend[0]
        e.decide(pend[0]["id"], "approve")
    raise AssertionError(f"never reached a {kind} decision")


class Base(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()
        self.src = FaultySource()
        self.e = None

    def tearDown(self):
        if self.e:
            self.e.close()
        self.tmp.cleanup()
        restore_env(self.saved)


class InvalidProtocolTests(Base):
    def setUp(self):
        super().setUp()
        drop = lambda i, r: {k: v for k, v in r.items() if k != "recommendation"} if i < 3 else r  # noqa: E731
        self.src.faults["t_02"] = drop
        self.e = start(self.tmp.path, self.src)
        self.e.run_until_idle()

    def test_three_invalid_replies_escalate_to_the_founder(self):
        t = self.e.task("t_02")
        self.assertEqual((t["status"], t["attempts"]), ("FAILED", 3))
        d = self.e.pending_decisions()[0]
        self.assertEqual((d["kind"], d["severity"]), ("escalation", "SEV-2"))
        self.assertIn("invalid protocol objects", d["problem"])
        self.assertIn("Escalation", [p["kind"] for p in self.e.store.all("protocol")])

    def test_founder_retries_and_the_run_finishes(self):
        d = self.e.pending_decisions()[0]
        self.e.decide(d["id"], "approve")
        self.assertEqual(self.e.task("t_02")["attempts"], 0)
        run_journey(self.e)
        self.assertEqual(self.e.meta["phase"], "accepted")

    def test_founder_stops_the_run(self):
        self.e.decide(self.e.pending_decisions()[0]["id"], "reject", note="Stop here")
        self.assertEqual(self.e.meta["phase"], "stopped")
        self.assertEqual(self.e.step()["did"], "idle")


class VerificationFailsThreeTimesTests(Base):
    def setUp(self):
        super().setUp()
        self.buggy = True
        self.src.faults["t_03"] = lambda i, r: (ScriptedSource.work(self.src, self.e.task("t_03"), call_index=0)[0]
                                                if self.buggy else r)
        self.e = start(self.tmp.path, self.src)
        self.d = approve_until(self.e, "escalation")

    def test_verdicts_then_escalation(self):
        vs = [v["verdict"] for v in self.e.store.all("verification") if v["task_id"] == "t_03"]
        self.assertEqual(vs, ["REQUIRES_REWORK", "REQUIRES_REWORK", "REQUIRES_HUMAN"])
        self.assertEqual(self.e.task("t_03")["status"], "FAILED")
        self.assertIn("failed verification 3 times", self.d["problem"])
        self.assertIn("test_list_returns_all", self.d["problem"], "the founder sees which test failed")
        self.assertNotIn("t_03", [a["task_id"] for a in self.e.store.all("artifact")], "failed code never integrated")

    def test_evolution_recommends_a_review(self):
        ev = self.e.evolution()
        self.assertTrue(ev["title"].startswith("Review"), ev)
        self.assertIn("recommendation only", ev["status"])

    def test_a_fixed_retry_recovers(self):
        self.buggy = False
        self.e.decide(self.d["id"], "approve")
        run_journey(self.e)
        self.assertEqual(self.e.meta["phase"], "accepted")
        vs = [v["verdict"] for v in self.e.store.all("verification") if v["task_id"] == "t_03"]
        self.assertEqual(vs[-1], "VERIFIED")


class WriteRefusedTests(Base):
    def test_a_write_outside_the_workspace_is_refused_and_reworked(self):
        def escape(i, r):
            if i == 0:
                r = dict(r)
                r["files"] = {"../../escape.md": "x"}
            return r
        self.src.faults["t_01"] = escape
        self.e = start(self.tmp.path, self.src)
        steps = [s["did"] for s in self.e.run_until_idle()]
        self.assertIn("write_refused", steps)
        self.assertFalse(any(self.tmp.path.rglob("escape.md")), "nothing was written anywhere")
        self.assertEqual(self.e.task("t_01")["status"], "VERIFIED")
        denied = [a for a in self.e.store.all("action") if a["status"] == "denied" and a["action_type"] == "write_file"]
        self.assertEqual(len(denied), 1)


class ReleaseCandidateFailsTests(Base):
    def test_merge_is_refused_when_the_candidate_fails(self):
        self.e = start(self.tmp.path, self.src)
        for _ in range(40):
            if self.e.task("t_04")["status"] == "VERIFIED":
                break
            if not self.e.pending_decisions():
                self.e.step()
            else:
                self.e.decide(self.e.pending_decisions()[0]["id"], "approve")
        (self.e.paths["integration"] / "test_broken.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.fail('broken')\n")
        self.e.run_until_idle()
        d = self.e.pending_decisions()[0]
        self.assertEqual((d["kind"], d["task_id"]), ("escalation", "t_05"))
        self.assertIn("nothing safe to merge", d["problem"])
        self.assertFalse((self.e.paths["main"] / "app.py").exists(), "nothing reached main")


class LiveSmokeFailsTests(Base):
    def setUp(self):
        super().setUp()
        self.e = start(self.tmp.path, self.src)
        self.d = approve_until(self.e, "deploy")
        dep = self.e.store.get("deployment", self.d["extra"]["deployment_id"])
        from pathlib import Path
        (Path(dep["folder"]) / "smoke.json").write_text(json.dumps(
            {"checks": [{"method": "GET", "path": "/health", "expect": 200},
                        {"method": "GET", "path": "/missing-page", "expect": 200}]}))
        self.e.decide(self.d["id"], "approve")
        self.e.run_until_idle()

    def test_rollback_and_escalation(self):
        dep = self.e.store.get("deployment", self.d["extra"]["deployment_id"])
        self.assertEqual(dep["status"], "rolled_back")
        self.assertEqual([x["stage"] for x in dep["log"]][-2:], ["SMOKE_TEST", "ROLLBACK"])
        types = [ev["event_type"] for ev in self.e.store.events(correlation_id="t_06")]
        self.assertIn("deployment.rolled_back", types)
        self.assertIsNone(self.e.live_url(), "nothing is live after a failed first release")
        esc = self.e.pending_decisions()[0]
        self.assertEqual((esc["kind"], esc["task_id"]), ("escalation", "t_06"))

    def test_retry_builds_a_new_release_and_goes_live(self):
        self.e.decide(self.e.pending_decisions()[0]["id"], "approve")
        run_journey(self.e)
        self.assertEqual(self.e.meta["phase"], "accepted")
        deps = self.e.store.all("deployment")
        self.assertEqual([d["status"] for d in deps], ["rolled_back", "live"])
        self.assertTrue(self.e.live_url())


class FounderSaysNoTests(Base):
    def test_rejected_delivery_is_recorded(self):
        self.e = start(self.tmp.path, self.src)
        d = approve_until(self.e, "accept_delivery")
        self.e.decide(d["id"], "reject", note="The stuck filter is too hidden")
        self.assertEqual(self.e.meta["phase"], "delivered")
        self.assertIn("Delivery not accepted", self.e.meta["notice"])
        types = [ev["event_type"] for ev in self.e.store.events()]
        self.assertIn("transition.rejected", types)
        self.assertNotIn("transition.approved", types)
        self.assertTrue(self.e.live_url(), "the product stays live")

    def test_budget_breaker_refused_stops_the_run(self):
        self.e = start(self.tmp.path, self.src, cap=30)
        d = approve_until(self.e, "budget_breaker")
        self.e.decide(d["id"], "reject")
        self.assertEqual(self.e.meta["phase"], "stopped")
        self.assertIn("budget cap", self.e.meta["notice"])

    def test_graph_rejects_unknown_questions(self):
        self.e = start(self.tmp.path, self.src)
        with self.assertRaises(EngineError):
            self.e.graph("likes", "t_01")


if __name__ == "__main__":
    unittest.main()
