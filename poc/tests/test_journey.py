"""The whole demo journey, end to end, through the engine, in the product definition's canonical flow:
objective, requirements, synthesized workforce (gate), intelligence, roadmap and budget (gate), governed
execution, verification, delivery (A1, A3, A4, A5, A7, A8, A11, A12, A13)."""
from __future__ import annotations

import json
import unittest
import urllib.request
import zipfile

from helpers import TempDir, engine_to_running, no_model_env, restore_env, run_journey

TWELVE = ["objective_id", "owner_worker_id", "context", "inputs", "expected_output", "dependencies", "tools",
          "budget_usd", "deadline_day", "verification_gate", "authority_policy_id", "status"]


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
        # submitting the objective, the workforce gate, the roadmap gate, and the four above
        self.assertEqual(self.e.metrics()["founder_interventions"], 7)
        risks = {d["kind"]: d["risk"] for d in self.answered}
        self.assertEqual(risks["decision"], "MEDIUM")
        self.assertEqual(risks["review_merge"], "MEDIUM")
        self.assertEqual(risks["deploy"], "HIGH")

    def test_objective_submitted_and_decomposed(self):  # A1, Stages 0 and 1
        o = self.e.objective()
        self.assertEqual((o["status"], o["version"], o["project"]), ("submitted", 1, "Harbor Recruiting"))
        req = self.e.requirements()
        self.assertEqual([r["id"] for r in req["requirements"]][:2], ["r_01", "r_02"])
        self.assertEqual(req["critical_path"], ["ws_01", "ws_02", "ws_03"])
        self.assertFalse([d for d in self.e.store.all("decision") if d["kind"] == "confirm_objective"],
                         "the founder specifies the outcome; there is no separate objective gate")

    def test_workforce_synthesized_then_approved(self):  # A3, Stages 2 and 3
        prop = self.e.proposal()
        self.assertEqual({r["role"]: r["quantity"] for r in prop["roles"]}, {"CTO": 1, "PM": 1, "Engineer": 2})
        self.assertTrue(all(r["why"] for r in prop["roles"]))
        self.assertTrue(all(prop["coverage"].values()), "every requirement covered by a proposed role")
        gate = [d for d in self.e.store.all("decision") if d["kind"] == "approve_workforce"][0]
        self.assertEqual(gate["outcome_label"], "approved")
        ws = self.e.store.all("worker")
        self.assertEqual(sorted(w["id"] for w in ws), ["w_cto", "w_eng_a", "w_eng_b", "w_pm"])
        self.assertEqual({w["id"]: w["reports_to"] for w in ws},
                         {"w_cto": "founder", "w_pm": "w_cto", "w_eng_a": "w_pm", "w_eng_b": "w_pm"},
                         "reporting lines generated from the roles present")
        org = self.e.store.get("organization", "org_1")
        self.assertEqual((org["proposal"], org["status"]), (prop["id"], "active"))

    def test_roadmap_and_budget_approved_separately(self):  # Stages 5, 6 and 7
        plan = self.e.store.get("plan", "plan_1")
        self.assertEqual([m["id"] for m in plan["milestones"]], ["m_1", "m_2", "m_3"])
        self.assertEqual(plan["critical_path"], ["t_01", "t_02", "t_03", "t_04", "t_05", "t_06"])
        self.assertTrue(plan["escalation_conditions"])
        for t in self.e.tasks():
            self.assertTrue(t["acceptance_criteria"] and t["verification_gate"] and t["accountable"], t["id"])
        self.assertEqual(self.e.task("t_03")["accountable"], "w_pm")
        f = self.e.store.get("forecast", "current")
        self.assertEqual(set(f["layers"]), {"inference", "tools", "infrastructure", "verification", "reserve"})
        self.assertTrue(f["fits"])
        self.assertEqual({r["task_id"] for r in f["tasks"]}, {t["id"] for t in self.e.tasks()})
        self.assertEqual(self.e.task("t_01")["kind"], "document")
        self.assertEqual(self.e.task("t_01")["documents"], ["product_spec", "acceptance"])
        kinds = [d["kind"] for d in self.e.store.all("decision")][:2]
        self.assertEqual(kinds, ["approve_workforce", "approve_roadmap"])

    def test_final_report(self):  # section 8, the last screen
        r = self.e.final_report()
        self.assertIn("app.py", r["artifacts"])
        self.assertTrue(r["live_url"])
        self.assertEqual({c["worker_id"] for c in r["performance"]}, {"w_cto", "w_pm", "w_eng_a", "w_eng_b"})
        eng = next(c for c in r["performance"] if c["worker_id"] == "w_eng_a")["overall"]
        self.assertEqual((eng["quality"]["verifications"], eng["quality"]["acceptance_rate"]), (2, 0.5))
        pack = r["company_pack"]  # what the founding team hands the CEO
        self.assertEqual([d["task"] for d in pack["documents"]], ["t_01"])
        self.assertTrue(pack["documents"][0]["verified"])
        self.assertIn("Product specification", pack["documents"][0]["types"])
        self.assertGreaterEqual(len(pack["ceo_decisions"]), 4, "the gates, the rule, the merge, the deploy")
        self.assertGreaterEqual(pack["settled_by_the_team"], 1, "a Blocker cleared without the CEO")
        self.assertGreater(pack["ceo_interventions"], 0)
        self.assertEqual(r["intelligence_changes"], [], "one scripted source: nothing to replace")
        m = r["metrics"]
        self.assertEqual((m["reworks"], m["defect_escapes"], m["false_rejections"]), (1, 0, 0))

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

    def test_the_orchestrator_implements_the_run_contract(self):
        from cynqra.run import Run
        self.assertIsInstance(self.e, Run)
        members = [k for k in Run.__dict__ if not k.startswith("_")] + list(Run.__annotations__)
        self.assertEqual([k for k in members if not hasattr(self.e, k)], [])

    def test_the_script_is_staffed_and_metered_like_a_model(self):  # WORKER is not MODEL, even in the demo
        view = self.e.workforce_view()
        self.assertEqual(view["models_in_use"], {"scripted-demo-candidate-tracker": ["w_cto", "w_pm", "w_eng_a", "w_eng_b"]})
        self.assertEqual([m["runtime"] for m in view["registry"]], ["scripted"])
        calls = self.e.store.all("call")
        self.assertTrue(calls and all(c["model_id"] == "scripted-demo-candidate-tracker" for c in calls))
        L = self.e.snapshot()["budget"]["ledger"]
        self.assertEqual((L["spent_total"], L["state"], L["warned"]), (0.0, "ok", []),
                         "a script costs nothing, and this machine's time is not priced by default")
        econ = self.e.final_report()["economics"]
        self.assertEqual((econ["total_actual"], econ["cap_usd"]), (0.0, 5.0))


class BluedipJourneyTests(unittest.TestCase):
    """The demo that opens first. A founder describes Bluedip, an app that predicts a restaurant's footfall and
    revenue hour by hour and estimates what an offer will do before it runs. The team the idea needs lays the
    company's foundation, builds and checks the models and the app, and hands the CEO the Company Pack."""

    @classmethod
    def setUpClass(cls):
        cls.saved = no_model_env()
        cls.tmp = TempDir()
        cls.e = engine_to_running(cls.tmp.path, scenario="bluedip")
        cls.answered = run_journey(cls.e)

    @classmethod
    def tearDownClass(cls):
        cls.e.close()
        cls.tmp.cleanup()
        restore_env(cls.saved)

    def call(self, path, body=None):
        req = urllib.request.Request(self.e.live_url() + path, data=None if body is None else json.dumps(body).encode(),
                                     method="POST" if body is not None else "GET",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def test_the_team_follows_the_idea(self):
        titles = sorted(w["title"] for w in self.e.workers())
        self.assertEqual(titles, sorted(["Business Lead", "Project Manager", "Senior Data Scientist",
                                         "Restaurant Revenue Management Specialist", "CFO", "Market Analyst",
                                         "Legal and Compliance Advisor", "CTO", "Software Engineer"]))

    def test_the_company_pack_holds_the_foundation_all_checked(self):
        self.assertEqual(self.e.meta["phase"], "accepted")
        pack = self.e.final_report()["company_pack"]
        authors = {d["author"] for d in pack["documents"] if d["verified"]}
        self.assertTrue({"Business Lead", "Market Analyst", "Restaurant Revenue Management Specialist",
                         "Legal and Compliance Advisor", "CFO", "Senior Data Scientist", "Project Manager"} <= authors)
        docs = self.e.paths["main"] / "docs"
        for name, marks in (("market_analysis.md", ["Assumption", "No market-size figure"]),
                            ("revenue_management_report.md", ["Sourced", "Confirm with a professional"]),
                            ("compliance_register.md", ["Sourced", "Assumption", "Confirm with a professional"]),
                            ("financial_model.md", ["assumption", "month 19", "₹85 lakh"]),
                            ("business_brief.md", ["**What.**", "**Why.**", "**How.**"])):
            text = (docs / name).read_text(encoding="utf-8")
            for m in marks:
                self.assertIn(m, text, f"{name}: trust is the product")

    def test_the_checks_caught_two_mistakes_before_they_counted(self):
        vs = {t: [v["verdict"] for v in self.e.store.all("verification") if v["task_id"] == t] for t in ("t_06", "t_10")}
        self.assertEqual(vs, {"t_06": ["REQUIRES_REWORK", "VERIFIED"], "t_10": ["REQUIRES_REWORK", "VERIFIED"]})
        first = next(v for v in self.e.store.all("verification") if v["task_id"] == "t_06")
        self.assertGreater(first["checks"]["backtest"]["model_mae"], first["checks"]["backtest"]["baseline_mae"])

    def test_a_doubt_went_to_the_right_colleague_not_the_ceo(self):
        cleared = self.e.store.all("blocker_cleared")
        self.assertEqual([(b["task_id"], b["by"], b["founder_involved"]) for b in cleared],
                         [("t_10", "w_spec_revenue_management", False)])

    def test_the_ceo_decided_only_ceo_questions(self):
        self.assertEqual([d["kind"] for d in self.answered], ["decision", "review_merge", "deploy", "accept_delivery"])
        self.assertEqual(self.answered[0]["source"], "w_cfo")
        self.assertIn("50%", (self.e.paths["main"] / "docs" / "DECISIONS.md").read_text(encoding="utf-8"))

    def test_the_live_app_shows_the_owners_example_loses_money_and_a_better_offer(self):
        day = self.call("/api/day")
        self.assertEqual([r["slot"] for r in day["recommendations"]], ["breakfast", "lunch", "dinner"])
        lunch = next(s for s in day["slots"] if s["slot"] == "lunch")
        self.assertEqual(lunch["quiet"], [13, 16], "1 pm to 4 pm")
        r = self.call("/api/offers/estimate", {"start": 13, "end": 16, "discount": 0.5, "cap": 15})
        self.assertLessEqual(r["estimate"]["customers_using"], 15)
        if r["estimate"]["expected_without"] > 5:
            self.assertGreater(r["estimate"]["revenue_change"], 0)
            self.assertLess(r["estimate"]["margin_change"], 0)
            self.assertGreater(r["better"]["margin_change"], 0)

    def test_every_task_replays_completely(self):
        for t in self.e.tasks():
            self.assertTrue(self.e.replay(t["id"])["complete"], t["id"])


class RestaurantJourneyTests(unittest.TestCase):
    """The second demo: a nine-worker organization, seven documents, a forecast the platform backtests (its first
    method fails and is reworked), a store, an app, acceptance tests, a merge and a deploy by DevOps."""

    @classmethod
    def setUpClass(cls):
        cls.saved = no_model_env()
        cls.tmp = TempDir()
        cls.e = engine_to_running(cls.tmp.path, scenario="restaurant_forecast")
        cls.answered = run_journey(cls.e)

    @classmethod
    def tearDownClass(cls):
        cls.e.close()
        cls.tmp.cleanup()
        restore_env(cls.saved)

    def test_accepted_and_the_forecast_is_live(self):
        self.assertEqual(self.e.meta["phase"], "accepted")
        self.assertEqual([t["status"] for t in self.e.tasks()], ["VERIFIED"] * 14)
        with urllib.request.urlopen(self.e.live_url() + "/api/forecast", timeout=5) as r:
            f = json.loads(r.read())
        self.assertEqual(len(f["days"]), 14)
        self.assertTrue(all(d["prep"] >= d["covers"] for d in f["days"]))

    def test_the_organization_was_synthesized_for_the_objective(self):
        roles = sorted(w["role"] for w in self.e.workers())
        self.assertEqual(roles, sorted(["CEO", "CTO", "PM", "DataScientist", "BackendEngineer", "FrontendEngineer",
                                        "Designer", "DevOps", "QA"]))
        self.assertEqual(self.e.worker("w_ceo")["reports_to"], "founder")
        self.assertEqual(self.e.worker("w_ds")["reports_to"], "w_ceo")
        self.assertEqual(self.e.worker("w_devops")["reports_to"], "w_pm")

    def test_the_backtest_rejected_the_first_forecast(self):
        vs = [v for v in self.e.store.all("verification") if v["task_id"] == "t_07"]
        self.assertEqual([v["verdict"] for v in vs], ["REQUIRES_REWORK", "VERIFIED"])
        self.assertFalse(vs[0]["checks"]["backtest"]["passed"])
        self.assertEqual(vs[0]["checks"]["failed"], [], "its own tests passed: only the backtest caught it")
        self.assertLess(vs[1]["checks"]["backtest"]["model_mae"], vs[1]["checks"]["backtest"]["baseline_mae"])
        self.assertIn("backtest", self.e.task("t_07")["verification_gate"])

    def test_documents_by_type_reached_the_repository(self):
        docs = sorted(p.name for p in (self.e.paths["main"] / "docs").iterdir())
        self.assertEqual(docs, ["DECISIONS.md", "acceptance.md", "architecture.md", "business_brief.md", "design.md",
                                "method.md", "product_spec.md", "runbook.md", "test_plan.md"])
        self.assertIn("plus 10 percent", (self.e.paths["main"] / "docs" / "DECISIONS.md").read_text())

    def test_the_founder_saw_only_what_needed_them(self):
        self.assertEqual([d["kind"] for d in self.answered], ["decision", "review_merge", "deploy", "accept_delivery"])
        self.assertEqual(self.answered[2]["source"], "w_devops", "DevOps proposed the deploy")
        self.assertEqual(self.e.metrics()["founder_interventions"], 7)

    def test_every_task_replays_completely(self):
        for t in self.e.tasks():
            self.assertTrue(self.e.replay(t["id"])["complete"], t["id"])


if __name__ == "__main__":
    unittest.main()
