"""Deployment service: the lifecycle fixed by the Book 2 addendum and D-24.

BUILD, TEST, PACKAGE, PREVIEW, VERIFY, APPROVAL, DEPLOY, HEALTH CHECK, SMOKE TEST, LIVE.
Failure after DEPLOY rolls back: the new process is stopped and the previous live
release, if any, keeps serving. In the POC a deployment is a local process on 127.0.0.1.
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .testrunner import NO_WINDOW, clean_env, python_exe, run_unittests

STAGES = ["BUILD", "TEST", "PACKAGE", "PREVIEW", "VERIFY", "APPROVAL", "DEPLOY", "HEALTH_CHECK", "SMOKE_TEST", "LIVE"]
_PROCS: list[subprocess.Popen] = []


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start(folder: Path, port: int, data_file: Path, log_file: Path | None = None) -> subprocess.Popen:
    """Start app.py. Its output goes to log_file so a crash can be shown, not guessed at."""
    log = open(log_file, "wb") if log_file else subprocess.DEVNULL
    try:
        proc = subprocess.Popen(
            [python_exe(), "app.py"], cwd=str(folder),
            env=clean_env({"PORT": str(port), "DATA_FILE": str(data_file)}),
            stdout=log, stderr=subprocess.STDOUT if log_file else subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            creationflags=NO_WINDOW,
        )
    finally:
        if log_file:
            log.close()
    _PROCS.append(proc)
    return proc


def tail(log_file: Path, n: int = 1200) -> str:
    try:
        return log_file.read_text(encoding="utf-8", errors="replace")[-n:].strip()
    except OSError:
        return ""


def stop(proc: subprocess.Popen | None) -> None:
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def stop_all() -> None:
    for p in list(_PROCS):
        stop(p)
    _PROCS.clear()


def _get(url: str, timeout: float = 2.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read()


def _post(url: str, body: dict, timeout: float = 3.0):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read() or b"null")


def health(base: str, wait: float = 10.0, proc: subprocess.Popen | None = None) -> dict:
    deadline = time.time() + wait
    last = "no answer"
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            return {"ok": False, "error": f"app.py exited with code {proc.returncode}"}
        try:
            t0 = time.time()
            code, _ = _get(base + "/health")
            if code == 200:
                return {"ok": True, "status": 200, "ms": round((time.time() - t0) * 1000, 1)}
            last = f"status {code}"
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            last = str(exc)
        time.sleep(0.15)
    return {"ok": False, "error": last}


def smoke(base: str, checks: list[dict] | None = None) -> dict:
    """Generic smoke: the screen loads and health answers. A product may add JSON API checks.

    Each extra check: {"method": "GET"|"POST", "path": "...", "body": {...}, "expect": 200}
    """
    results = []
    try:
        code, body = _get(base + "/")
        results.append({"check": "GET /", "ok": code == 200 and len(body) > 0})
        for c in checks or []:
            if not isinstance(c, dict) or not isinstance(c.get("path"), str):
                continue
            try:
                if c.get("method") == "POST":
                    status, _ = _post(base + c["path"], c.get("body") or {})
                else:
                    status, _ = _get(base + c["path"])
            except urllib.error.HTTPError as exc:
                status = exc.code
            results.append({"check": f"{c.get('method', 'GET')} {c['path']}", "ok": status == c.get("expect", 200)})
    except (urllib.error.URLError, OSError) as exc:
        results.append({"check": "reachable", "ok": False, "error": str(exc)})
    return {"ok": bool(results) and all(r["ok"] for r in results), "results": results}


def contract_check(folder: Path, smoke_checks: list[dict]) -> dict:
    """The delivery contract, checked while a code task is verified: app.py starts on PORT,
    GET /health and GET / answer 200. Runs in a copy so nothing leaks into the repository."""
    work = Path(folder).parent / (Path(folder).name + "_contract")
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(folder, work)
    port = free_port()
    log_file = work.parent / (work.name + ".log")
    proc = start(work, port, work / "contract_data.json", log_file)
    base = f"http://127.0.0.1:{port}"
    try:
        h = health(base, proc=proc)
        if not h["ok"]:
            return {"ok": False, "results": [{"check": "GET /health", "ok": False}],
                    "why": f"GET /health did not answer 200 ({h['error']}). app.py output: {tail(log_file) or 'none'}"}
        s = smoke(base, [c for c in smoke_checks if c.get("method", "GET") == "GET"])
        bad = [r["check"] for r in s["results"] if not r["ok"]]
        return {"ok": s["ok"], "results": [{"check": "GET /health", "ok": True}] + s["results"],
                "why": f"these checks failed: {', '.join(bad)}" if bad else ""}
    finally:
        stop(proc)
        shutil.rmtree(work, ignore_errors=True)


def build_to_verify(main: Path, releases: Path, release_id: str, smoke_checks: list[dict]) -> dict:
    """BUILD to VERIFY, run before the founder is asked. Returns the stage log and a preview report."""
    log = []
    folder = releases / release_id
    if folder.exists():
        shutil.rmtree(folder)
    shutil.copytree(main, folder)
    ok = (folder / "app.py").exists()
    log.append({"stage": "BUILD", "ok": ok, "note": "copied main" if ok else "app.py missing, delivery contract broken"})
    if not ok:
        return {"ok": False, "log": log, "folder": str(folder)}
    tests = run_unittests(folder)
    log.append({"stage": "TEST", "ok": tests["passed"], "note": f"{tests['ran']} tests", "test_ids": [t["id"] for t in tests["tests"]]})
    if not tests["passed"]:
        return {"ok": False, "log": log, "folder": str(folder)}
    package = releases / f"{release_id}.zip"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(folder.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith(".json"):
                z.write(p, p.relative_to(folder))
    log.append({"stage": "PACKAGE", "ok": True, "note": package.name})
    port = free_port()
    log_file = releases / f"{release_id}_preview.log"
    proc = start(folder, port, folder / "preview_data.json", log_file)
    base = f"http://127.0.0.1:{port}"
    h = health(base, proc=proc)
    log.append({"stage": "PREVIEW", "ok": h["ok"], "note": base if h["ok"] else f"{h['error']}: {tail(log_file, 400)}"})
    s = smoke(base, smoke_checks) if h["ok"] else {"ok": False, "results": []}
    log.append({"stage": "VERIFY", "ok": s["ok"], "note": "preview smoke", "results": s["results"]})
    stop(proc)
    return {"ok": h["ok"] and s["ok"], "log": log, "folder": str(folder), "package": str(package),
            "test_ids": [t["id"] for t in tests["tests"]]}


def deploy_live(folder: Path, data_dir: Path, smoke_checks: list[dict], previous: subprocess.Popen | None) -> dict:
    """DEPLOY to LIVE, run only after the founder approved. Rolls back on failure."""
    log = [{"stage": "APPROVAL", "ok": True, "note": "founder approved (D-21)"}]
    port = free_port()
    data_dir.mkdir(parents=True, exist_ok=True)
    proc = start(Path(folder), port, data_dir / "data.json", data_dir / "app.log")
    base = f"http://127.0.0.1:{port}"
    log.append({"stage": "DEPLOY", "ok": True, "note": base})
    h = health(base, proc=proc)
    log.append({"stage": "HEALTH_CHECK", "ok": h["ok"], "note": f"{h.get('status', '')} in {h.get('ms', '?')} ms" if h["ok"] else h.get("error")})
    live_checks = [c for c in smoke_checks if c.get("method", "GET") == "GET"]
    s = smoke(base, live_checks) if h["ok"] else {"ok": False, "results": []}
    log.append({"stage": "SMOKE_TEST", "ok": s["ok"], "results": s["results"], "note": "GET checks only on live"})
    if h["ok"] and s["ok"]:
        stop(previous)
        log.append({"stage": "LIVE", "ok": True, "note": base})
        return {"ok": True, "log": log, "url": base, "proc": proc}
    stop(proc)
    log.append({"stage": "ROLLBACK", "ok": True, "note": "new release stopped; previous release keeps serving"})
    return {"ok": False, "log": log, "url": None, "proc": previous}
