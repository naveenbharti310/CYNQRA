"""The product definition's canonical flow (Cynqra Product Flows and Architecture v1), piece by piece:
the role catalog, requirement decomposition, workforce synthesis and its gate, the roadmap gate, the Budget
Engine, the Performance Engine's signals and the gateway's output sanitizing."""
from __future__ import annotations

import json
import unittest

from helpers import M1_ROLES, SCENARIO, TempDir, approve, no_model_env, restore_env

from cynqra import budget, performance, policy, roles
from cynqra import settings as project_settings
from cynqra.engine import Engine, EngineError
from cynqra.intelligence import IntelligenceError, ScriptedSource
from cynqra.objective import validate_requirements
from cynqra.planner import validate_plan
from cynqra.registry import Registry
from cynqra.synthesis import validate_workforce

# The restaurant demand forecasting example of section 6, as requirements and the section 3 workforce table.
SECTION6_REQ = {"outcomes": ["Restaurants plan staff and stock from a demand forecast"], "requirements": [
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
SECTION3_ORG = {"summary": "Section 3's example organization", "roles": [
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
        self.req = validate_requirements(json.loads(json.dumps(SECTION6_REQ)))

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
        prop = validate_workforce(json.loads(json.dumps(SECTION3_ORG)), self.req)
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
            org = json.loads(json.dumps(SECTION3_ORG))
            change(org)
            with self.assertRaises(IntelligenceError):
                validate_workforce(org, self.req)
        bad(lambda o: o["roles"].append({"role": "Astrologer", "quantity": 1, "why": "x", "requirement_ids": []}))
        bad(lambda o: o["roles"][0].update(quantity=2))  # one CEO at most
        bad(lambda o: o.update(roles=[r for r in o["roles"] if r["role"] != "CTO"]))  # nobody reviews and merges
        bad(lambda o: o.update(roles=[r for r in o["roles"] if r["role"] not in ("DataScientist",)]))  # ai_ml uncovered
        bad(lambda o: o["roles"][1].update(why=""))

    def test_a_refusal_tells_the_model_how_to_fix_it(self):
        # the first real-model [workforce] run (27 Sep, run 36310111670) proposed no role covering a product
        # requirement, twice; the refusal named the gap but not the roles that close it
        org = json.loads(json.dumps(SECTION3_ORG))
        org["roles"] = [r for r in org["roles"] if r["role"] not in ("CEO", "CPO", "PM")]
        with self.assertRaises(IntelligenceError) as ctx:
            validate_workforce(org, self.req)
        self.assertIn("add a role that covers product: CEO, CPO, PM", str(ctx.exception))
        org = json.loads(json.dumps(SECTION3_ORG))
        org["roles"] = [r for r in org["roles"] if r["role"] not in ("CTO",)]
        with self.assertRaises(IntelligenceError) as ctx:
            validate_workforce(org, self.req)
        self.assertIn("add one of: CTO", str(ctx.exception))

    def test_authority_comes_from_the_catalog(self):
        self.assertEqual(policy.MATRIX, roles.matrix())
        self.assertEqual(policy.evaluate(role="DevOps", action_type="deploy_production")["decision"], "REQUIRE_APPROVAL")
        self.assertEqual(policy.evaluate(role="Designer", action_type="merge_to_main")["decision"], "DENY")
        self.assertEqual(policy.evaluate(role="QA", action_type="review_work")["decision"], "ALLOW")
        self.assertEqual(roles.instantiate(M1_ROLES)[0]["reports_to"], "founder", "the M1 fixture")


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

    EDIT = {"roles": [{"role": "CTO", "quantity": 1, "why": "x"}, {"role": "PM", "quantity": 1, "why": "x"},
                      {"role": "Engineer", "quantity": 2, "why": "x"},
                      {"role": "QA", "quantity": 1, "why": "the founder wants a QA engineer"}]}

    def test_editing_the_workforce_needs_the_governance_policy(self):
        with self.assertRaises(EngineError):
            approve(self.e, "approve_workforce", edited=self.EDIT)
        self.assertEqual([d["kind"] for d in self.e.pending_decisions()], ["approve_workforce"],
                         "a refused edit leaves the gate open")

    def test_an_allowed_override_is_checked_and_recorded(self):
        project_settings.update(self.e.store, {"allow_workforce_override": True})
        bad = {"roles": [{"role": "PM", "quantity": 1, "why": "x"}]}  # nobody can write code, merge or deploy
        with self.assertRaises(EngineError):
            approve(self.e, "approve_workforce", edited=bad)
        d = approve(self.e, "approve_workforce", edited=self.EDIT)
        self.assertEqual(d["outcome_label"], "approved_edited")
        self.assertEqual(sorted(w["id"] for w in self.e.workers()), ["w_cto", "w_eng_a", "w_eng_b", "w_pm", "w_qa"])
        self.assertEqual(self.e.worker("w_qa")["reports_to"], "w_pm")
        self.assertTrue(self.e.proposal()["overridden"])
        self.assertIn("workforce.overridden", [x["event_type"] for x in self.e.store.events()])

    def test_the_roadmap_is_a_separate_gate_and_can_be_rejected(self):
        approve(self.e, "approve_workforce")
        self.assertEqual(self.e.meta["phase"], "planning")
        self.assertTrue(all(w["model_id"] for w in self.e.workers()), "every worker staffed before the roadmap gate")
        approve(self.e, "approve_roadmap", "reject", note="Split the web app task")
        pend = self.e.pending_decisions()
        self.assertEqual([d["kind"] for d in pend], ["approve_roadmap"])
        self.assertEqual(self.e.store.get("plan", "plan_1")["note"], "Split the web app task")
        approve(self.e, "approve_roadmap")
        self.assertEqual(self.e.meta["phase"], "running")

    def test_the_budget_is_built_in_layers_against_the_cap(self):
        approve(self.e, "approve_workforce")
        f = self.e.store.get("forecast", "current")
        self.assertEqual(f["cap_usd"], 3.0)
        self.assertEqual(f["reserve_usd"], 3.0, "scripted and an unpriced machine: the whole cap is reserve")
        self.assertEqual(set(f["by_worker"]), {"w_cto", "w_pm", "w_eng_a", "w_eng_b"})
        self.assertEqual(set(f["by_milestone"]), {"m_1", "m_2", "m_3"})
        self.assertTrue(all(t["budget_usd"] == 0.0 for t in self.e.tasks()))


class BudgetEngineTests(unittest.TestCase):
    def test_layers_are_priced_from_the_machine_and_the_plan(self):
        tmp = TempDir()
        e = Engine(tmp.path)
        reg = Registry(tmp.path / "reg")
        try:
            reg.register({"runtime": "scripted", "ref": "candidate_tracker", "id": "m"})
            project_settings.update(e.store, {"budget_usd": 1.0, "compute_usd_per_hour": 3600.0,
                                              "infra_usd_per_day": 0.25})  # $1 a second of this machine's time
            tasks = [{"id": "t_01", "owner_worker_id": "w_eng_a", "kind": "code", "workstream_id": "w",
                      "milestone_id": "m", "deadline_day": 2}]
            f = budget.construct(e.store, tasks, [{"id": "w_eng_a", "model_id": "m"}], reg, None)
            attempts = f["tasks"][0]["attempts"]
            self.assertEqual(f["layers"]["infrastructure"]["usd"], 0.5)
            self.assertAlmostEqual(f["layers"]["verification"]["usd"], round(20 * attempts, 4), places=3)
            self.assertAlmostEqual(f["layers"]["tools"]["usd"], round(2 * 20 * attempts, 4), places=3,
                                   msg="two self-checks per attempt, each a full test run")
            self.assertFalse(f["fits"])
            self.assertIn("over", f["warnings"][0])
        finally:
            reg.close()
            e.close()
            tmp.cleanup()

    def test_a_charge_warns_then_opens_the_breaker_once(self):
        tmp = TempDir()
        e = Engine(tmp.path)
        try:
            project_settings.update(e.store, {"budget_usd": 1.0})
            self.assertEqual(budget.charge(e.store, "w", "t_01", 0.6, "inference")["warned"], [50])
            out = budget.charge(e.store, "w", "t_01", 0.5, "tools")
            self.assertEqual((out["warned"], out["breaker"]), ([80, 95], True))
            self.assertFalse(budget.charge(e.store, "w", "t_01", 0.1, "tools")["breaker"], "opened once")
            L = budget.ledger(e.store)
            self.assertEqual((L["spent_total"], L["by_layer"]["tools"]), (1.2, 0.6))
            with self.assertRaises(ValueError):
                budget.charge(e.store, "w", "t_01", 0.1, "snacks")
            budget.raise_cap(e.store, 2.0)
            self.assertEqual((budget.ledger(e.store)["state"], budget.ledger(e.store)["warned"]), ("ok", [50]))
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


class ScenariosAreHonestTests(unittest.TestCase):
    """Every prepared demo passes the same checks a model's answers do."""

    def check(self, scenario, workers_expected):
        src = ScriptedSource(scenario)
        src.bind(lambda worker: ("scripted", {}))
        req = validate_requirements(src.decompose({})[0])
        prop = validate_workforce(src.synthesize({}, req)[0], req)
        self.assertEqual(sum(r["quantity"] for r in prop["roles"]), workers_expected)
        self.assertTrue(all(prop["coverage"].values()))
        plan = validate_plan(src.plan({}, prop["workers"], req)[0], prop["workers"], [r["id"] for r in req["requirements"]])
        self.assertEqual(plan["uncovered_requirements"], [])
        return prop, plan

    def test_candidate_tracker(self):
        self.check("candidate_tracker", 4)

    def test_restaurant_forecast(self):
        prop, plan = self.check("restaurant_forecast", 9)
        kinds = [t["kind"] for t in plan["tasks"]]
        self.assertEqual(kinds.count("document"), 7)
        self.assertEqual(sum(len(t["documents"]) for t in plan["tasks"] if t["kind"] == "document"), 8)
        self.assertEqual(kinds.count("forecast"), 1)
        self.assertEqual(plan["tasks"][-1]["owner_worker_id"], "w_devops", "DevOps proposes the deploy")
        self.assertEqual(roles.assigner(prop["workers"]), "w_pm")


if __name__ == "__main__":
    unittest.main()
