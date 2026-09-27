"""HTTP API tests and the browser end to end test (A16)."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request

from helpers import POC, SCENARIO, TempDir, no_model_env, restore_env

from cynqra.server import App, make_server


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()
        self.app = App(self.tmp.path)
        self.srv = make_server(self.app, 0)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.app.close()
        self.tmp.cleanup()
        restore_env(self.saved)

    def call(self, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method="POST" if body is not None else "GET",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw)
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"{}")

    def test_serves_the_ui_and_blocks_traversal(self):
        code, body = self.call("/")
        self.assertEqual(code, 200)
        self.assertIn(b"/ui/app.js", body)
        self.assertEqual(self.call("/ui/app.css")[0], 200)
        self.assertEqual(self.call("/ui/../cynqra/engine.py")[0], 404)
        self.assertEqual(self.call("/ui/%2e%2e/cynqra/engine.py")[0], 404)
        self.assertEqual(self.call("/nothing")[0], 404)

    def test_full_journey_over_http(self):
        self.assertEqual(self.call("/api/state")[1]["meta"]["phase"], "new")
        self.assertEqual(self.call("/api/company", {"name": "Harbor Recruiting", "mode": "demo"})[0], 200)
        code, obj = self.call("/api/objective/draft", {"messy": SCENARIO["messy"]})
        self.assertEqual((code, obj["status"]), (200, "draft"))
        self.assertEqual(self.call("/api/objective/guardrails", {"budget_usd": 2.5, "constraints": {"deadline": "a week"}})[0], 200)
        self.assertEqual(self.call("/api/objective/guardrails", {"budget_usd": -1})[0], 400)
        self.assertEqual(self.call("/api/objective/submit", {})[0], 200)
        for _ in range(30):
            st = self.call("/api/state")[1]
            if st["meta"]["phase"] == "accepted":
                break
            pend = st["decisions"]["pending"]
            if pend:
                self.assertEqual(self.call(f"/api/decisions/{pend[0]['id']}", {"action": "approve"})[0], 200)
            else:
                for _ in range(40):
                    if self.call("/api/run/step", {})[1]["did"] in ("idle", "error"):
                        break
        st = self.call("/api/state")[1]
        self.assertEqual(st["meta"]["phase"], "accepted")
        self.assertTrue(st["live_url"])
        self.assertEqual(st["budget"]["settings"]["budget_usd"], 2.5)
        self.assertEqual(st["objective"]["founder_constraints"], {"deadline": "a week"})
        self.assertEqual({s["id"] for s in st["scenarios"]}, {"candidate_tracker", "restaurant_forecast"})
        code, rep = self.call("/api/replay/t_03")
        self.assertTrue(rep["complete"])
        code, g = self.call("/api/graph?q=approves&subject=deploy_production")
        self.assertEqual(g["approves"], "founder")
        req = urllib.request.urlopen(self.base + "/api/export", timeout=30)
        self.assertEqual(req.headers.get_content_type(), "application/zip")
        self.assertEqual(req.read()[:2], b"PK")

    def test_bad_requests_are_400_not_crashes(self):
        self.assertEqual(self.call("/api/objective/submit", {})[0], 400)
        self.assertEqual(self.call("/api/company", {"name": "X", "mode": "psychic"})[0], 400)
        self.assertEqual(self.call("/api/company", {"name": "X", "scenario": "../../etc"})[0], 400)
        self.assertEqual(self.call("/api/decisions/dec_nope", {"action": "approve"})[0], 400)
        self.assertEqual(self.call("/api/replay/t_99")[0], 400)
        req = urllib.request.Request(self.base + "/api/company", data=b"not json", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 400)

    def test_auto_run_and_reset_archive(self):
        self.call("/api/company", {"name": "A", "mode": "demo"})
        self.call("/api/objective/draft", {"messy": SCENARIO["messy"]})
        self.call("/api/objective/submit", {})
        pend = self.call("/api/state")[1]["decisions"]["pending"][0]
        self.call(f"/api/decisions/{pend['id']}", {"action": "approve"})
        self.assertTrue(self.call("/api/run/auto", {"on": True, "delay": 0})[1]["on"])
        deadline = time.time() + 30
        while time.time() < deadline:
            if self.call("/api/state")[1]["decisions"]["pending"]:
                break
            time.sleep(0.2)
        self.assertTrue(self.call("/api/state")[1]["decisions"]["pending"], "auto run reached the founder")
        self.call("/api/run/auto", {"on": False})
        self.assertEqual(self.call("/api/reset", {})[0], 200)
        self.assertEqual(self.call("/api/state")[1]["meta"]["phase"], "new")
        self.assertTrue(any(p.name.startswith("archive_") for p in self.tmp.path.iterdir()), "nothing deleted")


def _node_ready() -> bool:
    if not shutil.which("node"):
        return False
    probe = "try{require('playwright')}catch(e){require(require('path').join(require('child_process').execSync('npm root -g').toString().trim(),'playwright'))}"
    return subprocess.run(["node", "-e", probe], capture_output=True).returncode == 0


@unittest.skipUnless(_node_ready(), "Node and Playwright are not installed on this machine")
class BrowserEndToEnd(unittest.TestCase):  # A16
    def test_whole_journey_in_a_real_browser(self):
        saved = no_model_env()
        tmp = TempDir()
        port = free_port()
        proc = subprocess.Popen([sys.executable, str(POC / "run_poc.py"), "--port", str(port), "--no-browser",
                                 "--data", str(tmp.path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(50):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=1)
                    break
                except OSError:
                    time.sleep(0.1)
            shots = os.environ.get("CYNQRA_E2E_SHOTS", "")
            out = subprocess.run(["node", str(POC / "tests" / "e2e" / "walk.js"), f"http://127.0.0.1:{port}", shots],
                                 capture_output=True, text=True, timeout=240)
            line = [x for x in out.stdout.splitlines() if x.startswith("{")][-1]
            res = json.loads(line)
            self.assertTrue(res["ok"], res)
            self.assertEqual(res["phase"], "accepted")
            self.assertEqual(len([s for s in res["steps"] if s.startswith("founder approved")]), 4)
        finally:
            proc.terminate()
            proc.wait(timeout=10)
            tmp.cleanup()
            restore_env(saved)


if __name__ == "__main__":
    unittest.main()
