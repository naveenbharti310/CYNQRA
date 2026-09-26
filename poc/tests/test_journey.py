"""The whole demo journey, end to end, through the engine (A1, A3, A4, A5, A7, A8, A11, A12, A13)."""
from __future__ import annotations

import json
import unittest
import urllib.request
import zipfile

from helpers import TempDir, engine_to_running, no_model_env, restore_env, run_journey

TWELVE = ["objective_id", "owner_worker_id", "context", "inputs", "expected_output", "dependencies", "tools",
          "budget", "deadline_day", "verification_method", "authority_policy_id", "status"]


class JourneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = no_model_env()
        cls.tmp = TempDir()
        cls.e = engine_to_running(cls.tmp.path)
        cls.answered = run_journey(cls.e)

    @classmethod
    def tearDownClass(cls):
        cls.e.close()
        cls.tmp.cleanup()
        restore_env(cls.saved)

    def test_reaches_accepted_with_a_live_product(self):
        self.assertEqual(self.e.meta["phase"], "accepted")
        url = self.e.live_url()
        self.assertTrue(url)
        with urllib.request.urlopen(url + "/health", timeout=5) as r:
            self.assertEqual(json.loads(r.read()), {"ok": True})
        with urllib.request.urlopen(url + "/", timeout=5) as r:
            self.assertIn(b"Candidate tracker", r.read())

    def test_every_task_verified(self):
        self.assertEqual([t["status"] for t in self.e.tasks()], ["VERIFIED"] * 6)

    def test_founder_only_sees_what_needs_them(self):
        kinds = [d["kind"] for d in self.answered]
        self.assertEqual(kinds, ["decision", "review_merge", "deploy", "accept_delivery"])
        self.assertEqual(self.e.metrics()["founder_interventions"], 6)
        risks = {d["kind"]: d["risk"] for d in self.answered}
        self.assertEqual(risks["decision"], "MEDIUM")
        self.assertEqual(risks["review_merge"], "MEDIUM")
        self.assertEqual(risks["deploy"], "HIGH")

    def test_objective_confirmed_and_versioned(self):  # A1
        o = self.e.objective()
        self.assertEqual((o["status"], o["version"], o["confirmed_by"]), ("confirmed", 1, "founder"))
        confirm = self.e.store.get("decision", "dec_confirm_objective")
        self.assertEqual(confirm["outcome_label"], "approved")

    def test_exactly_the_fixed_template(self):  # A3
        ws = self.e.store.all("worker")
        self.assertEqual(sorted(w["id"] for w in ws), ["w_cto", "w_eng_a", "w_eng_b", "w_pm"])
        org = self.e.store.get("organization", "org_1")
        self.assertEqual(org["template"], "fixed_mvp_4")
        self.assertEqual(org["status"], "active")

    def test_graph_answers_owner_dependency_approver(self):  # A4
        self.assertEqual(self.e.graph("owns", "t_04")["owner"], "w_eng_b")
        self.assertEqual(self.e.graph("depends", "t_03")["needed_by"], ["t_04", "t_05"])
        self.assertEqual(self.e.graph("approves", "deploy_production")["approves"], "founder")

    def test_every_task_has_the_twelve_fields(self):  # A5
        for t in self.e.tasks():
            for f in TWELVE:
                self.assertIn(f, t, (t["id"], f))
            self.assertIn(t["risk_tier"], ("LOW", "MEDIUM", "HIGH"))

    def test_blocker_resolved_without_the_founder(self):  # A7
        m = self.e.metrics()
        self.assertEqual(m["blockers_cleared_without_founder"], 1)
        kinds = [p["kind"] for p in self.e.store.all("protocol")]
        for k in ("Handoff", "Blocker", "Approval"):
            self.assertIn(k, kinds)
        t4 = self.e.task("t_04")
        self.assertEqual(t4["blockers"], 1)
        founder_on_t4 = [d for d in self.answered if d.get("task_id") == "t_04"]
        self.assertEqual(founder_on_t4, [])

    def test_defect_caught_before_verified(self):  # A8
        vs = [v for v in self.e.store.all("verification") if v["task_id"] == "t_03"]
        self.assertEqual([v["verdict"] for v in vs], ["REQUIRES_REWORK", "VERIFIED"])
        self.assertEqual(self.e.metrics()["defects_caught_before_verified"], 1)
        t4v = [v for v in self.e.store.all("verification") if v["task_id"] == "t_04"][-1]
        self.assertIn("test_store.test_list_returns_all", t4v["test_ids"], "prior tests rerun on t_04")

    def test_completed_is_separate_from_verified(self):  # A8
        types = [e["event_type"] for e in self.e.store.events(correlation_id="t_03")]
        self.assertLess(types.index("task.completed"), types.index("task.verified"))

    def test_prohibited_action_denied_without_the_founder(self):  # A13
        denied = [a for a in self.e.store.all("action") if a["status"] == "denied"]
        self.assertEqual([a["action_type"] for a in denied], ["external_message"])
        self.assertEqual(self.e.metrics()["actions_stopped_by_policy"], 1)

    def test_replay_is_complete_for_every_task(self):  # A11
        for t in self.e.tasks():
            r = self.e.replay(t["id"])
            self.assertTrue(r["complete"], (t["id"], r["missing"]))
        self.assertTrue(self.e.replay("t_04")["test_ids"])

    def test_no_personal_data_in_events(self):  # D-22
        blob = json.dumps([e["payload"] for e in self.e.store.events()])
        for name in ("Priya Shah", "Jordan Lee", "Smoke check"):
            self.assertNotIn(name, blob)

    def test_deployment_record_and_export(self):  # A12
        dep = self.e.store.all("deployment")[-1]
        stages = [x["stage"] for x in dep["log"]]
        self.assertEqual(stages, ["BUILD", "TEST", "PACKAGE", "PREVIEW", "VERIFY", "APPROVAL", "DEPLOY",
                                  "HEALTH_CHECK", "SMOKE_TEST", "LIVE"])
        self.assertEqual(dep["approved_by"], "founder")
        exports = list(self.e.paths["exports"].glob("*.zip"))
        self.assertTrue(exports)
        with zipfile.ZipFile(exports[0]) as z:
            man = json.loads(z.read("manifest.json"))
            for cat in ("repository", "documents_and_designs", "decision_history", "event_log",
                        "organization_configuration", "infrastructure_configuration"):
                self.assertIn(cat, man["categories"])
            self.assertIn("repository/app.py", z.namelist())
            self.assertTrue(man["non_portable"])

    def test_transition_and_outcome_recorded(self):
        tr = self.e.store.get("transition", "tr_1")
        self.assertEqual(tr["approval"]["by"], "founder")
        types = {e["event_type"] for e in self.e.store.events()}
        for t in ("transition.proposed", "transition.approved", "transition.executed", "outcome.recorded"):
            self.assertIn(t, types)

    def test_budget_warned_at_fifty(self):  # A10, happy path
        b = self.e.budget()
        self.assertEqual(b["warned"], [50])
        self.assertLess(b["spent"], b["cap"])

    def test_evolution_is_view_only(self):
        ev = self.e.evolution()
        self.assertIn("recommendation only", ev["status"])
        self.assertEqual(ev["title"], "Keep the organization as it is")


if __name__ == "__main__":
    unittest.main()
