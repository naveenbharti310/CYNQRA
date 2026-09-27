"""The role catalog: every role Cynqra can staff an organization with, and what each role may do.

Product definition (Cynqra Product Flows and Architecture v1), section 2: the organization is synthesized from the
objective, not fixed. The Workforce Synthesizer chooses roles and quantities from this catalog; everything a role
means to the platform comes from here, so no other module names a role or a worker:

  owns          the kinds of task a worker in this role may own (the Execution Planner checks every task against it)
  areas         the requirement areas the role covers (the synthesizer checks every requirement is covered)
  authority     the role's row of the authority matrix (policy.MATRIX is built from these rows)
  assigns       may hand work to other workers with a Handoff
  answers       may clear another worker's Blocker
  reports_to    the roles it reports to, in order of preference; the first one present in the organization is used,
                else the founder. Reporting lines are generated from who is present, never fixed in advance.
  max           most workers of this role in one organization

The M1 fixed organization (CTO, PM, two engineers) is no longer the product: it is one instantiation of this
catalog, kept as a test fixture (FIXTURE_M1).
"""
from __future__ import annotations

E, P = "execute", "propose"
BASE = {"write_file": E, "read_artifact": E, "run_tests": E, "send_protocol": E}

AREAS = ["product", "functional", "non_functional", "ai_ml", "data", "design", "security", "qa", "devops",
         "deployment"]
TASK_KINDS = ["spec", "decision", "code", "review_merge", "deploy"]

ROLES: dict[str, dict] = {
    "CEO": {
        "title": "CEO / Business Lead", "slug": "ceo",
        "charter": "Owns the business outcome: direction, prioritization and the trade-offs between scope, time and "
                   "money. Writes the business brief and settles product rules the objective leaves open.",
        "capabilities": ["strategy", "prioritization", "business reasoning"],
        "areas": ["product"], "owns": ["spec", "decision"], "assigns": True, "answers": True,
        "authority": {**BASE, "assign_task": E, "answer_blocker": E, "review_work": E, "product_rule_decision": P},
        "reports_to": [], "max": 1},
    "CTO": {
        "title": "CTO", "slug": "cto",
        "charter": "Accountable for architecture and engineering. Decides the technical approach, reviews work "
                   "against the objective, and proposes merges and deploys. Never deploys or messages anyone itself.",
        "capabilities": ["architecture", "review", "release", "security"],
        "areas": ["non_functional", "security", "devops", "deployment"],
        "owns": ["spec", "review_merge", "deploy"], "assigns": True, "answers": True,
        "authority": {**BASE, "assign_task": E, "answer_blocker": E, "review_work": E, "product_rule_decision": P,
                      "merge_to_main": P, "install_package": P, "deploy_production": P},
        "reports_to": ["CEO"], "max": 1},
    "CPO": {
        "title": "CPO", "slug": "cpo",
        "charter": "Owns the product definition: who it is for, the customer workflow and what comes first. Writes "
                   "product specifications and settles product rules.",
        "capabilities": ["product discovery", "UX", "prioritization"],
        "areas": ["product", "functional", "design"], "owns": ["spec", "decision"], "assigns": False,
        "answers": True,
        "authority": {**BASE, "answer_blocker": E, "review_work": E, "product_rule_decision": P},
        "reports_to": ["CEO"], "max": 1},
    "PM": {
        "title": "Project Manager", "slug": "pm",
        "charter": "Coordinates the work: specs and acceptance checks, milestones, dependencies and reporting. "
                   "Assigns tasks and clears Blockers from the objective and the decided rules. Never writes "
                   "product code.",
        "capabilities": ["product", "specs", "planning", "coordination"],
        "areas": ["product", "functional", "qa"], "owns": ["spec", "decision"], "assigns": True, "answers": True,
        "authority": {**BASE, "assign_task": E, "answer_blocker": E, "review_work": E, "product_rule_decision": P},
        "reports_to": ["CEO", "CTO"], "max": 1},
    "DataScientist": {
        "title": "Senior Data Scientist", "slug": "ds",
        "charter": "Owns forecasting, statistics and machine learning: the method, the evaluation and the code that "
                   "computes it, with tests that check its numbers.",
        "capabilities": ["statistics", "machine learning", "experimentation", "Python"],
        "areas": ["ai_ml", "data"], "owns": ["spec", "code"], "assigns": False, "answers": True,
        "authority": {**BASE, "answer_blocker": E, "install_package": P, "merge_to_main": P},
        "reports_to": ["CEO", "CTO"], "max": 1},
    "BackendEngineer": {
        "title": "Backend Engineer", "slug": "be",
        "charter": "Builds data services, storage and the HTTP API, with unittest tests, inside its own workspace.",
        "capabilities": ["backend", "APIs", "databases", "testing"],
        "areas": ["functional", "data", "non_functional"], "owns": ["code"], "assigns": False, "answers": False,
        "authority": {**BASE, "merge_to_main": P, "install_package": P},
        "reports_to": ["PM", "CTO", "CEO"], "max": 3},
    "FrontendEngineer": {
        "title": "Frontend Engineer", "slug": "fe",
        "charter": "Builds the product's web pages, dashboards and workflows, with unittest tests, inside its own "
                   "workspace.",
        "capabilities": ["frontend", "UI", "testing"],
        "areas": ["functional", "design"], "owns": ["code"], "assigns": False, "answers": False,
        "authority": {**BASE, "merge_to_main": P, "install_package": P},
        "reports_to": ["PM", "CTO", "CEO"], "max": 3},
    "Engineer": {
        "title": "Software Engineer", "slug": "eng",
        "charter": "Full-stack engineer: writes Python and unittest tests, backend and web page, inside its own "
                   "workspace only.",
        "capabilities": ["backend", "frontend", "testing"],
        "areas": ["functional", "data", "non_functional", "design"], "owns": ["code"], "assigns": False, "answers": False,
        "authority": {**BASE, "merge_to_main": P, "install_package": P},
        "reports_to": ["PM", "CTO", "CEO"], "max": 3},
    "Designer": {
        "title": "Product Designer", "slug": "design",
        "charter": "Owns UX, information architecture and the design system: screens, flows and the words on them, "
                   "written as design specifications the engineers build from.",
        "capabilities": ["UX", "information architecture", "design systems"],
        "areas": ["design"], "owns": ["spec"], "assigns": False, "answers": True,
        "authority": {**BASE, "answer_blocker": E},
        "reports_to": ["PM", "CPO", "CTO", "CEO"], "max": 1},
    "DevOps": {
        "title": "DevOps Engineer", "slug": "devops",
        "charter": "Owns infrastructure, the release pipeline, deployment and observability: run configuration, "
                   "smoke checks and the deploy proposal.",
        "capabilities": ["CI/CD", "infrastructure", "deployment", "observability"],
        "areas": ["devops", "deployment", "security"], "owns": ["spec", "code", "deploy"], "assigns": False,
        "answers": False,
        "authority": {**BASE, "install_package": P, "deploy_production": P},
        "reports_to": ["PM", "CTO", "CEO"], "max": 1},
    "QA": {
        "title": "QA Engineer", "slug": "qa",
        "charter": "Owns the test strategy, regression and acceptance validation: writes the test plan and the "
                   "acceptance tests that check the product against its acceptance criteria.",
        "capabilities": ["test design", "regression", "acceptance validation"],
        "areas": ["qa", "non_functional"], "owns": ["spec", "code"], "assigns": False, "answers": False,
        "authority": {**BASE, "review_work": E},
        "reports_to": ["PM", "CTO", "CEO"], "max": 2},
}

ASSIGNERS = ["PM", "CTO", "CEO"]  # who hands out work, in order of preference, among the roles present
MAX_WORKERS = 14

# The M1 build's fixed organization, now a fixture: one instantiation of the catalog.
FIXTURE_M1 = [{"role": "CTO", "quantity": 1}, {"role": "PM", "quantity": 1}, {"role": "Engineer", "quantity": 2}]


class RoleError(ValueError):
    pass


def role(name: str) -> dict:
    r = ROLES.get(name)
    if r is None:
        raise RoleError(f"{name!r} is not a role in the catalog ({', '.join(ROLES)})")
    return r


def worker_ids(name: str, quantity: int) -> list[str]:
    """w_cto; w_eng_a, w_eng_b for more than one."""
    slug = role(name)["slug"]
    if quantity == 1:
        return [f"w_{slug}"]
    return [f"w_{slug}_{chr(ord('a') + i)}" for i in range(quantity)]


def instantiate(roles: list[dict]) -> list[dict]:
    """Roles and quantities to workers: id, role, title, capabilities, reporting line. Deterministic: the same
    roles always give the same workers, and each worker reports to the first role it prefers that is present."""
    present = {r["role"] for r in roles}
    head: dict[str, str] = {}
    workers = []
    for r in roles:
        spec = role(r["role"])
        ids = worker_ids(r["role"], int(r["quantity"]))
        head.setdefault(r["role"], ids[0])
        for i, wid in enumerate(ids):
            title = spec["title"] + (f" {chr(ord('A') + i)}" if len(ids) > 1 else "")
            workers.append({"id": wid, "role": r["role"], "title": title, "capabilities": list(spec["capabilities"]),
                            "why": r.get("why", ""), "requirement_ids": list(r.get("requirement_ids") or [])})
    for w in workers:
        boss = next((b for b in role(w["role"])["reports_to"] if b in present), None)
        w["reports_to"] = head[boss] if boss else "founder"
    return workers


def owners_of(kind: str, workers: list[dict]) -> list[str]:
    return [w["id"] for w in workers if kind in role(w["role"])["owns"]]


def assigner(workers: list[dict]) -> str | None:
    for name in ASSIGNERS:
        for w in workers:
            if w["role"] == name:
                return w["id"]
    return None


def answerers(workers: list[dict]) -> list[str]:
    return [w["id"] for w in workers if role(w["role"])["answers"]]


def staffing_kinds(name: str) -> list[str]:
    """The kinds of work a role's model is chosen for: the tasks it may own, and assigning when it assigns."""
    r = role(name)
    return list(r["owns"]) + (["assign"] if r["assigns"] else [])


def prompt_text(worker: dict) -> str:
    r = role(worker["role"])
    return f"You are {worker['title']} ({worker['id']}). {r['charter']}"


def matrix() -> dict:
    return {name: dict(r["authority"]) for name, r in ROLES.items()}


def catalog() -> list[dict]:
    """The catalog as the UI and the synthesizer's prompt show it."""
    return [{"role": k, "title": r["title"], "charter": r["charter"], "areas": r["areas"], "owns": r["owns"],
             "max": r["max"]} for k, r in ROLES.items()]
