"""Failure shapes a real model produces and the scripted demo never does.

Each test drives the real engine, gateway, verification and deployment code with a source
whose answers are replaced the way a live model's could be: odd task ids, missing files,
an app that breaks the delivery contract, a provider outage mid run.
"""
from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request

from helpers import SCENARIO, TempDir, no_model_env, restore_env
from test_failure_paths import FaultySource, approve_until, start

from cynqra import deploy
from cynqra.engine import Engine, EngineError
from cynqra.intelligence import IntelligenceError, ModelSource, ScriptedSource, validate_plan
from cynqra.server import App, make_server
from cynqra.verification import run_unittests



def plan_copy() -> dict:
    return json.loads(json.dumps(SCENARIO["plan"]))


class PlanValidationTests(unittest.TestCase):
    def test_model_ids_are_renumbered_and_dependencies_follow(self):
        plan = plan_copy()
        for i, t in enumerate(plan["tasks"], start=1):
            t["id"] = f"task-{i}"
            t["dependencies"] = [f"task-{d[-1]}" for d in t["dependencies"]]
        plan["tasks"][2]["dependencies"] = "task-1, task-2"
        plan["tasks"][0]["budget"] = "ten"
        out = validate_plan(plan)
        self.assertEqual([t["id"] for t in out["tasks"]], [f"t_0{i}" for i in range(1, 7)])
        self.assertEqual(out["tasks"][2]["dependencies"], ["t_01", "t_02"])
        self.assertEqual(out["tasks"][0]["budget"], 10)

    def test_the_rubric_still_refuses_a_wrong_owner(self):
        plan = plan_copy()
        plan["tasks"][4]["owner_worker_id"] = "w_eng_a"
        with self.assertRaises(IntelligenceError):
            validate_plan(plan)

    def test_a_refused_plan_is_retried_once_with_the_reason(self):
        src = ModelSource.__new__(ModelSource)
        src.label = "stub"
        bad = plan_copy()
        bad["tasks"] = bad["tasks"][:-1]
        prompts = []
        answers = iter([bad, plan_copy()])

        def call(prompt, max_tokens=0):
            prompts.append(prompt)
            return next(answers), {"tokens_in": 1, "tokens_out": 1, "units": 1, "estimated": False, "label": "stub"}

        src._call = call
        plan, usage = src.plan({"product": "x"})
        self.assertEqual(len(plan["tasks"]), 6)
        self.assertIn("previous plan was refused", prompts[1])
        self.assertEqual(usage["units"], 2)


class WorkerReplyTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()
        self.src = FaultySource()
        self.e = None

    def tearDown(self):
        if self.e:
            self.e.close()
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_no_files_is_rework_not_a_stopped_run(self):
        self.src.faults["t_01"] = lambda i, r: {"result": "done", "summary": "forgot the files"} if i == 0 else r
        self.e = start(self.tmp.path, self.src)
        self.e.run_until_idle()
        self.assertNotEqual(self.e.meta["phase"], "stopped_error")
        self.assertEqual(self.e.task("t_01")["status"], "VERIFIED")
        self.assertEqual(self.e.task("t_01")["attempts"], 1)

    def test_writes_refused_three_times_escalate_instead_of_looping(self):
        self.src.faults["t_01"] = lambda i, r: {"result": "done", "files": {"../escape.md": "x"}}
        self.e = start(self.tmp.path, self.src)
        self.e.run_until_idle()
        t = self.e.task("t_01")
        self.assertEqual((t["status"], t["attempts"]), ("FAILED", 3))
        self.assertIn("writes kept being refused", self.e.pending_decisions()[0]["problem"])

    def test_nested_files_are_verified_and_integrated_at_their_path(self):
        def nested(i, r):
            if "files" not in r:
                return r
            r = dict(r)
            r["files"] = dict(r["files"], **{"static/help.txt": "Press Add to add a candidate."})
            return r
        self.src.faults["t_04"] = nested
        self.e = start(self.tmp.path, self.src)
        approve_until(self.e, "review_merge")
        self.assertEqual((self.e.paths["integration"] / "static" / "help.txt").read_text(), "Press Add to add a candidate.")
        self.assertIsNotNone(self.e.store.get("artifact", "t_04/static/help.txt"))

    def test_an_app_without_a_page_fails_the_delivery_contract_and_is_reworked(self):
        broken = []

        def no_root(i, r):
            if broken or "app.py" not in r.get("files", {}):
                return r
            broken.append(i)
            r = json.loads(json.dumps(r))
            r["files"]["app.py"] = r["files"]["app.py"].replace('if self.path in ("/", "/index.html")', 'if self.path == "/nowhere"')
            return r
        self.src.faults["t_04"] = no_root
        self.e = start(self.tmp.path, self.src)
        approve_until(self.e, "review_merge")
        verdicts = [v for v in self.e.store.all("verification") if v["task_id"] == "t_04"]
        self.assertEqual(verdicts[0]["verdict"], "REQUIRES_REWORK")
        self.assertIn("delivery_contract", verdicts[0]["checks"])
        self.assertEqual(verdicts[-1]["verdict"], "VERIFIED")

    def test_a_bad_assignment_retries_assignment_not_the_work(self):
        class BadAssign(ScriptedSource):
            calls = 0

            def assign(self, task, **kw):
                content, usage = super().assign(task, **kw)
                if task["id"] == "t_03" and BadAssign.calls == 0:
                    BadAssign.calls += 1
                    content = {k: v for k, v in content.items() if k != "acceptance_check"}
                return content, usage

        self.e = start(self.tmp.path, BadAssign())
        self.e.run_until_idle()
        self.e.decide(self.e.pending_decisions()[0]["id"], "approve")
        steps = self.e.run_until_idle()
        self.assertIn("retry", [s["did"] for s in steps])
        t = self.e.task("t_03")
        self.assertTrue(t.get("handoff"), "the retried assignment produced a Handoff before any work")

    def test_escalation_retry_goes_back_to_the_stage_that_failed(self):
        class NeverAssign(ScriptedSource):
            def assign(self, task, **kw):
                content, usage = super().assign(task, **kw)
                return ({k: v for k, v in content.items() if k != "acceptance_check"} if task["id"] == "t_03"
                        else content), usage

        self.e = start(self.tmp.path, NeverAssign())
        self.e.run_until_idle()
        self.e.decide(self.e.pending_decisions()[0]["id"], "approve")
        self.e.run_until_idle()
        d = self.e.pending_decisions()[0]
        self.assertEqual((d["kind"], d["task_id"]), ("escalation", "t_03"))
        self.e.decide(d["id"], "approve")
        self.assertEqual(self.e.task("t_03")["status"], "PLANNED")


class PromptContentTests(unittest.TestCase):
    """What the model is shown. The scripted demo ignores its inputs, so only this catches a blank prompt."""

    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_the_planner_sees_the_confirmed_objective(self):
        seen = {}

        class Spy(ScriptedSource):
            def plan(self, objective, note=""):
                seen.update(objective)
                return super().plan(objective, note)

        e = Engine(self.tmp.path, intelligence=Spy())
        e.create_company("Harbor Recruiting")
        e.draft_objective(SCENARIO["messy"])
        e.confirm_objective()
        e.close()
        self.assertEqual(seen.get("product"), SCENARIO["objective"]["product"])
        self.assertTrue(all(seen.get(k) for k in ("target_customer", "success_criteria", "constraints")))


class OutageTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_a_run_stopped_by_a_model_error_resumes_on_the_same_step(self):
        class Flaky(ScriptedSource):
            down = True

            def work(self, task, **kw):
                if task["id"] == "t_01" and Flaky.down:
                    raise IntelligenceError("HTTP 529 from provider: overloaded")
                return super().work(task, **kw)

        e = start(self.tmp.path, Flaky())
        self.assertEqual(e.run_until_idle()[-1]["did"], "error")
        self.assertEqual(e.meta["phase"], "stopped_error")
        with self.assertRaises(EngineError):
            e.decide("dec_nothing", "approve")
        Flaky.down = False
        e.resume()
        e.run_until_idle()
        self.assertEqual(e.task("t_01")["status"], "VERIFIED")
        with self.assertRaises(EngineError):
            e.resume()
        e.close()

    def test_a_failed_plan_returns_the_objective_to_draft(self):
        class NoPlan(ScriptedSource):
            ok = False

            def plan(self, objective, note=""):
                if not NoPlan.ok:
                    raise IntelligenceError("network error: timed out")
                return super().plan(objective, note)

        e = Engine(self.tmp.path, intelligence=NoPlan())
        e.create_company("Harbor Recruiting")
        e.draft_objective(SCENARIO["messy"])
        with self.assertRaises(IntelligenceError):
            e.confirm_objective()
        self.assertEqual(e.objective()["status"], "draft")
        self.assertIn("Planning failed", e.meta["notice"])
        NoPlan.ok = True
        e.confirm_objective()
        self.assertEqual(e.meta["phase"], "planning")
        self.assertEqual(len([x for x in e.store.events() if x["event_type"] == "worker.hired"]), 4)
        e.close()


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()
        self.app = App(self.tmp.path)
        self.srv = make_server(self.app, 0)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.app.close()
        self.tmp.cleanup()
        restore_env(self.saved)

    def post(self, path, body=None):
        req = urllib.request.Request(self.base + path, data=json.dumps(body or {}).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_unexpected_errors_are_a_500_with_a_message(self):
        def boom():
            raise TypeError("model sent a list where an object belongs")
        self.app.engine.step = boom
        code, body = self.post("/api/run/step")
        self.assertEqual(code, 500)
        self.assertIn("TypeError", body["error"])

    def test_resume_route_and_a_bad_auto_delay(self):
        self.assertEqual(self.post("/api/run/resume")[0], 400)
        self.assertEqual(self.post("/api/run/auto", {"on": True, "delay": "soon"})[0], 400)
        self.assertFalse(self.app.auto["on"])


class ToolTests(unittest.TestCase):
    def test_docstring_tests_are_still_recorded(self):
        tmp = TempDir()
        (tmp.path / "test_doc.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n    def test_a(self):\n        \"\"\"Explains itself.\"\"\"\n"
            "        self.assertTrue(False)\n    def test_b(self):\n        pass\n", encoding="utf-8")
        rep = run_unittests(tmp.path)
        tmp.cleanup()
        self.assertEqual(sorted(t["id"] for t in rep["tests"]), ["test_doc.test_a", "test_doc.test_b"])
        self.assertEqual(rep["failed"], ["test_doc.test_a"])

    def test_contract_check_reports_a_crashing_app_with_its_output(self):
        tmp = TempDir()
        (tmp.path / "app.py").write_text("raise SystemExit('no PORT handling here')\n", encoding="utf-8")
        res = deploy.contract_check(tmp.path, [])
        tmp.cleanup()
        self.assertFalse(res["ok"])
        self.assertIn("exited", res["why"])
        self.assertIn("no PORT handling here", res["why"])


if __name__ == "__main__":
    unittest.main()
