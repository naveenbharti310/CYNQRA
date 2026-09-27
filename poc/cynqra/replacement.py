"""The Replacement Engine: should a worker's intelligence change?

Product definition, Stage 10 and section 5. When evidence says a worker's model is underperforming, Cynqra
evaluates the available alternatives and decides one of three things, and says why:

  keep      no alternative is expected to do better, or the evidence is not yet enough
  reroute   move the task to another worker of the same role, whose model is expected to do better; both workers
            keep their identities
  replace   give the worker another model; the worker's identity, role, authority, history and workspace stay

Before a new intelligence continues the work it passes a regression check (probe.regression_check): its verified
record on this kind of work for its current version, or the calibration work of that kind done now. A model that
fails is not used, and the next one is tried. "Worker -> model -> underperforms -> alternative -> regression check
-> continue" is exactly this module.

Triggers:
  forced     a task failed verification three times, replies kept overflowing, or the model stopped answering:
             the founder decides only when no alternative passes
  evidence   the Performance Engine's thresholds are crossed earlier (performance.below): keep is an answer
"""
from __future__ import annotations

import shutil

from . import performance
from .db import now
from .probe import regression_check
from .workforce import MAX_REPLACEMENTS, estimate


def _left(engine, t) -> float:
    L = engine.wf.ledger(engine.store)
    return L["reserve"] + max(0.0, L["allocated"].get(t["id"], 0.0) - L["spent"].get(t["id"], 0.0))


def _record(engine, t, decision: str, why: str, rows: list, extra: dict | None = None) -> dict:
    n = engine._count("evaluation") + 1
    ev = {"id": f"eval_{n:03d}", "task_id": t["id"], "worker_id": t["owner_worker_id"],
          "model_id": engine.model_of(t["owner_worker_id"]), "decision": decision, "why": why[:400],
          "candidates": [{k: r.get(k) for k in ("model_id", "model", "score", "p_task", "expected_usd", "fits_budget")}
                         for r in rows], **(extra or {}), "at": now()}
    engine.store.put("evaluation", ev["id"], ev)
    engine.event("intelligence.evaluated", "worker", t["owner_worker_id"],
                 {"task_id": t["id"], "decision": decision, "why": why[:200], **(extra or {})},
                 actor="replacement_engine", correlation_id=t["id"])
    return ev


def evaluate(engine, t: dict, why: str, forced: bool) -> dict:
    """Decide keep, reroute or replace for the worker that owns t. Returns the engine step's result."""
    if not engine.staffed_by_registry() or t.get("replacements", 0) >= MAX_REPLACEMENTS:
        return engine._escalate(t, why) if forced else {"did": "kept", "task": t["id"]}
    wid = t["owner_worker_id"]
    w = engine.worker(wid)
    old = w["model_id"]
    tv = engine.wf.settings(engine.store)["time_value_per_hour"]
    left = _left(engine, t)
    best, rows = engine.wf.choose(engine.store, [t["kind"]], budget_left=left, exclude={old}, role_name=w["role"])
    try:
        current = estimate(engine.wf.reg, engine.wf.reg.get(old), t["kind"], tv)
    except Exception:  # noqa: BLE001 - a removed model has no estimate; anything is better
        current = None
    # Reroute: another worker of the same role, on a different available model, with the least open work.
    peers = []
    for p in engine.store.all("worker"):
        if p["id"] == wid or p["role"] != w["role"] or not p.get("model_id") or p["model_id"] == old:
            continue
        m = engine.wf.reg.get(p["model_id"])
        if not engine.wf.reg.availability(m)[0]:
            continue
        e = estimate(engine.wf.reg, m, t["kind"], tv)
        if e["expected_usd"] > left + 1e-9:
            continue
        open_ = sum(1 for x in engine.tasks() if x["owner_worker_id"] == p["id"] and x["status"] != "VERIFIED")
        peers.append((e["score"], open_, p, e))
    peers.sort(key=lambda x: (x[0], x[1]))
    options = []  # (score, kind, payload)
    if peers:
        options.append((peers[0][0], "reroute", peers[0]))
    for r in rows:
        if r["fits_budget"]:
            options.append((r["score"], "replace", r))
    options.sort(key=lambda o: o[0])
    if not forced:  # evidence-triggered: only change when the alternative is expected to do better
        options = [o for o in options if current is None or o[0] < current["score"]]
    tried = []
    for score, kind, payload in options:
        model_id = payload[2]["model_id"] if kind == "reroute" else payload["model_id"]
        check = regression_check(engine.wf.reg, model_id, t["kind"])
        if check.get("usd"):
            engine.wf.charge(engine.store, wid, t["id"], check["usd"])
        tried.append({"model_id": model_id, "action": kind, "regression": check["evidence"], "passed": check["passed"]})
        if not check["passed"]:
            continue
        extra = {"regression_check": check["evidence"], "tried": tried, "forced": forced}
        if kind == "reroute":
            _record(engine, t, "reroute", why, rows, {**extra, "to_worker": payload[2]["id"]})
            return _reroute(engine, t, payload[2], why)
        _record(engine, t, "replace", why, rows, {**extra, "to_model": model_id})
        return _swap(engine, t, payload, rows, why, check["evidence"])
    if forced:
        _record(engine, t, "escalate", why, rows, {"tried": tried, "forced": True})
        reason = (" No other model passed its regression check." if tried else
                  " No other model in the registry can take it over within the budget." if rows else
                  " No other model in the registry is available.")
        return engine._escalate(t, why + reason)
    _record(engine, t, "keep", why, rows, {"tried": tried, "forced": False,
                                           "why_kept": "no alternative is expected to do better" if not tried
                                           else "no better alternative passed its regression check"})
    return {"did": "kept", "task": t["id"]}


def _swap(engine, t: dict, best: dict, rows: list, why: str, regression: str) -> dict:
    wid = t["owner_worker_id"]
    w = engine.worker(wid)
    old = w["model_id"]
    L = engine.wf.ledger(engine.store)
    spent = L["spent"].get(t["id"], 0.0)
    prior = [o for o in engine.wf.reg.outcomes(old) if o["run_id"] == engine.cid and o["task_id"] == t["id"]]
    w.update({"model_id": best["model_id"], "intelligence_source_id": best["model"]})
    engine.store.put("worker", wid, w)
    e = estimate(engine.wf.reg, engine.wf.reg.get(best["model_id"]), t["kind"],
                 engine.wf.settings(engine.store)["time_value_per_hour"])
    engine.wf.reallocate(engine.store, t, old, e)
    n = engine._count("replacement") + 1
    rep = {"id": f"rep_{n:03d}", "task_id": t["id"], "worker_id": wid, "role": w["role"], "from": old,
           "to": best["model_id"], "reason": why[:400], "attempts": len(prior), "usd_spent_by_previous": round(spent, 4),
           "candidates": rows, "regression_check": regression, "at": now(),
           "inherited": ["objective", "task specification and handoff", "decided rules", "workspace files",
                         "previous attempts and their failures", "test results"]}
    engine.store.put("replacement", rep["id"], rep)
    engine.event("worker.model_replaced", "worker", wid, {k: rep[k] for k in ("task_id", "from", "to", "reason", "attempts",
                 "usd_spent_by_previous", "regression_check")} | {"candidates": [{k: r[k] for k in (
                     "model", "score", "p_task", "expected_usd")} for r in rows]},
                 actor="replacement_engine", correlation_id=t["id"])
    handover = (f"You are taking over {t['id']} ({t['title']}) as {w['title']}; the previous intelligence, "
                f"{engine.wf.reg.get(old)['name']}, made {len(prior)} attempts without passing verification. "
                f"Why it was replaced: {why[:300]} Its files are in your workspace and kept; continue from them "
                "rather than starting again.")
    t.update({"status": "REWORK" if t["kind"] in ("spec", "code") else "ASSIGNED", "attempts": 0, "cut_offs": 0,
              "replacements": t.get("replacements", 0) + 1,
              "feedback": handover + ("\n" + t["feedback"] if t.get("feedback") else "")})
    engine._save_task(t)
    return {"did": "replaced", "task": t["id"], "from": old, "to": best["model_id"]}


def _reroute(engine, t: dict, peer: dict, why: str) -> dict:
    """Task reassignment: the work moves to a peer of the same role; its files move with it."""
    src_ws, dst_ws = engine._ws(t["owner_worker_id"], t["id"]), engine._ws(peer["id"], t["id"])
    for sub in ("inbox", "out"):
        if (src_ws / sub).exists():
            shutil.copytree(src_ws / sub, dst_ws / sub, dirs_exist_ok=True)
    frm = t["owner_worker_id"]
    L = engine.wf.ledger(engine.store)
    alloc = L["allocated"].get(t["id"], 0.0)
    for who, sign in ((frm, -1), (peer["id"], 1)):
        b = L["by_worker"].setdefault(who, {"allocated": 0.0, "spent": 0.0})
        b["allocated"] = round(b["allocated"] + sign * alloc, 4)
    engine.store.put("workforce", "ledger", L)
    n = engine._count("replacement") + 1
    rep = {"id": f"rep_{n:03d}", "task_id": t["id"], "worker_id": frm, "to_worker": peer["id"], "role": peer["role"],
           "from": engine.model_of(frm), "to": peer["model_id"], "reason": why[:400], "attempts": t["attempts"],
           "usd_spent_by_previous": round(L["spent"].get(t["id"], 0.0), 4), "candidates": [], "rerouted": True,
           "at": now(), "inherited": ["task specification and handoff", "workspace files", "test results"]}
    engine.store.put("replacement", rep["id"], rep)
    engine.event("task.rerouted", "task", t["id"], {"from_worker": frm, "to_worker": peer["id"], "reason": why[:200]},
                 actor="replacement_engine", correlation_id=t["id"])
    t.update({"owner_worker_id": peer["id"], "status": "REWORK" if t["kind"] in ("spec", "code") else "ASSIGNED",
              "attempts": 0, "cut_offs": 0, "replacements": t.get("replacements", 0) + 1,
              "accountable": peer.get("reports_to") or "founder",
              "feedback": f"Rerouted to you from {frm}: {why[:300]} Its files are in your workspace."})
    engine._save_task(t)
    return {"did": "rerouted", "task": t["id"], "from": frm, "to": peer["id"]}


def check_thresholds(engine, t: dict) -> dict | None:
    """After a failed verification: has the owner's current intelligence crossed a threshold?"""
    if not engine.staffed_by_registry():
        return None
    wid = t["owner_worker_id"]
    card = performance.scorecard(engine.store, wid, engine.model_of(wid))
    f = engine.store.get("forecast", "current") or {}
    per_task = next((r["inference"] for r in f.get("tasks", []) if r["task_id"] == t["id"]), None)
    reasons = performance.below(card, per_task)
    if not reasons:
        return None
    return evaluate(engine, t, f"{wid} on {engine.model_of(wid)}: " + "; ".join(reasons), forced=False)

