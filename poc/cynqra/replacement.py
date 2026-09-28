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
  replace   the worker is bound to another intelligence; its identity, role, authority, history and workspace
            stay (binding.py keeps the previous binding in its history)

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

import re
import shutil
import time

from . import binding, budget, performance, roles
from . import settings as project_settings
from .db import now
from .intelligence import IntelligenceError
from .intelligence_layer import router
from .probe import regression_check

MAX_REPLACEMENTS = 2  # intelligence changes per task before the founder decides

# Why a call failed. The provider's HTTP status says it best ("HTTP 402 from provider: ..."); the words of the
# message are read only when there is no status, and only as whole phrases, so a port number such as :40312 or a
# local "insufficient memory" is never mistaken for a refused key or an empty account. Anything unrecognised counts
# as the provider's side, the cautious reading: waiting costs time, replacing a capable AI costs its record.
_STATUS = re.compile(r"\bHTTP (\d{3})\b")
_CREDIT = re.compile(r"credits?\b|billing|payment required|insufficient[_ ](quota|credit|balance|funds)", re.I)
PHRASES = (
    ("no_credit", _CREDIT),
    ("access", re.compile(r"invalid api key|unauthori[sz]ed|forbidden|authentication|is not set\b|"
                          r"credential is missing|stored key is missing", re.I)),
    ("rate_limit", re.compile(r"rate limit|too many requests", re.I)),
    ("timeout", re.compile(r"timed out|\btimeout\b", re.I)),
    ("withdrawn", re.compile(r"\bretired\b|connection was removed|regression check", re.I)),
)
PLAIN = {"outage": "its provider is not answering", "timeout": "its provider took too long to answer",
         "rate_limit": "its provider is limiting how often it may be called",
         "no_credit": "the provider account has no credit left", "access": "the provider refused the key",
         "withdrawn": "it can no longer be used"}
PROVIDER_SIDE = ("outage", "timeout", "rate_limit")
ACCOUNT = ("no_credit", "access")
WORK_STATES = ("PLANNED", "ASSIGNED", "REWORK", "BLOCKED")


def diagnose(error: str) -> str:
    """Why a call failed: outage, timeout, rate_limit, no_credit, access, or withdrawn (the AI can no longer be used).
    None of these says the AI cannot do the work; that is known only from its work (verification, cut-offs,
    protocol violations, its measured record)."""
    e = error or ""
    m = _STATUS.search(e)
    if m:
        code = int(m.group(1))
        if code == 402 or (code == 429 and _CREDIT.search(e)):  # an empty account can answer 429 too
            return "no_credit"
        if code in (401, 403):
            return "access"
        if code == 404:  # the provider no longer serves this model
            return "withdrawn"
        if code == 429:
            return "rate_limit"
        if code in (408, 504):
            return "timeout"
        return "outage"
    for cause, pattern in PHRASES:
        if pattern.search(e):
            return cause
    return "outage"


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
        return out + f" Expected cost of a verified task: ${after:.4f}."
    d = after - before
    how = "more" if d > 1e-9 else "less" if d < -1e-9 else "the same"
    return (out + f" Expected cost of a verified task: ${after:.4f} against ${before:.4f} before"
            + (f" (${abs(d):.4f} {how})." if how != "the same" else ", the same."))


def inform(run, kind: str, *, worker_id: str, task_id: str | None, headline: str, detail: str,
           usd_before: float | None = None, usd_after: float | None = None) -> dict:
    """Tell the CEO what Cynqra changed and why. Not a decision: nothing waits on it, and it is not counted as the
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


def evaluate(run, t: dict, why: str, forced: bool) -> dict:
    """Decide keep, reroute or replace for the worker that owns t. Returns the step's result."""
    if t.get("replacements", 0) >= MAX_REPLACEMENTS:
        return run.escalate(t, why + " It has already had its intelligence changes.") if forced \
            else {"did": "kept", "task": t["id"]}
    reg, s = run.registry, project_settings.get(run.store)
    wid = t["owner_worker_id"]
    w = run.worker(wid)
    old = run.model_of(wid)
    left = budget.left_for(run.store, t["id"])
    _, rows = router.choose(reg, s, [t["kind"]], budget_left=left, exclude={old})
    try:
        current = router.estimate(reg, reg.get(old), t["kind"], s["time_value_per_hour"])
    except Exception:  # noqa: BLE001 - a removed model has no estimate: any alternative is better
        current = None
    options = []  # (score, action, payload); a reroute first among equals, it changes no intelligence
    peers = []
    for p in run.workers():
        pm = run.model_of(p["id"])
        if p["id"] == wid or p["role"] != w["role"] or not pm or pm == old:
            continue
        m = reg.get(pm)
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
    fallback = _fallback_of(reg, old)
    if forced and fallback:  # the failing intelligence names its fallback: that is tried first
        options.sort(key=lambda o: o[2] != "replace" or o[3]["model_id"] != fallback)
    if not forced:  # evidence-triggered: change only when an alternative is expected to do better
        options = [o for o in options if current is None or o[0] < current["score"]]
    tried = []
    for _, _, action, payload in options:
        model_id = payload["model_id"] if action == "replace" else run.model_of(payload["id"])
        check = regression_check(run.supply, model_id, t["kind"])
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


def _fallback_of(reg, model_id: str | None) -> str | None:
    try:
        fb = reg.get(model_id).get("fallback_id") if model_id else None
        return fb if fb and reg.availability(reg.get(fb))[0] else None
    except Exception:  # noqa: BLE001 - a removed intelligence has no fallback
        return None


def _swap(run, t: dict, best: dict, rows: list, why: str, regression: str) -> dict:
    wid = t["owner_worker_id"]
    w = run.worker(wid)
    old = run.model_of(wid)
    reg = run.registry
    spent = budget.ledger(run.store)["spent"].get(t["id"], 0.0)
    prior = [o for o in reg.outcomes(old) if o["run_id"] == run.cid and o["task_id"] == t["id"]]
    binding.bind(run, wid, reg.get(best["model_id"]), reason=why, by="replacement_engine", candidates=rows,
                 task_id=t["id"])
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
    before, after = _per_task(run, old, t["kind"]), e["expected_usd"]
    inform(run, "intelligence_replaced", worker_id=wid, task_id=t["id"], usd_before=before, usd_after=after,
           headline=f"{w['title']} now works on {reg.get(best['model_id'])['name']}, in place of {_name(run, old)}",
           detail=f"Why: {why[:300]} It is not the provider's side: the AI could not do this role's work. "
                  f"{reg.get(best['model_id'])['name']} passed its check first ({regression}). The worker keeps its "
                  f"role, history and files." + _cost_line(before, after, old, best["model_id"], run))
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
           "from": run.model_of(frm), "to": run.model_of(peer["id"]), "reason": why[:400], "attempts": t["attempts"],
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
    before, after = _per_task(run, rep["from"], t["kind"]), _per_task(run, rep["to"], t["kind"])
    inform(run, "task_rerouted", worker_id=frm, task_id=t["id"], usd_before=before, usd_after=after,
           headline=f"{t['title']} moved from {(run.worker(frm) or {}).get('title', frm)} to {peer['title']}",
           detail=f"Why: {why[:300]} {peer['title']} works on {_name(run, rep['to'])}, which passed its check on "
                  "this kind of work; both keep their roles." + _cost_line(before, after, rep["from"], rep["to"], run))
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
    """A call to a model failed. First, why: the provider's side and the account are not the AI's fault, so the
    worker waits (or a stand-in covers the wait) and nothing is replaced. Only an AI that can no longer be used is
    replaced here; one that cannot do the work is found from its work (execution.py, check_thresholds)."""
    if not exc.model_id:
        return None
    cause = diagnose(str(exc))
    involved = [t.get("owner_worker_id"), run.assigner_id(), (t.get("blocker") or {}).get("needs_from")]
    caller = next((w for w in involved if w and run.model_of(w) == exc.model_id), t.get("owner_worker_id"))
    n = run.count("call_error") + 1
    run.store.put("call_error", f"ce_{n:04d}", {"id": f"ce_{n:04d}", "worker_id": caller, "model_id": exc.model_id,
                                                "task_id": t.get("id"), "error": str(exc)[:300], "cause": cause,
                                                "at": now()})
    reg = run.registry
    reg.record_call(exc.model_id, role="", purpose="error", task_kind=t.get("kind", ""), usage=exc.usage, run_id=run.cid,
                    error=str(exc))
    m = reg.get(exc.model_id)
    run.event("worker.stopped", "worker", caller or "", {"task_id": t.get("id"), "intelligence_id": m["id"],
              "cause": cause, "why": PLAIN[cause], "error": str(exc)[:200]}, actor="replacement_engine",
              correlation_id=t.get("id"))
    if cause == "withdrawn":
        return _withdrawn(run, t, m, exc)
    if cause in ACCOUNT:
        return _account(run, t, m, cause, exc)
    if reg.availability(m)[0]:
        return {"did": "model_error_retry", "task": t["id"], "model": exc.model_id, "cause": cause, "why": str(exc)}
    return _outage(run, t, m, cause, exc)


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
            best, rows = router.choose(reg, s, roles.staffing_kinds(w["role"]), exclude={m["id"]})
            fb = _fallback_of(reg, m["id"])
            pick = next((r for r in rows if r["model_id"] == fb), None) if fb else None
            pick = pick or best
            if pick:
                binding.bind(run, w["id"], reg.get(pick["model_id"]), reason=f"{m['name']} {PLAIN['withdrawn']}",
                             by="intelligence_router", candidates=rows)
                inform(run, "intelligence_replaced", worker_id=w["id"], task_id=None,
                       headline=f"{w['title']} now works on {pick['model']}, in place of {m['name']}",
                       detail=f"{m['name']} {PLAIN['withdrawn']} ({str(exc)[:200]}).")
    # the control plane's own binding is chosen again on its next call, since its intelligence is unavailable
    return out or {"did": "model_replaced", "task": t["id"], "model": m["id"]}


def _actor(t: dict) -> str:
    return {"PLANNED": t.get("handoff_from"), "ASSIGNED": t["owner_worker_id"], "REWORK": t["owner_worker_id"],
            "BLOCKED": (t.get("blocker") or {}).get("needs_from")}.get(t["status"]) or ""


def _park(run, t: dict, model_ids: set, cause: str, decision_id: str | None, until: float) -> list[str]:
    """The failing task, and every task whose next move is by a worker on these intelligences, wait."""
    parked = []
    for x in run.tasks():
        if x["id"] != t["id"] and not (x["status"] in WORK_STATES and run.model_of(_actor(x)) in model_ids):
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
    s = project_settings.get(run.store)
    _, rows = router.choose(run.registry, s, [kind], exclude={m["id"]})
    alt = rows[0] if rows else None
    waiting = sorted({w["title"] for w in run.workers() if run.model_of(w["id"]) == m["id"]})
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
        cost=f"${after:.4f} a task on {alt['model']}" + (f" against ${before:.4f}" if before is not None else ""),
        evidence=[f"{m['name']}: {str(exc)[:200]}"], change=f"{m['name']} answering again.", task_id=t["id"],
        source="replacement_engine", extra={"model_id": m["id"], "stand_in": alt["model_id"], "cause": cause})
    _park(run, t, {m["id"]}, cause, d["id"], _down_until(run, m))
    return {"did": "waiting_on_ceo", "task": t["id"], "decision": d["id"], "cause": cause}


def _stand_in(run, t: dict, m: dict, cause: str, pick: str | None, kind: str, authority: str) -> dict | None:
    """A stand-in for the time the AI is down: the fallback, or the best alternative that passes its regression
    check. Every worker on the down AI is bound to it for now; each returns to its own AI when it answers again."""
    reg, s = run.registry, project_settings.get(run.store)
    _, rows = router.choose(reg, s, [kind], exclude={m["id"]})
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
                   "inherited": ["everything: the worker, its role, history and files are unchanged"]}
            run.store.put("replacement", rep["id"], rep)
            run.event("worker.stand_in", "worker", w["id"], {"from": m["id"], "to": mid, "cause": cause},
                      actor="replacement_engine", correlation_id=t["id"])
            moved.append(w["title"])
        for x in run.tasks():
            if x["status"] == "WAITING" and m["id"] in x["waiting"].get("model_ids", []):
                _unpark(run, x)
        inform(run, "stand_in", worker_id=t.get("owner_worker_id") or "", task_id=t["id"], usd_before=before,
               usd_after=after, headline=f"{reg.get(mid)['name']} stands in for {m['name']} ({', '.join(moved)})",
               detail=f"{m['name']} stopped answering: {PLAIN[cause]}. The AI is not at fault and was not replaced. "
                      f"By {authority}, {reg.get(mid)['name']} covers the wait (it passed its check: "
                      f"{check['evidence']}); each worker returns to {m['name']} when it answers again."
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
        waiting = sorted({w["title"] for w in run.workers() if run.model_of(w["id"]) in on_account})
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
            back = False
        if not back:
            continue
        rep["active"] = False
        run.store.put("replacement", rep["id"], rep)
        if run.model_of(rep["worker_id"]) == rep["to"]:
            binding.bind(run, rep["worker_id"], reg.get(rep["from"]), by="replacement_engine",
                         reason=f"back on its own AI: {reg.get(rep['from'])['name']} answers again")
            run.event("worker.returned", "worker", rep["worker_id"], {"from": rep["to"], "to": rep["from"]},
                      actor="replacement_engine")


def version_changed(run, worker_id: str, exc) -> None:
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
    binding.bind(run, worker_id, entry, by="replacement_engine",
                 reason=f"version {exc.pinned or 'unversioned'} to {exc.current or 'unversioned'}, regression check "
                        f"passed: {check['evidence']}")
