import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from store import REASONS, STAGES, CandidateError, CandidateStore

T0 = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


class StoreTests(unittest.TestCase):
    def test_create_starts_applied(self):
        s = CandidateStore()
        rec = s.create("Priya Shah")
        self.assertEqual(rec["stage"], "applied")
        self.assertEqual(rec["reason"], "")

    def test_empty_name_is_refused(self):
        with self.assertRaises(CandidateError):
            CandidateStore().create("   ")

    def test_list_returns_all(self):
        s = CandidateStore()
        s.create("Priya Shah")
        s.create("Jordan Lee")
        self.assertEqual(len(s.list()), 2)

    def test_stages_are_a_closed_list(self):
        self.assertEqual(STAGES, ("applied", "screen", "interview", "offer", "hired", "rejected"))
        s = CandidateStore()
        rec = s.create("Sam Okoye")
        with self.assertRaises(CandidateError):
            s.set_stage(rec["id"], "ghost")

    def test_unknown_candidate_is_refused(self):
        with self.assertRaises(CandidateError):
            CandidateStore().set_stage("c_999", "screen")

    def test_set_stage_persists(self):
        s = CandidateStore()
        rec = s.create("Ada West")
        s.set_stage(rec["id"], "interview")
        self.assertEqual(s.get(rec["id"])["stage"], "interview")

    def test_clock_only_flags(self):
        s = CandidateStore()
        rec = s.create("Old Card", applied_at=T0)
        now = T0 + timedelta(days=8)
        self.assertEqual([r["id"] for r in s.flagged(now)], [rec["id"]])
        self.assertEqual(s.stuck(now), [])

    def test_stuck_needs_a_named_reason(self):
        s = CandidateStore()
        rec = s.create("Old Card", applied_at=T0)
        s.set_reason(rec["id"], REASONS[0])
        self.assertEqual([r["id"] for r in s.stuck(T0 + timedelta(days=8))], [rec["id"]])
        with self.assertRaises(CandidateError):
            s.set_reason(rec["id"], "because")

    def test_moving_the_stage_clears_both_marks(self):
        s = CandidateStore()
        rec = s.create("Old Card", applied_at=T0)
        s.set_reason(rec["id"], "no_owner")
        s.set_stage(rec["id"], "interview", now=T0 + timedelta(days=8))
        later = T0 + timedelta(days=9)
        self.assertEqual(s.flagged(later), [])
        self.assertEqual(s.stuck(later), [])

    def test_survives_a_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "candidates.json")
            s = CandidateStore(path)
            rec = s.create("Kept")
            s.set_stage(rec["id"], "screen")
            again = CandidateStore(path)
            self.assertEqual(again.get(rec["id"])["stage"], "screen")
            self.assertEqual(again.create("Next")["id"], "c_002")


if __name__ == "__main__":
    unittest.main()
