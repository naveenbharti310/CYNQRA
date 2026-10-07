"""The Objective Intelligence Controller: the control plane's boundary for choosing, binding, measuring and
re-choosing the intelligence that does the objective's work (mandate 58).

    Inputs   the objective and its version, its requirements and acceptance criteria, the work graph, the candidate
             intelligence (the Intelligence Registry), the global evidence, this objective's evidence
             (objective_evidence.py), the selection, risk and budget policies (policies.py), and the run's state
             (bindings, budget, reservations)
    Outputs  candidate sets, calibration plans (calibration.py), selection decisions, bindings, evidence updates,
             reselection decisions, and the ranking the Replacement Engine reroutes or replaces by

It uses the registry, the router, the performance engine, calibration, binding and replacement; none of them
decides on its own which intelligence does a piece of work. One rule decides it (policies.SELECTION):

    Select the candidate that satisfies all hard constraints and has the strongest policy-consistent evidence for
    the specific work item, objective version and acceptance criteria, subject to risk, budget, latency and evidence
    sufficiency.

Every selection is a SelectionDecision, persisted with an immutable, content-addressed snapshot of exactly what it
was decided from (the work item, every candidate's facts, the evidence records, the budget, the exploration state
and the full bodies of the policies), so it can be explained and replayed without today's registry (mandate 37, 38,
56). A decision is made against an evidence version; committing it re-checks that version inside one transaction,
and a decision overtaken by newer evidence is decided again, the old one kept as history (mandate 52). Bindings
carry versions and a compare-and-set, so concurrent workers never overwrite one another's binding.
"""
from __future__ import annotations

import json
import re
import sys
import time

from . import binding, budget, objective_evidence as oe, policies, roles
from . import attribution as attr
from . import settings as project_settings
from .db import ConcurrencyError, digest, now
from .intelligence_layer import router
from .intelligence_layer import evidence as evidence_model
from .intelligence_layer.registry import RegistryError, served_version

KIND, IDX = "selection_decision", "decision_index"
LOCAL_ONLY = re.compile(r"\b(local only|locally only|on[- ]prem\w*|on this (computer|machine|laptop)|no cloud|offline"
                        r"|data (must )?(stay|not leave|never leave))", re.I)
_RISK_ORDER = ("LOW", "MEDIUM", "HIGH")


class ControlError(RuntimeError):
    pass


# --- who, which objective, which version ----------------------------------------------------------------------------
def env_fingerprint() -> str:
    """What the verifiers and tools run on: evidence gathered on another runtime loses some of its authority."""
    return digest({"python": f"{sys.version_info[0]}.{sys.version_info[1]}", "platform": sys.platform,
                   "verification": policies.version("verification")})[:16]


def objective_id(run) -> str:
    obj = run.objective() or {}
    return obj.get("objective_id") or run.meta.get("objective_id") or f"obj_{run.cid}"


def stamp(run, t: dict | None = None) -> dict:
    """The objective and version a record belongs to, written on it when it is made (mandate 5): a task's attempt
    keeps the version it started under, so a later version never re-labels what happened before it."""
    obj = run.objective() or {}
    t = t or {}
    return {"objective_id": objective_id(run),
            "objective_version": int(t.get("attempt_objective_version") or t.get("objective_version")
                                     or obj.get("version") or 1)}


def context(run) -> dict:
    from . import objective as objective_engine
    obj = run.objective() or {}
    m = run.meta
    return {"tenant_id": m.get("tenant_id") or "local", "workspace_id": m.get("workspace_id") or "local",
            "objective_id": objective_id(run), "objective_version": int(obj.get("version") or 1), "run_id": run.cid,
            "inheritance": objective_engine.inheritance_map(run), "env": env_fingerprint()}


def _local_only(run) -> bool:
    obj = run.objective() or {}
    text = " ".join([str((obj.get("structured") or {}).get("constraints") or ""),
                     *[str(v) for v in (obj.get("founder_constraints") or {}).values()]])
    return bool(project_settings.get(run.store).get("intelligence_local_only")) or bool(LOCAL_ONLY.search(text))


# --- the work an intelligence is chosen for -------------------------------------------------------------------------
def _tier(kinds: list[str], requirement_ids: list[str], run) -> tuple[str, str]:
    rp = policies.body("risk")
    tier = max((router._risk(k) for k in kinds), key=_RISK_ORDER.index, default="LOW")
    areas = {r["area"] for r in (run.requirements() or {}).get("requirements", []) if r["id"] in set(requirement_ids)}
    critical = bool(areas & set(rp["critical_areas"]))
    if critical and tier == "LOW":
        tier = "MEDIUM"  # work on security, legal or money is more important than its type alone says
    return tier, "critical" if critical else "normal"


def _work(run, *, item: str, scope: str, kinds: list[str], worker_id: str | None, role: str | None,
          requirement_ids=(), acceptance_hash=None, criterion_ids=(), tier=None, requires=()) -> dict:
    sel = policies.body("selection")
    t, importance = _tier(kinds, list(requirement_ids), run)
    ctx = context(run)
    return {"work_item_id": item, "scope": scope, "kinds": list(kinds), "worker_id": worker_id, "role": role,
            "objective_id": ctx["objective_id"], "objective_version": ctx["objective_version"],
            "requirement_ids": list(requirement_ids), "acceptance_hash": acceptance_hash,
            "criterion_ids": list(criterion_ids), "risk_tier": tier or t, "importance": importance,
            "min_context": sel["min_context"],
            "output_tokens": max(sel["output_tokens"].get(k, sel["output_tokens"]["default"]) for k in kinds),
            "local_only": _local_only(run),
            # capabilities the work needs (mandate 46): its type's, and any the task names (an image to read, say)
            "requires": sorted({*requires, *(r for k in kinds for r in roles.TASK_TYPES.get(k, {}).get("requires", []))})}


def work_for_task(run, t: dict) -> dict:
    owner = run.worker(t["owner_worker_id"]) or {}
    return _work(run, item=t["id"], scope="task", kinds=[t["kind"]], worker_id=t["owner_worker_id"],
                 role=owner.get("role"), requirement_ids=t.get("requirement_ids") or [],
                 acceptance_hash=t.get("acceptance_hash"),
                 criterion_ids=[c["criterion_id"] for c in t.get("acceptance") or []], requires=t.get("requires") or [])


def work_for_worker(run, w: dict, kinds: list[str]) -> dict:
    return _work(run, item=f"worker:{w['id']}", scope="worker", kinds=kinds, worker_id=w["id"], role=w.get("role"),
                 requirement_ids=w.get("requirement_ids") or [])


def work_for_system(run, purpose: str, kinds: list[str] | None = None) -> dict:
    return _work(run, item=f"system:{purpose}", scope="system", kinds=kinds or ["objective"], worker_id=binding.SYSTEM,
                 role=None)


# --- candidates and their evidence ----------------------------------------------------------------------------------
def candidate_facts(run, m: dict, kinds: list[str]) -> dict:
    """What a candidate is, as a decision keeps it: the registry's facts at decision time, never read back later."""
    reg = run.registry
    ok, why = reg.availability(m)
    tv = project_settings.get(run.store)["time_value_per_hour"]
    measured = {}
    for k in kinds:
        e = router.estimate(reg, m, k, tv)
        measured[k] = {"usd_per_attempt": e["usd_per_attempt"], "seconds_per_attempt": e["seconds_per_attempt"],
                       "basis": e["basis"], "global_p_attempt": e["p_attempt"]}
    calls = [c for c in reg.calls(m["id"]) if (c.get("served_by") or "") == (m.get("served_by") or "")]
    errors = sum(1 for c in calls if c.get("error"))
    reg_state = m.get("regression") or {}
    return {"id": m["id"], "name": m.get("name"), "ref": m.get("ref"), "provider": m.get("provider") or "",
            "publisher": m.get("publisher") or "", "connection_id": m.get("connection_id"),
            "served_by": m.get("served_by") or "", "served_version": served_version(m), "runtime": m.get("runtime"),
            "local": bool(m.get("local")), "context": int(m.get("context") or 0), "max_output": m.get("max_output"),
            "input_modalities": m.get("input_modalities") or [], "type": m.get("type") or "",
            "capabilities": m.get("capabilities") or [], "price_in": m.get("price_in"), "price_out": m.get("price_out"),
            "available": ok, "availability": why,
            "qualification": {"status": reg_state.get("status") or "unverified", "by_kind": reg_state.get("by_kind") or {},
                              "version": reg_state.get("version")},
            "reliability": {"calls": len(calls), "call_errors": errors,
                            "rate": round(1 - errors / len(calls), 3) if calls else None},
            "measured": measured}


def candidates(run, exclude=()) -> list[dict]:
    """Every intelligence the registry knows and has not retired: the candidate set. Hard constraints, not this list,
    decide which are eligible, so an excluded candidate is on the record with its reason."""
    return [m for m in run.registry.models() if m["id"] not in set(exclude or ())]


def raw_evidence(run, ids: list[str]) -> list[dict]:
    """This objective's evidence (every version: inheritance decides what carries authority) and the registry's
    record of other work inside this tenant, for the candidates."""
    ctx = context(run)
    want = set(ids)
    out = [oe.raw(r) | {"protocol": bool(r.get("protocol_violation"))}
           for r in oe.query(run.store, objective_id=ctx["objective_id"], tenant_id=ctx["tenant_id"],
                             workspace_id=ctx["workspace_id"], include_inactive=True)
           if r["intelligence_id"] in want]
    for o in run.registry.outcomes(tenant_id=ctx["tenant_id"]):
        if o["model_id"] in want and o.get("clean", True):
            out.append(oe.registry_raw(o))
    return out


def _budget_state(run) -> dict:
    h = budget.headroom(run.store)
    h["time_value_per_hour"] = project_settings.get(run.store)["time_value_per_hour"]
    return h


def _exploration_state(run) -> dict:
    ds = [d for d in run.store.all(KIND) if d.get("selection_mode") == "explore" and d.get("status") == "committed"
          and d.get("objective_id") == objective_id(run)]
    return {"used": len(ds), "spent_usd": round(sum(float(d.get("expected_cost") or 0) for d in ds), 6)}


POLICY_NAMES = ("selection", "evidence", "risk", "budget", "calibration", "verification", "isolation")


def snapshot(run, work: dict, *, exclude=(), exclude_why: dict | None = None, incumbent: dict | None = None,
             pool: list[dict] | None = None) -> dict:
    eff = policies.effective(run.store)
    pool = pool if pool is not None else candidates(run)
    facts = [candidate_facts(run, m, work["kinds"]) for m in pool]
    ctx = context(run)
    return {"schema": "selection-snapshot-1", "now": time.time(), "work": work,
            "context": {k: ctx[k] for k in ("tenant_id", "workspace_id", "objective_id", "objective_version", "run_id",
                                            "inheritance", "env")},
            "candidates": facts, "evidence": raw_evidence(run, [f["id"] for f in facts]),
            "budget": _budget_state(run), "exploration": _exploration_state(run),
            "exclude": sorted(set(exclude or ())), "exclude_why": exclude_why or {},
            "incumbent": incumbent, "policies": {n: eff[n] for n in POLICY_NAMES},
            "evidence_version": oe.evidence_version(run.store, ctx["objective_id"])}


# --- decisions ------------------------------------------------------------------------------------------------------
def _target(work: dict, task_id: str | None) -> tuple[str, str]:
    if work["scope"] == "task" or (task_id and work["scope"] == "verification"):
        return "work_binding", work["work_item_id"] if work["scope"] == "task" else task_id
    return "binding", work["worker_id"]


def decide(run, work: dict, purpose: str, *, exclude=(), exclude_why=None, incumbent=None, pool=None,
           revalidates: str | None = None, supersedes: str | None = None) -> dict:
    """Make and persist a selection decision (proposed, not yet bound). Its snapshot is immutable and
    content-addressed; mutable current scores never overwrite it."""
    snap = snapshot(run, work, exclude=exclude, exclude_why=exclude_why, incumbent=incumbent, pool=pool)
    res = router.select(snap)
    return _persist(run, work, purpose, snap, res, revalidates=revalidates, supersedes=supersedes)


def _persist(run, work, purpose, snap, res, revalidates=None, supersedes=None, status="proposed") -> dict:
    ctx = snap["context"]
    snap_hash = run.store.put_object("json", snap)
    rows = {r["id"]: r for r in res["rows"]}
    sel = rows.get(res["selected"]) if res["selected"] else None
    fact = next((c for c in snap["candidates"] if c["id"] == res["selected"]), None)
    kind, key = _target(work, work["work_item_id"] if work["scope"] == "task" else None)
    cur = run.store.get(kind, key) or {}
    seq = run.store.next_seq("selection_decision")
    did = f"sd_{seq:05d}"
    rec = {"decision_id": did, "seq": seq, "purpose": purpose, "scope": work["scope"],
           "objective_id": ctx["objective_id"], "objective_version": ctx["objective_version"],
           "tenant_id": ctx["tenant_id"], "workspace_id": ctx["workspace_id"], "work_item_id": work["work_item_id"],
           "worker_id": work.get("worker_id"), "role": work.get("role"), "kinds": work["kinds"],
           "acceptance_hash": work.get("acceptance_hash"), "criterion_ids": work.get("criterion_ids") or [],
           "candidate_set": [{"id": c["id"], "name": c["name"], "served_version": c["served_version"]}
                             for c in snap["candidates"]],
           "eligible_candidates": res["eligible"], "excluded_candidates": res["excluded"],
           "hard_constraints": snap["policies"]["selection"]["body"]["hard_constraints"],
           "selection_policy_version": snap["policies"]["selection"]["version"],
           "policy_versions": {n: p["version"] for n, p in snap["policies"].items()},
           "policy_hash": digest({n: p for n, p in snap["policies"].items()}),
           "evidence_snapshot": snap_hash, "evidence_version": snap["evidence_version"],
           "evidence_ids": sorted({r["id"] for r in snap["evidence"] if r.get("src") == "objective"}),
           "selected_intelligence": ({"id": fact["id"], "name": fact["name"], "served_version": fact["served_version"]}
                                     if fact else None),
           "selection_mode": res["mode"], "selection_reason": res.get("reason") or "", "basis": res["basis"],
           "tier": res["tier"], "challenger": res.get("challenger"),
           "ranking": [{"id": r, "quality": rows[r]["quality"]["mean"], "lcb": rows[r]["quality"]["lcb"],
                        "ucb": rows[r]["quality"]["ucb"], "maturity": rows[r]["quality"]["maturity"],
                        "effective_n": rows[r]["quality"]["effective_n"],
                        "decisive_level": rows[r]["quality"]["decisive_level"],
                        "expected_usd": rows[r]["economics"]["expected_usd"],
                        "expected_minutes": rows[r]["economics"]["expected_minutes"],
                        "fits_budget": rows[r]["economics"]["fits_budget"]} for r in res["ranking"]],
           "expected_cost": sel["economics"]["expected_usd"] if sel else None,
           "expected_latency_minutes": sel["economics"]["expected_minutes"] if sel else None,
           "risk_state": {"tier": work.get("risk_tier"), "importance": work.get("importance")},
           "budget_state": snap["budget"], "decision_timestamp": now(),
           "binding_target": {"kind": kind, "id": key}, "binding_version": int(cur.get("_v") or 0) + 1,
           "status": status, "revalidates": revalidates, "supersedes": supersedes,
           "result_hash": digest({"selected": res["selected"], "mode": res["mode"], "ranking": res["ranking"]})}
    rec["content_hash"] = run.store.put_object("json", {k: v for k, v in rec.items() if k != "status"})
    run.store.put(KIND, did, rec)
    # every decision, the control plane's own included, is shown as proposed before it is committed
    run.event("intelligence.candidate_set.created", "work_item", work["work_item_id"],
              {"decision_id": did, "candidates": len(rec["candidate_set"]), "eligible": len(rec["eligible_candidates"]),
               "excluded": [{"id": x["id"], "why": x["violations"][0]["why"][:120]} for x in res["excluded"]][:12]},
              actor="intelligence_controller", correlation_id=work["work_item_id"])
    run.event("intelligence.selection.proposed", "selection_decision", did, {
        "work_item_id": work["work_item_id"], "selected": (rec["selected_intelligence"] or {}).get("id"),
        "mode": rec["selection_mode"], "policy": rec["selection_policy_version"],
        "evidence_version": rec["evidence_version"], "reason": rec["selection_reason"][:300]},
        actor="intelligence_controller", correlation_id=work["work_item_id"], aggregate_version=None)
    return rec


def get_decision(run, did: str) -> dict | None:
    return run.store.get(KIND, did)


def _mark(run, did: str, **kw) -> dict:
    with run.store.atomic():
        d = run.store.get(KIND, did)
        d.update(kw)
        run.store.put(KIND, did, d)
        return d


def commit(run, d: dict, work: dict, *, reason: str, by: str, purpose: str, exclude=(), exclude_why=None,
           incumbent=None, pool=None, candidates_rows=None) -> dict | None:
    """Bind the decision's selection. Inside one transaction: if the objective's evidence moved on since the
    decision was made, the decision is made again against the new evidence (the old one stays, marked as decided
    against version N); the binding's version must be the one the decision expected, else ConcurrencyError and the
    caller decides again. Returns the binding, or None when nothing was feasible."""
    for _ in range(4):
        with run.store.atomic():
            cur_ev = oe.evidence_version(run.store, d["objective_id"])
            if cur_ev != d["evidence_version"]:
                nd = decide(run, work, purpose, exclude=exclude, exclude_why=exclude_why, incumbent=incumbent,
                            pool=pool, revalidates=d["decision_id"])
                _mark(run, d["decision_id"], status="superseded_before_commit", superseded_by=nd["decision_id"],
                      note=f"decided against evidence version {d['evidence_version']}; version {cur_ev} existed at "
                           "commit")
                d = nd
            if d["selected_intelligence"] is None:
                _mark(run, d["decision_id"], status="no_selection")
                return None
            entry = run.registry.get(d["selected_intelligence"]["id"])
            if served_version(entry) != d["selected_intelligence"]["served_version"]:
                raise ControlError(f"{entry['id']} changed version after it was selected; decide again")
            tk, key = d["binding_target"]["kind"], d["binding_target"]["id"]
            try:
                if tk == "work_binding":
                    b = binding.bind_task(run, key, work["worker_id"], entry, reason=reason, by=by, decision=d,
                                          candidates=candidates_rows, expected_version=d["binding_version"] - 1)
                else:
                    b = binding.bind(run, key, entry, reason=reason, by=by, candidates=candidates_rows, decision=d,
                                     expected_version=d["binding_version"] - 1)
            except ConcurrencyError:
                _mark(run, d["decision_id"], status="lost_binding_race")
                d = decide(run, work, purpose, exclude=exclude, exclude_why=exclude_why, incumbent=incumbent,
                           pool=pool, supersedes=d["decision_id"])
                continue
            _mark(run, d["decision_id"], status="committed", committed_at=now())
            run.event("intelligence.selection.committed", "selection_decision", d["decision_id"], {
                "work_item_id": d["work_item_id"], "intelligence_id": entry["id"], "version": served_version(entry),
                "binding_version": b.get("_v"), "mode": d["selection_mode"]}, actor="intelligence_controller",
                correlation_id=d["work_item_id"], aggregate_version=None)
            if d["selection_mode"] == "reselect" and purpose != "reselection":
                # evidence moved this work off its incumbent (the worker's own intelligence, say) on verified
                # superiority: the founder sees it as a reselection, whichever path decided it (revalidate says so
                # itself before it commits)
                run.event("intelligence.reselection.triggered", "task" if d["scope"] == "task" else "work_item",
                          d["work_item_id"], {"from": (incumbent or {}).get("intelligence_id"), "to": entry["id"],
                                              "decision_id": d["decision_id"], "evidence_version": d["evidence_version"],
                                              "mode": d["selection_mode"], "purpose": purpose},
                          actor="intelligence_controller", correlation_id=d["work_item_id"])
            return b
    raise ConcurrencyError(f"could not bind {d['work_item_id']}: the binding kept changing")


def record_direct(run, *, target_kind: str, target_id: str, worker_id: str, entry: dict, reason: str, by: str,
                  rows: list | None, task_id: str | None = None) -> dict:
    """A binding made by another engine's rule (a stand-in during an outage, the return to the worker's own AI, a
    version pin after its regression check, a test's choice): still a persisted decision, with the snapshot of
    the facts and the candidates it was made from, so no binding exists without one."""
    w = run.worker(worker_id) or {}
    kinds = [task_id and (run.store.get("task", task_id) or {}).get("kind")] if task_id else []
    kinds = [k for k in kinds if k] or (roles.staffing_kinds(w["role"]) if w.get("role") in roles.ROLES else ["objective"])
    item = task_id if target_kind == "work_binding" else (f"worker:{worker_id}" if worker_id != binding.SYSTEM
                                                           else "system:control_plane")
    work = _work(run, item=item, scope="task" if target_kind == "work_binding" else
                 ("system" if worker_id == binding.SYSTEM else "worker"), kinds=kinds, worker_id=worker_id,
                 role=w.get("role"))
    snap = snapshot(run, work, pool=[entry])
    res = router.select(snap)
    res = dict(res, selected=entry["id"], mode="directed",
               reason=f"{entry.get('name')} bound by {by}: {reason[:300]}",
               basis=f"directed by {by}; the candidates it chose from are kept with the binding")
    d = _persist(run, work, "directed:" + by, snap, res)
    d["candidates_considered"] = [{k: r.get(k) for k in ("model_id", "model", "score", "p_task", "expected_usd")}
                                  for r in rows or []]
    d["status"] = "committed"
    run.store.put(KIND, d["decision_id"], d)
    return d


# --- the flows ------------------------------------------------------------------------------------------------------
def staff(run, workers: list[dict], workload: dict[str, list[str]] | None = None, refine: bool = False) -> dict:
    """An intelligence for every worker, each a decision over its role's kinds of work (or, once there is a
    roadmap, the kinds it actually owns and coordinates). Returns {worker_id: {model_id, model, decision_id,
    candidates, kinds}} like the Router's staffing table."""
    out = {}
    for w in workers:
        kinds = (workload or {}).get(w["id"]) or roles.staffing_kinds(w["role"])
        work = work_for_worker(run, w, kinds)
        cur = binding.current(run.store, w["id"])
        inc = {"intelligence_id": cur["intelligence_id"], "served_version": cur.get("version")} if refine and cur else None
        d = decide(run, work, "worker_staffing" if not refine else "worker_refinement", incumbent=inc)
        if d["selected_intelligence"] is None:
            raise router.RouterError("no available model can staff the organization: " + (
                "; ".join(f"{x['id']}: {x['violations'][0]['why']}" for x in d["excluded_candidates"][:3])
                or "register one in the model registry"))
        out[w["id"]] = {"model_id": d["selected_intelligence"]["id"], "model": d["selected_intelligence"]["name"],
                        "decision": d, "kinds": kinds, "candidates": legacy_rows(d)}
    return out


def legacy_rows(d: dict) -> list[dict]:
    """A decision's ranking in the shape the screens and the budget have always read."""
    return [{"model_id": r["id"], "model": next((c["name"] for c in d["candidate_set"] if c["id"] == r["id"]), r["id"]),
             "score": r["expected_usd"], "p_task": r["quality"], "expected_usd": r["expected_usd"],
             "expected_minutes": r["expected_minutes"], "fits_budget": r["fits_budget"], "quality_lcb": r["lcb"],
             "maturity": r["maturity"], "decisive_level": r["decisive_level"]} for r in d["ranking"]]


def bind_worker(run, w: dict, info: dict, reason: str) -> dict | None:
    d = info["decision"]
    work = work_for_worker(run, w, info["kinds"])
    cur = binding.current(run.store, w["id"])
    if cur and cur["intelligence_id"] == d["selected_intelligence"]["id"] and \
            cur.get("version") == d["selected_intelligence"]["served_version"]:
        _mark(run, d["decision_id"], status="committed", note="the worker was already bound to this selection")
        return cur
    return commit(run, d, work, reason=reason, by="intelligence_router", purpose=d["purpose"],
                  candidates_rows=info["candidates"])


def bind_tasks(run, tasks: list[dict]) -> list[dict]:
    """Stage 4 at the work item: every task's own decision and binding. The worker stays the seat; the binding says
    which intelligence does this piece of its work, and why."""
    out = []
    for t in tasks:
        if t.get("status") == "VERIFIED":
            continue
        work = work_for_task(run, t)
        # the worker's own intelligence is the incumbent: a task goes to another only when the evidence for this
        # piece of work shows a verifiably superior one (or the incumbent cannot do it at all)
        wb = binding.current(run.store, t["owner_worker_id"])
        inc = {"intelligence_id": wb["intelligence_id"], "served_version": wb.get("version")} if wb else None
        d = decide(run, work, "task_execution", incumbent=inc)
        b = commit(run, d, work, reason=d["selection_reason"], by="intelligence_controller",
                   purpose="task_execution", incumbent=inc, candidates_rows=legacy_rows(d))
        if b is not None:
            out.append(b)
            t = run.task(t["id"])
            t.update(binding_decision_id=b["decision_id"], binding_version=b.get("_v"))
            run.save_task(t)
    return out


def system_intelligence(run, purpose: str = "objective intelligence and workforce synthesis") -> str:
    """The control plane's own work (structuring the objective, synthesizing the workforce), decided like any
    other: a persisted decision and a binding."""
    work = work_for_system(run, "control_plane")
    d = decide(run, work, "system")
    if d["selected_intelligence"] is None:
        from .intelligence import IntelligenceError
        raise IntelligenceError("no available intelligence in the registry")
    commit(run, d, work, reason=purpose, by="intelligence_router", purpose="system", candidates_rows=legacy_rows(d))
    return d["selected_intelligence"]["id"]


def system_failover(run, failed: str, error: str, tried=(), worker_id: str | None = None) -> str | None:
    """Work that has no task to wait in: the control plane's own, or a worker's stage of the run (the planner
    writing the roadmap). When its intelligence's provider or account refuses a call (never the intelligence's
    fault, and never learned as one), the controller decides again without it and the work goes on with the next
    qualified intelligence, if there is one; a worker keeps its seat and its binding history. The new decision and
    the reroute are on the record, with the reason."""
    cause = attr.call_failure(error)
    out = sorted(set(tried) | {failed})
    w = run.worker(worker_id) if worker_id and worker_id != binding.SYSTEM else None
    work = work_for_worker(run, w, roles.staffing_kinds(w["role"])) if w else work_for_system(run, "control_plane")
    whose = f"{w['id']}'s" if w else "the control plane's"
    why = f"its {cause['kind']} refused the call ({cause['reason']})"
    d = decide(run, work, "failover", exclude=out, exclude_why={m: why for m in out})
    if d["selected_intelligence"] is None:
        _mark(run, d["decision_id"], status="no_selection",
              note=f"no other qualified intelligence is available for {whose} work")
        return None
    b = commit(run, d, work, reason=f"{whose} intelligence {failed}: {why}; decided again without it",
               by="intelligence_controller", purpose="failover", exclude=out, exclude_why={m: why for m in out},
               candidates_rows=legacy_rows(d))
    if b is None:
        return None
    run.event("intelligence.rerouted", "work_item", work["work_item_id"], {
        "from": failed, "to": b["intelligence_id"], "worker_id": w["id"] if w else binding.SYSTEM,
        "decision_id": b["decision_id"], "cause": cause["kind"], "why": why[:200]}, actor="intelligence_controller",
        correlation_id=work["work_item_id"])
    return b["intelligence_id"]


def revalidate(run, t: dict) -> dict | None:
    """When a task is about to start: if the objective's evidence moved on since its binding was decided, decide
    again with the current intelligence as the incumbent. A challenger replaces it only on verified superiority, or
    when the incumbent can no longer do the work (a hard constraint now fails). Historical decisions stay."""
    tb = binding.task_binding(run.store, t["id"])
    eff = binding.effective(run, t["owner_worker_id"], t["id"])
    if eff is None:
        return None
    mid, ver = eff
    d_old = get_decision(run, tb["decision_id"]) if tb and tb.get("decision_id") else None
    ev_now = oe.evidence_version(run.store, objective_id(run))
    seen = int(t.get("revalidated_at_evidence") if t.get("revalidated_at_evidence") is not None else -1)
    if (d_old is not None and d_old.get("evidence_version") == ev_now and tb["intelligence_id"] == mid) or seen == ev_now:
        return None
    work = work_for_task(run, t)
    incumbent = {"intelligence_id": mid, "served_version": ver}
    snap = snapshot(run, work, incumbent=incumbent)
    res = router.select(snap)  # a dry run: keeping the incumbent is not a new selection and writes no decision
    t = run.task(t["id"])
    t["revalidated_at_evidence"] = ev_now
    run.save_task(t)
    if res["selected"] is None or res["selected"] == mid:
        return None
    d = _persist(run, work, "reselection", snap, res, supersedes=(d_old or {}).get("decision_id"))
    sel = d["selected_intelligence"]["id"]
    run.event("intelligence.reselection.triggered", "task", t["id"], {
        "from": mid, "to": sel, "decision_id": d["decision_id"], "evidence_version": d["evidence_version"],
        "mode": d["selection_mode"]}, actor="intelligence_controller", correlation_id=t["id"])
    b = commit(run, d, work, reason=d["selection_reason"], by="intelligence_controller", purpose="reselection",
               incumbent={"intelligence_id": mid, "served_version": ver}, candidates_rows=legacy_rows(d))
    if b is not None:
        run.event("intelligence.rerouted", "task", t["id"], {"from": mid, "to": b["intelligence_id"],
                  "worker_id": t["owner_worker_id"], "decision_id": b["decision_id"],
                  "why": d["selection_reason"][:200]}, actor="intelligence_controller", correlation_id=t["id"])
    return b


def after_evidence(run, ev: dict) -> list[dict]:
    """New evidence: the future work it bears on is decided again where it changes the choice. Work already done
    or in flight keeps its decision; history is never rewritten."""
    if not ev.get("clean") or ev.get("verified") is None or ev.get("stage") != "objective_execution":
        return []  # calibration evidence feeds the initial bindings, which come after it
    out = []
    for t in run.tasks():
        if t["status"] != "PLANNED" or t["kind"] != ev.get("task_kind") or t["id"] == ev.get("work_item_id"):
            continue
        b = revalidate(run, t)
        if b is not None:
            out.append(b)
    return out


def reviewer(run, t: dict, worker_id: str) -> tuple[str, str | None] | None:
    """Verification independence (mandate 17): for work at a tier the verification policy names, the intelligence
    that reviews it must not be the one that produced it. When the reviewer's own intelligence is the producer's,
    the review is routed to another qualified intelligence, by a decision of its own; when none can take it, the
    review runs as it is and its evidence is marked not independent. The seat doing the review does not change."""
    vpol = policies.body("verification")
    tier, _ = _tier([t["kind"]], t.get("requirement_ids") or [], run)
    if tier not in vpol["independent_review_tiers"]:
        return None
    prod, _v = producer(run, t)
    eff = binding.effective(run, worker_id, None)
    if not eff or eff[0] != prod:
        return None
    vb = run.store.get("verification_binding", t["id"])
    if vb and vb.get("worker_id") == worker_id:
        try:
            if run.registry.availability(run.registry.get(vb["intelligence_id"]))[0]:
                return vb["intelligence_id"], vb.get("version")
        except RegistryError:
            pass
    w = run.worker(worker_id) or {}
    work = _work(run, item=f"review:{t['id']}", scope="verification", kinds=["review"], worker_id=worker_id,
                 role=w.get("role"), requirement_ids=t.get("requirement_ids") or [], tier=tier)
    d = decide(run, work, "independent_verification", exclude=[prod],
               exclude_why={prod: "the producer's intelligence may not verify its own work"})
    if d["selected_intelligence"] is None:
        _mark(run, d["decision_id"], status="no_selection",
              note="no other qualified intelligence: the review runs on the producer's, marked not independent")
        return None
    sel = d["selected_intelligence"]
    with run.store.atomic():
        old = run.store.get("verification_binding", t["id"]) or {}
        run.store.put("verification_binding", t["id"], {"task_id": t["id"], "worker_id": worker_id,
                      "intelligence_id": sel["id"], "version": sel["served_version"], "decision_id": d["decision_id"],
                      "producer": prod, "_v": int(old.get("_v") or 0) + 1, "bound_at": now()})
    _mark(run, d["decision_id"], status="committed", committed_at=now())
    run.event("worker.bound", "binding", t["id"], {"scope": "verification", "task_id": t["id"], "worker_id": worker_id,
              "intelligence_id": sel["id"], "decision_id": d["decision_id"], "producer": prod,
              "worker_identity_unchanged": True}, actor="intelligence_controller", correlation_id=t["id"])
    return sel["id"], sel["served_version"]


def rank_for(run, t: dict, kinds: list[str], *, exclude=(), exclude_why=None, purpose="replacement") -> dict:
    """The Replacement Engine's alternatives for a task, from the same evidence and policy as every selection:
    the decision is persisted; the engine then checks the candidates' regression evidence and picks."""
    w = run.worker(t["owner_worker_id"]) or {}
    work = _work(run, item=t["id"], scope="task", kinds=kinds, worker_id=t["owner_worker_id"], role=w.get("role"),
                 requirement_ids=t.get("requirement_ids") or [], acceptance_hash=t.get("acceptance_hash"))
    return decide(run, work, purpose, exclude=exclude, exclude_why=exclude_why)


def quality_of(d: dict, intelligence_id: str) -> dict | None:
    """One candidate's evidenced quality in a decision's ranking."""
    r = next((x for x in d["ranking"] if x["id"] == intelligence_id), None)
    return {"mean": r["quality"], "lcb": r["lcb"], "ucb": r["ucb"], "effective_n": r.get("effective_n", 0),
            "maturity": r.get("maturity")} if r else None


def record_choice(run, d: dict, chosen: str, purpose: str, reason: str, tried: list[dict]) -> dict:
    """Another engine's pick from a decision's ranking (the Replacement Engine, after regression checks): a decision
    of its own over the same immutable snapshot, with the checks that ruled out the candidates before it, so it
    replays from its inputs."""
    snap = run.store.get_object(d["evidence_snapshot"])
    res = router.select(snap)
    res = dict(res, selected=chosen, mode="replacement",
               reason=f"{reason[:300]} Chosen after regression checks: " + "; ".join(
                   f"{x['model_id']} {'passed' if x['passed'] else 'failed'}" for x in tried))
    work = snap["work"]
    out = _persist(run, work, purpose, snap, res, supersedes=d["decision_id"], status="committed")
    out["regression_checks"] = tried
    out["skipped_before"] = [x["model_id"] for x in tried if not x["passed"]]
    run.store.put(KIND, out["decision_id"], out)
    return out


def assess_incumbent(run, t: dict, model_id: str, kinds: list[str]) -> dict | None:
    """The incumbent's own evidenced quality on this work, as the same rule sees it."""
    try:
        entry = run.registry.get(model_id)
    except RegistryError:
        return None
    w = run.worker(t["owner_worker_id"]) or {}
    work = _work(run, item=t["id"], scope="task", kinds=kinds, worker_id=t["owner_worker_id"], role=w.get("role"),
                 requirement_ids=t.get("requirement_ids") or [])
    snap = snapshot(run, work, pool=[entry])
    res = router.select(dict(snap, exclude=[]))
    row = next((r for r in res["rows"] if r["id"] == model_id), None)
    return row["quality"] if row else None


# --- evidence -------------------------------------------------------------------------------------------------------
def producer(run, t: dict) -> tuple[str | None, str | None]:
    """The intelligence that actually produced the task's current work: its last work call, at the version that
    answered, never whatever the worker happens to be bound to now."""
    calls = [c for c in run.store.all("call") if c.get("task_id") == t["id"] and c.get("purpose") == "work"
             and c.get("model_id")]
    if calls:
        c = calls[-1]
        return c["model_id"], c.get("model_version")
    eff = binding.effective(run, t["owner_worker_id"], t["id"])
    return eff if eff else (run.model_of(t["owner_worker_id"]), None)


def autonomy_of(run, t: dict) -> tuple[str, list[str]]:
    """How much a person helped this task's current work: human-assisted and human-corrected work never counts as
    autonomous success (mandate 50)."""
    ds = [d for d in run.store.all("decision") if d.get("task_id") == t["id"] and d.get("resolved_by") == "founder"]
    ids = [d["id"] for d in ds]
    if any(d.get("outcome_label") == "approved_edited" for d in ds):
        return "human_corrected", ids
    if any(d["kind"] == "escalation" and d["status"] == "approved" for d in ds):
        return "human_assisted", ids
    if any(d["kind"] in ("decision", "review_merge", "deploy") and d.get("outcome_label") in ("rejected",
                                                                                            "rejected_with_reason")
           for d in ds):
        return "human_assisted", ids  # it passed after a person sent it back
    mid, _ = producer(run, t)
    directed = [r for r in run.store.all("replacement") if r.get("human_directed") and r.get("active")
                and r.get("worker_id") == t.get("owner_worker_id") and r.get("to") == mid]
    if directed:  # a person chose which intelligence does this work; the work itself was its own
        return "human_directed_reroute", ids + [r["id"] for r in directed]
    return "autonomous", ids


def attempt_kind(t: dict) -> str:
    if t.get("replacements") and not t.get("attempts"):
        return "after_replacement" if not t.get("rerouted") else "after_reroute"
    if t.get("human_retry") and not t.get("attempts"):
        return "human_directed_retry"
    return "initial" if not t.get("attempts") else "rework"


def record_task_evidence(run, t: dict, *, verified: bool | None, failure: dict | None = None,
                         verification: dict | None = None, verifier_kind: str = "deterministic_platform",
                         defects: list | None = None, protocol_violation: bool = False, extra: dict | None = None,
                         idempotency_key: str | None = None, causation: dict | None = None,
                         stage: str = "objective_execution", vq: float | None = None,
                         intelligence: tuple[str | None, str | None] | None = None) -> dict | None:
    """One piece of objective execution evidence, from a real persisted fact: a verification record, a founder's
    decision, a protocol violation, a provider failure. The verdict is read from the verification record itself,
    never taken from the caller, and the record must still match its hash (mandate 59: false verification)."""
    mid, ver = intelligence or producer(run, t)
    if not mid:
        return None
    try:
        entry = run.registry.get(mid)
    except RegistryError:
        entry = {"id": mid, "name": mid}
    if verification is not None:
        if verification.get("record_hash") and verification["record_hash"] != verification_hash(verification):
            raise oe.EvidenceError(f"verification {verification['id']} does not match its hash: refused as evidence")
        derived = verification.get("verdict") == "VERIFIED"
        if verified is not None and bool(verified) != derived:
            raise oe.EvidenceError(f"evidence says {'verified' if verified else 'failed'} but verification "
                                   f"{verification['id']} says {verification.get('verdict')}: refused")
        verified = derived
        if verification.get("model_id") and verification["model_id"] != mid:
            raise oe.EvidenceError(f"verification {verification['id']} is about {verification['model_id']}, not {mid}")
    vpol = policies.body("verification")
    q = vq if vq is not None else vpol["quality"].get(verifier_kind, 1.0)
    reviewer = (verification or {}).get("reviewer_intelligence")
    independent = verifier_kind in ("deterministic_platform", "deterministic_with_own_tests", "human") or \
        (verifier_kind == "independent_intelligence" and reviewer != mid)
    autonomy, interventions = autonomy_of(run, t)
    if verified is False and failure is None:
        failure = attr.failure(attr.INTELLIGENCE, "the work failed its verification",
                               (verification or {}).get("feedback") or "")
    ctx = context(run)
    meter = run.store.get("meter", t["id"]) or {}
    w = run.worker(t["owner_worker_id"]) or {}
    tb = binding.task_binding(run.store, t["id"]) or {}
    outs = t.get("outputs") or []
    sev = max((d.get("severity", "major") for d in defects or []), key=("minor", "major", "critical").index,
              default="major") if (defects or verified is False) else None
    rec = {"tenant_id": ctx["tenant_id"], "workspace_id": ctx["workspace_id"], "objective_id": ctx["objective_id"],
           "objective_version": int(t.get("attempt_objective_version") or ctx["objective_version"]),
           "stage": stage, "work_item_id": t["id"], "work_class": f"{t['kind']}:{w.get('role')}",
           "requirement_ids": t.get("requirement_ids") or [], "role": w.get("role"), "task_kind": t["kind"],
           "worker_id": t["owner_worker_id"], "intelligence_id": mid, "intelligence": entry.get("name"),
           "provider": entry.get("provider"), "model_ref": entry.get("ref"),
           "served_version": ver if ver is not None else served_version(entry), "served_by": entry.get("served_by"),
           "connection_id": entry.get("connection_id"), "acceptance_hash": t.get("acceptance_hash"),
           "criterion_ids": [c["criterion_id"] for c in t.get("acceptance") or []],
           "attempt": int(t.get("attempts") or 0) + 1, "attempt_kind": attempt_kind(t),
           "replacement_round": int(t.get("replacements") or 0), "rework_count": int(t.get("attempts") or 0),
           "execution_status": "completed" if verified is not None else "failed",
           "verification_status": None if verified is None else ("verified" if verified else "rejected"),
           "verified": verified, "defects": defects or [], "defect_count": len(defects or []), "max_severity": sev,
           "cost_usd": round(float(meter.get("usd") or 0), 6), "latency_s": round(float(meter.get("seconds") or 0), 2),
           "tokens": int(meter.get("tokens") or 0), "failure": failure, "clean": attr.clean(failure),
           "artifact_hashes": {"work_hash": (verification or {}).get("work_hash"),
                               "files": [{"file": o.get("file"), "hash": o.get("hash")} for o in outs
                                         if isinstance(o, dict)]},
           "verification": {"verification_id": (verification or {}).get("id"),
                            "method": (verification or {}).get("method"), "verifier_kind": verifier_kind,
                            "verifier_intelligence": reviewer, "independent": independent,
                            "record_hash": (verification or {}).get("record_hash"),
                            "test_ids_count": len((verification or {}).get("test_ids") or []), "quality": q},
           "autonomy": autonomy, "human_interventions": interventions,
           "tool_use": dict(t.get("tool_use") or {}), "protocol_violation": protocol_violation,
           "selection": {"decision_id": tb.get("decision_id"), "binding_version": tb.get("_v"),
                         "binding_intelligence": tb.get("intelligence_id")},
           "environment": {"fingerprint": env_fingerprint(), "verification_policy": policies.version("verification")},
           "provenance": {"source": (extra or {}).pop("source", "execution") if extra else "execution",
                          "verification_event": (causation or {}).get("event_id")},
           "idempotency_key": idempotency_key or f"{stage}:{t['id']}:{(verification or {}).get('id') or now()}:{mid}"}
    rec.update(extra or {})
    rec["dimensions"] = _dimensions(run, rec["worker_id"], mid)

    def emit(body):
        run.store.append(company_id=run.cid, event_type="intelligence.evidence.updated", aggregate_type="evidence",
                         aggregate_id=body["objective_id"], actor_type="service", actor_id="intelligence_controller",
                         payload={"evidence_id": body["evidence_id"], "objective_version": body["objective_version"],
                                  "work_item_id": body["work_item_id"], "intelligence_id": body["intelligence_id"],
                                  "stage": body["stage"], "verified": body["verified"], "clean": body["clean"],
                                  "attribution": (body.get("failure") or {}).get("kind"),
                                  "evidence_version": body["evidence_version"]},
                         correlation_id=body["work_item_id"], causation_id=(causation or {}).get("event_id"),
                         idempotency_key="evidence:" + body["idempotency_key"],
                         aggregate_version=body["evidence_version"])
    ev, created = oe.record(run.store, rec, event=emit)
    if created and stage == "objective_execution" and ev["clean"] and verified is not None:
        run.registry.record_outcome(mid, role=ev.get("role") or "", task_kind=ev["task_kind"], task_id=t["id"],
                                    run_id=run.cid, attempt=rec["attempt"], verified=bool(verified),
                                    usd=rec["cost_usd"], seconds=rec["latency_s"], tokens=rec["tokens"],
                                    failure=(failure or {}).get("detail") or "", tenant_id=ctx["tenant_id"],
                                    workspace_id=ctx["workspace_id"], objective_id=ctx["objective_id"],
                                    objective_version=rec["objective_version"], model_version=rec["served_version"])
    if created:
        after_evidence(run, ev)
    return ev


def _dimensions(run, worker_id: str, model_id: str) -> dict:
    """The Performance Engine's measured dimensions for this worker on this intelligence, kept with the evidence
    as they stood: quality, reliability, efficiency, economics and human friction, never one number."""
    from . import performance
    try:
        c = performance.scorecard(run.store, worker_id, model_id)
    except Exception:  # noqa: BLE001 - a scorecard that cannot be built leaves the dimensions empty
        return {}
    return {k: c.get(k) for k in ("quality", "reliability", "efficiency", "economics", "human_friction")}


def verification_hash(v: dict) -> str:
    """The material fields of a verification record: a verdict changed afterwards no longer matches."""
    return digest({k: v.get(k) for k in ("id", "task_id", "attempt", "verdict", "method", "test_ids", "work_hash",
                                         "model_id", "worker_id", "output_hash")})


def work_of(t: dict, worker_id: str | None) -> str:
    """The kind of work a worker does on a task: its owner does the task's own kind; its cofounder hands it over
    and reviews it; a colleague answers its Blocker. A failure is evidence about the work the caller was doing."""
    if not worker_id or worker_id == t.get("owner_worker_id"):
        return t["kind"]
    if worker_id == t.get("handoff_from") and t.get("status") in ("PLANNED", None):
        return "assign"
    if worker_id == t.get("reviewed_by"):
        return "review"
    if worker_id == (t.get("blocker") or {}).get("needs_from"):
        return "answer"
    return "assign" if worker_id == t.get("handoff_from") else t["kind"]


def record_attempt_failure(run, t: dict, failure: dict, *, kind: str, idempotency_key: str,
                           intelligence: tuple[str | None, str | None] | None = None,
                           protocol_violation: bool = False, severity: str = "major",
                           caller: str | None = None) -> dict | None:
    """A failed attempt that is not a verification: a provider failure, a cancellation, a Blocker on a missing
    input, a protocol violation, an unusable reply. Only what the intelligence caused carries quality; the rest is
    recorded, contaminated, and never learned from. caller: the worker whose call it was, when not the owner (a
    cofounder's handoff, say): the evidence is about that worker's work, never the owner's."""
    verified = False if attr.clean(failure) else None
    extra = {"source": kind}
    if caller and caller != t.get("owner_worker_id"):
        w = run.worker(caller) or {}
        k = work_of(t, caller)
        extra.update(task_kind=k, role=w.get("role"), worker_id=caller, work_class=f"{k}:{w.get('role')}")
    try:
        return record_task_evidence(run, t, verified=verified, failure=failure, verifier_kind="deterministic_platform",
                                    defects=[{"severity": severity, "kind": kind}] if verified is False else [],
                                    protocol_violation=protocol_violation, idempotency_key=idempotency_key,
                                    intelligence=intelligence, extra=extra)
    except oe.EvidenceError:
        return None


def cancel_open_attempts(run, why: str) -> list[str]:
    """The objective was cancelled with work in progress: each open attempt is recorded as cancelled (mandate 49),
    contaminated, so it never becomes an intelligence failure, and closed. Returns the tasks it closed."""
    closed = []
    for t in run.tasks():
        if t["status"] == "VERIFIED" or not t.get("attempt_open"):
            continue
        record_attempt_failure(run, t, attr.failure("cancelled", "the objective was cancelled while this work was "
                                                    "in progress", why), kind="cancelled",
                               idempotency_key=f"objective_cancelled:{t['id']}:{t.get('attempts')}:{t.get('work_calls')}")
        t.update(attempt_open=False, cancelled_at=now())
        run.save_task(t)
        closed.append(t["id"])
    return closed


def _constraint_model(run) -> dict | None:
    """The objective's constraint model as stored with its requirements; a run saved before it was stored gets it
    computed from the same objective and policies."""
    req = run.requirements()
    if not req:
        return None
    from . import objective as objective_engine
    return req.get("constraint_model") or objective_engine.constraint_model(run)


# --- replay and audit -----------------------------------------------------------------------------------------------
def replay(run, decision_id: str) -> dict:
    """Reproduce a historical decision from its own immutable inputs (its snapshot, with the policy bodies it was
    made under), without reading today's registry or evidence. Reproduced: the same selection, mode and ranking."""
    d = get_decision(run, decision_id)
    if d is None:
        raise ControlError(f"no decision {decision_id}")
    snap = run.store.get_object(d["evidence_snapshot"])
    if snap is None:
        return {"decision_id": decision_id, "reproduced": False, "why": "its snapshot is missing"}
    intact = digest(snap) == d["evidence_snapshot"] or run.store.put_object("json", snap) == d["evidence_snapshot"]
    if d["purpose"].startswith("directed:"):
        res = {"selected": (d["selected_intelligence"] or {}).get("id"), "mode": "directed",
               "ranking": router.select(snap)["ranking"]}
    elif d.get("selection_mode") == "replacement":
        # the ranking from the snapshot, then the recorded regression checks: the first candidate not ruled out
        full = router.select(snap)
        out = [r for r in full["ranking"] if r not in set(d.get("skipped_before") or [])]
        chosen = (d["selected_intelligence"] or {}).get("id")
        res = {"selected": chosen if chosen in out else None, "mode": "replacement", "ranking": full["ranking"]}
    else:
        res = router.select(snap)
    same = digest({"selected": res["selected"], "mode": res["mode"], "ranking": res["ranking"]}) == d["result_hash"]
    return {"decision_id": decision_id, "reproduced": bool(same and intact), "snapshot_intact": bool(intact),
            "selected": res["selected"], "recorded": (d["selected_intelligence"] or {}).get("id"),
            "mode": res["mode"], "policy": d["selection_policy_version"], "evidence_version": d["evidence_version"],
            "from_snapshot_only": True}


def prior_choice(run, decision_id: str) -> dict:
    """What the global prior alone would have chosen for this decision (roadmap 1: compare the objective-specific
    choice against it): the decision's own snapshot, from its own inputs, with this objective's evidence removed and
    no incumbent or exploration, so only qualification and other work speak. Pure, like replay."""
    d = get_decision(run, decision_id)
    if d is None:
        raise ControlError(f"no decision {decision_id}")
    snap = run.store.get_object(d["evidence_snapshot"])
    if snap is None:
        return {"decision_id": decision_id, "prior": None, "why": "its snapshot is missing"}
    bare = dict(snap, evidence=[r for r in snap.get("evidence") or [] if r.get("src") != "objective"], incumbent=None,
                exploration={"used": 10 ** 9, "spent_usd": 0.0})
    res = router.select(bare)
    chosen = (d.get("selected_intelligence") or {}).get("id")
    return {"decision_id": decision_id, "work_item_id": d.get("work_item_id"), "chosen": chosen,
            "chosen_mode": d.get("selection_mode"), "prior": res["selected"], "agrees": res["selected"] == chosen,
            "objective_evidence_items": sum(1 for r in snap.get("evidence") or [] if r.get("src") == "objective"),
            "prior_ranking": res["ranking"][:5]}


def decisions(run, work_item_id: str | None = None) -> list[dict]:
    out = [d for d in run.store.all(KIND) if work_item_id is None or d["work_item_id"] == work_item_id]
    out.sort(key=lambda d: d["seq"])
    return out


def explain(run, task_id: str) -> dict:
    """The causal audit of one work item, from persisted records only (mandate 33, 64): every link from the
    founder's objective to the next intelligence decision, and which links are missing."""
    t = run.task(task_id)
    obj = run.objective() or {}
    ctx = context(run)
    ds = decisions(run, task_id)
    tb = binding.task_binding(run.store, task_id) or {}
    evs = oe.query(run.store, objective_id=ctx["objective_id"], tenant_id=ctx["tenant_id"], work_item_id=task_id,
                   include_inactive=True)
    ver = [v for v in run.store.all("verification") if v["task_id"] == task_id]
    calls = [c for c in run.store.all("call") if c.get("task_id") == task_id]
    reservations = [r for r in run.store.all("reservation") if r.get("task_id") == task_id]
    cal = [p for p in run.store.all("calibration_plan") if p.get("objective_id") == ctx["objective_id"]]
    cal_items = [i for p in cal for i in p.get("items") or [] if i.get("kind") == t["kind"]]
    reqs = {r["id"]: r for r in (run.requirements() or {}).get("requirements", [])}
    crit = [c for c in (run.requirements() or {}).get("acceptance_criteria", []) if c.get("requirement_id") in
            set(t.get("requirement_ids") or [])]
    prod = run.store.get("production_verification", f"pv_{run.cycle() if hasattr(run, 'cycle') else 1}")
    first = ds[0] if ds else None
    snap = run.store.get_object(first["evidence_snapshot"]) if first else None
    chain = {
        "founder_objective": {"objective_id": ctx["objective_id"], "statement_hash": digest(obj.get("statement") or "")}
        if obj else None,
        "objective_lifecycle_state": (obj.get("lifecycle") or {}).get("state"),
        "objective_version": ctx["objective_version"] if obj else None,
        "requirements": [reqs[r]["id"] for r in t.get("requirement_ids") or [] if r in reqs] or None,
        "constraints": ({"hard": [h["id"] for h in cm["hard_constraints"]],
                         "preferences": [p["id"] for p in cm["preferences"]],
                         "mandatory_requirements": len(cm["mandatory_requirements"])}
                        if (cm := _constraint_model(run)) else None),
        "acceptance_criteria": {"task": [c["criterion_id"] for c in t.get("acceptance") or []],
                                "requirements": [c["criterion_id"] for c in crit],
                                "acceptance_hash": t.get("acceptance_hash")} if t.get("acceptance") else None,
        "work_item": {"id": task_id, "kind": t["kind"], "owner": t["owner_worker_id"], "status": t["status"]},
        "candidate_intelligence": first["candidate_set"] if first else None,
        "global_qualification": [{"id": c["id"], "qualification": c["qualification"]["status"]}
                                 for c in (snap or {}).get("candidates", [])] or None,
        "objective_calibration": ({"plans": [p["plan_id"] for p in cal], "items": [i["item_id"] for i in cal_items],
                                   "stopped": [p.get("stopping") for p in cal]} if cal else None),
        "evidence_snapshot": [d["evidence_snapshot"] for d in ds] or None,
        "selection_policy_version": sorted({d["selection_policy_version"] for d in ds}) or None,
        "selection_decision": [{"id": d["decision_id"], "purpose": d["purpose"], "status": d["status"],
                                "selected": (d["selected_intelligence"] or {}).get("id"), "mode": d["selection_mode"],
                                "reason": d["selection_reason"][:240]} for d in ds] or None,
        "worker_binding": {"task_binding": {k: tb.get(k) for k in ("intelligence_id", "version", "decision_id", "_v")},
                           "history": tb.get("history") or []} if tb else None,
        "budget_reservation": [{k: r.get(k) for k in ("id", "usd", "status")} for r in reservations] or None,
        "execution_attempt": [{"id": c["id"], "model_id": c.get("model_id"), "purpose": c.get("purpose")}
                              for c in calls] or None,
        "artifact": [o for o in t.get("outputs") or []] or ([t["decision_id"]] if t.get("decision_id") else None),
        "independent_verification": [{"id": v["id"], "verdict": v["verdict"], "method": v["method"],
                                      "reviewer": v.get("reviewer_id")} for v in ver] or None,
        "causal_outcome_classification": [{"evidence_id": e["evidence_id"], "attribution": (e.get("failure") or {}).get(
            "kind") or "success", "clean": e["clean"]} for e in evs] or None,
        "objective_evidence_update": [e["evidence_id"] for e in evs] or None,
        "performance_update": [e.get("dimensions") for e in evs][-1:] or None,
        "exploration_exploitation": sorted({d["selection_mode"] for d in ds}) or None,
        "reselection_reroute_replacement": [{"decision": d["decision_id"], "purpose": d["purpose"]} for d in ds
                                            if d["purpose"] in ("reselection", "replacement", "reroute")]
        + [{"replacement": r["id"], "rerouted": r.get("rerouted")} for r in run.store.all("replacement")
           if r.get("task_id") == task_id],
        "production_verification": prod,
        "delivery": (run.store.get("transition", f"tr_{run.cycle()}") or {}).get("id") if hasattr(run, "cycle") else None,
        "immutable_audit_replay": [replay(run, d["decision_id"])["reproduced"] for d in ds] or None,
    }
    # links that legitimately may be empty: no calibration for proposal work, no reselection, delivery not yet
    optional = {"objective_calibration", "reselection_reroute_replacement", "budget_reservation",
                "production_verification", "delivery", "acceptance_criteria", "requirements", "artifact",
                "performance_update"}
    missing = [k for k, v in chain.items() if v in (None, [], {}) and k not in optional]
    return {"task_id": task_id, "chain": chain, "missing": missing, "complete": not missing}


def summary(run) -> dict:
    """What the founder's screen shows of the control plane: real records only."""
    ds = run.store.all(KIND)
    ctx = context(run) if run.objective() else None
    evs = oe.query(run.store, objective_id=ctx["objective_id"], tenant_id=ctx["tenant_id"]) if ctx else []
    return {"decisions": len(ds), "committed": sum(1 for d in ds if d.get("status") == "committed"),
            "explorations": sum(1 for d in ds if d.get("selection_mode") == "explore"),
            "evidence": len(evs), "evidence_version": oe.evidence_version(run.store, ctx["objective_id"]) if ctx else 0,
            "clean_evidence": sum(1 for e in evs if e["clean"]),
            "contaminated_evidence": sum(1 for e in evs if not e["clean"]),
            "latest": [{k: d.get(k) for k in ("decision_id", "work_item_id", "purpose", "selection_mode", "status",
                                               "selection_reason")} | {"selected": (d.get("selected_intelligence") or {})
                                                                       .get("name")} for d in ds[-8:]],
            "policies": policies.catalog()}


def to_json(obj) -> str:
    return json.dumps(obj, indent=1, default=str)
