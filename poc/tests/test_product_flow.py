"""The product definition's canonical flow (Cynqra Product Flows and Architecture v1), piece by piece:
the role catalog, requirement decomposition, workforce synthesis and its gate, the roadmap gate, the Budget
Engine, the Performance Engine's signals and the gateway's output sanitizing."""
from __future__ import annotations

import json
import unittest

from helpers import SCENARIO, TempDir, approve, no_model_env, restore_env

from cynqra import budget, performance, policy, roles
from cynqra.engine import Engine
from cynqra.intelligence import IntelligenceError, ScriptedSource, validate_requirements, validate_workforce
from cynqra.synthesis import OverrideRefused

# The restaurant demand forecasting example of section 6, as requirements and the section 3 workforce table.
RESTAURANT_REQ = {"outcomes": ["Restaurants plan staff and stock from a demand forecast"], "requirements": [
    {"id": "a", "area": "product", "text": "Restaurants see tomorrow's covers per service", "verification": "demo"},
    {"id": "b", "area": "data", "text": "Ingest a restaurant's past orders", "verification": "row checks"},
    {"id": "c", "area": "AI/ML", "text": "Forecast demand per day and service", "verification": "backtest error"},
    {"id": "d", "area": "functional", "text": "An API for the forecast", "verification": "API tests"},
    {"id": "e", "area": "UX", "text": "A dashboard of the forecast", "verification": "page test"},
    {"id": "f", "area": "security", "text": "Each restaurant sees only its own data", "verification": "access tests"},
    {"id": "g", "area": "testing", "text": "Regression and acceptance tests", "verification": "suite passes"},
    {"id": "h", "area": "deployment", "text": "Deployed with monitoring", "verification": "health and smoke"}],
    "workstreams": [{"id": "data", "name": "Data", "requirement_ids": ["b"], "depends_on": []},
                    {"id": "ml", "name": "Forecasting", "requirement_ids": ["c"], "depends_on": ["data"]},
                    {"id": "app", "name": "Product", "requirement_ids": ["a", "d", "e", "f"], "depends_on": ["ml"]},
                    {"id": "ops", "name": "Release", "requirement_ids": ["g", "h"], "depends_on": ["app"]}]}
RESTAURANT_ORG = {"summary": "Section 3's example organization", "roles": [
    {"role": "CEO", "quantity": 1, "why": "Business direction and outcome ownership", "requirement_ids": ["a"]},
    {"role": "CTO", "quantity": 1, "why": "Architecture and engineering accountability", "requirement_ids": ["f"]},
    {"role": "CPO", "quantity": 1, "why": "Product definition and customer workflow", "requirement_ids": ["a"]},
    {"role": "DataScientist", "quantity": 1, "why": "Forecasting and evaluation", "requirement_ids": ["b", "c"]},
    {"role": "PM", "quantity": 1, "why": "Coordination and milestones", "requirement_ids": []},
    {"role": "BackendEngineer", "quantity": 2, "why": "Data services and APIs", "requirement_ids": ["d"]},
    {"role": "FrontendEngineer", "quantity": 2, "why": "Dashboards and workflows", "requirement_ids": ["e"]},
    {"role": "Designer", "quantity": 1, "why": "UX and the design system", "requirement_ids": ["e"]},
    {"role": "DevOps", "quantity": 1, "why": "CI/CD, deployment and observability", "requirement_ids": ["h"]},
    {"role": "QA", "quantity": 1, "why": "Test strategy and acceptance validation", "requirement_ids": ["g"]}]}


class CatalogAndSynthesisTests(unittest.TestCase):
    def setUp(self):
        self.req = validate_requirements(json.loads(json.dumps(RESTAURANT_REQ)))

    def test_requirements_are_the_platforms_ids_areas_and_critical_path(self):
        r = self.req
        self.assertEqual([x["id"] for x in r["requirements"]], [f"r_0{i}" for i in range(1, 9)])
        self.assertEqual([x["area"] for x in r["requirements"]][2:7], ["ai_ml", "functional", "design", "security", "qa"])
        self.assertEqual(r["critical_path"], ["ws_01", "ws_02", "ws_03", "ws_04"])
        self.assertEqual(r["workstreams"][2]["requirement_ids"], ["r_01", "r_04", "r_05", "r_06"])
        with self.assertRaises(IntelligenceError):
            validate_requirements({"requirements": [{"area": "astrology", "text": "x"}]})
        loose = validate_requirements({"requirements": [{"area": "qa", "text": "x"}], "workstreams": []})
        self.assertEqual(loose["workstreams"][0]["placed_by"], "platform")

    def test_section_three_organization_is_synthesized_with_its_reporting_lines(self):
        prop = validate_workforce(json.loads(json.dumps(RESTAURANT_ORG)), self.req)
        ws = prop["workers"]
        self.assertEqual(len(ws), 12, "the twelve workers of the section 3 table")
        lines = {w["id"]: w["reports_to"] for w in ws}
        self.assertEqual(lines["w_ceo"], "founder")
        for top in ("w_cto", "w_cpo", "w_pm", "w_ds"):
            self.assertEqual(lines[top], "w_ceo", top)
        for low in ("w_be_a", "w_be_b", "w_fe_a", "w_fe_b", "w_design", "w_devops", "w_qa"):
            self.assertEqual(lines[low], "w_pm", low)
        self.assertTrue(all(prop["coverage"].values()), "every requirement covered")
        self.assertEqual(roles.assigner(ws), "w_pm")

    def test_the_synthesizer_cannot_leave_the_pipeline_unstaffed_or_exceed_the_catalog(self):
        def bad(change):
            org = json.loads(json.dumps(RESTAURANT_ORG))
            change(org)
            with self.assertRaises(IntelligenceError):
                validate_workforce(org, self.req)
        bad(lambda o: o["roles"].append({"role": "Astrologer", "quantity": 1, "why": "x", "requirement_ids": []}))
        bad(lambda o: o["roles"][0].update(quantity=2))  # one CEO at most
        bad(lambda o: o.update(roles=[r for r in o["roles"] if r["role"] != "CTO"]))  # nobody reviews and merges
        bad(lambda o: o.update(roles=[r for r in o["roles"] if r["role"] not in ("DataScientist",)]))  # ai_ml uncovered
        bad(lambda o: o["roles"][1].update(why=""))

    def test_authority_comes_from_the_catalog(self):
        self.assertEqual(policy.MATRIX, roles.matrix())
        self.assertEqual(policy.evaluate(role="DevOps", action_type="deploy_production")["decision"], "REQUIRE_APPROVAL")
        self.assertEqual(policy.evaluate(role="Designer", action_type="merge_to_main")["decision"], "DENY")
        self.assertEqual(policy.evaluate(role="QA", action_type="review_work")["decision"], "ALLOW")
        self.assertEqual(roles.instantiate(roles.FIXTURE_M1)[0]["reports_to"], "founder", "the M1 fixture")


class GateTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()
        self.e = Engine(self.tmp.path)
        self.e.create_company("Harbor Recruiting")
        self.e.draft_objective(SCENARIO["messy"])
        self.e.set_guardrails(budget_usd=3, constraints={"deadline": "two weeks", "geography": "", "nonsense": "x"})
        self.e.submit_objective()

    def tearDown(self):
        self.e.close()
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_stage_zero_constraints_reach_the_workers(self):
        self.assertEqual(self.e.objective()["founder_constraints"], {"deadline": "two weeks"})
        self.assertEqual(self.e.objective_ctx()["_constraints"], {"deadline": "two weeks"})

    def test_rejecting_the_workforce_revises_it_with_the_feedback(self):
        approve(self.e, "approve_workforce", "reject", note="Too many engineers")
        self.assertEqual(self.e.meta["phase"], "workforce")
        self.assertEqual(self.e.proposal()["id"], "wp_2")
        self.assertEqual(self.e.proposal()["note"], "Too many engineers")
        self.assertEqual(self.e.store.get("proposal", "wp_1")["status"], "rejected")
        self.assertFalse(self.e.store.all("worker"), "nobody is hired before the founder approves")

    def test_editing_the_workforce_needs_the_governance_policy(self):
        edit = {"roles": [{"role": "CTO", "quantity": 1, "why": "x"}, {"role": "PM", "quantity": 1, "why": "x"},
                          {"role": "Engineer", "quantity": 1, "why": "x"}]}
        with self.assertRaises(OverrideRefused):
            approve(self.e, "approve_workforce", edited=edit)

    def test_an_allowed_override_is_checked_and_recorded(self):
        s = self.e.wf  # no registry in this engine: governance lives in the run's settings
        self.assertIsNone(s)
        from cynqra.workforce import Workforce
        st = Workforce.settings(self.e.store)
        st["allow_workforce_override"] = True
        self.e.store.put("workforce", "settings", st)
        edit = {"roles": [{"role": "CTO", "quantity": 1, "why": "x"}, {"role": "PM", "quantity": 1, "why": "x"},
                          {"role": "Engineer", "quantity": 2, "why": "x"},
                          {"role": "QA", "quantity": 1, "why": "the founder wants a QA engineer"}]}
        d = approve(self.e, "approve_workforce", edited=edit)
        self.assertEqual(d["outcome_label"], "approved_edited")
        self.assertEqual(sorted(w["id"] for w in self.e.workers()), ["w_cto", "w_eng_a", "w_eng_b", "w_pm", "w_qa"])
        self.assertEqual(self.e.worker("w_qa")["reports_to"], "w_pm")
        self.assertTrue(self.e.proposal()["overridden"])
        self.assertIn("workforce.overridden", [x["event_type"] for x in self.e.store.events()])

    def test_the_roadmap_is_a_separate_gate_and_can_be_rejected(self):
        approve(self.e, "approve_workforce")
        self.assertEqual(self.e.meta["phase"], "planning")
        approve(self.e, "approve_roadmap", "reject", note="Split the web app task")
        pend = self.e.pending_decisions()
        self.assertEqual([d["kind"] for d in pend], ["approve_roadmap"])
        approve(self.e, "approve_roadmap")
        self.assertEqual(self.e.meta["phase"], "running")

    def test_the_budget_is_built_in_layers_against_the_cap(self):
        approve(self.e, "approve_workforce")
        f = self.e.store.get("forecast", "current")
        self.assertEqual(f["cap_usd"], 3.0)
        self.assertEqual(f["reserve_usd"], 3.0, "scripted: no model cost, the whole cap is reserve")
        self.assertEqual(set(f["by_worker"]), {"w_cto", "w_pm", "w_eng_a", "w_eng_b"})
        self.assertEqual(sum(v["units"] for v in f["by_milestone"].values()), 75)


class BudgetEngineTests(unittest.TestCase):
    def test_over_the_cap_warns_and_reserve_is_what_is_left(self):
        tmp = TempDir()
        e = Engine(tmp.path)
        try:
            from cynqra.workforce import Workforce
            s = Workforce.settings(e.store)
            s.update(budget_usd=1.0, compute_usd_per_hour=3600.0, infra_usd_per_day=0.25)  # $1 a second of machine time
            e.store.put("workforce", "settings", s)
            tasks = [{"id": "t_01", "owner_worker_id": "w_eng_a", "kind": "code", "workstream_id": "w", "milestone_id": "m",
                      "budget": 5, "deadline_day": 2}]
            f = budget.construct(e.store, tasks, [{"id": "w_eng_a"}])
            self.assertEqual(f["layers"]["infrastructure"]["usd"], 0.5)
            self.assertEqual(f["layers"]["verification"]["usd"], 20.0)  # 20 s of verification for a code task
            self.assertEqual(f["layers"]["tools"]["usd"], 40.0)         # two self-checks
            self.assertFalse(f["fits"])
            self.assertIn("over", f["warnings"][0])
        finally:
            e.close()
            tmp.cleanup()


class SignalsTests(unittest.TestCase):
    def test_thresholds(self):
        card = {"quality": {"verifications": 3, "acceptance_rate": 0.33}, "economics": {"usd_per_verified": 1.0},
                "reliability": {"calls": 4, "failed_calls": 0, "failure_rate": 0.0, "protocol_violations": 0}}
        self.assertTrue(performance.below(card))
        card["quality"]["acceptance_rate"] = 0.67
        self.assertEqual(performance.below(card), [])
        self.assertTrue(performance.below(card, forecast_per_task=0.1), "cost per verified task 10x the forecast")


class SanitizeTests(unittest.TestCase):
    def test_a_credential_is_never_written(self):
        saved = no_model_env()
        tmp = TempDir()
        from helpers import engine_to_running
        e = engine_to_running(tmp.path)
        try:
            r = e.gateway("w_eng_a", "t_03", "write_file", target="cfg.py",
                          content="KEY = 'sk-ant-api03-" + "x" * 40 + "'\n")
            self.assertEqual(r["status"], "denied")
            self.assertIn("credential", r["policy"]["reason"])
            self.assertFalse(any(tmp.path.rglob("cfg.py")))
        finally:
            e.close()
            tmp.cleanup()
            restore_env(saved)


class ScriptedIsHonestTests(unittest.TestCase):
    def test_the_demo_scenario_goes_through_the_same_checks(self):
        src = ScriptedSource()
        req, _ = src.decompose({})
        prop, _ = src.synthesize({}, req)
        self.assertEqual(sum(r["quantity"] for r in prop["roles"]), 4)
        plan, _ = src.plan({}, workers=prop["workers"], requirements=req)
        self.assertEqual(plan["uncovered_requirements"], [])


if __name__ == "__main__":
    unittest.main()
