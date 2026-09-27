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
from .testrunner import failure_summary, run_unittests

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
    """One intelligence's calibration or regression work: every call through the Intelligence Gateway, every round
    an outcome in the Intelligence Registry. It is the access point its model source is bound to."""

    def __init__(self, supply, model_id: str, source: str):
        self.supply, self.reg, self.model_id, self.source = supply, supply.registry, model_id, source
        self.run_id = f"{source}_{int(time.time())}"
        self.src = ModelSource()
        self.src.bind(self)
        self.usd = 0.0

    def intelligence_for(self, worker: str) -> str:
        return self.model_id

    def invoke(self, worker: str, request: dict) -> dict:
        return self.supply.gateway.invoke(self.model_id, request)

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
        """A structured answer. One field left empty is what the founder fills in review; more is not the job."""
        data, u = self.src.structure_objective(CHECK_OBJECTIVE)
        empty = [k for k in OBJECTIVE_KEYS if not str(data.get(k) or "").strip()]
        ok = len(empty) <= 1
        self.outcome("objective", ok, u, 1, "empty fields: " + ", ".join(empty) if empty else "")
        log(f"  objective {len(OBJECTIVE_KEYS) - len(empty)} of {len(OBJECTIVE_KEYS)} fields"
            + (f", left for the founder: {', '.join(empty)}" if empty else "") + _speed(u))
        return ok, {"filled": len(OBJECTIVE_KEYS) - len(empty), "left_for_founder": empty, "usage": _slim(u),
                    "fields": {k: str(data.get(k) or "") for k in OBJECTIVE_KEYS}}

    def code(self, objective: dict, log) -> tuple[bool, list]:
        """Code that passes its own tests, fixed from the failures for up to three rounds, as the engine asks: a reply
        carries only the files it changes, and one cut off at the output limit is asked for the rest."""
        rounds = []
        work = Path(tempfile.mkdtemp(prefix="cynqra_probe_"))
        feedback, previous = "", {}
        try:
            for rnd in range(3):
                out, u = self.src.work(CHECK_TASK, worker="w_eng_a", objective=objective, rules=[],
                                       handoff=CHECK_HANDOFF, inbox={}, feedback=feedback, previous=previous,
                                       repo_files=[], persona=ENGINEER, answerers=["w_pm"])
                for name in out.get("delete") or []:
                    if isinstance(name, str) and "/" not in name and (work / name).is_file():
                        (work / name).unlink()
                for name, text in (out.get("files") or {}).items():
                    if isinstance(text, str) and name.endswith(".py") and "/" not in name:
                        (work / name).write_text(text, encoding="utf-8")
                files = {f.name: f.read_text(encoding="utf-8") for f in sorted(work.glob("*.py"))}
                rep = run_unittests(work)
                cut = out.get("cut_off")
                ok = rep["passed"] and not cut
                self.outcome("code", ok, u, rnd + 1, "" if ok else failure_summary(rep))
                r = {"files": sorted(files), "tests": rep["ran"], "failed": len(rep["failed"]), "passed": ok,
                     "cut_off": cut, "usage": _slim(u)}
                if not out.get("files"):  # what the model wrote, so a format problem is visible, not guessed at
                    r["unreadable_reply"] = self.src.last_text[:6000]
                rounds.append(r)
                log(f"  code round {rnd + 1}: {sorted(files)}" + (f" (cut off while writing {cut})" if cut else "")
                    + f"; {rep['ran']} tests, {len(rep['failed'])} failed" + _speed(u))
                if ok:
                    return True, rounds
                previous = files
                if cut:
                    feedback = (f"Your reply was longer than the output limit and was cut off while writing {cut}. "
                                "Send only the files still missing or unfinished, each one complete and short.")
                elif not out.get("files"):
                    feedback = "Your reply contained no files. Every file must be in the === FILE: name === layout."
                else:
                    feedback = failure_summary(rep) + "\n" + rep["output"][-1500:]
        finally:
            shutil.rmtree(work, ignore_errors=True)
        return False, rounds


def _slim(u: dict) -> dict:
    return {k: u.get(k) for k in ("tokens_in", "tokens_out", "latency_s", "read_tps", "write_tps", "cached")}


def _speed(u: dict) -> str:
    return (f"; {u['tokens_in']} tokens in, {u['tokens_out']} out, {u.get('latency_s') or 0:.0f} s"
            + (f"; reads {u['read_tps']} tokens/s, writes {u['write_tps']} tokens/s" if u.get("write_tps") else ""))


def probe(supply, model_id: str, log=print) -> dict:
    """Run both probes on one registered model and record every round as an outcome. The result also settles the
    model's regression gate for its current version."""
    reg = supply.registry
    m = reg.get(model_id)
    if m["runtime"] == "scripted":
        raise ValueError("the scripted demo is not a model; there is nothing to probe")
    run = _Run(supply, model_id, "probe")
    result = {"model_id": model_id, "model": m["name"], "objective": None, "code_rounds": [], "passed": False}
    say = lambda s: log(f"{m['name']}:{s}")  # noqa: E731
    try:
        ok_obj, result["objective"] = run.objective(say)
        ok_code, result["code_rounds"] = run.code(result["objective"].pop("fields"), say)
        result.update(passed=ok_obj and ok_code, objective_passed=ok_obj, code_passed=ok_code)
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


def regression_check(supply, model_id: str, kind: str, log=lambda s: None) -> dict:
    """Before a model takes over a worker's task: evidence that it can do this kind of work now. Its own verified
    record on the kind is enough (and a passed regression gate for its version); otherwise it does the calibration
    work of that kind here, and the result is recorded like any other outcome."""
    reg = supply.registry
    m = reg.get(model_id)
    if m["runtime"] == "scripted":
        return {"passed": False, "evidence": "the scripted demo can only replay its own scenario", "ran": False}
    status = (m.get("regression") or {}).get("status")
    version = m.get("version") or ""
    done = [o for o in reg.outcomes(model_id, kind) if o["verified"] and (o.get("model_version") or "") == version]
    if status == "failed":
        return {"passed": False, "evidence": "its version failed the regression gate", "ran": False}
    if done:
        return {"passed": True, "evidence": f"{len(done)} verified {kind} attempt(s) on record for this version",
                "ran": False}
    run = _Run(supply, model_id, "regression")
    try:
        if kind in roles.BUILD_TYPES:
            ok, rounds = run.code({"product": "Order tracker for a bakery"}, log)
            evidence = f"calibration code task: {'passed' if ok else 'failed'} in {len(rounds)} round(s)"
        else:
            ok, info = run.objective(log)
            evidence = f"calibration structured answer: {info['filled']} of {len(OBJECTIVE_KEYS)} fields"
    except IntelligenceError as exc:
        reg.record_call(model_id, role="regression", purpose="error", task_kind=kind, usage=exc.usage,
                        run_id=run.run_id, error=str(exc))
        return {"passed": False, "evidence": f"model error: {exc}", "ran": True, "usd": run.usd}
    if status == "unverified" and kind in roles.BUILD_TYPES:
        reg.set_regression(model_id, ok, evidence)
    return {"passed": ok, "evidence": evidence, "ran": True, "usd": round(run.usd, 6)}
