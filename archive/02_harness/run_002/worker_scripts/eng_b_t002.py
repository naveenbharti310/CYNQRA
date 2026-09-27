#!/usr/bin/env python3
"""Engineer B: finish from inbox only. Guessing is forbidden."""
from __future__ import annotations

import json
from pathlib import Path

from guard import assert_inside, home

H = home()
handoff = json.loads(assert_inside(H / "inbox" / "handoff.json").read_text(encoding="utf-8"))
art = H / "inbox" / "artifacts"
store_src = art / "store.py"
check = (handoff.get("acceptance_check") or "").lower()


def raise_blocker(desc, category="underspecified"):
    blocker = {
        "protocol": "Blocker",
        "raised_by": "w_eng_b",
        "task_id": handoff.get("task_id", "t_002"),
        "category": category,
        "severity": "SEV-2",
        "description": desc,
        "needs_from": "w_pm",
    }
    assert_inside(H / "outbox" / "blocker.json").write_text(
        json.dumps(blocker, indent=2) + "\n", encoding="utf-8"
    )
    print("eng_b blocked:", desc)


if handoff.get("to_worker") != "w_eng_b":
    raise_blocker("Handoff is not addressed to Engineer B.", "wrong_recipient")
    raise SystemExit(0)
if not store_src.exists():
    raise_blocker("store.py was listed but not in inbox/artifacts.", "missing_input")
    raise SystemExit(0)

STAGES = None
for p in (H / "inbox").rglob("*.json"):
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        continue
    if isinstance(data, dict) and isinstance(data.get("allowed_stages"), list):
        STAGES = tuple(data["allowed_stages"])
        break
    blob = json.dumps(data).lower()
    if all(s in blob for s in ("applied", "screen", "interview", "offer", "hired", "rejected")):
        if "allowed_stages" in data:
            STAGES = tuple(data["allowed_stages"])
            break

if not STAGES:
    raise_blocker(
        "Closed list of stages is not in the inbox. "
        "Engineer B will not invent applied/screen/interview/offer/hired/rejected."
    )
    raise SystemExit(0)

src = store_src.read_text(encoding="utf-8")
stages_lit = ", ".join(repr(s) for s in STAGES)
extension = f'''
ALLOWED_STAGES = ({stages_lit})


def _patch():
    _create = CandidateStore.create
    def create(self, name):
        rec = _create(self, name)
        rec["stage"] = "applied"
        self._items[rec["id"]]["stage"] = "applied"
        return rec
    def set_stage(self, cid, stage):
        if cid not in self._items:
            raise CandidateError("unknown candidate")
        if stage not in ALLOWED_STAGES:
            raise CandidateError("unknown stage")
        self._items[cid]["stage"] = stage
        return dict(self._items[cid])
    CandidateStore.create = create
    CandidateStore.set_stage = set_stage

_patch()
'''
store = src + extension
test = f'''import unittest
from store import ALLOWED_STAGES, CandidateError, CandidateStore


class TestStages(unittest.TestCase):
    def test_create_starts_applied(self):
        s = CandidateStore()
        a = s.create("Priya Shah")
        self.assertEqual(a["stage"], "applied")

    def test_set_stage(self):
        s = CandidateStore()
        a = s.create("Jordan Lee")
        b = s.set_stage(a["id"], "interview")
        self.assertEqual(b["stage"], "interview")

    def test_unknown_stage(self):
        s = CandidateStore()
        a = s.create("Sam Okoye")
        with self.assertRaises(CandidateError):
            s.set_stage(a["id"], "ghost")

    def test_closed_list(self):
        self.assertEqual(set(ALLOWED_STAGES), set({list(STAGES)!r}))


if __name__ == "__main__":
    unittest.main()
'''
out = assert_inside(H / "outbox")
(out / "store.py").write_text(store, encoding="utf-8")
(out / "test_store.py").write_text(test, encoding="utf-8")
blocker = out / "blocker.json"
if blocker.exists():
    blocker.unlink()
print("eng_b wrote staged store and tests")
