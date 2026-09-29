"""The business numbers, checked like code (Stage 9, for the financial model).

A financial model a non-expert cannot check is worse than none: a wrong margin or payback reads exactly like a right
one. So the CFO's model carries its numbers in a block the platform can read, and the platform recomputes every
figure that follows from them:

  ```json
  {"currency": "INR",
   "inputs": {"price_per_month": {"value": 1999, "basis": "assumption"}, ...},
   "claims": {"margin_per_customer": 1749, "payback_months": 3.4, ...}}
  ```

Every input says where it comes from: "assumption", "measured", or "source: <where>". Every claim the model makes
is recomputed from the inputs with the formulas below; a claim more than 2% off fails the check, with the right
figure named. What the platform computes is also shown to the founder in the Company Pack, whether or not the model
claimed it: the unit economics, and whether the company reaches profit before its money runs out.
"""
from __future__ import annotations

import json
import re

INPUTS = {
    "price_per_month": "what one customer pays a month",
    "cost_to_serve_per_month": "what serving one customer costs a month",
    "fixed_costs_per_month": "team and running costs a month",
    "cost_to_win": "what winning one customer costs",
    "monthly_churn": "the share of customers who leave each month (0.04 is 4%)",
    "funding": "the money the company raises or has",
    "customers_per_month": "new customers won each month",
    "months_before_revenue": "months of running costs before the first customer pays (a pilot, a build)",
}
REQUIRED = ("price_per_month", "cost_to_serve_per_month", "fixed_costs_per_month", "cost_to_win", "monthly_churn")
TOLERANCE = 0.02
BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)


class NumbersError(ValueError):
    pass


def read(text: str) -> dict:
    """The numbers block of a financial model."""
    for m in BLOCK.finditer(text or ""):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError as exc:
            raise NumbersError(f"the numbers block is not valid JSON: {exc.msg}") from exc
        if isinstance(data, dict) and isinstance(data.get("inputs"), dict):
            return data
    raise NumbersError("the financial model has no numbers block (a ```json block with inputs and claims) for the "
                       "platform to recompute")


def _value(inputs: dict, name: str):
    v = inputs.get(name)
    v = v.get("value") if isinstance(v, dict) else v
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compute(inputs: dict) -> dict:
    """Every figure that follows from the inputs. Months are simple: no discounting, churn and growth constant."""
    p, c, f, w, ch = (_value(inputs, k) for k in REQUIRED)
    margin = p - c
    out = {"margin_per_customer": round(margin, 2), "margin_share": round(margin / p, 4) if p else None,
           "payback_months": round(w / margin, 2) if margin > 0 else None,
           "lifetime_value": round(margin / ch, 2) if ch and margin > 0 else None,
           "customers_to_cover_fixed_costs": round(f / margin, 1) if margin > 0 else None}
    if out["lifetime_value"] and w:
        out["value_to_cost_of_winning"] = round(out["lifetime_value"] / w, 2)
    n, fund = _value(inputs, "customers_per_month"), _value(inputs, "funding")
    before = int(_value(inputs, "months_before_revenue") or 0)
    if n and margin > 0:
        customers, cash, month = 0.0, -before * f, None
        low = cash
        for m in range(1, 121):  # ten years at most
            customers = customers * (1 - (ch or 0)) + n
            flow = customers * margin - f - n * w
            cash += flow
            low = min(low, cash)
            if month is None and flow >= 0:
                month = before + m
        out.update({"break_even_month": month, "funding_needed": round(-low, 2)})
        if fund is not None:
            out["reaches_profit_before_money_runs_out"] = month is not None and fund >= -low
    return out


def check(text: str) -> dict:
    """Read the block, check every input's basis, recompute, and compare with every claim."""
    findings = []
    try:
        data = read(text)
    except NumbersError as exc:
        return {"passed": False, "findings": [{"rule": "numbers_block", "why": str(exc)}], "computed": {}}
    inputs = data["inputs"]
    missing = [k for k in REQUIRED if _value(inputs, k) is None]
    if missing:
        findings.append({"rule": "numbers_inputs", "why": "inputs missing or not numbers: " + ", ".join(missing)})
        return {"passed": False, "findings": findings, "computed": {}}
    for k, v in inputs.items():
        basis = str(v.get("basis") or "").strip().lower() if isinstance(v, dict) else ""
        if not (basis in ("assumption", "measured") or basis.startswith("source:")):
            findings.append({"rule": "numbers_basis",
                             "why": f"{k}: say whether it is an assumption, measured, or 'source: <where>'"})
    computed = compute(inputs)
    for k, claimed in (data.get("claims") or {}).items():
        right = computed.get(k)
        if right is None or isinstance(right, bool):
            if isinstance(right, bool) and bool(claimed) != right:
                findings.append({"rule": "numbers_recomputed", "why": f"{k}: the inputs say {right}, not {claimed}"})
            continue
        try:
            c = float(claimed)
        except (TypeError, ValueError):
            findings.append({"rule": "numbers_recomputed", "why": f"{k}: {claimed!r} is not a number"})
            continue
        if abs(c - right) > max(abs(right) * TOLERANCE, 0.01):
            findings.append({"rule": "numbers_recomputed",
                             "why": f"{k}: the model says {c:g}, the inputs give {right:g}"})
    return {"passed": not findings, "findings": findings, "computed": computed,
            "currency": str(data.get("currency") or ""),
            "inputs": {k: {"value": _value(inputs, k), "basis": (v.get("basis") if isinstance(v, dict) else "")}
                       for k, v in inputs.items()}}
