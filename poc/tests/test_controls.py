"""Founder controls and edge paths: gateway, decisions, budget, kill switch, objective (A2, A6, A9, A10, A14)."""
from __future__ import annotations

import unittest

from helpers import SCENARIO, TempDir, engine_to_running, no_model_env, restore_env, run_journey

from cynqra.engine import Engine, EngineError


class Base(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()

    def tearDown(self):
        if getattr(self, "e", None):
            self.e.close()
        self.tmp.cleanup()
        restore_env(self.saved)


class GatewayTests(Base):  # A6
    def setUp(self):
        super().setUp()
        self.e = engine_to_running(self.tmp.path)

    def test_writes_stay_in_the_workspace(self):
        for bad in ("../escape.py", "/etc/passwd.py", "tool.exe", "a/b/c/d.py"):
            r = self.e.gateway("w_eng_a", "t_03", "write_file", target=bad, content="x = 1\n")
            self.assertEqual(r["status"], "denied", bad)
        ok = self.e.gateway("w_eng_a", "t_03", "write_file", target="ok.py", content="x = 1\n")
        self.assertEqual(ok["status"], "executed")
        self.assertTrue((self.e.paths["workspaces"] / "w_eng_a" / "t_03" / "out" / "ok.py").exists())

    def test_oversize_content_refused(self):
        r = self.e.gateway("w_eng_a", "t_03", "write_file", target="big.py", content="x" * 200_001)
        self.assertEqual(r["status"], "denied")

    def test_unknown_worker_refused(self):
        with self.assertRaises(EngineError):
            self.e.gateway("w_intern", "t_03", "write_file", target="a.py", content="")

    def test_approval_must_match(self):
        r = self.e.gateway("w_cto", "t_05", "merge_to_main", target="main")
        self.assertEqual(r["status"], "requires_approval")
        r = self.e.gateway("w_cto", "t_05", "merge_to_main", target="main", approval="dec_confirm_objective")
        self.assertEqual(r["status"], "requires_approval", "an approval for another action does not count")

    def test_every_gateway_call_is_audited(self):
        before = self.e.store.count_events()
        self.e.gateway("w_eng_a", "t_03", "external_message", target="x")
        self.e.gateway("w_eng_a", "t_03", "write_file", target="a.py", content="")
        types = [ev["event_type"] for ev in self.e.store.events()[before:]]
        self.assertIn("action.denied", types)
        self.assertIn("action.executed", types)


class DecisionTests(Base):  # A9
    def setUp(self):
        super().setUp()
        self.e = engine_to_running(self.tmp.path)
        self.e.run_until_idle()
        self.d = self.e.pending_decisions()[0]

    def test_inbox_card_has_every_field(self):
        for f in ("problem", "evidence_refs", "recommendation", "cost", "risk", "confidence", "what_would_change_this"):
            self.assertTrue(self.d[f], f)
        self.assertEqual(self.d["kind"], "decision")

    def test_edited_approval_is_labelled_and_used(self):
        rule = "Stuck means flagged plus a named reason. Custom wording by the founder."
        self.e.decide(self.d["id"], "approve", edited={"recommendation": rule})
        self.assertEqual(self.e.store.get("decision", self.d["id"])["outcome_label"], "approved_edited")
        self.e.step()
        self.assertIn(rule, self.e.rules())
        self.assertIn("Custom wording", (self.e.paths["integration"] / "docs" / "DECISIONS.md").read_text())

    def test_reject_sends_it_back_and_it_returns(self):
        self.e.decide(self.d["id"], "reject", note="Use a five day clock instead")
        self.assertEqual(self.e.store.get("decision", self.d["id"])["outcome_label"], "rejected_with_reason")
        self.assertEqual(self.e.task("t_02")["status"], "REWORK")
        self.e.run_until_idle()
        again = self.e.pending_decisions()
        self.assertEqual(len(again), 1)
        self.assertNotEqual(again[0]["id"], self.d["id"])

    def test_request_evidence_label(self):
        self.e.decide(self.d["id"], "request_evidence", note="Show me recruiter feedback")
        self.assertEqual(self.e.store.get("decision", self.d["id"])["outcome_label"], "more_evidence_requested")

    def test_cannot_decide_twice_or_badly(self):
        self.e.decide(self.d["id"], "approve")
        with self.assertRaises(EngineError):
            self.e.decide(self.d["id"], "approve")
        with self.assertRaises(EngineError):
            self.e.decide("dec_nope", "approve")
        d2 = self.e._decision("escalation", problem="p", recommendation="r", risk="LOW", confidence="low", cost="c",
                              evidence=[], change="c", source="w_pm")
        with self.assertRaises(EngineError):
            self.e.decide(d2["id"], "shrug")

    def test_escalation_budget_d29(self):
        for i in range(6):
            self.e._decision("escalation", problem=f"p{i}", recommendation="r", risk="LOW", confidence="low",
                             cost="c", evidence=[], change="c", source="w_eng_a", task_id=f"x_{i}")
        digest = [d for d in self.e.pending_decisions() if d["in_digest"]]
        self.assertEqual(len(digest), 2, "only five worker escalations a day interrupt the founder")
        sev1 = self.e._decision("escalation", problem="outage", recommendation="r", risk="HIGH", confidence="high",
                                cost="c", evidence=[], change="c", source="w_cto", severity="SEV-1", task_id="x_sev1")
        self.assertFalse(sev1["in_digest"], "SEV-1 always interrupts")


class BudgetTests(Base):  # A10
    def test_breaker_stops_work_and_the_founder_resumes_it(self):
        self.e = engine_to_running(self.tmp.path, cap=30)
        self.e.run_until_idle()
        for _ in range(10):
            pend = self.e.pending_decisions()
            if any(d["kind"] == "budget_breaker" for d in pend):
                break
            self.e.decide(pend[0]["id"], "approve")
            self.e.run_until_idle()
        b = self.e.budget()
        self.assertEqual(b["state"], "breaker")
        self.assertEqual(sorted(b["warned"]), [50, 80, 95])
        self.assertEqual(self.e.step(), {"did": "idle", "why": "budget breaker open"})
        types = [ev for ev in self.e.store.events() if ev["event_type"] == "budget.threshold_reached"]
        self.assertEqual([ev["payload"]["threshold"] for ev in types], [50, 80, 95, 100])
        br = [d for d in self.e.pending_decisions() if d["kind"] == "budget_breaker"][0]
        self.e.decide(br["id"], "approve", edited={"cap": 200})
        self.assertEqual((self.e.budget()["cap"], self.e.budget()["state"]), (200, "ok"))
        run_journey(self.e)
        self.assertEqual(self.e.meta["phase"], "accepted")

    def test_cap_below_floor_refused(self):
        self.e = Engine(self.tmp.path)
        self.e.create_company("X")
        with self.assertRaises(EngineError):
            self.e.set_guardrails(budget_cap=5)


class KillSwitchTests(Base):  # A14
    def test_freeze_mid_run_and_release(self):
        self.e = engine_to_running(self.tmp.path)
        self.e.step()
        self.e.kill_switch(True)
        self.assertEqual(self.e.step()["why"], "kill switch is on")
        r = self.e.gateway("w_pm", "t_01", "write_file", target="a.md", content="x")
        self.assertEqual(r["status"], "denied")
        self.e.kill_switch(False)
        run_journey(self.e)
        self.assertEqual(self.e.meta["phase"], "accepted")
        self.assertEqual(self.e.metrics()["founder_interventions"], 8, "6 decisions plus the switch on and off")


class ObjectiveTests(Base):  # A2
    def setUp(self):
        super().setUp()
        self.e = Engine(self.tmp.path)
        self.e.create_company("Harbor Recruiting")

    def test_inferred_fields_flagged_and_cleared_by_edit(self):
        o = self.e.draft_objective(SCENARIO["messy"])
        self.assertEqual(o["inferred_fields"], ["business_outcome", "priorities"])
        o = self.e.edit_objective({"priorities": "The stuck filter first"})
        self.assertEqual(o["inferred_fields"], ["business_outcome"])
        self.assertEqual(o["structured"]["priorities"], "The stuck filter first")

    def test_demo_mode_says_when_it_ignores_your_sentence(self):
        o = self.e.draft_objective("A cafe order board")
        self.assertIn("Demo mode only knows", o["notice"])

    def test_confirm_needs_every_field(self):
        self.e.draft_objective(SCENARIO["messy"])
        o = self.e.objective()
        o["structured"]["priorities"] = ""
        o["missing_fields"] = ["priorities"]
        self.e.store.put("objective", "obj_1", o)
        with self.assertRaises(EngineError):
            self.e.confirm_objective()

    def test_empty_objective_refused_and_phase_rules(self):
        with self.assertRaises(EngineError):
            self.e.draft_objective("   ")
        with self.assertRaises(EngineError):
            self.e.create_company("Again")
        with self.assertRaises(EngineError):
            self.e.confirm_objective()

    def test_change_during_a_run_pauses_d30(self):
        self.e.close()
        self.e = engine_to_running(self.tmp.path / "b")
        self.e.step()
        self.e.edit_objective({"constraints": "No public careers site, no email"})
        self.assertEqual(self.e.meta["phase"], "paused_objective")
        self.assertEqual(self.e.step()["did"], "idle")
        d = [x for x in self.e.pending_decisions() if x["kind"] == "objective_change"][0]
        self.assertIn("open tasks affected", " ".join(d["evidence_refs"]))
        self.e.decide(d["id"], "approve")
        o = self.e.objective()
        self.assertEqual((o["version"], o["structured"]["constraints"]), (2, "No public careers site, no email"))
        self.assertEqual(self.e.meta["phase"], "running")

    def test_change_rejected_keeps_version_one(self):
        self.e.close()
        self.e = engine_to_running(self.tmp.path / "c")
        self.e.edit_objective({"product": "Something else"})
        d = [x for x in self.e.pending_decisions() if x["kind"] == "objective_change"][0]
        self.e.decide(d["id"], "reject")
        self.assertEqual(self.e.objective()["version"], 1)
        self.assertEqual(self.e.objective()["structured"]["product"], "Internal candidate tracker")


class RestartTests(Base):
    def test_a_run_survives_a_restart(self):
        self.e = engine_to_running(self.tmp.path)
        self.e.run_until_idle()
        self.e.close()
        self.e = Engine(self.tmp.path)
        self.assertEqual(self.e.meta["phase"], "running")
        run_journey(self.e)
        self.assertEqual(self.e.meta["phase"], "accepted")


if __name__ == "__main__":
    unittest.main()
