"""The Replacement Engine: why did a worker stop, and should its intelligence change? (Stage 10, section 5)

Cynqra never replaces a worker's AI on the first sign of trouble. It first finds out why the worker stopped:

  the provider's side   an outage, a timeout or a rate limit: it will pass, and the AI is not at fault. The worker
                        waits and tries again. A stand-in covers the wait only when the CEO has named a fallback for
                        that AI, or approves one (it costs money); the worker returns to its own AI when it answers.
  the account           no credit left, or the key is refused: the CEO fixes it; the work waits, nothing is replaced.
  the AI itself         the work keeps failing its checks, the replies keep overflowing or breaking the protocol, the
                        measured record falls below the thresholds, or a new version fails its regression check:
                        the AI cannot do this role's work. Only then is it replaced, and the CEO is informed, with
                        what the better AI costs against the old one.

For the AI itself, Cynqra evaluates the alternatives and decides one of three things, and records why:

  keep      no alternative is expected to do better, or no better one passes its regression check
  reroute   the task moves to another worker of the same role whose model is expected to do better; both workers
            keep their identities
  replace   another intelligence takes the seat: a new person, with a new name and a record of its own (people.py).
            The seat's role, authority, work, history and workspace stay; the one who left stays in the history
            as a former holder with their record (binding.py keeps the previous binding in its history)

Before a new intelligence continues the work it passes a regression check (probe.regression_check): its verified
record on this kind of work for its current version, or the calibration work of that kind done now. A model that
fails is skipped and the next is tried: worker -> model -> underperforms -> alternative -> regression check ->
continue.

Triggers:
  forced     a task failed verification three times, replies kept overflowing or breaking the protocol, or the AI
             can no longer be used (retired, removed, failed its regression check); the founder decides only when no
             alternative passes, or the task has had its replacements. The failing intelligence's fallback (registry
             fallback_id) is tried first when it is available and fits.
  evidence   the Performance Engine's thresholds were crossed earlier (performance.below); keep is an answer
  version    the intelligence a worker is bound to reports a new version: it continues only after its regression
             check passes (the binding then pins the new version); otherwise it is unavailable and replaced
"""
from __future__ import annotations

import shutil
import time

from . import attribution as attr
from . import binding, budget, controller, people, performance, planner, policies, roles
from . import settings as project_settings
from .attribution import diagnose  # noqa: F401  - why a call failed; kept here for the engines that ask
from .intelligence_layer import evidence as evidence_model
from .db import now
from .intelligence import IntelligenceError
from .intelligence_layer import router
from .intelligence_layer.registry import served_version
from .probe import regression_check

_RP = policies.body("replacement")
MAX_REPLACEMENTS = _RP["max_replacements"]  # intelligence changes per task before the founder decides
MAX_BAD_REPLIES = _RP["max_bad_replies"]  # unusable replies in a row from one worker on one task before its AI changes

PLAIN = {"outage": "its provider is not answering", "timeout": "its provider took too long to answer",
         "rate_limit": "its provider is limiting how often it may be called",
         "no_credit": "the provider account has no credit or free allowance left for now", "access": "the provider refused the key",
         "withdrawn": "it can no longer be used", "reply": "its reply was cut off or could not be read"}
PROVIDER_SIDE = ("outage", "timeout", "rate_limit")
ACCOUNT = ("no_credit", "access")
WORK_STATES = ("PLANNED", "ASSIGNED", "REWORK", "BLOCKED", "LEAD_REVIEW")


def _per_task(run, model_id: str | None, kind: str) -> float | None:
    """What one task of this kind is expected to cost on this intelligence, in dollars."""
    try:
        return router.estimate(run.registry, run.registry.get(model_id), kind,
                               project_settings.get(run.store)["time_value_per_hour"])["expected_usd"]
    except Exception:  # noqa: BLE001 - a removed intelligence has no estimate
        return None


def _name(run, model_id: str | None) -> str:
    try:
        return run.registry.get(model_id)["name"]
    except Exception:  # noqa: BLE001
        return model_id or "none"


def _price(run, model_id: str | None) -> str:
    try:
        m = run.registry.get(model_id)
    except Exception:  # noqa: BLE001
        return ""
    if m.get("local"):
        return "runs on this computer"
    return f"${m.get('price_in') or 0:g} in and ${m.get('price_out') or 0:g} out per million tokens"


def _cost_line(before: float | None, after: float | None, old: str | None = None, new: str | None = None,
               run=None) -> str:
    """What the change costs: each AI's price, and the expected cost of a verified task (the price with its
    expected retries, so a pricier AI that gets it right first time can cost less per task)."""
    out = ""
    if run is not None and new:
        p_old, p_new = _price(run, old), _price(run, new)
        out += f" Price: {p_new}" + (f", against {p_old} before." if p_old else ".")
    if after is None:
        return out
    if before is None:
        return out + f" Expected cost of a verified task: {budget.dollars(after)}."
    d = after - before
    how = "more" if d > 1e-9 else "less" if d < -1e-9 else "the same"
    return (out + f" Expected cost of a verified task: {budget.dollars(after)} against {budget.dollars(before)} before"
            + (f" ({budget.dollars(abs(d))} {how})." if how != "the same" else ", the same."))


def inform(run, kind: str, *, worker_id: str, task_id: str | None, headline: str, detail: str,
           usd_before: float | None = None, usd_after: float | None = None) -> dict:
    """Tell the founder what Cynqra changed and why. Not a decision: nothing waits on it, and it is not counted as the
    CEO being needed. It stays in the run's record and in the Company Pack."""
    n = run.count("ceo_notice") + 1
    rec = {"id": f"note_{n:03d}", "kind": kind, "worker_id": worker_id, "task_id": task_id, "headline": headline,
           "detail": detail[:600], "usd_per_task_before": usd_before, "usd_per_task_after": usd_after,
           "usd_difference": None if usd_before is None or usd_after is None else round(usd_after - usd_before, 6),
           "at": now()}
    run.store.put("ceo_notice", rec["id"], rec)
    run.event("ceo.informed", "worker", worker_id, {k: rec[k] for k in ("kind", "task_id", "headline",
              "usd_difference")}, actor="replacement_engine", correlation_id=task_id or worker_id)
    return rec


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


def alternatives(run, t: dict, kinds: list[str], exclude: set, why: str, worker: dict | None = None) -> tuple[dict, list]:
    """The alternatives for a piece of work, ranked by the controller from the same evidence and policy as every
    selection (a persisted decision), in the Router's row shape."""
    if worker is not None and worker["id"] != t.get("owner_worker_id"):
        work = controller.work_for_worker(run, worker, kinds)
        d = controller.decide(run, work, "replacement", exclude=exclude, exclude_why={m: why[:200] for m in exclude})
    else:
        d = controller.rank_for(run, t, kinds, exclude=exclude, exclude_why={m: why[:200] for m in exclude})
    return d, controller.legacy_rows(d)


def evaluate(run, t: dict, why: str, forced: bool) -> dict:
    """Decide keep, reroute or replace for the worker that owns t. Returns the step's result. Forced (the work
    kept failing, or the AI can no longer be used): the best alternative that passes its regression check. On
    evidence alone: only an alternative whose evidenced quality is verifiably superior to the incumbent's on this
    work, so a single noisy failure or an untested challenger never displaces it."""
    if t.get("replacements", 0) >= MAX_REPLACEMENTS:
        return run.escalate(t, why + " It has already had its intelligence changes.") if forced \
            else {"did": "kept", "task": t["id"]}
    reg = run.registry
    wid = t["owner_worker_id"]
    w = run.worker(wid)
    old = run.model_for(wid, t["id"])
    left = budget.left_for(run.store, t["id"])
    d, rows = alternatives(run, t, [t["kind"]], {old} if old else set(), why)
    for r in rows:
        r["fits_budget"] = r["fits_budget"] and r["expected_usd"] <= left + 1e-9
    current = controller.assess_incumbent(run, t, old, [t["kind"]]) if old else None
    order = {r["model_id"]: i for i, r in enumerate(rows)}
    options = []  # (rank, tie, action, payload); a reroute first among equals, it changes no intelligence
    peers = []
    for p in run.workers():
        pm = run.model_of(p["id"])
        if p["id"] == wid or p["role"] != w["role"] or not pm or pm == old or pm not in order:
            continue
        if not reg.availability(reg.get(pm))[0]:
            continue
        r = rows[order[pm]]
        if r["fits_budget"]:
            busy = sum(1 for x in run.tasks() if x["owner_worker_id"] == p["id"] and x["status"] != "VERIFIED")
            peers.append((order[pm], busy, p))
    if peers:
        best_peer = min(peers, key=lambda x: (x[0], x[1]))
        options.append((best_peer[0], 0, "reroute", best_peer[2]))
    options += [(order[r["model_id"]], 1, "replace", r) for r in rows if r["fits_budget"]]
    options.sort(key=lambda o: (o[0], o[1]))
    fallback = _fallback_of(reg, old)
    if forced and fallback:  # the failing intelligence names its fallback: that is tried first
        options.sort(key=lambda o: o[2] != "replace" or o[3]["model_id"] != fallback)
    if not forced:  # evidence-triggered: change only on verified superiority
        def q(mid):
            return controller.quality_of(d, mid) or {"mean": 0, "lcb": 0, "ucb": 0, "effective_n": 0}
        options = [o for o in options if current is None or evidence_model.superior(
            q(o[3]["model_id"] if o[2] == "replace" else run.model_of(o[3]["id"])), current)]
    tried = []
    for _, _, action, payload in options:
        model_id = payload["model_id"] if action == "replace" else run.model_of(payload["id"])
        check = regression_check(run.supply, model_id, t["kind"])
        if check.get("usd"):
            run.spend(wid, t["id"], check["usd"], "verification")
        tried.append({"model_id": model_id, "action": action, "regression": check["evidence"], "passed": check["passed"]})
        if not check["passed"]:
            continue
        extra = {"regression_check": check["evidence"], "tried": tried, "forced": forced,
                 "ranking_decision": d["decision_id"]}
        choice = controller.record_choice(run, d, model_id, "reroute" if action == "reroute" else "replacement",
                                          why, tried)
        if action == "reroute":
            _record(run, t, "reroute", why, rows, {**extra, "to_worker": payload["id"],
                                                   "decision_id": choice["decision_id"]})
            return _reroute(run, t, payload, why, choice)
        _record(run, t, "replace", why, rows, {**extra, "to_model": model_id, "decision_id": choice["decision_id"]})
        return _swap(run, t, payload, rows, why, check["evidence"], choice)
    if forced:
        _record(run, t, "escalate", why, rows, {"tried": tried, "forced": True, "ranking_decision": d["decision_id"]})
        reason = (" No other model passed its regression check." if tried else
                  " No other model in the registry can take it over within the budget." if rows else
                  " No other model in the registry is available.")
        return run.escalate(t, why + reason)
    _record(run, t, "keep", why, rows, {"tried": tried, "forced": False, "ranking_decision": d["decision_id"],
                                        "why_kept": "no alternative is verifiably superior on this work" if not tried
                                        else "no superior alternative passed its regression check"})
    return {"did": "kept", "task": t["id"]}


def _fallback_of(reg, model_id: str | None) -> str | None:
    try:
        fb = reg.get(model_id).get("fallback_id") if model_id else None
        return fb if fb and reg.availability(reg.get(fb))[0] else None
    except Exception:  # noqa: BLE001 - a removed intelligence has no fallback
        return None


def _swap(run, t: dict, best: dict, rows: list, why: str, regression: str, decision: dict | None = None) -> dict:
    wid = t["owner_worker_id"]
    w = run.worker(wid)
    old = run.model_for(wid, t["id"])
    reg = run.registry
    spent = budget.ledger(run.store)["spent"].get(t["id"], 0.0)
    prior = [o for o in reg.outcomes(old) if o["run_id"] == run.cid and o["task_id"] == t["id"]]
    new = reg.get(best["model_id"])
    binding.bind(run, wid, new, reason=why, by="replacement_engine", candidates=rows, task_id=t["id"],
                 decision=decision)
    binding.bind_task(run, t["id"], wid, new, reason=why, by="replacement_engine", decision=decision, candidates=rows)
    left, joined = people.replace(run, wid, why, old, best["model_id"])
    w = run.worker(wid)
    e = router.estimate(reg, reg.get(best["model_id"]), t["kind"],
                        project_settings.get(run.store)["time_value_per_hour"])
    budget.reallocate(run.store, t["id"], old, e)
    n = run.count("replacement") + 1
    rep = {"id": f"rep_{n:03d}", "task_id": t["id"], "worker_id": wid, "role": w["role"], "from": old,
           "to": best["model_id"], "left": left, "joined": joined, "reason": why[:400], "attempts": len(prior), "usd_spent_by_previous": round(spent, 4),
           "candidates": rows, "regression_check": regression, "rerouted": False, "at": now(),
           "inherited": ["objective", "task specification and handoff", "decided rules", "workspace files",
                         "previous attempts and their failures", "test results"]}
    run.store.put("replacement", rep["id"], rep)
    run.event("worker.model_replaced", "worker", wid, {k: rep[k] for k in ("task_id", "from", "to", "reason", "attempts",
              "usd_spent_by_previous", "regression_check")} | {"candidates": [{k: r[k] for k in (
                  "model", "score", "p_task", "expected_usd")} for r in rows]},
              actor="replacement_engine", correlation_id=t["id"])
    handover = (f"You are {joined}, taking over {t['id']} ({t['title']}) as {people.seat(w)} from {left}, who "
                f"worked on {_name(run, old)} and made {len(prior)} attempts without passing verification. Why it was "
                f"replaced: {why[:300]} Its files are in your workspace and kept; continue from them rather than "
                "starting again.")
    t.update({"status": "REWORK" if t["kind"] in roles.FILE_TYPES else "ASSIGNED", "attempts": 0, "cut_offs": 0,
              "replacements": t.get("replacements", 0) + 1,
              "feedback": handover + ("\n" + t["feedback"] if t.get("feedback") else "")})
    run.save_task(t)
    before, after = _per_task(run, old, t["kind"]), e["expected_usd"]
    inform(run, "intelligence_replaced", worker_id=wid, task_id=t["id"], usd_before=before, usd_after=after,
           headline=f"{left} was replaced as your AI {people.seat(w)} by {joined}",
           detail=f"Why: {why[:300]} It is not the provider's side: the AI could not do this role's work. {joined} "
                  f"works on {reg.get(best['model_id'])['name']} and passed a check on this kind of work before taking "
                  f"the seat ({regression}). The seat keeps its work, files and history; {left}'s record stays in "
                  f"the history and {joined}'s starts now." + _cost_line(before, after, old, best["model_id"], run))
    return {"did": "replaced", "task": t["id"], "from": old, "to": best["model_id"]}


def _reroute(run, t: dict, peer: dict, why: str, decision: dict | None = None) -> dict:
    """Task reassignment: the work moves to a peer of the same role; its files and its allocation move with it."""
    frm = t["owner_worker_id"]
    to_model = run.model_of(peer["id"])
    if to_model:
        binding.bind_task(run, t["id"], peer["id"], run.registry.get(to_model), reason=f"rerouted: {why}"[:400],
                          by="replacement_engine", decision=decision)
    src, dst = run.workspace(frm, t["id"]), run.workspace(peer["id"], t["id"])
    for sub in ("inbox", "out"):
        if (src / sub).exists():
            shutil.copytree(src / sub, dst / sub, dirs_exist_ok=True)
    budget.move(run.store, t["id"], frm, peer["id"])
    n = run.count("replacement") + 1
    rep = {"id": f"rep_{n:03d}", "task_id": t["id"], "worker_id": frm, "to_worker": peer["id"], "role": peer["role"],
           "from": run.model_of(frm), "to": run.model_of(peer["id"]), "reason": why[:400], "attempts": t["attempts"],
           "usd_spent_by_previous": round(budget.ledger(run.store)["spent"].get(t["id"], 0.0), 4), "candidates": [],
           "rerouted": True, "at": now(), "inherited": ["task specification and handoff", "workspace files",
                                                        "test results"]}
    run.store.put("replacement", rep["id"], rep)
    run.event("task.rerouted", "task", t["id"], {"from_worker": frm, "to_worker": peer["id"], "reason": why[:200]},
              actor="replacement_engine", correlation_id=t["id"])
    t.update({"owner_worker_id": peer["id"], "status": "REWORK" if t["kind"] in roles.FILE_TYPES else "ASSIGNED",
              "attempts": 0, "cut_offs": 0, "replacements": t.get("replacements", 0) + 1, "rerouted": True,
              **planner.coordination(peer, run.workers()),
              "feedback": f"Rerouted to you from {frm}: {why[:300]} Its files are in your workspace."})
    run.save_task(t)
    before, after = _per_task(run, rep["from"], t["kind"]), _per_task(run, rep["to"], t["kind"])
    inform(run, "task_rerouted", worker_id=frm, task_id=t["id"], usd_before=before, usd_after=after,
           headline=f"{t['title']} moved from {people.label(run.worker(frm)) or frm} to {people.label(peer)}",
           detail=f"Why: {why[:300]} {peer.get('name') or peer['title']} works on {_name(run, rep['to'])}, which "
                  "passed its check on this kind of work; both keep their seats." + _cost_line(before, after, rep["from"], rep["to"], run))
    return {"did": "rerouted", "task": t["id"], "from": frm, "to": peer["id"]}


def check_thresholds(run, t: dict) -> dict | None:
    """After a failed verification: has the owner's current intelligence crossed a threshold?"""
    wid = t["owner_worker_id"]
    mid = run.model_for(wid, t["id"])
    card = performance.scorecard(run.store, wid, mid)
    f = run.store.get("forecast", "current") or {}
    per_task = next((r["inference"] for r in f.get("tasks", []) if r["task_id"] == t["id"]), None)
    reasons = performance.below(card, per_task)
    if not reasons:
        return None
    return evaluate(run, t, f"{wid} on {mid}: " + "; ".join(reasons), forced=False)


def model_failed(run, t: dict, exc) -> dict | None:
    """A call to a model failed. First, why: the provider's side and the account are not the AI's fault, so the
    worker waits (or a stand-in covers the wait) and nothing is replaced. Only an AI that can no longer be used is
    replaced here; one that cannot do the work is found from its work (execution.py, check_thresholds)."""
    if not exc.model_id:
        return None
    cause = diagnose(str(exc))
    involved = [actor(t), t.get("owner_worker_id"), t.get("handoff_from"), t.get("reviewed_by"),
                (t.get("blocker") or {}).get("needs_from")]
    caller = next((w for w in involved if w and run.model_of(w) == exc.model_id), t.get("owner_worker_id"))
    n = run.store.next_id("call_error")
    run.store.put("call_error", f"ce_{n:04d}", {"id": f"ce_{n:04d}", "worker_id": caller, "model_id": exc.model_id,
                                                "task_id": t.get("id"), "error": str(exc)[:300], "cause": cause,
                                                "at": now()})
    if t.get("id", "").startswith("t_"):  # evidence: a provider's failure is recorded and never learned as the AI's
        controller.record_attempt_failure(run, run.task(t["id"]), attr.call_failure(str(exc)),
                                          kind="call_failure", idempotency_key=f"call_error:{run.cid}:ce_{n:04d}",
                                          intelligence=(exc.model_id, None), severity="minor", caller=caller)
    reg = run.registry
    reg.record_call(exc.model_id, role="", purpose="error", task_kind=t.get("kind", ""), usage=exc.usage, run_id=run.cid,
                    error="" if cause == "reply" else str(exc))  # the provider answered: it is not down
    m = reg.get(exc.model_id)
    run.event("worker.stopped", "worker", caller or "", {"task_id": t.get("id"), "intelligence_id": m["id"],
              "cause": cause, "why": PLAIN[cause], "error": str(exc)[:200]}, actor="replacement_engine",
              correlation_id=t.get("id"))
    if cause == "reply":
        return _bad_reply(run, t, caller, m, exc)
    if cause == "withdrawn":
        return _withdrawn(run, t, m, exc)
    if cause in ACCOUNT:
        return _account(run, t, m, cause, exc)
    if reg.availability(m)[0]:
        return {"did": "model_error_retry", "task": t["id"], "model": exc.model_id, "cause": cause, "why": str(exc)}
    return _outage(run, t, m, cause, exc)


def _bad_reply(run, t: dict, caller: str, m: dict, exc) -> dict:
    """The provider answered, but the AI's reply was cut off or could not be read. It is asked again; after
    MAX_BAD_REPLIES in a row, the task's owner goes through the usual evaluation, and any other worker (a cofounder
    handing out or reviewing the task, a colleague answering its Blocker) is given another intelligence, and the CEO
    is told what it costs."""
    t = run.task(t["id"])
    counts = t.setdefault("bad_replies", {})
    counts[caller] = counts.get(caller, 0) + 1
    run.save_task(t)
    if counts[caller] < MAX_BAD_REPLIES:
        return {"did": "retry", "task": t["id"], "why": f"{caller}'s reply could not be used: {str(exc)[:200]}"}
    counts[caller] = 0
    run.save_task(t)
    why = f"{m['name']}: {MAX_BAD_REPLIES} replies in a row were cut off or could not be read ({str(exc)[:160]})."
    if caller == t["owner_worker_id"]:
        return evaluate(run, t, why, forced=True)
    return _rebind(run, t, caller, m, why)


def _rebind(run, t: dict, wid: str, m: dict, why: str) -> dict:
    """A worker whose own task is not the one failing (a cofounder coordinating it, a colleague answering it) is
    given the best other intelligence for its role's work that passes a check first."""
    reg, s = run.registry, project_settings.get(run.store)
    w = run.worker(wid)
    _, rows = alternatives(run, t, roles.staffing_kinds(w["role"]), {m["id"]}, why, worker=w)
    kind = "assign" if roles.is_cofounder(w["role"]) else "answer"  # the coordination work it failed at
    for r in [r for r in rows if r["fits_budget"]]:
        check = regression_check(run.supply, r["model_id"], kind)
        if check.get("usd"):
            run.spend(wid, t["id"], check["usd"], "verification")
        if not check["passed"]:
            continue
        new = reg.get(r["model_id"])
        binding.bind(run, wid, new, reason=why, by="intelligence_router", candidates=rows)
        left, joined = people.replace(run, wid, why, m["id"], new["id"])
        w = run.worker(wid)
        before = router.estimate(reg, m, kind, s["time_value_per_hour"])["usd_per_attempt"] if m else None
        after = router.estimate(reg, new, kind, s["time_value_per_hour"])["usd_per_attempt"]
        inform(run, "intelligence_replaced", worker_id=wid, task_id=t["id"], usd_before=before, usd_after=after,
               headline=f"{left} was replaced as your AI {people.seat(w)} by {joined}",
               detail=f"Why: {why} {joined} works on {new['name']} and passed a check first. The seat keeps its "
                      f"work and history; {left}'s record stays in the history." +
                      _cost_line(before, after, m["id"], new["id"], run))
        return {"did": "replaced", "task": t["id"], "worker": wid, "from": m["id"], "to": new["id"]}
    return run.escalate(t, why + f" No other model passed its check for {people.label(w)}'s work.")


def _withdrawn(run, t: dict, m: dict, exc) -> dict:
    """The AI can no longer be used (retired, its connection removed, a new version failed its regression check):
    every worker on it is given another, through the same evaluation, and the CEO is informed."""
    reg, s, out = run.registry, project_settings.get(run.store), None
    for w in run.workers():
        if run.model_of(w["id"]) != m["id"]:
            continue
        mine = [x for x in run.tasks() if x["owner_worker_id"] == w["id"] and x["status"] != "VERIFIED"]
        target = t if t["owner_worker_id"] == w["id"] else (mine[0] if mine else None)
        if target is not None:
            out = evaluate(run, target, f"{m['name']} {PLAIN['withdrawn']}: {exc}", forced=True)
        if run.model_of(w["id"]) == m["id"]:  # no open task, or its task went to a peer: the worker moves too
            _, rows = alternatives(run, target or t, roles.staffing_kinds(w["role"]), {m["id"]},
                                   f"{m['name']} {PLAIN['withdrawn']}", worker=w)
            fb = _fallback_of(reg, m["id"])
            pick = next((r for r in rows if r["model_id"] == fb), None) if fb else None
            pick = pick or next((r for r in rows if r["fits_budget"]), None)
            if pick:
                binding.bind(run, w["id"], reg.get(pick["model_id"]), reason=f"{m['name']} {PLAIN['withdrawn']}",
                             by="intelligence_router", candidates=rows)
                left, joined = people.replace(run, w["id"], f"{m['name']} {PLAIN['withdrawn']}", m["id"],
                                              pick["model_id"])
                inform(run, "intelligence_replaced", worker_id=w["id"], task_id=None,
                       headline=f"{left} was replaced as your AI {people.seat(w)} by {joined}",
                       detail=f"{m['name']}, the AI {left} worked on, {PLAIN['withdrawn']} ({str(exc)[:200]}). {joined} "
                              f"works on {pick['model']}. The seat keeps its work and history.")
    # the control plane's own binding is chosen again on its next call, since its intelligence is unavailable
    return out or {"did": "model_replaced", "task": t["id"], "model": m["id"]}


def actor(t: dict) -> str:
    """Whose move it is on a task: its cofounder hands it over and reviews it, its owner works on it, the colleague
    a Blocker names answers it."""
    return {"PLANNED": t.get("handoff_from"), "ASSIGNED": t["owner_worker_id"], "REWORK": t["owner_worker_id"],
            "BLOCKED": (t.get("blocker") or {}).get("needs_from"), "LEAD_REVIEW": t.get("reviewed_by")
            }.get(t["status"]) or ""


def _park(run, t: dict, model_ids: set, cause: str, decision_id: str | None, until: float) -> list[str]:
    """The failing task, and every task whose next move is by a worker on these intelligences, wait."""
    parked = []
    for x in run.tasks():
        if x["id"] != t["id"] and not (x["status"] in WORK_STATES and run.model_of(actor(x)) in model_ids):
            continue
        if x["status"] == "WAITING":
            x["waiting"].update(decision_id=decision_id or x["waiting"].get("decision_id"), until=until)
        elif x["status"] in WORK_STATES:
            x.update(status="WAITING", waiting_from=x["status"], waiting={
                "model_ids": sorted(model_ids), "cause": cause, "why": PLAIN[cause], "decision_id": decision_id,
                "until": until, "since": now()})
        else:
            continue
        run.save_task(x)
        parked.append(x["id"])
    if parked:
        run.event("tasks.waiting", "task", t["id"], {"tasks": parked, "cause": cause, "decision_id": decision_id},
                  actor="replacement_engine", correlation_id=t["id"])
    return parked


def _unpark(run, x: dict) -> None:
    x.update(status=x.pop("waiting_from"), waiting=None)
    run.save_task(x)


def _pending(run, kind: str, key: str, value: str) -> dict | None:
    return next((d for d in run.store.all("decision") if d["status"] == "pending" and d["kind"] == kind
                 and (d.get("extra") or {}).get(key) == value), None)


def _down_until(run, m: dict) -> float:
    return max((run.registry.get(m["id"]).get("health") or {}).get("down_until", 0), time.time() + 60)


def _kind_of(run, model_id: str, t: dict) -> str:
    return t.get("kind") or next((x["kind"] for x in run.tasks() if run.model_of(x["owner_worker_id"]) == model_id
                                  and x["status"] != "VERIFIED"), "objective")


def _outage(run, t: dict, m: dict, cause: str, exc) -> dict:
    """The provider's side: the AI is not at fault. A stand-in covers the wait when the CEO named a fallback for this
    AI or approved one; otherwise the work waits, and the CEO is asked once whether a stand-in may cover it."""
    policy = (run.store.get("outage_policy", m["id"]) or {}).get("answer")
    d = _pending(run, "provider_outage", "model_id", m["id"])
    if d is not None:
        _park(run, t, {m["id"]}, cause, d["id"], _down_until(run, m))
        return {"did": "waiting_on_ceo", "task": t["id"], "decision": d["id"], "cause": cause}
    kind = _kind_of(run, m["id"], t)
    fb = _fallback_of(run.registry, m["id"])
    if policy != "wait" and (fb or policy == "switch"):
        done = _stand_in(run, t, m, cause, fb, kind, "the fallback you named for it" if fb else "your approval")
        if done:
            return done
    if policy == "wait":
        _park(run, t, {m["id"]}, cause, None, _down_until(run, m))
        return {"did": "waiting", "task": t["id"], "model": m["id"], "cause": cause}
    _, rows = alternatives(run, t, [kind], {m["id"]}, f"{m['name']}: {PLAIN[cause]}")
    alt = rows[0] if rows else None
    waiting = sorted({people.label(w) for w in run.workers() if run.model_of(w["id"]) == m["id"]})
    if alt is None:
        _park(run, t, {m["id"]}, cause, None, _down_until(run, m))
        inform(run, "waiting_for_provider", worker_id=t.get("owner_worker_id") or "", task_id=t["id"],
               headline=f"{', '.join(waiting)} wait for {m['name']}: {PLAIN[cause]}",
               detail=f"The AI is not at fault, so nothing was replaced; no other AI is available to stand in. The "
                      f"work continues when {m['name']} answers again. The error: {str(exc)[:200]}")
        return {"did": "waiting", "task": t["id"], "model": m["id"], "cause": cause}
    before, after = _per_task(run, m["id"], kind), alt["expected_usd"]
    d = run.decision(
        "provider_outage", problem=f"{m['name']} stopped answering: {PLAIN[cause]}. The AI is not at fault, so "
        f"Cynqra has not replaced it. {', '.join(waiting)} wait; the rest of the team keeps working.",
        recommendation=f"Let {alt['model']} stand in until {m['name']} answers again; each worker then returns to "
                       f"its own AI. Reject to wait instead." + _cost_line(before, after, m["id"], alt["model_id"], run),
        risk="low", confidence="medium",
        cost=f"{budget.dollars(after)} a task on {alt['model']}"
             + (f" against {budget.dollars(before)}" if before is not None else ""),
        evidence=[f"{m['name']}: {str(exc)[:200]}"], change=f"{m['name']} answering again.", task_id=t["id"],
        source="replacement_engine", extra={"model_id": m["id"], "stand_in": alt["model_id"], "cause": cause})
    _park(run, t, {m["id"]}, cause, d["id"], _down_until(run, m))
    return {"did": "waiting_on_ceo", "task": t["id"], "decision": d["id"], "cause": cause}


def _stand_in(run, t: dict, m: dict, cause: str, pick: str | None, kind: str, authority: str) -> dict | None:
    """A stand-in for the time the AI is down: the fallback, or the best alternative that passes its regression
    check. Every worker on the down AI is bound to it for now; each returns to its own AI when it answers again."""
    reg, s = run.registry, project_settings.get(run.store)
    _, rows = alternatives(run, t, [kind], {m["id"]}, f"stand-in while {m['name']} is down")
    options = ([pick] if pick else []) + [r["model_id"] for r in rows if r["model_id"] != pick]
    tried = []
    for mid in options:
        check = regression_check(run.supply, mid, kind)
        if check.get("usd"):
            run.spend(t.get("owner_worker_id") or "platform", t["id"], check["usd"], "verification")
        tried.append({"model_id": mid, "regression": check["evidence"], "passed": check["passed"]})
        if not check["passed"]:
            continue
        _record(run, t, "stand_in", f"{m['name']}: {PLAIN[cause]}", rows,
                {"regression_check": check["evidence"], "tried": tried, "forced": True, "to_model": mid})
        before, after = _per_task(run, m["id"], kind), _per_task(run, mid, kind)
        moved = []
        for w in run.workers():
            if run.model_of(w["id"]) != m["id"]:
                continue
            binding.bind(run, w["id"], reg.get(mid), by="replacement_engine", candidates=rows, task_id=t["id"],
                         reason=f"stand-in while {m['name']} is down ({PLAIN[cause]}); it returns when {m['name']} "
                                "answers again")
            n = run.count("replacement") + 1
            rep = {"id": f"rep_{n:03d}", "task_id": t["id"], "worker_id": w["id"], "role": w["role"], "from": m["id"],
                   "to": mid, "reason": f"stand-in: {m['name']} {PLAIN[cause]}", "attempts": 0,
                   "usd_spent_by_previous": 0.0, "candidates": rows, "regression_check": check["evidence"],
                   "rerouted": False, "temporary": True, "active": True, "at": now(),
                   # the founder chose this: a fallback they named, or their approval (mandate 50)
                   "human_directed": True, "authority": authority,
                   "inherited": ["everything: the worker, its role, history and files are unchanged"]}
            run.store.put("replacement", rep["id"], rep)
            run.event("worker.stand_in", "worker", w["id"], {"from": m["id"], "to": mid, "cause": cause},
                      actor="replacement_engine", correlation_id=t["id"])
            moved.append(w.get("name") or w["title"])
        for x in run.tasks():
            if x["status"] == "WAITING" and m["id"] in x["waiting"].get("model_ids", []):
                _unpark(run, x)
        inform(run, "stand_in", worker_id=t.get("owner_worker_id") or "", task_id=t["id"], usd_before=before,
               usd_after=after, headline=f"A stand-in AI covers for {', '.join(moved)} while {m['name']} is down",
               detail=f"{m['name']} stopped answering: {PLAIN[cause]}. The AI is not at fault, so no one was "
                      f"replaced: {', '.join(moved)} stay in their seats. By {authority}, {reg.get(mid)['name']} "
                      f"covers the wait (it passed its check: {check['evidence']}); they return to {m['name']} when "
                      "it answers again."
                      + _cost_line(before, after, m["id"], mid, run))
        return {"did": "stand_in", "task": t["id"], "from": m["id"], "to": mid}
    return None


def _account(run, t: dict, m: dict, cause: str, exc) -> dict:
    """No credit, or the key is refused: the CEO's to fix. Every worker on that account waits; nothing is replaced,
    since another AI would not make the account work, and a paid one elsewhere is the CEO's choice."""
    conn = m.get("connection_id") or m["id"]
    on_account = {x["id"] for x in run.registry.models(include_retired=True) if (x.get("connection_id") or x["id"]) == conn}
    d = _pending(run, "provider_account", "connection_id", conn)
    if d is None:
        c = run.supply.connections.find_id(conn) if run.supply else None
        waiting = sorted({people.label(w) for w in run.workers() if run.model_of(w["id"]) in on_account})
        fix = ("Add credit to the account" if cause == "no_credit" else "Give Cynqra a key the provider accepts")
        d = run.decision(
            "provider_account", problem=f"{(c or {}).get('name') or m['name']}: {PLAIN[cause]}. No AI is at fault, so "
            f"nothing was replaced. {', '.join(waiting) or 'The team'} wait.",
            recommendation=f"{fix}, then approve: the waiting work continues where it stopped. Reject to stop the run.",
            risk="medium", confidence="high", cost="whatever the provider charges; nothing is spent while it waits",
            evidence=[f"{m['name']}: {str(exc)[:200]}"], change="The provider accepting calls again.", task_id=t["id"],
            source="replacement_engine", severity="SEV-2",
            extra={"connection_id": conn, "model_ids": sorted(on_account), "cause": cause})
    _park(run, t, on_account, cause, d["id"], 0)
    return {"did": "waiting_on_ceo", "task": t["id"], "decision": d["id"], "cause": cause}


def after_outage(run, d: dict, action: str) -> None:
    """The CEO's answer on an outage holds for the rest of the run: approve lets a stand-in cover it, reject waits."""
    mid = d["extra"]["model_id"]
    run.store.put("outage_policy", mid, {"id": mid, "answer": "switch" if action == "approve" else "wait",
                                         "decision_id": d["id"], "at": now()})
    m = run.registry.get(mid)
    parked = [x for x in run.tasks() if x["status"] == "WAITING" and x["waiting"].get("decision_id") == d["id"]]
    if action == "approve" and not run.registry.availability(m)[0] and parked:
        if _stand_in(run, parked[0], m, d["extra"]["cause"], d["extra"].get("stand_in"), parked[0]["kind"],
                     "your approval"):
            return
    for x in parked:  # wait until the provider is expected back, then try again
        x["waiting"].update(decision_id=None, until=_down_until(run, m))
        run.save_task(x)


def after_account(run, d: dict, action: str) -> None:
    parked = [x for x in run.tasks() if x["status"] == "WAITING" and x["waiting"].get("decision_id") == d["id"]]
    if action != "approve":
        run.set_meta(phase="stopped", notice=f"Run stopped by the CEO: {PLAIN[d['extra']['cause']]}.")
        return
    for mid in d["extra"]["model_ids"]:
        run.registry.clear_health(mid)
    for x in parked:
        _unpark(run, x)


def resume_waiting(run) -> None:
    """Each round: work that waited for a provider tries again once the wait is over, and a worker covered by a
    stand-in returns to its own AI once that AI is available again."""
    reg = run.registry

    def answering(mid: str) -> bool:  # a call succeeded since it failed: its failed-call count is back to zero
        try:
            m = reg.get(mid)
        except Exception:  # noqa: BLE001
            return False
        return reg.availability(m)[0] and not (m.get("health") or {}).get("errors")

    for x in run.tasks():
        if x["status"] != "WAITING" or x["waiting"].get("decision_id"):
            continue
        if time.time() >= x["waiting"]["until"] or all(answering(mid) for mid in x["waiting"].get("model_ids") or []):
            _unpark(run, x)
    for rep in run.store.all("replacement"):
        if not rep.get("temporary") or not rep.get("active"):
            continue
        try:
            back = reg.availability(reg.get(rep["from"]))[0]
        except Exception:  # noqa: BLE001 - the original was removed: the stand-in stays, as a replacement
            rep.update(active=False, temporary=False)
            run.store.put("replacement", rep["id"], rep)
            if run.model_of(rep["worker_id"]) == rep["to"]:  # a new person takes the seat for good
                why = "their AI was removed while a stand-in covered for them"
                left, joined = people.replace(run, rep["worker_id"], why, rep["from"], rep["to"])
                w = run.worker(rep["worker_id"])
                inform(run, "intelligence_replaced", worker_id=rep["worker_id"], task_id=rep.get("task_id"),
                       headline=f"{left} was replaced as your AI {people.seat(w)} by {joined}",
                       detail=f"Why: {why}. {joined} works on {_name(run, rep['to'])}, the stand-in that passed its "
                              "check. The seat keeps its work and history.")
            continue
        if not back:
            continue
        rep["active"] = False
        run.store.put("replacement", rep["id"], rep)
        if run.model_of(rep["worker_id"]) == rep["to"]:
            binding.bind(run, rep["worker_id"], reg.get(rep["from"]), by="replacement_engine",
                         reason=f"back on its own AI: {reg.get(rep['from'])['name']} answers again")
            run.event("worker.returned", "worker", rep["worker_id"], {"from": rep["to"], "to": rep["from"]},
                      actor="replacement_engine")


def version_changed(run, worker_id: str, exc, task_id: str | None = None) -> None:
    """The intelligence a worker is bound to reports a new version. It continues only after its regression check on
    the worker's kind of work passes; the binding then pins the new version. A failed check makes the intelligence
    unavailable, and the call fails like any model error, so the worker is rebound."""
    reg = run.registry
    entry = reg.get(exc.model_id)
    open_tasks = [x for x in run.tasks() if x["owner_worker_id"] == worker_id and x["status"] != "VERIFIED"]
    kind = open_tasks[0]["kind"] if open_tasks else "objective"
    check = regression_check(run.supply, exc.model_id, kind)
    if check.get("usd"):
        run.spend(worker_id, open_tasks[0]["id"] if open_tasks else "objective", check["usd"], "verification")
    run.event("intelligence.version_changed", "worker", worker_id, {"intelligence_id": exc.model_id,
              "from": exc.pinned, "to": exc.current, "regression_check": check["evidence"], "passed": check["passed"]},
              actor="replacement_engine")
    if not check["passed"]:
        reg.set_regression(exc.model_id, False, f"version {exc.current}: {check['evidence']}")
        raise IntelligenceError(f"{entry['name']} changed version to {exc.current or 'unversioned'} and failed its "
                                f"regression check ({check['evidence']})", model_id=exc.model_id)
    why = (f"version {exc.pinned or 'unversioned'} to {exc.current or 'unversioned'}, regression check passed: "
           f"{check['evidence']}")
    if (binding.current(run.store, worker_id) or {}).get("intelligence_id") == exc.model_id:
        binding.bind(run, worker_id, entry, by="replacement_engine", reason=why)
    tb = binding.task_binding(run.store, task_id) if task_id else None
    if tb and tb["intelligence_id"] == exc.model_id and tb.get("version") != served_version(entry):
        binding.bind_task(run, task_id, tb["worker_id"], entry, reason=why, by="replacement_engine")
