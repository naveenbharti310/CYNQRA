"""The Workforce Synthesizer: the organization the objective needs, built as a founder builds a real company
(Stages 2 and 3).

The founder is the CEO and states the outcome; Cynqra works out the team. First Cynqra proposes the cofounders the company
needs, each with its reason (a CTO for a product that is software, a Chief Product Officer for who it serves and
what it must do, a CFO when the value is money, a Chief Compliance Officer for a regulated business). Then each
cofounder, speaking as that cofounder, proposes the team for its own area, with the reason for every hire and the
requirements it covers. The model proposes; the platform checks every answer against the catalog and the
requirements (validate_cofounders, validate_team, validate_workforce), closes what is left open from the catalog
and says so, and generates identities and reporting lines (roles.instantiate). The founder approves the whole
organization once:

  approve   the organization is created as proposed
  reject    the synthesizer revises the proposal against the founder's feedback (add or drop a cofounder, say)
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


def _title(m: dict) -> str:
    return m.get("title") or roles.role(m["role"])["title"]


def _gaps(merged: dict, reqs: dict) -> list[tuple[str, set[str], str]]:
    """What the proposed roles leave open, each with the catalog roles that would close it: a requirement area no
    proposed role covers, a pipeline task type no role owns, no cofounder to lead the work."""
    present = [roles.role(m["role"]) for m in merged.values()]
    gaps = []
    for rid, r in reqs.items():
        if not any(r["area"] in p["areas"] for p in present):
            gaps.append((f"covers {rid} ({r['area']}: {r['text'][:80]})", set(roles_for_area(r["area"])), rid))
    for kind, what in PIPELINE:
        if not any(kind in p["owns"] for p in present):
            gaps.append((f"{what} ({kind})", {n for n, r in roles.ROLES.items() if kind in r["owns"]}, ""))
    if not any(roles.is_cofounder(m["role"]) for m in merged.values()):
        gaps.append(("leads the work as a cofounder", set(roles.COFOUNDERS), ""))
    return gaps


def complete(merged: dict, reqs: dict) -> None:
    """Close what the proposal leaves open from the catalog, one role at a time: the role that closes the most open
    gaps, the catalog's order breaking ties. The catalog decides which roles cover an area or own a task type, so
    this is the platform's rule, not a judgment the model has to get right; each added role says what it closes and
    the founder sees it at the workforce gate. Real models left a requirement area uncovered even when the refusal
    named the roles that close it (the [workforce] runs of 27 Sep: 36310111670, then 36315283277). A team role
    added here reports to the cofounder its role prefers, among those present."""
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


def _entry(merged: dict, r, where: str) -> dict:
    """One proposed role, read into merged: a known role, its quantity, its reason and requirement ids. A Specialist
    is one worker per field."""
    if not isinstance(r, dict):
        raise IntelligenceError(f"{where}: every role must be an object")
    name = str(r.get("role") or "").strip()
    if name not in roles.ROLES:
        raise IntelligenceError(f"{where}: {name!r} is not in the role catalog")
    q = as_int(r.get("quantity"), 1) or 1
    if name == "Specialist":
        field = str(r.get("field") or "").strip()
        if not field:
            raise IntelligenceError("a Specialist needs its field, such as food safety or maritime law")
        title = str(r.get("title") or "").strip() or f"{field.title()} Specialist"
        m = merged.setdefault(f"Specialist:{roles.field_slug(field)}", {
            "role": name, "field": field, "title": title[:60], "quantity": 0, "why": "", "requirement_ids": []})
        q = 1 - m["quantity"]
    else:
        m = merged.setdefault(name, {"role": name, "quantity": 0, "why": "", "requirement_ids": []})
    if roles.is_cofounder(name):  # a company has one of each cofounder
        if q > 1:
            raise IntelligenceError(f"{where}: {q} proposed; a company has one {roles.role(name)['title']}")
        m["quantity"] = 1
    else:
        m["quantity"] += q
    m["why"] = (m["why"] + " " + str(r.get("why") or "").strip()).strip()
    m["requirement_ids"] += [x for x in _slug_list(r.get("requirement_ids")) if x not in m["requirement_ids"]]
    if r.get("lead") and not roles.is_cofounder(name):
        m.setdefault("lead", str(r["lead"]).strip())
    return m


def _key(m: dict) -> str:
    return f"Specialist:{roles.field_slug(m['field'])}" if m["role"] == "Specialist" else m["role"]


def validate_cofounders(prop: dict, pkg: dict) -> dict:
    """Step one: the cofounders the company needs, each with its reason. Only cofounder roles; the teams come next."""
    if not isinstance(prop, dict) or not isinstance(prop.get("cofounders"), list) or not prop["cofounders"]:
        raise IntelligenceError("the proposal names no cofounders")
    merged: dict[str, dict] = {}
    for r in prop["cofounders"]:
        name = str((r or {}).get("role") or "").strip() if isinstance(r, dict) else ""
        if name in roles.ROLES and not roles.is_cofounder(name):
            raise IntelligenceError(f"{name} is not a cofounder role; cofounders are one of "
                                    f"{', '.join(roles.COFOUNDERS)}, and each cofounder proposes its own team next")
        _entry(merged, r, "cofounders")
    for m in merged.values():
        if not m["why"]:
            raise IntelligenceError(f"{m['role']}: say why the company needs this cofounder")
    reqs = {r["id"]: r for r in pkg["requirements"]}
    for m in merged.values():
        m["requirement_ids"] = [x for x in m["requirement_ids"] if x in reqs and reqs[x]["area"] in roles.role(m["role"])["areas"]]
    return {"summary": str(prop.get("summary") or "").strip(), "cofounders": list(merged.values())}


def hireable(lead: str, cofounders: list[str]) -> list[str]:
    """The team roles a cofounder may hire: those it may lead, and those no cofounder present may lead."""
    out = []
    for n, r in roles.ROLES.items():
        if r["tier"] != "team":
            continue
        present = [c for c in r["reports_to"] if c in cofounders]
        if lead in r["reports_to"] or not present:
            out.append(n)
    return out


def validate_team(prop: dict, pkg: dict, lead: str, cofounders: list[str], taken: dict[str, str]) -> dict:
    """Step two, for one cofounder: the team for its area, each hire with its reason. A cofounder hires only the
    roles it may lead, and not one another cofounder has already hired. An empty team is allowed: a cofounder may do
    its part alone."""
    if not isinstance(prop, dict) or not isinstance(prop.get("roles"), list):
        raise IntelligenceError("the team proposal needs a list of roles (it may be empty)")
    may = hireable(lead, cofounders)
    merged: dict[str, dict] = {}
    for r in prop["roles"]:
        name = str((r or {}).get("role") or "").strip() if isinstance(r, dict) else ""
        if name in roles.ROLES and roles.is_cofounder(name):
            raise IntelligenceError(f"{name} is a cofounder, chosen before the teams; propose only your own team")
        if name in roles.ROLES and name not in may:
            raise IntelligenceError(f"{roles.role(name)['title']} belongs on another cofounder's team; you may hire: "
                                    f"{', '.join(may)}")
        m = _entry(merged, r, f"{lead}'s team")
        m["lead"] = lead
    for key, m in merged.items():
        if key in taken:
            raise IntelligenceError(f"{_title(m)} is already on the {taken[key]}'s team; do not hire it twice")
        if not m["why"]:
            raise IntelligenceError(f"{_title(m)}: say why your team needs this role")
        if m["quantity"] > roles.role(m["role"])["max"]:
            raise IntelligenceError(f"{m['role']}: {m['quantity']} proposed, the catalog allows at most "
                                    f"{roles.role(m['role'])['max']}")
    return {"summary": str(prop.get("summary") or "").strip(), "roles": list(merged.values())}


def validate_workforce(prop: dict, pkg: dict, close_gaps: bool = True) -> dict:
    """The whole organization, checked by the platform against the role catalog and the requirements: known roles
    within their limits, each with its reason, every team member led by a cofounder. It reads the two-step proposal
    ({"cofounders": [...], "teams": {cofounder: {"roles": [...]}}}) or a flat list of roles ({"roles": [...]}, a
    team role may name its "lead"). What it leaves open (a requirement area no role covers; a role the delivery
    pipeline cannot run without: someone to write code, to review and merge, to deploy; a cofounder to lead) the
    platform closes from the catalog (complete). A founder's edit is not completed behind their back: what it leaves
    open is refused, naming the roles that close it."""
    if not isinstance(prop, dict):
        raise IntelligenceError("the workforce proposal must be an object")
    merged: dict[str, dict] = {}
    summaries: dict[str, str] = {}
    if isinstance(prop.get("cofounders"), list):
        for r in prop["cofounders"]:
            _entry(merged, r, "cofounders")
        teams = prop.get("teams") if isinstance(prop.get("teams"), dict) else {}
        for lead, team in teams.items():
            team = team if isinstance(team, dict) else {}
            if str(team.get("summary") or "").strip():
                summaries[lead] = str(team["summary"]).strip()
            for r in team.get("roles") if isinstance(team.get("roles"), list) else []:
                m = _entry(merged, r, f"{lead}'s team")
                m.setdefault("lead", lead)
    elif isinstance(prop.get("roles"), list) and prop["roles"]:
        for r in prop["roles"]:
            _entry(merged, r, "workforce")
    else:
        raise IntelligenceError("the workforce proposal has no roles")
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
    cofounders = [m["role"] for m in merged.values() if roles.is_cofounder(m["role"])]
    for m in merged.values():  # every team member led by a cofounder present: its hirer, else its role's preference
        m["tier"] = roles.role(m["role"])["tier"]
        if m["tier"] == "team":
            m["lead"] = roles.lead_role(m["role"], cofounders, m.get("lead"))
        else:
            m.pop("lead", None)
    coverage: dict[str, list[str]] = {rid: [] for rid in reqs}
    for m in merged.values():
        for rid in m["requirement_ids"]:
            coverage[rid].append(m["role"])
    for rid, r in reqs.items():  # a requirement no role claimed goes to the first present role that covers its area
        if not coverage[rid]:
            fit = next(m for m in merged.values() if r["area"] in roles.role(m["role"])["areas"])
            fit["requirement_ids"].append(rid)
            coverage[rid].append(fit["role"])
    # cofounders first, in the catalog's order; each cofounder's team after it
    order = list(roles.ROLES)
    rows = sorted(merged.values(), key=lambda m: (order.index(m.get("lead") or m["role"]), 0 if m["tier"] == "cofounder"
                                                  else 1, order.index(m["role"])))
    workers = roles.instantiate(rows)
    return {"summary": str(prop.get("summary") or "").strip(), "roles": rows, "cofounders": cofounders,
            "team_summaries": summaries, "coverage": coverage, "workers": workers}


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
    """The organization chart in words: each cofounder and why, then its team and why each hire."""
    lines = []
    costs = prop.get("cost_by_role") or {}

    def line(r, indent=""):
        cost = costs.get(r.get("title") or r["role"])
        return (f"{indent}{_title(r)} x{r['quantity']}: {r['why']} Covers "
                f"{', '.join(r['requirement_ids']) or 'no listed requirement'}."
                + (f" Expected ${cost:.4f} on the best available model." if cost is not None else ""))
    for c in [r for r in prop["roles"] if r.get("tier") == "cofounder"]:
        lines.append("Cofounder " + line(c))
        team = [r for r in prop["roles"] if r.get("lead") == c["role"]]
        why_team = (prop.get("team_summaries") or {}).get(c["role"])
        if why_team:
            lines.append(f"  The {_title(c)}'s team: {why_team}")
        lines += [line(r, "  ") for r in team]
    n = len(requirements["requirements"])
    lines.append(f"{n} requirements, {sum(1 for who in prop['coverage'].values() if who)} covered.")
    return lines


def current(run) -> dict | None:
    cur = (run.store.get("workforce", "proposal") or {}).get("id")
    return run.store.get("proposal", cur) if cur else None


def _draft(run, req: dict, note: str) -> tuple[dict, dict]:
    """The two steps: the cofounders, then each cofounder's team. Every answer is checked and asked again once with
    the reason; the whole organization is then checked and completed by the platform."""
    cof, usage = ask(lambda feedback: run.intel.cofounders(run.objective_ctx(), req, note=note, feedback=feedback),
                     lambda d: validate_cofounders(d, req))
    run.record_call("objective", "workforce_synthesizer", "cofounders", usage)
    names = [c["role"] for c in cof["cofounders"]]
    names.sort(key=list(roles.ROLES).index)
    teams: dict[str, dict] = {}
    taken: dict[str, str] = {}
    labels = [usage["label"]]
    for lead in names:
        persona = roles.prompt_text({"id": f"w_{roles.role(lead)['slug']}", "role": lead,
                                     "title": roles.role(lead)["title"]})
        team, u = ask(lambda feedback, lead=lead, persona=persona: run.intel.build_team(
                          run.objective_ctx(), req, cofounder=lead, cofounders=names, hired=dict(taken), note=note,
                          feedback=feedback, persona=persona),
                      lambda d, lead=lead: validate_team(d, req, lead, names, taken))
        run.record_call("objective", "workforce_synthesizer", f"team:{lead}", u)
        labels.append(u["label"])
        teams[lead] = team
        for m in team["roles"]:
            taken[_key(m)] = roles.role(lead)["title"]
    prop = validate_workforce({"summary": cof["summary"], "cofounders": cof["cofounders"], "teams": teams}, req)
    return prop, {"label": ", ".join(dict.fromkeys(labels))}


def propose(run, note: str = "") -> dict:
    """Stage 2, then Stage 3's decision: the proposal goes in front of the founder."""
    req = run.requirements()
    prop, usage = _draft(run, req, note)
    n = run.count("proposal") + 1
    prop.update({"id": f"wp_{n}", "version": n, "note": note, "intelligence": usage["label"], "created_at": now(),
                 "status": "proposed"})
    prop["cost_by_role"] = cost_by_role(run, prop)
    run.store.put("proposal", prop["id"], prop)
    run.store.put("workforce", "proposal", {"id": prop["id"]})
    run.event("workforce.proposed", "organization", "org_1", {"proposal": prop["id"], "roles": {  # by title: two
        r.get("title") or r["role"]: r["quantity"] for r in prop["roles"]}, "workers": len(prop["workers"]),  # Specialists stay two
        "cofounders": prop["cofounders"]}, actor="workforce_synthesizer")
    total = sum(r["quantity"] for r in prop["roles"])
    cofs = [r for r in prop["roles"] if r["tier"] == "cofounder"]
    costs = prop["cost_by_role"]
    run.decision("approve_workforce",
                 problem=f"Cynqra proposes {len(cofs)} cofounders for your company "
                         f"({', '.join(_title(c) for c in cofs)}) and {total - len(cofs)} team members they chose for "
                         f"their areas. {prop['summary']}",
                 recommendation="Approve the organization. Cynqra then gives every member the AI best suited to its "
                                "work and builds the roadmap and the budget for your second approval.",
                 risk="LOW", confidence="medium",
                 cost=f"about ${sum(costs.values()):.4f} of model work per unit of each role's work" if costs else
                      "priced in the roadmap and budget, next",
                 evidence=evidence(prop, req),
                 change="A cofounder the company does not need or is missing, a hire a team does not need, or a "
                        "missing one.",
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
    edited["team_summaries"] = prop.get("team_summaries") or {}
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
           "cofounders": [w["id"] for w in workers if w["tier"] == "cofounder"],
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
