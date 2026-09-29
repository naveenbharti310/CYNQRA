"""A project's settings: what the founder sets at Stage 0 and the governance the run follows.

budget_usd              the hard cap, in US dollars; the breaker opens when spending reaches it
time_value_per_hour     what an hour of waiting is worth to the founder; the router trades money against time
compute_usd_per_hour    the price of this machine's time, for tools and verification; 0 means not priced
infra_usd_per_day       hosting the deployed product; 0 means it runs on this machine
reserve_min_pct         the smallest contingency the Budget Engine accepts without a warning
allow_workforce_override  governance: may the founder edit a proposed workforce instead of rejecting it
self_checks             how many times an engineer may test and fix its own work before handing it over
cofounders_settle_reversible  governance: a decision that is easy to undo (a merge, a product rule outside money
                        and law) is settled by the cofounder accountable for it, and the founder is told instead of
                        asked; going live, money and legal choices always go to the founder
"""
from __future__ import annotations

DEFAULTS = {"budget_usd": 5.0, "time_value_per_hour": 10.0, "compute_usd_per_hour": 0.0, "infra_usd_per_day": 0.0,
            "reserve_min_pct": 0.15, "allow_workforce_override": False, "self_checks": 2,
            "parallel_workers": 6, "cofounders_settle_reversible": True}
NUMBERS = ("budget_usd", "time_value_per_hour", "compute_usd_per_hour", "infra_usd_per_day", "reserve_min_pct")


class SettingsError(ValueError):
    pass


def get(store) -> dict:
    return {**DEFAULTS, **(store.get("settings", "project") or {})}


def update(store, changes: dict) -> dict:
    s = get(store)
    for k, v in (changes or {}).items():
        if v is None:
            continue
        if k in NUMBERS:
            try:
                v = round(float(v), 4)
            except (TypeError, ValueError) as exc:
                raise SettingsError(f"{k} must be a number") from exc
            if v < 0:
                raise SettingsError(f"{k} cannot be negative")
        elif k in ("allow_workforce_override", "cofounders_settle_reversible"):
            v = bool(v)
        elif k == "self_checks":
            v = max(0, int(v))
        elif k == "parallel_workers":  # how many workers' model calls may be in flight at once
            v = max(1, int(v))
        else:
            raise SettingsError(f"unknown setting {k}")
        s[k] = v
    store.put("settings", "project", s)
    return s
