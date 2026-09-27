#!/usr/bin/env python3
"""Engineer A: hand t_001 artifacts to Engineer B with the stage contract."""
from __future__ import annotations

import json
from pathlib import Path

from guard import assert_inside, home

H = home()
out = assert_inside(H / "outbox")
store = out / "store.py"
test = out / "test_store.py"
if not store.exists() or not test.exists():
    raise SystemExit("Engineer A cannot hand off files that are not in outbox")

# Stages come from the PM task text that Engineer A does not have in inbox
# on this turn. Engineer A only has what is already in this home.
# The previous turn left store.py. The stage list is NOT in that file.
# If we invent the list here without a Handoff from PM, that is a guess.
# Check inbox for a PM object about t_002. If missing, write a Blocker
# instead of guessing the closed list.
inbox_files = {p.name for p in (H / "inbox").iterdir()}
handoff = {
    "protocol": "Handoff",
    "from_worker": "w_eng_a",
    "to_worker": "w_eng_b",
    "task_id": "t_002",
    "artifacts": ["store.py", "test_store.py"],
    "context_ref": "t_001 outbox",
    "acceptance_check": "",
}
# Honest: Engineer A does not have the closed stage list in inbox.
# Do not invent it. Engineer B must receive the list from PM, or raise Blocker.
handoff["acceptance_check"] = (
    "Extend the handed store so a candidate can hold a stage. "
    "The closed list of allowed stages is not in Engineer A inbox. "
    "Do not invent the list. If the list is not in your inbox, raise a Blocker."
)
assert_inside(out / "handoff_t002.json").write_text(
    json.dumps(handoff, indent=2) + "\n", encoding="utf-8"
)
print("eng_a wrote handoff_t002 (stage list not included)")
