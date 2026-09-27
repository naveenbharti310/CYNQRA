"""The Intelligence Router: which model powers each worker, and what each task is expected to cost on it.

Product definition, section 5: the Workforce Synthesizer decides which roles an objective needs (synthesis.py);
this module decides which model or runtime powers each worker. The two are separate on purpose. There is no
one-to-one relation between role and model: the same model can power many workers, and two workers with the same
title can run on different models when their workloads differ (staff() scores each worker over its own work).

A worker is a role with an identity, authority, tools and a budget; its model is an assignment that can change.
Replacing a worker's model changes nothing else: the task system, the organization and the policy gateway see
the same worker.

Selection. For a task kind k and an available model m, from the registry's measured outcomes:
  p      chance one attempt passes verification: m's verified/attempts on k, shrunk toward m's record on all kinds
         when k has few samples; with no history at all, 1/2 for every model (no model is favoured by name)
  c, t   cost (USD) and seconds of one attempt: m's measured means on k, else on all kinds, else the mean of
         every model on k, else S2's estimate of tokens per task priced at m's rate and speed
  Within A = 3 attempts:  P = 1 - (1-p)^A;  expected attempts E = (1 - (1-p)^A) / p
  score  = (E * c  +  time_value * E * t) / P
         = expected money and time spent per verified task. The lowest score wins, among models whose expected
           cost fits the budget left. The whole table is recorded with each choice, so a choice can be audited.

Budget. The founder sets a USD budget. After the plan is approved each task gets E * c of its owner's model; the
rest is a reserve for retries and replacements. Every call is charged to its worker and task. A replacement
releases what the failing model left of its task's allocation and draws the new model's E * c from the reserve;
if that does not fit, the founder decides.
"""
from __future__ import annotations

from . import roles
from .registry import Registry

ATTEMPTS = 3  # the engine's verification attempts before a task counts as failed (engine.MAX_ATTEMPTS)
PRIOR = 2.0  # pseudo-samples: how strongly a kind's few outcomes are pulled toward the model's overall record
EST_TOKENS = {"LOW": 12_000, "MEDIUM": 20_000, "HIGH": 20_000}  # S2_ESTIMATE.md, per task, when nothing is measured
MIN_CONTEXT = 8192  # tokens: the longest prompt a worker is sent (contract, objective, files handed over) fits in this
EST_WRITE_TPS = 8.0  # tokens/s for a model never measured on this machine, only to price its time before its first call
ROLE_KINDS = {name: roles.staffing_kinds(name) for name in roles.ROLES}
KIND_RISK = {"plan": "LOW", "spec": "LOW", "decision": "MEDIUM", "assign": "LOW", "code": "LOW",
             "review_merge": "MEDIUM", "deploy": "HIGH", "objective": "LOW"}
MAX_REPLACEMENTS = 2  # per task, before the founder decides


def estimate(reg: Registry, m: dict, kind: str, time_value_per_hour: float) -> dict:
    """What one model is expected to cost, take and achieve on one kind of task, and on what evidence."""
    st_k, st_all = reg.stats(m["id"], kind), reg.stats(m["id"])
    p_model = (st_all["verified"] + 1) / (st_all["attempts"] + 2)
    p = (st_k["verified"] + PRIOR * p_model) / (st_k["attempts"] + PRIOR)
    others = [o for o in reg.outcomes(task_kind=kind)]
    if st_k["attempts"]:
        c, t, basis = st_k["usd_per_attempt"], st_k["seconds_per_attempt"], f"{st_k['attempts']} measured attempts"
    elif st_all["attempts"]:
        c, t, basis = st_all["usd_per_attempt"], st_all["seconds_per_attempt"], "its measured attempts on other kinds"
    else:
        tokens = (sum(o["tokens"] for o in others) / len(others)) if others else EST_TOKENS[KIND_RISK.get(kind, "LOW")]
        tps = st_all["write_tps"] or EST_WRITE_TPS
        t = tokens * 0.35 / tps  # about a third of a task's tokens are written; reading is several times faster
        c = reg.cost(m, int(tokens * 0.65), int(tokens * 0.35), t)
        basis = ("no history: others' measured size on this kind" if others else "no history: S2's estimate") + \
                (", its measured speed" if st_all["write_tps"] else "")
    q = 1 - p
    P = 1 - q ** ATTEMPTS
    E = P / p
    exp_cost, exp_time = E * c, E * t
    score = (exp_cost + time_value_per_hour / 3600 * exp_time) / P
    return {"model_id": m["id"], "model": m["name"], "kind": kind, "p_attempt": round(p, 3), "p_task": round(P, 3),
            "usd_per_attempt": round(c, 4), "seconds_per_attempt": round(t, 1), "expected_attempts": round(E, 2),
            "expected_usd": round(exp_cost, 4), "expected_minutes": round(exp_time / 60, 1),
            "expected_tokens": int(E * (st_k["tokens_per_attempt"] or st_all["tokens_per_attempt"] or tokens_guess(reg, kind))),
            "score": round(score, 4), "basis": basis, "samples": st_k["attempts"]}


def tokens_guess(reg: Registry, kind: str) -> float:
    others = reg.outcomes(task_kind=kind)
    return (sum(o["tokens"] for o in others) / len(others)) if others else EST_TOKENS[KIND_RISK.get(kind, "LOW")]


def fits(m: dict, role_name: str | None) -> tuple[bool, str]:
    """Capability fit from the model's facts: a known context window too small for the role's work is excluded.
    An unknown fact excludes nothing; what a model can do is otherwise learned from outcomes, not assumed."""
    need = MIN_CONTEXT
    if m.get("context") and m["context"] < need:
        return False, f"context {m['context']} tokens, the work needs {need}"
    return True, ""


def rank(reg: Registry, kinds: list[str], time_value_per_hour: float, budget_left: float | None = None,
         exclude: set | None = None, role_name: str | None = None) -> list[dict]:
    """Every available model that fits the work, scored over a list of task kinds (a worker's work), best first."""
    rows = []
    for m in reg.available():
        if exclude and m["id"] in exclude:
            continue
        if not fits(m, role_name)[0]:
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


class Workforce:
    """One run's staffing and money, kept in the run's store; the learning lives in the registry."""

    def __init__(self, registry: Registry):
        self.reg = registry

    # --- settings -------------------------------------------------------------------------------------
    DEFAULTS = {"budget_usd": 5.0, "time_value_per_hour": 10.0,
                "compute_usd_per_hour": 0.0,    # this machine's time, for tools and verification; 0: not priced
                "infra_usd_per_day": 0.0,       # hosting of the deployed product; 0: it runs on this machine
                "reserve_min_pct": 0.15,        # the smallest contingency the Budget Engine accepts without a warning
                "allow_workforce_override": False}  # governance: may the founder edit a proposed workforce?

    @staticmethod
    def settings(store) -> dict:
        return {**Workforce.DEFAULTS, **(store.get("workforce", "settings") or {})}

    @staticmethod
    def ledger(store) -> dict:
        return store.get("workforce", "ledger") or {"allocated": {}, "spent": {}, "by_worker": {}, "reserve": 0.0,
                                                    "spent_total": 0.0, "events": []}

    def usable(self) -> bool:
        return bool(self.reg.available())

    # --- staffing -------------------------------------------------------------------------------------
    def choose(self, store, kinds: list[str], budget_left: float | None = None,
               exclude: set | None = None, role_name: str | None = None) -> tuple[dict | None, list[dict]]:
        rows = rank(self.reg, kinds, self.settings(store)["time_value_per_hour"], budget_left, exclude, role_name)
        return (rows[0] if rows and rows[0]["fits_budget"] else None), rows

    def staff(self, store, workers: list[dict], workload: dict[str, list[str]] | None = None) -> dict[str, dict]:
        """Give each worker the model with the lowest expected cost per verified task over its work: its role's kinds
        of work before there is a roadmap, the kinds of the tasks it owns once there is one."""
        out = {}
        for w in workers:
            kinds = (workload or {}).get(w["id"]) or ROLE_KINDS.get(w["role"], ["code"])
            best, rows = self.choose(store, kinds, self.settings(store)["budget_usd"], role_name=w["role"])
            if best is None and rows:  # nothing fits the budget: the best one anyway; the roadmap gate shows the overrun
                best = rows[0]
            if best is None:
                raise RuntimeError("no available model can staff the organization: register one in the model registry")
            out[w["id"]] = {"model_id": best["model_id"], "model": best["model"], "candidates": rows, "kinds": kinds}
        return out

    # --- budget ---------------------------------------------------------------------------------------
    def allocate(self, store, tasks: list[dict], model_of: dict[str, str]) -> dict:
        """After the plan: each task gets its expected cost on its owner's model; the rest is the reserve."""
        s, L = self.settings(store), self.ledger(store)
        for t in tasks:
            m = self.reg.get(model_of[t["owner_worker_id"]])
            e = estimate(self.reg, m, t["kind"], s["time_value_per_hour"])
            L["allocated"][t["id"]] = e["expected_usd"]
            w = L["by_worker"].setdefault(t["owner_worker_id"], {"allocated": 0.0, "spent": 0.0})
            w["allocated"] = round(w["allocated"] + e["expected_usd"], 4)
        L["reserve"] = round(s["budget_usd"] - sum(L["allocated"].values()) - L["spent_total"], 4)
        L["events"].append({"what": "allocated", "tasks": len(tasks), "reserve": L["reserve"]})
        store.put("workforce", "ledger", L)
        return L

    def charge(self, store, worker_id: str, task_id: str, usd: float) -> dict:
        if usd <= 0:
            return self.ledger(store)
        L = self.ledger(store)
        L["spent"][task_id] = round(L["spent"].get(task_id, 0.0) + usd, 6)
        w = L["by_worker"].setdefault(worker_id, {"allocated": 0.0, "spent": 0.0})
        w["spent"] = round(w["spent"] + usd, 6)
        L["spent_total"] = round(L["spent_total"] + usd, 6)
        over = L["spent"][task_id] - L["allocated"].get(task_id, 0.0)
        if over > 0 and task_id in L["allocated"]:  # a task past its allocation draws on the reserve
            draw = min(over, usd)
            L["reserve"] = round(L["reserve"] - draw, 6)
        store.put("workforce", "ledger", L)
        return L

    def reallocate(self, store, task: dict, old_worker_model: str, new_estimate: dict) -> dict:
        """A replacement: the failing model's unspent allocation goes back to the reserve, the new model's
        expected cost for the task comes out of it."""
        L = self.ledger(store)
        tid = task["id"]
        left = max(0.0, L["allocated"].get(tid, 0.0) - L["spent"].get(tid, 0.0))
        L["reserve"] = round(L["reserve"] + left, 6)
        new = new_estimate["expected_usd"]
        L["allocated"][tid] = round(L["spent"].get(tid, 0.0) + new, 6)
        L["reserve"] = round(L["reserve"] - new, 6)
        L["events"].append({"what": "reallocated", "task": tid, "released": round(left, 4), "drawn": new,
                            "from": old_worker_model, "to": new_estimate["model_id"], "reserve": L["reserve"]})
        store.put("workforce", "ledger", L)
        return L
