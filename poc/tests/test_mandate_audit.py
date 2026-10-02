"""What an audit of the P1 mandate against the code found missing, kept fixed.

Each test names the mandate section it holds the code to. Like the rest of the suite these use test doubles: they
prove the control plane's mechanics, never the quality of a real model.
"""
from __future__ import annotations

import http.client
import io
import unittest
import urllib.error
from unittest import mock

from helpers import TempDir, engine_to_running, no_model_env, restore_env, run_journey
from test_objective_intelligence import POL, ModelsServer, cand, ctx, live_engine, raw, snap, supply_with

from cynqra import attribution as attr
from cynqra import calibration, controller, execution, model_adapter, objective, objective_evidence as oe, policies
from cynqra import verifier
from cynqra.intelligence_layer import evidence as ev_model
from cynqra.intelligence_layer import router

BODIES = {k: v["body"] for k, v in POL.items()}


class ProviderFailureTests(unittest.TestCase):
    """Mandate 16: HTTP 408/409/425/429, 5xx, timeouts, dropped connections are the provider's side."""

    def test_425_and_a_dropped_connection_are_retried_and_never_the_models(self):
        self.assertIn(425, model_adapter.RETRY_STATUS)
        too_early = urllib.error.HTTPError("https://x", 425, "Too Early", {}, io.BytesIO(b"too early"))

        class Reply:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"ok": 1}'

        with mock.patch.object(model_adapter._OPENER, "open", side_effect=[too_early, Reply()]):
            self.assertEqual(model_adapter._post("https://x", {}, {}, waits=(0.0,)), {"ok": 1})
        for exc in (http.client.RemoteDisconnected("Remote end closed connection without response"),
                    http.client.IncompleteRead(b"")):
            with mock.patch.object(model_adapter._OPENER, "open", side_effect=exc):
                with self.assertRaises(model_adapter._Retryable):
                    model_adapter._post_once("https://x", b"{}", {})
        self.assertEqual(attr.call_failure("HTTP 425 from provider: too early")["kind"], "provider")
        self.assertEqual(attr.call_failure("network error: RemoteDisconnected: closed")["kind"], "network")

    def test_an_empty_account_is_the_accounts_never_the_models(self):
        """A real run: Anthropic answers an empty balance with HTTP 400. It is the account's, the founder is asked to
        add credit, and a probe that met it is inconclusive, never a failed qualification."""
        from cynqra import probe
        low = ('HTTP 400 from provider: {"type":"error","error":{"type":"invalid_request_error","message":"Your credit '
               'balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase '
               'credits."}}')
        self.assertEqual(attr.diagnose(low), "no_credit")
        self.assertEqual(attr.call_failure(low)["kind"], "account")
        self.assertEqual(attr.diagnose('HTTP 400 from provider: {"message":"max_tokens is too large"}'), "outage",
                         "a 400 that says nothing about money stays the provider's side")
        self.assertEqual(probe._provider_failure_kind(low), "account_unavailable")
        self.assertEqual(probe._provider_failure_kind("HTTP 503 from provider: overloaded"), "provider_unavailable")
        self.assertEqual(probe._provider_failure_kind("something nobody has seen before"), "provider_unavailable",
                         "an unrecognised failure is the cautious reading: unknown, not the model's")
        self.assertEqual(probe._provider_failure_kind("the model did not return a JSON object"), "model_error")


class TraceabilityTests(unittest.TestCase):
    """Mandate 5: every record names its objective and the version it was made under."""

    def test_verifications_and_calls_keep_the_version_they_were_made_under(self):
        tmp = TempDir()
        e = engine_to_running(tmp.path / "demo")
        try:
            run_journey(e)
            oid = e.objective()["objective_id"]
            for kind in ("verification", "call"):
                recs = e.store.all(kind)
                self.assertTrue(recs, kind)
                self.assertTrue(all(r.get("objective_id") == oid and isinstance(r.get("objective_version"), int)
                                    for r in recs), kind)
            later = {"attempt_objective_version": 1, "objective_version": 2}
            self.assertEqual(controller.stamp(e, later)["objective_version"], 1,
                             "an attempt keeps the version it started under, whatever the task says later")
        finally:
            e.close()
            tmp.cleanup()


class CapabilityFitTests(unittest.TestCase):
    """Mandate 46: what the work needs, cognitive or runtime/protocol, is a hard constraint; unknown is not unable."""

    def test_a_stated_inability_excludes_and_silence_never_does(self):
        text_only = cand("a", input_modalities=["text"])
        sees = cand("b", input_modalities=["text", "image"])
        silent = cand("c", input_modalities=[])
        work = {"kinds": ["code"], "requires": ["vision"], "min_context": 0, "output_tokens": 0}
        s = snap([text_only, sees, silent], [])
        why = {c["id"]: [v["constraint"] for v in router.hard_constraints(c, work, s)] for c in (text_only, sees, silent)}
        self.assertEqual(why, {"a": ["capability"], "b": [], "c": []})
        self.assertTrue(router.capability(cand("d", capabilities=["Tool use"]), "tool_calling"))
        self.assertIsNone(router.capability(cand("e", tools=False), "tool_calling"),
                          "a registry default is not a statement that the model cannot")

    def test_the_work_carries_its_needs_into_the_decision(self):
        tmp = TempDir()
        e = engine_to_running(tmp.path / "demo")
        try:
            t = next(t for t in e.tasks() if t["kind"] == "code")
            t["requires"] = ["vision"]
            self.assertEqual(controller.work_for_task(e, t)["requires"], ["vision"])
            d = controller.decide(e, controller.work_for_task(e, t), "probe")
            self.assertIn("capability", d["hard_constraints"])
            self.assertNotIn("budget_headroom", d["hard_constraints"], "only what the router enforces is listed")
        finally:
            e.close()
            tmp.cleanup()


class RelevanceAndIsolationTests(unittest.TestCase):
    def test_the_same_requirement_is_more_relevant_than_the_same_kind_alone(self):
        """Mandate 13: relevance follows the workstream and the acceptance criteria."""
        other_role = raw("m", "code", True, role="CTO") | {"requirement_ids": ["R1"]}
        near = ev_model.normalize(other_role, ctx(role="Engineer", requirement_ids=["R1"]), BODIES, "code")
        far = ev_model.normalize(other_role, ctx(role="Engineer", requirement_ids=["R2"]), BODIES, "code")
        self.assertEqual((near["match"], near["relevance"]), ("same_requirement", 0.85))
        self.assertEqual((far["match"], far["relevance"]), ("same_kind_other_role", 0.7))

    def test_another_workspace_is_isolated_by_policy(self):
        """Mandate 53: objective evidence never crosses workspaces; other work only where the policy shares it."""
        here = ctx(workspace_id="ws_a")
        other = raw("m", "code", True, src="registry") | {"workspace_id": "ws_b"}
        self.assertEqual(ev_model.normalize(other, here, BODIES, "code")["excluded"], "workspace_isolation")
        shared = dict(BODIES, isolation=dict(BODIES["isolation"], historical_scope="tenant"))
        self.assertIsNone(ev_model.normalize(other, here, shared, "code")["excluded"])
        probe = other | {"source": "probe"}
        self.assertIsNone(ev_model.normalize(probe, here, BODIES, "code")["excluded"], "qualification is global")
        mine = raw("m", "code", True, objective_id="obj_x") | {"workspace_id": "ws_b"}
        self.assertEqual(ev_model.normalize(mine, here, shared, "code")["excluded"], "workspace_isolation")


class PolicyAuthorityTests(unittest.TestCase):
    """Mandate 57: the rules live in the policy catalogue, not in module constants."""

    def test_rework_and_cut_off_limits_come_from_the_policies(self):
        self.assertEqual(verifier.MAX_ATTEMPTS, policies.body("verification")["max_attempts"])
        self.assertEqual(execution.MAX_CUT_OFFS, policies.body("replacement")["max_cut_offs"])
        self.assertEqual(policies.body("evidence")["autonomy_success"]["human_override"], 0.0)


class LifecycleAndInterventionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.e = engine_to_running(self.tmp.path / "demo")

    def tearDown(self):
        self.e.close()
        self.tmp.cleanup()

    def _in_flight(self) -> dict:
        for _ in range(40):
            open_ = [t for t in self.e.tasks() if t.get("attempt_open") and t["status"] != "VERIFIED"]
            if open_ and controller.producer(self.e, open_[0])[0]:
                return open_[0]
            self.e.step()
        self.fail("no work in flight")

    def test_a_cancelled_objective_cancels_its_work_and_fails_no_one(self):
        """Mandate 49: work in flight when the objective is cancelled is recorded as cancelled, never failed."""
        t = self._in_flight()
        self.assertTrue(objective.transition(self.e, "OBJECTIVE_CANCELLED", "the founder stopped the run"))
        evs = [x for x in oe.query(self.e.store, objective_id=self.e.objective()["objective_id"], tenant_id="local",
                                   work_item_id=t["id"]) if (x.get("failure") or {}).get("kind") == "cancelled"]
        self.assertEqual(len(evs), 1)
        self.assertEqual((evs[0]["verified"], evs[0]["clean"]), (None, False))
        self.assertFalse(self.e.task(t["id"]).get("attempt_open"))

    def test_a_founder_directed_stand_in_is_labelled_and_keeps_its_credit(self):
        """Mandate 50: who chose the intelligence is recorded apart from what the intelligence did."""
        t = self._in_flight()
        mid, _ = controller.producer(self.e, t)
        self.assertEqual(controller.autonomy_of(self.e, t)[0], "autonomous")
        self.e.store.put("replacement", "rep_test", {"id": "rep_test", "worker_id": t["owner_worker_id"], "to": mid,
                                                     "from": "x", "temporary": True, "active": True,
                                                     "human_directed": True, "authority": "your approval"})
        autonomy, ids = controller.autonomy_of(self.e, t)
        self.assertEqual(autonomy, "human_directed_reroute")
        self.assertIn("rep_test", ids)
        self.assertEqual(policies.body("evidence")["autonomy_success"]["human_directed_reroute"], 1.0)

    def test_the_constraint_model_keeps_each_kind_of_rule_apart(self):
        """Mandate 44: hard constraints, mandatory requirements, optimization dimensions, preferences, risk
        thresholds and acceptance criteria are distinct."""
        objective.set_constraints(self.e, {"deadline": "before December", "technology": "Python",
                                           "geography": "data stays in the EU"})
        cm = objective.constraint_model(self.e)
        self.assertEqual(set(cm) - {"objective_id", "objective_version"},
                         {"hard_constraints", "mandatory_requirements", "optimization_dimensions", "preferences",
                          "risk_thresholds", "acceptance_criteria"})
        hard = {h["id"] for h in cm["hard_constraints"]}
        self.assertTrue({"qualified", "capability", "budget_cap", "geography"} <= hard)
        self.assertEqual({p["id"] for p in cm["preferences"]}, {"deadline", "technology"})
        self.assertTrue(cm["mandatory_requirements"])
        self.assertEqual(set(cm["risk_thresholds"]["by_tier"]), {"LOW", "MEDIUM", "HIGH"})
        self.assertTrue(self.e.requirements()["constraint_model"]["acceptance_criteria"])


class CalibrationCoverageTests(unittest.TestCase):
    """Mandate 41: calibration never settles without acceptance coverage, and its task coverage is on record."""

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

    def test_coverage_is_recorded_and_required(self):
        e = live_engine(self.tmp.path / "run", self.sup)
        try:
            p = e.store.get(calibration.KIND, calibration.plan_id(e))
            cov = p["coverage"]
            accounted = set(cov["calibrated"]) | set(cov["skipped"]) | set(cov["not_verifiable_before_execution"]) \
                | set(cov["beyond_class_limit"])
            self.assertEqual(accounted, set(cov["work_classes"]), "every class of open work is accounted for")
            self.assertTrue(cov["calibrated"])
            for it in p["items"]:
                why = (p["stopping"].get(it["item_id"]) or {}).get("reason") or ""
                if why in ("candidate_separation", "evidence_sufficiency"):
                    self.assertTrue(any(calibration.covered(it, p["trials"], c) for c in it["candidates"]), it["item_id"])
            done = [x for x in e.store.events() if x["event_type"] == "intelligence.calibration.completed"][-1]
            self.assertIn("coverage", done["payload"])
            code = next(i for i in p["items"] if i["kind"] == "code" and not i.get("skipped"))
            stop, why, todo = calibration._stop(e, code, 1, 2, policies.body("calibration"), trials=[])
            self.assertFalse(stop, "no verified trial yet: the best is not settled on")
            self.assertTrue(todo)
            stop, why, _ = calibration._stop(e, code, 2, 2, policies.body("calibration"), trials=[])
            self.assertTrue(stop)
            self.assertIn("acceptance criteria", why)
        finally:
            e.close()


if __name__ == "__main__":
    unittest.main()
