#!/usr/bin/env python3
"""Cynqra desktop app: the window, the open model on this machine, and the Cynqra server.

  Cynqra (the installed app)       opens the Cynqra window
  python poc/desktop.py            the same from a source checkout (needs llama-server on PATH,
                                   or CYNQRA_LLAMA_SERVER pointing at one)
  --headless [--port N]            no window: serve on 127.0.0.1 and print the address
  --selftest [--online]            check this installation; exit 0 when every check passes
  --window-test                    open the window, wait until its page has loaded, close it
  --check-model MODEL              download and start MODEL, then have it structure an objective
                                   and write a module that must pass its own tests
  --e2e MODEL "objective"          download and start MODEL, then run a whole Cynqra journey through
                                   the app's own HTTP API (what the window does), approving every
                                   decision; writes a report; exit 0 on PASS

Everything the app keeps is in one folder per user (CYNQRA_DATA_DIR overrides it):
  Windows %LOCALAPPDATA%\\Cynqra   macOS ~/Library/Application Support/Cynqra   Linux ~/.local/share/cynqra
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cynqra.runtime import BY_ID, CATALOG, ModelRuntimeError, Runtime, argv, recommended, resolve  # noqa: E402
from cynqra.server import App, make_server  # noqa: E402

VERSION = (HERE / "VERSION").read_text(encoding="utf-8").strip() if (HERE / "VERSION").exists() else "dev"
ICON = HERE / "ui" / "icon.png"


def data_dir() -> Path:
    if os.environ.get("CYNQRA_DATA_DIR"):
        return Path(os.environ["CYNQRA_DATA_DIR"])
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Cynqra"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Cynqra"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "cynqra"


def log_to_file(d: Path) -> None:
    """The window app has no console (pythonw, a macOS .app): its output goes to app.log."""
    log = d / "app.log"
    if log.exists() and log.stat().st_size > 5 * 1024 ** 2:
        log.replace(d / "app.log.1")
    f = open(log, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = f
    print(f"\n==== Cynqra {VERSION} started {datetime.now().isoformat(timespec='seconds')} "
          f"on {platform.platform()}, Python {platform.python_version()}")


class Desktop:
    """The app's parts in one process: the model runtime, the engine and the HTTP server on 127.0.0.1."""

    def __init__(self, d: Path, port: int = 0):
        self.d = Path(d)
        self.d.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("CYNQRA_REPORTS_DIR", str(self.d / "reports"))
        os.environ.setdefault("CYNQRA_TIMEOUT", "3600")
        self.runtime = Runtime(self.d / "runtime")
        self.app = App(self.d / "runs", runtime=self.runtime)
        self.server = make_server(self.app, port)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def autostart(self) -> None:
        """Start the model chosen last time, if it is on disk. The window shows it starting."""
        m = self.runtime.settings().get("model")
        if m in BY_ID and self.runtime.installed(m):
            self.runtime.install_and_start(m)

    def close(self) -> None:
        self.app.auto["on"] = False
        self.runtime.cancel()
        try:
            self.app.close()
        finally:
            self.runtime.stop()
            self.server.shutdown()
            self.server.server_close()


# --------------------------------------------------------------------------------------- window --
def app_browser() -> str | None:
    """A Chromium browser that can open a page as an app window (no tabs, no address bar).
    CYNQRA_BROWSER names one explicitly."""
    if os.environ.get("CYNQRA_BROWSER") and Path(os.environ["CYNQRA_BROWSER"]).exists():
        return os.environ["CYNQRA_BROWSER"]
    if sys.platform == "win32":
        roots = [os.environ.get(k) for k in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
        rels = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"]
        for rel in rels:
            for root in filter(None, roots):
                if Path(root, rel).exists():
                    return str(Path(root, rel))
        return None
    if sys.platform == "darwin":
        for app in ("Google Chrome", "Microsoft Edge", "Chromium", "Brave Browser"):
            p = Path(f"/Applications/{app}.app/Contents/MacOS/{app}")
            if p.exists():
                return str(p)
        return None
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "brave-browser"):
        if shutil.which(name):
            return shutil.which(name)
    return None


def window_args(exe: str, url: str, profile: Path) -> list[str]:
    """An app window: the page alone, no tabs or address bar, with a browser profile of Cynqra's own."""
    args = [exe, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
            "--window-size=1440,920", "--disable-features=Translate,msEdgeSidebarV2"]
    if sys.platform.startswith("linux") and os.environ.get("CI"):
        args.append("--no-sandbox")  # CI machines run as root, where Chromium's sandbox cannot start
    return args


def idle_for(desk: Desktop, seconds: float) -> bool:
    return time.time() - desk.app.last_seen > seconds


def open_window(desk: Desktop, loaded: threading.Event | None = None) -> None:
    """Show the app and return when its window is closed or Quit is chosen."""
    if loaded is not None:
        def watch_load():
            t0 = time.time()
            while not desk.app.quit.is_set():
                if desk.app.window_polls:
                    print(f"  the window's page polled the app after {time.time() - t0:.1f} s", flush=True)
                    loaded.set()
                    desk.app.quit.set()
                time.sleep(0.2)
        threading.Thread(target=watch_load, daemon=True).start()
    if sys.platform == "darwin" and not os.environ.get("CYNQRA_NO_WEBVIEW"):
        try:
            import webview  # pywebview, bundled with the macOS app: a native window
        except ImportError:
            webview = None
        if webview is not None:
            return _webview_window(desk, webview)
    exe = app_browser()
    if exe:
        proc = subprocess.Popen(window_args(exe, desk.url, desk.d / "window"), stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        handed_off = False
        while not desk.app.quit.is_set():
            if proc.poll() is not None and not handed_off:
                time.sleep(5)  # the window closed, or the browser handed it to a process it already had
                if idle_for(desk, 4):
                    return
                handed_off = True
            if handed_off and idle_for(desk, 150):  # a hidden window still polls about once a minute
                return
            time.sleep(0.5)
        if proc.poll() is None:
            proc.terminate()
        return
    webbrowser.open(desk.url)
    while not desk.app.quit.is_set() and not idle_for(desk, 150):
        time.sleep(1)


def _webview_window(desk: Desktop, webview) -> None:
    try:
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    except (KeyError, TypeError):
        pass
    win = webview.create_window("Cynqra", desk.url, width=1440, height=920, min_size=(960, 640), text_select=True)

    def watch_quit():
        desk.app.quit.wait()
        print("  closing the window", flush=True)
        try:
            win.destroy()
        except Exception as exc:  # noqa: BLE001 - the window may already be gone
            print(f"  closing the window: {exc}", flush=True)
    threading.Thread(target=watch_quit, daemon=True).start()
    try:
        from AppKit import NSApplication, NSImage  # the Dock shows Cynqra's icon, not Python's
        if ICON.exists():
            NSApplication.sharedApplication().setApplicationIconImage_(NSImage.alloc().initWithContentsOfFile_(str(ICON)))
    except Exception:  # noqa: BLE001 - cosmetic only
        pass
    print("  pywebview window created; starting its loop", flush=True)
    webview.start()
    print("  pywebview loop ended", flush=True)


def running_instance(d: Path) -> str | None:
    try:
        info = json.loads((d / "instance.json").read_text(encoding="utf-8"))
        with urllib.request.urlopen(info["url"] + "/api/state", timeout=3) as r:
            if r.status == 200 and json.loads(r.read()).get("desktop"):
                return info["url"]
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        pass
    return None


def run_app(args) -> int:
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    if not args.headless and (sys.stdout is None or not sys.stdout.isatty() or args.log_file):
        log_to_file(d)
    url = running_instance(d)
    if url and not args.headless:
        print(f"Cynqra is already running at {url}; opening another window.")
        exe = app_browser()
        if exe and sys.platform != "darwin":
            subprocess.Popen(window_args(exe, url, d / "window"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            webbrowser.open(url)
        return 0
    desk = Desktop(d, args.port)
    (d / "instance.json").write_text(json.dumps({"url": desk.url, "pid": os.getpid()}), encoding="utf-8")
    desk.autostart()
    print(f"Cynqra {VERSION} running at {desk.url}", flush=True)
    try:
        if args.headless:
            desk.app.quit.wait()
        else:
            open_window(desk)
    except KeyboardInterrupt:
        pass
    finally:
        print("Closing: stopping the model server and any product Cynqra deployed.", flush=True)
        desk.close()
        try:
            (d / "instance.json").unlink()
        except OSError:
            pass
    if not args.headless:  # everything is stopped; a window toolkit's leftover thread must not keep the app alive
        sys.stdout.flush()
        os._exit(0)
    return 0


# ------------------------------------------------------------------------------------ self-test --
def http(url: str, body=None, timeout: float = 30.0):
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
                                 method="GET" if body is None else "POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if r.headers.get_content_type() == "application/json" else raw
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{url} -> HTTP {exc.code}: {exc.read()[:400].decode(errors='replace')}") from exc


def scripted_journey(d: Path) -> str:
    """The engine's machinery on this machine: workers' tests run in a subprocess, the product is deployed as
    a process and health-checked. The workers' words are the demo script here; no model is involved."""
    from cynqra.engine import Engine
    e = Engine(d)
    try:
        e.create_company("Self test", "demo")
        e.draft_objective(e.demo_messy)
        e.confirm_objective()
        plan = [x for x in e.pending_decisions() if x["kind"] == "approve_plan"][0]
        e.decide(plan["id"], "approve")
        for _ in range(300):
            if e.meta["phase"] in ("accepted", "stopped", "stopped_error"):
                break
            r = e.step()
            if r["did"] == "idle":
                pend = e.pending_decisions()
                if pend:
                    e.decide(pend[0]["id"], "approve")
        if e.meta["phase"] != "accepted":
            raise RuntimeError(f"ended in phase {e.meta['phase']}: {e.meta.get('notice', '')}")
        with urllib.request.urlopen(e.live_url() + "/health", timeout=10) as r:
            if r.status != 200:
                raise RuntimeError(f"deployed product health {r.status}")
        m = e.metrics()
        return f"{m['tasks_verified']} of {m['tasks_total']} tasks verified, deployed and healthy at {e.live_url()}"
    finally:
        e.close()


def selftest(args) -> int:
    results = []

    def check(name, fn):
        t0 = time.time()
        try:
            detail = fn()
            results.append({"check": name, "ok": True, "detail": detail, "s": round(time.time() - t0, 1)})
        except Exception as exc:  # noqa: BLE001 - every failure is reported
            results.append({"check": name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"[:800],
                            "s": round(time.time() - t0, 1)})
        r = results[-1]
        print(f"  [{'PASS' if r['ok'] else 'FAIL'}] {name}: {r['detail']}  ({r['s']} s)", flush=True)

    print(f"Cynqra {VERSION} self-test on {platform.platform()}")
    data_dir().mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="selftest_", dir=data_dir()))  # inside the data folder, whatever its path
    check("Python", lambda: f"{platform.python_version()} at {sys.executable}")
    check("App files", lambda: _need([HERE / "ui" / "index.html", HERE / "ui" / "app.js", HERE / "ui" / "icon.png",
                                      HERE / "scenarios" / "candidate_tracker" / "scenario.json",
                                      HERE / "cynqra" / "objective_prompt.txt"]))

    def servers():
        rt = Runtime(tmp / "rt")
        if not rt.servers:
            raise RuntimeError("no llama-server in this installation")
        out = []
        for accel, exe in sorted(rt.servers.items()):
            p = subprocess.run([*argv(exe), "--version"], capture_output=True, encoding="utf-8", errors="replace", timeout=60,
                               creationflags=0x08000000 if os.name == "nt" else 0)
            text = (p.stdout + p.stderr).strip()
            if p.returncode != 0:
                raise RuntimeError(f"{accel} llama-server --version exited {p.returncode}: {text[-400:]}")
            ver = next((ln for ln in text.splitlines() if ln.startswith("version")), text.splitlines()[0] if text else "")
            out.append(f"{accel} ({ver.strip()})")
        return ", ".join(out)
    check("llama-server runs", servers)
    ram = Runtime(tmp / "rt").ram_gb
    check("Memory and model choice", lambda: f"{ram:.1f} GB; recommended {BY_ID[recommended(ram)]['name']}"
          if ram else "memory unknown; recommended " + BY_ID[recommended(None)]["name"])

    def web():
        desk = Desktop(tmp / "app")
        try:
            page = http(desk.url + "/")
            st = http(desk.url + "/api/state")
            if b"/ui/app.js" not in page or not st.get("desktop") or not st["runtime"]["catalog"]:
                raise RuntimeError("the page or the state is not the desktop app's")
            return f"page and state served at {desk.url}; {len(st['runtime']['catalog'])} models in the catalog"
        finally:
            desk.close()
    check("App server", web)
    check("Engine on this machine (scripted words, real tests and deploy)", lambda: scripted_journey(tmp / "engine"))
    if args.online:
        def online():
            out = []
            for m in CATALOG:
                spec = resolve(m)
                gb = spec["size"] / 1024 ** 3
                if abs(gb - m["size_gb"]) > 0.1 or not spec["sha256"]:
                    raise RuntimeError(f"{m['id']}: {spec['repo']}/{spec['path']} is {gb:.2f} GB, sha256 "
                                       f"{spec['sha256'][:12] or 'missing'}; catalog says {m['size_gb']} GB")
                out.append(f"{m['id']} {gb:.1f} GB at {spec['repo']}")
            return "; ".join(out)
        check("Model files on Hugging Face", online)
    shutil.rmtree(tmp, ignore_errors=True)
    ok = all(r["ok"] for r in results)
    out = data_dir() / "selftest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"version": VERSION, "platform": platform.platform(), "ok": ok, "results": results},
                              indent=1), encoding="utf-8")
    print(("PASS" if ok else "FAIL") + f": {sum(r['ok'] for r in results)} of {len(results)} checks passed. {out}")
    return 0 if ok else 1


def _need(paths: list[Path]) -> str:
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise RuntimeError("missing " + ", ".join(missing))
    return f"{len(paths)} files present"


def window_test(args) -> int:
    d = Path(tempfile.mkdtemp(prefix="cynqra_window_"))
    desk = Desktop(d)
    loaded = threading.Event()
    timer = threading.Timer(args.timeout, desk.app.quit.set)
    timer.start()

    def watchdog():  # a window toolkit that never hands control back must fail the test, not hang it
        time.sleep(args.timeout + 45)
        print(f"FAIL: the window did not close within {args.timeout + 45:.0f} s "
              f"({'loaded' if loaded.is_set() else 'never loaded'}; {desk.app.window_polls} polls)", flush=True)
        os._exit(1)
    threading.Thread(target=watchdog, daemon=True).start()
    try:
        open_window(desk, loaded)
    finally:
        timer.cancel()
        desk.close()
    print(("PASS: the window opened and loaded the app" if loaded.is_set() else
           f"FAIL: no page load within {args.timeout} s") + f" ({'pywebview' if sys.platform == 'darwin' else app_browser()})",
          flush=True)
    # pywebview on macOS leaves a thread behind that keeps the interpreter alive after its window closed
    os._exit(0 if loaded.is_set() else 1)


# ------------------------------------------------------------------------- real model checks --
# Cynqra's own kinds of work, small enough for a quick check of a model on this machine.
CHECK_OBJECTIVE = (
    "I run a small bakery and my staff keep losing track of custom cake orders. I want a simple internal web page "
    "where they can log an order with the pickup date, see what is due in the next few days, and mark orders as "
    "paid and picked up. Nothing public, no card payments, and it has to run on the shop laptop.")
CHECK_TASK = {"id": "t_03", "title": "Order store", "kind": "code", "owner_worker_id": "w_eng_a",
                   "expected_output": "store.py and test_store.py"}
CHECK_HANDOFF = {"acceptance_check": (
    "Write store.py and test_store.py, standard library only. OrderStore(path) keeps orders in one JSON file, "
    "loading it if it exists and saving after every change. add(customer, cake, pickup_date) returns the order dict "
    "(keys id, customer, cake, pickup_date, paid, picked_up; paid and picked_up start False) and raises ValueError "
    "when customer or cake is blank or pickup_date is not a real YYYY-MM-DD date. set_paid(order_id, paid) and "
    "set_picked_up(order_id, picked_up) raise KeyError for an unknown id. due_soon(today) returns orders not picked "
    "up whose pickup date is before today or within today plus 3 days, soonest first. Tests must cover every rule."),
    "context_ref": "bench", "artifacts": []}


def prepare_model(desk: Desktop, model_id: str, gpu: str | None) -> None:
    if gpu:
        desk.runtime.save_settings(gpu=gpu)
    done = threading.Event()

    def progress():
        last = -1
        while not done.wait(15):
            s = desk.runtime.status
            if s["state"] == "downloading" and s["total"]:
                pct = int(100 * s["done"] / s["total"])
                if pct != last:
                    print(f"  download {pct}%  {s['done'] / 1e9:.2f} of {s['total'] / 1e9:.2f} GB  "
                          f"{s['rate'] / 1e6:.0f} MB/s", flush=True)
                    last = pct
    threading.Thread(target=progress, daemon=True).start()
    t0 = time.time()
    try:
        path = desk.runtime.download(model_id)
        print(f"Model file: {path} ({path.stat().st_size / 1e9:.2f} GB) ready in {time.time() - t0:.0f} s", flush=True)
        t1 = time.time()
        base = desk.runtime.start(model_id)
        print(f"llama-server ({desk.runtime.status['accel']}) serving {BY_ID[model_id]['name']} at {base}, "
              f"loaded in {time.time() - t1:.0f} s", flush=True)
    finally:
        done.set()


def check_model(args) -> int:
    """A real model on this machine does Cynqra's two kinds of work: a structured answer, and code that
    passes its own tests (fixing it from the failures for up to three rounds)."""
    from cynqra.engine import OBJECTIVE_FIELDS
    from cynqra.intelligence import IntelligenceError, ModelSource
    from cynqra.verification import run_unittests
    desk = Desktop(Path(args.data) if args.data else data_dir())
    ok = False
    result = {"model": args.check_model, "platform": platform.platform(), "ram_gb": desk.runtime.ram_gb, "passed": False}
    t0 = time.time()
    try:
        prepare_model(desk, args.check_model, args.gpu)
        result["accel"] = desk.runtime.status["accel"]
        result["ready_s"] = round(time.time() - t0)
        src = ModelSource()
        data, u = src.structure_objective(CHECK_OBJECTIVE)
        empty = [k for k in OBJECTIVE_FIELDS if not str(data.get(k) or "").strip()]
        # The objective contract lets a model leave a field it finds no support for, for the founder to fill on
        # the confirm screen; one such field is acceptable, more means the model did not do the job.
        complete = len(empty) <= 1
        result.update(objective_fields_filled=len(OBJECTIVE_FIELDS) - len(empty), objective_left_for_founder=empty)
        print(f"  objective: {len(OBJECTIVE_FIELDS) - len(empty)} of {len(OBJECTIVE_FIELDS)} fields"
              + (f", left for the founder: {', '.join(empty)}" if empty else "")
              + f"; {u['tokens_in']} tokens in, {u['tokens_out']} out, {u['latency_s']:.0f} s{speed(u)}", flush=True)
        calls = [u]
        objective = {k: str(data.get(k) or "") for k in OBJECTIVE_FIELDS}
        work = Path(tempfile.mkdtemp(prefix="cynqra_check_"))
        feedback, previous, passed = "", {}, False
        for rnd in range(3):
            try:
                out, u = src.work(CHECK_TASK, worker="w_eng_a", objective=objective, rules=[], handoff=CHECK_HANDOFF,
                                  inbox={}, feedback=feedback, previous=previous, repo_files=[])
            except IntelligenceError as exc:
                print(f"  code round {rnd + 1}: model error {str(exc)[:300]}")
                break
            files = {k: v for k, v in (out.get("files") or {}).items() if isinstance(v, str) and k.endswith(".py")
                     and "/" not in k}
            for p in work.glob("*.py"):
                p.unlink()
            for name, text in files.items():
                (work / name).write_text(text, encoding="utf-8")
            rep = run_unittests(work)
            calls.append(u)
            if not files:  # show exactly what the model wrote, so a format problem is visible, not guessed at
                raw = getattr(src, "last_text", "")
                result.setdefault("unreadable_replies", []).append(raw[:6000])
                print("  the reply had no readable files; it began:\n" + "\n".join("    | " + ln for ln in raw[:1500].splitlines()))
            print(f"  code round {rnd + 1}: {sorted(files)}; {rep['ran']} tests, {len(rep['failed'])} failed; "
                  f"{u['tokens_in']} tokens in, {u['tokens_out']} out, {u['latency_s']:.0f} s{speed(u)}", flush=True)
            if rep["passed"]:
                passed = True
                break
            previous = files
            feedback = ("Your reply contained no files. Every file must be in the === FILE: name === layout."
                        if not files else "Failing tests: " + (", ".join(rep["failed"]) or "none ran") + "\n" + rep["output"][-1500:])
        shutil.rmtree(work, ignore_errors=True)
        ok = complete and passed
        secs = sum(c["latency_s"] for c in calls)
        result.update(passed=ok, objective_complete=complete, code_passed=passed, rounds=len(calls) - 1, seconds=round(secs),
                      tokens_in=sum(c["tokens_in"] for c in calls), tokens_out=sum(c["tokens_out"] for c in calls),
                      read_tps=max((c.get("read_tps") or 0) for c in calls), write_tps=max((c.get("write_tps") or 0) for c in calls))
    except (ModelRuntimeError, IntelligenceError) as exc:
        print(f"  error: {exc}")
        result["error"] = str(exc)[:500]
    finally:
        desk.close()
    out = Path(os.environ["CYNQRA_REPORTS_DIR"]) / f"check_{args.check_model}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(("PASS" if ok else "FAIL") + f": {BY_ID[args.check_model]['name']} on {platform.platform()}. "
          f"Reading {result.get('read_tps', 0)} tokens/s, writing {result.get('write_tps', 0)} tokens/s. {out}")
    return 0 if ok else 1


def speed(u: dict) -> str:
    return f"; reads {u['read_tps']} tokens/s, writes {u['write_tps']} tokens/s" if u.get("write_tps") else ""


def e2e(args) -> int:
    """A whole Cynqra run with a real model, driven through the app's HTTP API exactly as the window drives it."""
    d = Path(args.data) if args.data else data_dir()
    desk = Desktop(d)
    import live_check
    api = lambda path, body=None: http(desk.url + path, body, timeout=4000)  # noqa: E731 - a model call can take long
    t0 = time.time()
    report = {"started_at": datetime.now().astimezone().isoformat(timespec="seconds"), "objective": args.objective,
              "app_version": VERSION, "platform": platform.platform(), "python": platform.python_version(),
              "ram_gb": desk.runtime.ram_gb, "model_id": args.e2e, "decisions": [], "resumes": [],
              "counts_as_measured_result": True, "max_usd": 0.0, "outcome": "FAIL", "reason": "did not finish"}
    seen = 0
    try:
        prepare_model(desk, args.e2e, args.gpu)
        report["model"] = {"kind": "local", "label": BY_ID[args.e2e]["name"], "tokens": "measured", "local": True,
                           "server": "llama.cpp llama-server", "accel": desk.runtime.status["accel"]}
        report["model_ready_s"] = round(time.time() - t0, 1)
        api("/api/company", {"name": args.company, "mode": "live"})
        print("Structuring the objective...", flush=True)
        for attempt in range(3):  # what a founder does when the model errs here: press the button again
            try:
                obj = api("/api/objective/draft", {"messy": args.objective})
                break
            except RuntimeError as exc:
                report["resumes"].append({"at_s": round(time.time() - t0), "notice": f"objective: {exc}"[:400]})
                print(f"  objective failed, trying again: {str(exc)[:300]}", flush=True)
                if attempt == 2:
                    raise
        missing = [k for k, v in obj["structured"].items() if not str(v).strip()]
        if missing:
            api("/api/objective/fields", {"fields": {k: "none stated" for k in missing}})
        print(f"  objective: {obj['structured'].get('product')!r}; inferred {obj['inferred_fields']}", flush=True)
        api("/api/objective/confirm", {})
        report["decisions"].append({"kind": "confirm_objective", "action": "approve"})
        deadline = t0 + args.max_minutes * 60
        while time.time() < deadline:
            st = api("/api/state")
            for ev in st.get("events") or []:
                if ev["seq"] > seen:
                    seen = ev["seq"]
                    if ev["event_type"] in ("task.verified", "verification.completed", "task.blocked", "action.denied",
                                            "decision.created", "deployment.verified", "worker.self_checked", "task.failed"):
                        p = ev.get("payload") or {}
                        extra = p.get("verdict") or p.get("kind") or p.get("passed") or p.get("reason") or ""
                        print(f"  {time.time() - t0:7.0f}s  {ev['event_type']:<24} {ev['aggregate_id']:<22} {str(extra)[:80]}",
                              flush=True)
            phase = st["meta"]["phase"]
            if phase in ("accepted", "stopped"):
                break
            if phase == "stopped_error":
                note = st["meta"].get("notice", "")
                report["resumes"].append({"at_s": round(time.time() - t0), "notice": note[:400]})
                print(f"  stopped on an error: {note[:300]}", flush=True)
                if len(report["resumes"]) > args.max_resumes:
                    break
                api("/api/run/resume", {})
                continue
            pend = [x for x in st["decisions"]["pending"] if not x.get("in_digest")] or st["decisions"]["pending"]
            if pend:
                dd = pend[0]
                edited = {"cap": st["budget"]["cap"] + 300} if dd["kind"] == "budget_breaker" else None
                report["decisions"].append({"id": dd["id"], "kind": dd["kind"], "risk": dd.get("risk"),
                                            "task_id": dd.get("task_id"), "problem": dd.get("problem", "")[:300],
                                            "action": "approve"})
                print(f"  {time.time() - t0:7.0f}s  approving {dd['kind']} {dd.get('task_id') or ''}", flush=True)
                api(f"/api/decisions/{dd['id']}", {"action": "approve", "note": "", "edited": edited})
                if dd["kind"] == "approve_plan":
                    api("/api/run/auto", {"on": True, "delay": 0})
                continue
            if phase == "running" and not st["auto"]["on"]:
                api("/api/run/auto", {"on": True, "delay": 0})
            time.sleep(3)
        api("/api/run/auto", {"on": False})
        e = desk.app.engine
        with e.lock:
            phase = e.meta["phase"]
            calls = e.store.all("call")
            m = e.metrics() if e.store.get("company", e.cid) else {}
            if phase == "accepted":
                health = live_check.health(e.live_url())
                tests = live_check.rerun_product_tests(e.paths["main"])
                report.update(health=health, product_tests=tests)
                ok = health.get("status") == 200 and tests["passed"]
                outcome, reason = ("PASS", "accepted, live, healthy, and the product's tests pass on rerun") if ok else \
                    ("FAIL", "accepted, but the independent checks failed")
            elif time.time() >= deadline:
                outcome, reason = "FAIL", f"not finished after {args.max_minutes} minutes (phase {phase})"
            else:
                outcome, reason = "FAIL", e.meta.get("notice") or f"ended in phase {phase}"
            report.update(
                outcome=outcome, reason=reason, seconds=round(time.time() - t0, 1), phase=phase, usd=0.0,
                tokens_in=sum(c.get("tokens_in", 0) for c in calls), tokens_out=sum(c.get("tokens_out", 0) for c in calls),
                metrics=m, live_url=e.live_url(),
                calls=[{k: c.get(k) for k in ("id", "task_id", "worker", "purpose", "label", "tokens_in", "tokens_out",
                                              "estimated", "latency_s", "read_tps", "write_tps")} for c in calls],
                plan=[{k: t.get(k) for k in ("id", "kind", "owner_worker_id", "title", "status", "attempts")}
                      for t in e.tasks()] if e.store.get("plan", "plan_1") else [],
                verifications=[{k: v.get(k) for k in ("id", "task_id", "verdict", "tier")}
                               for v in e.store.all("verification")])
            product = Path(os.environ["CYNQRA_REPORTS_DIR"]) / f"product_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            if e.paths["main"].exists():
                shutil.copytree(e.paths["main"], product, ignore=shutil.ignore_patterns("__pycache__"))
                report["product_copy"] = str(product)
    except Exception as exc:  # noqa: BLE001 - a test harness: every failure goes into the report
        report.update(outcome="FAIL", reason=f"{type(exc).__name__}: {exc}"[:1000], seconds=round(time.time() - t0, 1))
    finally:
        path = live_check.write(report)
        desk.close()
    calls = report.get("calls") or []
    print(f"\n{report['outcome']}: {report['reason']}\n{len(calls)} model calls, {report.get('tokens_in', 0)} tokens in, "
          f"{report.get('tokens_out', 0)} out, {report.get('seconds', 0) / 60:.1f} min. Report: {path}", flush=True)
    return 0 if report["outcome"] == "PASS" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Cynqra desktop app")
    ap.add_argument("--headless", action="store_true", help="no window; serve on 127.0.0.1")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--log-file", action="store_true", help="write output to app.log in the data folder")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--online", action="store_true", help="with --selftest: also check the model files on Hugging Face")
    ap.add_argument("--window-test", action="store_true")
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--check-model", choices=sorted(BY_ID))
    ap.add_argument("--e2e", choices=sorted(BY_ID))
    ap.add_argument("objective", nargs="?", default="")
    ap.add_argument("--company", default="Cynqra end-to-end")
    ap.add_argument("--gpu", choices=("auto", "on", "off"))
    ap.add_argument("--data", help="data folder for --check-model and --e2e (default: the app's own)")
    ap.add_argument("--max-resumes", type=int, default=3)
    ap.add_argument("--max-minutes", type=float, default=330)
    ap.add_argument("--version", action="version", version=f"Cynqra {VERSION}")
    args = ap.parse_args()
    if args.selftest:
        return selftest(args)
    if args.window_test:
        return window_test(args)
    if args.check_model:
        return check_model(args)
    if args.e2e:
        if not args.objective:
            ap.error("--e2e needs an objective")
        return e2e(args)
    return run_app(args)


if __name__ == "__main__":
    sys.exit(main())
