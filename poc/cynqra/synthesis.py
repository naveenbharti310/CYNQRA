"""The Workforce Synthesizer: the organization the objective needs, built as a founder builds a real company
(Stages 2 and 3).

The founder is the CEO and states the outcome; Cynqra works out the team. First Cynqra proposes the cofounders the company
needs, each with its reason (a CTO for a product that is software, a Chief Product Officer for who it serves and
what it must do, a CFO when the value is money, a Chief Compliance Officer for a regulated business). Then each
cofounder, speaking as that cofounder, proposes the team for its own area, with the reason for every hire and the
requirements it owns, helps with and the risks it watches. The model proposes; the platform checks every answer
against the catalog and the confirmed requirements and risks (validate_cofounders, validate_team,
validate_workforce), closes what is left open from the catalog and says so, gives every requirement exactly one
owner, and generates identities and reporting lines (roles.instantiate). Then an independent challenger tries to make
the team smaller, and the platform's own removal test decides what goes (seats.py): the founder sees the recommended
team, the lean one next to it, and for every seat who asked for it, what it owns and what would be left without it.
The founder approves the whole organization once:

  approve   the organization is created as proposed (or as the lean team, when the founder chooses it)
  reject    the synthesizer revises the proposal against the founder's feedback (add or drop a cofounder, say)
  edit      only when governance allows a human override (settings: allow_workforce_override); the edit is checked
            like any proposal and recorded as an override

Every approval, rejection and override is a labelled decision in the audit trail.
"""
from __future__ import annotations

import re

from . import people, lessons, policy, roles, seats
from .budget import dollars
from .intelligence_layer import router
from . import settings as project_settings
from .db import now
from .intelligence import IntelligenceError, as_int, ask
from .objective import TEAM_LIMIT, _slug_list, founder_areas


class OverrideRefused(PermissionError):
    pass


def roles_for_area(area: str) -> list[str]:
    return [n for n, r in roles.ROLES.items() if area in r["areas"]]


PIPELINE = [("code", "writes the product's code"), ("review_merge", "reviews and merges the release"),
            ("deploy", "proposes the production deploy")]


def _title(m: dict) -> str:
    return m.get("title") or roles.role(m["role"])["title"]


def _gaps(merged: dict, reqs: dict, risks: dict | None = None) -> list[tuple[str, set[str], str]]:
    """What the proposed roles leave open, each with the catalog roles that would close it: a requirement area no
    proposed role covers, a risk nobody can watch, a pipeline task type no role owns, no cofounder to lead the work.
    The founder's own requirements need no role."""
    present = [roles.role(m["role"]) for m in merged.values()]
    gaps = []
    for rid, r in reqs.items():
        if r.get("owner") != "founder" and not any(r["area"] in p["areas"] for p in present):
            gaps.append((f"covers {rid} ({r['area']}: {r['text'][:80]})", set(roles_for_area(r["area"])), rid))
    for kid, k in (risks or {}).items():
        if not k.get("founder") and not any(k["area"] in p["areas"] for p in present):
            gaps.append((f"watches {kid} ({k['area']}: {k['text'][:80]})", set(roles_for_area(k["area"])), ""))
    for kind, what in PIPELINE:
        if not any(kind in p["owns"] for p in present):
            gaps.append((f"{what} ({kind})", {n for n, r in roles.ROLES.items() if kind in r["owns"]}, ""))
    if not any(roles.is_cofounder(m["role"]) for m in merged.values()):
        gaps.append(("leads the work as a cofounder", set(roles.COFOUNDERS), ""))
    return gaps


def complete(merged: dict, reqs: dict, risks: dict | None = None, founder_leads: list[str] | None = None) -> None:
    """Close what the proposal leaves open from the catalog, one role at a time: the role that closes the most open
    gaps, the catalog's order breaking ties. The catalog decides which roles cover an area or own a task type, so
    this is the platform's rule, not a judgment the model has to get right; each added role says what it closes and
    the founder sees it at the workforce gate. Real models left a requirement area uncovered even when the refusal
    named the roles that close it (the [workforce] runs of 27 Sep: 36310111670, then 36315283277). A team role
    added here reports to the cofounder its role prefers, among those present."""
    order = [n for n in roles.ROLES if n not in (founder_leads or [])]  # never the seat the founder holds
    while gaps := _gaps(merged, reqs, risks):
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
                "requested_by": "Cynqra", "why": why, "requirement_ids": rids, "supports": [], "risk_ids": []}
            continue
        merged[name] = {"role": name, "quantity": 1, "added_by": "platform", "requested_by": "Cynqra", "why": why,
                        "requirement_ids": rids, "supports": [], "risk_ids": []}


def fit_seats(merged: dict, reqs: dict, risks: dict | None = None) -> list[str]:
    """Keep the organization within roles.MAX_WORKERS, the platform's own way, before refusing it: paid run
    37589136743 failed its SaaS objective at "18 workers proposed; at most 16", counted after the platform had closed
    gaps itself. First a second or third seat of one role gives way, the largest first (the role stays, so what it
    covers stays covered); then a team seat whose areas other seats cover too (nothing is left open without it). A
    cofounder, a seat the platform added and a Specialist are never cut. Each change is said for the founder, who
    sees the organization at the workforce gate. Returns the changes."""
    total = lambda: sum(m["quantity"] for m in merged.values())  # noqa: E731
    changes = []
    while total() > roles.MAX_WORKERS:
        many = [k for k, m in merged.items() if m["quantity"] > 1 and not roles.is_cofounder(m["role"])]
        if not many:
            break
        k = max(many, key=lambda k: (merged[k]["quantity"], k))
        merged[k]["quantity"] -= 1
        changes.append(f"{_title(merged[k])}: {merged[k]['quantity'] + 1} seats to {merged[k]['quantity']}")
    order = list(roles.ROLES)
    spare = sorted((k for k, m in merged.items() if not roles.is_cofounder(m["role"]) and m["role"] != "Specialist"
                    and m.get("added_by") != "platform"),
                   key=lambda k: (len(merged[k].get("requirement_ids") or []) + len(merged[k].get("risk_ids") or []),
                                  -order.index(merged[k]["role"]), k))
    for k in spare:
        if total() <= roles.MAX_WORKERS:
            break
        if _gaps({x: m for x, m in merged.items() if x != k}, reqs, risks):
            continue  # something would be left open without it
        changes.append(f"{_title(merged.pop(k))}: left out, every area it covers is covered by another seat")
    return changes


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
        title = str(r.get("title") or "").strip()
        if not field and title:  # the field it named in the title ("Geospatial Data Specialist"): read, not invented
            field = re.sub(r"\bspecialist\b", "", title, flags=re.I).strip(" -–—,:")
        if not field:  # said exactly, so the one retry can put it where it belongs
            raise IntelligenceError('a Specialist needs its field as "field", for example {"role": "Specialist", '
                                    '"field": "food safety", "title": "Food Safety Specialist"}')
        title = title or f"{field.title()} Specialist"
        m = merged.setdefault(f"Specialist:{roles.field_slug(field)}", {
            "role": name, "field": field, "title": title[:60], "quantity": 0, "why": "", "requirement_ids": [],
            "supports": [], "risk_ids": []})
        q = 1 - m["quantity"]
    else:
        m = merged.setdefault(name, {"role": name, "quantity": 0, "why": "", "requirement_ids": [], "supports": [],
                                     "risk_ids": []})
    if roles.is_cofounder(name):  # a company has one of each cofounder
        if q > 1:
            raise IntelligenceError(f"{where}: {q} proposed; a company has one {roles.role(name)['title']}")
        m["quantity"] = 1
    else:
        m["quantity"] += q
    m["why"] = (m["why"] + " " + str(r.get("why") or "").strip()).strip()
    for key in ("requirement_ids", "supports", "risk_ids"):
        m.setdefault(key, [])
        m[key] += [x for x in _slug_list(r.get(key)) if x not in m[key]]
    if r.get("requested_by"):
        m.setdefault("requested_by", str(r["requested_by"]).strip()[:40])
    for label in ("added_by", "mode", "mode_why"):  # kept when a checked team is read again
        if r.get(label):
            m[label] = str(r[label]).strip()[:300]
    if r.get("lead") and not roles.is_cofounder(name):
        m.setdefault("lead", str(r["lead"]).strip())
    return m


def _key(m: dict) -> str:
    return f"Specialist:{roles.field_slug(m['field'])}" if m["role"] == "Specialist" else m["role"]


def _claims(m: dict, reqs: dict, risks: dict) -> None:
    """What a role may claim: requirements and risks in its own areas, never the founder's own requirements."""
    areas = roles.role(m["role"])["areas"]
    for key in ("requirement_ids", "supports"):
        m[key] = [x for x in m.get(key) or [] if x in reqs and reqs[x]["area"] in areas and reqs[x].get("owner") != "founder"]
    m["supports"] = [x for x in m["supports"] if x not in m["requirement_ids"]]
    m["risk_ids"] = [x for x in m.get("risk_ids") or [] if x in risks and risks[x]["area"] in areas]


def _risks(pkg: dict, founder: dict | None) -> dict:
    mine = founder_areas(founder)
    return {k["id"]: dict(k, founder=k["area"] in mine) for k in pkg.get("risks") or []}


def validate_cofounders(prop: dict, pkg: dict, founder: dict | None = None) -> dict:
    """Step one: the cofounders the company needs, each with its reason. Only cofounder roles; the teams come next.
    A seat the founder holds themselves is never proposed: cofounders fill the founder's gaps."""
    if not isinstance(prop, dict) or not isinstance(prop.get("cofounders"), list) or not prop["cofounders"]:
        raise IntelligenceError("the proposal names no cofounders")
    merged: dict[str, dict] = {}
    for r in prop["cofounders"]:
        name = str((r or {}).get("role") or "").strip() if isinstance(r, dict) else ""
        if name in roles.ROLES and not roles.is_cofounder(name):
            raise IntelligenceError(f"{name} is not a cofounder role; cofounders are one of "
                                    f"{', '.join(roles.COFOUNDERS)}, and each cofounder proposes its own team next")
        if name in (founder or {}).get("leads", []):
            raise IntelligenceError(f"the founder leads the {roles.role(name)['title']}'s area themselves; propose "
                                    "cofounders only for the areas the founder does not lead")
        _entry(merged, r, "cofounders")
    if not merged:
        raise IntelligenceError("the proposal names no cofounders")
    for m in merged.values():
        if not m["why"]:
            raise IntelligenceError(f"{m['role']}: say why the company needs this cofounder")
    reqs = {r["id"]: r for r in pkg["requirements"]}
    for m in merged.values():
        _claims(m, reqs, _risks(pkg, founder))
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


def validate_team(prop: dict, pkg: dict, lead: str, cofounders: list[str], taken: dict[str, str],
                  limit: int = 0) -> dict:
    """Step two, for one cofounder: the team for its area, each hire with its reason. A cofounder hires only the
    roles it may lead, and not one another cofounder has already hired, and no more seats than its stage allows
    (limit: a real leader's headcount budget). An empty team is allowed: a cofounder may do its part alone."""
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
        m["requested_by"] = lead
    if limit and (n := sum(m["quantity"] for m in merged.values())) > limit:
        raise IntelligenceError(f"{n} seats proposed; at this stage a cofounder hires at most {limit}. Keep the seats "
                                "that own work no one else can do")
    for key, m in merged.items():
        if key in taken:
            raise IntelligenceError(f"{_title(m)} is already on the {taken[key]}'s team; do not hire it twice")
        if not m["why"]:
            raise IntelligenceError(f"{_title(m)}: say why your team needs this role")
        if m["quantity"] > roles.role(m["role"])["max"]:
            raise IntelligenceError(f"{m['role']}: {m['quantity']} proposed, the catalog allows at most "
                                    f"{roles.role(m['role'])['max']}")
    return {"summary": str(prop.get("summary") or "").strip(), "roles": list(merged.values())}


def validate_workforce(prop: dict, pkg: dict, close_gaps: bool = True, founder: dict | None = None) -> dict:
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
            _entry(merged, r, "cofounders")["requested_by"] = "Cynqra"
        teams = prop.get("teams") if isinstance(prop.get("teams"), dict) else {}
        for lead, team in teams.items():
            team = team if isinstance(team, dict) else {}
            if str(team.get("summary") or "").strip():
                summaries[lead] = str(team["summary"]).strip()
            for r in team.get("roles") if isinstance(team.get("roles"), list) else []:
                m = _entry(merged, r, f"{lead}'s team")
                m.setdefault("lead", lead)
                m.setdefault("requested_by", lead)
    elif isinstance(prop.get("roles"), list) and prop["roles"]:
        for r in prop["roles"]:
            m = _entry(merged, r, "workforce")
            m.setdefault("requested_by", "Cynqra" if roles.is_cofounder(m["role"]) else "you")
    else:
        raise IntelligenceError("the workforce proposal has no roles")
    for m in merged.values():
        cap = roles.role(m["role"])["max"]
        n = sum(x["quantity"] for x in merged.values() if x["role"] == m["role"])
        if n > cap:
            raise IntelligenceError(f"{m['role']}: {n} proposed, the catalog allows at most {cap}")
        if not m["why"]:
            raise IntelligenceError(f"{m['role']}: say why the role is needed")
    leads = (founder or {}).get("leads") or []
    for m in merged.values():
        if m["role"] in leads:
            raise IntelligenceError(f"the founder leads the {roles.role(m['role'])['title']}'s area themselves")
    reqs = {r["id"]: r for r in pkg["requirements"]}
    risks = _risks(pkg, founder)
    for m in merged.values():
        _claims(m, reqs, risks)
    if not close_gaps and (gaps := _gaps(merged, reqs, risks)):
        what, fits, _ = gaps[0]
        raise IntelligenceError(f"no role in the workforce {what}; add one of: "
                                f"{', '.join(n for n in roles.ROLES if n in fits and n not in leads)}")
    complete(merged, reqs, risks, leads)
    fitted = fit_seats(merged, reqs, risks) if close_gaps else []  # a founder's own edit is refused, not trimmed
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
    # cofounders first, in the catalog's order; each cofounder's team after it
    order = list(roles.ROLES)
    rows = sorted(merged.values(), key=lambda m: (order.index(m.get("lead") or m["role"]), 0 if m["tier"] == "cofounder"
                                                  else 1, order.index(m["role"])))
    assigned: dict[str, dict] = {"requirements": {}, "risks": {}}
    for rid, r in reqs.items():  # a requirement no role claimed goes to the first role that covers its area, and says so
        if r.get("owner") == "founder" or any(rid in m["requirement_ids"] + m["supports"] for m in rows):
            continue
        fit = next(m for m in rows if r["area"] in roles.role(m["role"])["areas"])
        fit["requirement_ids"].append(rid)
        assigned["requirements"][rid] = seats.key(fit)
    for kid, k in risks.items():  # a risk nobody watches goes to a role that covers its area: a team member first
        if k["founder"] or any(kid in m["risk_ids"] for m in rows):
            continue
        fits = [m for m in rows if k["area"] in roles.role(m["role"])["areas"]]
        fit = next((m for m in fits if m["tier"] == "team"), fits[0])
        fit["risk_ids"].append(kid)
        assigned["risks"][kid] = seats.key(fit)
    owners = seats.owners(rows, reqs)
    coverage: dict[str, list[str]] = {rid: (["founder"] if r.get("owner") == "founder" else []) for rid, r in reqs.items()}
    for m in rows:
        for rid in m["requirement_ids"] + m["supports"]:
            coverage[rid].append(m["role"])
    watchers = {kid: (["founder"] if k["founder"] else []) + [seats.key(m) for m in rows if kid in m["risk_ids"]]
                for kid, k in risks.items()}
    workers = roles.instantiate(rows)
    return {"summary": str(prop.get("summary") or "").strip(), "roles": rows, "cofounders": cofounders,
            "team_summaries": summaries, "coverage": coverage, "owners": owners, "watchers": watchers,
            "assigned": assigned, "founder_owned": [rid for rid, r in reqs.items() if r.get("owner") == "founder"],
            "workers": workers, "seat_limit": fitted}


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
    """The organization chart in words: each cofounder, then its team, each seat with who asked for it, what it owns,
    helps with and watches, and what would be left without it."""
    lines = []
    costs = prop.get("cost_by_role") or {}
    card = {c["seat"]: c for c in prop.get("cards") or []}

    def line(r, indent=""):
        c = card.get(seats.key(r)) or {}
        cost = costs.get(r.get("title") or r["role"])
        asked = "proposed by Cynqra" if r["tier"] == "cofounder" and c.get("requested_by") == "Cynqra" else \
            ("added by Cynqra to fill a gap" if c.get("added_by_cynqra") else f"requested by {c.get('requested_by')}")
        return (f"{indent}{_title(r)} x{r['quantity']} ({asked}): {r['why']} Owns "
                f"{', '.join(c.get('owns') or []) or 'no requirement'}"
                + (f"; helps with {', '.join(c['supports'])}" if c.get("supports") else "")
                + (f"; watches {', '.join(c['controls'])}" if c.get("controls") else "") + ". Without it: "
                + ("; ".join(c.get("without") or []) or "nothing would be left undone") + "."
                + (f" As {r['mode']}: {r.get('mode_why', '')}" if r.get("mode") else "")
                + (f" Expected {dollars(cost)} on the best available model." if cost is not None else ""))
    for c in [r for r in prop["roles"] if r.get("tier") == "cofounder"]:
        lines.append("Cofounder " + line(c))
        team = [r for r in prop["roles"] if r.get("lead") == c["role"]]
        why_team = (prop.get("team_summaries") or {}).get(c["role"])
        if why_team:
            lines.append(f"  The {_title(c)}'s team: {why_team}")
        lines += [line(r, "  ") for r in team]
    n = len(requirements["requirements"])
    lines.append(f"{n} requirements, {sum(1 for who in prop['coverage'].values() if who)} covered, each with one owner; "
                 f"{len(requirements.get('risks') or [])} risks, each watched.")
    return lines


def current(run) -> dict | None:
    cur = (run.store.get("workforce", "proposal") or {}).get("id")
    return run.store.get("proposal", cur) if cur else None


def _flat(rows: list[dict]) -> list[dict]:
    """Seats as a flat list of roles, keeping who asked for each, its lead and its labels."""
    return [dict(m) for m in rows]


def _challenge(run, req: dict, prop: dict, founder: dict) -> dict:
    """The independent challenge. Its answer is checked like any other; if it cannot be read, the platform's own
    removal test still runs on every seat, and the founder is told."""
    try:
        answer, usage = ask(lambda feedback: run.intel.challenge(run.objective_ctx(), req, seats.cards(prop, req),
                                                                 founder=founder, feedback=feedback),
                            seats.read_challenge)
        run.record_call("objective", "team_challenger", "challenge", usage)
        return answer
    except IntelligenceError as exc:
        return {"seats": [], "failure_stories": [], "unreadable": str(exc)[:200]}


def _draft(run, req: dict, note: str, founder: dict | None = None) -> tuple[dict, dict]:
    """The two steps: the cofounders, then each cofounder's team. Every answer is checked and asked again once with
    the reason; the whole organization is then checked and completed by the platform, challenged, and set next to
    the lean team. founder: the profile to build around, the founder's own by default."""
    founder = founder or run.founder()
    limit = TEAM_LIMIT[founder["stage"]]
    cof, usage = ask(lambda feedback: run.intel.cofounders(run.objective_ctx(), req, note=note, feedback=feedback,
                                                           founder=founder),
                     lambda d: validate_cofounders(d, req, founder))
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
                          feedback=feedback, persona=persona, founder=founder, limit=limit),
                      lambda d, lead=lead: validate_team(d, req, lead, names, taken, limit))
        run.record_call("objective", "workforce_synthesizer", f"team:{lead}", u)
        labels.append(u["label"])
        teams[lead] = team
        for m in team["roles"]:
            taken[_key(m)] = roles.role(lead)["title"]
    proposed = validate_workforce({"summary": cof["summary"], "cofounders": cof["cofounders"], "teams": teams}, req,
                                  founder=founder)
    challenge = _challenge(run, req, proposed, founder)
    applied = seats.apply_challenge(proposed["roles"], req, challenge)
    prop = validate_workforce({"summary": cof["summary"], "roles": _flat(applied["rows"])}, req, founder=founder)
    prop["team_summaries"] = proposed["team_summaries"]
    prop["assigned"] = proposed["assigned"]  # what Cynqra had to fill in the proposers' answers
    prop["seat_limit"] = proposed["seat_limit"] + prop["seat_limit"]  # what gave way to keep within the limit
    prop["proposed_seats"] = sum(m["quantity"] for m in proposed["roles"])
    prop["challenge"] = {"removed": applied["removed"], "overruled": applied["overruled"],
                         "failure_stories": applied["failure_stories"], "unreadable": challenge.get("unreadable", "")}
    prop["cards"] = seats.cards(prop, req)
    ln = seats.lean(prop["roles"], req)
    lean_prop = validate_workforce({"summary": "The lean team.", "roles": _flat(ln["rows"])}, req, founder=founder)
    prop["lean"] = {"seats": ln["seats"], "left_out": ln["left_out"], "fewer": ln["fewer"],
                    "roles": lean_prop["roles"], "workers": lean_prop["workers"], "owners": lean_prop["owners"],
                    "watchers": lean_prop["watchers"], "coverage": lean_prop["coverage"],
                    "cards": seats.cards(lean_prop, req)}  # its own cards: who takes over what in the lean team
    prop["why_team"] = seats.why(prop, req, lessons.track_record(run, {r["area"] for r in req["requirements"]}))
    return prop, {"label": ", ".join(dict.fromkeys(labels))}


def _name(run, prop: dict, keep: dict | None = None) -> None:
    """The founder meets the people with the proposal: every proposed member is named, and the lean team's members
    are the same people."""
    people.name_all(run, prop["workers"], keep=keep)
    names, used = {}, set()
    for lw in prop["lean"]["workers"]:  # the same seat, else a colleague in the same role (one engineer of two)
        same = [w for w in prop["workers"] if w["id"] == lw["id"]] or \
               [w for w in prop["workers"] if w["role"] == lw["role"] and w.get("field") == lw.get("field")]
        pick = next((w for w in same if w["name"] not in used), None)
        if pick:
            names[lw["id"]] = pick["name"]
            used.add(pick["name"])
    people.name_all(run, prop["lean"]["workers"], keep=names)


def propose(run, note: str = "") -> dict:
    """Stage 2, then Stage 3's decision: the proposal goes in front of the founder, with the lean team beside it."""
    req = run.requirements()
    prop, usage = _draft(run, req, note)
    _name(run, prop)
    n = run.count("proposal") + 1
    prop.update({"id": f"wp_{n}", "version": n, "note": note, "intelligence": usage["label"], "created_at": now(),
                 "status": "proposed", "founder": _profile(run.founder())})
    prop["cost_by_role"] = cost_by_role(run, prop)
    prop["lean"]["cost_by_role"] = cost_by_role(run, prop["lean"])
    run.store.put("proposal", prop["id"], prop)
    run.store.put("workforce", "proposal", {"id": prop["id"]})
    run.event("workforce.proposed", "organization", "org_1", {"proposal": prop["id"], "roles": {  # by title: two
        r.get("title") or r["role"]: r["quantity"] for r in prop["roles"]}, "workers": len(prop["workers"]),  # Specialists stay two
        "cofounders": prop["cofounders"], "cut_by_challenge": [r["seat"] for r in prop["challenge"]["removed"]],
        "lean_seats": prop["lean"]["seats"]}, actor="workforce_synthesizer")
    total = sum(r["quantity"] for r in prop["roles"])
    cofs = [r for r in prop["roles"] if r["tier"] == "cofounder"]
    costs = prop["cost_by_role"]
    w = prop["why_team"]
    run.decision("approve_workforce",
                 problem=f"Cynqra proposes {len(cofs)} cofounders for your company "
                         f"({', '.join(_title(c) for c in cofs)}) and {total - len(cofs)} team members they chose for "
                         f"their areas. {prop['summary']}",
                 recommendation="Approve the recommended team, or choose the lean one. Cynqra then gives every member "
                                "the AI best suited to its work and builds the roadmap and the budget for your second "
                                "approval.",
                 risk="LOW", confidence=w["confidence"],
                 cost=f"about {dollars(sum(costs.values()))} of model work per unit of each role's work" if costs else
                      "priced in the roadmap and budget, next",
                 evidence=w["lines"] + evidence(prop, req),
                 change="A cofounder the company does not need or is missing, a hire a team does not need, or a "
                        "missing one.",
                 source="workforce_synthesizer", extra={"proposal": prop["id"], "options": ["recommended", "lean"]})
    return prop


def _profile(founder: dict | None) -> dict:
    """The part of the founder's profile an organization is built around."""
    f = founder or {}
    return {"leads": list(f.get("leads") or []), "stage": f.get("stage"), "background": f.get("background") or ""}


def _seats(prop: dict) -> dict[str, int]:
    return {_title(r): r["quantity"] for r in prop.get("roles") or []}


FIT_NOTE = ("The founder has now described themselves. Build the organization around them: no seat for a skill or "
            "field the founder brings themselves, fewer or lighter seats where they are strong, and the capabilities "
            "they lack.")


def needs_refit(prop: dict | None, founder: dict) -> bool:
    """Whether the organization was built around a different founder than the one who has just described
    themselves. The seats the founder leads are fitted by the engine without a new draft, and a team the founder
    edited by hand at step 2 is kept as they edited it."""
    used = (prop or {}).get("founder")
    now_ = _profile(founder)
    return used is not None and not (prop or {}).get("overridden") and (used["background"], used["stage"]) != (now_["background"], now_["stage"])


def refit(run, founder: dict) -> dict:
    """Step 3: Cynqra understands the founder, then constructs the organization around them. The approved plan's
    organization is drafted again with the founder's background and stage, every step checked and challenged as
    before, and it replaces the one approved at step 2 before anyone is staffed. The seats the founder leads stay in
    the draft and are fitted afterwards (they report to the founder). What changed is recorded, for step 4."""
    old = current(run)
    req = run.requirements()
    base = _profile(founder)
    base["leads"] = list((old.get("founder") or {}).get("leads") or [])
    prop, usage = _draft(run, req, "", founder=base)  # the founder's profile carries the instruction to fit it
    keep = {w["id"]: w["name"] for w in run.workers() if w.get("name")}  # a seat that remains keeps its person
    _name(run, prop, keep=keep)
    n = run.count("proposal") + 1
    prop.update({"id": f"wp_{n}", "version": n, "note": FIT_NOTE, "intelligence": usage["label"], "created_at": now(),
                 "status": "proposed", "founder": _profile(founder), "fitted_from": old["id"]})
    prop["cost_by_role"] = cost_by_role(run, prop)
    prop["lean"]["cost_by_role"] = cost_by_role(run, prop["lean"])
    was, will = _seats(old), _seats(prop if old.get("chosen") != "lean" else dict(prop, roles=prop["lean"]["roles"]))
    def seat(t: str) -> str:  # a new or gone seat by its title; a changed headcount says from what to what
        return t if not (was.get(t) and will.get(t)) else f"{t} ({was[t]} to {will[t]})"
    prop["fitted"] = {"added": [seat(t) for t, q in will.items() if q > was.get(t, 0)],
                      "removed": [seat(t) for t, q in was.items() if q > will.get(t, 0)]}
    run.store.put("proposal", prop["id"], prop)
    run.store.put("workforce", "proposal", {"id": prop["id"]})
    for w in run.workers():  # hired at step 2, never staffed or given work: the new organization replaces them
        run.store.delete("worker", w["id"])
        run.event("worker.left", "worker", w["id"], {"why": "the organization was rebuilt around the founder"})
    run.event("workforce.fitted_to_founder", "organization", "org_1", {"proposal": prop["id"], "from": old["id"],
              **prop["fitted"]}, actor="workforce_synthesizer")
    return approve(run, option=old.get("chosen") or "recommended")


def reject(run, note: str) -> dict:
    prop = current(run)
    prop["status"] = "rejected"
    run.store.put("proposal", prop["id"], prop)
    return propose(run, note=note or "The founder rejected the proposal.")


def override(prop: dict, edited_roles, requirements: dict, allowed: bool, founder: dict | None = None) -> dict:
    """A founder's edit of the proposed workforce, when governance allows it."""
    if not allowed:
        raise OverrideRefused("the governance policy does not allow editing the proposed workforce; reject it with "
                              "your feedback and Cynqra revises it")
    if not isinstance(edited_roles, list) or not edited_roles:
        raise IntelligenceError("an edited workforce needs roles")
    edited = validate_workforce({"summary": prop.get("summary", ""), "roles": edited_roles}, requirements,
                                close_gaps=False, founder=founder)
    edited["team_summaries"] = prop.get("team_summaries") or {}
    edited["cards"] = seats.cards(edited, requirements)
    edited["overridden"] = True
    return edited


def approve(run, edited_roles=None, option: str = "recommended", keep_names: dict | None = None) -> dict:
    """The approved proposal becomes the organization: workers with identities, roles, authority and reporting
    lines generated from who is present. option: the recommended team, or the lean one set next to it. The people
    the founder met in the proposal keep their names; a seat the founder added gets a person now."""
    prop = current(run)
    met = {w["id"]: w["name"] for w in prop.get("workers") or [] if w.get("name")}
    keep_names = {**met, **(keep_names or {})}
    if option == "lean":
        ln = prop["lean"]
        prop = dict(prop, roles=ln["roles"], workers=ln["workers"], owners=ln["owners"], watchers=ln["watchers"],
                    coverage=ln["coverage"], chosen="lean")
        prop["cards"] = ln.get("cards") or seats.cards(prop, run.requirements())
        run.event("workforce.lean_chosen", "organization", "org_1", {"proposal": prop["id"], "seats": ln["seats"]},
                  actor="founder", actor_type="human", authority="founder")
    elif edited_roles:
        prop = dict(prop, **override(prop, edited_roles, run.requirements(),
                                     project_settings.get(run.store)["allow_workforce_override"], run.founder()))
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
    hired = [dict(t) for t in workers]
    people.name_all(run, hired, keep=keep_names)  # every member is a person, with a name
    for w in hired:
        w.update({"company_id": run.cid,
                  "authority_policy_id": f"{policy.POLICY_VERSION}:{w['role']}", "status": "active",
                  "performance_profile": {"verified": 0, "first_pass": 0, "reworks": 0, "blockers": 0}})
        run.store.put("worker", w["id"], w)
        run.event("worker.hired", "worker", w["id"], {"role": w["role"], "reports_to": w["reports_to"],
                                                      "person": w["name"]})
    run.event("workforce.created", "organization", "org_1", {
        "workers": len(hired), "cofounders": [w["id"] for w in hired if w["tier"] == "cofounder"],
        "roles": {r["role"]: r["quantity"] for r in prop["roles"]}, "option": option,
        "objective_version": (run.objective() or {}).get("version")})
    return org
