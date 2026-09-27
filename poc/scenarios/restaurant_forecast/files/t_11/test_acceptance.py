"""Acceptance checks from docs/acceptance.md, run against the product's own functions."""
import os
import tempfile
import unittest
from datetime import date, timedelta

from app import HORIZON, plan, prep
from data import CoversStore
from forecast import forecast


def weekly(weeks, start=date(2026, 3, 2)):
    pattern = [80, 85, 90, 100, 135, 155, 120]
    return [{"date": (start + timedelta(days=i)).isoformat(), "covers": pattern[i % 7]} for i in range(7 * weeks)]


class AcceptanceTest(unittest.TestCase):
    def test_1_fourteen_days_ahead(self):
        store = CoversStore(os.path.join(tempfile.mkdtemp(), "c.json"), today=date(2026, 5, 1))
        days = plan(store)["days"]
        self.assertEqual(HORIZON, 14)
        self.assertEqual(len(days), 14)
        self.assertEqual(days[0]["date"], "2026-05-01")

    def test_2_prep_is_forecast_plus_ten_percent(self):
        for covers in (0, 1, 99, 100, 137.4):
            self.assertEqual(prep(covers), -(-round(covers * 110, 6) // 100))

    def test_3_the_weekly_pattern_is_kept(self):
        history = weekly(8)
        self.assertEqual(forecast(history, 7), [float(h["covers"]) for h in history[:7]])

    def test_4_weekends_are_marked(self):
        store = CoversStore(os.path.join(tempfile.mkdtemp(), "c.json"), today=date(2026, 5, 1))
        for d in plan(store)["days"]:
            self.assertEqual(d["weekend"], date.fromisoformat(d["date"]).weekday() >= 5)


if __name__ == "__main__":
    unittest.main()
