"""The product definition's canonical flow (Cynqra Product Flows and Architecture v1), piece by piece:
the role catalog, requirement decomposition, workforce synthesis and its gate, the roadmap gate, the Budget
Engine, the Performance Engine's signals and the gateway's output sanitizing."""
from __future__ import annotations

import json
import types
import unittest

from helpers import M1_ROLES, SCENARIO, TempDir, approve, no_model_env, restore_env

from cynqra import budget, performance, policy, roles, seats
from cynqra import settings as project_settings
from cynqra.engine import Engine, EngineError
from cynqra.intelligence import IntelligenceError, ScriptedSource
from cynqra.objective import validate_requirements
from cynqra.planner import validate_plan
from cynqra.intelligence_layer import IntelligenceSupply
from cynqra.synthesis import validate_cofounders, validate_team, validate_workforce

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
SECTION3_ORG = {"summary": "Section 3's example organization, as cofounders and their teams", "roles": [
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
        self.assertEqual(len(ws), 11, "two cofounders and nine team members; the founder is the CEO")
        lines = {w["id"]: w["reports_to"] for w in ws}
        for cof in ("w_cto", "w_cpo"):
            self.assertEqual(lines[cof], "founder", cof)
        for eng in ("w_ds", "w_be_a", "w_be_b", "w_fe_a", "w_fe_b", "w_devops", "w_qa"):
            self.assertEqual(lines[eng], "w_cto", eng)
        for prod in ("w_pm", "w_design"):
            self.assertEqual(lines[prod], "w_cpo", prod)
        self.assertTrue(all(prop["coverage"].values()), "every requirement covered")
        self.assertEqual(roles.planner(ws), "w_pm")
        self.assertEqual(prop["cofounders"], ["CTO", "CPO"])

    def test_cofounders_first_then_each_builds_its_own_team(self):
        req = self.req
        cof = validate_cofounders({"summary": "s", "cofounders": [
            {"role": "CTO", "why": "it is software"}, {"role": "CPO", "why": "who it is for"}]}, req)
        self.assertEqual([c["role"] for c in cof["cofounders"]], ["CTO", "CPO"])
        with self.assertRaises(IntelligenceError):  # only cofounder roles in the first step
            validate_cofounders({"cofounders": [{"role": "Engineer", "why": "x"}]}, req)
        with self.assertRaises(IntelligenceError):  # every cofounder says why
            validate_cofounders({"cofounders": [{"role": "CTO", "why": ""}]}, req)
        with self.assertRaises(IntelligenceError):  # one of each
            validate_workforce({"roles": [{"role": "CTO", "quantity": 2, "why": "x"}]}, req)
        names, taken = ["CTO", "CPO"], {}
        cto = validate_team({"roles": [{"role": "BackendEngineer", "quantity": 2, "why": "APIs"},
                                       {"role": "QA", "quantity": 1, "why": "tests"}]}, req, "CTO", names, taken)
        self.assertEqual({r["lead"] for r in cto["roles"]}, {"CTO"})
        with self.assertRaises(IntelligenceError):  # the product team is the CPO's to hire
            validate_team({"roles": [{"role": "Designer", "quantity": 1, "why": "UX"}]}, req, "CFO", ["CTO", "CPO", "CFO"], {})
        taken.update({"BackendEngineer": "CTO", "QA": "CTO"})
        with self.assertRaises(IntelligenceError):  # nobody is hired twice
            validate_team({"roles": [{"role": "QA", "quantity": 1, "why": "tests"}]}, req, "CPO", names, taken)
        self.assertEqual(validate_team({"summary": "I do it myself", "roles": []}, req, "CPO", names, taken)["roles"], [],
                         "a cofounder may do its part alone")
        prop = validate_workforce({"summary": "s", "cofounders": cof["cofounders"], "teams": {"CTO": cto, "CPO": {
            "roles": [{"role": "PM", "quantity": 1, "why": "plans"}]}}}, req)
        lines = {w["id"]: w["reports_to"] for w in prop["workers"]}
        self.assertEqual((lines["w_be_a"], lines["w_qa"], lines["w_pm"]), ("w_cto", "w_cto", "w_cpo"))

    def test_the_synthesizer_cannot_leave_the_pipeline_unstaffed_or_exceed_the_catalog(self):
        def bad(change):
            org = json.loads(json.dumps(SECTION3_ORG))
            change(org)
            with self.assertRaises(IntelligenceError):
                validate_workforce(org, self.req)
        bad(lambda o: o["roles"].append({"role": "Astrologer", "quantity": 1, "why": "x", "requirement_ids": []}))
        bad(lambda o: o["roles"][0].update(quantity=2))  # one CTO at most
        bad(lambda o: o["roles"][1].update(why=""))

    def test_the_platform_closes_what_the_catalog_requires(self):
        # the real-model [workforce] runs of 27 Sep (36310111670, then 36315283277) proposed no role covering a
        # requirement area, even when the refusal named the roles that close it; the catalog decides that, so the
        # platform adds the role, says what it closes, and the founder sees it at the gate
        org = json.loads(json.dumps(SECTION3_ORG))
        org["roles"] = [r for r in org["roles"] if r["role"] not in ("CPO", "PM")]
        prop = validate_workforce(org, self.req)
        added = [r for r in prop["roles"] if r.get("added_by") == "platform"]
        self.assertEqual([r["role"] for r in added], ["CPO"], "the first catalog role that covers the product area")
        self.assertIn("Added by Cynqra", added[0]["why"])
        self.assertTrue(all(prop["coverage"].values()), "every requirement is covered")
        org = json.loads(json.dumps(SECTION3_ORG))
        org["roles"] = [r for r in org["roles"] if r["role"] not in ("CTO", "DataScientist")]
        prop = validate_workforce(org, self.req)
        self.assertEqual(sorted(r["role"] for r in prop["roles"] if r.get("added_by")), ["CTO", "DataScientist"])
        self.assertTrue(roles.owners_of("review_merge", prop["workers"]))
        self.assertEqual(len(prop["workers"]), sum(r["quantity"] for r in prop["roles"]))
        with self.assertRaises(IntelligenceError):  # an area nothing in the catalog covers is still refused
            validate_workforce(json.loads(json.dumps(SECTION3_ORG)), {"requirements": [
                {"id": "r_99", "area": "astrology", "text": "read the stars"}]})

    def test_a_company_gets_its_founding_team(self):
        # the founder is the CEO and describes a company (here, one example: an AI-agent governance platform): the
        # foundation it calls for (market, money, law) is covered by the experts whose field it is
        req = validate_requirements({"requirements": [
            {"area": "product", "text": "An AI-agent governance platform for mid-size companies"},
            {"area": "market", "text": "Who buys it and against whom it competes"},
            {"area": "finance", "text": "Pricing, costs and the funding the first year needs"},
            {"area": "legal", "text": "The regulations an AI governance product falls under"},
            {"area": "security", "text": "Customers' agent logs are protected"}], "workstreams": []})
        org = {"roles": [{"role": "CTO", "quantity": 1, "why": "architecture", "requirement_ids": []},
                         {"role": "Engineer", "quantity": 1, "why": "builds it", "requirement_ids": []}]}
        prop = validate_workforce(org, req)
        present = {r["role"] for r in prop["roles"]}
        self.assertTrue({"CFO", "MarketAnalyst", "LegalAdvisor"} <= present, present)
        lead = {r["role"]: r.get("lead") for r in prop["roles"]}
        self.assertEqual((lead["CFO"], lead["MarketAnalyst"], lead["LegalAdvisor"]), (None, "CPO", "CFO"),
                         "a CFO is a cofounder; the added experts report to the cofounder whose area they serve")
        self.assertTrue(all(prop["coverage"].values()))
        self.assertIn("confirm", roles.doc_rules("risk_compliance"), "a non-expert founder is told what to confirm")
        self.assertIn("source", roles.doc_rules("market_analysis"))
        self.assertNotIn("CEO", roles.ROLES, "the founder is the CEO: there is no AI CEO")
        self.assertEqual(roles.COFOUNDERS, ["CTO", "CPO", "CFO", "CCO"])

    def test_the_team_follows_the_objective_with_specialists_in_its_field(self):
        # a different company gets a different team: its field's experts are named from the objective
        req = validate_requirements({"requirements": [
            {"area": "product", "text": "Online ordering for a chain of bakeries"},
            {"area": "functional", "text": "Customers order cakes for pickup"},
            {"area": "domain", "text": "Allergen labelling and food hygiene rules for each item"},
            {"area": "domain", "text": "Cold-chain handling of cream cakes between shops"}], "workstreams": []})
        org = {"roles": [
            {"role": "PM", "quantity": 1, "why": "runs the work", "requirement_ids": ["r_01"]},
            {"role": "CTO", "quantity": 1, "why": "architecture", "requirement_ids": []},
            {"role": "Engineer", "quantity": 1, "why": "builds ordering", "requirement_ids": ["r_02"]},
            {"role": "Specialist", "quantity": 1, "field": "food safety", "title": "Food Safety Specialist",
             "why": "allergens and hygiene", "requirement_ids": ["r_03"]}]}
        prop = validate_workforce(org, req)
        ws = {w["id"]: w for w in prop["workers"]}
        self.assertEqual(ws["w_spec_food_safety"]["title"], "Food Safety Specialist")
        self.assertEqual(ws["w_spec_food_safety"]["field"], "food safety")
        self.assertNotIn("CFO", {w["role"] for w in prop["workers"]}, "no role the objective does not need")
        self.assertIn("Your field: food safety", roles.prompt_text(ws["w_spec_food_safety"]))
        two = json.loads(json.dumps(org))
        two["roles"].append({"role": "Specialist", "quantity": 1, "field": "cold-chain logistics",
                             "why": "cream cakes between shops", "requirement_ids": ["r_04"]})
        prop = validate_workforce(two, req)
        self.assertEqual(sorted(w["id"] for w in prop["workers"] if w["role"] == "Specialist"),
                         ["w_spec_cold_chain_logistics", "w_spec_food_safety"], "one worker per field")
        with self.assertRaises(IntelligenceError):  # a Specialist without its field is no one in particular
            validate_workforce({"roles": [{"role": "Specialist", "quantity": 1, "why": "x"}]}, req)

    def test_a_field_nobody_proposed_gets_its_specialist(self):
        req = validate_requirements({"requirements": [
            {"area": "product", "text": "A booking app for dive schools"},
            {"area": "domain", "text": "Diver certification levels and dive safety limits"}], "workstreams": []})
        org = {"roles": [{"role": "PM", "quantity": 1, "why": "runs the work", "requirement_ids": ["r_01"]},
                         {"role": "CTO", "quantity": 1, "why": "architecture", "requirement_ids": []},
                         {"role": "Engineer", "quantity": 1, "why": "builds it", "requirement_ids": []}]}
        prop = validate_workforce(org, req)
        spec = [r for r in prop["roles"] if r["role"] == "Specialist"]
        self.assertEqual(len(spec), 1)
        self.assertEqual((spec[0]["added_by"], spec[0]["requirement_ids"]), ("platform", ["r_02"]))
        self.assertIn("Diver certification", spec[0]["field"])
        self.assertTrue(all(prop["coverage"].values()))

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
        with self.assertRaises(EngineError) as ctx:
            approve(self.e, "approve_workforce", edited=bad)
        self.assertIn("add one of", str(ctx.exception), "a founder's edit is refused, not completed behind them")
        d = approve(self.e, "approve_workforce", edited=self.EDIT)
        self.assertEqual(d["outcome_label"], "approved_edited")
        self.assertEqual(next(w for w in self.e.proposal()["workers"] if w["id"] == "w_qa")["reports_to"], "w_cto",
                         "QA reports to the CTO")
        self.assertTrue(self.e.proposal()["overridden"])
        self.assertIn("workforce.overridden", [x["event_type"] for x in self.e.store.events()])
        # the plan gives the QA engineer the founder added no work: it leaves before anything starts, and the
        # roadmap says so instead of asking
        self.assertEqual(sorted(w["id"] for w in self.e.workers()), ["w_cto", "w_eng_a", "w_eng_b", "w_pm"])
        self.assertIn("worker.released", [x["event_type"] for x in self.e.store.events()])
        road = next(x for x in self.e.pending_decisions() if x["kind"] == "approve_roadmap")
        self.assertIn("QA Engineer had no work in this plan and was removed before anything started", road["evidence_refs"])

    def test_the_roadmap_is_a_separate_gate_and_can_be_rejected(self):
        approve(self.e, "approve_workforce")
        self.assertEqual(self.e.meta["phase"], "planning")
        self.assertTrue(all(self.e.model_of(w["id"]) for w in self.e.workers()), "every worker staffed before the roadmap gate")
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
        sup = IntelligenceSupply(tmp.path / "sup")
        try:
            got = sup.connect({"type": "demo_script", "name": "demo", "auth": {"method": "none"},
                               "models": ["candidate_tracker"]}, origin="demo")
            e.store.put("binding", "w_eng_a", {"worker_id": "w_eng_a", "intelligence_id": got["intelligence"][0]["id"]})
            project_settings.update(e.store, {"budget_usd": 1.0, "compute_usd_per_hour": 3600.0,
                                              "infra_usd_per_day": 0.25})  # $1 a second of this machine's time
            tasks = [{"id": "t_01", "owner_worker_id": "w_eng_a", "kind": "code", "workstream_id": "w",
                      "milestone_id": "m", "deadline_day": 2}]
            f = budget.construct(e.store, tasks, [{"id": "w_eng_a"}], sup.registry)
            attempts = f["tasks"][0]["attempts"]
            self.assertEqual(f["layers"]["infrastructure"]["usd"], 0.5)
            self.assertAlmostEqual(f["layers"]["verification"]["usd"], round(20 * attempts, 4), places=3)
            self.assertAlmostEqual(f["layers"]["tools"]["usd"], round(2 * 20 * attempts, 4), places=3,
                                   msg="two self-checks per attempt, each a full test run")
            self.assertFalse(f["fits"])
            self.assertIn("over", f["warnings"][0])
        finally:
            sup.close()
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
        src.bind(types.SimpleNamespace(intelligence_for=lambda worker: "scripted"))
        req = validate_requirements(src.decompose({})[0])
        cof = validate_cofounders(src.cofounders({}, req)[0], req)  # the same two steps a model's answers pass
        names, taken, teams = [c["role"] for c in cof["cofounders"]], {}, {}
        for lead in names:
            teams[lead] = validate_team(src.build_team({}, req, cofounder=lead)[0], req, lead, names, taken)
            taken.update({r["role"]: lead for r in teams[lead]["roles"]})
        proposed = validate_workforce({"summary": cof["summary"], "cofounders": cof["cofounders"], "teams": teams}, req)
        self.assertFalse([r for r in proposed["roles"] if r.get("added_by")], "the script needs nothing added")
        self.assertFalse(proposed["assigned"]["requirements"] or proposed["assigned"]["risks"],
                         "every requirement and risk was claimed by the proposers")
        challenge = seats.read_challenge(src.challenge({}, req, seats.cards(proposed, req))[0])
        applied = seats.apply_challenge(proposed["roles"], req, challenge)  # the same challenge the product runs
        prop = validate_workforce({"summary": "s", "roles": applied["rows"]}, req)
        prop["removed"] = applied["removed"]
        self.assertTrue(all(c["needed"] for c in seats.cards(prop, req)), "every seat left earns its place")
        self.assertEqual(sum(r["quantity"] for r in prop["roles"]), workers_expected)
        self.assertTrue(all(prop["coverage"].values()))
        plan = validate_plan(src.plan({}, prop["workers"], req)[0], prop["workers"], [r["id"] for r in req["requirements"]])
        self.assertEqual(plan["uncovered_requirements"], [])
        return prop, plan

    def test_candidate_tracker(self):
        prop, _ = self.check("candidate_tracker", 5)
        self.assertEqual(prop["cofounders"], ["CTO", "CPO"], "a simple tool: two cofounders")

    def test_bluedip(self):
        prop, plan = self.check("bluedip", 13)
        self.assertEqual(prop["cofounders"], ["CTO", "CPO", "CFO"])
        self.assertEqual([r["seat"] for r in prop["removed"]], ["SecurityExpert"],
                         "the CTO's Security Expert owned nothing: the challenge cut it")
        lead = {w["title"]: w["reports_to"] for w in prop["workers"]}
        self.assertEqual({t for t, to in lead.items() if to == "w_cto"}, {
            "Senior Data Scientist", "Backend Engineer", "Frontend Engineer", "DevOps Engineer", "QA Engineer"})
        self.assertEqual({t for t, to in lead.items() if to == "w_cpo"}, {
            "Project Manager", "Product Designer", "Market Analyst", "Restaurant Revenue Management Specialist"})
        self.assertEqual({t for t, to in lead.items() if to == "w_cfo"}, {"Legal and Compliance Advisor"})
        spec = next(w for w in prop["workers"] if w["role"] == "Specialist")
        self.assertEqual((spec["id"], spec["title"]),
                         ("w_spec_revenue_management", "Restaurant Revenue Management Specialist"))
        docs = {d for t in plan["tasks"] if t["kind"] == "document" for d in t["documents"]}
        self.assertTrue({"market_analysis", "gtm_plan", "financial_model", "risk_compliance", "specialist_report",
                         "method", "design", "test_plan", "runbook"} <= docs)
        self.assertEqual([t["kind"] for t in plan["tasks"]].count("forecast"), 1, "the model is backtested")
        self.assertEqual(roles.planner(prop["workers"]), "w_pm")

    def test_restaurant_forecast(self):
        prop, plan = self.check("restaurant_forecast", 9)
        kinds = [t["kind"] for t in plan["tasks"]]
        self.assertEqual(kinds.count("document"), 7)
        self.assertEqual(sum(len(t["documents"]) for t in plan["tasks"] if t["kind"] == "document"), 8)
        self.assertEqual(kinds.count("forecast"), 1)
        self.assertEqual(plan["tasks"][-1]["owner_worker_id"], "w_devops", "DevOps proposes the deploy")
        self.assertEqual(roles.planner(prop["workers"]), "w_pm")


if __name__ == "__main__":
    unittest.main()
