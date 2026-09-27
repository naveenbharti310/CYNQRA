"""The Budget Engine: what the approved organization and its roadmap will cost, and what they did cost.

Product definition, Stage 7. The budget is money, not work units, built in layers and reconciled against actuals:

  inference        each task's expected model cost on its owner's model (workforce.estimate: measured cost per
                   attempt times the expected attempts), plus the coordination calls around it (the Handoff that
                   assigns it, Blocker answers)
  tools            tool time the workers use (their own test runs), at the price of this machine's time
  infrastructure   hosting the deployed product for the plan's days
  verification     the Verification Service's runs, at the price of this machine's time
  reserve          what is left of the cap: the contingency for rework, retries and replacements
  total            the sum, against the founder's hard cap

Every line says what it is based on. Views by worker, workstream and milestone are the same money cut differently.
A run on the scripted demo has no model and no money: its lines are zero and say so, and the work-unit budget
of each task is shown beside them.
"""
from __future__ import annotations

from .workforce import Workforce, estimate

VERIFY_S_DEFAULT = {"code": 20.0, "spec": 1.0, "decision": 0.0, "review_merge": 30.0, "deploy": 30.0}
SELF_CHECKS = 2


def measured_verify_seconds(store) -> dict[str, float]:
    """Mean seconds of this run's verifications per kind of task, where there are any."""
    tasks = {t["id"]: t for t in store.all("task")}
    by: dict[str, list[float]] = {}
    for v in store.all("verification"):
        k = (tasks.get(v["task_id"]) or {}).get("kind")
        if k and v.get("seconds") is not None:
            by.setdefault(k, []).append(float(v["seconds"]))
    return {k: sum(x) / len(x) for k, x in by.items()}


def construct(store, tasks: list[dict], workers: list[dict], reg=None, assigner: str | None = None) -> dict:
    """The forecast for a roadmap. reg is the model registry for a run staffed from it, else None (scripted)."""
    s = Workforce.settings(store)
    rate = float(s["compute_usd_per_hour"]) / 3600
    wmodel = {w["id"]: w.get("model_id") for w in workers}
    vsec = {**VERIFY_S_DEFAULT, **measured_verify_seconds(store)}
    rows = []
    for t in tasks:
        row = {"task_id": t["id"], "owner": t["owner_worker_id"], "workstream": t.get("workstream_id"),
               "milestone": t.get("milestone_id"), "kind": t["kind"], "units": int(t.get("budget") or 0),
               "inference": 0.0, "coordination": 0.0, "tools": 0.0, "verification": 0.0, "minutes": 0.0,
               "tokens": 0, "attempts": 1.0, "basis": "scripted demo: no model, no money"}
        if reg is not None and wmodel.get(t["owner_worker_id"]):
            e = estimate(reg, reg.get(wmodel[t["owner_worker_id"]]), t["kind"], s["time_value_per_hour"])
            row.update(inference=e["expected_usd"], minutes=e["expected_minutes"], tokens=e["expected_tokens"],
                       attempts=e["expected_attempts"], basis=e["basis"], model_id=e["model_id"], p_task=e["p_task"])
            if assigner and t["owner_worker_id"] != assigner and wmodel.get(assigner):
                a = estimate(reg, reg.get(wmodel[assigner]), "assign", s["time_value_per_hour"])
                row["coordination"] = a["usd_per_attempt"]
        checks = SELF_CHECKS if t["kind"] == "code" else 0
        row["tools"] = round(checks * vsec.get(t["kind"], 0.0) * row["attempts"] * rate, 6)
        row["verification"] = round(vsec.get(t["kind"], 0.0) * row["attempts"] * rate, 6)
        rows.append(row)
    days = max([int(t.get("deadline_day") or 1) for t in tasks] or [1])
    layers = {
        "inference": {"usd": round(sum(r["inference"] + r["coordination"] for r in rows), 4),
                      "basis": "each task's expected attempts on its owner's model, measured cost per attempt"
                               if reg is not None else "scripted demo: no model cost"},
        "tools": {"usd": round(sum(r["tools"] for r in rows), 4),
                  "basis": f"workers' own test runs at ${s['compute_usd_per_hour']}/h of this machine"},
        "infrastructure": {"usd": round(days * float(s["infra_usd_per_day"]), 4),
                           "basis": f"{days} day(s) at ${s['infra_usd_per_day']}/day; the POC deploys to a process "
                                    "on this machine"},
        "verification": {"usd": round(sum(r["verification"] for r in rows), 4),
                         "basis": f"Verification Service runs at ${s['compute_usd_per_hour']}/h of this machine"},
    }
    subtotal = round(sum(v["usd"] for v in layers.values()), 4)
    cap = float(s["budget_usd"])
    reserve = round(cap - subtotal, 4)
    layers["reserve"] = {"usd": reserve, "basis": "the rest of the cap: rework, retries and replacements"}
    warnings = []
    if reserve < 0:
        warnings.append(f"The forecast is ${-reserve:.4f} over the ${cap:.2f} cap.")
    elif subtotal and reserve < float(s["reserve_min_pct"]) * subtotal:
        warnings.append(f"The reserve is under {int(100 * float(s['reserve_min_pct']))}% of the forecast.")

    def view(key):
        out: dict[str, dict] = {}
        for r in rows:
            v = out.setdefault(r[key] or "none", {"usd": 0.0, "units": 0, "minutes": 0.0, "tasks": []})
            v["usd"] = round(v["usd"] + r["inference"] + r["coordination"] + r["tools"] + r["verification"], 4)
            v["units"] += r["units"]
            v["minutes"] = round(v["minutes"] + r["minutes"], 1)
            v["tasks"].append(r["task_id"])
        return out
    return {"cap_usd": cap, "subtotal_usd": subtotal, "total_usd": round(subtotal + max(reserve, 0.0), 4),
            "reserve_usd": reserve, "fits": reserve >= 0, "warnings": warnings, "layers": layers, "tasks": rows,
            "by_worker": view("owner"), "by_workstream": view("workstream"), "by_milestone": view("milestone"),
            "units_total": sum(r["units"] for r in rows), "priced": reg is not None}


def actual(store, forecast: dict | None) -> dict:
    """What was spent, in the same layers, beside the forecast: the reconciliation the founder sees."""
    s = Workforce.settings(store)
    rate = float(s["compute_usd_per_hour"]) / 3600
    L = Workforce.ledger(store)
    vsec = sum(float(v.get("seconds") or 0) for v in store.all("verification"))
    tsec = sum(float((a.get("result") or {}).get("seconds") or 0) for a in store.all("action")
               if a.get("action_type") == "run_tests")
    meta = store.get("meta", "run") or {}
    days = 0.0
    if meta.get("started_at"):
        import time
        days = max(0.0, ((meta.get("delivered_at") or time.time()) - meta["started_at"]) / 86400)
    got = {"inference": round(L.get("spent_total", 0.0), 4), "tools": round(tsec * rate, 4),
           "infrastructure": round(days * float(s["infra_usd_per_day"]), 4), "verification": round(vsec * rate, 4)}
    f = (forecast or {}).get("layers") or {}
    rows = {k: {"forecast": (f.get(k) or {}).get("usd", 0.0), "actual": v,
                "variance": round(v - (f.get(k) or {}).get("usd", 0.0), 4)} for k, v in got.items()}
    total = round(sum(got.values()), 4)
    by_worker = {}
    for wid, fw in ((forecast or {}).get("by_worker") or {}).items():
        by_worker[wid] = {"forecast": fw["usd"], "actual": round((L.get("by_worker", {}).get(wid) or {}).get("spent", 0.0), 4)}
    for wid, w in (L.get("by_worker") or {}).items():
        by_worker.setdefault(wid, {"forecast": 0.0, "actual": round(w.get("spent", 0.0), 4)})
    return {"layers": rows, "total_forecast": (forecast or {}).get("subtotal_usd", 0.0), "total_actual": total,
            "cap_usd": float(s["budget_usd"]), "left_usd": round(float(s["budget_usd"]) - total, 4),
            "by_worker": by_worker, "verification_seconds": round(vsec, 1), "tool_seconds": round(tsec, 1)}
