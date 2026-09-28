import unittest
from datetime import date, timedelta

from forecast import forecast


def days(values, start=date(2026, 3, 2)):
    return [{"date": (start + timedelta(days=i)).isoformat(), "covers": v} for i, v in enumerate(values)]


class ForecastTest(unittest.TestCase):
    def test_one_number_per_day_ahead(self):
        self.assertEqual(len(forecast(days([100] * 56), 14)), 14)

    def test_numbers_are_never_negative(self):
        self.assertTrue(all(x >= 0 for x in forecast(days([0, 5, 0, 3, 0, 0, 1] * 8), 14)))

    def test_zero_horizon(self):
        self.assertEqual(forecast(days([100] * 14), 0), [])

    def test_refuses_empty_history(self):
        with self.assertRaises(ValueError):
            forecast([], 7)

    def test_refuses_negative_horizon(self):
        with self.assertRaises(ValueError):
            forecast(days([100] * 14), -1)

    def test_short_history(self):
        self.assertEqual(len(forecast(days([80, 90, 100]), 7)), 7)


if __name__ == "__main__":
    unittest.main()
