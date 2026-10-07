"""The tooling for roadmap item 1: prove objective-specific selection on real models.

The hosted examination carries a real objective through the control loop to delivery and reports, for every work
item, the controller's choice beside what the global prior alone would have chosen from the same snapshot, with the
verified outcomes. Here it runs on test doubles (an in-process server whose models answer from fake_model.py, one of
them writing broken code), so these tests prove the harness and the report, never the quality of a real model.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

from helpers import SCENARIO, TempDir, engine_to_running, no_model_env, restore_env
from test_objective_intelligence import ModelsServer, cand, raw, snap, supply_with

from cynqra import controller
from cynqra import run_hosted_examination as rhe


class PriorChoiceTests(unittest.TestCase):
    def test_the_prior_alone_is_computed_from_the_decisions_own_snapshot(self):
        tmp = TempDir()
        e = engine_to_running(tmp.path / "demo")
        try:
            # the registry's history favours a; this objective's verified work favours b
            history = [raw("a", "code", True, src="registry") for _ in range(6)] + \
                [raw("b", "code", False, src="registry") for _ in range(2)]
            mine = [raw("b", "code", True, objective_id="obj_x") for _ in range(8)] + \
                [raw("a", "code", False, objective_id="obj_x") for _ in range(8)]
            s = snap([cand("a"), cand("b")], history + mine, tier="HIGH")
            from cynqra.intelligence_layer import router
            self.assertEqual(router.select(s)["selected"], "b", "the objective's evidence decides")
            h = e.store.put_object("json", s)
            e.store.put(controller.KIND, "sd_test", {"decision_id": "sd_test", "evidence_snapshot": h,
                                                     "work_item_id": "t_09", "selection_mode": "exploit",
                                                     "selected_intelligence": {"id": "b"}})
            pc = controller.prior_choice(e, "sd_test")
            self.assertEqual((pc["chosen"], pc["prior"], pc["agrees"]), ("b", "a", False))
            self.assertEqual(pc["objective_evidence_items"], 16)
            self.assertEqual(controller.prior_choice(e, "sd_test"), pc, "deterministic, from the snapshot alone")
        finally:
            e.close()
            tmp.cleanup()


class HarnessTests(unittest.TestCase):
    def test_providers_can_be_combined_and_claude_left_out(self):
        self.assertIsNone(rhe.parse_providers("all"))
        self.assertEqual(rhe.parse_providers("google+nvidia"), ["google", "nvidia"])
        with self.assertRaises(SystemExit):
            rhe.parse_providers("google+someone")
        with mock.patch.dict(os.environ, {}, clear=False):
            for k in ("GEMINI_API_KEY", "NVIDIA_API_KEY", "ANTHROPIC_API_KEY"):
                os.environ.pop(k, None)
            with self.assertRaises(SystemExit) as ctx:
                rhe.main(["--provider", "google+nvidia"])
            self.assertIn("GEMINI_API_KEY or NVIDIA_API_KEY", str(ctx.exception))

    def test_the_examination_founder_never_spends_more_or_answers_for_a_person(self):
        self.assertEqual(rhe.examination_answer({"kind": "budget_breaker"}), "reject")
        self.assertEqual(rhe.examination_answer({"kind": "provider_account"}), "reject")
        for kind in ("approve_roadmap", "review_merge", "deploy", "accept_delivery", "escalation", "provider_outage"):
            self.assertEqual(rhe.examination_answer({"kind": kind}), "approve", kind)


class ToDeliveryTests(unittest.TestCase):
    """The whole path the hosted job takes with an objective and --to-delivery, on test doubles."""

    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()
        self.srv = ModelsServer()
        self.srv.broken.add("Sloppy")
        self.sup = supply_with(self.tmp.path, [("Steady", 0.2), ("Sloppy", 0.4), ("Careful", 0.6)], self.srv)

    def tearDown(self):
        self.sup.close()
        self.srv.close()
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_an_objective_to_delivery_with_its_selection_report(self):
        lines = []
        out = rhe.objective_run(self.sup, self.tmp.path / "run", SCENARIO["messy"], 5.0, to_delivery=True,
                                max_minutes=10, log=lines.append)
        self.assertIsNone(out.get("error"), out.get("error"))
        self.assertEqual(out["stage"], "accepted", out.get("notice"))
        self.assertEqual(out["lifecycle"], "OBJECTIVE_CLOSED")
        self.assertTrue(all(d["replayed"] for d in out["decisions"]))
        self.assertTrue(any("examination founder: approve accept_delivery" in x for x in lines))
        rep = out["selection_report"]
        items = rep["items"]
        self.assertTrue(items and all(x["prior_choice"] for x in items), "every work item has its prior choice")
        self.assertTrue(all(x["verified"] for x in items), "delivered: every work item verified")
        code = [x for x in items if x["kind"] == "code"]
        self.assertTrue(code and all(x["first_choice"] != "sloppy" for x in code),
                        "calibration kept the model that writes broken code off the code")
        head = rep["calibration_head_to_head"]
        self.assertTrue(head and all(h["verdicts"] for h in head))
        s = rep["summary"]
        self.assertEqual(s["work_items"], len(items))
        self.assertEqual(s["agree_with_prior"] + s["differ_from_prior"], len(items))
        self.assertIn("sloppy", s["evidence_by_intelligence"], "the failed calibration trials are on the record")
        summary = rhe.objective_summary(out)
        self.assertEqual(summary["journey"]["ended"], "accepted")
        self.assertEqual(summary["journey"]["refused"], [])

    def test_the_examination_founder_submits_again_once_after_a_failed_step(self):
        # real run 37013721424: "Objective intelligence failed: ... Submit again to retry." stopped every objective
        from cynqra import synthesis
        from cynqra.intelligence import IntelligenceError
        real, calls = synthesis.propose, []

        def flaky(run, note=""):
            calls.append(1)
            if len(calls) == 1:
                raise IntelligenceError("a Specialist needs its field")
            return real(run, note)

        lines = []
        with mock.patch.object(synthesis, "propose", side_effect=flaky):
            out = rhe.objective_run(self.sup, self.tmp.path / "again", SCENARIO["messy"], 5.0, to_delivery=True,
                                    max_minutes=10, log=lines.append)
        self.assertEqual(out["stage"], "accepted", out.get("error"))
        self.assertTrue(any("examination founder: submit again" in x for x in lines), lines[:5])
        self.assertEqual(len(calls), 2, "submitted again once, not more")

    def test_the_examination_founder_resumes_once_after_the_roadmap_failed(self):
        # real run 37028315336: "The roadmap failed: plan needs exactly 1 review_merge task. ... Resume to try again."
        # stopped two objectives at the plan, after the model's one retry with the reason
        from cynqra import planner
        from cynqra.intelligence import IntelligenceError
        real, calls = planner.plan, []

        def flaky(run, note="", cycle=1):
            calls.append(1)
            if len(calls) == 1:
                raise IntelligenceError("plan needs exactly 1 review_merge task")
            return real(run, note, cycle=cycle)

        lines = []
        with mock.patch.object(planner, "plan", side_effect=flaky):
            out = rhe.objective_run(self.sup, self.tmp.path / "resume", SCENARIO["messy"], 5.0, to_delivery=True,
                                    max_minutes=10, log=lines.append)
        self.assertEqual(out["stage"], "accepted", out.get("error"))
        self.assertTrue(any("examination founder: resume" in x for x in lines), lines[:5])
        self.assertEqual(len(calls), 2, "resumed once, not more")

    def test_a_second_failure_after_resuming_ends_the_objective_as_it_happened(self):
        from cynqra import planner
        from cynqra.intelligence import IntelligenceError
        with mock.patch.object(planner, "plan", side_effect=IntelligenceError("plan needs exactly 1 deploy task")):
            out = rhe.objective_run(self.sup, self.tmp.path / "twice", SCENARIO["messy"], 5.0, to_delivery=True,
                                    max_minutes=10, log=lambda *_: None)
        self.assertEqual(out["stage"], "roadmap")
        self.assertIn("plan needs exactly 1 deploy task", out["error"])

    def test_work_waiting_for_a_provider_is_waited_for_up_to_the_time_limit(self):
        # real run 37564551165: every task waited on one rate-limited provider; the examination stopped after ten
        # waits of 30 seconds with 44 of its 70 minutes left
        class Waiting:
            meta = {"phase": "running"}

            def __init__(self):
                self.waits = 0

            def run_until_idle(self, max_steps=10):
                return []

            def pending_decisions(self):
                return []

            def tasks(self):
                self.waits += 1
                if self.waits > 25:  # the provider answers again after 25 waits, and the work is delivered
                    self.meta = {"phase": "accepted"}
                return [{"status": "WAITING"}]

            def step(self):
                return {"did": "idle"}

        e = Waiting()
        out = rhe.journey(e, max_minutes=0.5, log=lambda *_: None, idle_wait=0.01)
        self.assertEqual(out["ended"], "accepted")
        self.assertGreater(e.waits, 10)
        # and the time limit still bounds the wait
        e = Waiting()
        e.tasks = lambda: [{"status": "WAITING"}]
        self.assertEqual(rhe.journey(e, max_minutes=0.01, log=lambda *_: None, idle_wait=0.05)["ended"], "time_limit")

    def test_an_examination_limited_to_some_providers_reaches_no_other(self):
        # real run 37564551165, limited to NVIDIA, Groq and Mistral: with nothing available the engine connected
        # what the environment names, Gemini among them, and qualified Gemini 3 Flash on the spot
        import os
        from cynqra.intelligence_layer.adapters import OpenAICompatibleAdapter
        env = {"GEMINI_API_KEY": "g", "NVIDIA_API_KEY": "n", "GROQ_API_KEY": "q", "MISTRAL_API_KEY": "m",
               "META_API_KEY": "x"}
        with mock.patch.dict(os.environ, env, clear=False):
            gone = rhe.limit_environment(["nvidia", "groq", "mistral"])
            self.assertEqual(sorted(gone), ["GEMINI_API_KEY", "META_API_KEY"])
            names = {s["name"] for s in OpenAICompatibleAdapter().environment_specs(None)}
            self.assertFalse({"Google Gemini (environment)", "Meta (environment)"} & names, names)
            self.assertTrue({"NVIDIA (environment)", "Groq (environment)", "Mistral (environment)"} <= names)

    def test_the_live_view_prints_every_saved_event_once_in_order(self):
        import re
        from cynqra.db import Store
        lines = []
        out = rhe.objective_run(self.sup, self.tmp.path / "live", SCENARIO["messy"], 5.0, to_delivery=True,
                                max_minutes=10, log=lines.append, live=True)
        self.assertEqual(out["stage"], "accepted", out.get("error"))
        shown = [int(m.group(1)) for x in lines if (m := re.match(r"  live #(\d+) ", x))]
        s = Store(str(self.tmp.path / "live" / "cynqra.db"))
        try:
            saved = [e["seq"] for e in s.events()]
            types = {e["seq"]: e["event_type"] for e in s.events()}
        finally:
            s.close()
        self.assertEqual(shown, saved, "every saved event, once, in order; nothing that was not saved")
        live = [x for x in lines if x.startswith("  live #")]
        for name in ("objective.created", "intelligence.selection.committed", "verification.completed",
                     "objective.completed"):
            self.assertTrue(any(f" {name} " in x for x in live), name)
        self.assertTrue(all(f" {types[n]} " in x for n, x in zip(shown, live)))


if __name__ == "__main__":
    unittest.main()
