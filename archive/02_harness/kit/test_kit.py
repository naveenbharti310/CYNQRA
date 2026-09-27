#!/usr/bin/env python3
"""Prove the kit verifier catches the five Day 6 seeds."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUN = ROOT.parent / "run_002"
sys.path.insert(0, str(ROOT))

from protocol import stamp, object_hash
from verify import verify_submission


class TestProtocol(unittest.TestCase):
    def test_stamp_adds_envelope(self):
        obj = {"protocol": "Handoff", "from_worker": "w_pm", "to_worker": "w_eng_a"}
        out = stamp(obj, "run_kit")
        self.assertEqual(out["protocol_version"], 1)
        self.assertTrue(out["created_at"])
        self.assertEqual(out["correlation_id"], "run_kit")
        self.assertEqual(len(out["object_hash"]), 16)
        self.assertEqual(out["object_hash"], object_hash(out))


class TestVerifierCatchesDay6(unittest.TestCase):
    def test_tainted_submission_fails_prior_tests_and_spec(self):
        submission = RUN / "day6" / "submission"
        held = [
            RUN / "workers" / "eng_a" / "outbox" / "test_store.py",
            RUN / "workers" / "eng_b" / "outbox" / "test_store.py",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            report = verify_submission(submission, held, Path(tmp) / "work")
        self.assertEqual(report["verdict"], "FAILED")
        failed = []
        for row in report["tests"]:
            failed.extend(row["failed_tests"])
        blob = " ".join(failed) + " " + " ".join(r["output"] for r in report["tests"])
        self.assertIn("test_unknown_stage", blob)
        self.assertTrue(
            "test_create_starts_applied" in blob or "test_empty_name" in blob or "test_create_and_list" in blob
        )
        self.assertTrue(report["spec_violations"])
        self.assertEqual(report["spec_violations"][0]["rule"], "decision_001")

    def test_clean_store_passes_held_tests_without_bad_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            sub = Path(tmp) / "sub"
            sub.mkdir()
            shutil_copy = (RUN / "workers" / "eng_b" / "outbox" / "store.py").read_text(encoding="utf-8")
            (sub / "store.py").write_text(shutil_copy, encoding="utf-8")
            (sub / "note.md").write_text(
                "Stuck requires a named reason such as waiting_on_recruiter.\n",
                encoding="utf-8",
            )
            held = [RUN / "workers" / "eng_b" / "outbox" / "test_store.py"]
            report = verify_submission(sub, held, Path(tmp) / "work")
        self.assertEqual(report["verdict"], "VERIFIED")
        self.assertFalse(report["spec_violations"])


if __name__ == "__main__":
    unittest.main()
