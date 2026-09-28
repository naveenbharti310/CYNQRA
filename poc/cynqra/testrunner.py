"""Running a repository's unittest tests in a clean process, as the workers' own checks, the Verification
Service, the merge and the release pipeline all do. The verdicts are the Verification Service's (verifier.py).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# unittest -v writes "name (module.Class.name) ... ok". The result can come lines later: after a docstring, or after
# whatever the code under test printed meanwhile (http.server logs every request to stderr, mid-line).
START = re.compile(r"^(\w+) \((\w+\.[\w.]+)\)")
RESULT = re.compile(r"(?:^|\.\.\. )(ok|FAIL|ERROR|skipped.*|expected failure|unexpected success)$")
SUMMARY = re.compile(r"^(FAIL|ERROR): (\w+) \((\w+[\w.]*)\)")  # the failure details printed after the run
NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW: tests and apps open no console on Windows


def python_exe() -> str:
    """The interpreter for workers' tests and deployed apps. The Windows desktop app runs under
    pythonw.exe, which has no console; its children use the python.exe beside it, with no window."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and (exe.parent / "python.exe").exists():
        return str(exe.parent / "python.exe")
    return sys.executable


def clean_env(extra: dict | None = None) -> dict:
    """Workers and tests get a minimal environment: no keys, no tokens, no home."""
    keep = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC") if k in os.environ}
    keep["PYTHONDONTWRITEBYTECODE"] = "1"
    keep["PYTHONIOENCODING"] = "utf-8"
    keep["PYTHONUTF8"] = "1"
    keep.update(extra or {})
    return keep


def _text(data) -> str:
    return data.decode("utf-8", "replace") if isinstance(data, bytes) else (data or "")


def run_unittests(folder: Path, timeout: int = 120) -> dict:
    """Run every test_*.py in folder. Returns pass/fail, test ids and their status, and, when the run
    itself went wrong (it hung, or the process died), a problem that says so and names the test."""
    folder = Path(folder).resolve()  # unittest is started inside the folder: a relative path would not resolve
    if not any(folder.glob("test_*.py")):
        return {"ran": 0, "passed": False, "tests": [], "failed": [], "output": "no test files", "returncode": None,
                "problem": ""}
    timed_out = False
    try:
        proc = subprocess.run(
            [python_exe(), "-m", "unittest", "discover", "-s", str(folder), "-p", "test_*.py", "-v"],
            cwd=str(folder), capture_output=True, encoding="utf-8", errors="replace", timeout=timeout, env=clean_env(),
            creationflags=NO_WINDOW,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        out = _text(exc.stdout) + _text(exc.stderr) + f"\n[stopped: the tests did not finish within {timeout} s]"
        code, timed_out = -1, True
    tests, failed = [], []
    pending = None
    for raw in out.splitlines():
        line = raw.strip()
        m = START.match(line)
        if m:
            pending = m.groups()
        r = RESULT.search(line) if pending else None
        if r:
            (name, owner), status = pending, r.group(1)
            pending = None
            tests.append({"id": f"{owner.split('.')[0]}.{name}", "status": "ok" if status == "ok" else status.split()[0]})
            continue
        s = SUMMARY.match(line)
        if s:
            failed.append(f"{s.group(3).split('.')[0]}.{s.group(2)}")
    failed = list(dict.fromkeys([t["id"] for t in tests if t["status"] in ("FAIL", "ERROR")] + failed))
    ran_match = re.search(r"^Ran (\d+) tests?", out, re.M)
    ran = int(ran_match.group(1)) if ran_match else len(tests)
    running = f"{pending[1].split('.')[0]}.{pending[0]}" if pending else ""
    problem = ""
    if timed_out:
        problem = (f"The tests did not finish within {timeout} s and were stopped"
                   + (f" while {running} was running" if running else "") + ". Something in them waits forever: "
                   "usually a server that is never shut down or whose serve_forever() is not in a daemon thread, a "
                   "request without a timeout, or code that waits for input. Start test servers on port 0 in a daemon "
                   "thread, give every request a timeout of a few seconds, and shut servers down in tearDown.")
    elif not ran_match and code not in (0, None):
        problem = ("The test process ended" + (f" during {running}" if running else "") + f" (exit code {code}) before "
                   "unittest could report: the code under test ended the process (os._exit, or sys.exit outside a "
                   "test) or crashed.")
    return {"ran": ran, "passed": code == 0 and ran > 0, "tests": tests, "failed": failed,
            "output": out[-3000:], "returncode": code, "problem": problem}


def failure_summary(report: dict) -> str:
    """Why a test run failed, in one sentence for the worker who has to fix it."""
    if report.get("problem"):
        return report["problem"]
    if report["failed"]:
        return "Failing tests: " + ", ".join(report["failed"]) + "."
    if report["output"] == "no test files":
        return "There is no test_*.py at the repository root."
    if not report["ran"]:
        return "unittest found no tests: write unittest.TestCase classes with test_ methods in test_*.py files."
    return "The tests failed without naming a failing test; the output is below."
