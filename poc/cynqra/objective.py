"""Objective Intelligence: Stages 0 and 1 of the product definition.

The founder hands over a project name, the outcome they want, a budget and any constraints (deadline, geography,
technology, compliance, risk tolerance). They do not describe a team. Cynqra structures the outcome into seven
fields, then decomposes it into requirements by area, groups them into workstreams, and computes the critical path.
The model proposes; the platform checks (validate_requirements) and owns every identifier.
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


def validate_requirements(pkg: dict) -> dict:
    """Stage 1's objective package, checked by the platform: known areas, ids it owns (r_01, ws_01), workstreams that
    hold every requirement, dependencies without cycles, and the critical path computed from them."""
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
    return {"outcomes": [str(x).strip() for x in outs if str(x).strip()],
            "requirements": reqs, "workstreams": workstreams, "critical_path": critical,
            "verification": [f"{r['id']}: {r['verification']}" for r in reqs if r["verification"]]}


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
    obj = {"id": "obj_1", "company_id": run.cid, "statement": messy.strip(), "structured": structured,
           "inferred_fields": inferred, "missing_fields": [k for k in FIELDS if not structured[k]],
           "founder_constraints": (prev or {}).get("founder_constraints") or {}, "status": "draft", "version": version,
           "notice": str(data.get("notice") or ""), "intelligence": usage["label"], "created_at": now()}
    run.store.put("objective", "obj_1", obj)
    run.event("objective.created" if version == 1 else "objective.changed", "objective", "obj_1",
              {"version": version, "status": "draft", "statement_hash": digest(messy.strip()),
               "inferred_fields": inferred, "missing_fields": obj["missing_fields"]}, actor="objective_intelligence")
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
    return obj


def decompose(run) -> dict:
    """Stage 1: requirements, workstreams, critical path. The model's answer is checked; refused once, it is asked
    again with the reason; refused twice, the step stops and nothing is invented."""
    pkg, usage = ask(lambda feedback: run.intel.decompose(run.objective_ctx(), feedback=feedback), validate_requirements)
    run.record_call("objective", "objective_intelligence", "decompose", usage)
    rec = {"id": "req_1", **pkg, "objective_version": run.objective()["version"], "intelligence": usage["label"],
           "created_at": now()}
    run.store.put("requirements", "req_1", rec)
    run.event("objective.decomposed", "objective", "obj_1", {"requirements": len(pkg["requirements"]),
              "workstreams": len(pkg["workstreams"]), "critical_path": pkg["critical_path"]},
              actor="objective_intelligence")
    return rec
