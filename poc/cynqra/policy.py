"""Policy and authority: the canonical policy.evaluate contract of the Book 2 addendum.

Rows come from the working text of D-27 (risk rubric) and D-28 (authority matrix) in
archive/old_docs/POC_SPEC.md, pending re-ratification under D-34. D-17 (founder reviews every MEDIUM
action) and D-21 (founder approves every production deploy) are enforced here.
Default is DENY: an action type or role not listed is refused.
"""
from __future__ import annotations

from . import roles

POLICY_VERSION = "poc-2026-09-27.1"

# action_type -> risk tier (D-27 working text)
RISK = {
    "write_file": "LOW",
    "read_artifact": "LOW",
    "run_tests": "LOW",
    "send_protocol": "LOW",
    "assign_task": "LOW",
    "answer_blocker": "LOW",
    "review_work": "LOW",
    "product_rule_decision": "MEDIUM",
    "merge_to_main": "MEDIUM",
    "install_package": "MEDIUM",
    "deploy_production": "HIGH",
    "delete_data": "HIGH",
    "external_message": "PROHIBITED",
    "move_money": "PROHIBITED",
    "legal_commitment": "PROHIBITED",
    "change_objective": "PROHIBITED",
    "change_budget": "PROHIBITED",
    "change_authority": "PROHIBITED",
}

E, P, N = "execute", "propose", "none"

# role -> action_type -> E / P / N (D-28 working text), one row per role in the catalog (roles.py). The rows of the
# M1 roles (CTO, PM, Engineer) are unchanged; the roles the product definition adds get rows of their own.
MATRIX = roles.matrix()

FOUNDER_ONLY = {"change_objective", "change_budget", "change_authority", "approve_workforce",
                "approve_roadmap", "accept_delivery", "kill_switch"}


def evaluate(*, role: str, action_type: str, autonomy_level: str = "L1", budget_state: str = "ok",
             frozen: bool = False, environment: str = "sandbox", target: str = "") -> dict:
    """Return ALLOW, DENY or REQUIRE_APPROVAL with the reason. Never raises."""
    risk = RISK.get(action_type)
    base = {"policy_version": POLICY_VERSION, "risk_tier": risk or "UNKNOWN", "action_type": action_type,
            "role": role, "required_approver": None, "conditions": []}

    def out(decision: str, reason: str, approver=None, conditions=None):
        d = dict(base)
        d.update({"decision": decision, "reason": reason, "required_approver": approver,
                  "conditions": conditions or []})
        return d

    if frozen:
        return out("DENY", "Kill switch is on. All workers are frozen.")
    if risk is None:
        return out("DENY", f"Unknown action type {action_type!r}. Default deny.")
    if risk == "PROHIBITED":
        return out("DENY", f"{action_type} is prohibited for every worker at every autonomy level (D-27, Book 1 addendum).")
    grant = MATRIX.get(role, {}).get(action_type, N)
    if grant == N:
        return out("DENY", f"{role} has no authority for {action_type} (D-28).")
    if budget_state == "breaker" and action_type not in ("send_protocol", "read_artifact"):
        return out("DENY", "Budget breaker is open. Work is paused until the founder acts.")
    if risk == "HIGH":
        return out("REQUIRE_APPROVAL", f"{action_type} is HIGH risk; production deploys need the founder at every level (D-21).",
                   approver="founder")
    if risk == "MEDIUM":
        return out("REQUIRE_APPROVAL", f"{action_type} is MEDIUM risk; the founder reviews every MEDIUM action in the MVP (D-17).",
                   approver="founder")
    if grant == P:
        return out("REQUIRE_APPROVAL", f"{role} may only propose {action_type}.", approver="founder")
    return out("ALLOW", f"{role} executes {action_type} at LOW risk inside its workspace.",
               conditions=["own workspace only", "allowlisted tool", "within task budget"])


def who_may(action_type: str) -> dict:
    """Graph query: who executes, who proposes, who approves an action type."""
    execs = sorted(r for r, m in MATRIX.items() if m.get(action_type) == E)
    props = sorted(r for r, m in MATRIX.items() if m.get(action_type) == P)
    risk = RISK.get(action_type, "UNKNOWN")
    if action_type in FOUNDER_ONLY:
        approver = "founder only"
    elif risk in ("MEDIUM", "HIGH") or props:
        approver = "founder"
    elif risk == "PROHIBITED":
        approver = "nobody: prohibited for workers"
    else:
        approver = "no approval needed at LOW"
    return {"action_type": action_type, "risk_tier": risk, "executes": execs, "proposes": props, "approves": approver}
