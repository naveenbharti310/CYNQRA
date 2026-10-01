"""The catalog: every role Cynqra can staff an organization with, the kinds of work there are, and how each kind
of work is proven done.

The organization is built the way a founder builds a real company. The founder is the CEO. Cynqra first proposes
the cofounders the company needs (a CTO, a Chief Product Officer, a CFO, and a Chief Compliance Officer for a
regulated business), each with a reason; then each cofounder proposes the team for its own area. Cofounders run
their areas: they hand out their team's work, answer its doubts, review its work before it counts, and bring the
founder only the decisions a CEO should make. Everything a role or a task type means to the platform is declared
here, and nowhere else:

TASK_TYPES   what a task can be, its risk tier, and the verifier that decides it is done
DOC_TYPES    the documents a worker can write, and the rules their verifier checks
ROLES        for each role:
               tier        "cofounder" (leads an area and reports to the founder) or "team" (works in a cofounder's
                           area and reports to that cofounder)
               owns        the task types a worker in this role may own
               documents   the document types it writes
               areas       the requirement areas it covers (the synthesizer checks every requirement is covered)
               authority   its row of the authority matrix (policy.MATRIX is built from these rows)
               answers     may clear another worker's Blocker
               reports_to  for a team role, the cofounders who may lead it, in order of preference: the one that
                           hired it, else the first of these present, else the first cofounder present
               max         most workers of this role in one organization
"""
from __future__ import annotations

E, P = "execute", "propose"
BASE = {"write_file": E, "read_artifact": E, "run_tests": E, "send_protocol": E, "search_files": E}

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
                        "sections": ["Costs", "Pricing", "Revenue", "Funding", "Assumptions"], "trust": True,
                        "numbers": True},
    "risk_compliance": {"title": "Risk and compliance register",
                        "sections": ["Regulations", "Risks", "Confirm with a professional"], "trust": True},
    "threat_model": {"title": "Threat model", "sections": ["Assets", "Threats", "Controls"], "trust": True},
    "specialist_report": {"title": "Specialist report",
                          "sections": ["Findings", "Recommendations", "Sources", "Confirm with a professional"],
                          "trust": True},
}

LEAD = {"assign_task": E, "answer_blocker": E, "review_work": E}  # what every cofounder does for its team

ROLES: dict[str, dict] = {
    # --- cofounders: the founder is the CEO; these lead the company with them ----------------------------------
    "CTO": {
        "title": "CTO", "slug": "cto", "tier": "cofounder",
        "charter": "Cofounder accountable for technology: the architecture, the engineering team and the release. "
                   "Decides the technical approach, hands out and reviews the engineering team's work, answers its "
                   "doubts, and proposes merges. Never deploys or messages anyone itself.",
        "capabilities": ["architecture", "engineering leadership", "review", "release"],
        "areas": ["non_functional", "security", "devops", "deployment"],
        "owns": ["document", "review_merge", "deploy"], "documents": ["architecture"], "answers": True,
        "authority": {**BASE, **LEAD, "product_rule_decision": P, "merge_to_main": P, "install_package": P,
                      "deploy_production": P},
        "reports_to": [], "max": 1},
    "CPO": {
        "title": "Chief Product Officer", "slug": "cpo", "tier": "cofounder",
        "charter": "Cofounder accountable for the product and the business it serves: who it is for, what it must "
                   "do for them and what comes first. Writes the business brief everyone works from, leads the "
                   "product team, reviews its work, and settles product rules the objective leaves open.",
        "capabilities": ["product strategy", "customer discovery", "UX", "prioritization"],
        "areas": ["product", "business", "functional", "design"], "owns": ["document", "decision"],
        "documents": ["business_brief", "product_spec"], "answers": True,
        "authority": {**BASE, **LEAD, "product_rule_decision": P},
        "reports_to": [], "max": 1},
    "CFO": {
        "title": "CFO", "slug": "cfo", "tier": "cofounder",
        "charter": "Cofounder accountable for the money: costs, pricing, the revenue model, funding needs and runway, "
                   "in a financial model whose every number is either sourced or marked as an assumption. Challenges "
                   "any plan whose cost it cannot justify, settles pricing rules the objective leaves open, and leads "
                   "the finance and legal work.",
        "capabilities": ["financial modelling", "pricing", "unit economics", "fundraising"],
        "areas": ["finance"], "owns": ["document", "decision"], "documents": ["financial_model"], "answers": True,
        "authority": {**BASE, **LEAD, "product_rule_decision": P},
        "reports_to": [], "max": 1},
    # --- the teams ----------------------------------------------------------------------------------------------
    "PM": {
        "title": "Project Manager", "slug": "pm", "tier": "team",
        "charter": "Plans and coordinates the work: the roadmap, specifications and acceptance checks, milestones "
                   "and dependencies. Never writes product code.",
        "capabilities": ["planning", "specs", "coordination"],
        "areas": ["product", "functional", "qa"], "owns": ["document", "decision"],
        "documents": ["product_spec", "acceptance"], "answers": True,
        "authority": {**BASE, "answer_blocker": E, "review_work": E, "product_rule_decision": P},
        "reports_to": ["CPO", "CTO"], "max": 1},
    "Engineer": {
        "title": "Software Engineer", "slug": "eng", "tier": "team",
        "charter": "Full-stack engineer: writes Python and unittest tests, backend and web page, inside its own "
                   "workspace only.",
        "capabilities": ["backend", "frontend", "testing"],
        "areas": ["functional", "data", "non_functional", "design"], "owns": ["code"], "documents": [],
        "answers": False, "authority": {**BASE, "run_command": E, "merge_to_main": P, "install_package": P},
        "reports_to": ["CTO"], "max": 3},
    "BackendEngineer": {
        "title": "Backend Engineer", "slug": "be", "tier": "team",
        "charter": "Builds the data, the business logic and the services behind the product, with unittest tests, "
                   "inside its own workspace.",
        "capabilities": ["backend", "APIs", "databases", "testing"],
        "areas": ["functional", "data", "non_functional"], "owns": ["code"], "documents": [], "answers": False,
        "authority": {**BASE, "merge_to_main": P, "install_package": P},
        "reports_to": ["CTO"], "max": 3},
    "FrontendEngineer": {
        "title": "Frontend Engineer", "slug": "fe", "tier": "team",
        "charter": "Builds the product's web app: its pages, dashboards and workflows and the web server that serves "
                   "them, with unittest tests, inside its own workspace.",
        "capabilities": ["frontend", "UI", "testing"],
        "areas": ["functional", "design"], "owns": ["code"], "documents": [], "answers": False,
        "authority": {**BASE, "merge_to_main": P, "install_package": P},
        "reports_to": ["CTO"], "max": 3},
    "DataScientist": {
        "title": "Senior Data Scientist", "slug": "ds", "tier": "team",
        "charter": "Owns forecasting, statistics and machine learning: the method, its evaluation and the code that "
                   "computes it, with tests that check its numbers.",
        "capabilities": ["statistics", "machine learning", "experimentation", "Python"],
        "areas": ["ai_ml", "data"], "owns": ["document", "forecast", "code"], "documents": ["method"],
        "answers": True, "authority": {**BASE, "run_command": E, "answer_blocker": E, "install_package": P, "merge_to_main": P},
        "reports_to": ["CTO"], "max": 1},
    "Designer": {
        "title": "Product Designer", "slug": "design", "tier": "team",
        "charter": "Owns UX, information architecture and the design system: screens, flows and the words on them, "
                   "written as design specifications the engineers build from.",
        "capabilities": ["UX", "information architecture", "design systems"],
        "areas": ["design"], "owns": ["document"], "documents": ["design"], "answers": True,
        "authority": {**BASE, "answer_blocker": E},
        "reports_to": ["CPO", "CTO"], "max": 1},
    "DevOps": {
        "title": "DevOps Engineer", "slug": "devops", "tier": "team",
        "charter": "Owns infrastructure, the release pipeline, deployment and observability: run configuration, "
                   "smoke checks, the runbook and the deploy proposal.",
        "capabilities": ["CI/CD", "infrastructure", "deployment", "observability"],
        "areas": ["devops", "deployment", "security"], "owns": ["document", "code", "deploy"],
        "documents": ["runbook"], "answers": False,
        "authority": {**BASE, "run_command": E, "install_package": P, "deploy_production": P},
        "reports_to": ["CTO"], "max": 1},
    "QA": {
        "title": "QA Engineer", "slug": "qa", "tier": "team",
        "charter": "Owns the test strategy, regression and acceptance validation: writes the test plan and the "
                   "acceptance tests that check the product against its acceptance criteria.",
        "capabilities": ["test design", "regression", "acceptance validation"],
        "areas": ["qa", "non_functional"], "owns": ["document", "code"], "documents": ["test_plan", "acceptance"],
        "answers": False, "authority": {**BASE, "run_command": E, "review_work": E},
        "reports_to": ["CTO", "CPO"], "max": 2},
    "MarketAnalyst": {
        "title": "Market Analyst", "slug": "market", "tier": "team",
        "charter": "Owns the market: who the customers are, the competitors and how the company is positioned "
                   "against them, and the go-to-market plan, each claim with its source.",
        "capabilities": ["market research", "competitive analysis", "positioning", "go-to-market"],
        "areas": ["market"], "owns": ["document"], "documents": ["market_analysis", "gtm_plan"], "answers": True,
        "authority": {**BASE, "answer_blocker": E, "review_work": E},
        "reports_to": ["CPO", "CFO"], "max": 1},
    "GrowthMarketer": {
        "title": "Growth Marketer", "slug": "growth", "tier": "team",
        "charter": "Owns reaching the first customers: the channels, the launch, what winning one customer costs and "
                   "the numbers that show whether it works, in a go-to-market plan whose every figure is sourced or "
                   "marked as an assumption.",
        "capabilities": ["go-to-market", "customer acquisition", "launch", "sales"],
        "areas": ["market"], "owns": ["document"], "documents": ["gtm_plan"], "answers": True,
        "authority": {**BASE, "answer_blocker": E},
        "reports_to": ["CPO", "CFO"], "max": 1},
    "LegalAdvisor": {
        "title": "Legal and Compliance Advisor", "slug": "legal", "tier": "team",
        "charter": "Owns legal and regulatory risk: the regulations that apply, data protection, terms and company "
                   "structure, in a risk and compliance register that says plainly what a qualified lawyer must "
                   "confirm. Blocks work that creates legal risk the founder has not accepted.",
        "capabilities": ["regulation", "data protection", "contracts", "compliance"],
        "areas": ["legal"], "owns": ["document"], "documents": ["risk_compliance"], "answers": True,
        "authority": {**BASE, "answer_blocker": E, "review_work": E},
        "reports_to": ["CCO", "CFO", "CPO"], "max": 1},
    "SecurityExpert": {
        "title": "Security Expert", "slug": "sec", "tier": "team",
        "charter": "Owns the security of the product and the company's data: the threat model, the controls it "
                   "requires and the security review of the architecture and the code.",
        "capabilities": ["threat modelling", "application security", "security review"],
        "areas": ["security"], "owns": ["document"], "documents": ["threat_model"], "answers": True,
        "authority": {**BASE, "answer_blocker": E, "review_work": E},
        "reports_to": ["CTO", "CCO"], "max": 1},
    # Not a fixed role: the objective names the field. One Specialist per field the company needs and no role above
    # holds, with its title ("Food Safety Specialist"); each is its own worker, hired by the cofounder whose area the
    # field serves.
    "Specialist": {
        "title": "Specialist", "slug": "spec", "tier": "team",
        "charter": "The expert in a field this company needs that no general role holds. Advises the team from that "
                   "field, answers its questions, reviews work that touches it, and writes a specialist report on "
                   "what the company must get right there, each claim with its source.",
        "capabilities": ["domain expertise"],
        "areas": ["domain"], "owns": ["document"], "documents": ["specialist_report"], "answers": True,
        "authority": {**BASE, "answer_blocker": E, "review_work": E},
        "reports_to": ["CPO", "CTO", "CFO", "CCO"], "max": 4},
    # A fourth cofounder for a regulated business (payments, lending, insurance, health, children's data). Listed
    # last so that an uncovered legal requirement is given a Legal and Compliance Advisor unless the company needs a
    # compliance cofounder.
    "CCO": {
        "title": "Chief Compliance Officer", "slug": "cco", "tier": "cofounder",
        "charter": "Cofounder accountable for regulation in a regulated business: the licences it needs, the rules "
                   "its product must follow and the evidence that it does, built in from the start. Leads the legal "
                   "and compliance work and reviews anything that touches regulated activity.",
        "capabilities": ["regulatory strategy", "licensing", "compliance by design", "audit"],
        "areas": ["legal", "security"], "owns": ["document", "decision"], "documents": ["risk_compliance"],
        "answers": True, "authority": {**BASE, **LEAD, "product_rule_decision": P},
        "reports_to": [], "max": 1},
}

COFOUNDERS = [n for n, r in ROLES.items() if r["tier"] == "cofounder"]
PLANNERS = ["PM", "CPO", "CTO", "CFO", "CCO"]  # who writes the roadmap, in order of preference, among the roles present
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


def is_cofounder(name: str) -> bool:
    return role(name)["tier"] == "cofounder"


def lead_role(name: str, cofounders: list[str], hired_by: str | None = None) -> str | None:
    """The cofounder a team role reports to: the one that hired it, else the first of its preferred leads present,
    else the first cofounder present. None for a cofounder, and when there is no cofounder at all."""
    if is_cofounder(name) or not cofounders:
        return None
    prefer = [c for c in role(name)["reports_to"] if c in cofounders]
    if hired_by in cofounders and (hired_by in role(name)["reports_to"] or not prefer):
        return hired_by  # the cofounder that hired it, when that cofounder may lead this role
    return prefer[0] if prefer else cofounders[0]


def instantiate(roles: list[dict]) -> list[dict]:
    """Roles and quantities to workers: id, role, title, capabilities, reporting line. Deterministic: the same
    roles always give the same workers. Cofounders report to the founder; a team member reports to the cofounder
    that hired it (the role's "lead"), else to the first cofounder its role prefers that is present."""
    cofounders = [r["role"] for r in roles if is_cofounder(r["role"])]
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
            w = {"id": wid, "role": r["role"], "tier": spec["tier"], "title": title,
                 "capabilities": [r["field"]] if r.get("field") else list(spec["capabilities"]), "why": r.get("why", ""),
                 "requirement_ids": list(r.get("requirement_ids") or []), "_lead": r.get("lead")}
            if r.get("field"):
                w["field"] = r["field"]
            workers.append(w)
    for w in workers:
        lead = lead_role(w["role"], cofounders, w.pop("_lead"))
        w["reports_to"] = head[lead] if lead else "founder"
    return workers


def field_slug(field: str) -> str:
    s = "".join(c if c.isalnum() else "_" for c in field.lower()).strip("_")
    return "_".join(p for p in s.split("_") if p)[:24].strip("_") or "field"


def owners_of(task_type: str, workers: list[dict]) -> list[str]:
    return [w["id"] for w in workers if task_type in role(w["role"])["owns"]]


def planner(workers: list[dict]) -> str | None:
    """Who writes the roadmap: the Project Manager, else a cofounder, in PLANNERS order."""
    for name in PLANNERS:
        for w in workers:
            if w["role"] == name:
                return w["id"]
    return None


def lead_of(worker: dict) -> str | None:
    """The cofounder a team member reports to (its worker id); None for a cofounder."""
    to = worker.get("reports_to")
    return to if to and to != "founder" else None


def answerers(workers: list[dict]) -> list[str]:
    return [w["id"] for w in workers if role(w["role"])["answers"]]


def staffing_kinds(name: str) -> list[str]:
    """The kinds of work a role's model is chosen for: the task types it may own, and assigning when it assigns."""
    r = role(name)
    return list(r["owns"]) + (["assign", "review"] if r["tier"] == "cofounder" else [])


def prompt_text(worker: dict, workers: list[dict] | None = None) -> str:
    r = role(worker["role"])
    docs = "; ".join(f"{DOC_TYPES[d]['title']}" for d in r["documents"])
    field = f" Your field: {worker['field']}." if worker.get("field") else ""
    who = f"{worker['name']}, the AI {worker['title']}" if worker.get("name") else worker["title"]
    out = f"You are {who} ({worker['id']}). {r['charter']}{field}" + (f" You write: {docs}." if docs else "")
    by_id = {w["id"]: w for w in workers or []}
    if r["tier"] == "cofounder":
        team = [w for w in workers or [] if w.get("reports_to") == worker["id"]]
        out += (" You are a cofounder: the founder is the CEO and you report to them." +
                (" Your team: " + ", ".join(f"{w.get('name') + ', ' if w.get('name') else ''}{w['title']} ({w['id']})" for w in team) + "." if team else ""))
    elif worker.get("reports_to") in by_id:
        lead = by_id[worker["reports_to"]]
        out += (f" You report to {lead.get('name') + ', ' if lead.get('name') else ''}{lead['title']} ({lead['id']}), "
                "the cofounder who leads your area.")
    return out


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
    if d.get("numbers"):
        from .numbers import INPUTS
        parts.append("a ```json block the platform recomputes: {\"currency\", \"inputs\": {name: {\"value\", "
                     "\"basis\": \"assumption\", \"measured\" or \"source: where\"}}, \"claims\": {figure: value}}, "
                     "with the inputs " + ", ".join(INPUTS) + " and any of the claims margin_per_customer, "
                     "payback_months, lifetime_value, break_even_month, funding_needed, "
                     "reaches_profit_before_money_runs_out")
    return f"{d['title']} ({doc_type}): " + "; ".join(parts)


def matrix() -> dict:
    return {name: dict(r["authority"]) for name, r in ROLES.items()}


def catalog() -> list[dict]:
    """The catalog as the UI and the synthesizer's prompt show it."""
    return [{"role": k, "title": r["title"], "tier": r["tier"], "charter": r["charter"], "areas": r["areas"],
             "owns": r["owns"], "documents": r["documents"], "leads": r["reports_to"], "max": r["max"]}
            for k, r in ROLES.items()]
