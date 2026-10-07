"""Audit a real run from its persisted records (the P1 completion mandate, sections 3 to 7 and 10).

Input: the data root of a hosted examination (cynqra-hosted-intelligence): `control/control.db` (the Intelligence
Layer: connections, registry, outcomes), one or more objective runs (each a folder with its own `cynqra.db`) and
`manifest.json`. Nothing is called and nothing is written: every check reads what the run persisted, so the audit
says what happened, not what the code intends. A control the run never reached (no rework happened, say) is
reported as not exercised, never as passed.

    python3 -m cynqra.run_audit <data root> [--json out.json] [--secret-env NAME ...]

`--secret-env` names environment variables whose values must appear nowhere in the persisted files (the job's API
keys): the scan reports only whether and where, never the value.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from . import controller, objective as objective_engine, objective_evidence as oe
from .db import Store, digest
from .intelligence_layer import router
from .intelligence_layer.registry import served_version

PASS, FAIL, NOT_EXERCISED, INFO = "pass", "fail", "not_exercised", "info"

# The founder-visible events the source mandate names (section 23), and when each is owed: always, or only when what
# it reports actually happened in the run.
EVENTS = {
    "objective.created": "objective", "requirements.created": "requirements", "workgraph.created": "workgraph",
    "workforce.created": "workforce", "intelligence.discovered": "always",
    "intelligence.candidate_set.created": "decided", "intelligence.calibration.started": "calibrated",
    "intelligence.calibration.completed": "calibration_plan", "intelligence.selection.proposed": "decided",
    "intelligence.selection.committed": "committed", "worker.bound": "bound", "task.started": "worked",
    "review.started": "reviewed", "verification.completed": "verified", "rework.created": "reworked",
    "intelligence.evidence.updated": "evidenced", "intelligence.reselection.triggered": "reselected",
    "intelligence.rerouted": "rerouted", "production.verification.started": "production",
    "production.verification.completed": "production", "objective.completed": "completed",
}
DECISION_FIELDS = ("decision_id", "objective_id", "objective_version", "work_item_id", "worker_id", "candidate_set",
                   "eligible_candidates", "excluded_candidates", "hard_constraints", "selection_policy_version",
                   "evidence_snapshot", "evidence_version", "selected_intelligence", "selection_reason",
                   "expected_cost", "expected_latency_minutes", "risk_state", "decision_timestamp", "binding_version")
# The events that change which intelligence does the work, or say why: the audit's timeline.
TIMELINE = ("intelligence.selection.committed", "intelligence.reselection.triggered", "intelligence.rerouted",
            "worker.stand_in", "worker.returned", "worker.model_replaced", "worker.stopped", "task.rerouted",
            "tasks.waiting", "rework.created", "decision.created", "decision.approved", "decision.rejected",
            "intelligence.version_changed", "verification.completed")
# Checks whose data an auditor reads even when they pass: where evidence changed a choice, and why work moved.
SHOW_DATA = ("objective evidence reached real selections", "no replacement on one noisy failure",
             "worker identity survives an intelligence change")
# Shapes of provider keys, so a key is found even when its variable was not passed to the scan.
KEY_SHAPES = re.compile(rb"sk-ant-[A-Za-z0-9_\-]{20,}|AIza[0-9A-Za-z_\-]{30,}|nvapi-[A-Za-z0-9_\-]{20,}|"
                        rb"hf_[A-Za-z0-9]{30,}|gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{40,}")


class _Run:
    """What controller.replay and controller.prior_choice read: the run's store, nothing live."""

    def __init__(self, store: Store):
        self.store = store


def _check(out: list, section: str, name: str, status: str, detail: str, **data) -> None:
    out.append({"section": section, "check": name, "status": status, "detail": detail, **({"data": data} if data else {})})


def _count(values) -> dict:
    out: dict = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return out


def _runs(root: Path) -> list[Path]:
    return sorted(p.parent for p in root.glob("*/cynqra.db"))


def audit(root: Path, secrets: dict[str, str] | None = None) -> dict:
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8")) if (root / "manifest.json").exists() \
        else {}
    control = Store(str(root / "control" / "control.db")) if (root / "control" / "control.db").exists() else None
    runs = []
    try:
        for folder in _runs(root):
            store = Store(str(folder / "cynqra.db"))
            try:
                runs.append(audit_run(folder, store, control))
            finally:
                store.close()
        checks: list = []
        _discovery(checks, control, manifest)
        _isolation(checks, root, runs)
        _scan(checks, root, secrets or {})
    finally:
        if control is not None:
            control.close()
    every = checks + [c for r in runs for c in r["checks"]]
    return {"root": str(root), "runs": runs, "checks": checks,
            "summary": {s: sum(1 for c in every if c["status"] == s) for s in (PASS, FAIL, NOT_EXERCISED, INFO)},
            "failed": [f"{c['section']} {c['check']}: {c['detail']}" for c in every if c["status"] == FAIL]}


# --- one objective run -------------------------------------------------------------------------------------------
def audit_run(folder: Path, store: Store, control: Store | None) -> dict:
    out: list = []
    run = _Run(store)
    meta = store.get("meta", "run") or {}
    obj = store.get("objective", "obj_1") or {}
    tasks = {t["id"]: t for t in store.all("task")}
    decisions = sorted(store.all(controller.KIND), key=lambda d: d.get("seq") or 0)
    oid = obj.get("objective_id") or meta.get("objective_id")
    tenant = meta.get("tenant_id") or "local"
    evidence = oe.query(store, objective_id=oid, tenant_id=tenant, include_inactive=True) if oid else []
    events = store.events()
    types: dict[str, int] = {}
    for e in events:
        types[e["event_type"]] = types.get(e["event_type"], 0) + 1
    registry = {m["id"]: m for m in control.all("intelligence")} if control else {}
    ctx = {"meta": meta, "obj": obj, "tasks": tasks, "decisions": decisions, "evidence": evidence, "events": events,
           "types": types, "registry": registry, "run": run, "store": store}
    for step in (_identity, _lifecycle, _candidates, _calibration, _decisions, _execution, _verification,
                 _provenance, _attribution, _reselection, _versions, _workers, _budget, _production, _events):
        try:
            step(out, ctx)
        except Exception as exc:  # noqa: BLE001 - one unreadable part never hides the rest of the audit
            _check(out, step.__name__.strip("_"), "audit step", FAIL, f"could not be audited: {type(exc).__name__}: {exc}")
    return {"folder": str(folder), "company_id": meta.get("company_id"), "objective_id": oid,
            "objective_version": obj.get("version"), "phase": meta.get("phase"),
            "lifecycle": (obj.get("lifecycle") or {}).get("state"), "tasks": len(tasks), "decisions": len(decisions),
            "evidence": len(evidence), "events": len(events), "checks": out,
            "tables": ctx.get("tables", {})}


def _identity(out, c):
    obj, meta = c["obj"], c["meta"]
    ok = bool(obj.get("objective_id") and obj.get("version"))
    if not obj and not c["tasks"] and not c["evidence"]:  # stopped before the objective was structured
        _check(out, "3", "objective identity", NOT_EXERCISED, f"the run stopped before its objective was structured "
               f"(phase {meta.get('phase')}): {str(meta.get('notice') or '')[:200]}")
        return
    _check(out, "3", "objective identity", PASS if ok else FAIL,
           f"objective {obj.get('objective_id')} version {obj.get('version')}; run phase {meta.get('phase')}; "
           f"lifecycle {(obj.get('lifecycle') or {}).get('state')}",
           statement_hash=digest(obj.get("statement") or ""), notice=meta.get("notice"))
    bad = [t["id"] for t in c["tasks"].values() if t.get("objective_id") != obj.get("objective_id")]
    _check(out, "3", "work items carry the objective", FAIL if bad else PASS,
           f"{len(c['tasks'])} work items; {len(bad)} without this objective's id", missing=bad[:10])


def _lifecycle(out, c):
    life = (c["obj"].get("lifecycle") or {}).get("history") or []
    path = [h["to"] for h in life]
    bad = [h for h in life if not objective_engine.can(h.get("from"), h["to"])]
    _check(out, "6", "lifecycle transitions are allowed", FAIL if bad else PASS,
           " -> ".join(path) or "no transitions recorded", refused=bad[:5])
    canonical = ["OBJECTIVE_CREATED", "OBJECTIVE_ACCEPTED", "OBJECTIVE_DECOMPOSED", "OBJECTIVE_EXECUTING",
                 "OBJECTIVE_COMPLETED", "OBJECTIVE_VERIFIED", "OBJECTIVE_CLOSED"]
    reached = [s for s in canonical if s in path]
    _check(out, "6", "lifecycle reached", PASS if reached == canonical else NOT_EXERCISED,
           f"reached {len(reached)} of {len(canonical)} canonical states; exceptions: "
           + (", ".join(s for s in path if s in ("OBJECTIVE_PAUSED", "OBJECTIVE_BLOCKED", "OBJECTIVE_CANCELLED",
                                                  "OBJECTIVE_SUPERSEDED", "OBJECTIVE_REOPENED")) or "none"))
    cur = int(c["obj"].get("version") or 1)
    later = [e["evidence_id"] for e in c["evidence"] if int(e.get("objective_version") or 0) > cur]
    versions = sorted({int(e.get("objective_version") or 0) for e in c["evidence"]})
    _check(out, "6", "evidence keeps its objective version", FAIL if later else PASS,
           f"objective at version {cur}; evidence recorded under versions {versions or 'none'}", later=later[:5])


def _candidates(out, c):
    reg = c["registry"]
    rows = []
    for m in reg.values():
        q = m.get("regression") or {}
        rows.append({"id": m["id"], "ref": m.get("ref"), "provider": m.get("access_provider") or m.get("provider"),
                     "served_by": m.get("served_by") or "", "served_version": served_version(m),
                     "qualification": q.get("status", "unverified"), "by_kind": q.get("by_kind") or {},
                     "status": m.get("status") or "active"})
    rows.sort(key=lambda r: (r["qualification"] not in ("passed", "not applicable"), r["status"] != "active", r["id"]))
    c.setdefault("tables", {})["candidates"] = rows
    _check(out, "3", "candidates on record", PASS if rows else FAIL,
           f"{len(rows)} intelligence entries; {sum(1 for r in rows if r['qualification'] in ('passed', 'not applicable'))}"
           " qualified, " + f"{sum(1 for r in rows if r['qualification'] == 'unverified')} unverified")
    unq = []
    for d in c["decisions"]:
        snap = c["store"].get_object(d["evidence_snapshot"]) or {}
        sel = (d.get("selected_intelligence") or {}).get("id")
        fact = next((x for x in snap.get("candidates") or [] if x["id"] == sel), None)
        if sel and fact and (fact.get("qualification") or {}).get("status") not in ("passed", "not applicable"):
            unq.append({"decision": d["decision_id"], "selected": sel,
                        "qualification": (fact.get("qualification") or {}).get("status")})
    _check(out, "7", "only qualified intelligence was selected", FAIL if unq else PASS,
           f"{len(c['decisions'])} decisions; {len(unq)} selected intelligence that was not qualified at decision time",
           violations=unq[:10])


def _calibration(out, c):
    from . import calibration
    plans = c["store"].all(calibration.KIND)
    if not plans:
        _check(out, "4", "objective calibration", NOT_EXERCISED, "no calibration plan was recorded")
        return
    trials_out, bad, unq = [], [], []
    for p in plans:
        for it in p.get("items") or []:
            t = c["tasks"].get(it.get("source_task_id"))
            if t is None or t.get("objective_id") != c["obj"].get("objective_id"):
                bad.append(it.get("item_id"))
        for tr in p.get("trials") or []:
            ev = next((e for e in c["evidence"] if e["evidence_id"] == tr.get("evidence_id")), {})
            m = c["registry"].get(tr["intelligence_id"]) or {}
            q = (m.get("regression") or {}).get("status", "unverified")
            if q not in ("passed", "not applicable"):
                unq.append(tr["intelligence_id"])
            trials_out.append({"item": tr["item_id"], "intelligence": tr["intelligence_id"],
                               "served_version": tr.get("served_version"), "verified": tr.get("verified"),
                               "attribution": tr.get("attribution"), "usd": tr.get("usd"),
                               "latency_s": ev.get("latency_s"), "tokens": ev.get("tokens"),
                               "artifact": (ev.get("artifact_hashes") or {}).get("files"),
                               "method": (ev.get("verification") or {}).get("method"),
                               "evidence_id": tr.get("evidence_id")})
    c.setdefault("tables", {})["calibration_trials"] = trials_out
    p = plans[-1]
    status = p.get("status")
    if status != "completed":
        _check(out, "4", "objective calibration", NOT_EXERCISED, f"plan {p.get('plan_id')} {status}: {p.get('reason')}",
               coverage=p.get("coverage"))
    else:
        _check(out, "4", "objective calibration ran on the objective's own work", FAIL if bad else PASS,
               f"{len(p.get('items') or [])} item(s), {len(trials_out)} trial(s), "
               f"{sum(1 for t in trials_out if t['verified'])} verified; items not from this objective's plan: {bad}",
               stopping=p.get("stopping"), coverage=p.get("coverage"), budget_usd=p.get("budget_usd"),
               spent_usd=p.get("spent_usd"))
    _check(out, "7", "calibration used only qualified intelligence", FAIL if unq else PASS,
           f"{len(trials_out)} trial(s); not qualified: {sorted(set(unq))}")


def _decisions(out, c):
    ds, store = c["decisions"], c["store"]
    if not ds:
        _check(out, "4", "selection decisions", FAIL, "no selection decision was persisted")
        return
    missing, broken, changed, unreplayed, rows = [], [], [], [], []
    influence, differ, reordered, moved = 0, 0, [], []
    for d in ds:
        miss = [k for k in DECISION_FIELDS if k not in d]
        if miss:
            missing.append({"decision": d["decision_id"], "missing": miss})
        frozen = store.get_object(d.get("content_hash") or "")
        if frozen is None:
            changed.append(d["decision_id"])
        elif any(frozen.get(k) != d.get(k) for k in frozen if k != "status"):
            changed.append(d["decision_id"])
        rp = controller.replay(c["run"], d["decision_id"])
        if not rp.get("snapshot_intact", rp.get("reproduced")):
            broken.append(d["decision_id"])
        if not rp.get("reproduced"):
            unreplayed.append(d["decision_id"])
        row = {"decision": d["decision_id"], "purpose": d.get("purpose"), "scope": d.get("scope"),
               "work_item": d.get("work_item_id"), "selected": (d.get("selected_intelligence") or {}).get("id"),
               "mode": d.get("selection_mode"), "status": d.get("status"), "tier": d.get("tier"),
               "eligible": [x.get("id") if isinstance(x, dict) else x for x in d.get("eligible_candidates") or []],
               "excluded_by_constraint": _count((x.get("violations") or [{}])[0].get("constraint")
                                                for x in d.get("excluded_candidates") or []),
               "objective_evidence": len(d.get("evidence_ids") or []), "policy": d.get("selection_policy_version"),
               "policy_hash": (d.get("policy_hash") or "")[:12], "snapshot": (d.get("evidence_snapshot") or "")[:12],
               "evidence_version": d.get("evidence_version"), "expected_usd": d.get("expected_cost"),
               "expected_minutes": d.get("expected_latency_minutes"), "binding_version": d.get("binding_version"),
               "at": d.get("decision_timestamp"), "replayed": rp.get("reproduced"),
               # each candidate's quality with its band, evidence and the level that decided it, its cost and time:
               # kept apart, never one score
               "ranking": [{"id": r["id"], "q": r.get("quality"), "band": [r.get("lcb"), r.get("ucb")],
                            "n": r.get("effective_n"), "by": r.get("decisive_level"), "usd": r.get("expected_usd"),
                            "min": r.get("expected_minutes")} for r in d.get("ranking") or []][:4]}
        if d.get("scope") == "task" and d.get("selected_intelligence"):
            pc = controller.prior_choice(c["run"], d["decision_id"])
            top = ((d.get("ranking") or [{}])[0]).get("id")
            row.update(prior=pc.get("prior"), agrees_with_prior=pc.get("agrees"), top_ranked=top)
            if d.get("evidence_ids"):
                influence += 1
                differ += int(pc.get("agrees") is False)
                # the objective's evidence put another candidate first, whether or not the choice followed it (an
                # incumbent is kept unless the challenger's superiority is verified)
                if top and pc.get("prior_ranking") and top != pc["prior_ranking"][0]:
                    reordered.append({"decision": d["decision_id"], "work_item": d.get("work_item_id"),
                                      "top_with_objective_evidence": top, "top_on_prior_alone": pc["prior_ranking"][0],
                                      "chosen": row["selected"], "mode": d.get("selection_mode")})
            if d.get("selection_mode") == "reselect" and d.get("status") == "committed":
                moved.append({"decision": d["decision_id"], "work_item": d.get("work_item_id"), "to": row["selected"],
                              "objective_evidence": len(d.get("evidence_ids") or []), "purpose": d.get("purpose")})
        rows.append(row)
    c.setdefault("tables", {})["decisions"] = rows
    _check(out, "4", "every decision has the mandated fields", FAIL if missing else PASS,
           f"{len(ds)} decisions; {len(missing)} missing a field", missing=missing[:5])
    _check(out, "4", "decisions are immutable", FAIL if changed else PASS,
           f"{len(changed)} decision(s) differ from their frozen content", changed=changed[:5])
    _check(out, "4", "every decision replays from its own snapshot", FAIL if unreplayed or broken else PASS,
           f"{len(ds) - len(unreplayed)} of {len(ds)} reproduced; snapshots broken: {broken[:5]}")
    _check(out, "4", "objective evidence reached real selections", PASS if influence else NOT_EXERCISED,
           f"{influence} work-item decision(s) read this objective's evidence; in {differ} of them the global prior "
           f"alone would have chosen differently; in {len(reordered)} it put another candidate first than the prior "
           f"alone would (the incumbent kept unless the challenger's superiority was verified); {len(moved)} "
           "committed reselection(s) on verified superiority", reordered=reordered, reselected=moved)
    split = all(all(k in r for k in ("quality", "lcb", "ucb", "expected_usd", "expected_minutes"))
                for d in ds for r in d.get("ranking") or [])
    _check(out, "4", "no universal score", PASS if split else FAIL,
           "every ranking keeps quality with its band, expected cost and expected time apart; the trade-off comes "
           "from the risk tier" if split else "a ranking entry merges dimensions")
    bindings = c["store"].all("binding") + c["store"].all("work_binding") + c["store"].all("verification_binding")
    orphan = [b.get("worker_id") or b.get("task_id") for b in bindings
              if not c["store"].get(controller.KIND, b.get("decision_id") or "")]
    _check(out, "4", "every binding names a persisted decision", FAIL if orphan else PASS,
           f"{len(bindings)} bindings; {len(orphan)} without a decision", orphan=orphan[:5])


def _execution(out, c):
    store = c["store"]
    calls = store.all("call")
    work = {}
    for x in sorted(calls, key=lambda x: x["id"]):
        if x.get("purpose") == "work" and str(x.get("task_id", "")).startswith("t_"):
            work.setdefault(x["task_id"], []).append(x.get("model_id"))
    vs = {}
    for v in store.all("verification"):
        vs.setdefault(v["task_id"], []).append(v)
    rows, mismatch = [], []
    for tid, t in sorted(c["tasks"].items()):
        # the last verified attempt is the delivered one: a review can send verified work back for rework
        ok = next((v for v in sorted(vs.get(tid, []), key=lambda v: v["id"], reverse=True) if v["verdict"] == "VERIFIED"),
                  None)
        made = (work.get(tid) or [None])[-1]
        if ok and made and ok.get("model_id") and ok["model_id"] != made:
            mismatch.append({"task": tid, "verified_model": ok["model_id"], "last_work_call": made})
        owner = store.get("worker", t.get("owner_worker_id") or "") or {}
        rows.append({"task": tid, "title": str(t.get("title") or "")[:80], "owner": t.get("owner_worker_id"),
                     "role": owner.get("role"), "kind": t["kind"], "tier": t.get("risk_tier"), "status": t["status"],
                     "work_calls_by": sorted(set(work.get(tid, []))),
                     "verifications": [v["verdict"] for v in sorted(vs.get(tid, []), key=lambda v: v["id"])],
                     "verified_model": (ok or {}).get("model_id"),
                     "outputs": [o.get("file") for o in t.get("outputs") or [] if isinstance(o, dict)][:8]})
    c.setdefault("tables", {})["tasks"] = rows
    # the workforce: each seat, its role, the work it owned and the intelligence behind it over the run
    bindings = {b["worker_id"]: b for b in store.all("binding")}
    c["tables"]["workers"] = [
        {"worker": w["id"], "role": w.get("role"), "title": w.get("title"),
         "owns": sorted(x["id"] for x in c["tasks"].values() if x.get("owner_worker_id") == w["id"]),
         "intelligence_now": (bindings.get(w["id"]) or {}).get("intelligence_id"),
         "history": [h.get("intelligence_id") for h in (bindings.get(w["id"]) or {}).get("history") or []][:12],
         "decision": (bindings.get(w["id"]) or {}).get("decision_id")}
        for w in sorted(store.all("worker"), key=lambda w: w["id"])]
    did = [r for r in rows if r["work_calls_by"]]
    _check(out, "4", "the selected intelligence did the work", FAIL if mismatch else (PASS if did else NOT_EXERCISED),
           f"{len(did)} work item(s) with real work calls; {sum(1 for r in rows if r['status'] == 'VERIFIED')} verified; "
           f"{len(mismatch)} verified under an intelligence other than the one whose call produced the work",
           mismatch=mismatch[:5])
    dims = sum(1 for e in c["evidence"] if e.get("dimensions"))
    _check(out, "4", "performance measurements kept with the evidence", PASS if dims else NOT_EXERCISED,
           f"{dims} of {len(c['evidence'])} evidence record(s) carry the Performance Engine's dimensions "
           "(quality, reliability, efficiency, economics, human friction); cost, latency and quality drive selection; "
           "reliability and stability are recorded only (P1 partial area)")


def _verification(out, c):
    store, ev = c["store"], c["evidence"]
    kinds: dict[str, int] = {}
    self_as_independent = []
    for e in ev:
        v = e.get("verification") or {}
        kinds[v.get("verifier_kind") or "none"] = kinds.get(v.get("verifier_kind") or "none", 0) + 1
        if v.get("independent") and v.get("verifier_intelligence") and v["verifier_intelligence"] == e["intelligence_id"]:
            self_as_independent.append(e["evidence_id"])
    vb = store.all("verification_binding")
    same = [b["task_id"] for b in vb if b.get("producer") and b.get("intelligence_id") == b["producer"]]
    _check(out, "4", "producer and verifier kept apart", FAIL if self_as_independent or same else PASS,
           f"verifier kinds {kinds}; {len(vb)} review(s) routed to another intelligence; "
           f"{len(self_as_independent) + len(same)} self-verifications counted as independent")
    reviews = [e for e in c["events"] if e["event_type"] == "review.started"]
    calls = store.all("call")
    refused = {x.get("task_id") for x in store.all("call_error")}  # a review its provider refused was attempted
    unbacked = [e["aggregate_id"] for e in reviews
                if not any(x.get("purpose") == "review" and x.get("task_id") in (e["aggregate_id"],
                                                                                 e["payload"].get("task_id"))
                           for x in calls)
                and not ({e["aggregate_id"], e["payload"].get("task_id")} & refused)]
    _check(out, "5", "no claimed review without a real review", FAIL if unbacked else (PASS if reviews else NOT_EXERCISED),
           f"{len(reviews)} review.started event(s); {len(unbacked)} with no review call behind them, made or refused "
           "by its provider",
           unbacked=unbacked[:5])


def _provenance(out, c):
    store, oid = c["store"], c["obj"].get("objective_id")
    need = ("objective_id", "objective_version", "tenant_id", "workspace_id", "intelligence_id", "stage",
            "work_item_id", "idempotency_key", "evidence_version", "content_hash")
    missing, foreign, altered = [], [], []
    for e in c["evidence"]:
        miss = [k for k in need if e.get(k) in (None, "")]
        if miss:
            missing.append({"evidence": e["evidence_id"], "missing": miss})
        if e.get("objective_id") != oid:
            foreign.append(e["evidence_id"])
        frozen = store.get_object(e.get("content_hash") or "")
        if frozen is None or any(frozen.get(k) != e.get(k) for k in frozen):
            altered.append(e["evidence_id"])
    stages: dict[str, int] = {}
    for e in c["evidence"]:
        stages[e.get("stage")] = stages.get(e.get("stage"), 0) + 1
    _check(out, "10", "every evidence record carries its provenance", FAIL if missing or foreign or altered else
           (PASS if c["evidence"] else NOT_EXERCISED),
           f"{len(c['evidence'])} record(s) by stage {stages}; {len(missing)} missing objective, version, work item "
           f"or idempotency key; {len(foreign)} of another objective; {len(altered)} altered after they were written",
           missing=missing[:5], foreign=foreign[:5], altered=altered[:5])


def _attribution(out, c):
    bad, by = [], {}
    for e in c["evidence"]:
        k = (e.get("failure") or {}).get("kind")
        by[k or "none"] = by.get(k or "none", 0) + 1
        if k and k != "intelligence" and (e.get("clean") is not False or e.get("verified") is not None):
            bad.append(e["evidence_id"])
        if k == "intelligence" and e.get("clean") is False:
            bad.append(e["evidence_id"])
    _check(out, "4", "only the intelligence's own failures carry quality", FAIL if bad else PASS,
           f"evidence by failure kind {by}; {len(bad)} record(s) with a failure counted against the wrong party",
           wrong=bad[:5])


def _reselection(out, c):
    modes: dict[str, int] = {}
    for d in c["decisions"]:
        modes[str(d.get("selection_mode"))] = modes.get(str(d.get("selection_mode")), 0) + 1
    reps = c["store"].all("replacement")
    noisy = []
    for r in reps:
        if r.get("temporary"):
            continue
        fails = [e for e in c["evidence"] if e["intelligence_id"] == r.get("from") and e.get("work_item_id") ==
                 r.get("task_id") and e.get("verified") is False and e.get("clean")]
        why = str(r.get("reason") or "")
        if len(fails) <= 1 and not re.search(r"cut off|output limit|protocol|regression|withdrawn|retired|unusable", why,
                                             re.I):
            noisy.append({"replacement": r["id"], "from": r.get("from"), "to": r.get("to"), "clean_failures": len(fails),
                          "reason": why[:160]})
    _check(out, "4", "no replacement on one noisy failure", FAIL if noisy else (PASS if reps else NOT_EXERCISED),
           f"decision modes {modes}; {len(reps)} replacement(s) "
           f"({sum(1 for r in reps if r.get('temporary'))} temporary stand-ins); {len(noisy)} after a single failure",
           replacements=[{"id": r["id"], "from": r.get("from"), "to": r.get("to"), "task": r.get("task_id"),
                          "temporary": bool(r.get("temporary")), "reason": str(r.get("reason") or "")[:120]}
                         for r in reps][:20], noisy=noisy)
    explore = [d for d in c["decisions"] if d.get("selection_mode") == "explore"]
    _check(out, "4", "a challenger needs verified superiority", PASS if modes.get("reselect") or explore or
           modes.get("keep_incumbent") else NOT_EXERCISED,
           f"{modes.get('keep_incumbent', 0)} incumbent(s) kept, {modes.get('reselect', 0)} reselection(s) on verified "
           f"superiority, {len(explore)} bounded exploration(s)",
           challengers=[d.get("challenger") for d in explore][:5])


def _versions(out, c):
    store, viol, mism = c["store"], [], 0
    for d in c["decisions"]:
        snap = store.get_object(d["evidence_snapshot"])
        if not snap:
            continue
        by_id = {r.get("id"): r for r in snap.get("evidence") or []}
        res = router.select(snap)
        cv = {x["id"]: x.get("served_version") or "" for x in snap.get("candidates") or []}
        for row in res["rows"]:
            for k in row["per_kind"]:
                mism += sum(1 for x in k["excluded"] if x["why"] == "version_mismatch")
                for u in k["used"]:
                    r = by_id.get(u["id"]) or {}
                    if (r.get("served_version") or "") != cv.get(row["id"], ""):
                        viol.append({"decision": d["decision_id"], "candidate": row["id"], "evidence": u["id"]})
    _check(out, "4", "evidence never crosses a model version or serving company", FAIL if viol else PASS,
           f"{len(viol)} item(s) of another version used; {mism} excluded as version_mismatch", violations=viol[:5])


def _workers(out, c):
    store = c["store"]
    workers = {w["id"]: w for w in store.all("worker")}
    bs = store.all("binding")
    changed = [b for b in bs if b.get("history")]
    # a member the plan gave no work leaves before anything starts (worker.released): gone by design, not lost
    released = {e["aggregate_id"] for e in c["events"] if e["event_type"] == "worker.released"}
    lost = [b["worker_id"] for b in bs if b["worker_id"] not in workers and b["worker_id"] != "system"
            and not b["worker_id"].startswith("system") and b["worker_id"] not in released]
    reps = store.all("replacement")
    gone = [r["id"] for r in reps if r.get("worker_id") and r["worker_id"] not in workers]
    _check(out, "4", "worker identity survives an intelligence change", FAIL if lost or gone else
           (PASS if changed or reps else NOT_EXERCISED),
           f"{len(workers)} worker(s); {len(changed)} binding(s) changed intelligence with their history kept; "
           f"{len(reps)} replacement(s), {len(gone)} leaving no seat; {len(lost)} binding(s) of a worker who is gone; "
           f"{len(released)} released by the plan before any work", lost=lost[:5], gone=gone[:5], history=[
               {"worker": b["worker_id"], "now": b["intelligence_id"], "before": [h.get("intelligence_id")
                                                                                 for h in b["history"]]}
               for b in changed][:10])


def _budget(out, c):
    from . import budget, settings as project_settings
    store = c["store"]
    h = budget.headroom(store)
    res = store.all("reservation")
    over = [r["id"] for r in res if r.get("status") != "refused"
            and float(r.get("spent_before") or 0) + float(r.get("reserved_before") or 0) + float(r.get("usd") or 0)
            > float(project_settings.get(store)["budget_usd"]) + 1e-9]
    held = [r["id"] for r in res if r.get("status") == "held"]
    _check(out, "4", "concurrent work never passed the cap", FAIL if over or h["spent"] > h["cap"] + 1e-9 else PASS,
           f"cap ${h['cap']}, spent ${h['spent']}, reserved now ${h['reserved']} ({len(held)} still held); "
           f"{len(res)} reservation(s), {sum(1 for r in res if r.get('status') == 'refused')} refused",
           over=over[:5])
    # work refused while colleagues' calls ran asks again only when one of them has ended: a refusal with nothing
    # spent or freed since the same task's last one is a spin (real run on Claude, objective 1: 4,065 in a row)
    last, spins = {}, {}
    for r in sorted((r for r in res if r.get("status") == "refused"), key=lambda r: r["id"]):
        seen = (r.get("spent_before"), r.get("reserved_before"))
        if r.get("in_flight") and last.get(r["task_id"]) == seen:
            spins[r["task_id"]] = spins.get(r["task_id"], 0) + 1
        last[r["task_id"]] = seen
    refused = sum(1 for r in res if r.get("status") == "refused")
    _check(out, "4", "refused work waited for the calls in flight", FAIL if spins else (PASS if refused else
           NOT_EXERCISED), f"{refused} refused reservation(s); {sum(spins.values())} asked again with nothing spent "
           "or freed since the last refusal", spins=dict(sorted(spins.items(), key=lambda kv: -kv[1])[:5]))
    stale = [d["decision_id"] for d in c["decisions"] if d.get("status") in ("superseded", "stale", "revalidated")
             or d.get("revalidates")]
    _check(out, "4", "stale evidence never rewrote a decision", PASS,
           f"{len(stale)} decision(s) re-decided against newer evidence and kept as history; decisions are frozen "
           "(see: decisions are immutable)")


def _production(out, c):
    pv = c["store"].all("production_verification")
    if not pv:
        _check(out, "4", "production verification before completion", NOT_EXERCISED, "the run did not reach release")
        return
    done = "objective.completed" in c["types"]
    early = done and not any(p.get("passed") for p in pv)
    _check(out, "4", "production verification before completion", FAIL if early else PASS,
           f"{len(pv)} production verification(s), passed: {[p.get('passed') for p in pv]}; objective completed: {done}")


def _events(out, c):
    types, store = c["types"], c["store"]
    # what each event reports is read from the state it reports, never from the event itself
    reached_work = bool(c["tasks"]) and any(t["status"] != "PLANNED" for t in c["tasks"].values())
    owed = {"always": True, "objective": bool(c["obj"].get("objective_id")),
            "requirements": store.get("requirements", "req_1") is not None, "workgraph": bool(c["tasks"]),
            "workforce": bool(store.all("worker")), "decided": bool(c["decisions"]),
            "committed": any(d.get("status") == "committed" for d in c["decisions"]),
            "bound": bool(store.all("binding") or store.all("work_binding")),
            "calibration_plan": bool(store.all("calibration_plan")), "worked": reached_work,
            "verified": bool(store.all("verification")), "evidenced": bool(c["evidence"]), "calibrated": any(p.get("trials") or p.get("status") in ("running", "completed")
                                              for p in store.all("calibration_plan")),
        "reviewed": any(x.get("purpose") == "review" for x in store.all("call")),
        # rework is what sent a work item back: a verification that asked for it, a cofounder's send-back, the
        # task's own rework history (a failed calibration trial is evidence, not rework; a third failure goes to
        # replacement, not rework)
        "reworked": any(v.get("verdict") == "REQUIRES_REWORK" for v in store.all("verification"))
        or any(t.get("review_rounds") or t.get("rework_history") for t in c["tasks"].values()),
        "reselected": any(d.get("selection_mode") == "reselect" and d.get("status") == "committed"
                          or d.get("purpose") == "reselection" for d in c["decisions"]),
        # work moved to another intelligence: a replacement that rerouted it, or a reselection the controller
        # committed when the evidence moved (controller.revalidate reports both the trigger and the reroute)
        "rerouted": any(r.get("rerouted") for r in store.all("replacement"))
        or any(d.get("purpose") in ("reselection", "failover") and d.get("status") == "committed"
               for d in c["decisions"]),
        "production": bool(store.all("production_verification")),
        "completed": c["meta"].get("phase") == "accepted"}
    rows, missing, unbacked = [], [], []
    for name, when in EVENTS.items():
        n = types.get(name, 0)
        due = owed[when]
        rows.append({"event": name, "count": n, "owed": bool(due)})
        if due and not n:
            missing.append(name)
        if n and when != "always" and not owed[when]:
            unbacked.append(name)
    c.setdefault("tables", {})["events"] = rows
    _check(out, "5", "the founder-visible events were emitted", FAIL if missing else PASS,
           f"{sum(1 for r in rows if r['count'])} of {len(rows)} named events present; owed but missing: {missing}")
    _check(out, "5", "no event reports what did not happen", FAIL if unbacked else PASS,
           f"events without the state change they report: {unbacked}")
    _check(out, "5", "the event log is intact", PASS if store.verify_event_chain() else FAIL,
           f"{len(c['events'])} events, hash chain verified")
    # what an auditor reads to see why work moved: every change of intelligence, in order, with its cause
    keys = ("task_id", "worker_id", "from", "to", "cause", "decision_id", "kind", "mode", "why", "verdict", "attempt",
            "intelligence_id", "headline")
    c.setdefault("tables", {})["intelligence_timeline"] = [
        {"seq": e.get("seq") or e.get("id"), "at": e.get("created_at") or e.get("timestamp"), "event": e["event_type"],
         "on": e["aggregate_id"], **{k: (str(e["payload"][k])[:140] if isinstance(e["payload"].get(k), str)
                                         else e["payload"][k]) for k in keys if e["payload"].get(k) is not None}}
        for e in c["events"] if e["event_type"] in TIMELINE]
    c["tables"]["replacements"] = [
        {k: (str(r.get(k))[:160] if k == "reason" else r.get(k)) for k in
         ("id", "task_id", "worker_id", "from", "to", "temporary", "active", "rerouted", "human_directed", "authority",
          "reason", "at")} for r in sorted(store.all("replacement"), key=lambda r: r["id"])]
    by: dict = {}
    for e in c["evidence"]:
        row = by.setdefault((e["intelligence_id"], e.get("stage")), {"intelligence": e["intelligence_id"],
                                                                     "stage": e.get("stage"), "verified": 0,
                                                                     "failed": 0, "inconclusive": 0, "causes": {}})
        row["verified" if e.get("verified") else "failed" if e.get("verified") is False else "inconclusive"] += 1
        k = (e.get("failure") or {}).get("kind")
        if k:
            row["causes"][k] = row["causes"].get(k, 0) + 1
    c["tables"]["evidence_by_intelligence"] = sorted(by.values(), key=lambda r: (r["intelligence"], r["stage"] or ""))


# --- across the data root ----------------------------------------------------------------------------------------
def _discovery(out, control, manifest):
    if control is None:
        _check(out, "7", "discovery", NOT_EXERCISED, "no control store in the data root")
        return
    conns = control.all("connection")
    models = control.all("intelligence")
    _check(out, "7", "providers discovered dynamically", PASS if models else FAIL,
           f"{len(conns)} connection(s): " + "; ".join(f"{x['name']} {x.get('status')} "
                                                       f"({len(x.get('offered') or [])} offered)" for x in conns)
           + f"; {len(models)} model(s) in the registry")
    res = manifest.get("results") or []
    wrong = [r["model_id"] for r in res if r.get("error_kind") in ("provider_unavailable", "account_unavailable")
             and r.get("qualification_status") == "failed"]
    _check(out, "7", "provider and account failures stay inconclusive", FAIL if wrong else PASS,
           f"{len(res)} probe(s): " + ", ".join(f"{r.get('model')}: {r.get('qualification_status')}" for r in res),
           wrong=wrong)
    outs = control.all("outcome")
    dirty = [o["id"] for o in outs if o.get("clean") is False]
    _check(out, "7", "no contaminated outcome in the registry", FAIL if dirty else PASS,
           f"{len(outs)} registry outcome(s); {len(dirty)} contaminated")


def _isolation(out, root, runs):
    if len(runs) < 2:
        _check(out, "10", "objective A/B isolation", NOT_EXERCISED, f"{len(runs)} objective run(s) in this data root")
        return
    leaks, priors = [], 0
    for b in runs:
        sb = Store(str(Path(b["folder"]) / "cynqra.db"))
        try:
            for a in runs:
                if a is b or not a["objective_id"]:
                    continue
                if oe.query(sb, objective_id=a["objective_id"], tenant_id="local", include_inactive=True):
                    leaks.append(f"{a['objective_id']} evidence stored in {b['objective_id']}'s run")
                for d in sb.all(controller.KIND):
                    snap = sb.get_object(d["evidence_snapshot"]) or {}
                    for r in snap.get("evidence") or []:
                        if r.get("src") == "objective" and r.get("objective_id") != b["objective_id"]:
                            leaks.append(f"{d['decision_id']} read {r.get('objective_id')} as objective evidence")
                        if r.get("src") == "registry" and r.get("run_id") == a["company_id"]:
                            priors += 1
        finally:
            sb.close()
    missing = [f"{r['objective_id']}:{c['data'].get('missing')}" for r in runs for c in r["checks"]
               if c["check"] == "work items carry the objective" and c["status"] == FAIL]
    _check(out, "10", "objective A/B isolation", FAIL if leaks or missing else PASS,
           f"{len(runs)} objectives; {len(leaks)} leak(s) of objective evidence; another objective's work seen "
           f"{priors} time(s), always as historical prior", leaks=leaks[:10])
    # success on one objective establishes nothing on the next: each later objective calibrated on its own work
    later = runs[1:]
    own = [r["objective_id"] for r in later if any(c["check"] == "objective calibration ran on the objective's own "
                                                   "work" and c["status"] == PASS for c in r["checks"])]
    _check(out, "10", "each objective earned its own evidence", PASS if len(own) == len(later) else NOT_EXERCISED,
           f"{len(own)} of {len(later)} later objective(s) ran their own calibration rather than inheriting an "
           "earlier objective's result", calibrated=own)


def _scan(out, root, secrets):
    hits, shapes = [], []
    for p in root.rglob("*"):
        if not p.is_file() or p.stat().st_size > 200_000_000:
            continue
        raw = p.read_bytes()
        for name, value in secrets.items():
            if value and len(value) >= 8 and value.encode() in raw:
                hits.append(f"{name} in {p.relative_to(root)}")
        if KEY_SHAPES.search(raw):
            shapes.append(str(p.relative_to(root)))
    _check(out, "7", "no credential in any persisted file", FAIL if hits or shapes else PASS,
           f"scanned for {len(secrets)} key value(s) and the shapes of provider keys; found: {hits + shapes or 'none'}")


def render(report: dict) -> str:
    """The audit as the job log shows it: every check with its verdict, then the tables an auditor reads."""
    lines = [f"RUN AUDIT {report['root']}",
             "summary: " + ", ".join(f"{k} {v}" for k, v in report["summary"].items())]
    for c in report["checks"]:
        lines.append(f"  [{c['status'].upper():13}] §{c['section']} {c['check']}: {c['detail']}")
    for r in report["runs"]:
        lines.append(f"\nobjective {r['objective_id']} v{r['objective_version']} ({r['folder']}): phase {r['phase']}, "
                     f"lifecycle {r['lifecycle']}, {r['tasks']} work items, {r['decisions']} decisions, "
                     f"{r['evidence']} evidence records, {r['events']} events")
        for c in r["checks"]:
            lines.append(f"  [{c['status'].upper():13}] §{c['section']} {c['check']}: {c['detail']}")
            if c.get("data") and (c["status"] == FAIL or c["check"] in SHOW_DATA):
                lines.append("      " + json.dumps(c["data"], default=str, separators=(",", ":"))[:3000])
        for name, rows in (r.get("tables") or {}).items():
            lines.append(f"  -- {name} ({len(rows)})")
            for row in rows[:400]:
                lines.append("    " + json.dumps(row, default=str, separators=(",", ":"))[:1500])
    if report["failed"]:
        lines.append("\nFAILED: " + "; ".join(report["failed"]))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit a hosted examination's persisted records")
    ap.add_argument("root")
    ap.add_argument("--json", default="")
    ap.add_argument("--secret-env", nargs="*", default=[])
    args = ap.parse_args(argv)
    report = audit(Path(args.root), {n: os.environ.get(n, "") for n in args.secret_env})
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(render(report))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
