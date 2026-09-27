"""Live mode wiring (A15), the deployment service (A12) and the demo product's own tests."""
from __future__ import annotations

import filecmp
import os
import shutil
import unittest
from pathlib import Path

from helpers import M1_ROLES, POC, TempDir, engine_to_running, fake_model_cmd, no_model_env, restore_env, run_journey

from cynqra import deploy, planner, roles
from cynqra.engine import Engine, EngineError
from cynqra.intelligence import IntelligenceError
from cynqra.testrunner import run_unittests

FILES = POC / "scenarios" / "candidate_tracker" / "files"
RESTAURANT = POC / "scenarios" / "restaurant_forecast" / "files"


class LiveModeTests(unittest.TestCase):  # A15
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_live_needs_a_model(self):
        e = Engine(self.tmp.path)
        with self.assertRaises(EngineError):
            e.create_company("X", "live")
        self.assertEqual(e.meta["phase"], "new", "nothing is written when live mode cannot start")
        e.close()

    def test_a_live_run_reopens_after_its_model_is_gone(self):
        os.environ["CYNQRA_S1_MODEL_CMD"] = fake_model_cmd()
        e = engine_to_running(self.tmp.path, mode="live")
        e.close()
        del os.environ["CYNQRA_S1_MODEL_CMD"]
        e = Engine(self.tmp.path)  # the app restarts without a model: the run still opens
        self.assertEqual(e.meta["phase"], "running")
        self.assertIn(e.step()["did"], ("assigned", "model_error_retry", "escalated"))
        e.close()

    def test_live_path_end_to_end_through_the_adapter(self):
        os.environ["CYNQRA_S1_MODEL_CMD"] = fake_model_cmd()
        e = engine_to_running(self.tmp.path, mode="live")
        run_journey(e)
        self.assertEqual(e.meta["phase"], "accepted")
        calls = e.store.all("call")
        self.assertTrue(calls)
        self.assertTrue(all(c["label"] == "shell command" for c in calls))
        self.assertTrue(all(c["model_id"] == "shell-command" for c in calls),
                        "the environment's model was connected, registered and bound like any other")
        self.assertEqual({e.model_of(w["id"]) for w in e.workers()}, {"shell-command"})
        conn = e.supply.connections.all()[0]
        self.assertEqual((conn["type"], conn["server"], conn["origin"]), ("local", "command", "environment"))
        self.assertTrue(all("model_id" not in w and "api_key" not in w for w in e.workers()),
                        "a worker record holds no model and no credential")
        self.assertTrue(all(c["estimated"] for c in calls), "command token counts are marked estimated")
        self.assertEqual([t["status"] for t in e.tasks()], ["VERIFIED"] * 6)
        e.close()

    def test_a_failing_model_with_no_alternative_waits_and_invents_nothing(self):
        os.environ["CYNQRA_S1_MODEL_CMD"] = fake_model_cmd()
        e = engine_to_running(self.tmp.path, mode="live")
        os.environ["CYNQRA_S1_MODEL_CMD"] = fake_model_cmd(fail=True)
        steps = [r["did"] for r in e.run_until_idle()]
        self.assertEqual(steps[:2], ["assigned", "model_error_retry"], "one failed call is retried")
        self.assertIn("waiting", steps, "a model that stopped answering is waited for, not replaced")
        self.assertIn("stopped", e.store.events()[-1]["event_type"] + " ".join(
            x["event_type"] for x in e.store.events()), "the stop is diagnosed and recorded")
        t = e.task("t_01")
        self.assertEqual((t["status"], t["outputs"]), ("WAITING", []))
        self.assertFalse(any((e.paths["workspaces"] / "w_pm" / "t_01" / "out").iterdir()), "nothing was invented")
        self.assertFalse(e.store.all("replacement"))
        os.environ["CYNQRA_S1_MODEL_CMD"] = fake_model_cmd()  # the model is back, and the wait is over
        t["waiting"]["until"] = 0
        e.save_task(t)
        run_journey(e)
        self.assertEqual(e.meta["phase"], "accepted")
        e.close()

    def test_plan_rules_are_the_platforms(self):
        good = {"tasks": [
            {"id": "t_01", "workstream_id": "w", "kind": "code", "owner_worker_id": "w_eng_a", "title": "a", "risk_tier": "HIGH"},
            {"id": "t_02", "workstream_id": "w", "kind": "review_merge", "owner_worker_id": "w_cto", "title": "b", "dependencies": ["t_01"]},
            {"id": "t_03", "workstream_id": "w", "kind": "deploy", "owner_worker_id": "w_cto", "title": "c", "dependencies": ["t_02"]}]}
        fixture = roles.instantiate(M1_ROLES)
        p = planner.enrich(planner.validate_plan(good, fixture), fixture)
        self.assertEqual(p["tasks"][0]["risk_tier"], "LOW", "the model cannot set its own risk tier")
        self.assertEqual(p["tasks"][0]["tools"], ["write_file", "run_tests"], "tools come from the task type")
        self.assertTrue(p["milestones"][0]["derived"], "milestones the model left out are derived and marked")
        bad_owner = {"tasks": [dict(good["tasks"][0], owner_worker_id="w_pm")] + good["tasks"][1:]}
        for bad in ({"tasks": []}, bad_owner, {"tasks": good["tasks"][:2]},
                    {"tasks": [dict(good["tasks"][0], dependencies=["t_09"])] + good["tasks"][1:]}):
            with self.assertRaises(IntelligenceError):
                planner.validate_plan(bad, fixture)

    def test_adapter_copy_matches_the_spike_adapter(self):
        spike = POC.parent / "archive" / "02_harness" / "spikes" / "model_adapter.py"
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

    def test_the_restaurant_product_passes_its_twenty(self):
        for f in ("t_07/attempt2/forecast.py", "t_07/test_forecast.py", "t_08/data.py", "t_08/test_data.py",
                  "t_09/app.py", "t_09/index.html", "t_09/test_app.py", "t_11/test_acceptance.py"):
            shutil.copy(RESTAURANT / f, self.tmp.path)
        r = run_unittests(self.tmp.path)
        self.assertTrue(r["passed"], r["output"])
        self.assertEqual(r["ran"], 20)


if __name__ == "__main__":
    unittest.main()
