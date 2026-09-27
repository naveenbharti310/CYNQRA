"""HTTP API and web UI for the POC. Standard library only. Binds to 127.0.0.1 only.

GET  /api/state                     everything the UI shows
POST /api/company                   {name, mode}
POST /api/objective/draft           {messy}
POST /api/objective/fields          {fields}
POST /api/objective/guardrails      {budget_cap}
POST /api/objective/confirm
POST /api/decisions/<id>            {action: approve|reject|request_evidence, note, edited}
POST /api/run/step
POST /api/run/auto                  {on, delay}
POST /api/killswitch                {on}
POST /api/run/resume                retry after a model or network error
GET  /api/replay/<task_id>
GET  /api/graph?q=approves|owns|depends&subject=...
GET  /api/export                    builds and downloads the export bundle
POST /api/reset                     archives this run and starts a new one

Desktop app only (App made with a runtime):
POST /api/runtime/start             {model}  download the model if needed, then start it
POST /api/runtime/cancel            pause a download, or stop a start in progress
POST /api/runtime/stop              stop the model server
POST /api/runtime/remove            {model}  delete a downloaded model
POST /api/runtime/gpu               {gpu: auto|on|off}
POST /api/app/quit                  close the app: the model server and the deployed product stop
"""
from __future__ import annotations

import json
import mimetypes
import re
import shutil
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .deploy import stop_all
from .engine import Engine, EngineError
from .intelligence import IntelligenceError
from .probe import probe
from .protocol import ProtocolError
from .registry import Registry, RegistryError
from .runtime import ModelRuntimeError
from .workforce import Workforce

UI = Path(__file__).resolve().parent.parent / "ui"
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/javascript", ".js")


class App:
    def __init__(self, data_root: Path, intelligence_factory=None, runtime=None):
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.factory = intelligence_factory
        self.runtime = runtime  # the desktop app's model on this machine; None for the plain web app
        self.quit = threading.Event()
        self.last_seen = time.time()  # the window's last poll: the desktop app notices a closed window
        self.window_polls = 0  # polls from the app's own page (?window=1), not from scripts or tests
        # The model registry sits beside the runs, not in one: what Cynqra learns about models outlives a run.
        self.registry = Registry(self.root / "registry", runtime=runtime)
        self.workforce = Workforce(self.registry)
        self.probes: dict[str, dict] = {}
        self.engine = self._new_engine()
        self.auto = {"on": False, "delay": 0.9}
        self.last_step: dict = {}
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _new_engine(self) -> Engine:
        intel = self.factory() if self.factory else None
        return Engine(self.root / "current", intelligence=intel, workforce=self.workforce)

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self.auto["on"]:
                try:
                    self.last_step = self.engine.step()
                except Exception as exc:  # the loop must not die; the error is shown, never hidden
                    self.last_step = {"did": "error", "why": str(exc)}
                if self.last_step.get("did") in ("idle", "error"):
                    time.sleep(0.4)
                else:
                    time.sleep(self.auto["delay"])
            else:
                time.sleep(0.2)

    def reset(self) -> None:
        self.auto["on"] = False
        with self.engine.lock:
            self.engine.close()
            cur = self.root / "current"
            if cur.exists():
                shutil.move(str(cur), str(self.root / f"archive_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"))
            self.engine = self._new_engine()

    def step(self) -> dict:
        self.last_step = self.engine.step()
        return self.last_step

    def decide(self, decision_id: str, action: str, note: str, edited) -> dict:
        d = self.engine.decide(decision_id, action, note, edited)
        if action == "approve":
            self.last_step = ({"did": "plan approved"} if d["kind"] == "approve_plan"
                              else {"did": "approved", "decision": d["id"], "kind": d["kind"]})
        return d

    def window_poll(self) -> None:
        self.last_seen = time.time()
        self.window_polls += 1

    def state(self) -> dict:
        s = self.engine.snapshot()
        s["auto"] = dict(self.auto)
        s["last_step"] = self.last_step
        if self.runtime is not None:
            s["desktop"] = True
            s["runtime"] = self.runtime.snapshot()
            s["window_polls"] = self.window_polls
        return s

    def runtime_call(self, what: str, body: dict) -> dict:
        rt = self.runtime
        if rt is None:
            raise EngineError("the model controls are part of the desktop app")
        if what == "start":
            if self.auto["on"] and self.engine.meta.get("phase") == "running":
                raise EngineError("pause the run before changing the model")
            rt.install_and_start(str(body.get("model") or ""))
        elif what == "cancel":
            rt.cancel()
        elif what == "stop":
            self.auto["on"] = False
            rt.stop()
        elif what == "remove":
            rt.remove(str(body.get("model") or ""))
        elif what == "gpu":
            if body.get("gpu") not in ("auto", "on", "off"):
                raise EngineError("gpu must be auto, on or off")
            rt.save_settings(gpu=body["gpu"])
        else:
            raise KeyError(what)
        return rt.snapshot()

    def models_call(self, model_id: str | None, what: str, body: dict):
        reg = self.registry
        if what == "register":
            return reg.register(body)
        if what == "fault":
            return reg.set_fault(model_id, body.get("offline"), body.get("max_reply"))
        if what == "remove":
            reg.remove(model_id)
            return {"ok": True}
        if what == "probe":
            reg.get(model_id)
            if (self.probes.get(model_id) or {}).get("state") == "running":
                raise EngineError("a probe of this model is already running")
            if self.auto["on"]:
                raise EngineError("pause the run before probing a model: one model runs at a time on this machine")
            self.probes[model_id] = {"state": "running", "log": []}

            def go():
                try:
                    r = probe(reg, model_id, log=self.probes[model_id]["log"].append)
                    self.probes[model_id].update(state="done", result=r)
                except Exception as exc:  # noqa: BLE001 - shown on the model's card
                    self.probes[model_id].update(state="error", error=str(exc))
            threading.Thread(target=go, daemon=True).start()
            return self.probes[model_id]
        raise KeyError(what)

    def close(self) -> None:
        self._stop.set()
        self.engine.close()
        self.registry.close()
        stop_all()


def make_server(app: App, port: int = 8750) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            return

        def _send(self, code: int, body, kind: str = "application/json", extra: dict | None = None):
            data = body if isinstance(body, (bytes, bytearray)) else json.dumps(body, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            data = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(data, dict):
                raise EngineError("body must be a JSON object")
            return data

        def _guard(self, fn):
            try:
                return self._send(200, fn())
            except (EngineError, IntelligenceError, ProtocolError, ModelRuntimeError, RegistryError, ValueError, KeyError) as exc:
                return self._send(400, {"error": str(exc)})
            except Exception as exc:  # noqa: BLE001 - shown to the founder, never a dropped connection
                return self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

        def do_GET(self):
            u = urlparse(self.path)
            path = u.path
            if path == "/favicon.ico":
                return self._send(200, (UI / "icon.png").read_bytes(), "image/png")
            if path in ("/", "/index.html"):
                return self._send(200, (UI / "index.html").read_bytes(), "text/html; charset=utf-8")
            if path.startswith("/ui/"):
                f = (UI / path[4:]).resolve()
                if UI.resolve() not in f.parents or not f.is_file():
                    return self._send(404, {"error": "not found"})
                kind = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                return self._send(200, f.read_bytes(), kind)
            if path == "/api/state":
                if "window" in parse_qs(u.query):
                    app.window_poll()
                return self._guard(app.state)
            m = re.match(r"^/api/replay/(t_\w+)$", path)
            if m:
                return self._guard(lambda: app.engine.replay(m.group(1)))
            if path == "/api/models":
                return self._guard(lambda: {"models": app.registry.snapshot(), "probes": app.probes})
            if path == "/api/graph":
                q = parse_qs(u.query)
                return self._guard(lambda: app.engine.graph(q.get("q", [""])[0], q.get("subject", [""])[0]))
            if path == "/api/export":
                try:
                    zpath = Path(app.engine.export())
                except EngineError as exc:
                    return self._send(400, {"error": str(exc)})
                return self._send(200, zpath.read_bytes(), "application/zip",
                                  {"Content-Disposition": f'attachment; filename="{zpath.name}"'})
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                body = self._body()
            except (ValueError, EngineError) as exc:
                return self._send(400, {"error": str(exc)})
            e = app.engine
            routes = {
                "/api/company": lambda: e.create_company(body.get("name", ""), body.get("mode", "demo")),
                "/api/objective/draft": lambda: e.draft_objective(body.get("messy", "")),
                "/api/objective/fields": lambda: e.edit_objective(body.get("fields") or {}),
                "/api/objective/guardrails": lambda: e.set_guardrails(body.get("budget_cap"), body.get("risk_tolerance"),
                                                                      body.get("budget_usd"), body.get("time_value_per_hour")),
                "/api/models": lambda: app.models_call(None, "register", body),
                "/api/objective/confirm": e.confirm_objective,
                "/api/run/step": app.step,
                "/api/killswitch": lambda: e.kill_switch(bool(body.get("on"))),
                "/api/run/resume": e.resume,
            }
            if path in routes:
                return self._guard(routes[path])
            if path == "/api/run/auto":
                try:
                    delay = None if body.get("delay") is None else max(0.0, min(5.0, float(body["delay"])))
                except (TypeError, ValueError):
                    return self._send(400, {"error": "delay must be a number of seconds"})
                app.auto["on"] = bool(body.get("on"))
                if delay is not None:
                    app.auto["delay"] = delay
                return self._send(200, app.auto)
            if path == "/api/reset":
                app.reset()
                return self._send(200, {"ok": True})
            m = re.match(r"^/api/runtime/(start|cancel|stop|remove|gpu)$", path)
            if m:
                return self._guard(lambda: app.runtime_call(m.group(1), body))
            if path == "/api/app/quit":
                if app.runtime is None:
                    return self._send(404, {"error": "not found"})
                app.quit.set()
                return self._send(200, {"ok": True})
            m = re.match(r"^/api/models/([a-z0-9-]+)/(fault|remove|probe)$", path)
            if m:
                return self._guard(lambda: app.models_call(m.group(1), m.group(2), body))
            m = re.match(r"^/api/decisions/(dec_\w+)$", path)
            if m:
                return self._guard(lambda: app.decide(m.group(1), body.get("action", ""), body.get("note", ""),
                                                       body.get("edited") or None))
            return self._send(404, {"error": "not found"})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
