"""Verification Service helpers: run tests, lint documents against the objective.

Book 0 section 13 tiers: LOW gets automated checks, MEDIUM gets independent review, HIGH
gets the founder. Verification is a platform service, not a fifth worker.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

LINE = re.compile(r"^(\w+) \(([\w.]+)\) \.\.\. (ok|FAIL|ERROR|skipped.*|expected failure|unexpected success)$")
HEAD = re.compile(r"^(\w+) \(([\w.]+)\)$")  # verbose output puts a docstring on the next line
TAIL = re.compile(r" \.\.\. (ok|FAIL|ERROR|skipped.*|expected failure|unexpected success)$")
VERDICTS = ("VERIFIED", "REJECTED", "REQUIRES_REWORK", "REQUIRES_HUMAN", "INCONCLUSIVE")


def clean_env(extra: dict | None = None) -> dict:
    """Workers and tests get a minimal environment: no keys, no tokens, no home."""
    keep = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC") if k in os.environ}
    keep["PYTHONDONTWRITEBYTECODE"] = "1"
    keep["PYTHONIOENCODING"] = "utf-8"
    keep.update(extra or {})
    return keep


def run_unittests(folder: Path, timeout: int = 120) -> dict:
    """Run every test_*.py in folder. Returns pass/fail, test ids and their status."""
    folder = Path(folder)
    if not any(folder.glob("test_*.py")):
        return {"ran": 0, "passed": False, "tests": [], "failed": [], "output": "no test files", "returncode": None}
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", str(folder), "-p", "test_*.py", "-v"],
            cwd=str(folder), capture_output=True, text=True, timeout=timeout, env=clean_env(),
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        out = f"timed out after {timeout}s\n" + str(exc.stdout or "")
        code = -1
    tests = []
    pending = None
    for raw in out.splitlines():
        line = raw.strip()
        m = LINE.match(line)
        if m:
            name, owner, status = m.groups()
        elif HEAD.match(line):
            pending = HEAD.match(line).groups()
            continue
        elif pending and TAIL.search(line):
            (name, owner), status = pending, TAIL.search(line).group(1)
        else:
            continue
        pending = None
        module = owner.split(".")[0]
        tests.append({"id": f"{module}.{name}", "status": "ok" if status == "ok" else status.split()[0]})
    failed = [t["id"] for t in tests if t["status"] in ("FAIL", "ERROR")]
    ran_match = re.search(r"Ran (\d+) tests?", out)
    ran = int(ran_match.group(1)) if ran_match else len(tests)
    return {"ran": ran, "passed": code == 0 and ran > 0, "tests": tests, "failed": failed,
            "output": out[-3000:], "returncode": code}


_STOP = {"a", "an", "the", "and", "or", "of", "to", "no", "not", "for", "in", "on", "with", "can", "set",
         "one", "is", "are", "be", "who", "all", "only", "ones", "their", "them", "it", "its", "that"}


def _terms(text: str) -> set[str]:
    words = re.findall(r"[a-z]+", (text or "").lower())
    return {w for w in words if len(w) > 3 and w not in _STOP}


def lint_documents(files: dict[str, str], objective: dict) -> dict:
    """Coverage lint derived from the confirmed objective, for any objective.

    1. Every constraint must be echoed: its key words appear in the documents, so the
       spec states what is out of scope instead of silently dropping it.
    2. The success criteria must be covered: at least two thirds of its key words appear.
    3. Documents must not be empty.
    This is a floor, not a review. MEDIUM work also gets an independent review.
    """
    text = "\n".join(files.values()).lower()
    findings = []
    if not text.strip():
        findings.append({"rule": "not_empty", "why": "no document content"})
    for part in re.split(r"[;,]|\band\b", objective.get("constraints", "") or ""):
        terms = _terms(part)
        if terms and not any(t in text for t in terms):
            findings.append({"rule": "constraint_echoed", "why": f"constraint not addressed: {part.strip()}"})
    crit = _terms(objective.get("success_criteria", ""))
    if crit:
        covered = {t for t in crit if t in text}
        if len(covered) < max(1, round(len(crit) * 2 / 3)):
            findings.append({"rule": "success_covered",
                             "why": f"success criteria not covered: {sorted(crit - covered)}"})
    return {"passed": not findings, "findings": findings}
