"""A registered model's first measured record: it does two pieces of Cynqra's real work.

1. objective: structure a founder's sentence into the seven objective fields (JSON Schema). Verified when every
   field is filled.
2. code: write a small module and its tests from a precise handoff, fixing it from the failing tests for up to
   three rounds, as an engineer does. Each round is verified by running the tests.

Every round is an outcome in the registry for this model (source "probe"), with its real tokens, time and cost,
exactly like work inside a project. Nothing is scored by hand and nothing is copied from a benchmark.
"""
from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

from . import roles
from .intelligence import OBJECTIVE_KEYS, IntelligenceError, ModelSource
from .verification import failure_summary, run_unittests

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


ENGINEER = roles.prompt_text({"id": "w_eng_a", "role": "Engineer", "title": "Software Engineer"})


class _Run:
    """One model's calibration or regression work: every round an outcome in the registry."""

    def __init__(self, reg, model_id: str, source: str):
        self.reg, self.model_id, self.source = reg, model_id, source
        self.run_id = f"{source}_{int(time.time())}"
        self.src = ModelSource(router=lambda worker: (model_id, reg.route(model_id)))
        self.usd = 0.0

    def outcome(self, kind, verified, usage, attempt, failure=""):
        c = self.reg.record_call(self.model_id, role=self.source, purpose=kind, task_kind=kind, usage=usage,
                                 run_id=self.run_id)
        self.reg.record_outcome(self.model_id, role=self.source, task_kind=kind, task_id=f"{self.source}_{kind}",
                                run_id=self.run_id, attempt=attempt, verified=verified, usd=c["usd"],
                                seconds=c["seconds"], tokens=c["tokens_in"] + c["tokens_out"], failure=failure,
                                source=self.source)
        self.usd += c["usd"]
        return c

    def objective(self, log) -> tuple[bool, dict]:
        data, u = self.src.structure_objective(CHECK_OBJECTIVE)
        empty = [k for k in OBJECTIVE_KEYS if not str(data.get(k) or "").strip()]
        self.outcome("objective", not empty, u, 1, "empty fields: " + ", ".join(empty) if empty else "")
        log(f"  objective {len(OBJECTIVE_KEYS) - len(empty)} of {len(OBJECTIVE_KEYS)} fields")
        return not empty, {"filled": len(OBJECTIVE_KEYS) - len(empty), "seconds": u.get("latency_s"),
                           "fields": {k: str(data.get(k) or "") for k in OBJECTIVE_KEYS}}

    def code(self, objective: dict, log) -> tuple[bool, list]:
        rounds = []
        work = Path(tempfile.mkdtemp(prefix="cynqra_probe_"))
        feedback, previous = "", {}
        try:
            for rnd in range(3):
                out, u = self.src.work(CHECK_TASK, worker="w_eng_a", objective=objective, rules=[],
                                       handoff=CHECK_HANDOFF, inbox={}, feedback=feedback, previous=previous,
                                       repo_files=[], persona=ENGINEER, answerers=["w_pm"])
                for name, text in (out.get("files") or {}).items():
                    if isinstance(text, str) and name.endswith(".py") and "/" not in name:
                        (work / name).write_text(text, encoding="utf-8")
                rep = run_unittests(work)
                ok = rep["passed"] and not out.get("cut_off")
                self.outcome("code", ok, u, rnd + 1, "" if ok else failure_summary(rep))
                rounds.append({"tests": rep["ran"], "failed": len(rep["failed"]), "passed": ok,
                               "seconds": u.get("latency_s")})
                log(f"  code round {rnd + 1}: {rep['ran']} tests, {len(rep['failed'])} failed")
                if ok:
                    return True, rounds
                previous = {p.name: p.read_text(encoding="utf-8") for p in sorted(work.glob("*.py"))}
                feedback = failure_summary(rep) + "\n" + rep["output"][-1500:]
        finally:
            shutil.rmtree(work, ignore_errors=True)
        return False, rounds


def probe(reg, model_id: str, log=print) -> dict:
    """Run both probes on one registered model and record every round as an outcome. The result also settles the
    model's regression gate for its current version."""
    m = reg.get(model_id)
    run = _Run(reg, model_id, "probe")
    result = {"model_id": model_id, "model": m["name"], "objective": None, "code_rounds": [], "passed": False}
    say = lambda s: log(f"{m['name']}:{s}")  # noqa: E731
    try:
        ok_obj, result["objective"] = run.objective(say)
        ok_code, result["code_rounds"] = run.code(result["objective"].pop("fields"), say)
        result["passed"] = ok_code
        reg.set_regression(model_id, ok_obj and ok_code,
                           f"probe: objective {'filled' if ok_obj else 'incomplete'}, code "
                           f"{'passed' if ok_code else 'failed'} in {len(result['code_rounds'])} round(s)")
    except IntelligenceError as exc:
        reg.record_call(model_id, role="probe", purpose="error", task_kind="probe", usage=exc.usage, run_id=run.run_id,
                        error=str(exc))
        result["error"] = str(exc)
        log(f"  {m['name']}: model error: {exc}")
    result["performance"] = reg.profile(model_id)
    return result


def regression_check(reg, model_id: str, kind: str, log=lambda s: None) -> dict:
    """Before a model takes over a worker's task: evidence that it can do this kind of work now. Its own verified
    record on the kind is enough (and a passed regression gate for its version); otherwise it does the calibration
    work of that kind here, and the result is recorded like any other outcome."""
    m = reg.get(model_id)
    status = (m.get("regression") or {}).get("status")
    version = m.get("version") or ""
    done = [o for o in reg.outcomes(model_id, kind) if o["verified"] and (o.get("model_version") or "") == version]
    if status == "failed":
        return {"passed": False, "evidence": "its version failed the regression gate", "ran": False}
    if done:
        return {"passed": True, "evidence": f"{len(done)} verified {kind} attempt(s) on record for this version",
                "ran": False}
    run = _Run(reg, model_id, "regression")
    try:
        if kind == "code":
            ok, rounds = run.code({"product": "Order tracker for a bakery"}, log)
            evidence = f"calibration code task: {'passed' if ok else 'failed'} in {len(rounds)} round(s)"
        else:
            ok, info = run.objective(log)
            evidence = f"calibration structured answer: {info['filled']} of {len(OBJECTIVE_KEYS)} fields"
    except IntelligenceError as exc:
        reg.record_call(model_id, role="regression", purpose="error", task_kind=kind, usage=exc.usage,
                        run_id=run.run_id, error=str(exc))
        return {"passed": False, "evidence": f"model error: {exc}", "ran": True, "usd": run.usd}
    if status == "unverified" and kind == "code":
        reg.set_regression(model_id, ok, evidence)
    return {"passed": ok, "evidence": evidence, "ran": True, "usd": round(run.usd, 6)}
