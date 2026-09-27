"""The Workforce Synthesizer: which roles, in what quantity, the objective needs (Stages 2 and 3).

The human specifies the outcome, not the team. The synthesizer turns the objective package (requirements,
workstreams) into a proposed organization chosen from the role catalog, with the reason for every role and the
requirements it covers. The model proposes; validate_workforce checks it against the catalog and the requirements,
and the platform generates identities and reporting lines (roles.instantiate). The human then approves the
proposed organization; they do not construct it:

  approve   the organization is created as proposed
  reject    the synthesizer revises the proposal against the founder's feedback
  edit      only when governance allows a human override (settings: allow_workforce_override); the edit is checked
            like any proposal and recorded as an override

Every approval, rejection and override is a labelled decision in the audit trail.
"""
from __future__ import annotations

from . import policy, roles
from .intelligence_layer import router
from . import settings as project_settings
from .db import now
from .intelligence import IntelligenceError, as_int, ask
from .objective import _slug_list


class OverrideRefused(PermissionError):
    pass


def roles_for_area(area: str) -> list[str]:
    return [n for n, r in roles.ROLES.items() if area in r["areas"]]


PIPELINE = [("code", "writes the product's code"), ("review_merge", "reviews and merges the release"),
            ("deploy", "proposes the production deploy")]


def _gaps(merged: dict, reqs: dict) -> list[tuple[str, set[str], str]]:
    """What the proposed roles leave open, each with the catalog roles that would close it: a requirement area no
    proposed role covers, a pipeline task type no role owns, nobody to assign work."""
    present = [roles.role(m["role"]) for m in merged.values()]
    gaps = []
    for rid, r in reqs.items():
        if not any(r["area"] in p["areas"] for p in present):
            gaps.append((f"covers {rid} ({r['area']}: {r['text'][:80]})", set(roles_for_area(r["area"])), rid))
    for kind, what in PIPELINE:
        if not any(kind in p["owns"] for p in present):
            gaps.append((f"{what} ({kind})", {n for n, r in roles.ROLES.items() if kind in r["owns"]}, ""))
    if not any(m["role"] in roles.ASSIGNERS for m in merged.values()):
        gaps.append(("assigns the work", set(roles.ASSIGNERS), ""))
    return gaps


def complete(merged: dict, reqs: dict) -> None:
    """Close what the proposal leaves open from the catalog, one role at a time: the role that closes the most open
    gaps, the catalog's order breaking ties. The catalog decides which roles cover an area or own a task type, so
    this is the platform's rule, not a judgment the model has to get right; each added role says what it closes and
    the founder sees it at the workforce gate. Real models left a requirement area uncovered even when the refusal
    named the roles that close it (the [workforce] runs of 27 Sep: 36310111670, then 36315283277)."""
    order = list(roles.ROLES)
    while gaps := _gaps(merged, reqs):
        name = max(order, key=lambda n: (sum(n in fits for _, fits, _ in gaps), -order.index(n)))
        closes = [g for g in gaps if name in g[1]]
        if not closes:  # nothing in the catalog closes what is left (an area no role covers)
            raise IntelligenceError(f"no role in the catalog {gaps[0][0]}")
        why = "Added by Cynqra: the organization needs a role that " + "; ".join(g[0] for g in closes) + "."
        rids = [g[2] for g in closes if g[2]]
        if name == "Specialist":  # the field is the uncovered requirement's own
            text = reqs[rids[0]]["text"] if rids else "the company's field"
            field = " ".join(text.split()[:6]).rstrip(".,;:")
            merged[f"Specialist:{roles.field_slug(field)}"] = {
                "role": name, "field": field, "title": f"Specialist: {field}", "quantity": 1, "added_by": "platform",
                "why": why, "requirement_ids": rids}
            continue
        merged[name] = {"role": name, "quantity": 1, "added_by": "platform", "why": why, "requirement_ids": rids}


def validate_workforce(prop: dict, pkg: dict, close_gaps: bool = True) -> dict:
    """Stage 2's proposal, checked by the platform against the role catalog and the requirements: known roles
    within their limits, each with its reason. What it leaves open (a requirement area no proposed role covers; a
    role the delivery pipeline cannot run without: someone to write code, to review and merge, to deploy, to assign
    work) the platform closes from the catalog (complete). A founder's edit is not completed behind their back:
    what it leaves open is refused, naming the roles that close it."""
    if not isinstance(prop, dict) or not isinstance(prop.get("roles"), list) or not prop["roles"]:
        raise IntelligenceError("the workforce proposal has no roles")
    merged: dict[str, dict] = {}
    for r in prop["roles"]:
        if not isinstance(r, dict):
            raise IntelligenceError("every role must be an object")
        name = str(r.get("role") or "").strip()
        if name not in roles.ROLES:
            raise IntelligenceError(f"{name!r} is not in the role catalog")
        q = as_int(r.get("quantity"), 1) or 1
        if name == "Specialist":  # one worker per field the objective needs
            field = str(r.get("field") or "").strip()
            if not field:
                raise IntelligenceError("a Specialist needs its field, such as food safety or maritime law")
            title = str(r.get("title") or "").strip() or f"{field.title()} Specialist"
            m = merged.setdefault(f"Specialist:{roles.field_slug(field)}", {
                "role": name, "field": field, "title": title[:60], "quantity": 0, "why": "", "requirement_ids": []})
            q = 1 - m["quantity"]
        else:
            m = merged.setdefault(name, {"role": name, "quantity": 0, "why": "", "requirement_ids": []})
        m["quantity"] += q
        m["why"] = (m["why"] + " " + str(r.get("why") or "").strip()).strip()
        m["requirement_ids"] += [x for x in _slug_list(r.get("requirement_ids")) if x not in m["requirement_ids"]]
    for m in merged.values():
        cap = roles.role(m["role"])["max"]
        n = sum(x["quantity"] for x in merged.values() if x["role"] == m["role"])
        if n > cap:
            raise IntelligenceError(f"{m['role']}: {n} proposed, the catalog allows at most {cap}")
        if not m["why"]:
            raise IntelligenceError(f"{m['role']}: say why the role is needed")
    reqs = {r["id"]: r for r in pkg["requirements"]}
    for m in merged.values():
        areas = roles.role(m["role"])["areas"]
        m["requirement_ids"] = [x for x in m["requirement_ids"] if x in reqs and reqs[x]["area"] in areas]
    if not close_gaps and (gaps := _gaps(merged, reqs)):
        what, fits, _ = gaps[0]
        raise IntelligenceError(f"no role in the workforce {what}; add one of: "
                                f"{', '.join(n for n in roles.ROLES if n in fits)}")
    complete(merged, reqs)
    total = sum(m["quantity"] for m in merged.values())
    if total > roles.MAX_WORKERS:
        raise IntelligenceError(f"{total} workers proposed; at most {roles.MAX_WORKERS}")
    coverage: dict[str, list[str]] = {rid: [] for rid in reqs}
    for m in merged.values():
        for rid in m["requirement_ids"]:
            coverage[rid].append(m["role"])
    for rid, r in reqs.items():  # a requirement no role claimed goes to the first present role that covers its area
        if not coverage[rid]:
            fit = next(m for m in merged.values() if r["area"] in roles.role(m["role"])["areas"])
            fit["requirement_ids"].append(rid)
            coverage[rid].append(fit["role"])
    workers = roles.instantiate(list(merged.values()))
    return {"summary": str(prop.get("summary") or "").strip(), "roles": list(merged.values()), "coverage": coverage,
            "workers": workers}


def cost_by_role(run, prop: dict) -> dict:
    """What each proposed role is expected to cost per unit of its work on the best model now available: an early
    signal at the workforce gate. The Budget Engine prices the real budget from the roadmap."""
    s = project_settings.get(run.store)
    out = {}
    for r in prop["roles"]:
        best, _ = router.choose(run.registry, s, roles.staffing_kinds(r["role"]))
        if best is not None:
            out[r.get("title") or r["role"]] = round(best["expected_usd"] * r["quantity"], 4)
    return out


def evidence(prop: dict, requirements: dict) -> list[str]:
    lines = []
    for r in prop["roles"]:
        cost = (prop.get("cost_by_role") or {}).get(r.get("title") or r["role"])
        lines.append(f"{r.get('title') or roles.role(r['role'])['title']} x{r['quantity']}: {r['why']} Covers "
                     f"{', '.join(r['requirement_ids']) or 'no listed requirement'}."
                     + (f" Expected ${cost:.4f} on the best available model." if cost is not None else ""))
    n = len(requirements["requirements"])
    lines.append(f"{n} requirements, {sum(1 for who in prop['coverage'].values() if who)} covered.")
    return lines


def current(run) -> dict | None:
    cur = (run.store.get("workforce", "proposal") or {}).get("id")
    return run.store.get("proposal", cur) if cur else None


def propose(run, note: str = "") -> dict:
    """Stage 2, then Stage 3's decision: the proposal goes in front of the founder."""
    req = run.requirements()
    prop, usage = ask(lambda feedback: run.intel.synthesize(run.objective_ctx(), req, note=note, feedback=feedback),
                      lambda d: validate_workforce(d, req))
    run.record_call("objective", "workforce_synthesizer", "synthesize", usage)
    n = run.count("proposal") + 1
    prop.update({"id": f"wp_{n}", "version": n, "note": note, "intelligence": usage["label"], "created_at": now(),
                 "status": "proposed"})
    prop["cost_by_role"] = cost_by_role(run, prop)
    run.store.put("proposal", prop["id"], prop)
    run.store.put("workforce", "proposal", {"id": prop["id"]})
    run.event("workforce.proposed", "organization", "org_1", {"proposal": prop["id"], "roles": {
        r["role"]: r["quantity"] for r in prop["roles"]}, "workers": len(prop["workers"])}, actor="workforce_synthesizer")
    total = sum(r["quantity"] for r in prop["roles"])
    costs = prop["cost_by_role"]
    run.decision("approve_workforce",
                 problem=f"Cynqra proposes a {total}-worker organization for your objective. {prop['summary']}",
                 recommendation="Approve the proposed organization. Cynqra then assigns a model to every worker and "
                                "builds the roadmap and the budget for your second approval.",
                 risk="LOW", confidence="medium",
                 cost=f"about ${sum(costs.values()):.4f} of model work per unit of each role's work" if costs else
                      "priced in the roadmap and budget, next",
                 evidence=evidence(prop, req),
                 change="A role the requirements do not need, a missing one, or a quantity that is wrong.",
                 source="workforce_synthesizer", extra={"proposal": prop["id"]})
    return prop


def reject(run, note: str) -> dict:
    prop = current(run)
    prop["status"] = "rejected"
    run.store.put("proposal", prop["id"], prop)
    return propose(run, note=note or "The founder rejected the proposal.")


def override(prop: dict, edited_roles, requirements: dict, allowed: bool) -> dict:
    """A founder's edit of the proposed workforce, when governance allows it."""
    if not allowed:
        raise OverrideRefused("the governance policy does not allow editing the proposed workforce; reject it with "
                              "your feedback and Cynqra revises it")
    if not isinstance(edited_roles, list) or not edited_roles:
        raise IntelligenceError("an edited workforce needs roles")
    edited = validate_workforce({"summary": prop.get("summary", ""), "roles": edited_roles}, requirements,
                                close_gaps=False)
    edited["overridden"] = True
    return edited


def approve(run, edited_roles=None) -> dict:
    """The approved proposal becomes the organization: workers with identities, roles, authority and reporting
    lines generated from who is present."""
    prop = current(run)
    if edited_roles:
        prop = dict(prop, **override(prop, edited_roles, run.requirements(),
                                     project_settings.get(run.store)["allow_workforce_override"]))
        run.event("workforce.overridden", "organization", "org_1", {"proposal": prop["id"], "roles": {
            r["role"]: r["quantity"] for r in prop["roles"]}}, actor="founder", actor_type="human", authority="founder")
    prop["status"] = "approved"
    run.store.put("proposal", prop["id"], prop)
    workers = prop["workers"]
    org = {"id": "org_1", "company_id": run.cid, "proposal": prop["id"], "version": 1, "status": "approved",
           "workers": [w["id"] for w in workers], "roles": {r["role"]: r["quantity"] for r in prop["roles"]},
           "reports_to": {w["id"]: w["reports_to"] for w in workers},
           "services": [{"id": "verification", "title": "Verification Service",
                         "note": "Platform service, not a worker. Runs the verifier of every task type."}]}
    run.store.put("organization", "org_1", org)
    run.event("organization.changed", "organization", "org_1", {"proposal": prop["id"], "worker_count": len(workers),
              "version": 1})
    for t in workers:
        w = dict(t)
        w.update({"company_id": run.cid,
                  "authority_policy_id": f"{policy.POLICY_VERSION}:{t['role']}", "status": "active",
                  "performance_profile": {"verified": 0, "first_pass": 0, "reworks": 0, "blockers": 0}})
        run.store.put("worker", t["id"], w)
        run.event("worker.hired", "worker", t["id"], {"role": t["role"], "reports_to": t["reports_to"]})
    return org
