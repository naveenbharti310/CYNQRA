"""Protocol objects: Handoff, Blocker, Review, Escalation, Approval (Book 2 section 7, MVP subset).

A Review is a cofounder's verdict on its team member's work: approve, or revise with what to change.

Same templates as archive/02_harness/protocols, with the envelope fields break b_006 asked
for. Routing fields are always set by the platform, never taken from model text.
"""
from __future__ import annotations

import json

from .db import digest, now

TEMPLATES = {
    "Handoff": {"from_worker": "", "to_worker": "", "task_id": "", "artifacts": [], "context_ref": "",
                "acceptance_check": ""},
    "Blocker": {"raised_by": "", "task_id": "", "category": "", "severity": "SEV-2", "description": "",
                "needs_from": ""},
    "Review": {"reviewed_by": "", "owner": "", "task_id": "", "verdict": "", "note": ""},
    "Escalation": {"raised_by": "", "issue": "", "severity": "SEV-2", "owner": "", "required_action": "",
                   "status": "open"},
    "Approval": {"decision_id": "", "from_worker": "", "to_worker": "founder", "task_id": "", "recommendation": "",
                 "evidence_refs": [], "cost": "", "risk": "", "confidence": "",
                 "options": ["approve", "reject", "request_evidence"], "what_would_change_this": ""},
}

REQUIRED = {
    "Handoff": ["from_worker", "to_worker", "task_id", "acceptance_check"],
    "Blocker": ["raised_by", "task_id", "description", "needs_from"],
    "Review": ["reviewed_by", "owner", "task_id", "verdict", "note"],
    "Escalation": ["raised_by", "issue", "owner", "required_action"],
    "Approval": ["decision_id", "from_worker", "recommendation", "risk", "confidence", "what_would_change_this"],
}

ROUTING = {"from_worker", "to_worker", "task_id", "raised_by", "decision_id", "risk", "owner", "reviewed_by"}


class ProtocolError(ValueError):
    pass


def _shape(value, template):
    """A model's value in the template's shape: a list of text where the template holds a list, else one text.
    A model may answer a field with a number, a list or an object; it is converted here before anything uses it."""
    if isinstance(template, list):
        value = [value] if isinstance(value, str) else value if isinstance(value, list) else []
        return [v.strip() for v in value if isinstance(v, str) and v.strip()]
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)[:4000]
    return str(value)


def build(kind: str, content: dict | None, routing: dict, correlation_id: str) -> dict:
    """Template, then model content (non routing keys only), then routing, then envelope."""
    if kind not in TEMPLATES:
        raise ProtocolError(f"unknown protocol {kind}")
    obj = dict(TEMPLATES[kind])
    for key, value in (content if isinstance(content, dict) else {}).items():
        if key in obj and key not in ROUTING:
            obj[key] = _shape(value, obj[key])
    obj.update(routing)
    obj["protocol"] = kind
    obj["protocol_version"] = 1
    obj["created_at"] = now()
    obj["correlation_id"] = correlation_id
    missing = [k for k in REQUIRED[kind] if not str(obj.get(k) or "").strip()]
    if missing:
        raise ProtocolError(f"{kind} is missing {', '.join(missing)}")
    obj["object_hash"] = digest({k: v for k, v in obj.items() if k != "object_hash"})
    return obj
