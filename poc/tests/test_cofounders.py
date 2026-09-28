"""Cofounders run their areas: the limits that keep a cofounder's review from stalling the company, and the
Blocker nobody in the company can answer. The journeys (test_journey) show the normal path: every team member's
work handed out, answered and reviewed by its cofounder."""
from __future__ import annotations

import unittest

from helpers import TempDir, engine_to_running, no_model_env, restore_env, run_journey

from cynqra import execution, planner, roles
from cynqra.engine import Engine, EngineError
from cynqra.intelligence import ScriptedSource


class Relentless(ScriptedSource):
    """A demo team whose cofounders send every piece of work back."""

    def review(self, task, worker="system", round_index=0, **_):
        return {"verdict": "revise", "note": f"Change it again (round {round_index + 1})."}, self._usage(worker)


class Garbled(ScriptedSource):
    """A demo team whose cofounders answer a review with something that is not a review."""

    def review(self, task, worker="system", **_):
        return {"verdict": "maybe", "note": ""}, self._usage(worker)


class ReviewLimitsTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_a_cofounder_sends_work_back_twice_then_the_checks_decide_and_the_concern_is_kept(self):
        e = engine_to_running(self.tmp.path, intelligence=Relentless("candidate_tracker"))
        run_journey(e, max_rounds=40)
        self.assertEqual(e.meta["phase"], "accepted", e.meta.get("notice"))
        reviewed = [t for t in e.tasks() if t.get("reviewed_by")]
        self.assertTrue(reviewed)
        for t in reviewed:
            self.assertEqual(t["review_rounds"], execution.MAX_SEND_BACKS, t["id"])
            self.assertEqual(t["review_concern"]["outcome"], "concern_recorded", t["id"])
            self.assertEqual(t["status"], "VERIFIED", t["id"])
        m = e.metrics()
        self.assertEqual(m["sent_back_by_cofounders"], execution.MAX_SEND_BACKS * len(reviewed))
        self.assertEqual({c["task"] for c in m["review_concerns"]}, {t["id"] for t in reviewed},
                         "every concern stays on the record for the CEO")
        decision = next(d for d in e.store.all("decision") if d["kind"] == "decision")
        self.assertNotIn("endorsed_by", decision["extra"], "a proposal the cofounder did not approve is not endorsed")
        e.close()

    def test_an_unreadable_review_is_asked_again_then_the_work_goes_on_and_it_is_said(self):
        e = engine_to_running(self.tmp.path, intelligence=Garbled("candidate_tracker"))
        run_journey(e, max_rounds=40)
        self.assertEqual(e.meta["phase"], "accepted", e.meta.get("notice"))
        t = e.task("t_03")
        self.assertEqual(t["review_concern"]["outcome"], "skipped")
        self.assertIn("could not be read", t["review_concern"]["note"])
        self.assertFalse(t.get("reviews"), "nothing unreadable is recorded as a review")
        e.close()


class ReportingLineTests(unittest.TestCase):
    def test_a_team_member_reports_to_a_cofounder_who_may_lead_it(self):
        cofs = ["CTO", "CPO", "CFO"]
        self.assertEqual(roles.lead_role("Engineer", cofs, "CFO"), "CTO", "an engineer is never under the CFO")
        self.assertEqual(roles.lead_role("LegalAdvisor", cofs, "CFO"), "CFO", "the CFO may lead legal")
        self.assertEqual(roles.lead_role("MarketAnalyst", cofs, None), "CPO")
        self.assertEqual(roles.lead_role("Designer", ["CTO"], None), "CTO", "without a CPO, the CTO leads design")
        self.assertEqual(roles.lead_role("MarketAnalyst", ["CTO"], "CTO"), "CTO", "no preferred lead present")
        self.assertIsNone(roles.lead_role("CTO", cofs, None), "a cofounder reports to the founder")


class OutdatedProjectTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_a_project_saved_with_roles_that_no_longer_exist_stops_with_a_plain_reason(self):
        e = engine_to_running(self.tmp.path, scenario="restaurant_forecast")
        w = e.worker("w_cpo")
        w["role"] = "CEO"  # as a project saved before the founder became the CEO stored its Business Lead
        e.store.put("worker", "w_cpo", w)
        e.close()
        e = Engine(self.tmp.path)
        try:
            self.assertEqual((e.meta["phase"], e.meta["failed_stage"]), ("stopped_error", "outdated"))
            self.assertIn("earlier version of Cynqra", e.meta["notice"])
            self.assertEqual(e.step()["did"], "idle")
            with self.assertRaises(EngineError):
                e.resume()
            self.assertTrue(e.snapshot()["workers"], "it can still be read")
        finally:
            e.close()


class NobodyCanAnswerTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_a_lone_cofounders_doubt_goes_to_the_ceo(self):
        workers = roles.instantiate([{"role": "CTO", "quantity": 1}, {"role": "Engineer", "quantity": 1}])
        by = {w["id"]: w for w in workers}
        self.assertEqual(planner.coordination(by["w_eng"], workers)["blockers_to"], ["w_cto"],
                         "an engineer's doubt goes to its cofounder")
        self.assertEqual(planner.coordination(by["w_cto"], workers)["blockers_to"], ["founder"],
                         "nobody else in the company can answer the CTO")

    def test_a_blocker_to_the_ceo_is_an_escalation_never_an_invented_answer(self):
        e = engine_to_running(self.tmp.path)
        t = e.task("t_05")
        t.update({"status": "BLOCKED", "blocker": {"needs_from": "founder", "description": "Which host runs it?",
                                                  "raised_by": "w_cto"}})
        e.save_task(t)
        r = execution.answer(e, t)
        self.assertEqual(r["did"], "escalated")
        d = next(x for x in e.pending_decisions() if x["kind"] == "escalation")
        self.assertIn("Which host runs it?", d["problem"])
        e.close()


if __name__ == "__main__":
    unittest.main()
