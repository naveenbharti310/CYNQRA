"""Objective Intelligence: Stages 0 and 1 of the product definition.

The founder hands over a project name, the outcome they want, a budget and any constraints (deadline, geography,
technology, compliance, risk tolerance), and says what they bring themselves: the areas they will lead, the time they
have, and the stage the company is at (FOUNDER). They do not describe a team. Cynqra structures the outcome into
seven fields, then decomposes it into the outcomes, the requirements by area and the risks the company must control,
groups the requirements into workstreams, and computes the critical path. The founder confirms that list before any
team is proposed: the team is built from it and from nothing else. The model proposes; the platform checks
(validate_requirements) and owns every identifier.
"""
from __future__ import annotations

import re

from . import roles
from .db import digest, now
from .intelligence import IntelligenceError, ask

FIELDS = ["product", "target_customer", "primary_outcome", "business_outcome", "success_criteria", "constraints",
          "priorities"]
CONSTRAINT_KEYS = ["deadline", "geography", "technology", "compliance", "risk_tolerance"]
NOT_STATED = "not stated in the brief"

# What the founder brings. A real founder chooses cofounders to fill their own gaps: an area the founder leads
# themselves gets no cofounder, and its requirements are the founder's own. The stage sets how large a team each
# cofounder may hire: a company building its first version needs few people, one going live a few more.
STAGES = {"idea": "Testing the idea", "first_version": "Building the first version", "launch": "Going live"}
TEAM_LIMIT = {"idea": 2, "first_version": 4, "launch": 6}  # team seats one cofounder may hire, by stage
FOUNDER_DEFAULT = {"leads": [], "stage": "launch", "hours_per_week": 10, "background": ""}  # Cynqra's aim: live

class ObjectiveError(ValueError):
    pass


# What a model may call an area, mapped to the catalog's name. "business" is an area of its own (roles.AREAS): it is
# not an alias of product, or a business requirement would be filed as a product one.
AREA_ALIASES = {"ai": "ai_ml", "ml": "ai_ml", "ai/ml": "ai_ml", "machine_learning": "ai_ml", "nonfunctional": "non_functional",
                "non-functional": "non_functional", "ux": "design", "ui": "design", "testing": "qa", "quality": "qa",
                "infrastructure": "devops", "ops": "devops", "deploy": "deployment", "strategy": "business",
                "operations": "business", "financial": "finance", "financials": "finance", "pricing": "finance",
                "marketing": "market", "go_to_market": "market", "gtm": "market", "sales": "market",
                "compliance": "legal", "regulatory": "legal", "regulation": "legal", "privacy": "legal",
                "specialist": "domain", "domain_expertise": "domain", "industry": "domain"}


def _slug_list(value) -> list[str]:
    if isinstance(value, str):
        value = [v for v in re.split(r"[,\s]+", value) if v]
    return [str(v).strip() for v in value or [] if str(v).strip()] if isinstance(value, list) else []


def founder_profile(value) -> dict:
    """The founder's profile, checked: only cofounder seats can be led by the founder, a known stage, whole hours."""
    v = value if isinstance(value, dict) else {}
    leads = [x for x in _slug_list(v.get("leads")) if x in roles.COFOUNDERS]
    stage = str(v.get("stage") or FOUNDER_DEFAULT["stage"]).strip()
    if stage not in STAGES:
        raise ObjectiveError(f"stage must be one of {', '.join(STAGES)}")
    try:
        hours = max(0, min(100, int(float(v.get("hours_per_week", FOUNDER_DEFAULT["hours_per_week"])))))
    except (TypeError, ValueError) as exc:
        raise ObjectiveError("hours_per_week must be a number") from exc
    return {"leads": list(dict.fromkeys(leads)), "stage": stage, "hours_per_week": hours,
            "background": str(v.get("background") or "").strip()[:400]}


def founder_areas(profile: dict | None) -> set[str]:
    """The requirement areas the founder leads themselves: the areas of the cofounder seats they hold."""
    return {a for c in (profile or {}).get("leads") or [] for a in roles.role(c)["areas"]}


def validate_requirements(pkg: dict, founder: dict | None = None) -> dict:
    """Stage 1's objective package, checked by the platform: known areas, ids it owns (r_01, ws_01, k_01), workstreams
    that hold every requirement, dependencies without cycles, and the critical path computed from them. A requirement
    in an area the founder leads is marked as the founder's own; a risk names what must not go wrong."""
    if not isinstance(pkg, dict) or not isinstance(pkg.get("requirements"), list) or not pkg["requirements"]:
        raise IntelligenceError("the objective package has no requirements")
    rename, reqs = {}, []
    for i, r in enumerate(pkg["requirements"], start=1):
        if not isinstance(r, dict) or not str(r.get("text") or "").strip():
            raise IntelligenceError(f"requirement {i} has no text")
        area = str(r.get("area") or "").strip().lower().replace(" ", "_")
        area = AREA_ALIASES.get(area, area)
        if area not in roles.AREAS:
            raise IntelligenceError(f"requirement {i}: unknown area {r.get('area')!r}; use one of {', '.join(roles.AREAS)}")
        rid = f"r_{i:02d}"
        if str(r.get("id") or "").strip():
            rename[str(r["id"]).strip()] = rid
        reqs.append({"id": rid, "area": area, "text": str(r["text"]).strip(),
                     "verification": str(r.get("verification") or "").strip()})
        if area in founder_areas(founder):
            reqs[-1]["owner"] = "founder"
    known = {r["id"] for r in reqs}
    ws_in = [w for w in pkg.get("workstreams") or [] if isinstance(w, dict) and str(w.get("name") or w.get("id") or "").strip()]
    ws_rename = {str(w.get("id") or "").strip(): f"ws_{i:02d}" for i, w in enumerate(ws_in, start=1)}
    workstreams, placed = [], set()
    for i, w in enumerate(ws_in, start=1):
        ids = [rename.get(x, x) for x in _slug_list(w.get("requirement_ids"))]
        ids = [x for x in dict.fromkeys(ids) if x in known and x not in placed]
        placed.update(ids)
        deps = [ws_rename.get(x) for x in _slug_list(w.get("depends_on"))]
        workstreams.append({"id": f"ws_{i:02d}", "name": str(w.get("name") or w.get("id")).strip(),
                            "requirement_ids": ids, "depends_on": [d for d in dict.fromkeys(deps) if d]})
    earns = any(r["area"] == "finance" for r in reqs) or any(
        r["area"] == "business" and EARNS.search(r["text"]) for r in reqs)
    if earns and not any(r["area"] == "market" for r in reqs):
        # a company must reach its customers: a business with no plan for it is missing its most common way to fail
        reqs.append({"id": f"r_{len(reqs) + 1:02d}", "area": "market", "added_by": "platform",
                     "text": "How the first customers will be reached, and what winning one costs.",
                     "verification": "Go-to-market plan"})
        known.add(reqs[-1]["id"])
    loose = [r["id"] for r in reqs if r["id"] not in placed]
    if loose:  # every requirement belongs to some workstream; the platform says when it had to place one
        workstreams.append({"id": f"ws_{len(workstreams) + 1:02d}", "name": "Other requirements",
                            "requirement_ids": loose, "depends_on": [], "placed_by": "platform"})
    ids = [w["id"] for w in workstreams]
    for w in workstreams:  # a dependency on itself or on a later workstream that loops back is dropped
        w["depends_on"] = [d for d in w["depends_on"] if d in ids and d != w["id"]]
    order, seen = [], set()

    def visit(wid, stack=()):
        if wid in stack:
            raise IntelligenceError(f"workstream dependencies loop through {wid}")
        if wid in seen:
            return
        for d in next(x for x in workstreams if x["id"] == wid)["depends_on"]:
            visit(d, stack + (wid,))
        seen.add(wid)
        order.append(wid)
    for wid in ids:
        visit(wid)
    longest: dict[str, list[str]] = {}
    for wid in order:
        w = next(x for x in workstreams if x["id"] == wid)
        best = max((longest[d] for d in w["depends_on"]), key=len, default=[])
        longest[wid] = best + [wid]
    critical = max(longest.values(), key=len, default=[])
    outs = pkg.get("outcomes")
    outs = [outs] if isinstance(outs, str) else outs if isinstance(outs, list) else []
    risks = []
    for r in pkg.get("risks") if isinstance(pkg.get("risks"), list) else []:
        if not isinstance(r, dict) or not str(r.get("text") or "").strip():
            continue
        area = str(r.get("area") or "").strip().lower().replace(" ", "_")
        area = AREA_ALIASES.get(area, area)
        if area not in roles.AREAS:
            raise IntelligenceError(f"risk {r.get('text')!r}: unknown area {r.get('area')!r}; use one of "
                                    f"{', '.join(roles.AREAS)}")
        risks.append({"id": f"k_{len(risks) + 1:02d}", "area": area, "text": str(r["text"]).strip()[:300]})
    return {"outcomes": [str(x).strip() for x in outs if str(x).strip()],
            "requirements": reqs, "risks": risks, "assumptions": assumptions(pkg, reqs, rename), "measures": measures(pkg),
            "workstreams": workstreams, "critical_path": critical,
            "verification": [f"{r['id']}: {r['verification']}" for r in reqs if r["verification"]]}


EARNS = re.compile(r"\b(pay|pays|paid|paying|price|pricing|revenue|sell|sells|selling|sales|subscri\w*|customers?)\b",
                   re.I)  # a business requirement about earning money; an internal tool's "business" goal is not
KINDS = {"desirability": "people want it", "viability": "it makes money", "feasibility": "it can be built"}
LEVELS = ("high", "medium", "low")


def assumptions(pkg: dict, reqs: list[dict], rename: dict | None = None) -> list[dict]:
    """The guesses the idea depends on, riskiest first: how bad it is if the guess is wrong (high, medium, low), then
    whether people want it, whether it makes money, whether it can be built. Each names the requirements whose work
    tests it and, when only a person can test it (talking to customers), the founder's step. Nothing here asks the
    founder anything: the plan tests what it can, and the rest is prepared as a next step."""
    known = {r["id"] for r in reqs}
    out = []
    for a in pkg.get("assumptions") if isinstance(pkg.get("assumptions"), list) else []:
        if not isinstance(a, dict) or not str(a.get("text") or "").strip():
            continue
        kind = str(a.get("kind") or "").strip().lower()
        risk = str(a.get("risk") or "medium").strip().lower()
        out.append({"text": str(a["text"]).strip()[:300], "kind": kind if kind in KINDS else "desirability",
                    "risk": risk if risk in LEVELS else "medium",
                    "tested_by": list(dict.fromkeys(y for x in _slug_list(a.get("tested_by"))
                                                    if (y := (rename or {}).get(x, x)) in known)),
                    "founder_step": str(a.get("founder_step") or "").strip()[:300]})
    out.sort(key=lambda a: (LEVELS.index(a["risk"]), list(KINDS).index(a["kind"])))
    for i, a in enumerate(out, start=1):
        a["id"] = f"a_{i:02d}"
    return out


def measures(pkg: dict) -> list[dict]:
    """How the founder will know it worked: each with its target and the line below which to rethink."""
    out = []
    for m in pkg.get("measures") if isinstance(pkg.get("measures"), list) else []:
        if not isinstance(m, dict) or not str(m.get("measure") or "").strip():
            continue
        out.append({"id": f"m_{len(out) + 1:02d}", "measure": str(m["measure"]).strip()[:200],
                    "target": str(m.get("target") or "").strip()[:80],
                    "rethink_below": str(m.get("rethink_below") or "").strip()[:80]})
    return out


def draft(run, messy: str) -> dict:
    """Stage 0 and the first half of Stage 1: the founder's words, structured. The founder can correct any field;
    nothing here is a gate."""
    if not (messy or "").strip():
        raise ObjectiveError("write the objective first")
    data, usage = run.intel.structure_objective(messy)
    run.record_call("objective", "objective_intelligence", "structure_objective", usage)
    structured = {k: str(data.get(k) or "").strip() for k in FIELDS}
    inferred = [k for k in _slug_list(data.get("inferred_fields")) if k in FIELDS]
    prev = run.objective()
    version = prev["version"] + 1 if prev else 1
    oid = (prev or {}).get("objective_id") or run.meta.get("objective_id") or f"obj_{run.cid}"
    obj = {"id": "obj_1", "objective_id": oid, "company_id": run.cid, "statement": messy.strip(),
           "structured": structured, "inferred_fields": inferred, "missing_fields": [k for k in FIELDS if not structured[k]],
           "founder_constraints": (prev or {}).get("founder_constraints") or {}, "status": "draft", "version": version,
           "notice": str(data.get("notice") or ""), "intelligence": usage["label"], "created_at": now(),
           "lifecycle": (prev or {}).get("lifecycle") or {"state": None, "history": []}}
    run.store.put("objective", "obj_1", obj)
    run.event("objective.created" if version == 1 else "objective.changed", "objective", "obj_1",
              {"version": version, "status": "draft", "statement_hash": digest(messy.strip()),
               "inferred_fields": inferred, "missing_fields": obj["missing_fields"], "objective_id": oid},
              actor="objective_intelligence")
    transition(run, "OBJECTIVE_CREATED", "the founder's words, structured", by="objective_intelligence")
    record_version(run, "draft")
    return obj


def edit(run, fields: dict) -> dict:
    obj = run.objective()
    changed = [k for k, v in (fields or {}).items()
               if k in FIELDS and str(v).strip() and str(v).strip() != obj["structured"][k]]
    for k in changed:
        obj["structured"][k] = str(fields[k]).strip()
    obj["inferred_fields"] = [k for k in obj["inferred_fields"] if k not in changed]
    obj["missing_fields"] = [k for k in FIELDS if not obj["structured"][k]]
    run.store.put("objective", "obj_1", obj)
    if changed:
        run.event("objective.changed", "objective", "obj_1", {"version": obj["version"], "status": obj["status"],
                  "fields_changed": changed}, actor="founder", actor_type="human", authority="founder")
    return obj


def set_constraints(run, constraints: dict) -> dict:
    clean = {k: str(v).strip() for k, v in (constraints or {}).items() if k in CONSTRAINT_KEYS and str(v or "").strip()}
    obj = run.objective()
    obj["founder_constraints"] = clean
    run.store.put("objective", "obj_1", obj)
    return obj


def submit(run) -> dict:
    """The founder hands the objective over. A field the brief does not state is recorded as such; then the
    objective is decomposed into requirements."""
    obj = run.objective()
    for k in obj["missing_fields"]:
        obj["structured"][k] = NOT_STATED
    obj.update({"status": "submitted", "submitted_at": now(), "missing_fields": [],
                "project": run.store.get("company", run.cid)["name"]})
    run.store.put("objective", "obj_1", obj)
    run.event("objective.changed", "objective", "obj_1", {"version": obj["version"], "status": "submitted",
              "constraints": sorted(obj["founder_constraints"])}, actor="founder", actor_type="human",
              authority="founder")
    transition(run, "OBJECTIVE_ACCEPTED", "the founder handed the objective over", by="founder")
    record_version(run, "active")
    return obj


def decompose(run, note: str = "") -> dict:
    """Stage 1: outcomes, requirements, risks, workstreams, critical path. The model's answer is checked; refused
    once, it is asked again with the reason; refused twice, the step stops and nothing is invented. note: the
    founder's feedback on the previous list."""
    founder = run.founder()
    pkg, usage = ask(lambda feedback: run.intel.decompose(run.objective_ctx(), feedback=feedback, note=note),
                     lambda d: validate_requirements(d, founder))
    run.record_call("objective", "objective_intelligence", "decompose", usage)
    version = run.objective()["version"]
    rec = {"id": "req_1", **pkg, "objective_version": version, "objective_id": objective_id(run),
           "acceptance_criteria": acceptance_criteria(pkg, version), "intelligence": usage["label"], "note": note,
           "created_at": now()}
    run.store.put("requirements", "req_1", rec)
    run.event("objective.decomposed", "objective", "obj_1", {"requirements": len(pkg["requirements"]),
              "workstreams": len(pkg["workstreams"]), "critical_path": pkg["critical_path"]},
              actor="objective_intelligence")
    run.event("requirements.created", "objective", objective_id(run), {
        "version": version, "requirements": len(pkg["requirements"]), "risks": len(pkg.get("risks") or []),
        "acceptance_criteria": len(rec["acceptance_criteria"]),
        "machine_verifiable": sum(1 for c in rec["acceptance_criteria"] if c["verification_method"] != "audit")},
        actor="objective_intelligence")
    transition(run, "OBJECTIVE_DECOMPOSED", "outcomes, requirements, risks and acceptance criteria",
               by="objective_intelligence")
    record_version(run, "active")
    return rec


# --- objective identity, lifecycle and versions (mandate 5, 36) ---------------------------------------------------
# The founder's objective has a first-class identity (objective_id) and a version. Its lifecycle is persisted and
# every move is checked against the allowed transitions; a move that is not allowed is refused and recorded, never
# made. A material change to the objective or its acceptance criteria makes a new version, and the version before it
# is superseded; what evidence the new version may inherit is decided by the inheritance policy, never silently.
from . import policies as _policies  # noqa: E402

TRANSITIONS = {
    "OBJECTIVE_CREATED": {"OBJECTIVE_ACCEPTED", "OBJECTIVE_CANCELLED"},
    "OBJECTIVE_ACCEPTED": {"OBJECTIVE_DECOMPOSED", "OBJECTIVE_CREATED", "OBJECTIVE_CANCELLED"},
    "OBJECTIVE_DECOMPOSED": {"OBJECTIVE_EXECUTING", "OBJECTIVE_BLOCKED", "OBJECTIVE_CANCELLED", "OBJECTIVE_PAUSED"},
    "OBJECTIVE_EXECUTING": {"OBJECTIVE_PAUSED", "OBJECTIVE_BLOCKED", "OBJECTIVE_COMPLETED", "OBJECTIVE_CANCELLED"},
    "OBJECTIVE_PAUSED": {"OBJECTIVE_EXECUTING", "OBJECTIVE_DECOMPOSED", "OBJECTIVE_BLOCKED", "OBJECTIVE_CANCELLED"},
    "OBJECTIVE_BLOCKED": {"OBJECTIVE_EXECUTING", "OBJECTIVE_PAUSED", "OBJECTIVE_DECOMPOSED", "OBJECTIVE_CANCELLED",
                          "OBJECTIVE_COMPLETED"},
    "OBJECTIVE_COMPLETED": {"OBJECTIVE_VERIFIED", "OBJECTIVE_BLOCKED", "OBJECTIVE_REOPENED"},
    "OBJECTIVE_VERIFIED": {"OBJECTIVE_CLOSED", "OBJECTIVE_REOPENED"},
    "OBJECTIVE_CLOSED": {"OBJECTIVE_REOPENED"},
    "OBJECTIVE_REOPENED": {"OBJECTIVE_EXECUTING", "OBJECTIVE_DECOMPOSED", "OBJECTIVE_BLOCKED", "OBJECTIVE_CANCELLED"},
    "OBJECTIVE_CANCELLED": set(),
    "OBJECTIVE_SUPERSEDED": set(),
}
assert set(TRANSITIONS) == set(_policies.body("objective")["states"])


def objective_id(run) -> str:
    obj = run.objective() or {}
    return obj.get("objective_id") or run.meta.get("objective_id") or f"obj_{run.cid}"


def state(run) -> str | None:
    return ((run.objective() or {}).get("lifecycle") or {}).get("state")


def can(frm: str | None, to: str) -> bool:
    return frm is None and to == "OBJECTIVE_CREATED" or frm == to or to in TRANSITIONS.get(frm or "", set())


def transition(run, to: str, reason: str, by: str = "orchestrator", strict: bool = False) -> bool:
    """Move the objective's lifecycle to the state to, if the lifecycle allows it. Not allowed: refused, recorded,
    and the state stays (strict: ObjectiveError)."""
    obj = run.objective()
    if obj is None:
        return False
    life = obj.get("lifecycle") or {"state": None, "history": []}
    frm = life.get("state")
    if frm == to:
        return True
    if not can(frm, to):
        run.event("objective.transition_refused", "objective", obj["objective_id"], {"from": frm, "to": to,
                  "reason": reason[:200], "version": obj["version"]}, actor=by, policy_decision="DENY")
        if strict:
            raise ObjectiveError(f"the objective cannot move from {frm} to {to}")
        return False
    life["history"] = (life.get("history") or []) + [{"from": frm, "to": to, "at": now(), "by": by,
                                                       "reason": reason[:200], "version": obj["version"]}]
    life.update(state=to, since=now())
    obj["lifecycle"] = life
    run.store.put("objective", "obj_1", obj)
    run.event("objective.state_changed", "objective", obj["objective_id"], {"from": frm, "to": to,
              "reason": reason[:200], "version": obj["version"]}, actor=by, aggregate_version=None)
    return True


def _hashes(obj: dict, req: dict | None) -> dict:
    return {"statement_hash": digest(obj.get("statement") or ""), "structured_hash": digest(obj.get("structured") or {}),
            "requirements_hash": digest([{k: r.get(k) for k in ("id", "area", "text", "verification")}
                                          for r in (req or {}).get("requirements", [])]) if req else None,
            "acceptance_hash": digest([{k: c.get(k) for k in ("criterion_id", "description", "verification_method",
                                                               "mandatory")}
                                        for c in (req or {}).get("acceptance_criteria", [])]) if req else None}


def record_version(run, status: str, change: dict | None = None) -> dict:
    """The version record: what this version is (hashes of its statement, fields, requirements and acceptance
    criteria), what changed from the one before, and what evidence it may inherit."""
    obj = run.objective()
    req = run.requirements() if (run.requirements() or {}).get("objective_version") == obj["version"] else None
    key = f"{obj['objective_id']}@{obj['version']}"
    old = run.store.get("objective_version", key) or {}
    rec = {**old, "id": key, "objective_id": obj["objective_id"], "version": obj["version"], "status": status,
           **_hashes(obj, req), "updated_at": now()}
    rec.setdefault("created_at", now())
    if change is not None:
        rec["change"] = change
        rec["parent_version"] = change.get("from_version")
        rec["inheritance"] = change.get("inheritance")
    run.store.put("objective_version", key, rec)
    return rec


def versions(run) -> list[dict]:
    oid = objective_id(run)
    return sorted([v for v in run.store.all("objective_version") if v.get("objective_id") == oid],
                  key=lambda v: v["version"])


def classify_change(before: dict, after: dict, requirements_changed: bool = False) -> dict:
    """Material or editorial, and what the new version inherits: none when what is being built or for whom
    changed, a prior only when the success criteria, constraints or acceptance changed, all of it when only an
    editorial field did."""
    ip = _policies.body("inheritance")
    op = _policies.body("objective")
    changed = sorted(k for k in set(before) | set(after) if str(before.get(k) or "") != str(after.get(k) or ""))
    if requirements_changed:
        changed = sorted(set(changed) | {"requirements"})
    material = bool(set(changed) & (set(op["material_fields"]) | {"requirements", "acceptance_criteria"}))
    if set(changed) & set(ip["none_if_changed"]):
        mode = "none"
    elif set(changed) & set(ip["prior_only_if_changed"]):
        mode = "prior_only"
    else:
        mode = "full"
    return {"fields": changed, "material": material, "inheritance": {"mode": mode, "relevance": ip["prior_relevance"]
            if mode == "prior_only" else (1.0 if mode == "full" else 0.0), "policy": _policies.version("inheritance")}}


def inheritance_map(run) -> dict:
    """For every earlier version: what authority its evidence has in the current one, combined along the chain of
    changes (none dominates, then a prior, then all of it)."""
    vs = {v["version"]: v for v in versions(run)}
    cur = int((run.objective() or {}).get("version") or 1)
    out, mode, rel = {}, "full", 1.0
    for v in range(cur, 1, -1):
        inh = (vs.get(v) or {}).get("inheritance") or {"mode": "full", "relevance": 1.0}
        if inh["mode"] == "none" or mode == "none":
            mode, rel = "none", 0.0
        elif inh["mode"] == "prior_only" or mode == "prior_only":
            mode, rel = "prior_only", rel * float(inh.get("relevance") or 0.5)
        out[str(v - 1)] = {"mode": mode, "relevance": round(rel, 4)}
    return out


def new_version(run, changes: dict, by: str = "founder") -> dict:
    """A change of the objective during a run, approved: the next version. The one before is superseded, kept, and
    its evidence carries over only as the inheritance policy says."""
    obj = run.objective()
    before = dict(obj["structured"])
    after = {**before, **changes}
    info = classify_change(before, after)
    prev = obj["version"]
    record_version(run, "superseded")
    run.event("objective.state_changed", "objective_version", f"{obj['objective_id']}@{prev}", {
              "from": "active", "to": "OBJECTIVE_SUPERSEDED", "version": prev, "superseded_by": prev + 1},
              actor=by, aggregate_version=None)
    obj["structured"] = after
    obj["version"] = prev + 1
    run.store.put("objective", "obj_1", obj)
    rec = record_version(run, "active", change={"from_version": prev, **info})
    run.event("objective.version_created", "objective", obj["objective_id"], {
        "version": obj["version"], "from_version": prev, "fields": info["fields"], "material": info["material"],
        "inheritance": info["inheritance"]["mode"]}, actor=by, aggregate_version=None)
    return rec


# --- machine-readable acceptance criteria (mandate 43) ---------------------------------------------------------------
METHOD_BY_VERIFIER = {"document": "document_verifier", "tests": "automated_tests", "backtest": "backtest",
                      "founder": "founder_review", "merge": "tests_on_main", "release": "live_health_and_smoke"}
DOC_AREAS = ("market", "finance", "legal", "business", "domain", "product")


def acceptance_criteria(pkg: dict, version: int) -> list[dict]:
    """Every requirement's acceptance criterion, with how it is verified: the method expected from its area now,
    refined from the tasks that cover it once there is a plan. The founder's own requirements are theirs, not
    mandatory for the team. Two criteria for the product as a whole close the list: it is live and healthy, and every
    mandatory criterion has verified work."""
    crit_areas = set(_policies.body("risk")["critical_areas"])
    risky = {k["area"] for k in pkg.get("risks") or []}
    out = []
    for r in pkg["requirements"]:
        method = "document_verifier" if r["area"] in DOC_AREAS else "automated_tests"
        out.append({"criterion_id": f"ac_{r['id']}", "requirement_id": r["id"],
                    "description": r.get("verification") or r["text"], "type": r["area"],
                    "verification_method": method, "verified_by_tasks": [], "mandatory": r.get("owner") != "founder",
                    "severity": "critical" if r["area"] in crit_areas or r["area"] in risky else "major",
                    "required_evidence": ["verification_record", "task_verified"], "objective_version": version})
    out.append({"criterion_id": "ac_prod_live", "requirement_id": None, "type": "production",
                "description": "The released product is live, answers its health check and passes its smoke checks.",
                "verification_method": "live_health_and_smoke", "mandatory": True, "severity": "critical",
                "required_evidence": ["deployment_verified", "live_check"], "objective_version": version,
                "verified_by_tasks": []})
    out.append({"criterion_id": "ac_prod_complete", "requirement_id": None, "type": "production",
                "description": "Every mandatory acceptance criterion has verified work behind it.",
                "verification_method": "audit", "mandatory": True, "severity": "critical",
                "required_evidence": ["audit"], "objective_version": version, "verified_by_tasks": []})
    return out


def task_acceptance(t: dict, version: int) -> list[dict]:
    """A task's acceptance criteria as the verification layer reads them: each with the verifier that evaluates it
    (from the task type, never the worker's choice), whether it is mandatory and how severe a miss is."""
    method = METHOD_BY_VERIFIER[roles.TASK_TYPES[t["kind"]]["verifier"]]
    sev = {"LOW": "major", "MEDIUM": "major", "HIGH": "critical"}[roles.risk(t["kind"])]
    return [{"criterion_id": f"ac_{t['id']}_{i}", "description": text, "type": "task", "verification_method": method,
             "mandatory": True, "severity": sev, "required_evidence": ["verification_record"],
             "requirement_ids": list(t.get("requirement_ids") or []), "objective_version": version}
            for i, text in enumerate(t.get("acceptance_criteria") or [], start=1)]


def acceptance_hash(t: dict) -> str:
    """The identity of what a task must meet: frozen when the plan is approved, checked before every verification,
    so neither a worker nor a candidate under calibration can move the bar it is measured against."""
    return digest({"criteria": [{k: c.get(k) for k in ("criterion_id", "description", "verification_method",
                                                        "mandatory", "severity")} for c in t.get("acceptance") or []],
                   "texts": list(t.get("acceptance_criteria") or []), "kind": t.get("kind"),
                   "requirement_ids": list(t.get("requirement_ids") or [])})
