"""Building the right thing: the guesses an idea rests on, riskiest first and tested early; the business numbers
recomputed like code; sources and assumptions marked; how the founder will know it worked; and a company that must
reach its customers. None of it asks the founder for anything: it is checked and shown."""
from __future__ import annotations

import json
import unittest

from helpers import POC, TempDir, engine_to_running, no_model_env, restore_env, run_journey

from cynqra import numbers, objective, planner, verifier

BLUEDIP = json.loads((POC / "scenarios" / "bluedip" / "scenario.json").read_text(encoding="utf-8"))
MODEL = (POC / "scenarios" / "bluedip" / "files" / "t_07" / "financial_model.md").read_text(encoding="utf-8")


def block(inputs: dict, claims: dict) -> str:
    return "```json\n" + json.dumps({"currency": "USD", "inputs": inputs, "claims": claims}) + "\n```"


BASE = {"price_per_month": {"value": 100, "basis": "assumption"},
        "cost_to_serve_per_month": {"value": 20, "basis": "measured"},
        "fixed_costs_per_month": {"value": 8000, "basis": "source: the lease"},
        "cost_to_win": {"value": 240, "basis": "assumption"},
        "monthly_churn": {"value": 0.05, "basis": "assumption"}}


class NumbersTests(unittest.TestCase):
    def test_every_claim_is_recomputed_from_the_inputs(self):
        r = numbers.check(block(BASE, {"margin_per_customer": 80, "payback_months": 3, "lifetime_value": 1600}))
        self.assertTrue(r["passed"], r["findings"])
        self.assertEqual(r["computed"]["customers_to_cover_fixed_costs"], 100.0)
        self.assertEqual(r["computed"]["value_to_cost_of_winning"], 6.67)

    def test_a_figure_that_does_not_follow_from_its_inputs_fails_with_the_right_one(self):
        r = numbers.check(block(BASE, {"lifetime_value": 2000}))  # price over churn, forgetting the cost to serve
        self.assertFalse(r["passed"])
        self.assertIn("lifetime_value: the model says 2000, the inputs give 1600", r["findings"][0]["why"])

    def test_every_input_says_where_it_comes_from(self):
        inputs = dict(BASE, price_per_month={"value": 100})
        r = numbers.check(block(inputs, {}))
        self.assertEqual([f["rule"] for f in r["findings"]], ["numbers_basis"])

    def test_a_model_without_numbers_cannot_be_checked(self):
        self.assertEqual(numbers.check("## Costs\nabout a lot")["findings"][0]["rule"], "numbers_block")
        self.assertEqual(numbers.check(block({"price_per_month": {"value": 1}}, {}))["findings"][0]["rule"],
                         "numbers_inputs")

    def test_months_to_profit_and_whether_the_money_lasts(self):
        inputs = dict(BASE, customers_per_month={"value": 20, "basis": "assumption"},
                      months_before_revenue={"value": 2, "basis": "assumption"},
                      funding={"value": 10000, "basis": "measured"})
        c = numbers.compute(inputs)
        self.assertGreater(c["break_even_month"], 2)
        self.assertGreater(c["funding_needed"], 16000, "two months of running costs before any revenue, at least")
        self.assertFalse(c["reaches_profit_before_money_runs_out"])

    def test_bluedips_model_holds_up(self):
        r = numbers.check(MODEL)
        self.assertTrue(r["passed"], r["findings"])
        self.assertEqual(r["computed"]["break_even_month"], 19, "the same month the model's own table shows")
        self.assertTrue(r["computed"]["reaches_profit_before_money_runs_out"])


class DocumentTrustTests(unittest.TestCase):
    TASK = {"documents": ["market_analysis"], "requirement_ids": []}
    GOOD = "## Customers\nOwners. Assumption: one screen.\n## Competitors\nx\n## Positioning\ny\n## Sources\n* a report\n"

    def test_a_trust_document_marks_its_assumptions_and_lists_its_sources(self):
        self.assertTrue(verifier.check_documents({"m.md": self.GOOD}, self.TASK, {})["passed"])
        r = verifier.check_documents({"m.md": self.GOOD.replace("Assumption: one screen.", "")}, self.TASK, {})
        self.assertIn("market_analysis_assumptions", [f["rule"] for f in r["findings"]])
        r = verifier.check_documents({"m.md": self.GOOD.replace("* a report\n", "none yet\n")}, self.TASK, {})
        self.assertIn("market_analysis_sources", [f["rule"] for f in r["findings"]])

    def test_the_financial_model_is_recomputed_when_it_is_verified(self):
        task = {"documents": ["financial_model"], "requirement_ids": []}
        r = verifier.check_documents({"f.md": MODEL}, task, {})
        self.assertTrue(r["passed"], r["findings"])
        self.assertEqual(r["numbers"]["computed"]["margin_per_customer"], 1749)


class GuessesTests(unittest.TestCase):
    def test_guesses_are_ranked_riskiest_first_and_measures_kept(self):
        req = objective.validate_requirements(BLUEDIP["requirements"])
        self.assertEqual([a["id"] for a in req["assumptions"]], ["a_01", "a_02", "a_03", "a_04"])
        self.assertEqual([(a["risk"], a["kind"]) for a in req["assumptions"]][:3],
                         [("high", "desirability"), ("high", "viability"), ("high", "feasibility")])
        self.assertEqual(len(req["measures"]), 3)
        self.assertTrue(all(m["target"] and m["rethink_below"] for m in req["measures"]))

    def test_a_company_that_must_earn_money_gets_a_way_to_reach_customers(self):
        pkg = {"requirements": [{"area": "business", "text": "Sell cakes"}, {"area": "functional", "text": "Order"}],
               "workstreams": []}
        req = objective.validate_requirements(pkg)
        added = [r for r in req["requirements"] if r.get("added_by") == "platform"]
        self.assertEqual([r["area"] for r in added], ["market"])
        tool = objective.validate_requirements({"requirements": [{"area": "functional", "text": "Track"}]})
        self.assertFalse([r for r in tool["requirements"] if r.get("added_by")], "an internal tool sells nothing")

    def test_a_high_risk_guess_tested_only_at_the_end_is_said_plainly(self):
        ms = [{"id": "m1", "name": "Build"}, {"id": "m2", "name": "Release"}]
        tasks = [{"id": "t_01", "milestone_id": "m1", "requirement_ids": ["r_01"]},
                 {"id": "t_02", "milestone_id": "m2", "requirement_ids": ["r_02"]}]
        out = planner.assumption_tests(tasks, ms, [{"id": "a_01", "text": "x", "risk": "high", "kind": "viability",
                                                    "tested_by": ["r_02"]},
                                                   {"id": "a_02", "text": "y", "risk": "high", "kind": "feasibility",
                                                    "tested_by": ["r_01"]}])
        self.assertEqual([(a["task"], a["early"]) for a in out], [("t_02", False), ("t_01", True)])


class BluedipTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_a_wrong_figure_is_caught_and_the_founder_gets_the_right_one(self):
        e = engine_to_running(self.tmp.path, scenario="bluedip")
        road = next(d for d in e.store.all("decision") if d["kind"] == "approve_roadmap")
        self.assertTrue(any(x.startswith("Guess a_01 (high risk)") for x in road["evidence_refs"]))
        run_journey(e, max_rounds=40)
        self.assertEqual(e.meta["phase"], "accepted", e.meta.get("notice"))
        checks = [v for v in e.store.all("verification") if v["task_id"] == "t_07"]
        self.assertEqual([v["verdict"] for v in checks], ["REQUIRES_REWORK", "VERIFIED"])
        self.assertIn("the inputs give 43725", checks[0]["checks"]["documents"][0]["why"])
        pack = e.final_report()["company_pack"]
        self.assertEqual(pack["numbers"]["computed"]["lifetime_value"], 43725)
        self.assertEqual(len(pack["outcome"]["measures"]), 3)
        status = {a["id"]: a["tested"] for a in pack["guesses"]}
        self.assertEqual(status["a_01"], "desk work checked; your step still needed",
                         "a market report does not prove owners will act: only the founder's step can")
        self.assertEqual(status["a_03"], "passed its checks", "the forecast passed its backtest")
        self.assertEqual(len(pack["your_next_steps"]), 2)
        e.close()


if __name__ == "__main__":
    unittest.main()
