"""Every AI team member is a person with a real name: always labelled as an AI in a seat, drawn at random but fixed
for the project, never two alike, renamable by the founder. A replacement brings a new person into the seat; an
outage does not (test_workforce covers both on a real run)."""
from __future__ import annotations

import unittest

from helpers import SCENARIO, TempDir, engine_to_gates, no_model_env, restore_env

from cynqra import people
from cynqra.engine import Engine, EngineError


class NamesTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_every_member_is_a_named_ai_and_no_two_are_alike(self):
        e = engine_to_gates(self._tracker("a"))
        ws = e.workers()
        self.assertTrue(ws and all(w.get("name") and len(w["name"].split()) == 2 for w in ws))
        firsts = [w["name"].split()[0] for w in ws]
        self.assertEqual(len(firsts), len(set(firsts)), "no two share a first name")
        self.assertEqual(len({f[0] for f in firsts}), len(firsts), "and no two start with the same letter")
        for w in ws:
            self.assertEqual(people.label(w), f"{w['name']}, AI {people.seat(w)}", "always labelled as an AI")
        engs = [w for w in ws if w["role"] == "Engineer"]
        self.assertEqual({people.seat(w) for w in engs}, {"Software Engineer"}, "names tell two engineers apart")
        e.close()

    def test_the_founder_meets_the_people_with_the_proposal_and_they_stay(self):
        e = self._tracker("a")
        met = {w["id"]: w["name"] for w in e.proposal()["workers"]}
        self.assertTrue(met and all(met.values()), "named at step 2, before anyone is hired")
        self.assertLessEqual({w["name"] for w in e.proposal()["lean"]["workers"]}, set(met.values()),
                             "the lean team is some of the same people")
        engine_to_gates(e)
        self.assertEqual({w["id"]: w["name"] for w in e.workers()}, met, "the people approved are the people hired")
        e.close()

    def test_the_same_project_always_draws_the_same_team(self):
        a, b = engine_to_gates(self._tracker("a")), engine_to_gates(self._tracker("b"))
        self.assertEqual({w["id"]: w["name"] for w in a.workers()}, {w["id"]: w["name"] for w in b.workers()},
                         "a demo shows the same people every time")
        a.close()
        b.close()

    def test_names_never_come_from_the_famous_or_repeat(self):
        self.assertEqual(len(people.FIRST), len(set(people.FIRST)))
        for famous in ("Jobs", "Musk", "Gates", "Bezos", "Zuckerberg", "Altman"):
            self.assertNotIn(famous, people.LAST)

    def test_the_founder_can_rename_anyone_and_the_seat_stays(self):
        e = engine_to_gates(self._tracker("a"))
        cto = e.worker("w_cto")
        other = next(w for w in e.workers() if w["id"] != "w_cto")
        w = e.rename_worker("w_cto", "  Ada   Byron ")
        self.assertEqual((w["name"], w["title"], w["role"]), ("Ada Byron", cto["title"], "CTO"))
        for bad in ("", "A", "R2-D2", "x" * 41, other["name"].upper()):
            with self.assertRaises(EngineError, msg=bad):
                e.rename_worker("w_cto", bad)
        with self.assertRaises(EngineError):
            e.rename_worker("w_nobody", "Sam Lee")
        self.assertTrue(any(x["event_type"] == "worker.renamed" for x in e.store.events()))
        e.close()

    def test_the_prompt_tells_each_member_who_they_are(self):
        from cynqra import roles
        e = engine_to_gates(self._tracker("a"))
        eng = next(w for w in e.workers() if w["role"] == "Engineer")
        lead = e.worker(eng["reports_to"])
        text = roles.prompt_text(eng, e.workers())
        self.assertIn(f"You are {eng['name']}, the AI {eng['title']}", text)
        self.assertIn(lead["name"], text)
        e.close()

    def test_a_replaced_person_leaves_a_record_and_the_newcomer_starts_fresh(self):
        e = engine_to_gates(self._tracker("a"))
        w = e.worker("w_cto")
        w["performance_profile"]["reworks"] = 3
        e.store.put("worker", "w_cto", w)
        left, joined = people.replace(e, "w_cto", "failed its checks three times", "model-a", "model-b")
        now = e.worker("w_cto")
        self.assertEqual((left, now["name"]), (w["name"], joined))
        self.assertEqual(now["former"][0]["record"]["reworks"], 3)
        self.assertEqual(now["performance_profile"]["reworks"], 0)
        firsts = [x["name"].split()[0] for x in e.workers()]
        self.assertNotIn(left.split()[0], firsts, "the one who left is not on the team")
        again_left, again = people.replace(e, "w_cto", "again", "model-b", "model-c")
        self.assertNotIn(again.split()[0], (left.split()[0], joined.split()[0]), "a name always means one record")
        e.close()

    def test_the_readme_names_the_people_the_bluedip_demo_shows(self):
        from pathlib import Path
        e = Engine(self.tmp.path / "b")
        e.create_company("Bluedip", "demo", "bluedip")
        from cynqra.engine import scenarios
        e.draft_objective(next(x for x in scenarios() if x["id"] == "bluedip")["messy"])
        e.submit_objective()
        readme = (Path(__file__).resolve().parents[2] / "README.md").read_text(encoding="utf-8").replace("\n", " ")
        for w in e.proposal()["workers"]:
            if w["tier"] == "cofounder":
                self.assertIn(f"{w['name']}, AI {people.seat(w)}", readme)
        e.close()

    def _tracker(self, where):
        e = Engine(self.tmp.path / where)
        e.create_company("Harbor Recruiting")
        e.draft_objective(SCENARIO["messy"])
        e.submit_objective()
        return e


if __name__ == "__main__":
    unittest.main()
