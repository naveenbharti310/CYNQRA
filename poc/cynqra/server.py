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
from .protocol import ProtocolError

UI = Path(__file__).resolve().parent.parent / "ui"
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/javascript", ".js")


class App:
    def __init__(self, data_root: Path, intelligence_factory=None):
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.factory = intelligence_factory
        self.engine = self._new_engine()
        self.auto = {"on": False, "delay": 0.9}
        self.last_step: dict = {}
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _new_engine(self) -> Engine:
        intel = self.factory() if self.factory else None
        return Engine(self.root / "current", intelligence=intel)

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

    def state(self) -> dict:
        s = self.engine.snapshot()
        s["auto"] = dict(self.auto)
        s["last_step"] = self.last_step
        return s

    def close(self) -> None:
        self._stop.set()
        self.engine.close()
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
            except (EngineError, IntelligenceError, ProtocolError, ValueError, KeyError) as exc:
                return self._send(400, {"error": str(exc)})
            except Exception as exc:  # noqa: BLE001 - shown to the founder, never a dropped connection
                return self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

        def do_GET(self):
            u = urlparse(self.path)
            path = u.path
            if path in ("/", "/index.html"):
                return self._send(200, (UI / "index.html").read_bytes(), "text/html; charset=utf-8")
            if path.startswith("/ui/"):
                f = (UI / path[4:]).resolve()
                if UI.resolve() not in f.parents or not f.is_file():
                    return self._send(404, {"error": "not found"})
                kind = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                return self._send(200, f.read_bytes(), kind)
            if path == "/api/state":
                return self._guard(app.state)
            m = re.match(r"^/api/replay/(t_\w+)$", path)
            if m:
                return self._guard(lambda: app.engine.replay(m.group(1)))
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
                "/api/objective/guardrails": lambda: e.set_guardrails(body.get("budget_cap"), body.get("risk_tolerance")),
                "/api/objective/confirm": e.confirm_objective,
                "/api/run/step": e.step,
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
            m = re.match(r"^/api/decisions/(dec_\w+)$", path)
            if m:
                return self._guard(lambda: e.decide(m.group(1), body.get("action", ""), body.get("note", ""),
                                                     body.get("edited") or None))
            return self._send(404, {"error": "not found"})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
