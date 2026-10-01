"""The Verification Service (Stage 9): the difference between "the worker says it is done" and "it is done".

Every task type in the catalog names its verifier; the worker never chooses how its work is judged:

  document   each document type's rules (its sections, or its numbered checks), the requirement ids the task
             covers cited in the text, and for briefs and specifications the objective's constraints and success
             criteria (lint_documents)
  tests      every test in the repository rerun in a clean copy with the task's files merged in, and the delivery
             contract when the task delivers the app
  backtest   the tests, then the platform's own backtest of forecast(history, horizon) on held-out days of a
             platform-owned series: no worse than the seasonal baseline (the same weekday a week before)
  founder, merge, release   recorded by execution when the founder's approval is carried out

It records what the product definition asks for: first-pass success, rework, defect escape (a defect found after
verification, in the release candidate, on main or live, counted against the task and model it came from), false
rejection (the same work failing, then passing), and verification latency and cost.
"""
from __future__ import annotations

import json
import random
import re
import shutil
import subprocess
import time
from datetime import date, timedelta
from pathlib import Path

from . import budget, deploy, numbers, roles
from .db import digest, now
from .testrunner import NO_WINDOW, clean_env, failure_summary, python_exe, run_unittests

MAX_ATTEMPTS = 3
HOLDOUT = 14


# --- the verifiers -----------------------------------------------------------------------------------------------
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


def check_documents(files: dict[str, str], task: dict, objective: dict) -> dict:
    findings = []
    md = {k: v for k, v in files.items() if k.endswith(".md")}
    if not md:
        findings.append({"rule": "documents", "why": "no Markdown document was delivered"})
    for doc_type in task.get("documents") or []:
        rules = roles.DOC_TYPES[doc_type]
        best = None
        for name, text in md.items():
            miss = [s for s in rules.get("sections", [])
                    if not re.search(rf"^#+\s*{re.escape(s)}\b", text, re.M | re.I)]
            if rules.get("numbered") and len(re.findall(r"^\s*\d+[.)]\s+\S", text, re.M)) < rules["numbered"]:
                miss.append(f"at least {rules['numbered']} numbered checks")
            if best is None or len(miss) < len(best[1]):
                best = (name, miss)
        if best and best[1]:
            findings.append({"rule": f"{doc_type}_sections",
                             "why": f"{rules['title']}: missing {', '.join(best[1])}"})
    text = "\n".join(md.values())
    computed = None
    for doc_type in task.get("documents") or []:
        rules = roles.DOC_TYPES[doc_type]
        if rules.get("trust") and "assumption" not in text.lower():
            findings.append({"rule": f"{doc_type}_assumptions",
                             "why": f"{rules['title']}: no estimate is marked as an assumption; mark every figure "
                                    "that is not sourced"})
        if "Sources" in rules.get("sections", []):
            m = re.search(r"^#+\s*Sources\b[^\n]*\n(.*?)(?=^#|\Z)", text, re.M | re.S | re.I)
            if m and not re.search(r"^\s*(?:[*-]|\d+[.)])\s+\S", m.group(1), re.M):
                findings.append({"rule": f"{doc_type}_sources",
                                 "why": f"{rules['title']}: the Sources section lists no source"})
        if rules.get("numbers"):
            r = numbers.check(text)
            findings += r["findings"]
            computed = {k: r.get(k) for k in ("computed", "inputs", "currency")}
    missing_ids = [r for r in task.get("requirement_ids") or [] if r not in text]
    if missing_ids:
        findings.append({"rule": "requirements_cited", "why": f"requirements not cited: {', '.join(missing_ids)}"})
    if any(roles.DOC_TYPES[d].get("objective") for d in task.get("documents") or []):
        findings += lint_documents(md, objective)["findings"]
    return {"passed": not findings, "findings": findings, "numbers": computed}


def series(days: int = 16 * 7, start: date = date(2026, 1, 5)) -> list[dict]:
    """The platform's own daily covers: weekly seasonality, a slow trend and noise, the same every time."""
    rng = random.Random(7)
    week = [0.80, 0.85, 0.90, 1.00, 1.35, 1.55, 1.20]
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        value = 120 * week[d.weekday()] * (1 + 0.002 * i) + rng.gauss(0, 6)
        out.append({"date": d.isoformat(), "covers": max(0, round(value))})
    return out


def seasonal_baseline(history: list[dict], horizon: int) -> list[float]:
    ys = [h["covers"] for h in history]
    return [float(ys[len(ys) - 7 + (h % 7)]) for h in range(horizon)]


RUNNER = ("import json, sys\n"
          "sys.path.insert(0, sys.argv[1])\n"
          "from forecast import forecast\n"
          "data = json.load(sys.stdin)\n"
          "print(json.dumps([float(x) for x in forecast(data['history'], data['horizon'])]))\n")


def backtest(folder: Path, timeout: int = 60) -> dict:
    """Run the candidate's forecast on the held-out days in its own process and compare it with the baseline."""
    data = series()
    history, truth = data[:-HOLDOUT], [d["covers"] for d in data[-HOLDOUT:]]
    base = seasonal_baseline(history, HOLDOUT)
    mae = lambda p: round(sum(abs(a - b) for a, b in zip(p, truth)) / HOLDOUT, 2)  # noqa: E731
    out = {"holdout_days": HOLDOUT, "baseline": "same weekday a week before", "baseline_mae": mae(base)}
    if not (folder / "forecast.py").exists():
        return {**out, "passed": False, "why": "forecast.py is missing at the repository root"}
    try:
        proc = subprocess.run([python_exe(), "-c", RUNNER, str(folder)], input=json.dumps({"history": history,
                              "horizon": HOLDOUT}), capture_output=True, text=True, timeout=timeout, env=clean_env(),
                              cwd=str(folder), creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        return {**out, "passed": False, "why": f"forecast() did not return within {timeout} s"}
    try:
        pred = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {**out, "passed": False, "why": "forecast() failed: " + (proc.stderr or proc.stdout)[-600:]}
    if not isinstance(pred, list) or len(pred) != HOLDOUT or any(not isinstance(x, (int, float)) or x < 0 for x in pred):
        return {**out, "passed": False, "why": f"forecast() must return {HOLDOUT} non-negative numbers"}
    out["model_mae"] = mae(pred)
    out["passed"] = out["model_mae"] <= out["baseline_mae"]
    if not out["passed"]:
        out["why"] = (f"the backtest's mean absolute error is {out['model_mae']} covers a day, worse than the baseline's "
                      f"{out['baseline_mae']} (the same weekday a week before)")
    return out


def smoke_checks(folder: Path) -> list[dict]:
    f = folder / "smoke.json"
    if f.exists():
        try:
            checks = json.loads(f.read_text(encoding="utf-8")).get("checks", [])
        except (ValueError, AttributeError):
            return []
        return [c for c in checks if isinstance(c, dict) and isinstance(c.get("path"), str)
                and c["path"].startswith("/")] if isinstance(checks, list) else []
    return [{"method": "GET", "path": "/health", "expect": 200}]


def run_checks(kind: str, candidate: Path, out: Path, task: dict, objective: dict) -> dict:
    """The verifier of a file-delivering task type, on its work merged into a clean copy of the repository."""
    if kind == "document":
        docs = {p.name: p.read_text(encoding="utf-8", errors="replace") for p in out.rglob("*") if p.is_file()}
        r = check_documents(docs, task, objective)
        return {"passed": r["passed"], "test_ids": [], "checks": {"documents": r["findings"],
                "acceptance_criteria": task.get("acceptance_criteria") or [],
                **({"numbers": r["numbers"]} if r.get("numbers") else {})},
                "feedback": "; ".join(f["why"] for f in r["findings"]), "method": "document verifier"}
    report = run_unittests(candidate)
    checks = {"ran": report["ran"], "failed": report["failed"], "prior_tests_rerun": True}
    passed, feedback = report["passed"], "" if report["passed"] else failure_summary(report) + "\n" + report["output"][-1500:]
    method = "automated tests, prior tests rerun"
    if passed and kind == "forecast":
        bt = backtest(candidate)
        checks["backtest"] = bt
        passed, method = bt["passed"], method + ", backtest against the seasonal baseline"
        feedback = "" if passed else "The platform's backtest failed: " + bt["why"]
    if passed and (out / "app.py").exists():
        contract = deploy.contract_check(candidate, smoke_checks(candidate))
        checks["delivery_contract"] = contract["results"]
        method += ", delivery contract"
        if not contract["ok"]:
            passed, feedback = False, "The app breaks the delivery contract: " + contract["why"]
    return {"passed": passed, "test_ids": [x["id"] for x in report["tests"]], "checks": checks, "feedback": feedback,
            "method": method}


# --- the service ---------------------------------------------------------------------------------------------------
def repo_path(rel: Path) -> Path:
    """Markdown is filed under docs/, everything else keeps its path from the repository root."""
    return Path("docs") / rel if rel.suffix == ".md" and rel.parts[0] != "docs" else rel


def candidate(run, t: dict, dest: Path) -> Path:
    """The repository as it would be with this task's files merged in."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(run.paths["integration"], dest)
    out = run.workspace(t["owner_worker_id"], t["id"]) / "out"
    for p in out.rglob("*"):
        if p.is_file():
            target = dest / repo_path(p.relative_to(out))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
    return dest


def record(run, t: dict, *, verdict: str, method: str, checks: dict, test_ids: list, reviewer: str,
           seconds: float | None, work_hash: str | None = None) -> dict:
    n = run.count("verification") + 1
    v = {"id": f"v_{n:03d}", "company_id": run.cid, "task_id": t["id"], "attempt": t["attempts"] + 1,
         "risk_tier": t["risk_tier"], "method": method, "checks": checks,
         "reviewer_type": "human" if reviewer == "founder" else "service", "reviewer_id": reviewer, "verdict": verdict,
         "test_ids": test_ids, "output_hash": digest(json.dumps(checks, sort_keys=True, default=str)),
         "work_hash": work_hash, "worker_id": t["owner_worker_id"], "model_id": run.model_of(t["owner_worker_id"]),
         "seconds": seconds, "created_at": now()}
    run.store.put("verification", v["id"], v)
    run.event("verification.completed", "verification", v["id"], {"task_id": t["id"], "verdict": verdict,
              "method": method, "attempt": v["attempt"]}, actor="verification", correlation_id=t["id"], test_ids=test_ids)
    return v


def outcome(run, t: dict, verified: bool, failure: str = "") -> None:
    """One verification of one attempt: counted in the registry for the model that did it, on its kind of work."""
    wid = t["owner_worker_id"]
    meter = run.store.get("meter", t["id"]) or {"usd": 0.0, "seconds": 0.0, "tokens": 0}
    work_calls = [x for x in run.store.all("call")
                   if x.get("task_id") == t["id"] and x.get("worker") == wid and x.get("purpose") == "work"]
    last_call = work_calls[-1] if work_calls else {}
    run.registry.record_outcome(
        run.model_of(wid), role=run.worker(wid)["role"], task_kind=t["kind"], task_id=t["id"],
        run_id=run.cid, attempt=t["attempts"] + 1, verified=verified, usd=meter["usd"],
        seconds=meter["seconds"], tokens=meter["tokens"], failure=failure,
        execution_profile_id=last_call.get("execution_profile_id"),
        binding_epoch_id=last_call.get("binding_epoch_id"))
    run.store.put("meter", t["id"], {"usd": 0.0, "seconds": 0.0, "tokens": 0})


def integrate(run, t: dict) -> None:
    out = run.workspace(t["owner_worker_id"], t["id"]) / "out"
    root = run.paths["integration"]
    for p in sorted(out.rglob("*")):
        if not p.is_file():
            continue
        rel = repo_path(p.relative_to(out))
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, root / rel)
        aid = f"{t['id']}/{p.relative_to(out).as_posix()}"
        run.store.put("artifact", aid, {"id": aid, "task_id": t["id"], "path": rel.as_posix(),
                                        "hash": digest(p.read_bytes()), "by": t["owner_worker_id"]})
    run.event("action.executed", "action", f"integrate_{t['id']}", {"task_id": t["id"], "action_type": "integrate",
              "files": sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())},
              actor="verification", correlation_id=t["id"])


def verify(run, t: dict) -> dict:
    """Verify a file-delivering task. Returns {passed, verdict, feedback, verification}."""
    owner = t["owner_worker_id"]
    t0 = time.time()
    out = run.workspace(owner, t["id"]) / "out"
    cand = candidate(run, t, run.paths["verify"] / f"{t['id']}_{t['attempts'] + 1}")
    r = run_checks(t["kind"], cand, out, t, run.objective()["structured"])
    seconds = round(time.time() - t0, 2)
    run.spend("verification", t["id"], budget.machine_usd(run.store, seconds), "verification")
    verdict = "VERIFIED" if r["passed"] else ("REQUIRES_REWORK" if t["attempts"] + 1 < MAX_ATTEMPTS else "REQUIRES_HUMAN")
    work = digest({p.relative_to(out).as_posix(): digest(p.read_bytes()) for p in sorted(out.rglob("*")) if p.is_file()})
    outcome(run, t, r["passed"], r["feedback"])
    v = record(run, t, verdict=verdict, method=r["method"], checks=r["checks"], test_ids=r["test_ids"],
               reviewer="verification", seconds=seconds, work_hash=work)
    if r["passed"]:  # the same work failed before and passes now: that earlier verdict was a false rejection
        for old in run.store.all("verification"):
            if old["task_id"] == t["id"] and old["id"] != v["id"] and old.get("work_hash") == work \
                    and old["verdict"] != "VERIFIED" and not old.get("false_rejection"):
                old["false_rejection"] = True
                run.store.put("verification", old["id"], old)
                run.event("verification.false_rejection", "verification", old["id"], {"task_id": t["id"],
                          "confirmed_by": v["id"]}, actor="verification", correlation_id=t["id"])
    return {"passed": r["passed"], "verdict": verdict, "feedback": r["feedback"], "verification": v}


def escaped(run, failed_ids: list[str], where: str, found_by: str) -> None:
    """A defect found after verification escaped it. It is counted against the verified build task that owns the
    failing tests (the one that delivered the app when nothing names a test), and the model that did it."""
    mods = {i.split(".")[0] for i in failed_ids or []}
    for x in run.tasks():
        files = {Path(o.get("file", "")).stem for o in x.get("outputs") or [] if isinstance(o, dict)}
        if x["status"] != "VERIFIED" or x["kind"] not in roles.BUILD_TYPES or not (files & mods or (not mods and "app" in files)):
            continue
        v = [y for y in run.store.all("verification") if y["task_id"] == x["id"] and y["verdict"] == "VERIFIED"]
        n = run.count("escape") + 1
        rec = {"id": f"esc_{n:03d}", "task_id": x["id"], "worker_id": x["owner_worker_id"],
               "model_id": v[-1].get("model_id") if v else None, "where": where, "found_by": found_by,
               "tests": sorted(failed_ids or [])[:20], "at": now()}
        run.store.put("escape", rec["id"], rec)
        run.event("verification.defect_escaped", "task", x["id"], {"where": where, "found_by": found_by},
                  actor="verification", correlation_id=x["id"])
