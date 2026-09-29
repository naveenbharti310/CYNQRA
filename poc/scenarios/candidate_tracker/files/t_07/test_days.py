import json
import threading
import unittest
import urllib.request
from datetime import datetime, timedelta, timezone

from app import make_server


class DaysInStageTests(unittest.TestCase):
    """Release 1.1: the recruiters asked to see how long each candidate has sat in its stage."""

    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def call(self, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method="POST" if body is not None else "GET",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def test_a_candidate_shows_the_days_since_it_last_moved(self):
        ten = (datetime.now(timezone.utc) - timedelta(days=10, hours=1)).isoformat()
        rec = self.call("/api/candidates", {"name": "Asha", "applied_at": ten})
        self.assertEqual(rec["days_in_stage"], 10)
        moved = self.call(f"/api/candidates/{rec['id']}/stage", {"stage": "interview"})
        self.assertEqual(moved["days_in_stage"], 0, "moving the stage starts the count again")

    def test_every_listed_candidate_has_the_count(self):
        self.call("/api/candidates", {"name": "Ravi"})
        self.assertTrue(all("days_in_stage" in c for c in self.call("/api/candidates")))

    def test_the_page_shows_the_column(self):
        with urllib.request.urlopen(self.base + "/", timeout=5) as resp:
            self.assertIn("Days in stage", resp.read().decode())


if __name__ == "__main__":
    unittest.main()
