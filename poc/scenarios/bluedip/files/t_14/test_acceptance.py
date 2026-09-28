"""Acceptance tests: the numbered acceptance checks of release 1 (docs/acceptance.md), each run against the app as
an owner uses it. The restaurant's history is fixed so every number is the same on every run."""
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date

from app import make_server
from store import Store

HISTORY_ENDS = date(2026, 10, 6)
DAY = "2026-10-07"  # a Wednesday, the day after the history


class Acceptance(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.data = os.path.join(self.dir, "bluedip.json")
        Store(self.data, today=date(2026, 10, 7))  # the sample restaurant, its history ending the day before DAY
        self.start()

    def tearDown(self):
        self.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def start(self):
        self.server = make_server(0, self.data)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def call(self, path, body=None):
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                     method="POST" if body is not None else "GET",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"null")

    def offer(self, **kw):
        body = {"date": DAY, "start": 13, "end": 16, "discount": 0.5, "cap": 15}
        body.update(kw)
        return body

    def test_1_the_day_by_hour_and_every_meal_with_a_recommendation(self):
        code, d = self.call(f"/api/day?date={DAY}")
        self.assertEqual(code, 200)
        self.assertEqual([h["hour"] for h in d["hours"]], list(range(8, 23)))
        self.assertTrue(all(h["covers"] >= 0 and "revenue" in h for h in d["hours"]))
        self.assertEqual([r["slot"] for r in d["recommendations"]], ["breakfast", "lunch", "dinner"])
        self.assertTrue(d["sample"], "sample data is said to be sample")

    def test_2_the_quiet_lunch_window_is_1_pm_to_4_pm(self):
        lunch = next(s for s in self.call(f"/api/day?date={DAY}")[1]["slots"] if s["slot"] == "lunch")
        self.assertEqual(lunch["quiet"], [13, 16])

    def test_3_covers_so_far_correct_the_rest_of_the_day_within_bounds(self):
        busy = self.call("/api/nowcast", {"date": DAY, "now_hour": 12, "seen": {"8": 40, "9": 40, "10": 40, "11": 40}})[1]
        empty = self.call("/api/nowcast", {"date": DAY, "now_hour": 12, "seen": {"8": 0, "9": 0, "10": 0, "11": 0}})[1]
        self.assertLessEqual(busy["correction"], 1.5)
        self.assertGreaterEqual(empty["correction"], 0.5)

    def test_4_an_estimate_shows_every_part_and_its_assumptions(self):
        code, r = self.call("/api/offers/estimate", self.offer())
        self.assertEqual(code, 200)
        e = r["estimate"]
        for key in ("customers_using", "new_customers", "would_have_come_anyway", "revenue_change", "margin_change"):
            self.assertIn(key, e)
        self.assertTrue(e["assumptions"]["food_cost_assumed"], "the assumed food cost is said to be assumed")

    def test_5_the_owners_example_raises_revenue_and_loses_money_and_a_better_offer_earns(self):
        r = self.call("/api/offers/estimate", self.offer())[1]
        self.assertGreater(r["estimate"]["revenue_change"], 0)
        self.assertLess(r["estimate"]["margin_change"], 0)
        self.assertGreater(r["better"]["margin_change"], 0)

    def test_6_no_offer_passes_its_cap(self):
        code, o = self.call("/api/offers", self.offer(discount=0.2))
        self.assertEqual(code, 201)
        self.assertLessEqual(o["estimate"]["customers_using"], 15)
        for _ in range(15):
            self.assertEqual(self.call(f"/api/offers/{o['id']}/redeem", {})[0], 200)
        self.assertEqual(self.call(f"/api/offers/{o['id']}/redeem", {})[0], 409, "the 16th customer is refused")

    def test_7_the_rule_on_record_is_enforced(self):
        self.assertEqual(self.call("/api/offers", self.offer(discount=0.6))[0], 400, "deeper than 50%")
        self.assertEqual(self.call("/api/offers", self.offer(start=5, end=7))[0], 400, "outside opening hours")
        self.assertEqual(self.call("/api/restaurant", {"food_cost": 0.6})[0], 200)
        self.assertEqual(self.call("/api/offers", self.offer(discount=0.45))[0], 400, "below its food cost")

    def test_8_a_finished_offer_updates_the_response(self):
        o = self.call("/api/offers", self.offer(discount=0.2))[1]
        code, closed = self.call(f"/api/offers/{o['id']}/close", {"covers": round(o["expected"]) + 10})
        self.assertEqual(code, 200)
        self.assertGreater(closed["response_now"], 1.2)

    def test_9_data_survives_a_restart_and_release_one_has_no_payment_or_diner_route(self):
        o = self.call("/api/offers", self.offer(discount=0.2))[1]
        self.stop()
        self.start()
        self.assertIn(o["id"], [x["id"] for x in self.call("/api/offers")[1]])
        self.assertEqual(self.call("/health")[0], 200)
        with urllib.request.urlopen(self.base + "/", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
        for path in ("/pay", "/checkout", "/diner"):
            self.assertEqual(self.call(path)[0], 404)


if __name__ == "__main__":
    unittest.main()
