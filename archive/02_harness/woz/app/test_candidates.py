#!/usr/bin/env python3
import unittest
from datetime import datetime, timedelta, timezone

from candidates import (
    CandidateError,
    create_candidate,
    list_candidates,
    list_flagged,
    list_stuck,
    new_store,
    set_stage,
    set_stuck_reason,
)


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.store = new_store()
        self.t0 = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)

    def test_create_and_list(self):
        created = create_candidate(self.store, "Ada West", "Engineer", "ref", now=self.t0)
        self.assertEqual(created["stage"], "applied")
        self.assertEqual(created["stuck_reason"], "")
        self.assertEqual(len(list_candidates(self.store)), 1)

    def test_create_requires_name_and_role(self):
        with self.assertRaises(CandidateError):
            create_candidate(self.store, "", "Engineer")
        with self.assertRaises(CandidateError):
            create_candidate(self.store, "Ada", "")

    def test_set_stage(self):
        created = create_candidate(self.store, "Ada West", "Engineer", now=self.t0)
        later = self.t0 + timedelta(days=1)
        updated = set_stage(self.store, created["id"], "interview", now=later)
        self.assertEqual(updated["stage"], "interview")
        self.assertEqual(updated["last_moved_at"], later.isoformat())

    def test_unknown_stage_rejected(self):
        created = create_candidate(self.store, "Ada West", "Engineer", now=self.t0)
        with self.assertRaises(CandidateError):
            set_stage(self.store, created["id"], "ghost")

    def test_clock_only_flags(self):
        create_candidate(self.store, "Old Card", "PM", now=self.t0)
        now = self.t0 + timedelta(days=8)
        self.assertEqual([c["name"] for c in list_flagged(self.store, now=now)], ["Old Card"])
        self.assertEqual(list_stuck(self.store, now=now), [])

    def test_stuck_needs_a_reason(self):
        created = create_candidate(self.store, "Old Card", "PM", now=self.t0)
        set_stuck_reason(self.store, created["id"], "waiting_on_recruiter")
        now = self.t0 + timedelta(days=8)
        stuck = list_stuck(self.store, now=now)
        self.assertEqual([c["name"] for c in stuck], ["Old Card"])
        self.assertEqual(stuck[0]["stuck_reason"], "waiting_on_recruiter")

    def test_stage_change_clears_stuck_immediately(self):
        created = create_candidate(self.store, "Old Card", "PM", now=self.t0)
        set_stuck_reason(self.store, created["id"], "waiting_on_candidate")
        later = self.t0 + timedelta(days=8)
        set_stage(self.store, created["id"], "interview", now=later)
        self.assertEqual(list_flagged(self.store, now=later), [])
        self.assertEqual(list_stuck(self.store, now=later), [])

    def test_cannot_mark_stuck_after_interview(self):
        created = create_candidate(self.store, "Ada West", "Engineer", now=self.t0)
        set_stage(self.store, created["id"], "interview", now=self.t0)
        with self.assertRaises(CandidateError):
            set_stuck_reason(self.store, created["id"], "waiting_on_recruiter")

    def test_unknown_reason_rejected(self):
        created = create_candidate(self.store, "Ada West", "Engineer", now=self.t0)
        with self.assertRaises(CandidateError):
            set_stuck_reason(self.store, created["id"], "bad_vibes")


if __name__ == "__main__":
    unittest.main()
