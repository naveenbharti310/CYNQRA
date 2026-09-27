"""The Execution Planner: the roadmap as an executable organizational plan.

Product definition, Stage 5. The model proposes milestones, workstreams and tasks with acceptance criteria and an
owner (intelligence.plan, checked by validate_plan). The platform then adds what is not the model's call:

  accountability     every task's owner and the worker it reports to (generated from the organization)
  coordination       the Handoff that starts each task (who hands it over, and which earlier tasks' artifacts),
                     and who clears its Blockers
  verification gate  how the task is proven done; decided by its kind, never by the worker
  escalation         the conditions under which work leaves the organization for the founder
  sequencing         the critical path through the task dependencies
"""
from __future__ import annotations

from . import roles

VERIFICATION_GATES = {
    "spec": "Coverage lint against the objective and the task's acceptance criteria",
    "decision": "Founder review (MEDIUM risk)",
    "code": "Automated tests in a clean copy with every earlier test rerun; the delivery contract for the app",
    "review_merge": "The founder approves the merge (MEDIUM); the full suite then runs on main",
    "deploy": "Build, test, preview, health and smoke checks; the founder approves the deploy (HIGH)",
}
ESCALATION_CONDITIONS = [
    "A task fails verification three times and no other model in the registry can take it over within the budget.",
    "A task has already had two model replacements and fails again.",
    "A worker's model stops answering and no other model can take its work.",
    "A Blocker cannot be cleared by any worker allowed to answer it.",
    "Policy denies an action a task cannot finish without.",
    "The budget cap is reached (the breaker pauses all work).",
    "Every MEDIUM action (product rules, merges) and every HIGH action (production deploy) needs the founder.",
]


def critical_path(tasks: list[dict]) -> list[str]:
    longest: dict[str, list[str]] = {}
    for t in tasks:  # tasks are in dependency order: dependencies only name earlier tasks
        best = max((longest[d] for d in t.get("dependencies", []) if d in longest), key=len, default=[])
        longest[t["id"]] = best + [t["id"]]
    return max(longest.values(), key=len, default=[])


def enrich(plan: dict, workers: list[dict]) -> dict:
    by_id = {w["id"]: w for w in workers}
    assigner = roles.assigner(workers)
    answer = roles.answerers(workers)
    for t in plan["tasks"]:
        owner = by_id[t["owner_worker_id"]]
        manager = t["owner_worker_id"] == assigner or roles.role(owner["role"])["assigns"]
        t["accountable"] = owner.get("reports_to") or "founder"
        t["verification_gate"] = VERIFICATION_GATES[t["kind"]]
        t["handoff_from"] = "orchestrator" if manager else assigner
        t["blockers_to"] = [w for w in answer if w != t["owner_worker_id"]] or [assigner]
        t["escalates_to"] = "founder"
    plan["critical_path"] = critical_path(plan["tasks"])
    plan["escalation_conditions"] = list(ESCALATION_CONDITIONS)
    plan["reporting"] = {w["id"]: w.get("reports_to") or "founder" for w in workers}
    plan["coordination"] = {"assigns": assigner, "answers_blockers": answer,
                            "protocols": ["Handoff", "Blocker", "Approval", "Escalation"]}
    return plan
