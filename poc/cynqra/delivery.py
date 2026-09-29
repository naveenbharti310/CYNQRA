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

from . import budget, lessons, performance, policy, roles
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
        "sent_back_by_cofounders": sum(int(t.get("review_rounds") or 0) for t in tasks),
        "reviewed_by_cofounders": len([t for t in tasks if any(r["verdict"] == "approve" for r in t.get("reviews") or [])]),
        "review_concerns": [{"task": t["id"], **t["review_concern"]} for t in tasks if t.get("review_concern")],
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
    n = int(run.meta.get("cycle") or 1)
    tid = f"tr_{n}"
    tr = {"id": tid, "cycle": n, "company_id": run.cid, "problem": run.objective()["statement"],
          "evidence_refs": [v["id"] for v in run.store.all("verification")],
          "proposed_change": "Synthesize the organization the objective needs, staff it with intelligence and run the "
                             "approved roadmap to a live release.",
          "expected_result": run.objective()["structured"]["success_criteria"],
          "cost": f"{budget.dollars(ec['total_actual'])} of the {budget.dollars(ec['cap_usd'])} budget",
          "risk": "HIGH (production deploy)",
          "reversibility": "Stop the live process; the export holds everything.",
          "authority_check": "every MEDIUM and HIGH step approved by the founder", "approval": None,
          "actual_result": f"Live at {live_url(run)}", "confidence": "high", "metrics": metrics(run),
          "export": Path(export_path).name}
    run.store.put("transition", tid, tr)
    run.event("transition.proposed", "transition", tid, {"tasks": len(run.tasks()), "cost_usd": ec["total_actual"],
              "cycle": n})
    run.decision("accept_delivery", problem="Every task is verified and the product is live."
                 + (f" This is cycle {n}; the release before it stays as the way back." if n > 1 else ""),
                 recommendation="Accept delivery. The export bundle is ready to download.", risk="LOW",
                 confidence="high", cost="none", evidence=[live_url(run) or "", Path(export_path).name],
                 change="Anything in the live product that does not meet the objective.", source="orchestrator")
    run.set_meta(phase="delivered", delivered_at=time.time())
    return {"did": "delivered"}


def after_accept(run, d: dict, action: str) -> None:
    tid = f"tr_{int(run.meta.get('cycle') or 1)}"
    tr = run.store.get("transition", tid)
    if action == "approve":
        tr["approval"] = {"by": "founder", "at": now(), "decision": d["id"]}
        run.store.put("transition", tid, tr)
        run.event("transition.approved", "transition", tid, {}, actor="founder", actor_type="human", authority="founder")
        run.event("transition.executed", "transition", tid, {})
        run.event("outcome.recorded", "outcome", "out_" + tid[3:], {"transition": tid, "live": bool(live_url(run))})
        lessons.record(run)
        company = run.store.get("company", run.cid)
        company["stage"] = "PILOT"
        run.store.put("company", run.cid, company)
        run.set_meta(phase="accepted")
    else:
        run.event("transition.rejected", "transition", tid, {"label": d["outcome_label"]}, actor="founder",
                  actor_type="human", authority="founder")
        run.set_meta(phase="delivered", notice="Delivery not accepted. The product stays live and your note is on "
                                               "record. Start a new cycle with what to change.")


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


FOUNDATIONS = [
    # (what, why, the verified document types that prepare it, when it applies)
    ("Register the company", "Contracts, a bank account and investment need a legal company.", ["risk_compliance"],
     "company"),
    ("Make sure the company owns the code and the brand", "Investors and buyers check it first; the export holds all "
     "the code, and whoever builds on it should sign that the company owns what they make.", [], "always"),
    ("A privacy policy, and what data you keep", "The product holds people's data.", ["risk_compliance", "threat_model"],
     "data"),
    ("Terms for your customers", "What customers pay for and what you promise them.", ["risk_compliance"], "company"),
    ("Security basics", "Who can reach the product and its data, and what happens if a key leaks.",
     ["threat_model", "architecture", "runbook"], "always"),
    ("Tax registration and invoicing", "Selling means charging and reporting tax.", ["financial_model"], "company"),
]


def foundations(run) -> list[dict]:
    """The company's foundations: what a real company must have in place, whether the team's verified work prepared
    it, and that a qualified professional should review it before it is relied on. Cynqra prepares; the founder
    acts."""
    req = (run.requirements() or {}).get("requirements", [])
    areas = {r["area"] for r in req}
    company = bool(areas & {"business", "finance", "market"})
    data = bool(areas & {"data", "security", "legal"}) or any("data" in r["text"].lower() for r in req)
    done = {d for t in run.tasks() if t["kind"] == "document" and t["status"] == "VERIFIED" for d in t.get("documents") or []}
    out = []
    for what, why, docs, when in FOUNDATIONS:
        if (when == "company" and not company) or (when == "data" and not data):
            continue
        prepared = [roles.DOC_TYPES[d]["title"] for d in docs if d in done]
        out.append({"what": what, "why": why, "prepared_in": prepared,
                    "status": ("prepared: " + ", ".join(prepared) + "; a professional should review it") if prepared
                    else "to do: only you can do this; a professional should advise"})
    return out


def company_pack(run) -> dict:
    """What the founding team hands the CEO: the outcome and how the founder will know it worked; the guesses the idea
    depends on and which were tested; the business numbers the platform recomputed; the next steps only the founder
    can take; every document, who wrote it and how it was verified; the decisions the CEO made and the ones the team
    settled; and how few times the CEO was needed."""
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
    title = lambda tid: (run.store.get("task", tid) or {}).get("title", "") if tid else ""  # noqa: E731
    workers = run.workers()
    org = [{"cofounder": c["title"], "why": c.get("why", ""),
            "team": [{"title": w["title"], "why": w.get("why", "")} for w in workers if w.get("reports_to") == c["id"]]}
           for c in workers if c.get("tier") == "cofounder"]
    req = run.requirements() or {}
    plan = run.store.get("plan", "plan_1") or {}
    status = {t["id"]: t["status"] for t in run.tasks()}
    def tested(a):  # a guess only a person can test is never called proven by desk work
        done = a.get("tasks") and all(status.get(x) == "VERIFIED" for x in a["tasks"])
        if not a.get("tasks"):
            return "no task tests it"
        if not done:
            return "not tested yet"
        return "desk work checked; your step still needed" if a.get("founder_step") else "passed its checks"
    guesses = [dict(a, tested=tested(a)) for a in plan.get("assumption_tests") or []]
    checked = [v for v in run.store.all("verification") if v["verdict"] == "VERIFIED" and (v.get("checks") or {}).get("numbers")]
    return {"outcome": {"outcomes": req.get("outcomes") or [], "measures": req.get("measures") or []},
            "foundations": foundations(run),
            "guesses": guesses,
            "your_next_steps": [{"guess": a["id"], "step": a["founder_step"]} for a in guesses if a.get("founder_step")],
            "numbers": checked[-1]["checks"]["numbers"] if checked else None,
            "organization": org, "documents": docs,
            "ceo_decisions": [{"kind": d["kind"], "problem": d["problem"][:200], "outcome": d.get("outcome_label"),
                               "status": d["status"], "task": title(d.get("task_id"))}
                              for d in decided if d.get("resolved_by") == "founder"],
            "settled_for_you": [{"kind": d["kind"], "problem": d["problem"][:200], "status": d["status"],
                                 "task": title(d.get("task_id")),
                                 "by": (run.worker(d["resolved_by"]) or {}).get("title", d["resolved_by"])}
                                for d in decided if d.get("resolved_by") not in (None, "founder")],
            "ceo_informed": [{k: n[k] for k in ("kind", "headline", "detail", "usd_difference")}
                             for n in run.store.all("ceo_notice")],
            "settled_by_the_team": len([b for b in run.store.all("blocker_cleared") if not b["founder_involved"]]),
            "sent_back_by_cofounders": sum(int(t.get("review_rounds") or 0) for t in run.tasks()),
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
    if t.get("reviews"):
        facts["reviews"] = [f"{r['verdict']} by {r['by']}: {r['note'][:160]}" for r in t["reviews"]]
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
