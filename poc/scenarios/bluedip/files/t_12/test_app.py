import json
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta

from app import make_server

TOMORROW = (date.today() + timedelta(days=1)).isoformat()


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def call(self, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method="POST" if body is not None else "GET",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"null")

    def offer(self, **kw):
        body = {"date": TOMORROW, "start": 13, "end": 16, "discount": 0.5, "cap": 15}
        body.update(kw)
        return body

    def test_health_and_page(self):
        self.assertEqual(self.call("/health"), (200, {"ok": True}))
        with urllib.request.urlopen(self.base + "/", timeout=5) as resp:
            self.assertIn(b"Bluedip", resp.read())

    def test_the_day_by_hour_and_by_meal_with_recommendations(self):
        code, d = self.call(f"/api/day?date={TOMORROW}")
        self.assertEqual(code, 200)
        self.assertEqual(len(d["hours"]), 15)
        self.assertEqual([s["slot"] for s in d["slots"]], ["breakfast", "lunch", "dinner"])
        self.assertEqual([r["slot"] for r in d["recommendations"]], ["breakfast", "lunch", "dinner"])
        self.assertTrue(d["sample"], "sample data is said to be sample")

    def test_an_offer_is_estimated_before_it_is_created(self):
        code, r = self.call("/api/offers/estimate", self.offer())
        self.assertEqual(code, 200)
        e = r["estimate"]
        self.assertLessEqual(e["customers_using"], 15)
        self.assertIn("margin_change", e)
        self.assertTrue(e["assumptions"]["food_cost_assumed"], "the assumed food cost is shown as one")

    def test_create_redeem_up_to_the_cap_and_learn(self):
        code, o = self.call("/api/offers", self.offer(cap=2))
        self.assertEqual(code, 201)
        self.assertEqual(self.call(f"/api/offers/{o['id']}/redeem", {})[0], 200)
        self.assertEqual(self.call(f"/api/offers/{o['id']}/redeem", {})[0], 200)
        self.assertEqual(self.call(f"/api/offers/{o['id']}/redeem", {})[0], 409, "the cap is a promise")
        code, closed = self.call(f"/api/offers/{o['id']}/close", {"covers": round(o["expected"]) + 8})
        self.assertEqual((code, closed["status"]), (200, "closed"))
        self.assertGreater(closed["response_now"], 1.2, "a busier window than expected raises the estimate")

    def test_the_rule_on_record_refuses_deep_discounts(self):
        self.assertEqual(self.call("/api/offers", self.offer(discount=0.6))[0], 400)
        self.assertEqual(self.call("/api/offers", self.offer(start=5, end=7))[0], 400)
        self.assertEqual(self.call("/api/offers/estimate", {"date": TOMORROW})[0], 400)
        self.assertEqual(self.call("/api/offers/of_999/redeem", {})[0], 404)

    def test_the_rest_of_the_day_follows_what_has_happened(self):
        code, d = self.call("/api/nowcast", {"date": TOMORROW, "now_hour": 12,
                                             "seen": {"8": 4, "9": 9, "10": 10, "11": 10}})
        self.assertEqual(code, 200)
        self.assertGreater(d["correction"], 1.0)

    def test_the_owner_can_enter_their_own_figures(self):
        code, r = self.call("/api/restaurant", {"food_cost": 0.3})
        self.assertEqual((code, r["food_cost_assumed"]), (200, False))
        self.assertEqual(self.call("/api/restaurant", {"food_cost": 3})[0], 400)
        self.call("/api/restaurant", {"food_cost": 0.35})

    def test_no_diner_app_and_no_payments_in_release_one(self):
        for path in ("/pay", "/checkout", "/diner", "/api/payments"):
            self.assertEqual(self.call(path)[0], 404)


if __name__ == "__main__":
    unittest.main()
