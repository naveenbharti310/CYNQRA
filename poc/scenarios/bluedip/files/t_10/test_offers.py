import os
import tempfile
import unittest
from datetime import date

import demand
import offers
from store import SLOTS, Store, StoreError, sample_history

REST = {"open": 8, "close": 23, "seats": 60, "avg_bill": 600, "food_cost": 0.35, "food_cost_assumed": True}


class DemandTests(unittest.TestCase):
    def setUp(self):
        self.history = sample_history(date(2026, 10, 6))
        self.day = date(2026, 10, 7)  # a Wednesday

    def test_the_day_is_spread_over_opening_hours(self):
        total = demand.day_total(self.history, self.day)
        hours = demand.by_hour(total, REST)
        self.assertEqual(sorted(hours), list(range(8, 23)))
        self.assertAlmostEqual(sum(hours.values()), total, delta=1)

    def test_the_afternoon_after_lunch_is_the_quiet_lunch_window(self):
        hours = demand.by_hour(demand.day_total(self.history, self.day), REST)
        self.assertEqual(demand.quiet_window(hours, "lunch"), (13, 16))
        self.assertEqual(demand.quiet_window(hours, "dinner"), (16, 19))

    def test_the_day_must_follow_the_history(self):
        with self.assertRaises(ValueError):
            demand.day_total(self.history, date(2026, 10, 6))

    def test_covers_so_far_correct_the_rest_of_the_day(self):
        hours = demand.by_hour(100, REST)
        busy = {h: c * 1.2 for h, c in hours.items() if h < 13}
        now, factor = demand.nowcast(hours, busy, 13)
        self.assertAlmostEqual(factor, 1.2, places=2)
        self.assertAlmostEqual(now[14], round(hours[14] * 1.2, 1))
        self.assertEqual(demand.nowcast(hours, {h: 1000 for h in hours}, 13)[1], 1.5, "one odd morning is capped")

    def test_every_meal_is_in_the_view(self):
        v = demand.day_view(demand.by_hour(108, REST), REST)
        self.assertEqual([s["slot"] for s in v["slots"]], list(SLOTS))
        self.assertEqual(v["revenue"], round(v["covers"] * 600))


class OfferTests(unittest.TestCase):
    def test_the_owners_example_raises_revenue_and_loses_margin(self):
        e = offers.estimate(11.9, 0.5, 15, REST)
        self.assertEqual((e["new_customers"], e["would_have_come_anyway"]), (7.1, 3.6))
        self.assertGreater(e["revenue_change"], 1000)
        self.assertLess(e["margin_change"], 0, "half price for customers who would have come anyway")
        self.assertFalse(e["cap_reached"])

    def test_bluedip_finds_the_offer_that_earns_money(self):
        b = offers.best(11.9, 15, REST)
        self.assertEqual(b["discount"], 0.2)
        self.assertGreater(b["margin_change"], 300)
        self.assertGreater(b["revenue_change"], 900)

    def test_the_cap_is_never_exceeded(self):
        e = offers.estimate(80, 0.5, 15, REST)
        self.assertEqual(e["customers_using"], 15)
        self.assertTrue(e["cap_reached"])
        self.assertAlmostEqual(e["new_customers"] + e["would_have_come_anyway"], 15, delta=0.1)

    def test_no_offer_when_every_discount_loses_money(self):
        self.assertIsNone(offers.best(10, 15, {**REST, "food_cost": 0.75}))

    def test_the_rule_on_record_is_enforced(self):
        for bad in ((13, 16, 0.55, 15), (13, 16, 0.0, 15), (6, 9, 0.2, 15), (16, 13, 0.2, 15), (13, 16, 0.2, 0)):
            with self.assertRaises(offers.OfferError, msg=bad):
                offers.check(*bad, REST)
        with self.assertRaises(offers.OfferError):
            offers.check(13, 16, 0.5, 15, {**REST, "food_cost": 0.55})
        offers.check(13, 16, 0.5, 15, REST)

    def test_a_recommendation_for_each_meal(self):
        slots = [{"slot": "breakfast", "quiet": (8, 9), "quiet_covers": 2.2},
                 {"slot": "lunch", "quiet": (13, 16), "quiet_covers": 11.9},
                 {"slot": "dinner", "quiet": None, "quiet_covers": 0}]
        recs = offers.recommend(slots, REST)
        self.assertEqual([r["slot"] for r in recs], ["breakfast", "lunch", "dinner"])
        self.assertIsNone(recs[0]["offer"], "two covers: not worth an offer")
        self.assertIn("under ₹100", recs[0]["why"])
        self.assertEqual(recs[1]["offer"]["discount"], 0.2)
        self.assertIsNone(recs[2]["offer"])

    def test_it_learns_from_finished_offers(self):
        seen = offers.observed_response(10, 16, 0.3)
        self.assertAlmostEqual(seen, 2.0)
        self.assertGreater(offers.learn([seen]), offers.RESPONSE)
        self.assertEqual(offers.learn([]), offers.RESPONSE)


class StoreTests(unittest.TestCase):
    def test_redemptions_stop_at_the_cap(self):
        s = Store()
        o = s.add_offer({"date": "2026-10-07", "start": 13, "end": 16, "discount": 0.5, "cap": 2, "expected": 11.9})
        s.redeem(o["id"])
        s.redeem(o["id"])
        with self.assertRaises(StoreError):
            s.redeem(o["id"])

    def test_the_owners_figures_replace_the_assumption(self):
        s = Store()
        self.assertTrue(s.restaurant["food_cost_assumed"])
        r = s.set_restaurant(avg_bill=750, food_cost=0.3)
        self.assertEqual((r["avg_bill"], r["food_cost"], r["food_cost_assumed"]), (750, 0.3, False))
        with self.assertRaises(StoreError):
            s.set_restaurant(food_cost=2)

    def test_everything_survives_a_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bluedip.json")
            s = Store(path, today=date(2026, 10, 7))
            o = s.add_offer({"date": "2026-10-07", "start": 13, "end": 16, "discount": 0.2, "cap": 12, "expected": 11.9})
            s.close(o["id"], 16, 1.7)
            again = Store(path, today=date(2026, 10, 9))
            self.assertEqual((len(again.list_offers()), again.learned), (1, [1.7]))
            self.assertEqual(again.history[-1]["date"], "2026-10-06", "the stored history is kept")


if __name__ == "__main__":
    unittest.main()
