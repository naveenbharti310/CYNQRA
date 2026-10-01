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
from .workload import compile_contract

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


def fits(m: dict, workload: dict | None = None) -> tuple[bool, str]:
    """Capability and context fit. Unknown capability facts do not invent support, but explicit requirements are hard."""
    if m.get("context") and m["context"] < MIN_CONTEXT:
        return False, f"context {m['context']} tokens, the work needs {MIN_CONTEXT}"
    required = {str(x).strip().lower() for x in ((workload or {}).get("required_capabilities") or []) if str(x).strip()}
    if required and m.get("capabilities"):
        have = {str(x).strip().lower() for x in (m.get("capabilities") or [])}
        aliases = {
            "coding": {"coding", "code", "programming"},
            "reasoning": {"reasoning", "agentic"},
            "tool use": {"tool use", "tools", "function calling"},
            "structured output": {"structured output", "json", "structured_outputs"},
            "multimodal": {"multimodal", "vision"},
        }
        for need in required:
            accepted = aliases.get(need, {need})
            if not have.intersection(accepted):
                return False, f"missing capability: {need}"
    need_ctx = int((workload or {}).get("min_context_tokens") or MIN_CONTEXT)
    if m.get("context") and m["context"] < need_ctx:
        return False, f"context {m['context']} tokens, the workload needs {need_ctx}"
    return True, ""


def rank(reg: Registry, kinds: list[str], time_value_per_hour: float, budget_left: float | None = None,
         exclude: set | None = None, workload: dict | None = None) -> list[dict]:
    """Every available model that fits the WorkloadContract, scored over the worker's kinds of work."""
    rows = []
    for m in reg.available():
        if (exclude and m["id"] in exclude) or not fits(m, workload)[0]:
            continue
        per = [estimate(reg, m, k, time_value_per_hour) for k in kinds]
        samples = sum(int(e.get("samples") or 0) for e in per)
        confidence = round(min(1.0, samples / 10.0), 3)
        row = {"model_id": m["id"], "model": m["name"], "runtime": m["runtime"],
               "score": round(sum(e["score"] for e in per), 4),
               "expected_usd": round(sum(e["expected_usd"] for e in per), 4),
               "expected_minutes": round(sum(e["expected_minutes"] for e in per), 1),
               "p_task": round(min(e["p_task"] for e in per), 3),
               "confidence": confidence, "sample_count": samples, "by_kind": per}
        row["fits_budget"] = budget_left is None or row["expected_usd"] <= budget_left + 1e-9
        rows.append(row)
    rows.sort(key=lambda r: (not r["fits_budget"], r["score"], -r["confidence"]))
    return rows


def choose(reg: Registry, settings: dict, kinds: list[str], budget_left: float | None = None,
           exclude: set | None = None, workload: dict | None = None) -> tuple[dict | None, list[dict]]:
    rows = rank(reg, kinds, settings["time_value_per_hour"], budget_left, exclude, workload)
    return (rows[0] if rows and rows[0]["fits_budget"] else None), rows


def staff(reg: Registry, settings: dict, workers: list[dict], workload=None) -> dict:
    """Choose intelligence for each worker from its actual workload contract and measured evidence."""
    out = {}
    for w in workers:
        requested = (workload or {}).get(w["id"])
        if isinstance(requested, dict):
            kinds = list(requested.get("kinds") or [])
            contract = dict(requested)
        else:
            kinds = list(requested or roles.staffing_kinds(w["role"]))
            contract = {"kinds": kinds}
        if not kinds:
            kinds = roles.staffing_kinds(w["role"])
            contract["kinds"] = kinds
        contracts = [compile_contract({"kind": k}) for k in kinds]
        required = sorted({cap for x in contracts for cap in x["required_capabilities"]})
        contract["required_capabilities"] = required
        contract["min_context_tokens"] = max((x["min_context_tokens"] for x in contracts), default=MIN_CONTEXT)
        contract["risk"] = "HIGH" if any(x["risk"] == "HIGH" for x in contracts) else (
            "MEDIUM" if any(x["risk"] == "MEDIUM" for x in contracts) else "LOW")
        best, rows = choose(reg, settings, kinds, settings["budget_usd"], workload=contract)
        best = best or (rows[0] if rows else None)
        if best is None:
            raise RouterError("no available model can staff the organization: register one in the model registry")
        out[w["id"]] = {"model_id": best["model_id"], "model": best["model"], "candidates": rows,
                        "kinds": kinds, "workload_contract": contract}
    return out
