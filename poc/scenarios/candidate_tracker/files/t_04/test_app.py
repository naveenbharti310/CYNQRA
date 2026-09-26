import json
import threading
import unittest
import urllib.error
import urllib.request

from app import make_server


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

    def test_health(self):
        self.assertEqual(self.call("/health"), (200, {"ok": True}))

    def test_create_stage_and_list(self):
        code, rec = self.call("/api/candidates", {"name": "Jordan Lee"})
        self.assertEqual(code, 201)
        code, rec = self.call(f"/api/candidates/{rec['id']}/stage", {"stage": "screen"})
        self.assertEqual((code, rec["stage"]), (200, "screen"))
        code, rows = self.call("/api/candidates")
        self.assertIn(rec["id"], [r["id"] for r in rows])

    def test_stuck_filter_needs_a_reason(self):
        code, rec = self.call("/api/candidates", {"name": "Old Card", "applied_at": "2026-01-01T09:00:00+00:00"})
        rows = {r["id"]: r for r in self.call("/api/candidates")[1]}
        self.assertTrue(rows[rec["id"]]["flagged"])
        self.assertFalse(rows[rec["id"]]["stuck"])
        self.call(f"/api/candidates/{rec['id']}/reason", {"reason": "missing_document"})
        rows = {r["id"]: r for r in self.call("/api/candidates")[1]}
        self.assertTrue(rows[rec["id"]]["stuck"])

    def test_bad_input_is_refused(self):
        self.assertEqual(self.call("/api/candidates", {"name": " "})[0], 400)
        self.assertEqual(self.call("/api/candidates/c_999/stage", {"stage": "screen"})[0], 404)
        code, rec = self.call("/api/candidates", {"name": "Sam Okoye"})
        self.assertEqual(self.call(f"/api/candidates/{rec['id']}/stage", {"stage": "ghost"})[0], 400)

    def test_meta_lists_closed_stages(self):
        code, meta = self.call("/api/meta")
        self.assertEqual(meta["stages"], ["applied", "screen", "interview", "offer", "hired", "rejected"])

    def test_no_public_careers_page_or_login(self):
        for path in ("/careers", "/apply", "/login"):
            self.assertEqual(self.call(path)[0], 404)


if __name__ == "__main__":
    unittest.main()
