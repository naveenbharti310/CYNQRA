"""HTTP API and web UI for the POC. Standard library only. Binds to 127.0.0.1 only.

GET  /api/state                     everything the UI shows
POST /api/company                   {name, mode: demo|live, scenario}  (scenario: a prepared demo)
POST /api/objective/draft           {messy}
POST /api/objective/fields          {fields}
POST /api/objective/guardrails      {budget_usd, time_value_per_hour, constraints, governance}
POST /api/objective/founder         {leads, stage, hours_per_week, background}  what the founder brings
POST /api/founder/define            {founder}  step 3: define yourself; the team and budget follow for step 4
POST /api/rework                    {note, budget_usd}  step 7: what to change; the team plans the rework
POST /api/worker/rename             {worker_id, name}   the founder names a team member; the seat and record stay
POST /api/objective/submit          hand the objective over: requirements, then the proposed workforce
GET  /api/update                    the founder's update: numbers, learned, decided, at risk, waiting for them
POST /api/feedback                  {text}  what users said; it goes into the next cycle
POST /api/live/check                Cynqra checks the live product is up
POST /api/cycle                     {note, budget_usd}  the next cycle on the live product
POST /api/decisions/<id>            {action: approve|reject|request_evidence, note, edited}
POST /api/run/step
POST /api/run/auto                  {on, delay}
POST /api/killswitch                {on}
POST /api/run/resume                retry after a model or network error
GET  /api/replay/<task_id>
GET  /api/explain/<task_id>          why that work item's intelligence was chosen, and why it changed (controller.py)
GET  /api/decisions/<sd_id>/replay   a selection decision reproduced from its own immutable snapshot
GET  /api/intelligence/decisions     the run's selection decisions (?work_item=t_03 for one work item)
GET  /api/policies                   every policy the control plane decides by, with its version and hash
GET  /api/graph?q=approves|owns|depends&subject=...
GET  /api/intelligence              the Intelligence Layer: provider connections (credentials described, never
                                    revealed), the registry, the provider types, running probes
POST /api/connections               connect a provider {type, name, endpoint, auth: {method: env|secret|none,
                                    env_var | secret}, server (local), models, account, region, rate_limits,
                                    settings, price_per_m, machine_usd_per_hour}; its models are discovered
POST /api/connections/<id>/discover|update|remove   update: {models, settings, rate_limits, price_per_m,
                                    machine_usd_per_hour, name, account, region}; then discovered again, and
                                    each new hosted model does Cynqra's evaluation work in the background
POST /api/connections/<id>/catalog  every model the provider lists, offered now or not, to search and choose from
POST /api/intelligence              register an intelligence a connection offers but does not list
                                    {connection_id, ref, name, ...facts}
POST /api/intelligence/<id>/fault|fallback|retire|probe
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
import os
import re
import shutil
import signal
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .deploy import stop_all
from .engine import Engine, EngineError
from .intelligence import IntelligenceError
from . import policies
from .probe import probe
from .protocol import ProtocolError
from .intelligence_layer import IntelligenceSupply, SupplyError
from .runtime import ModelRuntimeError

UI = Path(__file__).resolve().parent.parent / "ui"
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/javascript", ".js")


class App:
    def __init__(self, data_root: Path, intelligence_factory=None, runtime=None, auto_evaluate: bool | None = None):
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.factory = intelligence_factory
        self.runtime = runtime  # the desktop app's model on this machine; None for the plain web app
        self.quit = threading.Event()
        self.last_seen = time.time()  # the window's last poll: the desktop app notices a closed window
        self.window_polls = 0  # polls from the app's own page (?window=1), not from scripts or tests
        # The Intelligence Layer sits beside the runs, not in one: its connections outlive a run, and what Cynqra
        # learns about each intelligence carries across projects.
        self.supply = IntelligenceSupply(self.root / "control", runtime=runtime)
        if runtime is not None:  # the desktop app: the models this computer can run, as a local provider connection
            local = self.supply.connections.find(origin="app", name="This computer") or self.supply.connections.create(
                {"type": "local", "server": "llama", "name": "This computer", "auth": {"method": "none"}}, origin="app")
            self.supply.discover(local["id"])
        self.probes: dict[str, dict] = {}
        # A newly connected model does Cynqra's evaluation work before any project relies on it, so the Router
        # chooses from measured evidence, not from a name or a default (CYNQRA_AUTO_EVALUATE=0 turns it off).
        self.auto_evaluate = (os.environ.get("CYNQRA_AUTO_EVALUATE", "1") != "0") if auto_evaluate is None \
            else auto_evaluate
        self._eval_lock = threading.Lock()
        self.engine = self._new_engine()
        self.auto = {"on": False, "delay": 0.9}
        self.last_step: dict = {}
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _new_engine(self) -> Engine:
        intel = self.factory() if self.factory else None
        return Engine(self.root / "current", intelligence=intel, supply=self.supply, memory=self.root / "lessons.json")

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
        self.last_step = {"did": d["outcome_label"], "decision": d["id"], "kind": d["kind"]}
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

    def supply_call(self, what: str, target: str | None, body: dict):
        sup = self.supply
        if what == "connect":
            out = sup.connect(body)
            self.evaluate_new(out["intelligence"])
            return out
        if what == "catalog":
            return sup.catalog(target)
        if what == "discover":
            found = sup.discover(target)
            self.evaluate_new(found)
            return {"intelligence": found, "connection": sup.connections.public(target)}
        if what == "update":
            sup.connections.update(target, body)
            found = sup.discover(target)
            self.evaluate_new(found)
            return {"intelligence": found, "connection": sup.connections.public(target)}
        if what == "disconnect":
            sup.remove_connection(target)
            return {"ok": True}
        if what == "register":
            conn = sup.connections.get(str(body.get("connection_id") or ""))
            return sup.registry.register({k: v for k, v in body.items() if k != "connection_id"}, conn["id"],
                                         source="registered")
        if what == "fault":
            return sup.registry.set_fault(target, body.get("offline"), body.get("max_reply"))
        if what == "fallback":
            return sup.registry.set_fallback(target, str(body.get("fallback_id") or ""))
        if what == "retire":
            sup.registry.retire(target, "retired by the founder")
            return {"ok": True}
        if what == "probe":
            sup.registry.get(target)
            if (self.probes.get(target) or {}).get("state") == "running":
                raise EngineError("a probe of this intelligence is already running")
            if self.auto["on"]:
                raise EngineError("pause the run before probing: one model runs at a time on this machine")
            self.probes[target] = {"state": "running", "log": []}

            def go():
                try:
                    r = probe(sup, target, log=self.probes[target]["log"].append)
                    self.probes[target].update(state="done", result=r)
                except Exception as exc:  # noqa: BLE001 - shown on the intelligence's card
                    self.probes[target].update(state="error", error=str(exc))
            threading.Thread(target=go, daemon=True).start()
            return self.probes[target]
        raise KeyError(what)

    def evaluate_new(self, entries: list[dict]) -> None:
        """Every hosted model with no measured record does Cynqra's evaluation work (probe.py) in the background, one
        at a time. A model on this computer is evaluated on request: starting it loads gigabytes."""
        if not self.auto_evaluate:
            return
        reg = self.supply.registry
        todo = [e["id"] for e in entries if not e.get("local") and e.get("status") != "retired"
                and not reg.stats(e["id"])["attempts"]
                and (self.probes.get(e["id"]) or {}).get("state") not in ("queued", "running", "done")]
        for mid in todo:
            self.probes[mid] = {"state": "queued", "log": [], "auto": True}
        if not todo:
            return

        def go():
            with self._eval_lock:
                for mid in todo:
                    if self._stop.is_set():
                        return
                    self.probes[mid]["state"] = "running"
                    try:
                        r = probe(self.supply, mid, log=self.probes[mid]["log"].append)
                        self.probes[mid].update(state="done", result=r)
                    except Exception as exc:  # noqa: BLE001 - shown on the intelligence's card
                        self.probes[mid].update(state="error", error=str(exc))
        threading.Thread(target=go, daemon=True).start()

    def close(self) -> None:
        self._stop.set()
        self.engine.close()
        self.supply.close()
        stop_all()


LOCAL_NAMES = ("127.0.0.1", "localhost")
MAX_BODY = 2_000_000  # a command is a small JSON object; nothing Cynqra's page sends comes near this
# Every response: no other site may show Cynqra's pages inside its own (a hidden frame could trick a click on
# "approve"), load its answers as images or scripts, or run anything on its pages but Cynqra's own scripts.
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                               "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
                               "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def stop_on_terminate() -> None:
    """A terminate signal (a shutdown, a task or service manager) stops Cynqra as Ctrl+C does, so its clean-up runs
    and the product it deployed and the model server stop with it, instead of being left running unwatched."""
    def handler(signum, frame):
        raise KeyboardInterrupt
    try:
        signal.signal(signal.SIGTERM, handler)
    except (ValueError, OSError, AttributeError):  # not the main thread, or no such signal here
        pass


def make_server(app: App, port: int = 8750) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            return

        def _local(self) -> bool:
            """Only Cynqra's own page and tools may use the API. Binding to 127.0.0.1 is not enough: any website open
            in the same browser can send requests to it, and a name an attacker controls can be pointed at
            127.0.0.1 (DNS rebinding). So the request must be addressed to this machine by name, a browser request
            must come from Cynqra's own page, and a command must be JSON, which a page elsewhere cannot send
            without the browser first asking this server, which never agrees."""
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].lower()
            if host not in LOCAL_NAMES:
                return False
            # a browser says where a request comes from; one from another site is refused even without an Origin
            # (a plain link or image), except opening Cynqra's page itself
            fetch_site = (self.headers.get("Sec-Fetch-Site") or "").lower()
            if fetch_site in ("cross-site", "same-site") and not (
                    self.command == "GET" and self.headers.get("Sec-Fetch-Mode") == "navigate"
                    and urlparse(self.path).path in ("/", "/index.html")):
                return False
            origin = self.headers.get("Origin")
            if origin:
                o = urlparse(origin)
                if o.hostname not in LOCAL_NAMES or o.port != self.server.server_address[1]:
                    return False
            return self.command != "POST" or self.headers.get_content_type() == "application/json"

        def _send(self, code: int, body, kind: str = "application/json", extra: dict | None = None):
            data = body if isinstance(body, (bytes, bytearray)) else json.dumps(body, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for k, v in SECURITY_HEADERS.items():
                self.send_header(k, v)
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict:
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                raise EngineError("Content-Length must be a number") from None
            if n < 0 or n > MAX_BODY:
                raise EngineError(f"a command must be between 0 and {MAX_BODY} bytes")
            if not n:
                return {}
            data = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(data, dict):
                raise EngineError("body must be a JSON object")
            return data

        def _guard(self, fn):
            try:
                return self._send(200, fn())
            except (EngineError, IntelligenceError, ProtocolError, ModelRuntimeError, SupplyError, ValueError, KeyError) as exc:
                return self._send(400, {"error": str(exc)})
            except Exception as exc:  # noqa: BLE001 - shown to the founder, never a dropped connection
                return self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

        def do_GET(self):
            if not self._local():
                return self._send(403, {"error": "only Cynqra's own page may use this server"})
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
            m = re.match(r"^/api/explain/(t_\w+)$", path)
            if m:  # why this work item's intelligence was chosen, and why it changed, from the record
                return self._guard(lambda: app.engine.explain(m.group(1)))
            m = re.match(r"^/api/decisions/(sd_\d+)/replay$", path)
            if m:
                return self._guard(lambda: app.engine.replay_decision(m.group(1)))
            if path == "/api/intelligence/decisions":
                q = parse_qs(u.query)
                return self._guard(lambda: {"decisions": app.engine.decisions(q.get("work_item", [None])[0])[-200:]})
            if path == "/api/policies":
                return self._guard(lambda: {"policies": policies.catalog()})
            if path == "/api/intelligence":
                return self._guard(lambda: {**app.supply.snapshot(), "probes": app.probes})
            if path == "/api/update":
                return self._guard(lambda: app.engine.update())
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
            if not self._local():
                return self._send(403, {"error": "only Cynqra's own page may use this server"})
            path = urlparse(self.path).path
            try:
                body = self._body()
            except (ValueError, EngineError) as exc:
                return self._send(400, {"error": str(exc)})
            e = app.engine
            routes = {
                "/api/company": lambda: e.create_company(body.get("name", ""), body.get("mode", "demo"),
                                                         body.get("scenario")),
                "/api/objective/draft": lambda: e.draft_objective(body.get("messy", "")),
                "/api/objective/fields": lambda: e.edit_objective(body.get("fields") or {}),
                "/api/objective/guardrails": lambda: e.set_guardrails(body.get("budget_usd"),
                                                                      body.get("time_value_per_hour"),
                                                                      body.get("constraints"), body.get("governance")),
                "/api/connections": lambda: app.supply_call("connect", None, body),
                "/api/intelligence": lambda: app.supply_call("register", None, body),
                "/api/objective/submit": e.submit_objective,
                "/api/objective/founder": lambda: e.set_founder(body.get("founder") or {}),
                "/api/founder/define": lambda: e.define_founder(body.get("founder") or {}),
                "/api/feedback": lambda: e.feedback(body.get("text", "")),
                "/api/live/check": e.check_live,
                "/api/cycle": lambda: e.start_cycle(body.get("note", ""), body.get("budget_usd")),
                "/api/rework": lambda: e.rework(body.get("note", ""), body.get("budget_usd")),
                "/api/worker/rename": lambda: e.rename_worker(body.get("worker_id", ""), body.get("name", "")),
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
            m = re.match(r"^/api/connections/(conn_[a-z0-9]+)/(discover|update|remove|catalog)$", path)
            if m:
                what = {"remove": "disconnect"}.get(m.group(2), m.group(2))
                return self._guard(lambda: app.supply_call(what, m.group(1), body))
            m = re.match(r"^/api/intelligence/([a-z0-9-]+)/(fault|fallback|retire|probe)$", path)
            if m:
                return self._guard(lambda: app.supply_call(m.group(2), m.group(1), body))
            m = re.match(r"^/api/decisions/(dec_\w+)$", path)
            if m:
                return self._guard(lambda: app.decide(m.group(1), body.get("action", ""), body.get("note", ""),
                                                       body.get("edited") or None))
            return self._send(404, {"error": "not found"})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
