#!/usr/bin/env python3
"""PM: open the first three tasks from the objective and the org."""
from __future__ import annotations

import json
from pathlib import Path

from guard import assert_inside, home

H = home()
obj = json.loads(assert_inside(H / "inbox" / "objective.json").read_text(encoding="utf-8"))
org = json.loads(assert_inside(H / "inbox" / "organization.json").read_text(encoding="utf-8"))
ids = {w["id"] for w in org["workers"]}
if ids != {"w_cto", "w_pm", "w_eng_a", "w_eng_b"}:
    raise SystemExit("PM refuses an org that is not the fixed four")

fields = obj["structured"]
tasks = {
    "workstreams": [
        {"id": "ws_core", "name": "Candidate record core", "status": "open"},
        {"id": "ws_stuck", "name": "Stuck visibility", "status": "open"},
    ],
    "tasks": [
        {
            "id": "t_001",
            "workstream_id": "ws_core",
            "owner_worker_id": "w_eng_a",
            "inputs": "PM Handoff handoff_t001.json",
            "expected_output": "in memory candidate store with create and list",
            "dependencies": [],
            "tools": ["python", "test runner"],
            "budget": "local only",
            "deadline": "2026-08-26",
            "verification_method": "automated tests",
            "risk_tier": "LOW",
            "status": "OPEN",
        },
        {
            "id": "t_002",
            "workstream_id": "ws_core",
            "owner_worker_id": "w_eng_b",
            "inputs": "Engineer A Handoff plus listed artifacts",
            "expected_output": "stage field with the closed list of stages",
            "dependencies": ["t_001"],
            "tools": ["python", "test runner"],
            "budget": "local only",
            "deadline": "2026-08-27",
            "verification_method": "automated tests",
            "risk_tier": "LOW",
            "status": "OPEN",
        },
        {
            "id": "t_003",
            "workstream_id": "ws_stuck",
            "owner_worker_id": "w_pm",
            "inputs": "objective success criteria",
            "expected_output": "named meaning of stuck, as an Approval",
            "dependencies": [],
            "tools": ["editor"],
            "budget": "none",
            "deadline": "2026-08-26",
            "verification_method": "founder review",
            "risk_tier": "MEDIUM",
            "status": "OPEN",
        },
    ],
}
assert_inside(H / "outbox" / "tasks.json").write_text(
    json.dumps(tasks, indent=2) + "\n", encoding="utf-8"
)

# First Handoff to Engineer A. Create and list only. No stages. No stuck.
handoff = {
    "protocol": "Handoff",
    "from_worker": "w_pm",
    "to_worker": "w_eng_a",
    "task_id": "t_001",
    "artifacts": [],
    "context_ref": "objective.json structured fields",
    "acceptance_check": (
        "create(name) stores a candidate and returns it with an id; "
        "list() returns all created candidates; empty name is an error; "
        "do not add stages; do not add stuck."
    ),
    "constraints": fields["constraints"],
    "product": fields["product"],
}
assert_inside(H / "outbox" / "handoff_t001.json").write_text(
    json.dumps(handoff, indent=2) + "\n", encoding="utf-8"
)
print("pm wrote tasks and handoff_t001")
