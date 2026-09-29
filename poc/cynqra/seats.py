"""Every seat has to earn its place: the seat cards, the independent challenge, the lean team, the answer to "why
this team?", and the check of the plan's work (Stages 2, 3 and 5).

A real company does not hire because "we should have one". Every hire has an owner who asked for it and a written
case: the outcomes it owns, what fails without it, when it starts, what it costs. Someone outside the team tries to
cut it, and the team is checked again once the work is planned. Cynqra does the same, with rules the platform owns:

  owners       every requirement has exactly one owner (the seat answerable for it); other seats may help
  card         for every seat: who asked for it, what it owns, helps with and watches, and what would be left without
               it (the removal test). A seat that leaves nothing behind "may not be needed".
  challenge    an independent reviewer, whose only job is to make the team smaller, gives verdicts (cut, merge,
               advisor, later) and the likeliest reasons the company would fail. The platform decides: a cut is
               accepted only when the removal test agrees, and an overruled cut says why.
  lean         the smallest team that still covers every requirement, risk and step of the delivery, set next to the
               recommended one with what each extra seat adds
  why          the answer to "why are you confident this is the team?", with a confidence that comes from these checks
  work_check   once the roadmap exists: a member with no work is shown to the founder, who can remove it, and every
               member joins with its first task
"""
from __future__ import annotations

from . import roles
from .intelligence import IntelligenceError

VERDICTS = ("keep", "cut", "merge", "advisor", "later")
# The steps every delivery needs someone for. A seat that is the only one able to do one of them is needed.
DUTIES = {"code": "write the product's code", "review_merge": "review and merge the release",
          "deploy": "put the release live"}


def key(m: dict) -> str:
    """A seat's key: its role, or Specialist:<field> for a Specialist (one per field)."""
    return f"Specialist:{roles.field_slug(m['field'])}" if m["role"] == "Specialist" else m["role"]


def title(m: dict) -> str:
    return m.get("title") or roles.role(m["role"])["title"]


def owners(rows: list[dict], reqs: dict) -> dict[str, str]:
    """Exactly one owner per requirement. Among the seats that claim it, the one doing the work owns it: a team member
    before its cofounder, then the seat with the fewest claims (the most focused), then the order of the proposal.
    A requirement only helped with is owned by its first helper. The founder's own requirements are theirs."""
    out = {}
    for rid, r in reqs.items():
        if r.get("owner") == "founder":
            out[rid] = "founder"
            continue
        claim = [m for m in rows if rid in m["requirement_ids"]] or [m for m in rows if rid in m.get("supports", [])]
        if claim:
            best = min(claim, key=lambda m: (m["tier"] == "cofounder", len(m["requirement_ids"]), rows.index(m)))
            out[rid] = key(best)
    return out


def _duty_holders(rows: list[dict]) -> dict[str, list[str]]:
    return {d: [key(m) for m in rows if d in roles.role(m["role"])["owns"]] for d in DUTIES}


def cards(prop: dict, requirements: dict) -> list[dict]:
    """A card for every seat, with the removal test: what would be left with no one working on it if this seat went.
    A team seat is needed when it works on a requirement no other team seat works on, is the only seat watching a
    risk, or is the only seat able to do a step every delivery needs. A cofounder is needed when it leads a team,
    or is the only seat on a requirement, a risk or such a step."""
    rows = prop["roles"]
    reqs = {r["id"]: r for r in requirements["requirements"]}
    own = prop.get("owners") or owners(rows, reqs)
    duties = _duty_holders(rows)
    out = []
    for m in rows:
        k, cof = key(m), m["tier"] == "cofounder"
        others = [x for x in rows if x is not m and (cof or x["tier"] == "team")]
        works = m["requirement_ids"] + m.get("supports", [])
        alone = [rid for rid in works if not any(rid in x["requirement_ids"] + x.get("supports", []) for x in others)]
        watch_alone = [kid for kid in m.get("risk_ids", []) if not any(kid in x.get("risk_ids", []) for x in rows if x is not m)]
        sole_duties = [d for d, who in duties.items() if who == [k]]
        team = [key(x) for x in rows if x.get("lead") == m["role"] and x["tier"] == "team"]
        both = lambda xs: xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]
        without = ([f"{both(alone)} would have no one working on {'it' if len(alone) == 1 else 'them'}"] if alone else []) \
            + ([f"no one would watch {both(watch_alone)}"] if watch_alone else []) \
            + [f"no one could {DUTIES[d]}" for d in sole_duties] \
            + ([f"its team ({', '.join(title(x) for x in rows if key(x) in team)}) would have no one to lead it"]
               if cof and team else [])
        out.append({"seat": k, "role": m["role"], "title": title(m), "tier": m["tier"], "quantity": m["quantity"],
                    "requested_by": m.get("requested_by") or ("Cynqra" if cof else m.get("lead") or "Cynqra"),
                    "added_by_cynqra": m.get("added_by") == "platform", "why": m["why"],
                    "owns": [rid for rid, who in own.items() if who == k], "supports": list(m.get("supports", [])),
                    "works_on": works, "controls": list(m.get("risk_ids", [])), "leads": team,
                    "without": without, "needed": bool(without)})
    return out


def _find(answer_seat: str, rows: list[dict]) -> dict | None:
    s = str(answer_seat or "").strip().lower()
    for m in rows:
        if s in (key(m).lower(), title(m).lower(), m["role"].lower()):
            return m
    return None


def read_challenge(answer) -> dict:
    """The challenger's answer, checked: known verdicts, a reason for each."""
    if not isinstance(answer, dict) or not isinstance(answer.get("seats"), list):
        raise IntelligenceError("the challenge needs a list of seats (it may be empty) and failure stories")
    verdicts = []
    for v in answer["seats"]:
        if not isinstance(v, dict):
            continue
        verdict = str(v.get("verdict") or "").strip().lower()
        if verdict not in VERDICTS:
            raise IntelligenceError(f"verdict {v.get('verdict')!r}: use one of {', '.join(VERDICTS)}")
        if verdict != "keep" and not str(v.get("why") or "").strip():
            raise IntelligenceError(f"{v.get('seat')}: give the reason for the verdict")
        verdicts.append({"seat": str(v.get("seat") or "").strip(), "verdict": verdict,
                         "into": str(v.get("into") or "").strip(), "why": str(v.get("why") or "").strip()})
    stories = answer.get("failure_stories")
    stories = [stories] if isinstance(stories, str) else stories if isinstance(stories, list) else []
    return {"seats": verdicts, "failure_stories": [str(x).strip()[:300] for x in stories if str(x).strip()][:3]}


def apply_challenge(rows: list[dict], requirements: dict, challenge: dict | None) -> dict:
    """The platform decides what the challenge changes. A seat the removal test finds nothing behind is cut, whether
    or not the challenger named it; a seat the challenger would cut or merge but that is the only one on something
    stays, and the record says why. Advisor and later are kept as labels on the seat. Cutting a seat can leave a
    cofounder with no team, so the test runs until nothing changes."""
    challenge = challenge or {"seats": [], "failure_stories": []}
    rows = [dict(m) for m in rows]
    said = {}
    for v in challenge["seats"]:
        m = _find(v["seat"], rows)
        if m is not None:
            said[key(m)] = v
    removed, overruled = [], []
    while True:
        prop = {"roles": rows}
        cut = next((c for c in cards(prop, requirements) if not c["needed"]), None)
        if cut is None:
            break
        m = next(x for x in rows if key(x) == cut["seat"])
        v = said.get(cut["seat"])
        removed.append({"seat": cut["seat"], "title": cut["title"], "requested_by": cut["requested_by"],
                        "why": (v or {}).get("why") or "No requirement, risk or delivery step would be left without "
                                                           "it: every piece of its work has someone else on it.",
                        "by": "challenger and platform" if v and v["verdict"] in ("cut", "merge") else "platform"})
        rows.remove(m)
    for c in cards({"roles": rows}, requirements):
        v = said.get(c["seat"])
        if v and v["verdict"] in ("cut", "merge"):
            overruled.append({"seat": c["seat"], "title": c["title"], "verdict": v["verdict"], "why": v["why"],
                              "kept_because": "; ".join(c["without"])})
    for m in rows:
        v = said.get(key(m))
        if v and v["verdict"] in ("advisor", "later"):
            m["mode"] = v["verdict"]
            m["mode_why"] = v["why"]
    return {"rows": rows, "removed": removed, "overruled": overruled,
            "failure_stories": challenge["failure_stories"]}


def _can_take(m: dict, other: dict, area: str) -> bool:
    """Whether another seat can take over a seat's work in this area: it covers the area and can do every kind of
    work the seat does (a Project Manager cannot take over a QA Engineer's test code)."""
    a, b = roles.role(m["role"]), roles.role(other["role"])
    return area in b["areas"] and set(a["owns"]) <= set(b["owns"])


def lean(rows: list[dict], requirements: dict) -> dict:
    """The smallest team that still covers everything: one of each role, and every team seat whose work another seat
    can take over (it covers the same area and can do every kind of work the seat does) left out, as long as every
    risk is watched and every step of the delivery has someone. The cofounders stay: they lead. What each left-out seat would have added
    is its own reason."""
    reqs = {r["id"]: r for r in requirements["requirements"]}
    risk_area = {k["id"]: k["area"] for k in requirements.get("risks") or []}
    team = [dict(m, quantity=1) if m["quantity"] > 1 and not m.get("field") else dict(m) for m in rows]
    fewer = [{"seat": key(m), "title": title(m), "from": m["quantity"], "to": 1} for m in rows
             if m["quantity"] > 1 and not m.get("field")]
    left_out = []
    for m in sorted([x for x in team if x["tier"] == "team"], key=lambda x: len(x["requirement_ids"])):
        rest = [x for x in team if x is not m]
        takes = {}
        for rid in m["requirement_ids"] + m.get("supports", []):
            by = next((x for x in rest if _can_take(m, x, reqs[rid]["area"])
                       and rid in x["requirement_ids"] + x.get("supports", [])), None) or \
                next((x for x in rest if _can_take(m, x, reqs[rid]["area"])), None)
            if by is None:
                break
            takes[rid] = key(by)
        else:
            risks_ok = all(any(kid in x.get("risk_ids", []) or risk_area.get(kid) in roles.role(x["role"])["areas"]
                               for x in rest) for kid in m.get("risk_ids", []))
            duties_ok = all(any(d in roles.role(x["role"])["owns"] for x in rest)
                            for d in DUTIES if d in roles.role(m["role"])["owns"])
            if risks_ok and duties_ok:
                team.remove(m)
                left_out.append({"seat": key(m), "title": title(m), "work_goes_to": takes,
                                 "adds": m["why"] or "a specialist on its work"})
    return {"rows": team, "left_out": left_out, "fewer": fewer,
            "seats": sum(m["quantity"] for m in team)}


def why(prop: dict, requirements: dict, history: dict | None = None) -> dict:
    """The answer to "why are you confident this is the team my company needs?", from the checks, with the
    confidence they support: high when every requirement has one owner, every risk someone watching it, every seat
    passed the removal test and the proposers needed no help; medium when Cynqra had to fill a gap they left or the
    challenge could not be read; low when anything is left without an owner."""
    reqs = requirements["requirements"]
    risks = requirements.get("risks") or []
    own = prop.get("owners") or {}
    unowned = [r["id"] for r in reqs if r["id"] not in own]
    unwatched = [k["id"] for k in risks if not (prop.get("watchers") or {}).get(k["id"])]
    ch = prop.get("challenge") or {}
    filled = sorted(set((prop.get("assigned") or {}).get("requirements", {})) |
                    set((prop.get("assigned") or {}).get("risks", {})))
    added = [c["title"] for c in prop.get("cards") or [] if c["added_by_cynqra"]]
    if unowned or unwatched:
        confidence = "low"
    elif filled or added or ch.get("unreadable"):
        confidence = "medium"
    else:
        confidence = "high"
    n_seats = sum(m["quantity"] for m in prop["roles"])
    names = {key(m): title(m) for m in prop["roles"]}
    name = lambda k: names.get(k) or ("you" if k == "founder" else roles.ROLES.get(k, {}).get("title", k))
    lines = [f"Every one of the {len(reqs)} requirements has exactly one owner"
             + (f" ({len(prop.get('founder_owned') or [])} of them are yours)." if prop.get("founder_owned") else ".")
             if not unowned else f"No owner yet for: {', '.join(unowned)}.",
             (f"Every one of the {len(risks)} risks has someone watching it." if len(risks) != 1 else
              "The one risk has someone watching it.") if not unwatched
             else f"No one watches: {', '.join(unwatched)}.",
             "Every seat was asked for by someone named, with a reason you can read, and each one owns work, a risk or "
             "a step no other seat covers."]
    if ch.get("removed"):
        lines.append("The independent challenge cut " + ", ".join(f"{r['title']} ({r['why']})" for r in ch["removed"]))
    if ch.get("overruled"):
        lines.append("It also tried to cut " + ", ".join(f"{o['title']}, but kept it because {o['kept_because']}"
                                                          for o in ch["overruled"]))
    if not ch.get("removed") and not ch.get("overruled"):
        lines.append("The independent challenge found no seat to cut.")
    if ch.get("unreadable"):
        lines.append("The challenger's own answer could not be read; the platform's removal test still ran on every seat.")
    if filled or added:
        lines.append("Cynqra had to fill what the proposers left open: "
                     + ", ".join(filled + [f"the {a} seat" for a in added]) + ". Check those seats first.")
    ln = prop.get("lean") or {}
    if ln.get("left_out") or ln.get("fewer"):
        lines.append(f"This is {n_seats} seats. The lean team is {ln['seats']}: "
                     + "; ".join([f"without the {x['title']}, whose work goes to the "
                                  + " and the ".join(sorted({name(k) for k in x['work_goes_to'].values()}))
                                  for x in ln.get("left_out", [])]
                                 + [f"one {x['title']} instead of {x['from']}" for x in ln.get("fewer", [])])
                     + ". You choose.")
    else:
        lines.append(f"This is {n_seats} seats, and no smaller team covers everything.")
    if history:
        lines.append(f"Track record on this computer: {history['projects']} earlier project"
                     f"{'s' if history['projects'] != 1 else ''} covered the same kinds of work, "
                     f"{history['accepted']} delivered and accepted, with {history['mistakes_caught']} mistakes caught "
                     "by the checks before they counted.")
    lines.append("Once the plan exists, every member joins with its first task, and a member with no work in it is removed "
                 "before anything starts; the roadmap tells you.")
    return {"confidence": confidence, "lines": lines, "failure_stories": ch.get("failure_stories") or []}


def work_check(tasks: list[dict], workers: list[dict], milestones: list[dict]) -> dict:
    """Once the roadmap exists: when each member joins (with its first task) and who has no work in it. A cofounder
    whose team has work has work too: it hands that work out and reviews it."""
    order = {m["id"]: i for i, m in enumerate(milestones)}
    ms = {m["id"]: m for m in milestones}
    first: dict[str, dict] = {}
    for t in sorted(tasks, key=lambda t: (order.get(t.get("milestone_id"), 99), t.get("deadline_day") or 0, t["id"])):
        for who in (t["owner_worker_id"], t.get("handoff_from"), t.get("reviewed_by")):
            if who and who.startswith("w_") and who not in first:
                first[who] = t
    joins, idle = {}, []
    for w in workers:
        t = first.get(w["id"])
        if t is None:
            idle.append({"worker": w["id"], "title": w["title"], "role": w["role"]})
            continue
        m = ms.get(t.get("milestone_id")) or {}
        joins[w["id"]] = {"task": t["id"], "milestone": m.get("name", ""), "day": t.get("deadline_day")}
    return {"joins": joins, "idle": idle}
