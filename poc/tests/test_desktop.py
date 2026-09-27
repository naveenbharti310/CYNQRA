"""The desktop app: model download, the llama-server runtime, the app's HTTP API and a whole run.

Hugging Face and llama-server are replaced by local test doubles (FakeHF below, fake_llama_server.py);
the real ones are exercised by the desktop build workflow on GitHub's Windows, macOS and Linux machines.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from helpers import POC, TempDir, no_model_env, restore_env

sys.path.insert(0, str(POC))
import desktop  # noqa: E402
from cynqra import model_adapter, runtime  # noqa: E402
from cynqra.runtime import BY_ID, ModelRuntimeError, Runtime  # noqa: E402
from cynqra.server import App, make_server  # noqa: E402

FAKE_SERVER = [sys.executable, str(POC / "tests" / "fake_llama_server.py")]
MODEL = "qwen3.5-4b"
REPO, FILE = BY_ID[MODEL]["files"][0]


class FakeHF:
    """Hugging Face's file listing and downloads: redirect to a 'CDN', byte ranges, and on request
    a connection cut part way through or a corrupted file."""

    def __init__(self, files: dict):
        self.files = files  # {(repo, path): bytes}
        self.sha = {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}
        self.cut_once_at: int | None = None
        self.corrupt = False
        self.ranges: list[str] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, obj):
                raw = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_HEAD(self):
                self.do_GET(head=True)

            def do_GET(self, head=False):
                p = self.path
                if p.startswith("/api/models/") and p.endswith("/tree/main"):
                    repo = p[len("/api/models/"):-len("/tree/main")]
                    items = [{"type": "file", "path": path, "size": len(data), "lfs": {"oid": outer.sha[(r, path)]}}
                             for (r, path), data in outer.files.items() if r == repo]
                    return self._json(200, items) if items else self._json(404, {"error": "Repository not found"})
                if "/resolve/main/" in p:
                    repo, path = p[1:].split("/resolve/main/")
                    if (repo, path) not in outer.files:
                        return self._json(404, {"error": "Entry not found"})
                    self.send_response(302)
                    self.send_header("Location", f"/cdn/{repo}/{path}")
                    self.send_header("X-Linked-Size", str(len(outer.files[(repo, path)])))
                    self.send_header("X-Linked-Etag", f'"{outer.sha[(repo, path)]}"')
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if p.startswith("/cdn/"):
                    owner, name, path = p[5:].split("/", 2)
                    data = outer.files[(f"{owner}/{name}", path)]
                    if outer.corrupt:
                        data = data[:-1] + bytes([data[-1] ^ 1])
                    rng = self.headers.get("Range") or ""
                    outer.ranges.append(rng)
                    start = int(rng[6:].split("-")[0]) if rng.startswith("bytes=") else 0
                    body = data[start:]
                    self.send_response(206 if start else 200)
                    self.send_header("Content-Length", str(len(body)))
                    if start:
                        self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
                    self.end_headers()
                    if head:
                        return
                    if outer.cut_once_at is not None and start < outer.cut_once_at:
                        cut, outer.cut_once_at = outer.cut_once_at, None
                        self.wfile.write(body[: cut - start])
                        self.wfile.flush()
                        self.close_connection = True
                        return
                    self.wfile.write(body)
                    return
                return self._json(404, {"error": "not found"})

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class DesktopBase(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()
        self.blob = os.urandom(3 * 1024 * 1024 + 123)
        self.hf = FakeHF({(REPO, FILE): self.blob})
        self._hf, runtime.HF = runtime.HF, self.hf.base
        self.requests = self.tmp.path / "requests.jsonl"
        os.environ["FAKE_LLAMA_REQUESTS"] = str(self.requests)

    def tearDown(self):
        runtime.HF = self._hf
        for k in ("FAKE_LLAMA_REQUESTS", "FAKE_LLAMA_FAIL_GPU", "FAKE_LLAMA_EXIT", "FAKE_LLAMA_LOAD_S",
                  "FAKE_LLAMA_STUCK_GPU", "CYNQRA_GPU_PROBE_S"):
            os.environ.pop(k, None)
        self.hf.close()
        self.tmp.cleanup()
        restore_env(self.saved)

    def runtime(self, **servers) -> Runtime:
        rt = Runtime(self.tmp.path / "rt", servers=servers or {"cpu": FAKE_SERVER})
        self.addCleanup(rt.stop)
        return rt


class DownloadTests(DesktopBase):
    def test_download_resumes_after_a_cut_and_verifies(self):
        self.hf.cut_once_at = len(self.blob) // 3
        rt = self.runtime()
        path = rt.download(MODEL)
        self.assertEqual(path.read_bytes(), self.blob)
        self.assertEqual(rt.installed(MODEL), path)
        self.assertEqual(self.hf.ranges[0], "bytes=0-")
        self.assertEqual(self.hf.ranges[1], f"bytes={len(self.blob) // 3}-")  # resumed, not restarted
        manifest = json.loads((path.parent / "manifest.json").read_text())
        self.assertEqual((manifest["repo"], manifest["path"], manifest["size"]), (REPO, FILE, len(self.blob)))
        self.assertEqual(manifest["sha256"], hashlib.sha256(self.blob).hexdigest())
        self.assertEqual(rt.status["done"], len(self.blob))

    def test_a_corrupted_download_is_deleted_not_used(self):
        self.hf.corrupt = True
        rt = self.runtime()
        with self.assertRaises(ModelRuntimeError) as cm:
            rt.download(MODEL)
        self.assertIn("SHA-256", str(cm.exception))
        self.assertIsNone(rt.installed(MODEL))
        self.assertFalse(any(rt.model_path(MODEL).parent.glob("*.part")))

    def test_a_mirror_is_used_when_the_publisher_lacks_the_file(self):
        self.hf.close()
        mirror = ("lmstudio-community/Qwen3.5-9B-GGUF", "Qwen3.5-9B-Q4_K_M.gguf")
        self.hf = FakeHF({mirror: self.blob})
        runtime.HF = self.hf.base
        spec = runtime.resolve(BY_ID["qwen3.5-9b"])
        self.assertEqual((spec["repo"], spec["path"], spec["size"]), (*mirror, len(self.blob)))

    def test_pause_keeps_the_partial_file_and_resume_finishes_it(self):
        rt = self.runtime()
        rt._cancel.set()
        with self.assertRaises(ModelRuntimeError):
            rt.download(MODEL)
        rt._cancel.clear()
        self.assertEqual(rt.download(MODEL).read_bytes(), self.blob)

    def test_catalog_recommends_by_memory(self):
        self.assertEqual(runtime.recommended(15.6), "qwen3.6-35b-a3b-q2")  # a 16 GB laptop reports about 15.6
        self.assertEqual(runtime.recommended(24.0), "qwen3.6-35b-a3b-iq3")
        self.assertEqual(runtime.recommended(32.0), "qwen3.6-35b-a3b")
        self.assertEqual(runtime.recommended(11.5), "qwen3.5-9b")
        self.assertEqual(runtime.recommended(8.0), "qwen3.5-4b")
        self.assertEqual(runtime.recommended(None), "qwen3.6-35b-a3b-q2")
        rt = self.runtime()
        rt.ram_gb = 15.6
        cat = {m["id"]: m for m in rt.catalog()}
        self.assertTrue(cat["qwen3.6-35b-a3b-q2"]["recommended"])
        self.assertFalse(cat["qwen3.6-35b-a3b"]["fits"])
        self.assertNotIn("qwen3.6-35b-a3b-iq2", cat)  # failed the race: not offered
        self.assertTrue(all(m["files"] and m["ctx"] >= 24576 for m in runtime.CATALOG))


class ServerTests(DesktopBase):
    def test_start_points_the_adapter_at_the_local_server_with_the_research_settings(self):
        rt = self.runtime()
        base = rt.start(MODEL)
        self.assertEqual(rt.status["state"], "ready")
        self.assertEqual(os.environ["CYNQRA_LOCAL_BASE_URL"], base + "/v1")
        self.assertEqual(model_adapter.resolve()["kind"], "local")
        out = model_adapter.complete("Convert the founder objective", want_json=True,
                                     schema={"type": "object", "properties": {"a": {"type": "string"}}})
        self.assertIsNone(out["error"])
        body = json.loads(self.requests.read_text().splitlines()[-1])["body"]
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual((body["temperature"], body["seed"], body["max_tokens"]), (0.0, 42, 6144))
        cmd = rt.log_tail().splitlines()[0]
        self.assertIn("-c 24576", cmd)
        self.assertIn("-ngl 0", cmd)  # the processor build gets no GPU layers
        self.assertEqual(rt.settings()["model"], MODEL)
        rt.stop()
        self.assertNotIn("CYNQRA_LOCAL_BASE_URL", os.environ)

    def test_gpu_failure_falls_back_to_the_processor(self):
        os.environ["FAKE_LLAMA_FAIL_GPU"] = "1"
        rt = self.runtime(metal=FAKE_SERVER)
        rt.start(MODEL)
        self.assertEqual(rt.status["state"], "ready")
        self.assertIn("-ngl 0", rt.log_tail().splitlines()[0])

    def test_a_gpu_that_loads_but_cannot_answer_falls_back_to_the_processor(self):
        os.environ["FAKE_LLAMA_STUCK_GPU"] = "5"
        os.environ["CYNQRA_GPU_PROBE_S"] = "1"
        self.addCleanup(os.environ.pop, "FAKE_LLAMA_STUCK_GPU", None)
        self.addCleanup(os.environ.pop, "CYNQRA_GPU_PROBE_S", None)
        rt = self.runtime(metal=FAKE_SERVER)
        rt.start(MODEL)
        self.assertEqual(rt.status["state"], "ready")
        self.assertIn("-ngl 0", rt.log_tail().splitlines()[0])  # restarted on the processor
        out = model_adapter.complete("Convert the founder objective", want_json=True,
                                     schema={"type": "object", "properties": {"a": {"type": "string"}}})
        self.assertIsNone(out["error"])

    def test_a_working_gpu_passes_its_probe(self):
        rt = self.runtime(metal=FAKE_SERVER)
        rt.start(MODEL)
        self.assertIn("-ngl auto", rt.log_tail().splitlines()[0])
        self.assertIn("gpu_probe_s", rt.status)

    def test_acceleration_plan(self):
        rt = self.runtime(cpu="c", vulkan="v")
        rt._gpus = []
        self.assertEqual([a for a, _ in rt.plan_accel("auto")], ["cpu"])
        self.assertEqual(rt.plan_accel("on"), [("vulkan", ["-ngl", "auto"]), ("cpu", ["-ngl", "0"])])
        self.assertEqual([a for a, _ in rt.plan_accel("off")], ["cpu"])
        rt = self.runtime(metal="m")
        self.assertEqual(rt.plan_accel("auto"), [("metal", ["-ngl", "auto"]), ("metal", ["-ngl", "0"])])
        self.assertEqual(rt.plan_accel("off"), [("metal", ["-ngl", "0"])])

    def test_automatic_uses_a_discrete_card_with_room_and_skips_integrated_graphics(self):
        rt = self.runtime(cpu="c", vulkan="v")
        cases = [("NVIDIA GeForce RTX 4060 Laptop GPU", 8188, True), ("AMD Radeon RX 7600M XT", 8176, True),
                 ("Intel(R) Arc(TM) A770 Graphics", 16032, True), ("Intel(R) Iris(R) Xe Graphics", 8000, False),
                 ("Intel(R) Arc(TM) Graphics", 16000, False), ("AMD Radeon(TM) Graphics", 2048, False),
                 ("NVIDIA GeForce MX450", 2048, False), ("llvmpipe (LLVM 17.0.6, 256 bits)", 32000, False)]
        for name, mib, used in cases:
            rt._gpus = [{"id": "Vulkan0", "name": name, "mib": mib, "free_mib": mib}]
            self.assertEqual([a for a, _ in rt.plan_accel("auto")][0] == "vulkan", used, name)

    def test_devices_are_read_from_llama_server(self):
        os.environ["FAKE_LLAMA_DEVICES"] = ("  Vulkan0: NVIDIA GeForce RTX 4060 Laptop GPU (8188 MiB, 7934 MiB free)\n"
                                            "  Vulkan1: Intel(R) UHD Graphics (4096 MiB, 3900 MiB free)")
        self.addCleanup(os.environ.pop, "FAKE_LLAMA_DEVICES", None)
        rt = self.runtime(cpu=FAKE_SERVER, vulkan=FAKE_SERVER)
        rt._gpus = None
        self.assertEqual([(d["id"], d["mib"]) for d in rt.gpus()], [("Vulkan0", 8188), ("Vulkan1", 4096)])
        self.assertEqual(rt.discrete_gpu()["name"], "NVIDIA GeForce RTX 4060 Laptop GPU")
        self.assertEqual(rt.snapshot()["gpu_pick"], "NVIDIA GeForce RTX 4060 Laptop GPU")
        self.assertEqual(runtime.parse_devices("Available devices:\n  (none)\n"), [])

    def test_a_server_that_cannot_load_the_model_is_an_error_with_its_log(self):
        os.environ["FAKE_LLAMA_EXIT"] = "1"
        rt = self.runtime()
        with self.assertRaises(ModelRuntimeError):
            rt.start(MODEL)
        self.assertEqual(rt.status["state"], "error")
        self.assertIn("error loading model", rt.status["log"])

    def test_no_server_is_a_clear_error(self):
        rt = Runtime(self.tmp.path / "rt2", servers={})
        with self.assertRaises(ModelRuntimeError) as cm:
            rt.start(MODEL)
        self.assertIn("llama-server is missing", str(cm.exception))


class AppApiTests(DesktopBase):
    def setUp(self):
        super().setUp()
        self.rt = self.runtime()
        self.app = App(self.tmp.path / "runs", runtime=self.rt)
        self.srv = make_server(self.app, 0)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.app.close()
        super().tearDown()

    def test_first_launch_download_and_start_through_the_api(self):
        st = desktop.http(self.base + "/api/state")
        self.assertTrue(st["desktop"])
        self.assertEqual(st["runtime"]["state"], "none")
        self.assertEqual(len(st["runtime"]["catalog"]), len([m for m in runtime.CATALOG if not m.get("hidden")]))
        desktop.http(self.base + "/api/runtime/start", {"model": MODEL})
        for _ in range(200):
            st = desktop.http(self.base + "/api/state")
            if st["runtime"]["state"] in ("ready", "error"):
                break
            time.sleep(0.1)
        self.assertEqual(st["runtime"]["state"], "ready", st["runtime"]["error"])
        self.assertEqual(st["runtime"]["model_name"], "Qwen3.5 4B")
        self.assertTrue([m for m in st["runtime"]["catalog"] if m["id"] == MODEL][0]["installed"])
        with self.assertRaises(RuntimeError):
            desktop.http(self.base + "/api/runtime/gpu", {"gpu": "maybe"})
        desktop.http(self.base + "/api/runtime/gpu", {"gpu": "on"})
        self.assertEqual(self.rt.settings()["gpu"], "on")

    def test_unknown_model_is_refused(self):
        with self.assertRaises(RuntimeError) as cm:
            desktop.http(self.base + "/api/runtime/start", {"model": "llama-9000"})
        self.assertIn("HTTP 400", str(cm.exception))

    def test_quit_ends_the_app(self):
        self.assertFalse(self.app.quit.is_set())
        desktop.http(self.base + "/api/app/quit", {})
        self.assertTrue(self.app.quit.is_set())

    def test_only_the_apps_own_page_counts_as_an_open_window(self):
        desktop.http(self.base + "/api/state")
        self.assertEqual(desktop.http(self.base + "/api/state")["window_polls"], 0)
        desktop.http(self.base + "/api/state?window=1")
        self.assertEqual(desktop.http(self.base + "/api/state")["window_polls"], 1)

    def test_favicon_and_icon(self):
        with urllib.request.urlopen(self.base + "/favicon.ico") as r:
            self.assertEqual(r.read()[:8], b"\x89PNG\r\n\x1a\n")


class PlainAppTests(unittest.TestCase):
    def test_runtime_routes_are_not_part_of_the_plain_web_app(self):
        tmp = TempDir()
        app = App(tmp.path)
        srv = make_server(app, 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            self.assertNotIn("desktop", desktop.http(base + "/api/state"))
            with self.assertRaises(RuntimeError):
                desktop.http(base + "/api/app/quit", {})
            with self.assertRaises(RuntimeError):
                desktop.http(base + "/api/runtime/start", {"model": MODEL})
        finally:
            srv.shutdown()
            srv.server_close()
            app.close()
            tmp.cleanup()


class WholeRunTests(DesktopBase):
    """desktop.py --e2e and --check-model, the commands the build machines run with a real model."""

    def setUp(self):
        super().setUp()
        self._find, runtime.find_servers = runtime.find_servers, lambda: {"cpu": FAKE_SERVER}
        os.environ["CYNQRA_REPORTS_DIR"] = str(self.tmp.path / "reports")

    def tearDown(self):
        runtime.find_servers = self._find
        super().tearDown()

    def args(self, **kw):
        base = dict(data=str(self.tmp.path / "data"), gpu=None, max_resumes=3, max_minutes=10, company="Test",
                    objective="Build me an internal tracker for candidates.", e2e=None, check_model=None)
        base.update(kw)
        return argparse.Namespace(**base)

    def test_e2e_runs_the_whole_journey_through_the_app_api(self):
        self.assertEqual(desktop.e2e(self.args(e2e=MODEL)), 0)
        reports = sorted((self.tmp.path / "reports").glob("live_*.json"))
        rep = json.loads(reports[-1].read_text())
        self.assertEqual(rep["outcome"], "PASS", rep["reason"])
        self.assertEqual(rep["phase"], "accepted")
        self.assertEqual(rep["model"]["server"], "llama.cpp llama-server")
        self.assertTrue(rep["product_tests"]["passed"])
        self.assertEqual(rep["health"]["status"], 200)
        kinds = [d["kind"] for d in rep["decisions"]]
        self.assertEqual(kinds[:3], ["submit_objective", "approve_workforce", "approve_roadmap"])
        self.assertIn("accept_delivery", kinds)
        self.assertTrue(Path(rep["product_copy"], "app.py").exists())
        self.assertGreater(len(rep["calls"]), 5)

    def test_check_model_structures_and_writes_code_that_passes(self):
        self.assertEqual(desktop.check_model(self.args(check_model=MODEL)), 0)
        rep = json.loads(sorted((self.tmp.path / "reports").glob("check_*.json"))[-1].read_text())
        self.assertTrue(rep["passed"])
        self.assertEqual((rep["read_tps"], rep["write_tps"]), (250.0, 20.0))  # llama-server's own timings


class SelfTestTests(unittest.TestCase):
    def test_selftest_passes_on_this_machine(self):
        saved = no_model_env()
        tmp = TempDir()
        os.environ["CYNQRA_DATA_DIR"] = str(tmp.path)
        find, runtime.find_servers = runtime.find_servers, lambda: {"cpu": FAKE_SERVER}
        try:
            self.assertEqual(desktop.selftest(argparse.Namespace(online=False)), 0)
            out = json.loads((tmp.path / "selftest.json").read_text())
            self.assertTrue(out["ok"])
            self.assertIn("fake0000", [r for r in out["results"] if r["check"] == "llama-server runs"][0]["detail"])
        finally:
            runtime.find_servers = find
            tmp.cleanup()
            restore_env(saved)



class WorkforceDemoTests(DesktopBase):
    """desktop.py --workforce local, the [workforce] run, against the llama-server test double: three catalog
    models downloaded (from a fake Hugging Face), registered, probed, the synthesized workforce approved, Engineer
    A's model faulted, replaced, and the product delivered."""

    args = WholeRunTests.args

    def setUp(self):
        super().setUp()
        self._find, runtime.find_servers = runtime.find_servers, lambda: {"cpu": FAKE_SERVER}
        os.environ["CYNQRA_REPORTS_DIR"] = str(self.tmp.path / "reports")
        import workforce_demo
        self.demo = workforce_demo
        files = {}
        for ref, _ in workforce_demo.LOCAL:
            for repo, path in BY_ID[ref]["files"]:
                files[(repo, path)] = os.urandom(1024 * 64)
        self.hf.close()
        self.hf = FakeHF(files)
        runtime.HF = self.hf.base

    def tearDown(self):
        runtime.find_servers = self._find
        super().tearDown()

    def test_the_workforce_demonstration_passes(self):
        args = self.args(workforce="local", budget_usd=2.0, no_probe=False, max_minutes=10,
                         objective="Build me an internal tracker for candidates.")
        self.assertEqual(self.demo.run(args), 0)
        rep = json.loads(sorted((self.tmp.path / "reports").glob("workforce_*.json"))[-1].read_text())
        self.assertEqual(rep["outcome"], "PASS", rep["reason"])
        self.assertEqual([d["kind"] for d in rep["decisions"]][:2], ["approve_workforce", "approve_roadmap"])
        self.assertTrue(rep["workforce_proposal"]["roles"])
        self.assertTrue(rep["replacements"] and rep["replacements"][0]["from"] == rep["fault"]["model_id"])
        self.assertIn("inference", rep["economics"]["layers"])


class PackagingTests(unittest.TestCase):
    def test_every_module_the_app_imports_is_packaged(self):
        """The [workforce] run of 27 September failed on ModuleNotFoundError: workforce_demo was never copied into
        the app. Every top-level module desktop.py imports from the POC folder must be in the build's APP_FILES."""
        import ast
        import importlib.util
        spec = importlib.util.spec_from_file_location("build", POC.parent / "desktop" / "build.py")
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        tree = ast.parse((POC / "desktop.py").read_text(encoding="utf-8"))
        names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        local = {x for x in names if (POC / f"{x}.py").exists() or (POC / x).is_dir()}
        packaged = {f.removesuffix(".py") for f in build.APP_FILES}
        self.assertEqual(local - packaged, set())

if __name__ == "__main__":
    unittest.main()
