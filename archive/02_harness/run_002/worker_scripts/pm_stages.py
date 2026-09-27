#!/usr/bin/env python3
"""PM: clear Engineer B Blocker with the closed stage list. Founder stays out."""
from __future__ import annotations

import json

from guard import assert_inside, home

H = home()
blocker_path = H / "inbox" / "blocker.json"
if not blocker_path.exists():
    raise SystemExit("PM expected a Blocker in inbox")
blocker = json.loads(assert_inside(blocker_path).read_text(encoding="utf-8"))
if blocker.get("task_id") != "t_002":
    raise SystemExit("PM expected Blocker for t_002")

handoff = {
    "protocol": "Handoff",
    "from_worker": "w_pm",
    "to_worker": "w_eng_b",
    "task_id": "t_002",
    "artifacts": [],
    "context_ref": "tasks.json t_002",
    "acceptance_check": (
        "set_stage accepts only the closed list in allowed_stages. "
        "create starts at applied. unknown stages raise CandidateError."
    ),
    "allowed_stages": ["applied", "screen", "interview", "offer", "hired", "rejected"],
}
assert_inside(H / "outbox" / "handoff_t002_stages.json").write_text(
    json.dumps(handoff, indent=2) + "\n", encoding="utf-8"
)
print("pm wrote closed stage list for t_002")
