"""Security: what the security audit found, kept fixed. A key never follows a redirect to another server; a key is
never sent unencrypted to another computer, and a provider's address is a web address, never a file; and code the
team wrote, when its tests hang or finish, leaves nothing it started running. The local server's own protections
are in test_server."""
from __future__ import annotations

import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from helpers import TempDir

from cynqra import model_adapter
from cynqra.intelligence_layer import IntelligenceSupply, SupplyError, adapters
from cynqra.testrunner import run_unittests


def _serve(handler) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class KeyNeverFollowsARedirect(unittest.TestCase):
    def setUp(self):
        self.seen = seen = []

        class Elsewhere(BaseHTTPRequestHandler):
            def log_message(self, *a):
                return

            def _any(self):
                seen.append({k.lower(): v for k, v in self.headers.items()})
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"data": [], "choices": [{"message": {"content": "x"}}]}')
            do_GET = do_POST = _any

        self.other = _serve(Elsewhere)
        target = f"http://localhost:{self.other.server_address[1]}/elsewhere"
        self.codes = []
        codes = self.codes

        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *a):
                return

            def _any(self):
                self.send_response(codes[0])
                self.send_header("Location", target)
                self.end_headers()
            do_GET = do_POST = _any

        self.provider = _serve(Provider)
        self.base = f"http://127.0.0.1:{self.provider.server_address[1]}"

    def tearDown(self):
        for s in (self.provider, self.other):
            s.shutdown()
            s.server_close()

    def test_discovery_and_calls_refuse_redirects(self):
        """Found in the security audit: urllib follows a redirect with every header, the key included."""
        for code in (301, 302, 303, 307, 308):
            self.codes[:] = [code]
            with self.subTest(code=code):
                with self.assertRaises(SupplyError):
                    adapters._get_json(self.base + "/v1/models", {"Authorization": "Bearer sk-secret-1"})
                with self.assertRaises(RuntimeError):
                    model_adapter._post(self.base + "/v1/chat/completions", {"x": 1}, {"x-api-key": "sk-secret-2"},
                                        5, retry=False)
        self.assertEqual(self.seen, [], "nothing reached the other server")


class ProviderAddresses(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.supply = IntelligenceSupply(self.tmp.path / "control")

    def tearDown(self):
        self.supply.close()
        self.tmp.cleanup()

    def connect(self, endpoint, auth):
        return self.supply.connections.create({"type": "openai_compatible", "name": "P", "endpoint": endpoint,
                                               "auth": auth, "models": ["m"]})

    def test_a_key_travels_only_encrypted_and_only_to_a_web_address(self):
        import socket
        from unittest import mock
        real = socket.getaddrinfo
        public = {"models.example.com": "93.184.216.34", "lan.example.com": "192.168.1.20"}  # DNS, held fixed

        def resolve(host, *a, **kw):
            if host in public:
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (public[host], 443))]
            return real(host, *a, **kw)
        patch = mock.patch.object(socket, "getaddrinfo", resolve)
        patch.start()
        self.addCleanup(patch.stop)
        with self.assertRaises(SupplyError):  # a name that resolves into the private network, with a key: refused
            self.connect("https://lan.example.com/v1", {"method": "secret", "secret": "sk-test-not-real"})
        key = {"method": "secret", "secret": "sk-test-not-real"}
        for bad, auth in (("file:///etc/passwd", {"method": "none"}), ("ftp://example.com/v1", {"method": "none"}),
                          ("http://models.example.com/v1", key), ("http://192.168.1.20:8080/v1", key)):
            with self.subTest(endpoint=bad), self.assertRaises(SupplyError):
                self.connect(bad, auth)
        self.assertTrue(self.connect("https://models.example.com/v1", key)["id"])
        self.assertTrue(self.connect("http://127.0.0.1:8080/v1", key)["id"], "this computer: nothing on the network")
        self.assertTrue(self.connect("http://192.168.1.20:11434/v1", {"method": "none"})["id"], "no key to read")


class NoKeyInTheRecord(unittest.TestCase):
    def test_a_key_quoted_in_an_error_is_never_written(self):
        """A provider's error message can quote the key it refused; the record keeps the message and drops the key."""
        from cynqra.db import KEY_REMOVED, Store
        tmp = TempDir()
        s = Store(str(tmp.path / "t.db"))
        try:
            key = "sk-proj-" + "Ab1_" * 10
            s.put("call_error", "ce_1", {"error": f"HTTP 401: Incorrect API key provided: {key}"})
            s.append(company_id="c", event_type="worker.stopped", aggregate_type="worker", aggregate_id="w",
                     payload={"error": f"refused {key}"}, actor_type="service", actor_id="t", correlation_id="c")
            for f in tmp.path.iterdir():  # the database and its write-ahead log
                self.assertNotIn(key.encode(), f.read_bytes(), f.name)
            self.assertIn(KEY_REMOVED, s.get("call_error", "ce_1")["error"])
            self.assertIn(KEY_REMOVED, s.events()[-1]["payload"]["error"])
        finally:
            s.close()
            tmp.cleanup()


@unittest.skipIf(os.name == "nt", "process groups are stopped with taskkill on Windows; checked on the build machines")
class NothingLeftRunning(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()

    def _alive(self, marker) -> bool:
        pid = int((self.tmp.path / marker).read_text())
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:  # a zombie is dead, only not yet collected
            return fh.read().split(")")[-1].split()[0] != "Z"

    def _repo(self, body: str) -> None:
        (self.tmp.path / "test_x.py").write_text(
            "import os, subprocess, sys, time, unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_it(self):\n"
            "        p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
            f"        open(os.path.join({str(self.tmp.path)!r}, 'pid'), 'w').write(str(p.pid))\n"
            f"        {body}\n", encoding="utf-8")

    def test_a_hung_test_and_what_it_started_are_stopped(self):
        """Found in the security audit: the timeout stopped the tests but left running what they had started."""
        self._repo("time.sleep(300)")
        r = run_unittests(self.tmp.path, timeout=3)
        self.assertFalse(r["passed"])
        self.assertIn("did not finish", r["problem"])
        time.sleep(0.3)
        self.assertFalse(self._alive("pid"))

    def test_a_passing_test_leaves_nothing_running(self):
        self._repo("pass")
        r = run_unittests(self.tmp.path, timeout=30)
        self.assertTrue(r["passed"], r["output"][-400:])
        time.sleep(0.3)
        self.assertFalse(self._alive("pid"))


if __name__ == "__main__":
    unittest.main()
