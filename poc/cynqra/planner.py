"""The Execution Planner: the objective as an executable organizational plan (Stage 5).

The model proposes milestones, workstreams and tasks: each with an owner, acceptance criteria, the requirements it
satisfies, its dependencies and, for documents, the document types it writes. The platform checks the proposal
against the catalog (validate_plan) and then adds what is never the model's call (enrich):

  risk and verification   from the task type: how the task is proven done
  tools                   from the task type: the gateway actions its owner will use
  accountability          the owner and the worker it reports to
  coordination            who hands the task over, who clears its Blockers
  escalation              the conditions under which work leaves the organization for the founder
  sequencing              the critical path through the dependencies
"""
from __future__ import annotations

import re

from . import policy, roles
from .db import now
from .intelligence import IntelligenceError, as_int, ask
from .objective import _slug_list

TOOLS = {"document": ["write_file"], "decision": ["product_rule_decision"], "code": ["write_file", "run_tests"],
         "forecast": ["write_file", "run_tests"], "review_merge": ["run_tests", "merge_to_main"],
         "deploy": ["deploy_production"]}
GATES = {
    "document": "The document verifier: the sections each document type needs, the requirement ids the task covers, "
                "and for briefs and specifications the objective's constraints and success criteria",
    "decision": "Founder review (MEDIUM risk)",
    "code": "Automated tests in a clean copy with every earlier test rerun; the delivery contract for the app",
    "forecast": "Its tests, then the platform's backtest: its error on held-out days against a seasonal baseline",
    "review_merge": "The founder approves the merge (MEDIUM); the full suite then runs on main",
    "deploy": "Build, test, preview, health and smoke checks; the founder approves the deploy (HIGH)",
}
ESCALATION_CONDITIONS = [
    "A task fails verification three times and no other intelligence passes its regression check within the budget.",
    "A task has already had two intelligence changes and fails again.",
    "A worker's model stops answering and no other model can take its work.",
    "A Blocker cannot be cleared by any worker allowed to answer it.",
    "Policy denies an action a task cannot finish without.",
    "Spending reaches the budget cap: the breaker pauses all work.",
    "Every MEDIUM action (product rules, merges) and every HIGH action (production deploy) needs the founder.",
]


def validate_plan(plan: dict, workers: list[dict], requirement_ids: list[str] | None = None) -> dict:
    """The platform owns the rubric: a task type's risk, its verifier, and which roles may own it are not the model's
    call. Task ids are renumbered t_01, t_02 in plan order and dependencies follow them; model text never becomes an
    identifier. Milestones, acceptance criteria and document types a model left out are derived and marked so."""
    if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list) or not plan["tasks"]:
        raise IntelligenceError("plan has no tasks")
    if not all(isinstance(t, dict) for t in plan["tasks"]):
        raise IntelligenceError("every task must be an object")
    by_id = {w["id"]: w for w in workers}
    rename = {}
    for i, t in enumerate(plan["tasks"], start=1):
        old = str(t.get("id") or "").strip()
        if old:
            rename[old] = f"t_{i:02d}"
        t["id"] = f"t_{i:02d}"
    known_req = set(requirement_ids or [])
    ids, kinds, tasks = set(), [], []
    for t in plan["tasks"]:
        for key in ("workstream_id", "kind", "owner_worker_id", "title"):
            if not str(t.get(key) or "").strip():
                raise IntelligenceError(f"{t['id']} is missing {key}")
        kind, owner_id = str(t["kind"]).strip(), str(t["owner_worker_id"]).strip()
        if kind not in roles.TASK_TYPES:
            raise IntelligenceError(f"{t['id']}: unknown task type {kind}; use one of {', '.join(roles.TASK_TYPES)}")
        owner = by_id.get(owner_id)
        if owner is None:
            raise IntelligenceError(f"{t['id']}: {owner_id} is not a worker in this organization")
        if kind not in roles.role(owner["role"])["owns"]:
            raise IntelligenceError(f"{t['id']}: a {kind} task cannot be owned by {owner_id} ({owner['role']}); it "
                                    f"can be owned by {', '.join(roles.owners_of(kind, workers)) or 'nobody here'}")
        deps = t.get("dependencies") or []
        deps = [d for d in re.split(r"[,\s]+", deps) if d] if isinstance(deps, str) else deps
        if not isinstance(deps, list):
            raise IntelligenceError(f"{t['id']}: dependencies must be a list")
        clean_deps = []
        for dep in deps:
            dep = rename.get(str(dep).strip(), str(dep).strip())
            if dep not in ids:
                raise IntelligenceError(f"{t['id']} depends on {dep}, which is not an earlier task")
            if dep not in clean_deps:
                clean_deps.append(dep)
        crit = t.get("acceptance_criteria")
        crit = [crit] if isinstance(crit, str) else crit if isinstance(crit, list) else []
        crit = [str(x).strip() for x in crit if str(x).strip()]
        out = {"id": t["id"], "workstream_id": str(t["workstream_id"]).strip(), "kind": kind, "owner_worker_id": owner_id,
               "title": str(t["title"]).strip(), "inputs": str(t.get("inputs") or ""),
               "expected_output": str(t.get("expected_output") or ""), "dependencies": clean_deps,
               "acceptance_criteria": crit or [str(t.get("expected_output") or t["title"])],
               "acceptance_derived": not crit, "deadline_day": as_int(t.get("deadline_day"), 1) or 1,
               "requirement_ids": [x for x in _slug_list(t.get("requirement_ids")) if not known_req or x in known_req],
               "milestone_id": str(t.get("milestone_id") or "").strip()}
        if kind == "document":
            mine = roles.role(owner["role"])["documents"]
            docs = [d for d in _slug_list(t.get("documents")) if d in mine]
            out["documents"], out["documents_derived"] = (docs, False) if docs else (mine[:1], True)
            if not out["documents"]:
                raise IntelligenceError(f"{t['id']}: {owner_id} writes no document type")
        tasks.append(out)
        ids.add(out["id"])
        kinds.append(kind)
    for kind, n in (("review_merge", 1), ("deploy", 1)):
        if kinds.count(kind) != n:
            raise IntelligenceError(f"plan needs exactly {n} {kind} task")
    if kinds[-1] != "deploy":
        raise IntelligenceError("deploy must be the last task")
    if "code" not in kinds:
        raise IntelligenceError("plan has no code task; one of them owns app.py and the web page")
    merge = next(t for t in tasks if t["kind"] == "review_merge")
    builds = [t["id"] for t in tasks if t["kind"] in roles.BUILD_TYPES]
    if any(tasks.index(merge) < [x["id"] for x in tasks].index(b) for b in builds):
        raise IntelligenceError("review_merge must come after every build task")
    ws = [{"id": str(w["id"]).strip(), "name": str(w.get("name") or w["id"]).strip()}
          for w in plan.get("workstreams") or [] if isinstance(w, dict) and str(w.get("id") or "").strip()]
    for t in tasks:
        if t["workstream_id"] not in {w["id"] for w in ws}:
            ws.append({"id": t["workstream_id"], "name": t["workstream_id"]})
    ms = [{"id": str(m["id"]).strip(), "name": str(m.get("name") or m["id"]).strip(), "due_day": as_int(m.get("due_day"), 0)}
          for m in plan.get("milestones") or [] if isinstance(m, dict) and str(m.get("id") or "").strip()]
    if not ms:  # one milestone per workstream, in plan order, said to be derived
        ms = [{"id": "m_" + w["id"], "name": w["name"], "due_day": 0, "derived": True} for w in ws]
        for t in tasks:
            t["milestone_id"] = "m_" + t["workstream_id"]
    mids = {m["id"] for m in ms}
    for t in tasks:
        if t["milestone_id"] not in mids:
            t["milestone_id"] = ms[-1]["id"] if t["kind"] in ("review_merge", "deploy") else ms[0]["id"]
    for m in ms:
        own = [t for t in tasks if t["milestone_id"] == m["id"]]
        m["task_ids"] = [t["id"] for t in own]
        m["due_day"] = max([m["due_day"]] + [t["deadline_day"] for t in own])
    return {"workstreams": ws, "milestones": [m for m in ms if m["task_ids"]], "tasks": tasks,
            "uncovered_requirements": [r for r in (requirement_ids or [])
                                       if not any(r in t["requirement_ids"] for t in tasks)]}


def critical_path(tasks: list[dict]) -> list[str]:
    longest: dict[str, list[str]] = {}
    for t in tasks:  # dependencies only name earlier tasks
        best = max((longest[d] for d in t["dependencies"] if d in longest), key=len, default=[])
        longest[t["id"]] = best + [t["id"]]
    return max(longest.values(), key=len, default=[])


def enrich(plan: dict, workers: list[dict]) -> dict:
    by_id = {w["id"]: w for w in workers}
    boss = roles.assigner(workers)
    answer = roles.answerers(workers)
    for t in plan["tasks"]:
        owner = by_id[t["owner_worker_id"]]
        manager = t["owner_worker_id"] == boss or roles.role(owner["role"])["assigns"]
        t.update({"risk_tier": roles.risk(t["kind"]), "verification_gate": GATES[t["kind"]], "tools": TOOLS[t["kind"]],
                  "accountable": owner["reports_to"], "handoff_from": "orchestrator" if manager else boss,
                  "blockers_to": [w for w in answer if w != t["owner_worker_id"]] or [boss], "escalates_to": "founder",
                  "authority_policy_id": f"{policy.POLICY_VERSION}:{owner['role']}"})
    plan.update({"critical_path": critical_path(plan["tasks"]), "escalation_conditions": list(ESCALATION_CONDITIONS),
                 "reporting": {w["id"]: w["reports_to"] for w in workers},
                 "coordination": {"assigns": boss, "answers_blockers": answer,
                                  "protocols": ["Handoff", "Blocker", "Approval", "Escalation"]}})
    return plan


def plan(run, note: str = "") -> dict:
    """Stage 5 for the approved organization. Tasks keep their ids across a revised roadmap; the new plan replaces
    the old one before any work starts."""
    workers = run.workers()
    boss = roles.assigner(workers)
    rids = [r["id"] for r in run.requirements()["requirements"]]
    p, usage = ask(lambda feedback: run.intel.plan(run.objective_ctx(), workers, run.requirements(), note=note,
                                                   feedback=feedback, planner=boss, persona=run.persona(boss)),
                   lambda d: validate_plan(d, workers, rids))
    run.record_call("plan", boss, "plan", usage)
    p = enrich(p, workers)
    order = []
    for i, t in enumerate(p["tasks"]):
        t.update({"company_id": run.cid, "objective_id": "obj_1", "context": f"objective v{run.objective()['version']}",
                  "status": "PLANNED", "attempts": 0, "work_calls": 0, "blockers": 0, "feedback": "", "handoff_hash": None,
                  "answers": [], "outputs": [], "decision_id": None, "seq": i, "created_at": now()})
        run.save_task(t)
        order.append(t["id"])
        run.event("task.created", "task", t["id"], {"kind": t["kind"], "risk_tier": t["risk_tier"],
                  "owner_worker_id": t["owner_worker_id"], "dependencies": t["dependencies"],
                  "milestone": t["milestone_id"]}, actor=boss, actor_type="worker", correlation_id=t["id"])
    record = {k: p[k] for k in ("workstreams", "milestones", "critical_path", "escalation_conditions", "reporting",
                                "coordination", "uncovered_requirements")}
    run.store.put("plan", "plan_1", {"id": "plan_1", "order": order, "note": note, **record})
    return run.store.get("plan", "plan_1")
