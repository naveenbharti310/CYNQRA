"""Every seat earns its place: what the founder brings, one owner per requirement, who asked for each seat, the
independent challenge, the lean team, the answer to "why this team?", and the plan's check that every member has
work. The founder is asked nothing more for any of it: the checks run by themselves and are shown at the gates."""
from __future__ import annotations

import json
import unittest

from helpers import POC, TempDir, approve, no_model_env, restore_env

from cynqra import objective, seats, synthesis
from cynqra.engine import Engine, EngineError
from cynqra.intelligence import IntelligenceError, ScriptedSource
from cynqra.objective import validate_requirements

BLUEDIP = json.loads((POC / "scenarios" / "bluedip" / "scenario.json").read_text(encoding="utf-8"))


def to_gate(folder, scenario="bluedip", intelligence=None, founder=None) -> Engine:
    e = Engine(folder, intelligence=intelligence)
    e.create_company("C", "demo", scenario)
    if founder is not None:
        e.set_founder(founder)
    e.draft_objective(json.loads((POC / "scenarios" / scenario / "scenario.json").read_text(encoding="utf-8"))["messy"])
    e.submit_objective()
    return e


class Grumpy(ScriptedSource):
    """A challenger that wants to cut every seat."""

    def challenge(self, objective, requirements, seats, **_):
        return {"seats": [{"seat": s["seat"], "verdict": "cut", "why": "Not needed."} for s in seats],
                "failure_stories": ["Too many people."]}, self._usage()


class Mute(ScriptedSource):
    """A challenger whose answer cannot be read."""

    def challenge(self, objective, requirements, seats, **_):
        return {"verdict": "hmm"}, self._usage()


class TeamCheckTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_bluedip_every_seat_is_owned_asked_for_and_challenged(self):
        e = to_gate(self.tmp.path)
        p = e.proposal()
        self.assertEqual(e.meta["phase"], "workforce", "no step is added for the founder")
        self.assertEqual((p["proposed_seats"], sum(r["quantity"] for r in p["roles"])), (14, 13))
        self.assertEqual([r["seat"] for r in p["challenge"]["removed"]], ["SecurityExpert"])
        self.assertEqual([o["seat"] for o in p["challenge"]["overruled"]], ["Designer"],
                         "the challenger wanted the Designer merged away; it is the only seat on the screen design")
        self.assertIn("r_11", p["challenge"]["overruled"][0]["kept_because"])
        reqs = [r["id"] for r in e.requirements()["requirements"]]
        self.assertEqual(sorted(p["owners"]), sorted(reqs), "every requirement has exactly one owner")
        self.assertTrue(all(p["watchers"].values()), "every risk has someone watching it")
        cards = {c["seat"]: c for c in p["cards"]}
        self.assertEqual(cards["CFO"]["requested_by"], "Cynqra")
        self.assertEqual(cards["LegalAdvisor"]["requested_by"], "CFO", "the cofounder who asked for the hire")
        self.assertTrue(all(c["needed"] and c["without"] for c in p["cards"]))
        legal = next(r for r in p["roles"] if r["role"] == "LegalAdvisor")
        self.assertEqual(legal.get("mode"), "advisor")
        why = p["why_team"]
        self.assertEqual(why["confidence"], "high")
        self.assertEqual(len(why["failure_stories"]), 2)
        d = next(x for x in e.pending_decisions() if x["kind"] == "approve_workforce")
        self.assertEqual(d["confidence"], "high", "the confidence comes from the checks")
        self.assertIn("The independent challenge cut Security Expert", " ".join(d["evidence_refs"]))
        e.close()

    def test_the_lean_team_covers_everything_with_fewer_seats(self):
        e = to_gate(self.tmp.path)
        ln = e.proposal()["lean"]
        self.assertEqual(ln["seats"], 10)
        self.assertEqual({x["seat"] for x in ln["left_out"]}, {"FrontendEngineer", "PM", "Designer"})
        self.assertTrue(all(ln["coverage"].values()), "the lean team still covers every requirement")
        self.assertTrue(all(ln["watchers"].values()), "and watches every risk")
        self.assertIn("QA", {r["role"] for r in ln["roles"]}, "no one else on the team can write the acceptance tests")
        cards = {c["seat"]: c for c in ln["cards"]}
        self.assertNotIn("FrontendEngineer", cards, "the lean team shows its own seats")
        self.assertIn("r_13", cards["CPO"]["owns"], "the Chief Product Officer takes over the Project Manager's work")
        self.assertNotIn("Frontend Engineer", " ".join(cards["CTO"]["without"]))
        with self.assertRaises(EngineError) as ctx:
            approve(e, "approve_workforce", edited={"option": "lean"})
        self.assertIn("recommended team only", str(ctx.exception), "the demo's script plans one team, and says so")
        org = synthesis.approve(e, option="lean")  # what live mode does
        self.assertEqual(len(org["workers"]), 10)
        self.assertEqual(e.proposal()["status"], "approved")
        e.close()

    def test_a_challenger_cannot_cut_a_seat_that_is_the_only_one_on_something(self):
        e = to_gate(self.tmp.path, intelligence=Grumpy("bluedip"))
        p = e.proposal()
        self.assertEqual(sum(r["quantity"] for r in p["roles"]), 13, "only the seat that owned nothing went")
        self.assertEqual(len(p["challenge"]["overruled"]), 13, "every seat that stayed says why")
        self.assertTrue(all(o["kept_because"] for o in p["challenge"]["overruled"]))
        e.close()

    def test_an_unreadable_challenge_still_runs_the_platforms_test_and_lowers_the_confidence(self):
        e = to_gate(self.tmp.path, intelligence=Mute("bluedip"))
        p = e.proposal()
        self.assertTrue(p["challenge"]["unreadable"])
        self.assertEqual([r["seat"] for r in p["challenge"]["removed"]], ["SecurityExpert"],
                         "the removal test does not need the challenger")
        self.assertEqual(p["why_team"]["confidence"], "medium")
        e.close()


class FounderTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_an_area_the_founder_leads_gets_no_cofounder_and_its_requirements_are_theirs(self):
        req = validate_requirements(BLUEDIP["requirements"], {"leads": ["CFO"]})
        mine = [r["id"] for r in req["requirements"] if r.get("owner") == "founder"]
        self.assertEqual(mine, ["r_03", "r_08"])
        with self.assertRaises(IntelligenceError):
            synthesis.validate_cofounders(BLUEDIP["workforce"], req, {"leads": ["CFO"]})
        cof = synthesis.validate_cofounders({"summary": "s", "cofounders": [c for c in BLUEDIP["workforce"]["cofounders"]
                                                                            if c["role"] != "CFO"]}, req, {"leads": ["CFO"]})
        teams = {k: v for k, v in BLUEDIP["workforce"]["teams"].items() if k != "CFO"}
        teams["CPO"] = dict(teams["CPO"], roles=teams["CPO"]["roles"] + BLUEDIP["workforce"]["teams"]["CFO"]["roles"])
        prop = synthesis.validate_workforce({"summary": "s", "cofounders": cof["cofounders"], "teams": teams}, req,
                                            founder={"leads": ["CFO"]})
        self.assertNotIn("CFO", [r["role"] for r in prop["roles"]], "Cynqra never adds the seat the founder holds")
        self.assertEqual(prop["owners"]["r_03"], "founder")
        self.assertEqual(prop["founder_owned"], ["r_03", "r_08"])
        self.assertEqual(prop["watchers"]["k_01"], ["founder"], "a money risk is the founder's to watch")

    def test_the_founders_profile_is_checked(self):
        e = Engine(self.tmp.path)
        e.create_company("C", "demo", "bluedip")
        self.assertEqual(e.founder()["stage"], "launch", "the demo's founder")
        with self.assertRaises(EngineError):
            e.set_founder({"stage": "someday"})
        with self.assertRaises(EngineError) as ctx:
            e.set_founder({"leads": ["CTO"]})
        self.assertIn("only a team member can do", str(ctx.exception))
        with self.assertRaises(EngineError) as ctx:  # the demo's team was written for its founder
            e.set_founder({"leads": ["CFO"], "stage": "launch"})
        self.assertIn("part of its script", str(ctx.exception))
        kept = e.set_founder({"stage": "launch", "hours_per_week": "400"})
        self.assertEqual((kept["hours_per_week"], kept["background"]), (100, "Has run a restaurant; not technical."),
                         "hours are capped, and a form that does not show the background keeps it")
        self.assertEqual(objective.founder_profile({"leads": ["CFO", "Engineer"]})["leads"], ["CFO"],
                         "only a cofounder seat can be led by the founder")
        self.assertEqual(objective.founder_profile({})["stage"], "launch", "by default Cynqra aims at a live product")
        e.close()

    def test_the_stage_limits_how_many_seats_a_cofounder_may_hire(self):
        req = validate_requirements(BLUEDIP["requirements"])
        cto = BLUEDIP["workforce"]["teams"]["CTO"]
        self.assertEqual(objective.TEAM_LIMIT["idea"], 2)
        with self.assertRaises(IntelligenceError) as ctx:
            synthesis.validate_team(cto, req, "CTO", ["CTO", "CPO", "CFO"], {}, objective.TEAM_LIMIT["idea"])
        self.assertIn("at most 2", str(ctx.exception))
        synthesis.validate_team(cto, req, "CTO", ["CTO", "CPO", "CFO"], {}, objective.TEAM_LIMIT["launch"])

    def test_a_demo_founder_cannot_be_changed_into_one_its_script_does_not_fit(self):
        with self.assertRaises(EngineError):  # the demo's CTO hires six, too many for the idea stage
            to_gate(self.tmp.path, founder={"stage": "idea"})


class WorkCheckTests(unittest.TestCase):
    def test_every_member_joins_with_its_first_task_and_one_with_none_is_listed(self):
        workers = [{"id": "w_cto", "title": "CTO", "role": "CTO"}, {"id": "w_be", "title": "BE", "role": "BackendEngineer"},
                   {"id": "w_qa", "title": "QA", "role": "QA"}]
        tasks = [{"id": "t_01", "owner_worker_id": "w_be", "handoff_from": "w_cto", "reviewed_by": "w_cto",
                  "milestone_id": "m_1", "deadline_day": 2},
                 {"id": "t_02", "owner_worker_id": "w_cto", "milestone_id": "m_2", "deadline_day": 4}]
        wc = seats.work_check(tasks, workers, [{"id": "m_1", "name": "Build"}, {"id": "m_2", "name": "Release"}])
        self.assertEqual(wc["joins"]["w_be"], {"task": "t_01", "milestone": "Build", "day": 2})
        self.assertEqual(wc["joins"]["w_cto"]["task"], "t_01", "a cofounder starts by handing out its team's work")
        self.assertEqual(wc["idle"], [{"worker": "w_qa", "title": "QA", "role": "QA"}])


if __name__ == "__main__":
    unittest.main()
