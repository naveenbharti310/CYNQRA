"""A company that keeps running: decisions that can be undone are settled by the cofounder accountable for them;
after launch the work continues in cycles on the live product, from what users said; the founder's update is plain
and built from the record; the company's foundations are listed with what prepared them; and Cynqra remembers how
earlier projects went."""
from __future__ import annotations

import unittest
import urllib.request

from helpers import SCENARIO, TempDir, approve, engine_to_running, no_model_env, restore_env, run_journey

from cynqra import execution, lessons
from cynqra.engine import Engine, EngineError
from cynqra.intelligence import IntelligenceError


class DoorTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_what_can_be_undone_and_what_cannot(self):
        e = engine_to_running(self.tmp.path, scenario="bluedip")
        kinds = {t["id"]: execution.door(e, t)[0] for t in e.tasks() if t["kind"] in ("decision", "review_merge", "deploy")}
        self.assertEqual(kinds, {"t_08": "one_way", "t_16": "two_way", "t_17": "one_way"},
                         "a rule on money and going live are the founder's; a merge can be undone")
        e.close()

    def test_governance_can_send_every_decision_to_the_founder(self):
        e = engine_to_running(self.tmp.path, governance={"cofounders_settle_reversible": False})
        answered = run_journey(e)
        self.assertEqual([d["kind"] for d in answered], ["decision", "review_merge", "deploy", "accept_delivery"])
        self.assertFalse([d for d in e.store.all("decision") if d["outcome_label"] == "settled_by_cofounder"])
        e.close()


class CycleTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()
        self.e = engine_to_running(self.tmp.path / "run1")

    def tearDown(self):
        self.e.close()
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_a_cycle_needs_a_delivered_product_and_something_to_do(self):
        with self.assertRaises(EngineError):
            self.e.start_cycle("more")
        run_journey(self.e)
        with self.assertRaises(EngineError):
            self.e.start_cycle("")
        with self.assertRaises(EngineError):
            self.e.feedback("  ")

    def test_the_next_cycle_builds_what_users_asked_for_and_puts_it_live(self):
        run_journey(self.e)
        self.assertTrue(self.e.check_live()["ok"])
        fb = self.e.feedback("The recruiters cannot tell how long someone has been waiting.")
        cap = self.e.store.get("settings", "project")["budget_usd"]
        self.e.start_cycle("Show how many days each candidate has been in its stage.", budget_usd=2)
        self.assertEqual(self.e.store.get("settings", "project")["budget_usd"], cap + 2)
        self.assertEqual(self.e.store.get("feedback", fb["id"])["used_in"], 2)
        road = next(d for d in self.e.pending_decisions() if d["kind"] == "approve_roadmap")
        self.assertIn("Cycle 2 on the live product: 3 tasks", road["problem"])
        self.assertIn("cannot tell how long", road["problem"], "what users said goes into the plan")
        approve(self.e, "approve_roadmap")
        answered = run_journey(self.e)
        self.assertEqual(self.e.meta["phase"], "accepted", self.e.meta.get("notice"))
        self.assertEqual([d["kind"] for d in answered], ["deploy", "accept_delivery"],
                         "the CTO merged; the founder only put it live and accepted it")
        new = [t for t in self.e.tasks() if t.get("cycle") == 2]
        self.assertEqual([(t["id"], t["status"]) for t in new],
                         [("t_07", "VERIFIED"), ("t_08", "VERIFIED"), ("t_09", "VERIFIED")])
        self.assertEqual(len(self.e.tasks()), 9, "the first cycle's work stays on the record")
        page = urllib.request.urlopen(self.e.live_url() + "/", timeout=5).read().decode()
        self.assertIn("Days in stage", page, "release 1.1 is what is live")
        self.assertEqual(self.e.store.get("transition", "tr_2")["cycle"], 2)
        self.assertEqual(self.e.store.get("plan", "plan_1")["earlier_cycles"][0]["cycle"], 1)

    def test_a_demo_without_a_script_for_the_cycle_stops_plainly(self):
        run_journey(self.e)
        self.e.start_cycle("Days in stage.")
        approve(self.e, "approve_roadmap")
        run_journey(self.e)
        with self.assertRaises(IntelligenceError):
            self.e.start_cycle("Something else.")
        self.assertEqual(self.e.meta["phase"], "stopped_error")
        self.assertIn("no plan for cycle 3", self.e.meta["notice"])

    def test_a_rejected_delivery_can_be_fixed_in_a_cycle(self):
        for _ in range(20):
            self.e.run_until_idle()
            d = next((x for x in self.e.pending_decisions() if x["kind"] == "accept_delivery"), None)
            if d:
                break
            self.e.decide(self.e.pending_decisions()[0]["id"], "approve")
        self.e.decide(d["id"], "reject", note="Show the days in stage.")
        self.assertEqual(self.e.meta["phase"], "delivered")
        self.e.start_cycle("Show the days in stage.")
        self.assertEqual(self.e.meta["phase"], "planning")


class UpdateAndMemoryTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_the_update_says_what_needs_the_founder_and_what_was_settled(self):
        e = engine_to_running(self.tmp.path)
        e.run_until_idle()
        u = e.update()
        self.assertEqual([w["what"][:15] for w in u["waiting_for_you"]], ["Release 1 is me"],
                         "the only thing waiting is going live")
        self.assertIn("Chief Product Officer", [d["by"] for d in u["decided"]])
        self.assertEqual(u["numbers"]["tasks"], 6)
        e.close()

    def test_the_foundations_say_what_the_work_prepared(self):
        e = engine_to_running(self.tmp.path, scenario="bluedip")
        run_journey(e, max_rounds=40)
        f = {x["what"]: x for x in e.final_report()["company_pack"]["foundations"]}
        self.assertIn("Risk and compliance register", f["Register the company"]["prepared_in"])
        self.assertIn("a professional should review it", f["Register the company"]["status"])
        self.assertIn("Financial model", f["Tax registration and invoicing"]["prepared_in"])
        e.close()

    def test_the_next_project_like_this_one_gets_a_track_record(self):
        memory = self.tmp.path / "lessons.json"  # the app keeps one memory beside every run
        first = engine_to_running(self.tmp.path / "a", memory=memory)
        run_journey(first)
        first.close()
        self.assertEqual(len(lessons.load(first)), 1)
        second = Engine(self.tmp.path / "b", memory=memory)
        second.create_company("C", "demo", "candidate_tracker")
        second.draft_objective(SCENARIO["messy"])
        second.submit_objective()
        why = " ".join(second.proposal()["why_team"]["lines"])
        self.assertIn("1 earlier project covered the same kinds of work, 1 delivered and accepted", why)
        second.close()


if __name__ == "__main__":
    unittest.main()
