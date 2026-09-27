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


def probe(reg, model_id: str, log=print) -> dict:
    """Run both probes on one registered model and record every round as an outcome."""
    m = reg.get(model_id)
    run_id = f"probe_{int(time.time())}"
    src = ModelSource(router=lambda worker: (model_id, reg.route(model_id)))
    result = {"model_id": model_id, "model": m["name"], "objective": None, "code_rounds": [], "passed": False}

    def outcome(kind, verified, usage, attempt, failure=""):
        c = reg.record_call(model_id, role="probe", purpose=kind, task_kind=kind, usage=usage, run_id=run_id)
        reg.record_outcome(model_id, role="probe", task_kind=kind, task_id=f"probe_{kind}", run_id=run_id,
                           attempt=attempt, verified=verified, usd=c["usd"], seconds=c["seconds"],
                           tokens=c["tokens_in"] + c["tokens_out"], failure=failure, source="probe")

    try:
        data, u = src.structure_objective(CHECK_OBJECTIVE)
        empty = [k for k in OBJECTIVE_KEYS if not str(data.get(k) or "").strip()]
        outcome("objective", not empty, u, 1, "empty fields: " + ", ".join(empty) if empty else "")
        result["objective"] = {"filled": len(OBJECTIVE_KEYS) - len(empty), "seconds": u.get("latency_s")}
        log(f"  {m['name']}: objective {len(OBJECTIVE_KEYS) - len(empty)} of {len(OBJECTIVE_KEYS)} fields")
        objective = {k: str(data.get(k) or "") for k in OBJECTIVE_KEYS}
        work = Path(tempfile.mkdtemp(prefix="cynqra_probe_"))
        feedback, previous = "", {}
        try:
            for rnd in range(3):
                out, u = src.work(CHECK_TASK, worker="w_eng_a", objective=objective, rules=[], handoff=CHECK_HANDOFF,
                                  inbox={}, feedback=feedback, previous=previous, repo_files=[])
                for name, text in (out.get("files") or {}).items():
                    if isinstance(text, str) and name.endswith(".py") and "/" not in name:
                        (work / name).write_text(text, encoding="utf-8")
                rep = run_unittests(work)
                ok = rep["passed"] and not out.get("cut_off")
                outcome("code", ok, u, rnd + 1, "" if ok else failure_summary(rep))
                result["code_rounds"].append({"tests": rep["ran"], "failed": len(rep["failed"]), "passed": ok,
                                              "seconds": u.get("latency_s")})
                log(f"  {m['name']}: code round {rnd + 1}: {rep['ran']} tests, {len(rep['failed'])} failed")
                if ok:
                    result["passed"] = True
                    break
                previous = {p.name: p.read_text(encoding="utf-8") for p in sorted(work.glob("*.py"))}
                feedback = failure_summary(rep) + "\n" + rep["output"][-1500:]
        finally:
            shutil.rmtree(work, ignore_errors=True)
    except IntelligenceError as exc:
        reg.record_call(model_id, role="probe", purpose="error", task_kind="probe", usage=exc.usage, run_id=run_id,
                        error=str(exc))
        result["error"] = str(exc)
        log(f"  {m['name']}: model error: {exc}")
    result["performance"] = reg.profile(model_id)
    return result
