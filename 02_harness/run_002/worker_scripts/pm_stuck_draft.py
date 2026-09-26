#!/usr/bin/env python3
"""PM: first draft of stuck, then the amended object after founder label.

The first draft is the failure mode we already saw. It is written on purpose
so the tape contains the wrong metric, then the amended rule.
"""
from __future__ import annotations

import json

from guard import assert_inside, home

H = home()
draft = {
    "protocol": "Approval",
    "decision_id": "decision_001",
    "task_id": "t_003",
    "recommendation": "A candidate with no stage change for 7 days is stuck.",
    "evidence_refs": ["objective.json success_criteria"],
    "cost": "none. local product rule only",
    "risk": "MEDIUM",
    "confidence": "medium",
    "options": ["approve", "reject", "request_evidence"],
    "what_would_change_this": "Evidence that recruiters already treat age as stuck.",
    "outcome_label": "",
    "labeled_by": "",
    "labeled_at": "",
    "status": "pending_founder",
}
assert_inside(H / "outbox" / "approval_decision_001_draft.json").write_text(
    json.dumps(draft, indent=2) + "\n", encoding="utf-8"
)

amended = {
    "protocol": "Approval",
    "decision_id": "decision_001",
    "task_id": "t_003",
    "recommendation": (
        "A 7 day clock only flags a card in applied or screen. "
        "Stuck requires a named reason from: waiting_on_recruiter, "
        "waiting_on_candidate, waiting_on_founder, missing_document, no_owner. "
        "If the stage already moved, both marks clear."
    ),
    "evidence_refs": ["objective.json success_criteria", "founder int_002"],
    "cost": "none. local product rule only",
    "risk": "MEDIUM",
    "confidence": "high",
    "options": ["approve", "reject", "request_evidence"],
    "what_would_change_this": (
        "Evidence that recruiters need the clock itself to mean stuck, "
        "or a new allowed reason that is not in the closed list."
    ),
    "outcome_label": "approved_edited",
    "labeled_by": "founder",
    "labeled_at": "2026-08-24T16:58:00+05:30",
    "status": "decided",
    "note": "First draft rejected. Founder required cause, not only elapsed days.",
}
assert_inside(H / "outbox" / "approval_decision_001.json").write_text(
    json.dumps(amended, indent=2) + "\n", encoding="utf-8"
)
print("pm wrote stuck draft and amended approval")
