"""The Execution Planner: the objective as an executable organizational plan (Stage 5).

The model proposes milestones, workstreams and tasks: each with an owner, acceptance criteria, the requirements it
satisfies, its dependencies and, for documents, the document types it writes. The platform checks the proposal
against the catalog (validate_plan) and then adds what is never the model's call (enrich):

  risk and verification   from the task type: how the task is proven done
  tools                   from the task type: the gateway actions its owner will use
  accountability          the owner and the cofounder it reports to
  coordination            cofounders run their areas: the owner's cofounder hands the task over, is the first to
                          answer its Blockers, and reviews the work before it counts (a cofounder's own task comes
                          straight from the approved roadmap and is not reviewed by a peer)
  escalation              the conditions under which work leaves the organization for the founder
  sequencing              the critical path through the dependencies
"""
from __future__ import annotations

import re

from . import policy, roles
from .db import now
from .intelligence import PLAN_MAX_TASKS, PLAN_MAX_WAVES, IntelligenceError, as_int, ask
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
    "Every HIGH action (production deploy) and every MEDIUM action that cannot be undone (a rule on money or law) "
    "needs the founder; a MEDIUM action that can be undone (a merge, a product rule) is settled by the accountable "
    "cofounder and the founder is told.",
]


def validate_plan(plan: dict, workers: list[dict], requirement_ids: list[str] | None = None, start: int = 1,
                  done: set[str] | None = None) -> dict:
    """The platform owns the rubric: a task type's risk, its verifier, and which roles may own it are not the model's
    call. Task ids are renumbered t_01, t_02 in plan order and dependencies follow them; model text never becomes an
    identifier. Milestones, acceptance criteria and document types a model left out are derived and marked so. A later
    cycle's tasks are numbered after the earlier ones (start), and a dependency on work already done (done) is
    dropped: that work is finished."""
    if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list) or not plan["tasks"]:
        raise IntelligenceError("plan has no tasks")
    if not all(isinstance(t, dict) for t in plan["tasks"]):
        raise IntelligenceError("every task must be an object")
    by_id = {w["id"]: w for w in workers}
    rename = {}
    for i, t in enumerate(plan["tasks"], start=start):
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
            if done and str(dep).strip() in done and str(dep).strip() not in rename:
                continue  # finished in an earlier cycle
            dep = rename.get(str(dep).strip(), str(dep).strip())
            if dep not in ids:
                raise IntelligenceError(f"{t['id']} depends on {dep}, which is not an earlier task")
            if dep not in clean_deps:
                clean_deps.append(dep)
        crit = t.get("acceptance_criteria")
        crit = [crit] if isinstance(crit, str) else crit if isinstance(crit, list) else []
        crit = [str(x).strip() for x in crit if str(x).strip()]
        files = t.get("files") if isinstance(t.get("files"), list) else []
        files = [f for f in dict.fromkeys(str(x).strip().removeprefix("./") for x in files)
                 if f and ".." not in f.split("/") and not f.startswith("/")] if kind in roles.BUILD_TYPES else []
        out = {"id": t["id"], "workstream_id": str(t["workstream_id"]).strip(), "kind": kind, "owner_worker_id": owner_id,
               "files": files[:40],
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
    _contract_safe(tasks, merge)
    ws = [{"id": str(w["id"]).strip(), "name": str(w.get("name") or w["id"]).strip()}
          for w in (plan.get("workstreams") if isinstance(plan.get("workstreams"), list) else []) if isinstance(w, dict) and str(w.get("id") or "").strip()]
    for t in tasks:
        if t["workstream_id"] not in {w["id"] for w in ws}:
            ws.append({"id": t["workstream_id"], "name": t["workstream_id"]})
    ms = [{"id": str(m["id"]).strip(), "name": str(m.get("name") or m["id"]).strip(), "due_day": as_int(m.get("due_day"), 0)}
          for m in (plan.get("milestones") if isinstance(plan.get("milestones"), list) else []) if isinstance(m, dict) and str(m.get("id") or "").strip()]
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
    uncovered = [r for r in (requirement_ids or []) if not any(r in t["requirement_ids"] for t in tasks)]
    if uncovered:
        raise IntelligenceError("plan leaves requirements uncovered: " + ", ".join(uncovered))
    return {"workstreams": ws, "milestones": [m for m in ms if m["task_ids"]], "tasks": tasks,
            "uncovered_requirements": []}


def assumption_tests(tasks: list[dict], milestones: list[dict], assumptions: list[dict]) -> list[dict]:
    """When the plan tests each guess the idea depends on: the first task whose work covers a requirement that tests
    it. The riskiest guesses should be tested early, before money goes into what depends on them; a high-risk guess
    first tested only in the last milestone, or never, is said plainly at the roadmap gate."""
    order = {m["id"]: i for i, m in enumerate(milestones)}
    names = {m["id"]: m["name"] for m in milestones}
    out = []
    for a in assumptions:
        hits = sorted((t for t in tasks if set(a.get("tested_by") or []) & set(t.get("requirement_ids") or [])),
                      key=lambda t: (order.get(t.get("milestone_id"), 99), t["id"]))
        first = hits[0] if hits else None
        late = first is None or (len(milestones) > 1 and order.get(first.get("milestone_id")) == len(milestones) - 1)
        out.append({"id": a["id"], "text": a["text"], "risk": a["risk"], "kind": a["kind"],
                    "task": first["id"] if first else None, "tasks": [t["id"] for t in hits],
                    "milestone": names.get(first.get("milestone_id"), "") if first else "",
                    "early": not late, "founder_step": a.get("founder_step", "")})
    return out


DEFAULT_DURATION_MINUTES = {
    "code": 45, "document": 30, "research": 30, "design": 45, "data": 45, "backtest": 45,
    "review_merge": 20, "deploy": 20, "decision": 15, "accept_delivery": 10,
}

def critical_path(tasks: list[dict]) -> list[str]:
    """Critical path by estimated elapsed minutes, not task count."""
    best: dict[str, tuple[float, list[str]]] = {}
    for t in tasks:
        own = float(t.get("estimated_minutes") or DEFAULT_DURATION_MINUTES.get(t.get("kind"), 30))
        dep = max((best[d] for d in t["dependencies"] if d in best), key=lambda x: x[0], default=(0.0, []))
        best[t["id"]] = (dep[0] + own, dep[1] + [t["id"]])
    return max(best.values(), key=lambda x: x[0], default=(0.0, []))[1]


def coordination(owner: dict, workers: list[dict]) -> dict:
    """Who hands a task over, who answers its Blockers and who reviews it, from its owner's place in the company."""
    lead = roles.lead_of(owner)
    answer = [w for w in roles.answerers(workers) if w not in (owner["id"], lead)]
    cofounders = [w["id"] for w in workers if w.get("tier") == "cofounder" and w["id"] != owner["id"]]
    return {"accountable": owner["reports_to"], "handoff_from": lead or "orchestrator",
            "blockers_to": ([lead] if lead else []) + answer or cofounders or ["founder"],
            "reviewed_by": lead}


def oversized(tasks: list[dict]) -> str | None:
    """Why a plan is larger than its objective needs (PLAN_MAX_TASKS tasks, PLAN_MAX_WAVES waves), said so the
    planner can answer with a leaner one; None when it fits."""
    depth = len(waves(tasks))
    if len(tasks) <= PLAN_MAX_TASKS and depth <= PLAN_MAX_WAVES:
        return None
    return (f"the plan has {len(tasks)} tasks in {depth} waves: plan the fewest that meet every acceptance criterion, "
            f"at most {PLAN_MAX_TASKS} tasks in at most {PLAN_MAX_WAVES} waves. Merge work one member can do in one "
            "reply into one task (a document task may write several document types), and let tasks that do not need "
            "each other's output run side by side")


def waves(tasks: list[dict]) -> list[list[str]]:
    """The work as waves: each task in the first wave after every task it depends on. Tasks in one wave can run side
    by side; the number of waves is the plan's sequential depth."""
    level: dict[str, int] = {}
    for t in tasks:
        level[t["id"]] = 1 + max((level[d] for d in t.get("dependencies") or [] if d in level), default=-1)
    out: list[list[str]] = [[] for _ in range(max(level.values(), default=-1) + 1)]
    for t in tasks:
        out[level[t["id"]]].append(t["id"])
    return out


def _contract_safe(tasks: list[dict], merge: dict) -> None:
    """Builds side by side only where that is safe (contract-first, intelligence.CONTRACT_FIRST): two builds that own
    the same file run one after the other, the later depending on the earlier, so neither's verified work is
    copied over by the other at integration; and review_merge depends on every build, so nothing is merged or
    deployed while a build is still running. Repaired here, in plan order, rather than refused."""
    builds = [t for t in tasks if t["kind"] in roles.BUILD_TYPES]
    for i, b in enumerate(builds):
        for a in builds[:i]:
            up = _ancestors(tasks)
            if set(a.get("files") or []) & set(b.get("files") or []) and a["id"] not in up[b["id"]] \
                    and b["id"] not in up[a["id"]]:
                b["dependencies"].append(a["id"])
    up = _ancestors(tasks)
    for b in builds:
        if b["id"] not in up[merge["id"]]:
            merge["dependencies"].append(b["id"])
            up = _ancestors(tasks)


def _ancestors(tasks: list[dict]) -> dict[str, set]:
    up: dict[str, set] = {}
    for t in tasks:
        up[t["id"]] = set()
        for d in t.get("dependencies") or []:
            up[t["id"]] |= {d} | up.get(d, set())
    return up


def enrich(plan: dict, workers: list[dict]) -> dict:
    by_id = {w["id"]: w for w in workers}
    # contract-first: a build task learns the files the builds running alongside it own (no dependency either way)
    up = _ancestors(plan["tasks"])
    builds = [t for t in plan["tasks"] if t["kind"] in roles.BUILD_TYPES]
    for t in builds:
        t["others_files"] = {f: o["id"] for o in builds if o is not t and o["id"] not in up[t["id"]]
                             and t["id"] not in up[o["id"]] for f in o.get("files") or []
                             if f not in (t.get("files") or [])}
    for t in plan["tasks"]:
        owner = by_id[t["owner_worker_id"]]
        t.update({"risk_tier": roles.risk(t["kind"]), "verification_gate": GATES[t["kind"]], "tools": TOOLS[t["kind"]],
                  **coordination(owner, workers), "escalates_to": "founder",
                  "authority_policy_id": f"{policy.POLICY_VERSION}:{owner['role']}"})
    leads = {w["id"]: [x["id"] for x in workers if x.get("reports_to") == w["id"]] for w in workers
             if w.get("tier") == "cofounder"}
    w = waves(plan["tasks"])
    plan.update({"critical_path": critical_path(plan["tasks"]), "waves": w, "sequential_depth": len(w),
                 "escalation_conditions": list(ESCALATION_CONDITIONS),
                 "reporting": {w["id"]: w["reports_to"] for w in workers},
                 "coordination": {"cofounders": leads, "planner": roles.planner(workers),
                                  "answers_blockers": roles.answerers(workers),
                                  "protocols": ["Handoff", "Blocker", "Review", "Approval", "Escalation"]}})
    return plan


def _refine_criteria(run, tasks: list[dict]) -> None:
    """Each requirement's criterion learns how it is really verified: the verifiers of the tasks that cover it."""
    from .objective import METHOD_BY_VERIFIER
    req = run.requirements()
    if not req or not req.get("acceptance_criteria"):
        return
    for c in req["acceptance_criteria"]:
        mine = [t for t in tasks if c.get("requirement_id") in (t.get("requirement_ids") or [])]
        if not mine:
            continue
        c["verified_by_tasks"] = sorted(set(c.get("verified_by_tasks") or []) | {t["id"] for t in mine})
        c["verification_method"] = "+".join(sorted({METHOD_BY_VERIFIER[roles.TASK_TYPES[t["kind"]]["verifier"]]
                                                    for t in mine}))
    run.store.put("requirements", "req_1", req)


def plan(run, note: str = "", cycle: int = 1) -> dict:
    """Stage 5 for the approved organization. Tasks keep their ids across a revised roadmap; the new plan replaces
    the old one before any work starts. A later cycle plans only the new work, numbered after what is done, and keeps
    the earlier tasks in the record."""
    workers = run.workers()
    boss = roles.planner(workers)
    earlier = [t for t in run.tasks() if int(t.get("cycle") or 1) < cycle]
    done = {t["id"] for t in earlier}
    rids = [] if cycle > 1 else [r["id"] for r in run.requirements()["requirements"] if r.get("owner") != "founder"]
    answers = []

    def check(d: dict) -> dict:
        answers.append(1)
        out = validate_plan(d, workers, rids, start=len(earlier) + 1, done=done)
        why = oversized(out["tasks"]) if len(answers) == 1 and run.meta.get("mode") == "live" else None
        if why:  # asked once more for a leaner plan; a second answer is taken at the size it comes
            raise IntelligenceError(why)
        return out

    p, usage = ask(lambda feedback: run.intel.plan(run.objective_ctx(), workers, run.requirements(), note=note,
                                                   feedback=feedback, planner=boss, persona=run.persona(boss),
                                                   cycle=cycle, done=[f"{t['id']}: {t['title']}" for t in earlier]),
                   check)
    run.record_call("plan", boss, "plan", usage)
    p = enrich(p, workers)
    order = []
    from . import objective as objective_engine
    version = run.objective()["version"]
    oid = objective_engine.objective_id(run)
    for i, t in enumerate(p["tasks"]):
        t.update({"company_id": run.cid, "objective_id": oid, "objective_version": version,
                  "context": f"objective v{version}", "cycle": cycle,
                  "status": "PLANNED", "attempts": 0, "work_calls": 0, "blockers": 0, "feedback": "", "handoff_hash": None,
                  "answers": [], "outputs": [], "decision_id": None, "seq": len(earlier) + i, "created_at": now(),
                  "work_class": f"{t['kind']}:{(run.worker(t['owner_worker_id']) or {}).get('role')}",
                  "rework_history": []})
        t["acceptance"] = objective_engine.task_acceptance(t, version)
        t["acceptance_hash"] = objective_engine.acceptance_hash(t)
        run.save_task(t)
        order.append(t["id"])
        run.event("task.created", "task", t["id"], {"kind": t["kind"], "risk_tier": t["risk_tier"],
                  "owner_worker_id": t["owner_worker_id"], "dependencies": t["dependencies"],
                  "milestone": t["milestone_id"]}, actor=boss, actor_type="worker", correlation_id=t["id"])
    record = {k: p[k] for k in ("workstreams", "milestones", "critical_path", "escalation_conditions", "reporting",
                                "coordination", "uncovered_requirements")}
    record.update(waves=p.get("waves") or [], sequential_depth=p.get("sequential_depth"))
    record["assumption_tests"] = assumption_tests(p["tasks"], p["milestones"],
                                                  run.requirements().get("assumptions") or []) if cycle == 1 else \
        (run.store.get("plan", "plan_1") or {}).get("assumption_tests", [])
    _refine_criteria(run, p["tasks"])
    graph = {"nodes": [t["id"] for t in p["tasks"]],
             "edges": [[d, t["id"]] for t in p["tasks"] for d in t["dependencies"]],
             "requirements": {t["id"]: t["requirement_ids"] for t in p["tasks"]}}
    record["work_graph"] = {**graph, "hash": run.store.put_object("json", graph)}
    run.event("workgraph.created", "plan", "plan_1", {"objective_id": oid, "version": version, "cycle": cycle,
              "work_items": len(graph["nodes"]), "dependencies": len(graph["edges"]),
              "critical_path": p["critical_path"], "sequential_depth": p.get("sequential_depth"),
              "graph_hash": record["work_graph"]["hash"]}, actor=boss,
              actor_type="worker" if (boss or "").startswith("w_") else "service")
    before = run.store.get("plan", "plan_1") if cycle > 1 else None
    history = (before or {}).get("earlier_cycles", []) + ([{"cycle": cycle - 1, "milestones": before["milestones"],
                                                           "critical_path": before["critical_path"]}] if before else [])
    run.store.put("plan", "plan_1", {"id": "plan_1", "order": [t["id"] for t in earlier] + order, "note": note,
                                     "cycle": cycle, "earlier_cycles": history, **record})
    return run.store.get("plan", "plan_1")
