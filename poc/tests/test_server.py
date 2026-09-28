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

    def test_other_websites_cannot_use_the_api(self):
        """Found in the audit: a page on any website could send commands to this server (for example connect a
        "provider" at its own address with the founder's key from the environment), and a name pointed at
        127.0.0.1 could read it."""
        def raw(path, headers, body=None):
            req = urllib.request.Request(self.base + path, data=body, headers=headers,
                                         method="POST" if body is not None else "GET")
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    return r.status
            except urllib.error.HTTPError as exc:
                return exc.code
        cmd = json.dumps({"on": True}).encode()
        port = self.srv.server_address[1]
        self.assertEqual(raw("/api/state", {"Host": f"attacker.example:{port}"}), 403, "DNS rebinding")
        self.assertEqual(raw("/api/killswitch", {"Origin": "https://attacker.example", "Content-Type": "application/json"},
                             cmd), 403, "a page on another website")
        self.assertEqual(raw("/api/killswitch", {"Content-Type": "text/plain"}, cmd), 403, "a form or no-cors request")
        self.assertFalse(self.app.engine.meta["frozen"], "nothing was done")
        self.assertEqual(raw("/api/killswitch", {"Origin": f"http://127.0.0.1:{port}",
                                                 "Content-Type": "application/json"}, cmd), 200, "Cynqra's own page")
        self.assertEqual(raw("/api/state", {"Host": f"localhost:{port}"}), 200)

    def test_no_other_site_can_frame_embed_or_flood_it(self):
        """Found in the security audit: any website could show Cynqra in a hidden frame and trick a click on
        "approve"; a request another site's page makes without an Origin (a link, an image) was answered; and a
        command could be any size."""
        def raw(path, headers, body=None):
            req = urllib.request.Request(self.base + path, data=body, headers=headers,
                                         method="POST" if body is not None else "GET")
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    return r.status, r.headers
            except urllib.error.HTTPError as exc:
                return exc.code, exc.headers
        code, h = raw("/", {})
        self.assertEqual(code, 200)
        self.assertIn("frame-ancestors 'none'", h["Content-Security-Policy"])
        self.assertIn("script-src 'self'", h["Content-Security-Policy"])
        self.assertEqual((h["X-Frame-Options"], h["X-Content-Type-Options"]), ("DENY", "nosniff"))
        self.assertEqual(raw("/api/state", {})[1]["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertEqual(raw("/api/state", {"Sec-Fetch-Site": "cross-site"})[0], 403, "an image or link elsewhere")
        self.assertEqual(raw("/api/state", {"Sec-Fetch-Site": "same-site"})[0], 403, "another port on this computer")
        self.assertEqual(raw("/", {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate"})[0], 200,
                         "a link to Cynqra still opens it (and the page refuses to be framed)")
        self.assertEqual(raw("/api/state", {"Sec-Fetch-Site": "same-origin"})[0], 200)
        json_cmd = {"Content-Type": "application/json"}
        self.assertEqual(raw("/api/run/step", {**json_cmd, "Content-Length": "5000000"}, b"{}")[0], 400)

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
        self.assertEqual({s["id"] for s in st["scenarios"]}, {"bluedip", "candidate_tracker", "restaurant_forecast"})
        code, rep = self.call("/api/replay/t_03")
        self.assertTrue(rep["complete"])
        code, g = self.call("/api/graph?q=approves&subject=deploy_production")
        self.assertEqual(g["approves"], "founder")
        req = urllib.request.urlopen(self.base + "/api/export", timeout=30)
        self.assertEqual(req.headers.get_content_type(), "application/zip")
        self.assertEqual(req.read()[:2], b"PK")

    def test_provider_connections_over_http(self):
        from test_workforce import Servers
        srv = Servers(1, self.tmp.path)
        self.addCleanup(srv.close)
        os.environ["CYNQRA_TEST_KEY"] = "sk-test-not-real"
        self.addCleanup(os.environ.pop, "CYNQRA_TEST_KEY", None)
        code, out = self.call("/api/connections", {"type": "openai_compatible", "name": "Team API",
                                                   "endpoint": srv.urls[0] + "/v1", "models": "Model A, Model B",
                                                   "auth": {"method": "env", "env_var": "CYNQRA_TEST_KEY"}})
        self.assertEqual(code, 200, out)
        cid = out["connection"]["id"]
        self.assertEqual(sorted(m["name"] for m in out["intelligence"]), ["Model A", "Model B"])
        self.assertEqual(out["connection"]["credential"]["present"], True)
        self.assertNotIn("sk-test-not-real", json.dumps(self.call("/api/intelligence")[1]), "a key is never shown")
        code, out = self.call(f"/api/connections/{cid}/update", {"models": ["Model A"], "rate_limits": {"calls_per_minute": 30}})
        self.assertEqual(code, 200, out)
        self.assertEqual(out["connection"]["rate_limits"], {"calls_per_minute": 30}, "the update is applied")
        state = self.call("/api/intelligence")[1]
        self.assertEqual([m["name"] for m in state["intelligence"] if m["status"] != "retired"], ["Model A"],
                         "what the connection no longer offers is retired")
        self.assertIn("bedrock", [t["type"] for t in state["provider_types"] if not t["implemented"]])
        self.assertEqual(self.call(f"/api/connections/{cid}/update", {"endpoint": "http://elsewhere"})[0], 400)
        self.assertEqual(self.call("/api/connections", {"type": "bedrock"})[0], 400)
        mid = next(m["id"] for m in state["intelligence"] if m["name"] == "Model A")
        self.assertEqual(self.call(f"/api/intelligence/{mid}/fault", {"offline": True})[1]["fault"], {"offline": True})
        self.assertEqual(self.call(f"/api/connections/{cid}/remove", {})[0], 200)
        state = self.call("/api/intelligence")[1]
        self.assertFalse([c for c in state["connections"] if c["id"] == cid])
        self.assertTrue(all(m["status"] == "retired" for m in state["intelligence"] if m["connection_id"] == cid))

    def test_bad_requests_are_400_not_crashes(self):
        self.assertEqual(self.call("/api/objective/submit", {})[0], 400)
        self.assertEqual(self.call("/api/company", {"name": "X", "mode": "psychic"})[0], 400)
        self.assertEqual(self.call("/api/company", {"name": "X", "scenario": "../../etc"})[0], 400)
        self.assertEqual(self.call("/api/decisions/dec_nope", {"action": "approve"})[0], 400)
        self.assertEqual(self.call("/api/replay/t_99")[0], 400)
        req = urllib.request.Request(self.base + "/api/company", data=b"not json", method="POST",
                                     headers={"Content-Type": "application/json"})
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
