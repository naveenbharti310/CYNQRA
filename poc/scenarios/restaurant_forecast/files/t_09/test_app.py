import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from app import make_server, prep


class AppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0, os.path.join(tempfile.mkdtemp(), "covers.json"))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as r:
            return r.status, r.read()

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_health_and_page(self):
        self.assertEqual(self.get("/health")[0], 200)
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Covers for the next 14 days", body)

    def test_forecast_has_fourteen_days_with_prep(self):
        f = json.loads(self.get("/api/forecast")[1])
        self.assertEqual(len(f["days"]), 14)
        for d in f["days"]:
            self.assertGreaterEqual(d["prep"], d["covers"])

    def test_record_covers(self):
        self.assertEqual(self.post("/api/covers", {"date": "2030-01-01", "covers": 90})[0], 201)
        self.assertEqual(self.post("/api/covers", {"date": "2030-01-01", "covers": -3})[0], 400)
        self.assertEqual(self.post("/api/covers", ["not", "an", "object"])[0], 400)

    def test_unknown_route(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/admin")
        self.assertEqual(ctx.exception.code, 404)

    def test_prep_margin(self):
        self.assertEqual(prep(100), 110)
        self.assertEqual(prep(101), 112)


if __name__ == "__main__":
    unittest.main()
