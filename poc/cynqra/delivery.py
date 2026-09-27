"""Delivery and the record of the run: the transition, the final report, the metrics, replay, the organization graph
and the export bundle.

Section 8, the last screen: delivered artifacts, the budget forecast against the actual, how every worker and
every intelligence performed, and every intelligence change. Nothing here is locked in: the export holds the
repository, the decisions, the event log, the organization and the infrastructure configuration.
"""
from __future__ import annotations

import json
import time
import zipfile
from datetime import datetime
from pathlib import Path

from . import budget, performance, policy, roles
from .db import IST, digest, now

ESCALATIONS_PER_DAY = 5  # D-29


def live_url(run) -> str | None:
    live = [d for d in run.store.all("deployment") if d["status"] == "live"]
    return live[-1]["url"] if live else None


def metrics(run) -> dict:
    tasks = run.tasks()
    verified = [t for t in tasks if t["status"] == "VERIFIED"]
    protos = [p for p in run.store.all("protocol") if p["sender"].startswith("w_")]
    ver = run.store.all("verification")
    m = run.meta
    start, end = m.get("started_at"), m.get("delivered_at")
    today = datetime.now(IST).date().isoformat()
    return {
        "founder_interventions": run.count("intervention"),
        "tasks_total": len(tasks),
        "tasks_verified": len(verified),
        "defects_caught_before_verified": len([v for v in ver if v["verdict"] in ("REQUIRES_REWORK", "REQUIRES_HUMAN")]),
        "blockers_cleared_without_founder": len([b for b in run.store.all("blocker_cleared") if not b["founder_involved"]]),
        "actions_stopped_by_policy": len([a for a in run.store.all("action") if a["status"] == "denied"]),
        "fixed_by_workers_own_checks": len([e for e in run.store.events() if e["event_type"] == "worker.self_checked"
                                            and not e["payload"].get("passed")]),
        "worker_protocol_objects": len(protos),
        "protocol_objects_per_verified_task": round(len(protos) / len(verified), 1) if verified else None,
        "escalations_today": len([d for d in run.store.all("decision") if d.get("source", "").startswith("w_")
                                  and d.get("created_day") == today]),
        "escalation_budget": ESCALATIONS_PER_DAY,
        "seconds_to_live": round(end - start, 1) if start and end else None,
        "events": run.store.count_events(),
        # Stage 9: what verification itself achieved
        "first_pass_rate": round(sum(1 for t in verified if not t["attempts"]) / len(verified), 3) if verified else None,
        "reworks": len([v for v in ver if v["verdict"] == "REQUIRES_REWORK"]),
        "defect_escapes": run.count("escape"),
        "false_rejections": len([v for v in ver if v.get("false_rejection")]),
        "verification_seconds": round(sum(float(v.get("seconds") or 0) for v in ver), 1),
        "protocol_violations": run.count("violation"),
        "intelligence_changes": run.count("replacement"),
        "spent_usd": budget.ledger(run.store)["spent_total"],
    }


def deliver(run) -> dict:
    export_path = export(run)
    ec = budget.actual(run.store, run.store.get("forecast", "current"))
    tr = {"id": "tr_1", "company_id": run.cid, "problem": run.objective()["statement"],
          "evidence_refs": [v["id"] for v in run.store.all("verification")],
          "proposed_change": "Synthesize the organization the objective needs, staff it with intelligence and run the "
                             "approved roadmap to a live release.",
          "expected_result": run.objective()["structured"]["success_criteria"],
          "cost": f"${ec['total_actual']:.4f} of the ${ec['cap_usd']:.2f} budget", "risk": "HIGH (production deploy)",
          "reversibility": "Stop the live process; the export holds everything.",
          "authority_check": "every MEDIUM and HIGH step approved by the founder", "approval": None,
          "actual_result": f"Live at {live_url(run)}", "confidence": "high", "metrics": metrics(run),
          "export": Path(export_path).name}
    run.store.put("transition", "tr_1", tr)
    run.event("transition.proposed", "transition", "tr_1", {"tasks": len(run.tasks()), "cost_usd": ec["total_actual"]})
    run.decision("accept_delivery", problem="Every task is verified and the product is live.",
                 recommendation="Accept delivery. The export bundle is ready to download.", risk="LOW",
                 confidence="high", cost="none", evidence=[live_url(run) or "", Path(export_path).name],
                 change="Anything in the live product that does not meet the objective.", source="orchestrator")
    run.set_meta(phase="delivered", delivered_at=time.time())
    return {"did": "delivered"}


def after_accept(run, d: dict, action: str) -> None:
    tr = run.store.get("transition", "tr_1")
    if action == "approve":
        tr["approval"] = {"by": "founder", "at": now(), "decision": d["id"]}
        run.store.put("transition", "tr_1", tr)
        run.event("transition.approved", "transition", "tr_1", {}, actor="founder", actor_type="human", authority="founder")
        run.event("transition.executed", "transition", "tr_1", {})
        run.event("outcome.recorded", "outcome", "out_1", {"transition": "tr_1", "live": bool(live_url(run))})
        company = run.store.get("company", run.cid)
        company["stage"] = "PILOT"
        run.store.put("company", run.cid, company)
        run.set_meta(phase="accepted")
    else:
        run.event("transition.rejected", "transition", "tr_1", {"label": d["outcome_label"]}, actor="founder",
                  actor_type="human", authority="founder")
        run.set_meta(phase="delivered", notice="Delivery not accepted. The product stays live and your note is on "
                                               "record. Iterating on a delivered product is outside this proof of concept.")


def final_report(run) -> dict:
    src = run.paths["main"] if any(run.paths["main"].iterdir()) else run.paths["integration"]
    files = sorted(p.relative_to(src).as_posix() for p in src.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    forecast = run.store.get("forecast", "current")
    return {"artifacts": files, "live_url": live_url(run),
            "exports": sorted(p.name for p in run.paths["exports"].glob("*.zip")),
            "requirements": {"total": len((run.requirements() or {}).get("requirements", [])),
                             "uncovered_by_tasks": (run.store.get("plan", "plan_1") or {}).get("uncovered_requirements", [])},
            "economics": budget.actual(run.store, forecast), "forecast": forecast,
            "performance": performance.all_cards(run.store, run.registry),
            "intelligence_changes": run.store.all("replacement"), "evaluations": run.store.all("evaluation"),
            "company_pack": company_pack(run), "metrics": metrics(run)}


def company_pack(run) -> dict:
    """What the founding team hands the CEO: every document, who wrote it and how it was verified; the decisions the
    CEO made and the ones the team settled; and how few times the CEO was needed."""
    docs = []
    for t in run.tasks():
        if t["kind"] != "document":
            continue
        w = run.worker(t["owner_worker_id"]) or {}
        docs.append({"task": t["id"], "title": t["title"], "author": w.get("title", t["owner_worker_id"]),
                     "types": [roles.DOC_TYPES[d]["title"] for d in t.get("documents") or [] if d in roles.DOC_TYPES],
                     "files": [o.get("file") for o in t.get("outputs") or [] if isinstance(o, dict)],
                     "verified": t["status"] == "VERIFIED"})
    decided = [d for d in run.store.all("decision") if d["status"] != "pending"]
    return {"documents": docs,
            "ceo_decisions": [{"kind": d["kind"], "problem": d["problem"][:200], "outcome": d.get("outcome_label")}
                              for d in decided],
            "settled_by_the_team": len([b for b in run.store.all("blocker_cleared") if not b["founder_involved"]]),
            "ceo_interventions": run.count("intervention")}


def replay(run, task_id: str) -> dict:
    t = run.task(task_id)
    events = run.store.events(correlation_id=task_id)
    actions = [a for a in run.store.all("action") if a["task_id"] == task_id]
    calls = [c for c in run.store.all("call") if c["task_id"] == task_id]
    verifs = [v for v in run.store.all("verification") if v["task_id"] == task_id]
    protos = [run.store.get_object(e["protocol_hash"]) for e in events if e.get("protocol_hash")]
    w = run.worker(t["owner_worker_id"])
    facts = {
        "actor": f"{w['id']}, role {w['role']}",
        "authority": t["authority_policy_id"],
        "policy_decisions": [f"{a['action_type']}: {a['policy_decision']}" for a in actions],
        "context": t.get("handoff_hash"),
        "intelligence": sorted({c["label"] for c in calls}),
        "tools": (sorted({a["action_type"] for a in actions if a["status"] in ("executed", "approved")})
                  or (["none: a founder decision, no tool runs"] if t["kind"] == "decision" else [])),
        "result": [o.get("file") or o for o in (t.get("outputs") or [])] or ([t["decision_id"]] if t.get("decision_id") else []),
        "verification": [f"{v['verdict']} by {v['method']}, {len(v['test_ids'])} test ids" for v in verifs],
    }
    missing = [k for k, v in facts.items() if not v]
    return {"task_id": task_id, "facts": facts, "missing": missing, "complete": not missing, "events": len(events),
            "protocols": [p for p in protos if p], "test_ids": sorted({i for v in verifs for i in v["test_ids"]})}


class GraphError(ValueError):
    pass


def graph(run, question: str, subject: str) -> dict:
    if question == "approves":
        return policy.who_may(subject)
    t = run.task(subject)
    if question == "owns":
        return {"task": subject, "owner": t["owner_worker_id"], "reports_to": t["accountable"]}
    if question == "depends":
        return {"task": subject, "depends_on": t["dependencies"],
                "needed_by": [x["id"] for x in run.tasks() if subject in x["dependencies"]]}
    raise GraphError("ask owns, depends or approves")


def export(run) -> str:
    ts = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
    path = run.paths["exports"] / f"cynqra_export_{ts}.zip"
    manifest = {"format": "cynqra-export-1", "company_id": run.cid, "created_at": now(), "categories": {}, "files": {}}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        def add(arc: str, data: bytes, cat: str):
            z.writestr(arc, data)
            manifest["files"][arc] = digest(data)
            manifest["categories"][cat] = manifest["categories"].get(cat, 0) + 1
        src = run.paths["main"] if any(run.paths["main"].iterdir()) else run.paths["integration"]
        for p in sorted(src.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                rel = p.relative_to(src).as_posix()
                add(f"repository/{rel}", p.read_bytes(), "documents_and_designs" if rel.startswith("docs/") else "repository")
        add("decisions.json", json.dumps(run.store.all("decision"), indent=1).encode(), "decision_history")
        add("events.jsonl", "\n".join(json.dumps(e) for e in run.store.events()).encode(), "event_log")
        org = {"organization": run.store.get("organization", "org_1"), "workers": run.workers(),
               "intelligence_bindings": run.store.all("binding"),
               "proposal": run.store.get("proposal", (run.store.get("organization", "org_1") or {}).get("proposal", "")),
               "policy_version": policy.POLICY_VERSION, "matrix": policy.MATRIX, "risk": policy.RISK}
        add("organization.json", json.dumps(org, indent=1).encode(), "organization_configuration")
        add("objective.json", json.dumps({"objective": run.objective(), "requirements": run.requirements()},
                                         indent=1).encode(), "organization_configuration")
        add("roadmap.json", json.dumps({"plan": run.store.get("plan", "plan_1"), "tasks": run.tasks(),
                                        "forecast": run.store.get("forecast", "current")}, indent=1).encode(),
            "organization_configuration")
        add("protocols.json", json.dumps([run.store.get_object(p["hash"]) for p in run.store.all("protocol")],
                                         indent=1).encode(), "decision_history")
        infra = {"run": "python app.py", "env": {"PORT": "port to serve on", "DATA_FILE": "path to the JSON data file"},
                 "deployments": [{k: d[k] for k in ("id", "status", "url")} for d in run.store.all("deployment")]}
        add("infrastructure.json", json.dumps(infra, indent=1).encode(), "infrastructure_configuration")
        manifest["non_portable"] = ["The POC deploys to a local process only. There are no cloud resources to move."]
        z.writestr("manifest.json", json.dumps(manifest, indent=1))
    run.event("state.changed", "company", run.cid, {"export": path.name, "files": len(manifest["files"])}, actor="export")
    return str(path)
