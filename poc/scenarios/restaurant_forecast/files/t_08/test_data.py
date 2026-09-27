import json
import os
import tempfile
import unittest
from datetime import date

from data import CoversError, CoversStore


class CoversStoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "covers.json")

    def test_first_start_seeds_a_marked_sample(self):
        s = CoversStore(self.path, today=date(2026, 5, 1))
        self.assertTrue(s.sample)
        self.assertEqual(len(s.history()), 112)
        self.assertEqual(s.history()[-1]["date"], "2026-04-30")

    def test_add_saves_and_reloads(self):
        s = CoversStore(self.path, today=date(2026, 5, 1))
        s.add("2026-05-01", 140)
        again = CoversStore(self.path)
        self.assertEqual(again.history()[-1], {"date": "2026-05-01", "covers": 140})

    def test_same_day_replaces(self):
        s = CoversStore(self.path, today=date(2026, 5, 1))
        s.add("2026-05-01", 140)
        s.add("2026-05-01", 150)
        self.assertEqual([r for r in s.history() if r["date"] == "2026-05-01"], [{"date": "2026-05-01", "covers": 150}])

    def test_refuses_bad_rows(self):
        s = CoversStore(self.path, today=date(2026, 5, 1))
        for day, covers in (("01/05/2026", 10), ("2026-05-01", -1), ("2026-05-01", 2.5), ("2026-05-01", "ten"),
                            ("2026-05-01", True), ("2026-05-01", 99999)):
            with self.assertRaises(CoversError):
                s.add(day, covers)

    def test_recent_run_stops_at_a_gap(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"days": [{"date": "2026-05-01", "covers": 1}, {"date": "2026-05-03", "covers": 2},
                                {"date": "2026-05-04", "covers": 3}]}, fh)
        self.assertEqual([r["covers"] for r in CoversStore(self.path).recent_run()], [2, 3])


if __name__ == "__main__":
    unittest.main()
