"""Verification that reruns prior tests and lints specs against decided rules.

Kit only. Not M2. Not a second model.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

STUCK_CLOCK = re.compile(
    r"stuck.{0,80}(7\s*day|elapsed|no stage change|clock)",
    re.I | re.S,
)
NAMED_REASON = re.compile(
    r"named reason|waiting_on_recruiter|waiting_on_candidate|waiting_on_founder",
    re.I,
)


def run_tests(test_file: Path, cwd: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(test_file)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    failed = []
    for line in out.splitlines():
        if line.startswith("FAIL:") or line.startswith("ERROR:"):
            parts = line.split()
            if len(parts) >= 2:
                failed.append(parts[1].split(".")[-1])
    return {
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
        "failed_tests": failed,
        "output": out[-4000:],
    }


def lint_specs(paths: list[Path]) -> list[dict]:
    hits = []
    for p in paths:
        if not p.exists() or p.suffix not in {".md", ".txt", ".json"}:
            continue
        text = p.read_text(encoding="utf-8")
        if "stuck" not in text.lower():
            continue
        if STUCK_CLOCK.search(text) and not NAMED_REASON.search(text):
            hits.append(
                {
                    "file": str(p),
                    "rule": "decision_001",
                    "what": "spec treats stuck as a clock without a named reason",
                }
            )
    return hits


def verify_submission(submission: Path, held_tests: list[Path], work: Path) -> dict:
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    store = submission / "store.py"
    if store.exists():
        shutil.copy2(store, work / "store.py")
    test_results = []
    for t in held_tests:
        dest = work / t.name
        # Avoid colliding names when more than one test_store.py exists.
        dest = work / (t.parent.name + "_" + t.name)
        shutil.copy2(t, dest)
        test_results.append({"held": str(t), **run_tests(dest, work)})
    specs = list(submission.glob("*.md")) + list(submission.glob("*.txt"))
    lint = lint_specs(specs)
    tests_ok = all(r["passed"] for r in test_results) if test_results else False
    return {
        "tests_ok": tests_ok,
        "tests": test_results,
        "spec_violations": lint,
        "verdict": "VERIFIED" if tests_ok and not lint else "FAILED",
    }
