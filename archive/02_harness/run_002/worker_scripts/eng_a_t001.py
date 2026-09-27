#!/usr/bin/env python3
"""Engineer A: implement only what the Handoff says."""
from __future__ import annotations

import json
from pathlib import Path

from guard import assert_inside, home

H = home()
handoff = json.loads(assert_inside(H / "inbox" / "handoff.json").read_text(encoding="utf-8"))
if handoff.get("to_worker") != "w_eng_a" or handoff.get("task_id") != "t_001":
    raise SystemExit("Engineer A expected handoff t_001")
check = handoff.get("acceptance_check") or ""
if "create" not in check or "list" not in check:
    blocker = {
        "protocol": "Blocker",
        "raised_by": "w_eng_a",
        "task_id": "t_001",
        "category": "underspecified",
        "severity": "SEV-2",
        "description": "Handoff acceptance_check does not mention create and list.",
        "needs_from": "w_pm",
    }
    assert_inside(H / "outbox" / "blocker.json").write_text(
        json.dumps(blocker, indent=2) + "\n", encoding="utf-8"
    )
    print("eng_a blocked")
    raise SystemExit(0)

store = '''class CandidateError(Exception):
    pass


class CandidateStore:
    def __init__(self):
        self._items = {}
        self._n = 0

    def create(self, name):
        if not str(name or "").strip():
            raise CandidateError("name required")
        self._n += 1
        cid = f"c_{self._n:03d}"
        rec = {"id": cid, "name": str(name).strip()}
        self._items[cid] = rec
        return dict(rec)

    def list(self):
        return [dict(v) for v in self._items.values()]
'''
test = '''import unittest
from store import CandidateError, CandidateStore


class TestCreateList(unittest.TestCase):
    def test_create_and_list(self):
        s = CandidateStore()
        a = s.create("Priya Shah")
        self.assertEqual(a["name"], "Priya Shah")
        self.assertTrue(a["id"].startswith("c_"))
        self.assertEqual(len(s.list()), 1)

    def test_empty_name(self):
        s = CandidateStore()
        with self.assertRaises(CandidateError):
            s.create("  ")

    def test_no_stage_yet(self):
        s = CandidateStore()
        a = s.create("Jordan Lee")
        self.assertNotIn("stage", a)


if __name__ == "__main__":
    unittest.main()
'''
ws = assert_inside(H / "workspace")
(ws / "store.py").write_text(store, encoding="utf-8")
(ws / "test_store.py").write_text(test, encoding="utf-8")
out = assert_inside(H / "outbox")
(out / "store.py").write_text(store, encoding="utf-8")
(out / "test_store.py").write_text(test, encoding="utf-8")
print("eng_a wrote store and tests")
