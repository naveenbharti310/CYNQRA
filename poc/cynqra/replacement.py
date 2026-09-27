"""The Replacement Engine: should a worker's intelligence change? (Stage 10, section 5)

When evidence says a worker's model is underperforming, Cynqra evaluates the available alternatives and decides one
of three things, and records why:

  keep      no alternative is expected to do better, or no better one passes its regression check
  reroute   the task moves to another worker of the same role whose model is expected to do better; both workers
            keep their identities
  replace   the worker gets another model; its identity, role, authority, history and workspace stay

Before a new intelligence continues the work it passes a regression check (probe.regression_check): its verified
record on this kind of work for its current version, or the calibration work of that kind done now. A model that
fails is skipped and the next is tried: worker -> model -> underperforms -> alternative -> regression check ->
continue.

Triggers:
  forced     a task failed verification three times, replies kept overflowing, or the model stopped answering;
             the founder decides only when no alternative passes, or the task has had its replacements
  evidence   the Performance Engine's thresholds were crossed earlier (performance.below); keep is an answer
"""
from __future__ import annotations

import shutil

from . import budget, performance, roles, router
from . import settings as project_settings
from .db import now
from .probe import regression_check

MAX_REPLACEMENTS = 2  # intelligence changes per task before the founder decides


def _record(run, t, decision: str, why: str, rows: list, extra: dict | None = None) -> dict:
    n = run.count("evaluation") + 1
    ev = {"id": f"eval_{n:03d}", "task_id": t["id"], "worker_id": t["owner_worker_id"],
          "model_id": run.model_of(t["owner_worker_id"]), "decision": decision, "why": why[:400],
          "candidates": [{k: r.get(k) for k in ("model_id", "model", "score", "p_task", "expected_usd", "fits_budget")}
                         for r in rows], **(extra or {}), "at": now()}
    run.store.put("evaluation", ev["id"], ev)
    run.event("intelligence.evaluated", "worker", t["owner_worker_id"], {"task_id": t["id"], "decision": decision,
              "why": why[:200], **(extra or {})}, actor="replacement_engine", correlation_id=t["id"])
    return ev


def evaluate(run, t: dict, why: str, forced: bool) -> dict:
    """Decide keep, reroute or replace for the worker that owns t. Returns the step's result."""
    if t.get("replacements", 0) >= MAX_REPLACEMENTS:
        return run.escalate(t, why + " It has already had its intelligence changes.") if forced \
            else {"did": "kept", "task": t["id"]}
    reg, s = run.registry, project_settings.get(run.store)
    wid = t["owner_worker_id"]
    w = run.worker(wid)
    old = w["model_id"]
    left = budget.left_for(run.store, t["id"])
    _, rows = router.choose(reg, s, [t["kind"]], budget_left=left, exclude={old})
    try:
        current = router.estimate(reg, reg.get(old), t["kind"], s["time_value_per_hour"])
    except Exception:  # noqa: BLE001 - a removed model has no estimate: any alternative is better
        current = None
    options = []  # (score, action, payload); a reroute first among equals, it changes no intelligence
    peers = []
    for p in run.workers():
        if p["id"] == wid or p["role"] != w["role"] or not p.get("model_id") or p["model_id"] == old:
            continue
        m = reg.get(p["model_id"])
        if not reg.availability(m)[0]:
            continue
        e = router.estimate(reg, m, t["kind"], s["time_value_per_hour"])
        if e["expected_usd"] <= left + 1e-9:
            busy = sum(1 for x in run.tasks() if x["owner_worker_id"] == p["id"] and x["status"] != "VERIFIED")
            peers.append((e["score"], busy, p))
    if peers:
        best_peer = min(peers, key=lambda x: (x[0], x[1]))
        options.append((best_peer[0], 0, "reroute", best_peer[2]))
    options += [(r["score"], 1, "replace", r) for r in rows if r["fits_budget"]]
    options.sort(key=lambda o: (o[0], o[1]))
    if not forced:  # evidence-triggered: change only when an alternative is expected to do better
        options = [o for o in options if current is None or o[0] < current["score"]]
    tried = []
    for _, _, action, payload in options:
        model_id = payload["model_id"]
        check = regression_check(reg, model_id, t["kind"])
        if check.get("usd"):
            run.spend(wid, t["id"], check["usd"], "verification")
        tried.append({"model_id": model_id, "action": action, "regression": check["evidence"], "passed": check["passed"]})
        if not check["passed"]:
            continue
        extra = {"regression_check": check["evidence"], "tried": tried, "forced": forced}
        if action == "reroute":
            _record(run, t, "reroute", why, rows, {**extra, "to_worker": payload["id"]})
            return _reroute(run, t, payload, why)
        _record(run, t, "replace", why, rows, {**extra, "to_model": model_id})
        return _swap(run, t, payload, rows, why, check["evidence"])
    if forced:
        _record(run, t, "escalate", why, rows, {"tried": tried, "forced": True})
        reason = (" No other model passed its regression check." if tried else
                  " No other model in the registry can take it over within the budget." if rows else
                  " No other model in the registry is available.")
        return run.escalate(t, why + reason)
    _record(run, t, "keep", why, rows, {"tried": tried, "forced": False,
                                        "why_kept": "no alternative is expected to do better" if not tried
                                        else "no better alternative passed its regression check"})
    return {"did": "kept", "task": t["id"]}


def _swap(run, t: dict, best: dict, rows: list, why: str, regression: str) -> dict:
    wid = t["owner_worker_id"]
    w = run.worker(wid)
    old = w["model_id"]
    reg = run.registry
    spent = budget.ledger(run.store)["spent"].get(t["id"], 0.0)
    prior = [o for o in reg.outcomes(old) if o["run_id"] == run.cid and o["task_id"] == t["id"]]
    w.update({"model_id": best["model_id"], "model": best["model"]})
    run.store.put("worker", wid, w)
    e = router.estimate(reg, reg.get(best["model_id"]), t["kind"],
                        project_settings.get(run.store)["time_value_per_hour"])
    budget.reallocate(run.store, t["id"], old, e)
    n = run.count("replacement") + 1
    rep = {"id": f"rep_{n:03d}", "task_id": t["id"], "worker_id": wid, "role": w["role"], "from": old,
           "to": best["model_id"], "reason": why[:400], "attempts": len(prior), "usd_spent_by_previous": round(spent, 4),
           "candidates": rows, "regression_check": regression, "rerouted": False, "at": now(),
           "inherited": ["objective", "task specification and handoff", "decided rules", "workspace files",
                         "previous attempts and their failures", "test results"]}
    run.store.put("replacement", rep["id"], rep)
    run.event("worker.model_replaced", "worker", wid, {k: rep[k] for k in ("task_id", "from", "to", "reason", "attempts",
              "usd_spent_by_previous", "regression_check")} | {"candidates": [{k: r[k] for k in (
                  "model", "score", "p_task", "expected_usd")} for r in rows]},
              actor="replacement_engine", correlation_id=t["id"])
    handover = (f"You are taking over {t['id']} ({t['title']}) as {w['title']}; the previous intelligence, "
                f"{reg.get(old)['name']}, made {len(prior)} attempts without passing verification. Why it was "
                f"replaced: {why[:300]} Its files are in your workspace and kept; continue from them rather than "
                "starting again.")
    t.update({"status": "REWORK" if t["kind"] in roles.FILE_TYPES else "ASSIGNED", "attempts": 0, "cut_offs": 0,
              "replacements": t.get("replacements", 0) + 1,
              "feedback": handover + ("\n" + t["feedback"] if t.get("feedback") else "")})
    run.save_task(t)
    return {"did": "replaced", "task": t["id"], "from": old, "to": best["model_id"]}


def _reroute(run, t: dict, peer: dict, why: str) -> dict:
    """Task reassignment: the work moves to a peer of the same role; its files and its allocation move with it."""
    frm = t["owner_worker_id"]
    src, dst = run.workspace(frm, t["id"]), run.workspace(peer["id"], t["id"])
    for sub in ("inbox", "out"):
        if (src / sub).exists():
            shutil.copytree(src / sub, dst / sub, dirs_exist_ok=True)
    budget.move(run.store, t["id"], frm, peer["id"])
    n = run.count("replacement") + 1
    rep = {"id": f"rep_{n:03d}", "task_id": t["id"], "worker_id": frm, "to_worker": peer["id"], "role": peer["role"],
           "from": run.model_of(frm), "to": peer["model_id"], "reason": why[:400], "attempts": t["attempts"],
           "usd_spent_by_previous": round(budget.ledger(run.store)["spent"].get(t["id"], 0.0), 4), "candidates": [],
           "rerouted": True, "at": now(), "inherited": ["task specification and handoff", "workspace files",
                                                        "test results"]}
    run.store.put("replacement", rep["id"], rep)
    run.event("task.rerouted", "task", t["id"], {"from_worker": frm, "to_worker": peer["id"], "reason": why[:200]},
              actor="replacement_engine", correlation_id=t["id"])
    t.update({"owner_worker_id": peer["id"], "status": "REWORK" if t["kind"] in roles.FILE_TYPES else "ASSIGNED",
              "attempts": 0, "cut_offs": 0, "replacements": t.get("replacements", 0) + 1,
              "accountable": peer["reports_to"],
              "feedback": f"Rerouted to you from {frm}: {why[:300]} Its files are in your workspace."})
    run.save_task(t)
    return {"did": "rerouted", "task": t["id"], "from": frm, "to": peer["id"]}


def check_thresholds(run, t: dict) -> dict | None:
    """After a failed verification: has the owner's current intelligence crossed a threshold?"""
    wid = t["owner_worker_id"]
    card = performance.scorecard(run.store, wid, run.model_of(wid))
    f = run.store.get("forecast", "current") or {}
    per_task = next((r["inference"] for r in f.get("tasks", []) if r["task_id"] == t["id"]), None)
    reasons = performance.below(card, per_task)
    if not reasons:
        return None
    return evaluate(run, t, f"{wid} on {run.model_of(wid)}: " + "; ".join(reasons), forced=False)


def model_failed(run, t: dict, exc) -> dict | None:
    """A call to a model failed. It counts against the model; a model that is now down is replaced in every worker
    that runs on it, and the step is tried again."""
    if not exc.model_id:
        return None
    involved = [t.get("owner_worker_id"), run.assigner_id(), (t.get("blocker") or {}).get("needs_from")]
    caller = next((w for w in involved if w and run.model_of(w) == exc.model_id), t.get("owner_worker_id"))
    n = run.count("call_error") + 1
    run.store.put("call_error", f"ce_{n:04d}", {"id": f"ce_{n:04d}", "worker_id": caller, "model_id": exc.model_id,
                                                "task_id": t.get("id"), "error": str(exc)[:300], "at": now()})
    reg = run.registry
    reg.record_call(exc.model_id, role="", purpose="error", task_kind=t.get("kind", ""), usage=exc.usage, run_id=run.cid,
                    error=str(exc))
    m = reg.get(exc.model_id)
    if reg.availability(m)[0]:
        return {"did": "model_error_retry", "task": t["id"], "model": exc.model_id, "why": str(exc)}
    out = None
    s = project_settings.get(run.store)
    for w in run.workers():
        if w.get("model_id") != exc.model_id:
            continue
        mine = [x for x in run.tasks() if x["owner_worker_id"] == w["id"] and x["status"] != "VERIFIED"]
        target = t if t["owner_worker_id"] == w["id"] else (mine[0] if mine else None)
        if target is not None:
            out = evaluate(run, target, f"{m['name']} stopped answering: {exc}", forced=True)
        w = run.worker(w["id"])
        if w.get("model_id") == exc.model_id:  # no open task, or its task went to a peer: the worker moves too
            best, _ = router.choose(reg, s, roles.staffing_kinds(w["role"]), exclude={exc.model_id})
            if best:
                w.update({"model_id": best["model_id"], "model": best["model"]})
                run.store.put("worker", w["id"], w)
                run.event("worker.model_assigned", "worker", w["id"], {"role": w["role"], "model_id": best["model_id"],
                          "model": best["model"], "why": f"{m['name']} is down"}, actor="intelligence_router")
    sys_ = run.store.get("workforce", "system")
    if sys_ and sys_.get("model_id") == exc.model_id:
        run.store.put("workforce", "system", {"model_id": None})  # chosen again on the next call
    return out or {"did": "model_replaced", "task": t["id"], "model": exc.model_id}
