#!/usr/bin/env python3
"""Tests for the spike harness. Written 26 September 2026 by the acting CTO.

Every test runs on a throwaway copy of 02_harness, so nothing here can write a
report into the real tree. No test calls a real model. The stub in
stub_model.py is a wiring aid and refuses S1 prompts.

Run: python spikes/test_spikes.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
PY = sys.executable
NO_MODEL = {k: v for k, v in os.environ.items()
            if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CYNQRA_S1_MODEL_CMD", "CYNQRA_MODEL")}


# Pure functions are imported from the real tree. They only read files.
sys.path.insert(0, str(HARNESS / "spikes" / "s1"))
sys.path.insert(0, str(HARNESS / "spikes" / "s2"))
sys.path.insert(0, str(HARNESS / "spikes"))
sys.path.insert(0, str(HARNESS / "kit"))
from run_s1 import load_corpus, prompt_for, score_one  # noqa: E402
from run_s2 import ratio_check  # noqa: E402
from contract_checks import check_store  # noqa: E402


def copy_harness() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="cynqra_test_"))
    dest = tmp / "02_harness"
    shutil.copytree(HARNESS, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return dest


def run(args, cwd, extra_env=None):
    env = dict(NO_MODEL)
    env.update(extra_env or {})
    return subprocess.run([PY] + args, cwd=str(cwd), env=env, capture_output=True, text=True)


def cmd(path: Path) -> str:
    return f'"{PY}" "{path}"'


class S1(unittest.TestCase):
    def setUp(self):
        self.h = copy_harness()

    def tearDown(self):
        shutil.rmtree(self.h.parent, ignore_errors=True)

    def test_no_model_refuses(self):
        r = run(["spikes/s1/run_s1.py"], self.h)
        self.assertEqual(r.returncode, 2)
        self.assertFalse((self.h / "spikes/s1/s1_report.json").exists())

    def test_model_error_is_unrun_not_zero(self):
        failing = self.h / "fail.py"
        failing.write_text("import sys\nsys.exit(1)\n")
        r = run(["spikes/s1/run_s1.py"], self.h, {"CYNQRA_S1_MODEL_CMD": cmd(failing)})
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertFalse((self.h / "spikes/s1/s1_report.json").exists())
        self.assertTrue((self.h / "spikes/s1/s1_unrun.json").exists())

    def test_stub_cannot_produce_an_s1_report(self):
        r = run(["spikes/s1/run_s1.py"], self.h, {"CYNQRA_S1_MODEL_CMD": cmd(self.h / "spikes/stub_model.py")})
        self.assertEqual(r.returncode, 3)
        self.assertFalse((self.h / "spikes/s1/s1_report.json").exists())

    def test_scorer_unchanged_and_why_prompt_changed(self):
        corpus = load_corpus()
        full = sum(score_one(dict(c["gold"]), c["gold"])["passed"] for c in corpus)
        blank = 0
        for c in corpus:
            ans = dict(c["gold"])
            ans["priorities"] = ""
            blank += score_one(ans, c["gold"])["passed"]
        self.assertEqual(full, 10)
        self.assertEqual(blank, 0, "a blank field fails, which is why prompt v1 could not pass")

    def test_prompt_and_pages_hold_no_expected_answers(self):
        corpus = load_corpus()
        blobs = [prompt_for(c["messy"]) + prompt_for(c["messy"], retry=True) for c in corpus]
        blobs.append((self.h / "spikes/s1/PASTE_PACK.md").read_text(encoding="utf-8"))
        page = HARNESS.parent / "03_pages" / "cynqra-s1-paste-pack.html"
        if page.exists():
            blobs.append(page.read_text(encoding="utf-8"))
        for c in corpus:
            for field, gold in c["gold"].items():
                if gold.lower() in c["messy"].lower():
                    continue  # the founder's own words are allowed to appear
                for b in blobs:
                    self.assertNotIn(gold, b, f"{c['id']} {field} leaks")

    def test_manual_scorer_refuses_partial_and_reads_bundle(self):
        r = run(["spikes/s1/score_manual.py"], self.h)
        self.assertEqual(r.returncode, 2)
        corpus = json.loads((self.h / "spikes/s1/corpus.json").read_text())
        bundle = {"prompt_version": "test", "model": "test harness",
                  "answers": {c["id"]: json.dumps(c["gold"]) for c in corpus}}
        (self.h / "spikes/s1/answers/s1_answers.json").write_text(json.dumps(bundle))
        r = run(["spikes/s1/score_manual.py"], self.h)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rep = json.loads((self.h / "spikes/s1/s1_report.json").read_text())
        self.assertEqual(rep["passed"], 10)
        self.assertEqual(rep["source"], "manual_paste")
        self.assertIn("test harness", rep["model"])


class S2(unittest.TestCase):
    def setUp(self):
        self.h = copy_harness()

    def tearDown(self):
        shutil.rmtree(self.h.parent, ignore_errors=True)

    def test_no_model_refuses(self):
        r = run(["spikes/s2/run_s2.py"], self.h)
        self.assertEqual(r.returncode, 2)

    def test_stub_is_a_wiring_test_never_a_result(self):
        r = run(["spikes/s2/run_s2.py"], self.h, {"CYNQRA_S1_MODEL_CMD": cmd(self.h / "spikes/stub_model.py")})
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertFalse((self.h / "spikes/s2/s2_report.json").exists())
        rep = json.loads((self.h / "spikes/s2/s2_wiring_test.json").read_text())
        self.assertIsNone(rep["met_bar"])
        self.assertEqual(rep["tasks"], 12)
        self.assertTrue(rep["all_messages_structured"])
        t07 = [x for x in rep["rows"] if x["task_id"] == "t2_07"][0]
        self.assertEqual(t07["blocker_rounds"], 1, "Blocker path must run")
        med = [x for x in rep["rows"] if x["risk"] == "MEDIUM"]
        self.assertTrue(all(x["founder_touched"] for x in med), "D-17: founder reviews MEDIUM")
        msgs = json.loads((self.h / "spikes/s2/s2_wiring_messages.json").read_text())["messages"]
        for m in msgs:
            for k in ("protocol", "protocol_version", "created_at", "correlation_id", "object_hash"):
                self.assertIn(k, m["object"])

    def test_model_error_is_unrun(self):
        failing = self.h / "fail.py"
        failing.write_text("import sys\nsys.exit(1)\n")
        r = run(["spikes/s2/run_s2.py"], self.h, {"CYNQRA_S1_MODEL_CMD": cmd(failing)})
        self.assertEqual(r.returncode, 3)
        self.assertTrue((self.h / "spikes/s2/s2_unrun.json").exists())
        self.assertFalse((self.h / "spikes/s2/s2_report.json").exists())

    def test_two_sided_bar(self):
        self.assertTrue(ratio_check(12000, 12000)["within_2x"])
        self.assertTrue(ratio_check(24000, 12000)["within_2x"])
        self.assertTrue(ratio_check(6000, 12000)["within_2x"])
        self.assertFalse(ratio_check(229, 12000)["within_2x"])
        self.assertFalse(ratio_check(30000, 12000)["within_2x"])


class S3(unittest.TestCase):
    def setUp(self):
        self.h = copy_harness()

    def tearDown(self):
        shutil.rmtree(self.h.parent, ignore_errors=True)

    def test_v1_record_is_never_overwritten(self):
        before = (self.h / "spikes/s3/s3_report.json").read_bytes()
        r = run(["spikes/s3/run_s3.py"], self.h)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(before, (self.h / "spikes/s3/s3_report.json").read_bytes())
        rec = json.loads(before)
        self.assertEqual(rec["missed"], ["s3_06"])

    def test_error_surfacing_probes(self):
        tainted = {f["id"]: f["caught"] for f in check_store(self.h / "spikes/s3/tainted/store.py")}
        clean = {f["id"]: f["caught"] for f in check_store(self.h / "spikes/s3v2/fixtures/base_store.py")}
        self.assertTrue(tainted["failure_surfaces"])
        self.assertFalse(clean["failure_surfaces"])
        self.assertFalse(clean["write_persists"])
        self.assertFalse(any(v for v in clean.values()), f"clean store flagged: {clean}")

    def test_v2_refuses_without_blind_seal(self):
        r = run(["spikes/s3v2/run_s3_v2.py"], self.h)
        self.assertEqual(r.returncode, 2)
        self.assertIn("SEAL.json", r.stdout)

    def test_v2_wiring_with_stub(self):
        fx = self.h / "spikes/s3v2/fixtures"
        seeds = []
        for i in range(1, 7):
            (fx / f"w{i}.py").write_text((fx / "base_store.py").read_text())
            seeds.append({"id": f"w{i}", "kind": "code", "file": f"fixtures/w{i}.py", "what": "wiring"})
        for i in range(7, 11):
            (fx / f"w{i}.md").write_text("Wiring spec.")
            seeds.append({"id": f"w{i}", "kind": "non_code", "file": f"fixtures/w{i}.md", "what": "wiring"})
        seal = {"sealed_by": "test", "sealed_at": "now", "has_read_checks": False, "seeds": seeds,
                "controls": [{"id": "c1", "kind": "code", "file": "fixtures/base_store.py"}]}
        (self.h / "spikes/s3v2/SEAL.json").write_text(json.dumps(seal))
        r = run(["spikes/s3v2/run_s3_v2.py"], self.h, {"CYNQRA_S1_MODEL_CMD": cmd(self.h / "spikes/stub_model.py")})
        self.assertFalse((self.h / "spikes/s3v2/s3v2_report.json").exists(), r.stdout + r.stderr)
        self.assertTrue((self.h / "spikes/s3v2/s3v2_wiring_test.json").exists(), r.stdout + r.stderr)


class Run002(unittest.TestCase):
    def test_closed_run_cannot_be_rerun(self):
        h = copy_harness()
        try:
            for script in ("runner.py", "days_6_9.py", "day10_close.py"):
                r = run([script], h / "run_002")
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("closed", r.stderr + r.stdout)
            self.assertTrue((h / "run_002/workers/eng_b/outbox/store.py").exists())
        finally:
            shutil.rmtree(h.parent, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
