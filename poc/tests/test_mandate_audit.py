"""What an audit of the P1 mandate against the code found missing, kept fixed.

Each test names the mandate section it holds the code to. Like the rest of the suite these use test doubles: they
prove the control plane's mechanics, never the quality of a real model.
"""
from __future__ import annotations

import http.client
import json
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


class ProviderBackOffTests(unittest.TestCase):
    """Real run 36972596704: a rate-limited provider on a fixed ten-minute wait took seven workers back three times,
    each refusing again within two minutes. The wait now doubles each time it goes down without answering between."""

    def test_the_wait_doubles_each_time_it_goes_down_again_and_an_answer_resets_it(self):
        from cynqra.intelligence_layer import registry as reg_mod
        tmp = TempDir()
        srv = ModelsServer()
        sup = supply_with(tmp.path, [("Busy", 0.0)], srv)
        try:
            reg = sup.registry
            mid = reg.models()[0]["id"]
            clock = [1_000_000.0]

            def call(error=""):
                reg.record_call(mid, role="Engineer", purpose="work", task_kind="code", usage={}, run_id="r",
                                error=error)
                return (reg.get(mid).get("health") or {})

            with mock.patch.object(reg_mod.time, "time", lambda: clock[0]):
                self.assertEqual(call("HTTP 429")["down_until"], 0, "one failure is not down")
                waits = []
                for _ in range(5):
                    h = call("HTTP 429")
                    waits.append(h["down_until"] - clock[0])
                    self.assertFalse(reg.availability(reg.get(mid))[0])
                    clock[0] += 60  # a call that was in flight fails while it is down: the wait stays as it was
                    self.assertEqual(call("HTTP 429")["down_until"] - clock[0], waits[-1] - 60)
                    clock[0] = h["down_until"] + 1  # the wait is over: it may be tried again
                    self.assertTrue(reg.availability(reg.get(mid))[0])
                self.assertEqual(waits, [600, 1200, 2400, 3600, 3600])
                h = call("")
                self.assertEqual((h["errors"], h["down_until"], h["trips"]), (0, 0, 0), "an answer resets it")
                call("HTTP 429")
                self.assertEqual(call("HTTP 429")["down_until"] - clock[0], 600, "and the next outage starts again")
        finally:
            sup.close()
            srv.close()
            tmp.cleanup()


class ControlPlaneFailoverTests(unittest.TestCase):
    """Real run 36986998224: the control plane's intelligence had used its provider's free daily quota (HTTP 429,
    "retry in 14h57m"), and structuring each of three objectives failed although another qualified intelligence was
    available. The control plane's own work now goes to the next qualified intelligence, on the record."""

    QUOTA = json.dumps({"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "You exceeded your current "
                                  "quota, please check your plan and billing details. Please retry in 14h57m16s."}})

    def setUp(self):
        self.saved = no_model_env()
        self.waits = model_adapter.HOSTED_RETRY_WAITS_S
        model_adapter.HOSTED_RETRY_WAITS_S = (0.01, 0.01, 0.01, 0.01)
        self.tmp = TempDir()
        self.srv = ModelsServer()
        self.sup = supply_with(self.tmp.path, [("Quota", 0.1), ("Steady", 0.2)], self.srv)

    def tearDown(self):
        model_adapter.HOSTED_RETRY_WAITS_S = self.waits
        self.sup.close()
        self.srv.close()
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_a_refused_provider_moves_the_control_planes_work_to_the_next_qualified_intelligence(self):
        from cynqra.engine import Engine
        from helpers import SCENARIO
        self.srv.refused["Quota"] = (429, self.QUOTA)
        e = Engine(self.tmp.path / "run", supply=self.sup)
        try:
            e.create_company("Harbor Recruiting", "live")
            e.draft_objective(SCENARIO["messy"])
            self.assertTrue((e.objective() or {}).get("structured"), e.meta.get("notice"))
            ds = e.decisions()
            self.assertEqual(ds[0]["selected_intelligence"]["id"], "quota", "the cheaper one was chosen first")
            fo = [d for d in ds if d["purpose"] == "failover"]
            self.assertEqual(len(fo), 1)
            self.assertEqual((fo[0]["selected_intelligence"]["id"], fo[0]["status"]), ("steady", "committed"))
            why = next(x for x in fo[0]["excluded_candidates"] if x["id"] == "quota")["violations"][0]["why"]
            self.assertIn("provider refused the call", why)
            self.assertTrue(controller.replay(e, fo[0]["decision_id"])["reproduced"])
            ev = e.store.events()
            moved = [x for x in ev if x["event_type"] == "intelligence.rerouted"]
            self.assertEqual([(x["payload"]["from"], x["payload"]["to"], x["payload"]["cause"]) for x in moved],
                             [("quota", "steady", "provider")])
            proposed = {x["payload"]["decision_id"] if "decision_id" in x["payload"] else x["aggregate_id"]
                        for x in ev if x["event_type"] == "intelligence.selection.proposed"}
            self.assertTrue({d["decision_id"] for d in ds} <= proposed, "every decision is shown as proposed")
            # the refusal is the provider's: nothing about the intelligence is learned from it
            self.assertFalse([o for o in e.registry.store.all("outcome") if o.get("model_id") == "quota"])
            self.assertFalse(oe.query(e.store, objective_id=controller.objective_id(e), tenant_id="local"))
            # and the next call of the control plane's goes straight to the one that answers
            n = len(self.srv.requests)
            e.submit_objective()
            self.assertTrue(all(r["model"] == "Steady" for r in self.srv.requests[n:]), self.srv.requests[n:])
        finally:
            e.close()

    def test_a_refused_planner_moves_the_roadmap_to_the_next_qualified_intelligence(self):
        # real run 37080673901: the planner's model (gpt-oss-120b on Groq) used its free daily allowance mid-roadmap
        # ("tokens per day ... try again in"), and all three objectives stopped there, Kimi K3 qualified and answering
        from cynqra.engine import Engine
        from helpers import SCENARIO
        tpd = json.dumps({"error": {"message": "Rate limit reached for model `quota` on tokens per day (TPD): Limit "
                                               "200000, Used 199444, Requested 3669. Please try again in 26m3s.",
                                    "type": "tokens", "code": "rate_limit_exceeded"}})
        e = Engine(self.tmp.path / "run", supply=self.sup)
        try:
            e.create_company("Harbor Recruiting", "live")
            e.draft_objective(SCENARIO["messy"])
            e.submit_objective()
            d = next(x for x in e.pending_decisions() if x["kind"] == "approve_workforce")
            e.decide(d["id"], "approve")
            from unittest import mock
            from cynqra import planner
            real, seen = planner.plan, {}

            def refuse_then_plan(run, note="", cycle=1):  # the planner's provider stops answering as the plan starts
                seen.setdefault("boss", run.planner_id())
                seen.setdefault("on", run.model_of(seen["boss"]))
                self.srv.refused[seen["on"].capitalize()] = (429, tpd)
                return real(run, note, cycle=cycle)

            with mock.patch.object(planner, "plan", side_effect=refuse_then_plan):
                e.define_founder()  # the roadmap: the planner's call is refused, and the plan is written all the same
            boss, other = seen["boss"], ({"quota", "steady"} - {seen["on"]}).pop()
            self.assertNotEqual(e.meta.get("phase"), "stopped_error", e.meta.get("notice"))
            self.assertTrue(e.tasks(), "the roadmap was planned")
            fo = [x for x in e.decisions() if x["purpose"] == "failover" and x.get("worker_id") == boss]
            self.assertEqual([(x["selected_intelligence"]["id"], x["status"]) for x in fo], [(other, "committed")])
            moved = [x["payload"] for x in e.store.events() if x["event_type"] == "intelligence.rerouted"
                     and x["payload"].get("worker_id") == boss]
            self.assertEqual([(m["from"], m["to"], m["cause"]) for m in moved], [(seen["on"], other, "provider")])
            self.assertTrue(e.worker(boss), "the planner keeps its seat")
            self.assertTrue(controller.replay(e, fo[0]["decision_id"])["reproduced"])
            self.assertFalse([o for o in e.registry.store.all("outcome") if o.get("model_id") == seen["on"]
                              and o.get("purpose") == "plan"], "nothing is learned about the refused one")
        finally:
            e.close()

    def test_with_no_other_intelligence_the_failure_is_reported_as_before(self):
        from cynqra.engine import Engine
        from cynqra.intelligence import IntelligenceError
        from helpers import SCENARIO
        self.srv.refused.update({"Quota": (429, self.QUOTA), "Steady": (503, "{}")})
        e = Engine(self.tmp.path / "run", supply=self.sup)
        try:
            e.create_company("Harbor Recruiting", "live")
            with self.assertRaises(IntelligenceError):
                e.draft_objective(SCENARIO["messy"])
            fo = [d for d in e.decisions() if d["purpose"] == "failover"]
            self.assertEqual([d["status"] for d in fo], ["committed", "no_selection"])
        finally:
            e.close()


class UnreadableReplyTests(unittest.TestCase):
    """Real run 36990295187: in each of three objectives an intelligence answered a task in prose, not the JSON asked
    for, and the run stopped ("the intelligence failed (model did not return a JSON object)") with nothing for the
    founder to decide, although the Replacement Engine has a path for exactly this. The error did not name the
    model, so the engine could not act on it. Now it is asked again, then replaced, and the work goes on."""

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

    def test_a_reply_that_is_not_json_goes_to_the_replacement_engine_not_a_stop(self):
        e = live_engine(self.tmp.path / "run", self.sup)
        try:
            self.srv.garbled.add("Steady")  # everyone's incumbent now answers in prose
            run_journey(e, max_rounds=80)
            self.assertNotEqual(e.meta["phase"], "stopped_error", e.meta.get("notice"))
            self.assertEqual(e.meta["phase"], "accepted", e.meta.get("notice"))
            errs = [x for x in e.store.all("call_error") if x["model_id"] == "steady"]
            self.assertTrue(errs and all(x["cause"] == "reply" for x in errs), errs[:3])
            self.assertTrue([r for r in e.store.all("replacement") if r["from"] == "steady"],
                            "after the unusable replies its work moved to another intelligence")
            # an unreadable reply is the intelligence's own failure, never the provider's
            ev = [x for x in oe.query(e.store, objective_id=controller.objective_id(e), tenant_id="local")
                  if x["intelligence_id"] == "steady" and (x.get("failure") or {}).get("reason") ==
                  "the provider answered; the reply could not be used"]
            self.assertFalse([x for x in ev if x["failure"]["kind"] != "intelligence"])
            self.assertTrue(all(t["status"] == "VERIFIED" for t in e.tasks()))
        finally:
            e.close()


class SpecialistFieldTests(unittest.TestCase):
    """Real run 37013721424: each of three objectives stopped at the workforce ("a Specialist needs its field") after
    the one retry, the model proposing a Specialist without the "field" key; the reason did not name the key."""

    def test_a_specialist_titled_by_its_field_keeps_it_and_one_with_neither_is_told_the_key(self):
        from cynqra import synthesis
        from cynqra.intelligence import IntelligenceError
        merged = {}
        m = synthesis._entry(merged, {"role": "Specialist", "title": "Geospatial Data Specialist", "quantity": 1,
                                      "why": "routes"}, "team")
        self.assertEqual((m["field"], m["title"]), ("Geospatial Data", "Geospatial Data Specialist"))
        m = synthesis._entry({}, {"role": "Specialist", "field": "food safety"}, "team")
        self.assertEqual((m["field"], m["title"]), ("food safety", "Food Safety Specialist"))
        with self.assertRaises(IntelligenceError) as ctx:
            synthesis._entry({}, {"role": "Specialist", "why": "domain"}, "team")
        self.assertIn('"field"', str(ctx.exception), "the retry is told exactly where the field goes")


if __name__ == "__main__":
    unittest.main()


class GroqLimitTests(unittest.TestCase):
    """Real run 37028315336: Groq's free tier answered "Rate limit reached ... on tokens per day (TPD) ... Please try
    again in 26m3s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing". The
    billing link made it read as an empty account, the founder was asked to add credit, the examination founder
    refused, and the objective stopped although Kimi K3 on NVIDIA was qualified and answering. A limit that says when
    to try again passes: the provider's side, waited for or covered by a stand-in."""

    TPD = ('HTTP 429 from provider: {"error":{"message":"Rate limit reached for model `openai/gpt-oss-120b` in '
           'organization `org_x` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 199216, '
           'Requested 4383. Please try again in 26m3.0s. Need more tokens? Upgrade to Dev Tier today at '
           'https://console.groq.com/settings/billing","type":"tokens","code":"rate_limit_exceeded"}}')

    def test_a_limit_that_says_when_to_try_again_is_the_providers(self):
        from cynqra.attribution import call_failure, diagnose
        self.assertEqual(diagnose(self.TPD), "rate_limit")
        self.assertEqual(call_failure(self.TPD)["kind"], "provider")
        tpm = self.TPD.replace("tokens per day (TPD)", "tokens per minute (TPM)").replace("26m3.0s", "7.2s")
        self.assertEqual(diagnose(tpm), "rate_limit")

    def test_an_empty_account_is_still_the_founders(self):
        from cynqra.attribution import diagnose
        self.assertEqual(diagnose(self.TPD.replace(" Please try again in 26m3.0s.", "")), "no_credit",
                         "a billing limit with no time to try again is the account's")
        self.assertEqual(diagnose('HTTP 400 from provider: {"error": {"message": "Your credit balance is too low"}}'),
                         "no_credit")
        self.assertEqual(diagnose("HTTP 402 from provider: payment required"), "no_credit")


class ProviderFailedCallsTests(unittest.TestCase):
    """Real run 37044180144: the SaaS objective's QA seat lost Qwen 3.8 27B for good, "2 of 3 calls failed", where both
    failures were Groq not answering. Every failed call is recorded, but only the intelligence's own (a reply that
    could not be used) counts against it; a provider's outage or limit never replaces anyone."""

    def _store(self, causes):
        from cynqra.db import Store
        tmp = TempDir()
        self.addCleanup(tmp.cleanup)
        s = Store(str(tmp.path / "cards.db"))
        self.addCleanup(s.close)
        s.put("call", "c_1", {"id": "c_1", "worker": "w_qa", "model_id": "qwen", "tokens_in": 10, "tokens_out": 10})
        for i, cause in enumerate(causes, 1):
            s.put("call_error", f"ce_{i}", {"id": f"ce_{i}", "worker_id": "w_qa", "model_id": "qwen", "cause": cause,
                                            "error": "HTTP 503 from provider" if cause != "reply" else
                                            "model did not return a JSON object"})
        return s

    def test_a_providers_failures_are_recorded_and_never_cross_a_threshold(self):
        from cynqra import performance
        card = performance.scorecard(self._store(["rate_limit", "outage"]), "w_qa", "qwen")
        self.assertEqual(card["reliability"]["failed_calls"], 0)
        self.assertEqual(card["reliability"]["not_its_failed_calls"], 2)
        self.assertFalse([r for r in performance.below(card) if "calls failed" in r], performance.below(card))

    def test_its_own_unusable_replies_still_count(self):
        from cynqra import performance
        card = performance.scorecard(self._store(["reply", "reply"]), "w_qa", "qwen")
        self.assertEqual(card["reliability"]["failed_calls"], 2)
        self.assertIn("2 of 3 calls failed", performance.below(card))
        # a record from before causes were kept is read from its error
        s = self._store([])
        s.put("call_error", "ce_9", {"id": "ce_9", "worker_id": "w_qa", "model_id": "qwen",
                                     "error": "HTTP 429 from provider: rate limit"})
        self.assertEqual(performance.scorecard(s, "w_qa", "qwen")["reliability"]["failed_calls"], 0)


class HostedTimeoutTests(unittest.TestCase):
    """Real run 37044180144: one call to a provider that held it open took 51 minutes (five attempts of ten), and the
    objective's 70 minutes became 140. A call that timed out fails at once, as the provider's side; one refused fast
    is still retried."""

    def test_a_call_that_timed_out_is_not_sent_again(self):
        import threading
        import time
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from cynqra import model_adapter
        from cynqra.attribution import call_failure, diagnose
        hits = []

        class Slow(BaseHTTPRequestHandler):
            def do_POST(self):
                hits.append(1)
                time.sleep(1.5)
                try:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"{}")
                except OSError:
                    pass

            def log_message(self, *_):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Slow)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        started = time.time()
        with self.assertRaises(RuntimeError) as ctx:
            model_adapter._post(f"http://127.0.0.1:{srv.server_address[1]}/v1/chat/completions", {}, {},
                                timeout=0.3, waits=model_adapter.HOSTED_RETRY_WAITS_S)
        self.assertEqual(len(hits), 1, "sent once")
        self.assertLess(time.time() - started, 4.0, "no retry waits")
        self.assertEqual(diagnose(str(ctx.exception)), "timeout")
        self.assertIn(call_failure(str(ctx.exception))["kind"], ("provider", "network"))


class NoQualifiedIntelligenceTests(unittest.TestCase):
    """Paid run 37587595496: Google answered every qualification call with HTTP 402, "Your prepayment credits are
    depleted", and one model with 404; the founder was told only "live mode needs intelligence: connect a provider".
    A run refused because nothing qualified says, provider by provider and in the provider's words, what stopped it
    and what the founder can do."""

    def setUp(self):
        from cynqra.intelligence_layer import IntelligenceSupply
        self.saved = no_model_env()
        self.tmp = TempDir()
        self.srv = ModelsServer()
        self.sup = IntelligenceSupply(self.tmp.path / "control")
        self.sup.connect({"type": "openai_compatible", "name": "Paid Provider", "endpoint": self.srv.url,
                          "auth": {"method": "none"}, "models": ["flash-preview", "old-pro"], "price_per_m": [1, 4]})

    def tearDown(self):
        self.sup.close()
        self.srv.close()
        self.tmp.cleanup()
        restore_env(self.saved)

    def _refused(self) -> str:
        from cynqra.engine import Engine, EngineError
        e = Engine(self.tmp.path / "run", supply=self.sup)
        with self.assertRaises(EngineError) as ctx:
            e.create_company("Harbor Recruiting", "live")
        return str(ctx.exception)

    def test_an_empty_prepaid_account_is_named_with_the_providers_words_and_the_fix(self):
        depleted = json.dumps([{"error": {"code": 402, "status": "RESOURCE_EXHAUSTED", "message":
                                          "Your prepayment credits are depleted. Please go to AI Studio to manage "
                                          "your project and billing."}}])
        gone = json.dumps([{"error": {"code": 404, "status": "NOT_FOUND",
                                      "message": "This model is no longer available to new users."}}])
        self.srv.refused = {"flash-preview": (402, depleted), "old-pro": (404, gone)}
        said = self._refused()
        self.assertIn("live mode needs intelligence", said)
        self.assertIn("Paid Provider: flash-preview: the provider account has no credit", said)
        self.assertIn("Your prepayment credits are depleted", said, "in the provider's own words")
        self.assertIn("add credit to the account", said, "what the founder can do")
        self.assertIn("old-pro: it can no longer be used", said)
        self.assertNotIn("old-pro: the provider account", said, "each model's own reason")

    def test_a_refused_key_says_so_without_repeating_the_key(self):
        key = "sk-proj-" + "Ab1_" * 10
        self.srv.refused = {m: (401, json.dumps({"error": {"message": f"Incorrect API key provided: {key}"}}))
                            for m in ("flash-preview", "old-pro")}
        said = self._refused()
        self.assertIn("Paid Provider: flash-preview, old-pro: the provider refused the key", said, "one line per reason")
        self.assertIn("give Cynqra a key the provider accepts", said)
        self.assertIn("Incorrect API key provided", said)
        self.assertNotIn(key, said, "a key the provider quotes is never repeated")

    def test_a_model_that_cannot_do_the_work_is_not_called_an_account_problem(self):
        self.srv.garbled = {"flash-preview", "old-pro"}
        said = self._refused()
        self.assertIn("did not pass its qualification work", said)
        self.assertNotIn("credit", said)
        self.assertNotIn("refused the key", said)


class NoRoundBarrierTests(unittest.TestCase):
    """Real run 37044180144: workers moved in lock-step rounds, and a round ended only when every call in it had
    returned, so one call held open ten minutes five times kept every other worker waiting 51 minutes, and the
    objective's 70-minute limit was checked only between rounds. Each worker now takes its next piece as soon as its
    own call returns; a worker still does one thing at a time, and a task is held for its whole call."""

    def setUp(self):
        from test_objective_intelligence import live_engine
        self.saved = no_model_env()
        self.tmp = TempDir()
        self.srv = ModelsServer()
        self.sup = supply_with(self.tmp.path, [("Steady", 0.2)], self.srv)
        self.e = live_engine(self.tmp.path / "run", self.sup)
        self.started, self.ended = {}, {}

    def tearDown(self):
        if self.e is not None:
            self.e.close()
        self.sup.close()
        self.srv.close()
        self.tmp.cleanup()
        restore_env(self.saved)

    def _work(self, delays: dict):
        """Four pieces of work: t_01 and t_02 for the same worker, t_03 and t_04 for two others. Each piece takes
        its delay and is then done; t_05 and t_06 are held, so nothing is delivered."""
        import time
        from unittest import mock
        from cynqra.engine import Engine
        for tid in ("t_01", "t_02", "t_03", "t_04"):
            t = self.e.task(tid)
            t.update(status="ASSIGNED", owner_worker_id="w_pm" if tid in ("t_01", "t_02") else t["owner_worker_id"])
            self.e.save_task(t)
        for tid in ("t_05", "t_06"):  # held out of this test: nothing moves them
            t = self.e.task(tid)
            t["status"] = "HELD_FOR_TEST"
            self.e.save_task(t)

        def act(run, t):
            self.assertNotIn(t["id"], self.started, "a piece of work is started once")
            self.started[t["id"]] = time.time()
            time.sleep(delays.get(t["id"], 0.05))
            with run.lock:  # recording the result is serialized, as the real work records it
                t = run.task(t["id"])
                t["status"] = "VERIFIED"
                run.save_task(t)
            self.ended[t["id"]] = time.time()
            return {"did": "worked", "task": t["id"]}

        return mock.patch.dict(Engine.ACTIONS, {"ASSIGNED": act})

    def test_a_slow_call_does_not_hold_up_the_other_workers(self):
        import time
        with self._work({"t_01": 2.0}):
            t0 = time.time()
            r = self.e.step()
            self.assertLess(time.time() - t0, 1.5, "the step returned when the fast work finished")
            done = {x["task"] for x in r.get("actions", [r])}
            self.assertTrue(done and done <= {"t_03", "t_04"}, done)
            self.assertIn("t_01", self.e._inflight, "the slow call is still running")
            self.assertNotIn("t_02", self.started, "its worker does one thing at a time")
            for _ in range(10):
                if self.e.step()["did"] == "idle":
                    break
        self.assertEqual(sorted(self.started), ["t_01", "t_02", "t_03", "t_04"])
        self.assertGreaterEqual(self.started["t_02"], self.ended["t_01"], "w_pm's next piece after its own call")
        self.assertFalse(self.e._inflight)

    def test_a_step_reports_work_in_flight_so_a_time_limit_is_checked(self):
        import time
        self.e.STEP_WAIT_S = 0.2
        with self._work({"t_01": 1.5, "t_03": 1.5, "t_04": 1.5}):
            t0 = time.time()
            r = self.e.step()
            self.assertEqual(r["did"], "working", r)
            self.assertLess(time.time() - t0, 1.0)
            self.e.close()  # the calls in flight finish and record what they did before the store closes
            self.e = None
        self.assertEqual(sorted(self.ended), ["t_01", "t_03", "t_04"])
        from cynqra.db import Store
        s = Store(str(self.tmp.path / "run" / "cynqra.db"))
        try:
            self.assertEqual({tid: s.get("task", tid)["status"] for tid in ("t_01", "t_03", "t_04")},
                             {"t_01": "VERIFIED", "t_03": "VERIFIED", "t_04": "VERIFIED"})
            self.assertIsNone(s.task_lease("t_01"), "no lease outlives its work")
        finally:
            s.close()

    def test_a_task_is_held_for_its_whole_call(self):
        from cynqra.db import Store
        self.e.STEP_WAIT_S, self.e.LIVE_LEASE_S = 0.2, 0.5  # a lease shorter than the call: renewed while it runs
        other = Store(str(self.tmp.path / "run" / "cynqra.db"))
        try:
            with self._work({"t_01": 1.5}):
                self.e.step()
                for _ in range(20):  # past the short lease three times over while the call runs
                    if "t_01" in self.ended:
                        break
                    self.assertIsNone(other.claim_task("t_01", "another_engine"), "nobody else may start it")
                    self.e.step()
                while self.e._inflight:
                    self.e.step()
            self.assertIn("t_01", self.ended)
            self.assertEqual(list(self.started).count("t_01"), 1)
        finally:
            other.close()

    def test_closing_while_holding_the_run_waits_for_the_work_in_flight_without_deadlock(self):
        # the app's reset closes the engine while holding its lock; the work in flight needs that lock to record
        import threading
        self.e.STEP_WAIT_S = 0.1
        with self._work({"t_01": 1.0}):
            self.e.step()
            done = threading.Event()

            def reset():
                with self.e.lock:
                    self.e.close()
                done.set()

            threading.Thread(target=reset, daemon=True).start()
            self.assertTrue(done.wait(10), "close finished")
            self.e = None
        self.assertIn("t_01", self.ended)

