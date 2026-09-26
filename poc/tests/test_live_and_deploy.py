"""Live mode wiring (A15), the deployment service (A12) and the demo product's own tests."""
from __future__ import annotations

import filecmp
import os
import shutil
import unittest
from pathlib import Path

from helpers import POC, TempDir, engine_to_running, fake_model_cmd, no_model_env, restore_env, run_journey

from cynqra import deploy
from cynqra.engine import Engine
from cynqra.intelligence import IntelligenceError, ModelSource, validate_plan
from cynqra.verification import run_unittests

FILES = POC / "scenarios" / "candidate_tracker" / "files"


class LiveModeTests(unittest.TestCase):  # A15
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_live_needs_a_model(self):
        with self.assertRaises(IntelligenceError):
            ModelSource()
        e = Engine(self.tmp.path)
        with self.assertRaises(IntelligenceError):
            e.create_company("X", "live")
        self.assertEqual(e.meta["phase"], "new", "nothing is written when live mode cannot start")
        e.close()

    def test_live_path_end_to_end_through_the_adapter(self):
        os.environ["CYNQRA_S1_MODEL_CMD"] = fake_model_cmd()
        e = engine_to_running(self.tmp.path, mode="live")
        run_journey(e)
        self.assertEqual(e.meta["phase"], "accepted")
        calls = e.store.all("call")
        self.assertTrue(calls)
        self.assertTrue(all(c["label"] == "shell command" for c in calls))
        self.assertTrue(all(c["estimated"] for c in calls), "command token counts are marked estimated")
        self.assertEqual([t["status"] for t in e.tasks()], ["VERIFIED"] * 6)
        e.close()

    def test_a_model_error_stops_the_run_and_invents_nothing(self):
        os.environ["CYNQRA_S1_MODEL_CMD"] = fake_model_cmd()
        e = engine_to_running(self.tmp.path, mode="live")
        os.environ["CYNQRA_S1_MODEL_CMD"] = fake_model_cmd(fail=True)
        e._intel = None
        r = e.run_until_idle()[-1]
        self.assertEqual(r["did"], "error")
        self.assertEqual(e.meta["phase"], "stopped_error")
        self.assertIn("Nothing was invented", e.meta["notice"])
        self.assertEqual(e.tasks()[0]["status"], "ASSIGNED")
        e.close()

    def test_plan_rules_are_the_platforms(self):
        good = {"tasks": [
            {"id": "t_01", "workstream_id": "w", "kind": "code", "owner_worker_id": "w_eng_a", "title": "a", "risk_tier": "HIGH"},
            {"id": "t_02", "workstream_id": "w", "kind": "review_merge", "owner_worker_id": "w_cto", "title": "b", "dependencies": ["t_01"]},
            {"id": "t_03", "workstream_id": "w", "kind": "deploy", "owner_worker_id": "w_cto", "title": "c", "dependencies": ["t_02"]}]}
        p = validate_plan(good)
        self.assertEqual(p["tasks"][0]["risk_tier"], "LOW", "the model cannot set its own risk tier")
        bad_owner = {"tasks": [dict(good["tasks"][0], owner_worker_id="w_pm")] + good["tasks"][1:]}
        for bad in ({"tasks": []}, bad_owner, {"tasks": good["tasks"][:2]},
                    {"tasks": [dict(good["tasks"][0], dependencies=["t_09"])] + good["tasks"][1:]}):
            with self.assertRaises(IntelligenceError):
                validate_plan(bad)

    def test_adapter_copy_matches_the_spike_adapter(self):
        spike = POC.parent / "02_harness" / "spikes" / "model_adapter.py"
        if not spike.exists():
            self.skipTest("POC shipped without the harness")
        self.assertTrue(filecmp.cmp(spike, POC / "cynqra" / "model_adapter.py", shallow=False))


class DeployServiceTests(unittest.TestCase):  # A12
    def setUp(self):
        self.tmp = TempDir()
        self.main = self.tmp.path / "main"
        self.main.mkdir()
        for f in ("t_03/store.py", "t_03/test_store.py", "t_04/app.py", "t_04/index.html", "t_04/test_app.py", "t_04/smoke.json"):
            shutil.copy(FILES / f, self.main)

    def tearDown(self):
        deploy.stop_all()
        self.tmp.cleanup()

    def test_build_to_verify_then_live(self):
        import json
        checks = json.loads((self.main / "smoke.json").read_text())["checks"]
        pre = deploy.build_to_verify(self.main, self.tmp.path / "rel", "release_1", checks)
        self.assertTrue(pre["ok"], pre["log"])
        self.assertEqual([x["stage"] for x in pre["log"]], ["BUILD", "TEST", "PACKAGE", "PREVIEW", "VERIFY"])
        live = deploy.deploy_live(Path(pre["folder"]), self.tmp.path / "live", checks, None)
        self.assertTrue(live["ok"], live["log"])
        self.assertEqual(live["log"][-1]["stage"], "LIVE")
        self.assertEqual({r["check"].split()[0] for r in live["log"][-2]["results"]}, {"GET"}, "live smoke is read only")

    def test_missing_app_fails_the_build(self):
        (self.main / "app.py").unlink()
        pre = deploy.build_to_verify(self.main, self.tmp.path / "rel", "r", [])
        self.assertFalse(pre["ok"])
        self.assertEqual(pre["log"][-1]["stage"], "BUILD")

    def test_failing_tests_stop_the_build(self):
        shutil.copy(FILES / "t_03/attempt1/store.py", self.main / "store.py")
        pre = deploy.build_to_verify(self.main, self.tmp.path / "rel", "r", [])
        self.assertFalse(pre["ok"])
        self.assertEqual(pre["log"][-1]["stage"], "TEST")

    def test_failed_smoke_rolls_back_and_the_old_release_keeps_serving(self):
        old = deploy.deploy_live(self.main, self.tmp.path / "live_old", [], None)
        self.assertTrue(old["ok"])
        bad_checks = [{"method": "GET", "path": "/does-not-exist", "expect": 200}]
        new = deploy.deploy_live(self.main, self.tmp.path / "live_new", bad_checks, old["proc"])
        self.assertFalse(new["ok"])
        self.assertEqual(new["log"][-1]["stage"], "ROLLBACK")
        self.assertIs(new["proc"], old["proc"])
        self.assertTrue(deploy.health(old["url"], wait=3)["ok"], "previous release still serving")


class DemoProductTests(unittest.TestCase):
    """The product the demo organization builds is real code with real tests."""

    def setUp(self):
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_final_product_passes_all_sixteen(self):
        for f in ("t_03/store.py", "t_03/test_store.py", "t_04/app.py", "t_04/index.html", "t_04/test_app.py"):
            shutil.copy(FILES / f, self.tmp.path)
        r = run_unittests(self.tmp.path)
        self.assertTrue(r["passed"], r["output"])
        self.assertEqual(r["ran"], 16)


if __name__ == "__main__":
    unittest.main()
