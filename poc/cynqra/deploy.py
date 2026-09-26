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
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .verification import clean_env, run_unittests

STAGES = ["BUILD", "TEST", "PACKAGE", "PREVIEW", "VERIFY", "APPROVAL", "DEPLOY", "HEALTH_CHECK", "SMOKE_TEST", "LIVE"]
_PROCS: list[subprocess.Popen] = []


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start(folder: Path, port: int, data_file: Path) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "app.py"], cwd=str(folder),
        env=clean_env({"PORT": str(port), "DATA_FILE": str(data_file)}),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    _PROCS.append(proc)
    return proc


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


def health(base: str, wait: float = 10.0) -> dict:
    deadline = time.time() + wait
    last = "no answer"
    while time.time() < deadline:
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
    proc = start(folder, port, folder / "preview_data.json")
    base = f"http://127.0.0.1:{port}"
    h = health(base)
    log.append({"stage": "PREVIEW", "ok": h["ok"], "note": base})
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
    proc = start(Path(folder), port, data_dir / "candidates.json")
    base = f"http://127.0.0.1:{port}"
    log.append({"stage": "DEPLOY", "ok": True, "note": base})
    h = health(base)
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
