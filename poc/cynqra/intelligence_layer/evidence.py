"""Intelligence evidence as selection authority: what is known about one intelligence for one piece of work, how
strongly, and from where. Pure functions over plain records, so a decision made from a snapshot of them can be
replayed exactly (cynqra/controller.py).

The hierarchy (policies.EVIDENCE), strongest first:

  1 objective_verified   this objective, this version: independently verified results (the platform's checks, a
                         person, another intelligence)
  2 objective_partial    this objective: weaker results (self-review, protocol-only checks)
  3 historical           other objectives of the same tenant, or an earlier version this one may inherit from
  4 global               qualification and regression work (probe.py): whether it is safe to use at all
  5 capability           what the provider says it can do: a hard constraint when it is known to be unable,
                         never a measure of quality
  6 reputation           name, provider, release date, benchmark: calibration priority only, never quality

Every item weighs level weight x relevance x verification quality x recency x environment x conflict. Levels 2 to 4
are capped, so a long history informs a new objective without outvoting what the objective itself shows, and one
objective result does not outvote a mature history either. Quality is a Beta posterior from a uniform prior: its mean,
an 80% band (lcb, ucb) and the effective sample size, never a raw win rate. An item is excluded, with its reason,
when it belongs to another served version, another objective, an objective version this one may not inherit, another
tenant, when it is contaminated (a failure the intelligence did not cause), archived or invalidated.
"""
from __future__ import annotations

import math

OBJECTIVE_LEVELS = ("objective_verified", "objective_partial")
ORDER = ("objective_verified", "objective_partial", "historical", "global")
BUILD = ("code", "forecast")


def proxy_kind(kind: str) -> str:
    """The evaluation work closest to a kind of work: code for what becomes files, the objective for the rest."""
    return "code" if kind in BUILD else "objective"


def relevance(item_kind: str, item_role: str, kind: str, role: str, rel: dict) -> tuple[float, str]:
    if item_kind == kind:
        if not role or not item_role or item_role == role:
            return rel["same_class"], "same_class"
        return rel["same_kind_other_role"], "same_kind_other_role"
    if item_kind == proxy_kind(kind):
        return rel["proxy_kind"], "proxy_kind"
    return rel["other_kind"], "other_kind"


def normalize(raw: dict, ctx: dict, policy: dict, kind: str) -> dict:
    """One raw evidence record, as it bears on one candidate's work of one kind. Returns the item with its level and
    weights, or with excluded set to the reason it carries no authority here."""
    ev = policy["evidence"]
    out = {"id": raw.get("id"), "src": raw.get("src"), "intelligence_id": raw.get("intelligence_id"),
           "served_version": raw.get("served_version") or "", "kind": raw.get("task_kind"), "excluded": None,
           "level": None, "weight": 0.0, "success": 0.0, "failure": 0.0}
    want = (ctx.get("candidate_versions") or {}).get(raw.get("intelligence_id"))
    if want is not None and (raw.get("served_version") or "") != want:
        out["excluded"] = "version_mismatch"  # another version, or another company serving it
        return out
    if raw.get("status") in ("archived", "invalidated"):
        out["excluded"] = raw["status"]
        return out
    if raw.get("tenant_id", "local") != ctx.get("tenant_id", "local"):
        out["excluded"] = "tenant_isolation"
        return out
    if raw.get("clean") is False:
        out["excluded"] = "contaminated:" + str(raw.get("attribution") or "not the intelligence's fault")
        return out
    if raw.get("autonomy") == "human_override":
        out["excluded"] = "human_override"
        return out
    rel, how = relevance(raw.get("task_kind") or "", raw.get("role") or "", kind, ctx.get("role") or "",
                         ev["relevance"])
    if raw.get("src") == "objective":
        if raw.get("objective_id") != ctx.get("objective_id"):
            out["excluded"] = "other_objective"
            return out
        v, cur = int(raw.get("objective_version") or 0), int(ctx.get("objective_version") or 0)
        if v > cur:
            out["excluded"] = "later_objective_version"
            return out
        mode = "full" if v == cur else ((ctx.get("inheritance") or {}).get(str(v)) or {}).get("mode", "none")
        if mode == "none":
            out["excluded"] = "objective_version_boundary"
            return out
        if mode == "prior_only":
            level = "historical"
            rel *= float(((ctx.get("inheritance") or {}).get(str(v)) or {}).get("relevance") or 0.5)
            out["inherited_from_version"] = v
        else:
            level = "objective_verified" if float(raw.get("vq") or 0) >= 0.7 else "objective_partial"
        if raw.get("work_item_id") and raw.get("work_item_id") == ctx.get("work_item_id") \
                and raw.get("task_kind") == kind:  # the same piece of work, not a colleague's coordination of it
            rel = max(rel, ev["relevance"]["same_work_item"])
        recency = 1.0
    else:  # the registry's record of other work
        if raw.get("run_id") and raw.get("run_id") == ctx.get("run_id"):
            out["excluded"] = "counted_as_objective_evidence"
            return out
        level = "global" if raw.get("source") in ("probe", "regression") else "historical"
        age = max(0.0, float(ctx.get("now") or 0) - float(raw.get("at") or ctx.get("now") or 0)) / 86400
        recency = 0.5 ** (age / ev["historical_half_life_days"]) if level == "historical" else 1.0
    vq = float(raw.get("vq") if raw.get("vq") is not None else 1.0)
    env = ev["environment_change_factor"] if raw.get("env") and ctx.get("env") and raw["env"] != ctx["env"] else 1.0
    conflict = float(policy["calibration"]["author_conflict_factor"]) if raw.get("author_conflict") else 1.0
    deps = float(policy["calibration"]["unmet_dependency_factor"]) if raw.get("dependencies_unmet") else 1.0
    w = ev["weight"][level] * rel * vq * recency * env * conflict * deps
    if raw.get("verified") is None:
        out["excluded"] = "not_verified"
        return out
    if raw.get("verified"):
        s, f = ev["autonomy_success"].get(raw.get("autonomy") or "autonomous", 1.0), 0.0
    else:
        s, f = 0.0, ev["severity_factor"].get(raw.get("severity") or "major", 1.0)
    out.update(level=level, relevance=round(rel, 4), match=how, vq=vq, recency=round(recency, 4), env=env,
               weight=round(w, 6), success=round(w * s, 6), failure=round(w * f, 6),
               verified=bool(raw.get("verified")), autonomy=raw.get("autonomy") or "autonomous")
    return out


def _maturity(n: float, m: dict) -> str:
    if n < m["thin"]:
        return "none"
    if n < m["developing"]:
        return "thin"
    if n < m["mature"]:
        return "developing"
    return "mature"


def assess(raws: list[dict], ctx: dict, policy: dict, kind: str) -> dict:
    """Everything known about one candidate's work of one kind, as authority: quality with its uncertainty, how
    mature and how strong the evidence is, which level decided it, and every record left out with its reason."""
    ev = policy["evidence"]
    items = [normalize(r, ctx, policy, kind) for r in raws]
    used = [i for i in items if not i["excluded"]]
    levels = {}
    for name in ORDER:
        mine = [i for i in used if i["level"] == name]
        s, f = sum(i["success"] for i in mine), sum(i["failure"] for i in mine)
        cap = ev["cap"].get(name)
        scale = 1.0
        if cap is not None and s + f > cap:
            scale = cap / (s + f)
        levels[name] = {"items": len(mine), "verified": sum(1 for i in mine if i["verified"]),
                        "failed": sum(1 for i in mine if not i["verified"]),
                        "success": round(s * scale, 4), "failure": round(f * scale, 4), "capped": scale < 1.0}
    a0, b0 = ev["prior"]
    a = a0 + sum(levels[n]["success"] for n in ORDER)
    b = b0 + sum(levels[n]["failure"] for n in ORDER)
    mean = a / (a + b)
    sd = math.sqrt(mean * (1 - mean) / (a + b + 1))
    z = ev["z"]
    obj_n = sum(levels[n]["success"] + levels[n]["failure"] for n in OBJECTIVE_LEVELS)
    total_n = sum(levels[n]["success"] + levels[n]["failure"] for n in ORDER)
    decisive = next((n for n in ORDER if levels[n]["success"] + levels[n]["failure"] >= 0.5), "prior")
    raw_n = sum(levels[n]["items"] for n in ORDER)
    raw_ok = sum(levels[n]["verified"] for n in ORDER)
    excluded = [{"id": i["id"], "why": i["excluded"]} for i in items if i["excluded"]]
    contaminated = sum(1 for e in excluded if e["why"].startswith("contaminated"))
    mismatched = sum(1 for e in excluded if e["why"] == "version_mismatch")

    def avg(key):
        tw = sum(i["weight"] for i in used)
        return round(sum(i[key] * i["weight"] for i in used) / tw, 4) if tw else None

    strength = {"sample_maturity": round(min(1.0, total_n / ev["maturity"]["mature"]), 4),
                "relevance": avg("relevance"), "verification_quality": avg("vq"), "recency": avg("recency"),
                "causal_cleanliness": round(len(used) / (len(used) + contaminated), 4) if used or contaminated else None,
                "version_integrity": round(len(used) / (len(used) + mismatched), 4) if used or mismatched else None}
    parts = [v for v in strength.values() if v is not None]
    strength["score"] = round(sum(parts) / len(parts), 4) if parts else 0.0
    return {"kind": kind,
            "quality": {"mean": round(mean, 4), "lcb": round(max(0.0, mean - z * sd), 4),
                        "ucb": round(min(1.0, mean + z * sd), 4), "effective_n": round(total_n, 3),
                        "objective_n": round(obj_n, 3), "maturity": _maturity(obj_n, ev["maturity"]),
                        "prior_maturity": _maturity(total_n - obj_n, ev["maturity"]), "decisive_level": decisive},
            "raw": {"records": raw_n, "verified": raw_ok, "success_rate": round(raw_ok / raw_n, 3) if raw_n else None},
            "levels": levels, "strength": strength, "excluded": excluded,
            "used": [{"id": i["id"], "level": i["level"], "weight": i["weight"], "verified": i["verified"]}
                     for i in used]}


def bundle(per_kind: list[dict]) -> dict:
    """A worker's work of several kinds, as one quality: its weakest kind (a seat is as good as what it does worst),
    the evidence counts summed."""
    if len(per_kind) == 1:
        return per_kind[0]["quality"]
    q = [p["quality"] for p in per_kind]
    return {"mean": min(x["mean"] for x in q), "lcb": min(x["lcb"] for x in q), "ucb": min(x["ucb"] for x in q),
            "effective_n": round(sum(x["effective_n"] for x in q), 3),
            "objective_n": round(sum(x["objective_n"] for x in q), 3),
            "maturity": min((x["maturity"] for x in q), key=("none", "thin", "developing", "mature").index),
            "prior_maturity": min((x["prior_maturity"] for x in q), key=("none", "thin", "developing", "mature").index),
            "decisive_level": min((x["decisive_level"] for x in q),
                                  key=lambda d: ORDER.index(d) if d in ORDER else len(ORDER))}


def superior(challenger: dict, incumbent: dict) -> bool:
    """Verified superiority, the bar a challenger must clear to replace a working incumbent: its mean above the
    incumbent's upper bound, or its lower bound above the incumbent's mean. An untested challenger never clears it."""
    if challenger.get("effective_n", 0) <= 0:
        return False
    return challenger["mean"] > incumbent["ucb"] or challenger["lcb"] > incumbent["mean"]
