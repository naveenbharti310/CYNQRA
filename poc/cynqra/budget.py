"""The Budget Engine: the project's money. One currency, US dollars, from the forecast to the hard stop.

Product definition, Stage 7. The budget is built in layers from the approved roadmap and reconciled against what
is actually spent:

  inference        each task's expected model cost on its owner's model (router.estimate: measured cost per attempt
                   times the expected attempts), plus the Handoff and the review by the cofounder who leads it
  tools            the workers' own test runs, at the price of this machine's time
  infrastructure   hosting the deployed product for the plan's days
  verification     the Verification Service's runs and the regression checks of replacement models
  reserve          what is left of the cap: the contingency for rework, retries and replacements
  total            against the founder's hard cap

Every dollar spent is charged to a worker, a task and a layer in the ledger. A task past its allocation draws on
the reserve; a replacement releases the failing model's unspent allocation and draws the successor's expected
cost. When spending reaches the cap the breaker opens and all work pauses until the founder raises the cap or
stops the run. Every line says what it is based on.
"""
from __future__ import annotations

import time

from . import roles
from .binding import intelligence_of
from . import settings as project_settings
from .intelligence_layer.router import estimate

LAYERS = ("inference", "tools", "infrastructure", "verification")
WARN_AT = (50, 80, 95)  # percent of the cap
VERIFY_S_DEFAULT = {"document": 1.0, "decision": 0.0, "code": 20.0, "forecast": 25.0, "review_merge": 30.0,
                    "deploy": 30.0}


def dollars(v: float) -> str:
    """Dollars as the founder reads them: cents as usual; a fraction of a cent (one AI call can cost that) keeps four
    places."""
    a = abs(float(v))
    return f"${float(v):.{4 if 0 < a < 0.01 else 2}f}"


def ledger(store) -> dict:
    return store.get("budget", "ledger") or {
        "allocated": {}, "spent": {}, "by_worker": {}, "by_layer": {k: 0.0 for k in LAYERS}, "reserve": 0.0,
        "spent_total": 0.0, "state": "ok", "warned": [], "events": [], "reservations": {}}


def _save(store, L: dict) -> dict:
    store.put("budget", "ledger", L)
    return L


def machine_usd(store, seconds: float) -> float:
    return round(float(seconds) * float(project_settings.get(store)["compute_usd_per_hour"]) / 3600, 6)


def charge(store, worker_id: str, task_id: str, usd: float, layer: str) -> dict:
    """Charge money to a worker, a task and a layer. Returns what crossed: warnings (percent marks) and whether the
    breaker must open now. One transaction: concurrent workers' charges never overwrite one another."""
    if layer not in LAYERS:
        raise ValueError(f"unknown budget layer {layer}")
    out = {"warned": [], "breaker": False}
    if usd <= 0:
        return out
    with store.atomic():
        return _charge(store, worker_id, task_id, usd, layer, out)


def _charge(store, worker_id: str, task_id: str, usd: float, layer: str, out: dict) -> dict:
    L = ledger(store)
    L["spent"][task_id] = round(L["spent"].get(task_id, 0.0) + usd, 6)
    w = L["by_worker"].setdefault(worker_id, {"allocated": 0.0, "spent": 0.0})
    w["spent"] = round(w["spent"] + usd, 6)
    L["by_layer"][layer] = round(L["by_layer"].get(layer, 0.0) + usd, 6)
    L["spent_total"] = round(L["spent_total"] + usd, 6)
    over = L["spent"][task_id] - L["allocated"].get(task_id, 0.0)
    if over > 0 and task_id in L["allocated"]:  # past its allocation: the task draws on the reserve
        L["reserve"] = round(L["reserve"] - min(over, usd), 6)
    cap = float(project_settings.get(store)["budget_usd"])
    pct = 100 * L["spent_total"] / cap if cap else 100
    for mark in WARN_AT:
        if pct >= mark and mark not in L["warned"]:
            L["warned"].append(mark)
            out["warned"].append(mark)
    if L["spent_total"] >= cap and L["state"] != "breaker":
        L["state"] = "breaker"
        out["breaker"] = True
    _save(store, L)
    return out


# --- reservations: in-flight spend counts before it is spent (mandate 19) ---------------------------------------------
def reserved_total(L: dict) -> float:
    return round(sum(float(r["usd"]) for r in (L.get("reservations") or {}).values()), 6)


def headroom(store) -> dict:
    """What may still be committed: the cap less what is spent and what in-flight work has reserved."""
    L = ledger(store)
    cap = float(project_settings.get(store)["budget_usd"])
    res = reserved_total(L)
    return {"cap": cap, "spent": round(L["spent_total"], 6), "reserved": res,
            "headroom": round(cap - L["spent_total"] - res, 6), "state": L["state"],
            "in_flight": len(L.get("reservations") or {})}


def call_upper_bound(entry: dict, request: dict, measured_tps: float | None = None) -> float:
    """The most one call can cost: every prompt token read and the whole reply limit written, at the model's
    price (a model on this computer: its machine time at its measured speed, or the cautious default)."""
    from . import policies
    bp = policies.body("budget")
    tin = int(len(str(request.get("prompt") or "")) / bp["prompt_chars_per_token"]) + 1
    tout = int(request.get("max_tokens") or 4000)
    if entry.get("local"):
        tps = float(measured_tps or bp["unknown_tokens_per_second"])
        return round(tout / max(tps, 0.1) * float(entry.get("compute_usd_per_hour") or 0) / 3600, 6)
    return round(tin * float(entry.get("price_in") or 0) / 1e6 + tout * float(entry.get("price_out") or 0) / 1e6, 6)


def reserve(store, *, worker_id: str, task_id: str, model_id: str, usd: float, purpose: str) -> dict:
    """Reserve a call's upper-bound cost before it starts. Atomic: of many workers reserving at once, those whose
    reservations fit go ahead and the rest are refused, so spent plus reserved never passes the cap. A refused
    reservation says whether other work is still in flight (wait for it) or nothing is (the founder decides)."""
    from .db import now
    with store.atomic():
        L = ledger(store)
        cap = float(project_settings.get(store)["budget_usd"])
        res = L.setdefault("reservations", {})
        held = reserved_total(L)
        n = store.next_seq("reservation")
        rid = f"res_{n:06d}"
        rec = {"id": rid, "task_id": task_id, "worker_id": worker_id, "model_id": model_id, "usd": round(usd, 6),
               "purpose": purpose, "at": now(), "spent_before": round(L["spent_total"], 6), "reserved_before": held}
        if L["state"] == "breaker" or (usd > 0 and L["spent_total"] + held + usd > cap + 1e-12):
            rec.update(status="refused", in_flight=len(res),
                       why="the budget breaker is open" if L["state"] == "breaker" else
                       f"spent ${L['spent_total']:.4f} + in flight ${held:.4f} + this call's ${usd:.4f} would pass "
                       f"the ${cap:.2f} cap")
            store.put("reservation", rid, rec)
            return rec
        rec["status"] = "held"
        res[rid] = {"usd": rec["usd"], "task_id": task_id, "worker_id": worker_id, "model_id": model_id}
        _save(store, L)
        store.put("reservation", rid, rec)
        return rec


def release(store, reservation_ids: list[str], outcome: str = "settled") -> None:
    """In-flight work ended: its reservations end; what it really cost was charged when it was recorded."""
    if not reservation_ids:
        return
    from .db import now
    with store.atomic():
        L = ledger(store)
        res = L.setdefault("reservations", {})
        for rid in reservation_ids:
            if res.pop(rid, None) is not None:
                rec = store.get("reservation", rid) or {"id": rid}
                rec.update(status=outcome, ended_at=now())
                store.put("reservation", rid, rec)
        _save(store, L)


def raise_cap(store, new_cap: float) -> dict:
    with store.atomic():
        return _raise_cap(store, new_cap)


def _raise_cap(store, new_cap: float) -> dict:
    s = project_settings.update(store, {"budget_usd": new_cap})
    L = ledger(store)
    L["state"] = "ok"
    L["reserve"] = round(s["budget_usd"] - sum(L["allocated"].values()) - _unallocated_spend(L), 6)
    L["warned"] = [m for m in L["warned"] if 100 * L["spent_total"] / s["budget_usd"] >= m]
    return _save(store, L)


def _unallocated_spend(L: dict) -> float:
    """Spend on work that has no allocation (the objective, the synthesis, the roadmap): it comes out of the cap."""
    return sum(v for k, v in L["spent"].items() if k not in L["allocated"])


def allocate(store, forecast: dict) -> dict:
    with store.atomic():
        return _allocate(store, forecast)


def _allocate(store, forecast: dict) -> dict:
    """After the roadmap is approved: each task gets its forecast; what is left of the cap is the reserve."""
    L = ledger(store)
    L["allocated"], L["by_worker"] = {}, {w: {"allocated": 0.0, "spent": v["spent"]} for w, v in L["by_worker"].items()}
    for r in forecast["tasks"]:
        usd = round(r["inference"] + r["coordination"] + r["tools"] + r["verification"], 6)
        L["allocated"][r["task_id"]] = usd
        w = L["by_worker"].setdefault(r["owner"], {"allocated": 0.0, "spent": 0.0})
        w["allocated"] = round(w["allocated"] + usd, 6)
    cap = float(project_settings.get(store)["budget_usd"])
    L["reserve"] = round(cap - sum(L["allocated"].values()) - _unallocated_spend(L)
                         - forecast["layers"]["infrastructure"]["usd"], 6)
    L["events"].append({"what": "allocated", "tasks": len(forecast["tasks"]), "reserve": L["reserve"]})
    return _save(store, L)


def reallocate(store, task_id: str, from_model: str, new: dict) -> dict:
    with store.atomic():
        return _reallocate(store, task_id, from_model, new)


def _reallocate(store, task_id: str, from_model: str, new: dict) -> dict:
    """A replacement: the failing model's unspent allocation goes back to the reserve; the successor's expected cost
    for the task comes out of it."""
    L = ledger(store)
    left = max(0.0, L["allocated"].get(task_id, 0.0) - L["spent"].get(task_id, 0.0))
    L["reserve"] = round(L["reserve"] + left - new["expected_usd"], 6)
    L["allocated"][task_id] = round(L["spent"].get(task_id, 0.0) + new["expected_usd"], 6)
    L["events"].append({"what": "reallocated", "task": task_id, "released": round(left, 4), "drawn": new["expected_usd"],
                        "from": from_model, "to": new["model_id"], "reserve": L["reserve"]})
    return _save(store, L)


def move(store, task_id: str, from_worker: str, to_worker: str) -> dict:
    with store.atomic():
        return _move(store, task_id, from_worker, to_worker)


def _move(store, task_id: str, from_worker: str, to_worker: str) -> dict:
    """A reroute: the task's allocation moves with it to the peer that takes it over."""
    L = ledger(store)
    alloc = L["allocated"].get(task_id, 0.0)
    for who, sign in ((from_worker, -1), (to_worker, 1)):
        b = L["by_worker"].setdefault(who, {"allocated": 0.0, "spent": 0.0})
        b["allocated"] = round(b["allocated"] + sign * alloc, 6)
    L["events"].append({"what": "moved", "task": task_id, "from_worker": from_worker, "to_worker": to_worker,
                        "usd": round(alloc, 4), "reserve": L["reserve"]})
    return _save(store, L)


def left_for(store, task_id: str) -> float:
    """What a task may still spend: the reserve plus what is left of its own allocation."""
    L = ledger(store)
    return L["reserve"] + max(0.0, L["allocated"].get(task_id, 0.0) - L["spent"].get(task_id, 0.0))


def _measured_verify_seconds(store) -> dict[str, float]:
    tasks = {t["id"]: t for t in store.all("task")}
    by: dict[str, list[float]] = {}
    for v in store.all("verification"):
        k = (tasks.get(v["task_id"]) or {}).get("kind")
        if k and v.get("seconds") is not None:
            by.setdefault(k, []).append(float(v["seconds"]))
    return {k: sum(x) / len(x) for k, x in by.items()}


def construct(store, tasks: list[dict], workers: list[dict], reg) -> dict:
    """The forecast for a roadmap, in layers, with views by worker, workstream and milestone."""
    s = project_settings.get(store)
    rate = float(s["compute_usd_per_hour"]) / 3600
    wmodel = {w["id"]: intelligence_of(store, w["id"]) for w in workers}
    wseq = {w["id"]: int((store.get("binding", w["id"]) or {}).get("seq") or 0) for w in workers}

    def model_for(t):  # the task's own binding when it is the newer decision (binding.effective, without a run)
        tb = store.get("work_binding", t["id"])
        if tb and tb.get("worker_id") == t["owner_worker_id"] and int(tb.get("seq") or 0) > wseq.get(t["owner_worker_id"], 0):
            return tb["intelligence_id"]
        return wmodel[t["owner_worker_id"]]
    vsec = {**VERIFY_S_DEFAULT, **_measured_verify_seconds(store)}
    rows = []
    for t in tasks:
        e = estimate(reg, reg.get(model_for(t)), t["kind"], s["time_value_per_hour"])
        coord = 0.0  # the cofounder who hands the task over, and reviews it before it counts
        for who, kind in ((t.get("handoff_from"), "assign"), (t.get("reviewed_by"), "review")):
            if who in wmodel and who != t["owner_worker_id"]:
                coord += estimate(reg, reg.get(wmodel[who]), kind, s["time_value_per_hour"])["usd_per_attempt"]
        checks = s["self_checks"] if t["kind"] in roles.BUILD_TYPES else 0
        v = vsec.get(t["kind"], 0.0) * e["expected_attempts"]
        rows.append({"task_id": t["id"], "owner": t["owner_worker_id"], "workstream": t.get("workstream_id"),
                     "milestone": t.get("milestone_id"), "kind": t["kind"], "model_id": e["model_id"],
                     "inference": e["expected_usd"], "coordination": coord, "tools": round(checks * v * rate, 6),
                     "verification": round(v * rate, 6), "minutes": e["expected_minutes"], "tokens": e["expected_tokens"],
                     "attempts": e["expected_attempts"], "p_task": e["p_task"], "basis": e["basis"]})
    days = max([int(t.get("deadline_day") or 1) for t in tasks] or [1])
    layers = {
        "inference": {"usd": round(sum(r["inference"] + r["coordination"] for r in rows), 4),
                      "basis": "each task's expected attempts on its owner's model at its measured cost per attempt, "
                               "and the Handoff and review by the cofounder who leads it"},
        "tools": {"usd": round(sum(r["tools"] for r in rows), 4),
                  "basis": f"workers' own test runs at ${s['compute_usd_per_hour']}/h of this machine"},
        "infrastructure": {"usd": round(days * float(s["infra_usd_per_day"]), 4),
                           "basis": f"{days} day(s) at ${s['infra_usd_per_day']}/day"},
        "verification": {"usd": round(sum(r["verification"] for r in rows), 4),
                         "basis": f"Verification Service runs at ${s['compute_usd_per_hour']}/h of this machine"},
    }
    subtotal = round(sum(v["usd"] for v in layers.values()), 4)
    cap = float(s["budget_usd"])
    spent_before = round(ledger(store)["spent_total"], 4)  # the objective, the synthesis and the roadmap itself
    reserve = round(cap - subtotal - spent_before, 4)
    layers["reserve"] = {"usd": reserve, "basis": "the rest of the cap: rework, retries and replacements"
                         + (f"; ${spent_before} already spent" if spent_before else "")}
    warnings = []
    if reserve < 0:
        warnings.append(f"The forecast is ${-reserve:.4f} over the ${cap:.2f} cap.")
    elif subtotal and reserve < float(s["reserve_min_pct"]) * subtotal:
        warnings.append(f"The reserve is under {int(100 * float(s['reserve_min_pct']))}% of the forecast.")

    def view(key):
        out: dict[str, dict] = {}
        for r in rows:
            v = out.setdefault(r[key] or "none", {"usd": 0.0, "minutes": 0.0, "tasks": []})
            v["usd"] = round(v["usd"] + r["inference"] + r["coordination"] + r["tools"] + r["verification"], 4)
            v["minutes"] = round(v["minutes"] + r["minutes"], 1)
            v["tasks"].append(r["task_id"])
        return out
    return {"cap_usd": cap, "subtotal_usd": subtotal, "spent_before_usd": spent_before,
            "total_usd": round(subtotal + spent_before + max(reserve, 0.0), 4), "reserve_usd": reserve,
            "fits": reserve >= 0, "warnings": warnings, "layers": layers, "tasks": rows,
            "by_worker": view("owner"), "by_workstream": view("workstream"), "by_milestone": view("milestone")}


def actual(store, forecast: dict | None) -> dict:
    """What was spent, in the same layers, beside the forecast: the reconciliation the founder sees."""
    s = project_settings.get(store)
    L = ledger(store)
    meta = store.get("meta", "run") or {}
    if meta.get("started_at"):  # hosting is accrued over the days the product has been in build and live
        days = max(0.0, ((meta.get("delivered_at") or time.time()) - meta["started_at"]) / 86400)
        infra = round(days * float(s["infra_usd_per_day"]), 4)
    else:
        infra = 0.0
    got = {k: round(L["by_layer"].get(k, 0.0), 4) for k in LAYERS}
    got["infrastructure"] = round(got["infrastructure"] + infra, 4)
    f = (forecast or {}).get("layers") or {}
    rows = {k: {"forecast": (f.get(k) or {}).get("usd", 0.0), "actual": v,
                "variance": round(v - (f.get(k) or {}).get("usd", 0.0), 4)} for k, v in got.items()}
    total = round(sum(got.values()), 4)
    by_worker = {wid: {"forecast": fw["usd"], "actual": round((L["by_worker"].get(wid) or {}).get("spent", 0.0), 4)}
                 for wid, fw in ((forecast or {}).get("by_worker") or {}).items()}
    for wid, w in L["by_worker"].items():
        by_worker.setdefault(wid, {"forecast": 0.0, "actual": round(w.get("spent", 0.0), 4)})
    return {"layers": rows, "total_forecast": round((forecast or {}).get("subtotal_usd", 0.0), 4),
            "total_actual": total, "cap_usd": float(s["budget_usd"]), "left_usd": round(float(s["budget_usd"]) - total, 4),
            "reserve_usd": L["reserve"], "by_worker": by_worker, "state": L["state"]}
