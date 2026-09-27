"""The Performance Engine: how well each worker, on each model it has run on, is performing.

Product definition, Stage 10. Intelligence is measured at the worker and task level, on the work itself:

  quality          acceptance rate, test pass rate, defect escape
  reliability      failure rate of its calls, protocol violations, tool errors
  efficiency       latency, retries, tokens per verified outcome
  economics        cost per verified task
  capability fit   the model's result on Cynqra's role/workload benchmark (probe and regression work)
  stability        the model version's regression gate, and the worker's record on its previous model
  human friction   escalations and founder rejections its work caused

A scorecard is kept per worker and per (worker, model): the worker's identity is stable, the intelligence under it
can change, and each intelligence is judged on what it did while it was there. thresholds() says when the
Replacement Engine must look at the alternatives.
"""
from __future__ import annotations

THRESHOLDS = {
    "min_verifications": 2,     # judge quality only after this many verifications on this worker and model
    "acceptance_rate": 0.5,     # below this, alternatives are evaluated
    "protocol_violations": 3,   # invalid protocol objects in this run
    "min_calls": 2,
    "failure_rate": 0.5,        # failed calls / calls
    "cost_vs_forecast": 3.0,    # cost per verified task over this multiple of the forecast per task
}


def _rate(a, b):
    return round(a / b, 3) if b else None


def scorecard(store, worker_id: str, model_id: str | None, reg=None) -> dict:
    """Signals for one worker on one model (model_id None: across every model it ran on)."""
    tasks = {t["id"]: t for t in store.all("task")}
    mine = lambda r: r.get("worker_id") == worker_id and (model_id is None or r.get("model_id") == model_id)  # noqa: E731
    ver = [v for v in store.all("verification") if mine(v) and v.get("reviewer_type") == "service"]
    passed = [v for v in ver if v["verdict"] == "VERIFIED"]
    code = [v for v in ver if (tasks.get(v["task_id"]) or {}).get("kind") == "code"]
    calls = [c for c in store.all("call") if c.get("worker") == worker_id
             and (model_id is None or c.get("model_id") == model_id)]
    errors = [c for c in store.all("call_error") if mine(c)]
    violations = [x for x in store.all("violation") if mine(x)]
    denied = [a for a in store.all("action") if a.get("worker_id") == worker_id and a.get("status") == "denied"
              and (model_id is None or a.get("model_id") == model_id)]
    escapes = [x for x in store.all("escape") if mine(x)]
    false_rej = [v for v in ver if v.get("false_rejection")]
    tokens = sum(int(c.get("tokens_in") or 0) + int(c.get("tokens_out") or 0) for c in calls)
    usd = sum(float(c.get("usd") or 0) for c in calls)
    verified_tasks = {v["task_id"] for v in passed}
    decisions = store.all("decision")
    esc = [d for d in decisions if d["kind"] == "escalation" and d.get("source") == worker_id]
    rej = [d for d in decisions if d.get("source") == worker_id and d["status"] == "rejected"]
    card = {
        "worker_id": worker_id, "model_id": model_id,
        "quality": {"verifications": len(ver), "acceptance_rate": _rate(len(passed), len(ver)),
                    "test_pass_rate": _rate(sum(1 for v in code if v["verdict"] == "VERIFIED"), len(code)),
                    "defect_escapes": len(escapes), "false_rejections": len(false_rej)},
        "reliability": {"calls": len(calls), "failed_calls": len(errors),
                        "failure_rate": _rate(len(errors), len(calls) + len(errors)),
                        "protocol_violations": len(violations), "tool_errors": len(denied)},
        "efficiency": {"latency_s": round(sum(float(c.get("latency_s") or 0) for c in calls) / len(calls), 1) if calls else None,
                       "retries": len(ver) - len(passed),
                       "tokens_per_verified": round(tokens / len(verified_tasks)) if verified_tasks else None},
        "economics": {"usd": round(usd, 4),
                      "usd_per_verified": round(usd / len(verified_tasks), 4) if verified_tasks else None},
        "human_friction": {"escalations": len(esc), "rejections": len(rej)},
    }
    if reg is not None and model_id:
        try:
            m = reg.get(model_id)
            prof = reg.profile(model_id)
            bench = prof.get("benchmark") or {}
            att = sum(b["attempts"] for b in bench.values())
            card["capability_fit"] = {"benchmark_attempts": att,
                                      "benchmark_pass_rate": _rate(sum(b["verified"] for b in bench.values()), att)}
            card["stability"] = {"version": m.get("version") or "",
                                 "regression": (m.get("regression") or {}).get("status", "unverified"),
                                 "by_version": prof.get("by_version")}
        except Exception:  # noqa: BLE001 - a removed model still has a scorecard, without registry facts
            card["capability_fit"] = card["stability"] = None
    return card


def below(card: dict, forecast_per_task: float | None = None, t: dict | None = None) -> list[str]:
    """The thresholds this worker-and-model has crossed, as reasons. Empty: keep it."""
    t = {**THRESHOLDS, **(t or {})}
    q, r, e = card["quality"], card["reliability"], card["economics"]
    out = []
    if q["verifications"] >= t["min_verifications"] and (q["acceptance_rate"] or 0) < t["acceptance_rate"]:
        out.append(f"acceptance rate {q['acceptance_rate']} over {q['verifications']} verifications, under "
                   f"{t['acceptance_rate']}")
    if r["protocol_violations"] >= t["protocol_violations"]:
        out.append(f"{r['protocol_violations']} protocol violations")
    if r["calls"] + r["failed_calls"] >= t["min_calls"] and (r["failure_rate"] or 0) >= t["failure_rate"]:
        out.append(f"{r['failed_calls']} of {r['calls'] + r['failed_calls']} calls failed")
    if forecast_per_task and e["usd_per_verified"] and e["usd_per_verified"] > t["cost_vs_forecast"] * forecast_per_task:
        out.append(f"${e['usd_per_verified']} per verified task, over {t['cost_vs_forecast']}x the forecast "
                   f"${forecast_per_task:.4f}")
    return out


def all_cards(store, reg=None) -> list[dict]:
    """Every worker: its card across models, and one per model it ran on, current model first."""
    out = []
    for w in store.all("worker"):
        models = [w.get("model_id")] if w.get("model_id") else []
        for v in store.all("verification") + store.all("call"):
            mid = v.get("model_id")
            if (v.get("worker_id") or v.get("worker")) == w["id"] and mid and mid not in models:
                models.append(mid)
        out.append({"worker_id": w["id"], "title": w.get("title"), "role": w.get("role"), "model_id": w.get("model_id"),
                    "overall": scorecard(store, w["id"], None, None),
                    "by_model": [scorecard(store, w["id"], m, reg) for m in models]})
    return out
