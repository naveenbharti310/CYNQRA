"""The Intelligence Router: which model powers each worker, and what a task is expected to cost on it.

Product definition, Stage 4 and section 5. The Workforce Synthesizer decides which roles an objective needs; this
module decides which model powers each worker. There is no one-to-one relation between role and model: the same
model can power many workers, and two workers with the same title can run on different models when their
workloads differ (staff() scores each worker over its own work).

Selection. For a kind of work k and an available model m, from the registry's measured outcomes:
  p      chance one attempt passes verification: m's verified/attempts on k, pulled toward m's record on the closest
         measured work (code for building work, the evaluation's planning work for coordination), else on all kinds,
         with the weight of two samples; with no history at all, 1/2 for every model (no model is favoured by name)
  c, t   cost (USD) and seconds of one attempt: m's measured means on k, else on all kinds, else the mean size every
         model has measured on k, priced at m's rate and speed, else S2's estimate of tokens per task
  Within A = 3 attempts:  P = 1 - (1-p)^A;  expected attempts E = P / p
  score  = (E * c  +  value of an hour * E * t) / P
         = expected money and time spent per verified task. The lowest score wins among the models that fit the
           work and the budget left. The whole table is kept with every choice, so any choice can be audited.
"""
from __future__ import annotations

from .. import roles
from .registry import IntelligenceRegistry as Registry

ATTEMPTS = 3  # verification attempts before a task counts as failed (execution.MAX_ATTEMPTS)
PRIOR = 2.0
EST_TOKENS = {"LOW": 12_000, "MEDIUM": 20_000, "HIGH": 20_000}  # S2_ESTIMATE.md, per task, when nothing is measured
EST_WRITE_TPS = 8.0  # tokens/s for a model never measured, only to price its time before its first call
MIN_CONTEXT = 8192  # tokens: the longest prompt a worker is sent fits in this


class RouterError(RuntimeError):
    pass


def _risk(kind: str) -> str:
    return roles.risk(kind) if kind in roles.TASK_TYPES else "LOW"  # assign, objective, plan: coordination work


def proxy_kind(kind: str) -> str:
    """The evaluation work closest to a kind of work: code for what becomes files, the objective for the rest."""
    return "code" if kind in roles.BUILD_TYPES else "objective"


def tokens_guess(reg: Registry, kind: str) -> float:
    others = reg.outcomes(task_kind=kind)
    return (sum(o["tokens"] for o in others) / len(others)) if others else EST_TOKENS[_risk(kind)]


def estimate(reg: Registry, m: dict, kind: str, time_value_per_hour: float) -> dict:
    """What one model is expected to cost, take and achieve on one kind of work, and on what evidence."""
    st_k, st_all = reg.stats(m["id"], kind), reg.stats(m["id"])
    # With no record on this kind, the closest measured work speaks first: writing code for building work, and
    # structuring a founder's words into a plan (the evaluation's objective) for a cofounder's planning, assigning
    # and reviewing. So a cofounder's seat goes to the model that plans best, an engineer's to the one that codes.
    near = st_k if st_k["attempts"] else reg.stats(m["id"], proxy_kind(kind))
    base = near if near["attempts"] else st_all
    p_model = (base["verified"] + 1) / (base["attempts"] + 2)
    p = (st_k["verified"] + PRIOR * p_model) / (st_k["attempts"] + PRIOR)
    tokens = st_k["tokens_per_attempt"] or st_all["tokens_per_attempt"] or tokens_guess(reg, kind)
    if st_k["attempts"]:
        c, t, basis = st_k["usd_per_attempt"], st_k["seconds_per_attempt"], f"{st_k['attempts']} measured attempts"
    elif st_all["attempts"]:
        c, t, basis = st_all["usd_per_attempt"], st_all["seconds_per_attempt"], "its measured attempts on other work"
    else:
        tps = st_all["write_tps"] or EST_WRITE_TPS
        t = tokens * 0.35 / tps  # about a third of a task's tokens are written; reading is several times faster
        c = reg.cost(m, int(tokens * 0.65), int(tokens * 0.35), t)
        basis = ("no history: others' measured size on this work" if reg.outcomes(task_kind=kind)
                 else "no history: S2's estimate") + (", its measured speed" if st_all["write_tps"] else "")
    P = 1 - (1 - p) ** ATTEMPTS
    E = P / p
    score = (E * c + time_value_per_hour / 3600 * E * t) / P
    return {"model_id": m["id"], "model": m["name"], "kind": kind, "p_attempt": round(p, 3), "p_task": round(P, 3),
            "usd_per_attempt": round(c, 4), "seconds_per_attempt": round(t, 1), "expected_attempts": round(E, 2),
            "expected_usd": round(E * c, 4), "expected_minutes": round(E * t / 60, 1),
            "expected_tokens": int(E * tokens), "score": round(score, 4), "basis": basis, "samples": st_k["attempts"]}


def fits(m: dict) -> tuple[bool, str]:
    """Capability fit from the model's facts: a known context window too small for the work is excluded. An unknown
    fact excludes nothing; what a model can do is otherwise learned from outcomes, not assumed."""
    if m.get("context") and m["context"] < MIN_CONTEXT:
        return False, f"context {m['context']} tokens, the work needs {MIN_CONTEXT}"
    return True, ""


def rank(reg: Registry, kinds: list[str], time_value_per_hour: float, budget_left: float | None = None,
         exclude: set | None = None) -> list[dict]:
    """Every available model that fits the work, scored over a list of kinds (a worker's work), best first."""
    rows = []
    for m in reg.available():
        if (exclude and m["id"] in exclude) or not fits(m)[0]:
            continue
        if not all(reg.qualified_for(m, k)[0] for k in kinds):  # it failed the qualification of this family of work
            continue
        per = [estimate(reg, m, k, time_value_per_hour) for k in kinds]
        row = {"model_id": m["id"], "model": m["name"], "runtime": m["runtime"],
               "score": round(sum(e["score"] for e in per), 4),
               "expected_usd": round(sum(e["expected_usd"] for e in per), 4),
               "expected_minutes": round(sum(e["expected_minutes"] for e in per), 1),
               "p_task": round(min(e["p_task"] for e in per), 3), "by_kind": per}
        row["fits_budget"] = budget_left is None or row["expected_usd"] <= budget_left + 1e-9
        rows.append(row)
    rows.sort(key=lambda r: (not r["fits_budget"], r["score"]))
    return rows


def choose(reg: Registry, settings: dict, kinds: list[str], budget_left: float | None = None,
           exclude: set | None = None) -> tuple[dict | None, list[dict]]:
    rows = rank(reg, kinds, settings["time_value_per_hour"], budget_left, exclude)
    return (rows[0] if rows and rows[0]["fits_budget"] else None), rows


def staff(reg: Registry, settings: dict, workers: list[dict], workload: dict[str, list[str]] | None = None) -> dict:
    """A model for every worker: the lowest expected cost per verified task over its work (its role's kinds of work
    before there is a roadmap, the kinds of the tasks it owns once there is one). When no model fits the budget the
    best one is still chosen; the roadmap gate shows the overrun and the founder decides."""
    out = {}
    for w in workers:
        kinds = (workload or {}).get(w["id"]) or roles.staffing_kinds(w["role"])
        best, rows = choose(reg, settings, kinds, settings["budget_usd"])
        best = best or (rows[0] if rows else None)
        if best is None:
            raise RouterError("no available model can staff the organization: register one in the model registry")
        out[w["id"]] = {"model_id": best["model_id"], "model": best["model"], "candidates": rows, "kinds": kinds}
    return out


# --- objective-aware selection (mandate 12, 44, 45, 61) ----------------------------------------------------------
# A pure function of a decision snapshot (cynqra/controller.py builds and persists it), so any historical selection
# can be replayed from its own inputs:
#   1 eligible intelligence: the candidate set
#   2-4 hard constraints, each a fact: qualified (for this family of work), available, context, output limit,
#       modality, protocol fit, the founder's constraints. A violation makes a candidate infeasible whatever else it
#       is good at; constraints are never traded against evidence
#   5-6 evidence: the global prior and this objective's evidence, per kind of work (evidence.py)
#   8 selection by the risk tier's policy: quality first, or the lowest expected cost of a verified result among
#       candidates whose evidenced quality clears the tier's floor. No score is universal: the same candidates are
#       ordered differently for different work, objectives and tiers
#   then exploitation or bounded exploration, and an incumbent kept unless a challenger is verifiably superior
from . import evidence as _evidence  # noqa: E402

TIERS = ("LOW", "MEDIUM", "HIGH")


def hard_constraints(c: dict, work: dict, snap: dict) -> list[dict]:
    """Every hard constraint this candidate violates for this work, each with its reason. An unknown fact excludes
    nothing; a known incompatibility excludes."""
    out = []

    def no(name, why):
        out.append({"constraint": name, "why": why})
    q = c.get("qualification") or {}
    if q.get("status") not in ("passed", "not applicable"):
        no("qualified", f"not qualified ({q.get('status') or 'unverified'}): unverified means unknown, not usable")
    else:
        for k in work["kinds"]:
            fam = "code" if k in roles.BUILD_TYPES else "objective"
            if (q.get("by_kind") or {}).get(fam) == "failed":
                no("qualified", f"failed its {fam} qualification, which {k} work needs")
    if not c.get("available", False):
        no("available", c.get("availability") or "unavailable")
    if c.get("context") and int(c["context"]) < int(work.get("min_context") or 0):
        no("context", f"context {c['context']} tokens, the work needs {work['min_context']}")
    if c.get("max_output") and int(c["max_output"]) < int(work.get("output_tokens") or 0):
        no("output_limit", f"writes at most {c['max_output']} tokens, the work needs {work['output_tokens']}")
    mods = c.get("input_modalities") or []
    if mods and "text" not in [str(x).lower() for x in mods]:
        no("modality", "does not read text")
    for need in work.get("requires") or []:  # what the work item needs, cognitive or runtime/protocol
        if capability(c, need) is False:
            no("capability", f"the work needs {need}; its provider states it cannot")
    if work.get("local_only") and not c.get("local"):
        no("founder_constraints", "the founder's constraints keep the work on this computer")
    if c["id"] in (snap.get("exclude") or []):
        no("excluded", "excluded for this decision: " + str((snap.get("exclude_why") or {}).get(c["id"]) or
                                                            "the intelligence being replaced"))
    bad = [r for r in snap.get("evidence") or [] if r.get("intelligence_id") == c["id"] and r.get("protocol")
           and r.get("src") == "objective" and r.get("clean") is not False
           and r.get("objective_version") == snap["context"].get("objective_version")
           and r.get("served_version") == c.get("served_version") and r.get("task_kind") in work["kinds"]]
    if len(bad) >= 3:
        no("protocol", f"{len(bad)} protocol violations on this work in this objective: incompatible protocol behavior")
    return out


_MODALITY = {"vision": "image", "audio": "audio", "video": "video"}
_STATED = {"tool_calling": {"tool use", "tools", "function calling"},
           "structured_output": {"structured output", "json mode", "json schema"},
           "reasoning": {"reasoning"}, "coding": {"coding"}, "long_context": {"long context"},
           "parallel_tool_calls": {"parallel tool calls", "parallel tools"}}


def capability(c: dict, need: str) -> bool | None:
    """Whether a candidate has a capability the work needs: True when its provider states it, False only when its
    stated facts rule it out (its listed input types leave out images, say), None when nothing says (unknown is not
    unable, and a capability a provider claims is never evidence of quality)."""
    if need in _MODALITY:
        mods = [str(x).lower() for x in c.get("input_modalities") or []]
        return (_MODALITY[need] in mods) if mods else None
    caps = {str(x).lower() for x in c.get("capabilities") or []}
    return True if caps & _STATED.get(need, {need.replace("_", " ")}) else None


def _economics(c: dict, per_kind: list[dict], sel: dict, budget: dict, tv: float) -> dict:
    """Expected money and time of a verified result on each kind, at the evidenced chance of success: cost and
    latency as dimensions of their own, never folded into a quality number."""
    A = int(sel.get("attempts") or ATTEMPTS)
    usd = minutes = value = 0.0
    out_kinds = []
    for a in per_kind:
        k = a["kind"]
        meas = (c.get("measured") or {}).get(k) or {}
        cost, secs = float(meas.get("usd_per_attempt") or 0.0), float(meas.get("seconds_per_attempt") or 0.0)
        p = max(1e-3, float(a["quality"]["mean"]))
        P = 1 - (1 - p) ** A
        E = P / p
        usd += E * cost
        minutes += E * secs / 60
        value += (E * cost + tv / 3600 * E * secs) / P
        out_kinds.append({"kind": k, "usd_per_attempt": round(cost, 6), "seconds_per_attempt": round(secs, 1),
                          "p_attempt": round(p, 4), "p_task": round(P, 4), "expected_attempts": round(E, 3),
                          "basis": meas.get("basis")})
    head = float(budget.get("headroom") if budget.get("headroom") is not None else 1e18)
    return {"expected_usd": round(usd, 6), "expected_minutes": round(minutes, 2),
            "expected_value_cost": round(value, 6), "fits_budget": usd <= head + 1e-9, "by_kind": out_kinds}


def select(snap: dict) -> dict:
    """The selection a snapshot implies. Deterministic: the same snapshot always gives the same result."""
    pol = {k: v["body"] for k, v in snap["policies"].items()}
    sel, work, ctx = pol["selection"], snap["work"], dict(snap["context"])
    ctx.update(role=work.get("role"), work_item_id=work.get("work_item_id"), now=snap["now"],
               requirement_ids=work.get("requirement_ids") or [], criterion_ids=work.get("criterion_ids") or [])
    ctx["candidate_versions"] = {c["id"]: c.get("served_version") or "" for c in snap["candidates"]}
    by: dict[str, list] = {}
    for r in snap.get("evidence") or []:
        by.setdefault(r.get("intelligence_id"), []).append(r)
    tv = float((snap.get("budget") or {}).get("time_value_per_hour") or 0.0)
    rows = []
    for c in snap["candidates"]:
        per_kind = [_evidence.assess(by.get(c["id"], []), ctx, pol, k) for k in work["kinds"]]
        q = _evidence.bundle(per_kind)
        econ = _economics(c, per_kind, sel, snap.get("budget") or {}, tv)
        rows.append({"id": c["id"], "name": c.get("name"), "served_version": c.get("served_version") or "",
                     "violations": hard_constraints(c, work, snap), "quality": q, "economics": econ,
                     "per_kind": [{"kind": a["kind"], "quality": a["quality"], "raw": a["raw"], "levels": a["levels"],
                                   "strength": a["strength"], "excluded": a["excluded"], "used": a["used"]}
                                  for a in per_kind]})
    feasible = [r for r in rows if not r["violations"]]
    tier = work.get("risk_tier") if work.get("risk_tier") in TIERS else "LOW"
    tp = sel["tiers"][tier]
    kq = lambda r: (not r["economics"]["fits_budget"], -r["quality"]["lcb"], -r["quality"]["mean"],  # noqa: E731
                    r["economics"]["expected_value_cost"], r["id"])
    ke = lambda r: (not r["economics"]["fits_budget"], r["economics"]["expected_value_cost"],  # noqa: E731
                    -r["quality"]["lcb"], r["id"])
    clears = [r for r in feasible if r["quality"][tp["floor"]] >= tp["quality_floor"]]
    if tp["tradeoff"] == "quality_first" or not clears:
        ordered = sorted(feasible, key=kq)
        basis = "quality first" if tp["tradeoff"] == "quality_first" else \
            f"no candidate clears the {tier} quality floor ({tp['floor']} {tp['quality_floor']}): quality first"
    else:
        rest = [r for r in feasible if r not in clears]
        ordered = sorted(clears, key=ke) + sorted(rest, key=kq)
        basis = (f"{tp['tradeoff']}: the lowest expected cost of a verified result among candidates whose "
                 f"{tp['floor']} quality clears {tp['quality_floor']}")
    out = {"tier": tier, "tradeoff": tp["tradeoff"], "basis": basis, "ranking": [r["id"] for r in ordered],
           "eligible": [r["id"] for r in feasible],
           "excluded": [{"id": r["id"], "violations": r["violations"]} for r in rows if r["violations"]],
           "rows": rows, "selected": None, "mode": "no_feasible_candidate", "challenger": None}
    if not ordered:
        out["reason"] = "no candidate satisfies every hard constraint: " + "; ".join(
            f"{r['id']}: {r['violations'][0]['why']}" for r in rows) if rows else "no candidate intelligence"
        return out
    top = ordered[0]
    mode = "single_candidate" if len(ordered) == 1 else "exploit"
    chosen = top
    inc = snap.get("incumbent") or {}
    inc_row = next((r for r in feasible if r["id"] == inc.get("intelligence_id")
                    and r["served_version"] == (inc.get("served_version") or r["served_version"])), None)
    if inc_row is not None and inc_row is not top:
        if _evidence.superior(top["quality"], inc_row["quality"]):
            mode = "reselect"
        else:  # stability: a challenger must demonstrate verified superiority before it replaces the incumbent
            chosen, mode = inc_row, "keep_incumbent"
    elif inc_row is not None:
        mode = "keep_incumbent"
    ex = sel["exploration"]
    explore = snap.get("exploration") or {}
    if (tp["explore"] and work.get("scope") == "task" and mode in ("exploit", "keep_incumbent") and len(ordered) > 1
            and _rank(chosen["quality"]["maturity"]) >= _rank(ex["incumbent_maturity"])
            and int(explore.get("used") or 0) < int(ex["max_per_objective"])):
        room = float(ex["budget_fraction"]) * float((snap.get("budget") or {}).get("cap") or 0) \
            - float(explore.get("spent_usd") or 0)
        challengers = [r for r in ordered if r is not chosen and r["quality"]["maturity"] in ex["challenger_maturity"]
                       and r["quality"]["ucb"] > chosen["quality"]["mean"] and r["economics"]["fits_budget"]
                       and r["economics"]["expected_usd"] <= room + 1e-12]
        if challengers:
            pick = sorted(challengers, key=lambda r: (-r["quality"]["ucb"], r["economics"]["expected_value_cost"],
                                                      r["id"]))[0]
            out["challenger"] = {"id": pick["id"], "against": chosen["id"],
                                 "why": f"its upper bound {pick['quality']['ucb']} beats the incumbent's mean "
                                        f"{chosen['quality']['mean']} on {pick['quality']['maturity']} evidence"}
            chosen, mode = pick, "explore"
    q, e = chosen["quality"], chosen["economics"]
    out.update(selected=chosen["id"], mode=mode, reason=(
        f"{chosen.get('name') or chosen['id']} ({mode}) for {work.get('work_item_id')}: {basis}. Evidenced quality "
        f"{q['mean']} (80% band {q['lcb']} to {q['ucb']}), decided by {q['decisive_level']} evidence, "
        f"{q['objective_n']} weighted samples on this objective ({q['maturity']}); expected ${e['expected_usd']} and "
        f"{e['expected_minutes']} min per verified result. {len(feasible) - 1} feasible alternative(s) considered, "
        f"{len(rows) - len(feasible)} excluded by hard constraints."))
    return out


def _rank(maturity: str) -> int:
    return ("none", "thin", "developing", "mature").index(maturity) if maturity in ("none", "thin", "developing",
                                                                                     "mature") else 0
