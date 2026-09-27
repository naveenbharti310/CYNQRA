"""The Workforce Synthesizer: which roles, in what quantity, the objective needs.

Product definition, Stages 2 and 3. The human specifies the outcome, not the team. The synthesizer turns the
objective package (requirements, workstreams) into a proposed organization chosen from the role catalog, with the
reason for every role and the requirements it covers (intelligence.synthesize, checked by validate_workforce).
The human then approves the proposed organization; they do not construct it:

  approve   the organization is created as proposed
  reject    the synthesizer revises the proposal against the founder's feedback
  edit      only when the governance policy allows a human override (Workforce settings,
            allow_workforce_override); the edit is checked like any proposal and recorded as an override

Every approval, rejection and override is a labelled decision in the audit trail.
"""
from __future__ import annotations

from . import roles
from .intelligence import IntelligenceError, validate_workforce


class OverrideRefused(PermissionError):
    pass


def evidence(proposal: dict, requirements: dict, cost_by_role: dict | None = None) -> list[str]:
    reqs = {r["id"]: r for r in requirements["requirements"]}
    lines = []
    for r in proposal["roles"]:
        title = roles.role(r["role"])["title"]
        cost = (cost_by_role or {}).get(r["role"])
        lines.append(f"{title} x{r['quantity']}: {r['why']} Covers {', '.join(r['requirement_ids']) or 'no listed requirement'}."
                     + (f" Expected ${cost:.4f} on the best available model." if cost is not None else ""))
    uncovered = [rid for rid, who in proposal["coverage"].items() if not who]
    lines.append(f"{len(reqs)} requirements, {len(reqs) - len(uncovered)} covered.")
    return lines


def cost_by_role(wf, store, proposal: dict) -> dict | None:
    """What each proposed role is expected to cost per unit of its work on the best model now available: an early
    signal for the founder at the workforce gate. The Budget Engine builds the real budget from the roadmap."""
    if wf is None:
        return None
    out = {}
    for r in proposal["roles"]:
        best, _ = wf.choose(store, roles.staffing_kinds(r["role"]), role_name=r["role"])
        if best is not None:
            out[r["role"]] = round(best["expected_usd"] * r["quantity"], 4)
    return out


def override(proposal: dict, edited_roles, requirements: dict, allowed: bool) -> dict:
    """A founder's edit of the proposed workforce, when governance allows it."""
    if not allowed:
        raise OverrideRefused("the governance policy does not allow editing the proposed workforce; reject it with "
                              "your feedback and Cynqra revises it")
    if not isinstance(edited_roles, list) or not edited_roles:
        raise IntelligenceError("an edited workforce needs roles")
    edited = validate_workforce({"summary": proposal.get("summary", ""), "roles": edited_roles}, requirements)
    edited["overridden"] = True
    return edited
