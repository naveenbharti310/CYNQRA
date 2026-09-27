"""The catalog: every role Cynqra can staff an organization with, the kinds of work there are, and how each kind
of work is proven done.

Product definition (Cynqra Product Flows and Architecture v1), section 2: the organization is synthesized from the
objective, not fixed. Everything a role or a task type means to the platform is declared here, and nowhere else:

TASK_TYPES   what a task can be, its risk tier, and the verifier that decides it is done
DOC_TYPES    the documents a worker can write, and the rules their verifier checks
ROLES        for each role:
               owns        the task types a worker in this role may own
               documents   the document types it writes
               areas       the requirement areas it covers (the synthesizer checks every requirement is covered)
               authority   its row of the authority matrix (policy.MATRIX is built from these rows)
               assigns     may hand work to other workers with a Handoff
               answers     may clear another worker's Blocker
               reports_to  the roles it reports to, in order of preference; the first one present is used, else
                           the founder. Reporting lines are generated from who is present.
               max         most workers of this role in one organization
"""
from __future__ import annotations

E, P = "execute", "propose"
BASE = {"write_file": E, "read_artifact": E, "run_tests": E, "send_protocol": E}

AREAS = ["product", "functional", "non_functional", "ai_ml", "data", "design", "security", "qa", "devops",
         "deployment", "business", "market", "finance", "legal", "domain"]
# The team always follows the objective. A company is more than its product: the founder states the company they want
# and is its CEO, and the team covers whatever the objective calls for, the business foundation (market, finance,
# legal and compliance) as well as the product. "domain" is expertise particular to the company's field that no
# general role holds (food safety for a bakery chain, clinical safety for a health app, maritime law for a shipping
# marketplace): a Specialist in that field is staffed for it.

TASK_TYPES: dict[str, dict] = {
    "document": {"risk": "LOW", "verifier": "document",
                 "about": "Markdown documents of the types the owner writes, each with the sections its type needs"},
    "decision": {"risk": "MEDIUM", "verifier": "founder",
                 "about": "exactly one product rule the objective leaves open, proposed to the founder"},
    "code": {"risk": "LOW", "verifier": "tests",
             "about": "Python files and their unittest tests; exactly one code task owns app.py and the web page"},
    "forecast": {"risk": "LOW", "verifier": "backtest",
                 "about": "forecast.py with forecast(history, horizon) and its tests; the platform backtests it"},
    "review_merge": {"risk": "MEDIUM", "verifier": "merge", "about": "exactly one, after every build task"},
    "deploy": {"risk": "HIGH", "verifier": "release", "about": "exactly one, the last task"},
}
BUILD_TYPES = ("code", "forecast")  # work that becomes files in the repository and is merged
FILE_TYPES = ("document", "code", "forecast")  # work a worker delivers as files

DOC_TYPES: dict[str, dict] = {
    "business_brief": {"title": "Business brief", "sections": ["Outcome", "Priorities", "Risks"], "objective": True},
    "product_spec": {"title": "Product specification", "sections": ["Users", "Out of scope"], "objective": True},
    "acceptance": {"title": "Acceptance checks", "numbered": 3},
    "design": {"title": "Design specification", "sections": ["Screens", "Flows"]},
    "architecture": {"title": "Architecture", "sections": ["Components", "Data"]},
    "method": {"title": "Forecasting method", "sections": ["Method", "Evaluation"]},
    "test_plan": {"title": "Test plan", "sections": ["Strategy", "Acceptance"]},
    "runbook": {"title": "Runbook", "sections": ["Run", "Rollback"]},
    # The company's foundation. Each one separates what is sourced from what is assumed, because the founder reading
    # it is not an expert in its field and must be able to tell the two apart.
    "market_analysis": {"title": "Market and competitor analysis",
                        "sections": ["Customers", "Competitors", "Positioning", "Sources"], "trust": True},
    "gtm_plan": {"title": "Go-to-market plan", "sections": ["Channels", "Launch", "Metrics"], "trust": True},
    "financial_model": {"title": "Financial model",
                        "sections": ["Costs", "Pricing", "Revenue", "Funding", "Assumptions"], "trust": True},
    "risk_compliance": {"title": "Risk and compliance register",
                        "sections": ["Regulations", "Risks", "Confirm with a professional"], "trust": True},
    "threat_model": {"title": "Threat model", "sections": ["Assets", "Threats", "Controls"], "trust": True},
    "specialist_report": {"title": "Specialist report",
                          "sections": ["Findings", "Recommendations", "Sources", "Confirm with a professional"],
                          "trust": True},
}

ROLES: dict[str, dict] = {
    "CEO": {
        "title": "Business Lead", "slug": "ceo",
        "charter": "The founder is the CEO; the Business Lead runs the business side for them: direction, "
                   "prioritization and the trade-offs between scope, time and money. Writes the business brief and "
                   "settles product rules the objective leaves open, and brings the founder only real decisions.",
        "capabilities": ["strategy", "prioritization", "business reasoning"],
        "areas": ["product", "business"], "owns": ["document", "decision"], "documents": ["business_brief"],
        "assigns": True, "answers": True,
        "authority": {**BASE, "assign_task": E, "answer_blocker": E, "review_work": E, "product_rule_decision": P},
        "reports_to": [], "max": 1},
    "CTO": {
        "title": "CTO", "slug": "cto",
        "charter": "Accountable for architecture and engineering. Decides the technical approach, reviews work "
                   "against the objective, and proposes merges and deploys. Never deploys or messages anyone itself.",
        "capabilities": ["architecture", "review", "release", "security"],
        "areas": ["non_functional", "security", "devops", "deployment"],
        "owns": ["document", "review_merge", "deploy"], "documents": ["architecture"],
        "assigns": True, "answers": True,
        "authority": {**BASE, "assign_task": E, "answer_blocker": E, "review_work": E, "product_rule_decision": P,
                      "merge_to_main": P, "install_package": P, "deploy_production": P},
        "reports_to": ["CEO"], "max": 1},
    "CPO": {
        "title": "CPO", "slug": "cpo",
        "charter": "Owns the product definition: who it is for, the customer workflow and what comes first. Writes "
                   "product specifications and acceptance checks, and settles product rules.",
        "capabilities": ["product discovery", "UX", "prioritization"],
        "areas": ["product", "functional", "design"], "owns": ["document", "decision"],
        "documents": ["product_spec", "acceptance"], "assigns": False, "answers": True,
        "authority": {**BASE, "answer_blocker": E, "review_work": E, "product_rule_decision": P},
        "reports_to": ["CEO"], "max": 1},
    "PM": {
        "title": "Project Manager", "slug": "pm",
        "charter": "Coordinates the work: specs and acceptance checks, milestones, dependencies and reporting. "
                   "Assigns tasks and clears Blockers from the objective and the decided rules. Never writes "
                   "product code.",
        "capabilities": ["product", "specs", "planning", "coordination"],
        "areas": ["product", "functional", "qa"], "owns": ["document", "decision"],
        "documents": ["product_spec", "acceptance"], "assigns": True, "answers": True,
        "authority": {**BASE, "assign_task": E, "answer_blocker": E, "review_work": E, "product_rule_decision": P},
        "reports_to": ["CEO", "CTO"], "max": 1},
    "DataScientist": {
        "title": "Senior Data Scientist", "slug": "ds",
        "charter": "Owns forecasting, statistics and machine learning: the method, its evaluation and the code that "
                   "computes it, with tests that check its numbers.",
        "capabilities": ["statistics", "machine learning", "experimentation", "Python"],
        "areas": ["ai_ml", "data"], "owns": ["document", "forecast", "code"], "documents": ["method"],
        "assigns": False, "answers": True,
        "authority": {**BASE, "answer_blocker": E, "install_package": P, "merge_to_main": P},
        "reports_to": ["CEO", "CTO"], "max": 1},
    "BackendEngineer": {
        "title": "Backend Engineer", "slug": "be",
        "charter": "Builds data services, storage and the HTTP API, with unittest tests, inside its own workspace.",
        "capabilities": ["backend", "APIs", "databases", "testing"],
        "areas": ["functional", "data", "non_functional"], "owns": ["code"], "documents": [],
        "assigns": False, "answers": False,
        "authority": {**BASE, "merge_to_main": P, "install_package": P},
        "reports_to": ["PM", "CTO", "CEO"], "max": 3},
    "FrontendEngineer": {
        "title": "Frontend Engineer", "slug": "fe",
        "charter": "Builds the product's web pages, dashboards and workflows, with unittest tests, inside its own "
                   "workspace.",
        "capabilities": ["frontend", "UI", "testing"],
        "areas": ["functional", "design"], "owns": ["code"], "documents": [],
        "assigns": False, "answers": False,
        "authority": {**BASE, "merge_to_main": P, "install_package": P},
        "reports_to": ["PM", "CTO", "CEO"], "max": 3},
    "Engineer": {
        "title": "Software Engineer", "slug": "eng",
        "charter": "Full-stack engineer: writes Python and unittest tests, backend and web page, inside its own "
                   "workspace only.",
        "capabilities": ["backend", "frontend", "testing"],
        "areas": ["functional", "data", "non_functional", "design"], "owns": ["code"], "documents": [],
        "assigns": False, "answers": False,
        "authority": {**BASE, "merge_to_main": P, "install_package": P},
        "reports_to": ["PM", "CTO", "CEO"], "max": 3},
    "Designer": {
        "title": "Product Designer", "slug": "design",
        "charter": "Owns UX, information architecture and the design system: screens, flows and the words on them, "
                   "written as design specifications the engineers build from.",
        "capabilities": ["UX", "information architecture", "design systems"],
        "areas": ["design"], "owns": ["document"], "documents": ["design"], "assigns": False, "answers": True,
        "authority": {**BASE, "answer_blocker": E},
        "reports_to": ["PM", "CPO", "CTO", "CEO"], "max": 1},
    "DevOps": {
        "title": "DevOps Engineer", "slug": "devops",
        "charter": "Owns infrastructure, the release pipeline, deployment and observability: run configuration, "
                   "smoke checks, the runbook and the deploy proposal.",
        "capabilities": ["CI/CD", "infrastructure", "deployment", "observability"],
        "areas": ["devops", "deployment", "security"], "owns": ["document", "code", "deploy"],
        "documents": ["runbook"], "assigns": False, "answers": False,
        "authority": {**BASE, "install_package": P, "deploy_production": P},
        "reports_to": ["PM", "CTO", "CEO"], "max": 1},
    "QA": {
        "title": "QA Engineer", "slug": "qa",
        "charter": "Owns the test strategy, regression and acceptance validation: writes the test plan and the "
                   "acceptance tests that check the product against its acceptance criteria.",
        "capabilities": ["test design", "regression", "acceptance validation"],
        "areas": ["qa", "non_functional"], "owns": ["document", "code"], "documents": ["test_plan", "acceptance"],
        "assigns": False, "answers": False,
        "authority": {**BASE, "review_work": E},
        "reports_to": ["PM", "CTO", "CEO"], "max": 2},
    "CFO": {
        "title": "CFO", "slug": "cfo",
        "charter": "Owns the money: costs, pricing, the revenue model, funding needs and runway, in a financial "
                   "model whose every number is either sourced or marked as an assumption. Challenges any plan whose "
                   "cost it cannot justify, and settles pricing rules the objective leaves open.",
        "capabilities": ["financial modelling", "pricing", "unit economics", "fundraising"],
        "areas": ["finance"], "owns": ["document", "decision"], "documents": ["financial_model"],
        "assigns": False, "answers": True,
        "authority": {**BASE, "answer_blocker": E, "review_work": E, "product_rule_decision": P},
        "reports_to": ["CEO"], "max": 1},
    "MarketAnalyst": {
        "title": "Market Analyst", "slug": "market",
        "charter": "Owns the market: who the customers are, the competitors and how the company is positioned "
                   "against them, and the go-to-market plan, each claim with its source.",
        "capabilities": ["market research", "competitive analysis", "positioning", "go-to-market"],
        "areas": ["market"], "owns": ["document"], "documents": ["market_analysis", "gtm_plan"],
        "assigns": False, "answers": True,
        "authority": {**BASE, "answer_blocker": E, "review_work": E},
        "reports_to": ["CEO", "CPO"], "max": 1},
    "LegalAdvisor": {
        "title": "Legal and Compliance Advisor", "slug": "legal",
        "charter": "Owns legal and regulatory risk: the regulations that apply, data protection, terms and company "
                   "structure, in a risk and compliance register that says plainly what a qualified lawyer must "
                   "confirm. Blocks work that creates legal risk the founder has not accepted.",
        "capabilities": ["regulation", "data protection", "contracts", "compliance"],
        "areas": ["legal"], "owns": ["document"], "documents": ["risk_compliance"],
        "assigns": False, "answers": True,
        "authority": {**BASE, "answer_blocker": E, "review_work": E},
        "reports_to": ["CEO"], "max": 1},
    "SecurityExpert": {
        "title": "Security Expert", "slug": "sec",
        "charter": "Owns the security of the product and the company's data: the threat model, the controls it "
                   "requires and the security review of the architecture and the code.",
        "capabilities": ["threat modelling", "application security", "security review"],
        "areas": ["security"], "owns": ["document"], "documents": ["threat_model"],
        "assigns": False, "answers": True,
        "authority": {**BASE, "answer_blocker": E, "review_work": E},
        "reports_to": ["CTO", "CEO"], "max": 1},
    # Not a fixed role: the objective names the field. The synthesizer proposes one Specialist per field the company
    # needs and no role above holds, with its title ("Food Safety Specialist"); each is its own worker.
    "Specialist": {
        "title": "Specialist", "slug": "spec",
        "charter": "The expert in a field this company needs that no general role holds. Advises the team from that "
                   "field, answers its questions, reviews work that touches it, and writes a specialist report on "
                   "what the company must get right there, each claim with its source.",
        "capabilities": ["domain expertise"],
        "areas": ["domain"], "owns": ["document"], "documents": ["specialist_report"],
        "assigns": False, "answers": True,
        "authority": {**BASE, "answer_blocker": E, "review_work": E},
        "reports_to": ["CEO", "CTO"], "max": 4},
}

ASSIGNERS = ["PM", "CTO", "CEO"]  # who hands out work, in order of preference, among the roles present
MAX_WORKERS = 16


class RoleError(ValueError):
    pass


def role(name: str) -> dict:
    r = ROLES.get(name)
    if r is None:
        raise RoleError(f"{name!r} is not a role in the catalog ({', '.join(ROLES)})")
    return r


def risk(task_type: str) -> str:
    return TASK_TYPES[task_type]["risk"]


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
        if r.get("field"):  # a Specialist: one worker per field, named after it
            ids = [f"w_spec_{field_slug(r['field'])}"]
        else:
            ids = worker_ids(r["role"], int(r["quantity"]))
        head.setdefault(r["role"], ids[0])
        for i, wid in enumerate(ids):
            title = r.get("title") or spec["title"] + (f" {chr(ord('A') + i)}" if len(ids) > 1 else "")
            w = {"id": wid, "role": r["role"], "title": title, "capabilities": [r["field"]] if r.get("field")
                 else list(spec["capabilities"]), "why": r.get("why", ""),
                 "requirement_ids": list(r.get("requirement_ids") or [])}
            if r.get("field"):
                w["field"] = r["field"]
            workers.append(w)
    for w in workers:
        boss = next((b for b in role(w["role"])["reports_to"] if b in present), None)
        w["reports_to"] = head[boss] if boss else "founder"
    return workers


def field_slug(field: str) -> str:
    s = "".join(c if c.isalnum() else "_" for c in field.lower()).strip("_")
    return "_".join(p for p in s.split("_") if p)[:24] or "field"


def owners_of(task_type: str, workers: list[dict]) -> list[str]:
    return [w["id"] for w in workers if task_type in role(w["role"])["owns"]]


def assigner(workers: list[dict]) -> str | None:
    for name in ASSIGNERS:
        for w in workers:
            if w["role"] == name:
                return w["id"]
    return None


def answerers(workers: list[dict]) -> list[str]:
    return [w["id"] for w in workers if role(w["role"])["answers"]]


def staffing_kinds(name: str) -> list[str]:
    """The kinds of work a role's model is chosen for: the task types it may own, and assigning when it assigns."""
    r = role(name)
    return list(r["owns"]) + (["assign"] if r["assigns"] else [])


def prompt_text(worker: dict) -> str:
    r = role(worker["role"])
    docs = "; ".join(f"{DOC_TYPES[d]['title']}" for d in r["documents"])
    field = f" Your field: {worker['field']}." if worker.get("field") else ""
    return f"You are {worker['title']} ({worker['id']}). {r['charter']}{field}" + (f" You write: {docs}." if docs else "")


def doc_rules(doc_type: str) -> str:
    """The rules a document type's verifier checks, as the worker is told them."""
    d = DOC_TYPES[doc_type]
    parts = []
    if d.get("sections"):
        parts.append("sections headed " + ", ".join(f"'## {s}'" for s in d["sections"]))
    if d.get("numbered"):
        parts.append(f"at least {d['numbered']} numbered checks (1., 2., ...)")
    if d.get("objective"):
        parts.append("every constraint of the objective addressed and its success criteria covered")
    if d.get("trust"):
        parts.append("every fact with its source, every estimate marked as an assumption, and what a qualified "
                     "professional must confirm said plainly")
    return f"{d['title']} ({doc_type}): " + "; ".join(parts)


def matrix() -> dict:
    return {name: dict(r["authority"]) for name, r in ROLES.items()}


def catalog() -> list[dict]:
    """The catalog as the UI and the synthesizer's prompt show it."""
    return [{"role": k, "title": r["title"], "charter": r["charter"], "areas": r["areas"], "owns": r["owns"],
             "documents": r["documents"], "max": r["max"]} for k, r in ROLES.items()]
