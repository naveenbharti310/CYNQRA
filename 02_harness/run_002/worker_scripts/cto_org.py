#!/usr/bin/env python3
"""CTO: instantiate the fixed four worker template. Nothing else."""
from __future__ import annotations

import json
from pathlib import Path

from guard import assert_inside, home

H = home()
inbox = assert_inside(H / "inbox" / "objective.json")
obj = json.loads(inbox.read_text(encoding="utf-8"))
if obj.get("id") != "obj_001":
    raise SystemExit("CTO expected obj_001")

org = {
    "id": "org_001",
    "company_id": obj["company_id"],
    "version": 1,
    "status": "active",
    "template": "fixed_mvp_4",
    "workers": [
        {"id": "w_cto", "role": "CTO", "authority": "LOW and MEDIUM, propose HIGH"},
        {"id": "w_pm", "role": "PM", "authority": "LOW protocols and MEDIUM priorities"},
        {"id": "w_eng_a", "role": "Engineer A", "authority": "LOW sandbox, MEDIUM merge and preview"},
        {"id": "w_eng_b", "role": "Engineer B", "authority": "LOW sandbox, MEDIUM merge and preview"},
    ],
    "note": "QA is the platform Verification Service, not a fifth worker.",
}
out = assert_inside(H / "outbox" / "organization.json")
out.write_text(json.dumps(org, indent=2) + "\n", encoding="utf-8")
print("cto wrote organization.json")
