"""Objective-specific intelligence control: the P1 mandate's loop, its guarantees and its failure modes.

    objective -> version -> requirements and acceptance criteria -> work graph -> workforce -> candidates
    -> qualification -> objective calibration -> selection decision -> binding -> budget reservation -> execution
    -> independent verification -> causal attribution -> objective evidence -> reselection -> replacement
    -> production verification -> delivery -> immutable audit and replay

The models here are test doubles (an in-process OpenAI-compatible server whose "models" answer from
tests/fake_model.py, one of them writing broken code on purpose). They prove the control plane's mechanics and state
transitions only; they say nothing about the quality of any real model, which only real provider runs can show.
"""
from __future__ import annotations

import json
import re
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from helpers import POC, SCENARIO, TempDir, approve, engine_to_gates, engine_to_running, no_model_env, restore_env, \
    run_journey

import fake_model
from cynqra import attribution as attr
from cynqra import binding, budget, calibration, controller, objective, objective_evidence as oe, policies
from cynqra import settings as project_settings
from cynqra.db import ConcurrencyError, Store, digest
from cynqra.engine import Engine
from cynqra.intelligence_layer import IntelligenceSupply
from cynqra.intelligence_layer import evidence as ev_model
from cynqra.intelligence_layer import router

BROKEN = {"result": "done", "summary": "store", "acceptance_check": "done",
          "files": {"store.py": "def broken(:\n    pass\n",
                    "test_store.py": "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n"
                                     "        self.assertTrue(False)\n"}}


class ModelsServer:
    """One OpenAI-compatible endpoint serving several test-double models. Each answers from fake_model.py, except
    that its code tasks come back finished first time (good), or broken (a model that cannot code)."""

    def __init__(self):
        self.broken: set[str] = set()
        self.refused: dict[str, tuple[int, str]] = {}  # model -> (HTTP status, body): the provider refusing it
        self.garbled: set[str] = set()  # models that answer in prose, never the JSON asked for
        self.requests: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                prompt = body["messages"][-1]["content"]
                model = body.get("model")
                outer.requests.append({"model": model, "prompt": prompt[:300]})
                if model in outer.refused:
                    code, msg = outer.refused[model]
                    raw = msg.encode()
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                tid = fake_model._task_in(prompt, "Task ")
                code = tid in ("t_03", "t_04") and "=== FILE:" in prompt and "Assign task" not in prompt
                if model in outer.garbled:
                    text = "I have thought about this carefully and I am confident the work is fine."
                elif code and model in outer.broken:
                    text = "```json\n" + json.dumps(BROKEN) + "\n```"
                elif code:
                    text = "```json\n" + json.dumps(fake_model._resolve(fake_model.S["work"][tid][-1])) + "\n```"
                else:
                    text = fake_model.answer(prompt)
                raw = json.dumps({"choices": [{"message": {"role": "assistant", "content": text}}],
                                  "usage": {"prompt_tokens": max(1, len(prompt) // 4),
                                            "completion_tokens": max(1, len(text) // 4)}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def supply_with(tmp: Path, models: list[tuple[str, float]], srv: ModelsServer) -> IntelligenceSupply:
    sup = IntelligenceSupply(tmp / "control")
    for i, (name, price) in enumerate(models):
        sup.connect({"type": "openai_compatible", "name": f"Provider {i}", "endpoint": srv.url, "auth": {"method": "none"},
                     "models": [name], "price_per_m": [price, price * 4]})
    for m in sup.registry.models():  # test doubles stand for qualified providers; real ones qualify through probe.py
        sup.registry.set_regression(m["id"], True, "test fixture: qualified test double",
                                    by_kind={"objective": "passed", "code": "passed"})
    return sup


def live_engine(folder: Path, sup: IntelligenceSupply, budget_usd: float = 5.0, tenant: str | None = None) -> Engine:
    e = Engine(folder, supply=sup, tenant=tenant)
    e.create_company("Harbor Recruiting", "live")
    e.draft_objective(SCENARIO["messy"])
    e.set_guardrails(budget_usd=budget_usd, time_value_per_hour=10)
    e.submit_objective()
    return engine_to_gates(e)


# --- pure: the evidence model and the selection rule ---------------------------------------------------------------
POL = {n: {"version": p["version"], "body": p["body"]} for n, p in policies.effective().items()}


def raw(iid, kind, verified, *, src="objective", version="", objective_id="obj_x", objective_version=1, role="Engineer",
        vq=1.0, clean=True, tenant="local", run_id="other", source="project", autonomy="autonomous", item="t_09",
        protocol=False):
    r = {"src": src, "id": f"{iid}-{kind}-{verified}-{id(object())}", "intelligence_id": iid, "served_version": version,
         "task_kind": kind, "role": role, "verified": verified, "clean": clean, "tenant_id": tenant, "vq": vq,
         "autonomy": autonomy, "status": "active", "at": 1e9, "protocol": protocol}
    if src == "objective":
        r.update(objective_id=objective_id, objective_version=objective_version, work_item_id=item, stage="objective_execution")
    else:
        r.update(run_id=run_id, source=source)
    return r


def ctx(**kw):
    base = {"tenant_id": "local", "workspace_id": "local", "objective_id": "obj_x", "objective_version": 1,
            "run_id": "co_me", "inheritance": {}, "env": None, "now": 1e9}
    base.update(kw)
    return base


def cand(iid, price=1.0, **kw):
    c = {"id": iid, "name": iid, "served_version": "", "available": True, "availability": "available",
         "qualification": {"status": "passed", "by_kind": {}}, "context": 0, "max_output": None, "local": False,
         "input_modalities": ["text"], "measured": {k: {"usd_per_attempt": price * 0.01, "seconds_per_attempt": 30}
                                                    for k in ("code", "document", "decision", "deploy", "review")}}
    c.update(kw)
    return c


def snap(cands, evidence, kinds=("code",), tier="LOW", scope="task", incumbent=None, local_only=False, exclude=(),
         cap=5.0, explore=None):
    return {"now": 1e9, "work": {"work_item_id": "t_09", "scope": scope, "kinds": list(kinds), "role": "Engineer",
                                 "worker_id": "w_eng_a", "risk_tier": tier, "min_context": 8192, "output_tokens": 8000,
                                 "local_only": local_only},
            "context": ctx(), "candidates": cands, "evidence": evidence,
            "budget": {"cap": cap, "spent": 0.0, "reserved": 0.0, "headroom": cap, "time_value_per_hour": 10},
            "exploration": explore or {"used": 0, "spent_usd": 0.0}, "exclude": list(exclude), "exclude_why": {},
            "incumbent": incumbent, "policies": POL, "evidence_version": 0}


class EvidenceModelTests(unittest.TestCase):
    def q(self, items, kind="code", **kw):
        return ev_model.assess(items, ctx(**kw), {k: v["body"] for k, v in POL.items()}, kind)

    def test_unverified_means_unknown_not_bad_and_not_best(self):
        a = self.q([])
        self.assertEqual((a["quality"]["mean"], a["quality"]["maturity"], a["quality"]["decisive_level"]),
                         (0.5, "none", "prior"))

    def test_a_tiny_sample_does_not_outvote_a_mature_body_of_evidence(self):
        history = [raw("m", "code", False, src="registry") for _ in range(50)]
        one = [raw("m", "code", True)]
        a = self.q(history + one)
        self.assertLess(a["quality"]["mean"], 0.25, "one objective success against fifty relevant failures")
        self.assertTrue(a["levels"]["historical"]["capped"], "a long history is capped, so objective evidence can win")
        many = self.q(history + [raw("m", "code", True) for _ in range(20)])
        self.assertGreater(many["quality"]["mean"], 0.6, "objective evidence becomes authoritative as it accumulates")
        self.assertEqual(many["quality"]["decisive_level"], "objective_verified")

    def test_success_rate_and_strength_are_different_things(self):
        thin = self.q([raw("m", "code", True)])
        mature = self.q([raw("m", "code", True) for _ in range(12)])
        self.assertEqual(thin["raw"]["success_rate"], mature["raw"]["success_rate"], "both 100% raw")
        self.assertLess(thin["strength"]["sample_maturity"], mature["strength"]["sample_maturity"])
        self.assertLess(thin["quality"]["lcb"], mature["quality"]["lcb"], "uncertainty is explicit")
        self.assertEqual((thin["quality"]["maturity"], mature["quality"]["maturity"]), ("thin", "mature"))

    def test_relevance_follows_the_work(self):
        same = self.q([raw("m", "code", True) for _ in range(4)], role="Engineer")
        other_role = self.q([raw("m", "code", True, role="CTO") for _ in range(4)], role="Engineer")
        other_kind = self.q([raw("m", "document", True) for _ in range(4)], role="Engineer")
        self.assertGreater(same["quality"]["mean"], other_role["quality"]["mean"])
        self.assertGreater(other_role["quality"]["mean"], other_kind["quality"]["mean"])

    def test_another_version_or_serving_company_is_never_this_ones_evidence(self):
        items = [raw("m", "code", True, version="v1") for _ in range(6)]
        a = ev_model.assess(items, ctx(candidate_versions={"m": "v2"}), {k: v["body"] for k, v in POL.items()}, "code")
        self.assertEqual(a["quality"]["mean"], 0.5)
        self.assertTrue(all(x["why"] == "version_mismatch" for x in a["excluded"]))
        self.assertEqual(a["strength"]["version_integrity"], 0.0)

    def test_contaminated_failures_are_kept_out(self):
        outage = [raw("m", "code", False, clean=False) | {"attribution": "provider"} for _ in range(8)]
        a = self.q(outage)
        self.assertEqual(a["quality"]["mean"], 0.5, "a provider's outage teaches nothing about the intelligence")
        self.assertTrue(all(x["why"] == "contaminated:provider" for x in a["excluded"]))

    def test_another_tenant_and_another_objective_are_isolated(self):
        a = self.q([raw("m", "code", True, tenant="enterprise_b") for _ in range(5)]
                   + [raw("m", "code", True, objective_id="obj_other") for _ in range(5)])
        self.assertEqual(a["quality"]["mean"], 0.5)
        self.assertEqual(sorted({x["why"] for x in a["excluded"]}), ["other_objective", "tenant_isolation"])

    def test_human_help_is_not_autonomous_success(self):
        auto = self.q([raw("m", "code", True) for _ in range(4)])
        helped = self.q([raw("m", "code", True, autonomy="human_corrected") for _ in range(4)])
        self.assertGreater(auto["quality"]["mean"], helped["quality"]["mean"])
        self.assertLess(helped["levels"]["objective_verified"]["success"], 4 * 0.5)

    def test_self_review_is_partial_evidence_only(self):
        a = self.q([raw("m", "code", True, vq=0.1) for _ in range(5)])
        self.assertEqual(a["levels"]["objective_verified"]["items"], 0)
        self.assertEqual(a["levels"]["objective_partial"]["items"], 5)
        self.assertLess(a["quality"]["mean"], 0.65)

    def test_objective_version_inheritance(self):
        items = [raw("m", "code", True, objective_version=1) for _ in range(6)]
        body = {k: v["body"] for k, v in POL.items()}
        none = ev_model.assess(items, ctx(objective_version=2, inheritance={"1": {"mode": "none"}}), body, "code")
        prior = ev_model.assess(items, ctx(objective_version=2, inheritance={"1": {"mode": "prior_only",
                                                                                      "relevance": 0.5}}), body, "code")
        full = ev_model.assess(items, ctx(objective_version=2, inheritance={"1": {"mode": "full"}}), body, "code")
        self.assertTrue(all(x["why"] == "objective_version_boundary" for x in none["excluded"]))
        self.assertEqual(prior["levels"]["objective_verified"]["items"], 0, "never objective evidence of v2")
        self.assertEqual(prior["levels"]["historical"]["items"], 6, "a prior only")
        self.assertEqual(full["levels"]["objective_verified"]["items"], 6)
        later = ev_model.assess(items, ctx(objective_version=0), body, "code")
        self.assertTrue(all(x["why"] == "later_objective_version" for x in later["excluded"]))


class SelectionRuleTests(unittest.TestCase):
    def test_hard_constraints_cannot_be_traded_for_quality(self):
        strong = [raw("big", "code", True) for _ in range(10)]
        cands = [cand("big", context=4096), cand("cloud"), cand("failed_code", qualification={
            "status": "passed", "by_kind": {"code": "failed"}}), cand("laptop", local=True)]
        r = router.select(snap(cands, strong))
        why = {x["id"]: x["violations"][0]["constraint"] for x in r["excluded"]}
        self.assertEqual(why, {"big": "context", "failed_code": "qualified"})
        r = router.select(snap(cands, strong, local_only=True))
        self.assertEqual(r["selected"], "laptop", "the founder's local-only constraint is a hard constraint")

    def test_three_protocol_violations_make_it_ineligible_for_that_work(self):
        bad = [raw("x", "code", False, protocol=True) for _ in range(3)]
        r = router.select(snap([cand("x", price=0.1), cand("y")], bad))
        self.assertEqual(r["excluded"][0]["violations"][0]["constraint"], "protocol")
        self.assertEqual(r["selected"], "y")

    def test_no_universal_ranking_the_work_decides(self):
        ev = [raw("a", "code", True) for _ in range(6)] + [raw("a", "document", False, role="CPO") for _ in range(6)] \
            + [raw("b", "code", False) for _ in range(6)] + [raw("b", "document", True, role="CPO") for _ in range(6)]
        code = router.select(snap([cand("a"), cand("b")], ev, kinds=("code",)))
        doc = router.select(dict(snap([cand("a"), cand("b")], ev, kinds=("document",)),
                                 work={**snap([], [], kinds=("document",))["work"], "role": "CPO"}))
        self.assertEqual((code["selected"], doc["selected"]), ("a", "b"))

    def test_tradeoffs_follow_the_risk_tier_not_a_score(self):
        ev = [raw("premium", "code", True) for _ in range(10)] + [raw("budget", "code", True) for _ in range(5)] + \
            [raw("budget", "code", False) for _ in range(1)]
        cands = [cand("premium", price=20.0), cand("budget", price=0.5)]
        low = router.select(snap(cands, ev, tier="LOW"))
        high = router.select(snap(cands, ev, tier="HIGH"))
        self.assertEqual((low["selected"], high["selected"]), ("budget", "premium"),
                         "cheap qualified intelligence for low-risk work, the strongest evidence for high-risk work")
        self.assertEqual((low["tradeoff"], high["tradeoff"]), ("economy", "quality_first"))

    def test_an_untested_challenger_never_replaces_a_working_incumbent(self):
        ev = [raw("inc", "code", True) for _ in range(4)] + [raw("inc", "code", False)]
        cands = [cand("inc", price=3.0), cand("new", price=0.1)]
        r = router.select(snap(cands, ev, incumbent={"intelligence_id": "inc", "served_version": ""}, scope="worker"))
        self.assertEqual((r["selected"], r["mode"]), ("inc", "keep_incumbent"))
        ev += [raw("new", "code", True) for _ in range(12)] + [raw("inc", "code", False) for _ in range(6)]
        r = router.select(snap(cands, ev, incumbent={"intelligence_id": "inc", "served_version": ""}, scope="worker"))
        self.assertEqual((r["selected"], r["mode"]), ("new", "reselect"), "verified superiority replaces it")

    def test_exploration_is_explicit_bounded_and_never_for_high_risk(self):
        ev = [raw("inc", "code", True) for _ in range(5)] + [raw("inc", "code", False) for _ in range(3)]
        cands = [cand("inc"), cand("unknown")]
        r = router.select(snap(cands, ev, tier="LOW", incumbent={"intelligence_id": "inc", "served_version": ""}))
        self.assertEqual((r["selected"], r["mode"]), ("unknown", "explore"))
        self.assertIn("upper bound", r["challenger"]["why"])
        used = router.select(snap(cands, ev, tier="LOW", explore={"used": 3, "spent_usd": 0.0},
                                  incumbent={"intelligence_id": "inc", "served_version": ""}))
        self.assertEqual(used["mode"], "keep_incumbent", "at most three explorations an objective")
        poor = router.select(snap(cands, ev, tier="LOW", cap=0.0001,
                                  incumbent={"intelligence_id": "inc", "served_version": ""}))
        self.assertNotEqual(poor["mode"], "explore", "bounded by budget")
        high = router.select(snap(cands, ev, tier="HIGH", incumbent={"intelligence_id": "inc", "served_version": ""}))
        self.assertNotEqual(high["mode"], "explore", "high-risk work exploits; it is never an experiment")

    def test_selection_is_deterministic(self):
        ev = [raw("a", "code", True), raw("b", "code", False)]
        s = snap([cand("a"), cand("b"), cand("c")], ev)
        self.assertEqual(router.select(s)["ranking"], router.select(json.loads(json.dumps(s)))["ranking"])

    def test_no_model_or_provider_is_named_in_the_control_plane(self):
        names = re.compile(r"\b(kimi|gemini|gpt|claude|anthropic|openai|qwen|glm|llama|mistral|deepseek|nvidia)\b", re.I)
        for f in ("controller.py", "calibration.py", "objective_evidence.py", "policies.py", "attribution.py",
                  "intelligence_layer/evidence.py", "intelligence_layer/candidates.py"):
            text = (POC / "cynqra" / f).read_text(encoding="utf-8")
            self.assertFalse(names.search(text), f"{f} names {names.search(text) and names.search(text).group(0)}")
        text = (POC / "cynqra" / "intelligence_layer" / "router.py").read_text(encoding="utf-8")
        self.assertFalse(names.search(text.split("# --- objective-aware selection")[1]))


class AttributionTests(unittest.TestCase):
    def test_causes(self):
        self.assertEqual(attr.call_failure("HTTP 503: Service Unavailable")["kind"], "provider")
        for code in (408, 409, 425, 429, 500, 502, 503, 504):
            self.assertFalse(attr.call_failure(f"HTTP {code} from provider")["attributable_to_intelligence"], code)
        self.assertEqual(attr.call_failure("network error: remote end closed connection")["kind"], "network")
        self.assertEqual(attr.call_failure("RuntimeError: reply truncated at max_tokens")["kind"], "intelligence")
        self.assertEqual(attr.verification_failure("sqlite3.OperationalError: unable to open database file")["kind"],
                         "environment")
        self.assertEqual(attr.verification_failure("Failing tests: test_store.T.test_x.")["kind"], "intelligence")
        self.assertEqual(attr.tool_failure("denied", "Kill switch is on. All workers are frozen.")["kind"], "environment")
        self.assertEqual(attr.tool_failure("denied", "target '../x' is outside the workspace rules")["kind"],
                         "intelligence")
        self.assertEqual(attr.tool_failure("denied", "command timed out after 120s")["kind"], "tool")
        self.assertFalse(attr.clean(attr.failure("specification", "an ambiguous requirement")))


class StoreLevelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir()
        self.store = Store(str(self.tmp.path / "s.db"))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def rec(self, **kw):
        r = {"tenant_id": "local", "workspace_id": "local", "objective_id": "obj_a", "objective_version": 1,
             "intelligence_id": "m", "stage": "objective_execution", "work_item_id": "t_01", "task_kind": "code",
             "verified": True, "idempotency_key": "k1", "artifact_hashes": {"work_hash": "h1", "files": []}}
        r.update(kw)
        return r

    def test_evidence_is_immutable_idempotent_scoped_and_holds_no_content(self):
        r, created = oe.record(self.store, self.rec())
        again, created2 = oe.record(self.store, self.rec())
        self.assertEqual((created, created2, again["evidence_id"]), (True, False, r["evidence_id"]),
                         "a duplicated event never counts twice")
        self.assertEqual(oe.evidence_version(self.store, "obj_a"), 1)
        self.assertTrue(oe.verify_integrity(self.store, r["evidence_id"]))
        tampered = self.store.get(oe.KIND, r["evidence_id"])
        tampered["verified"] = False
        self.store.put(oe.KIND, r["evidence_id"], tampered)
        self.assertFalse(oe.verify_integrity(self.store, r["evidence_id"]), "a changed record no longer matches")
        self.assertEqual(oe.query(self.store, objective_id="obj_a", tenant_id="enterprise_b"), [])
        self.assertEqual(oe.query(self.store, objective_id="obj_b", tenant_id="local"), [])
        with self.assertRaises(oe.EvidenceError):
            oe.query(self.store, objective_id="obj_a", tenant_id="")
        with self.assertRaises(oe.EvidenceError):
            oe.record(self.store, self.rec(idempotency_key="k2", content="def secret(): ..."))
        with self.assertRaises(oe.EvidenceError):  # a failure must carry its cause
            oe.record(self.store, self.rec(idempotency_key="k3", verified=False, failure={"kind": "bogus"}))

    def test_retention_and_redaction_keep_the_causal_record(self):
        r, _ = oe.record(self.store, self.rec())
        hit = oe.redact_artifact(self.store, "h1", "customer data, deleted on request")
        self.assertEqual(hit, [r["evidence_id"]])
        kept = self.store.get(oe.KIND, r["evidence_id"])
        self.assertEqual((kept["artifact_hashes"]["work_hash"], kept["verified"], kept["status"]), ("h1", True, "active"))
        self.assertIn("deleted", kept["status_note"])
        self.assertTrue(oe.verify_integrity(self.store, r["evidence_id"]), "redaction never rewrites the record")
        gone = oe.archive_older_than(self.store, "obj_a", days=0, now_ts=r["at"] + 10)
        self.assertEqual(gone, [r["evidence_id"]])
        self.assertEqual(oe.query(self.store, objective_id="obj_a", tenant_id="local"), [])
        self.assertEqual(len(oe.query(self.store, objective_id="obj_a", tenant_id="local", include_inactive=True)), 1)

    def test_out_of_order_and_concurrent_evidence_keeps_every_record(self):
        def go(i):
            oe.record(self.store, self.rec(idempotency_key=f"k{i}", work_item_id=f"t_{i:02d}", verified=i % 2 == 0))
        threads = [threading.Thread(target=go, args=(i,)) for i in range(20)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        recs = oe.query(self.store, objective_id="obj_a", tenant_id="local")
        self.assertEqual(len(recs), 20)
        self.assertEqual(sorted(r["evidence_version"] for r in recs), list(range(1, 21)), "no lost update")
        self.assertEqual(oe.evidence_version(self.store, "obj_a"), 20)

    def test_budget_reservations_hold_under_concurrent_workers(self):
        project_settings.update(self.store, {"budget_usd": 1.0})
        budget.charge(self.store, "w", "t_00", 0.25, "inference")
        out = []

        def go(i):
            out.append(budget.reserve(self.store, worker_id=f"w_{i}", task_id=f"t_{i}", model_id="m", usd=0.1,
                                      purpose="model_call"))
        threads = [threading.Thread(target=go, args=(i,)) for i in range(10)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        held = [r for r in out if r["status"] == "held"]
        self.assertEqual(len(held), 7, "0.25 spent + 7 x 0.1 in flight fit the $1 cap; the other three do not start")
        h = budget.headroom(self.store)
        self.assertLessEqual(h["spent"] + h["reserved"], 1.0 + 1e-9)
        refused = [r for r in out if r["status"] == "refused"]
        self.assertTrue(all(r["in_flight"] > 0 for r in refused), "they wait for in-flight work, they did not fail")
        budget.release(self.store, [r["id"] for r in held])
        self.assertEqual(budget.headroom(self.store)["reserved"], 0)

    def test_concurrent_charges_never_lose_spend(self):
        project_settings.update(self.store, {"budget_usd": 100.0})
        threads = [threading.Thread(target=budget.charge, args=(self.store, f"w{i}", f"t{i}", 0.01, "inference"))
                   for i in range(40)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertAlmostEqual(budget.ledger(self.store)["spent_total"], 0.40, places=6)


# --- the demo run: lifecycle, acceptance, decisions, concurrency, replay -------------------------------------------
class DemoRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TempDir()
        cls.e = engine_to_running(cls.tmp.path / "demo")
        run_journey(cls.e)

    @classmethod
    def tearDownClass(cls):
        cls.e.close()
        cls.tmp.cleanup()

    def test_objective_identity_version_and_lifecycle(self):
        e = self.e
        obj = e.objective()
        self.assertTrue(obj["objective_id"].startswith("obj_") and obj["objective_id"] != "obj_1")
        states = [h["to"] for h in obj["lifecycle"]["history"]]
        self.assertEqual(states, ["OBJECTIVE_CREATED", "OBJECTIVE_ACCEPTED", "OBJECTIVE_DECOMPOSED",
                                  "OBJECTIVE_EXECUTING", "OBJECTIVE_COMPLETED", "OBJECTIVE_VERIFIED", "OBJECTIVE_CLOSED"])
        self.assertTrue(all(t["objective_id"] == obj["objective_id"] and t["objective_version"] == obj["version"]
                            for t in e.tasks()))
        self.assertTrue(objective.versions(e))
        self.assertFalse(objective.transition(e, "OBJECTIVE_EXECUTING", "a closed objective cannot just run again"))
        self.assertTrue([x for x in e.store.events() if x["event_type"] == "objective.transition_refused"])
        with self.assertRaises(objective.ObjectiveError):
            objective.transition(e, "OBJECTIVE_CREATED", "no", strict=True)

    def test_acceptance_criteria_are_machine_readable(self):
        req = self.e.requirements()
        crit = req["acceptance_criteria"]
        self.assertTrue(all({"criterion_id", "description", "type", "verification_method", "mandatory", "severity",
                             "required_evidence", "objective_version"} <= set(c) for c in crit))
        self.assertIn("live_health_and_smoke", {c["verification_method"] for c in crit})
        self.assertTrue(all(c["verified_by_tasks"] for c in crit if c.get("requirement_id") and c["mandatory"]))
        for t in self.e.tasks():
            self.assertEqual(t["acceptance_hash"], objective.acceptance_hash(t))
            self.assertTrue(all(c["verification_method"] for c in t["acceptance"]))

    def test_every_binding_has_a_persisted_decision_with_its_policy(self):
        e = self.e
        bs = list(binding.all_bindings(e.store).values()) + list(binding.all_task_bindings(e.store).values())
        self.assertTrue(bs)
        for b in bs:
            d = controller.get_decision(e, b["decision_id"])
            self.assertIsNotNone(d, b)
            self.assertEqual(d["selection_policy_version"], policies.version("selection"))
            self.assertTrue(e.store.get_object(d["evidence_snapshot"]))
        self.assertEqual(len(binding.all_task_bindings(e.store)), len(e.tasks()), "one binding per work item")

    def test_every_decision_replays_from_its_own_snapshot(self):
        ds = self.e.decisions()
        self.assertTrue(ds)
        self.assertTrue(all(controller.replay(self.e, d["decision_id"])["reproduced"] for d in ds),
                        [d["decision_id"] for d in ds if not controller.replay(self.e, d["decision_id"])["reproduced"]])

    def test_production_verification_is_part_of_completion(self):
        pv = self.e.store.get("production_verification", "pv_1")
        self.assertTrue(pv["passed"])
        self.assertIn("ac_prod_live", {c["criterion_id"] for c in pv["criteria"]})
        types = [x["event_type"] for x in self.e.store.events()]
        for name in ("objective.created", "requirements.created", "workgraph.created", "workforce.created",
                     "intelligence.discovered", "intelligence.selection.proposed", "intelligence.selection.committed",
                     "worker.bound", "task.started", "verification.completed", "intelligence.evidence.updated",
                     "production.verification.started", "production.verification.completed", "objective.completed"):
            self.assertIn(name, types, name)
        self.assertLess(types.index("production.verification.completed"), types.index("objective.completed"))

    def test_evidence_records_reference_and_never_contain_the_work(self):
        evs = oe.query(self.e.store, objective_id=self.e.objective()["objective_id"], tenant_id="local")
        self.assertTrue(evs)
        dump = json.dumps(evs)
        self.assertNotIn("def ", dump, "no source code in evidence")
        self.assertTrue(all(e["verification"]["verifier_kind"] for e in evs))
        self.assertTrue(all(oe.verify_integrity(self.e.store, e["evidence_id"]) for e in evs))

    def test_the_causal_audit_of_a_task_is_complete(self):
        code = next(t for t in self.e.tasks() if t["kind"] == "code")
        x = self.e.explain(code["id"])
        self.assertTrue(x["complete"], x["missing"])
        self.assertEqual(x["chain"]["objective_lifecycle_state"], "OBJECTIVE_CLOSED")
        self.assertTrue(all(x["chain"]["immutable_audit_replay"]))


class GuardTests(unittest.TestCase):
    """Adversarial: the control plane fails safely."""

    def setUp(self):
        self.tmp = TempDir()
        self.e = engine_to_running(self.tmp.path / "demo")

    def tearDown(self):
        self.e.close()
        self.tmp.cleanup()

    def test_moving_the_acceptance_bar_is_refused(self):
        e = self.e
        t = next(t for t in e.tasks() if t["kind"] in ("code", "document"))
        t["acceptance_criteria"] = ["anything passes"]  # a worker or a candidate trying to lower the bar
        e.save_task(t)
        from cynqra import verifier
        r = verifier.verify(e, e.task(t["id"]))
        self.assertEqual((r["passed"], r.get("integrity")), (False, False))
        self.assertTrue([x for x in e.store.events() if x["event_type"] == "acceptance.integrity_violation"])
        evs = oe.query(e.store, objective_id=e.objective()["objective_id"], tenant_id="local", work_item_id=t["id"])
        self.assertTrue(evs and evs[-1]["failure"]["kind"] == "specification" and not evs[-1]["clean"])

    def test_false_or_misleading_verification_is_refused_as_evidence(self):
        e = self.e
        e.run_until_idle()
        v = next(v for v in e.store.all("verification"))
        t = e.task(v["task_id"])
        with self.assertRaises(oe.EvidenceError):  # a claim that contradicts its verification record
            controller.record_task_evidence(e, t, verified=v["verdict"] != "VERIFIED", verification=v,
                                            idempotency_key="lie")
        forged = dict(v, verdict="VERIFIED" if v["verdict"] != "VERIFIED" else "REQUIRES_REWORK")
        with self.assertRaises(oe.EvidenceError):  # a verdict changed after the fact no longer matches its hash
            controller.record_task_evidence(e, t, verified=None, verification=forged, idempotency_key="forged")

    def test_a_stale_decision_is_decided_again_and_kept_as_history(self):
        e = self.e
        t = next(t for t in e.tasks() if t["status"] == "PLANNED")
        work = controller.work_for_task(e, t)
        d = controller.decide(e, work, "test")
        controller.record_task_evidence(e, t, verified=True, verifier_kind="deterministic_platform",
                                        idempotency_key="new-evidence", stage="objective_calibration")
        b = controller.commit(e, d, work, reason="test", by="test", purpose="test")
        old = controller.get_decision(e, d["decision_id"])
        self.assertEqual(old["status"], "superseded_before_commit", "decided against evidence version N, kept")
        self.assertEqual(controller.get_decision(e, b["decision_id"])["revalidates"], d["decision_id"])
        self.assertTrue(controller.replay(e, d["decision_id"])["reproduced"], "the old decision still replays")

    def test_a_stale_binding_cannot_overwrite_a_newer_one(self):
        e = self.e
        t = next(t for t in e.tasks() if t["status"] == "PLANNED")
        cur = binding.task_binding(e.store, t["id"])
        entry = e.registry.get(cur["intelligence_id"])
        binding.bind_task(e, t["id"], t["owner_worker_id"], entry, reason="a newer decision", by="test",
                          expected_version=cur["_v"])
        with self.assertRaises(ConcurrencyError):
            binding.bind_task(e, t["id"], t["owner_worker_id"], entry, reason="decided against the old one", by="test",
                              expected_version=cur["_v"])
        now = binding.task_binding(e.store, t["id"])
        self.assertEqual((now["_v"], len(now["history"])), (cur["_v"] + 1, len(cur["history"]) + 1))

    def test_concurrent_selections_on_one_work_item_never_lose_a_binding(self):
        e = self.e
        t = next(t for t in e.tasks() if t["status"] == "PLANNED")
        before = binding.task_binding(e.store, t["id"])["_v"]
        errors = []

        def go():
            try:
                work = controller.work_for_task(e, t)
                d = controller.decide(e, work, "race")
                controller.commit(e, d, work, reason="race", by="test", purpose="race")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
        threads = [threading.Thread(target=go) for _ in range(6)]
        [x.start() for x in threads]
        [x.join() for x in threads]
        self.assertEqual(errors, [])
        tb = binding.task_binding(e.store, t["id"])
        self.assertEqual(tb["_v"], before + 6, "every commit is a version: none overwrote another")
        self.assertEqual(len(tb["history"]), before + 5)

    def test_duplicate_events_never_duplicate_evidence(self):
        e = self.e
        t = e.tasks()[0]
        for _ in range(3):
            controller.record_task_evidence(e, t, verified=True, idempotency_key="the-same-verification",
                                            stage="objective_calibration")
        evs = [x for x in e.store.all(oe.KIND) if x["idempotency_key"] == "the-same-verification"]
        self.assertEqual(len(evs), 1)
        upd = [x for x in e.store.events() if x["event_type"] == "intelligence.evidence.updated"
               and x["payload"]["evidence_id"] == evs[0]["evidence_id"]]
        self.assertEqual(len(upd), 1)

    def test_a_replayed_snapshot_that_was_tampered_with_is_not_reproduced(self):
        e = self.e
        d = e.decisions()[-1]
        snap = e.store.get_object(d["evidence_snapshot"])
        snap["candidates"] = []
        with e.store.lock:
            e.store.conn.execute("UPDATE objects SET body=? WHERE hash=?", (json.dumps(snap), d["evidence_snapshot"]))
        self.assertFalse(controller.replay(e, d["decision_id"])["reproduced"])


# --- the closed loop, live, on test doubles that really differ -----------------------------------------------------
class ClosedLoopTests(unittest.TestCase):
    """A real objective end to end through the control plane. Three test-double models: Steady and Careful write
    working code; Sloppy writes broken code. Steady is cheapest, so it starts as everyone's incumbent; after
    calibration, Steady breaks: its code fails verification, the evidence moves the future code work to Careful,
    and the engineer whose code kept failing gets Careful too, keeping its seat."""

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

    def test_objective_to_production_through_the_control_loop(self):
        e = live_engine(self.tmp.path / "run", self.sup)
        oid = e.objective()["objective_id"]
        # cold start: calibration on the objective's own work, bounded, with platform-owned verdicts
        p = e.store.get(calibration.KIND, calibration.plan_id(e))
        self.assertEqual(p["status"], "completed", p.get("reason"))
        code_item = next(i for i in p["items"] if i["kind"] == "code")
        self.assertEqual(len(code_item["candidates"]), 3)
        verdicts = {t["intelligence_id"]: t["verified"] for t in p["trials"] if t["item_id"] == code_item["item_id"]}
        self.assertEqual(verdicts, {"steady": True, "sloppy": False, "careful": True})
        self.assertTrue(all(v.get("reason") for v in p["stopping"].values()))
        cal = oe.query(e.store, objective_id=oid, tenant_id="local", stage="objective_calibration")
        self.assertEqual(len(cal), len(p["trials"]))
        # initial bindings: every work item decided; nobody on the model that failed its calibration code
        tbs = binding.all_task_bindings(e.store)
        code_tasks = [t for t in e.tasks() if t["kind"] == "code"]
        self.assertTrue(all(tbs[t["id"]]["intelligence_id"] != "sloppy" for t in code_tasks))
        d = controller.get_decision(e, tbs[code_tasks[0]["id"]]["decision_id"])
        self.assertTrue(d["evidence_ids"], "the selection read this objective's evidence")
        rank = {r["id"]: r for r in d["ranking"]}
        self.assertLess(rank["sloppy"]["quality"], rank["steady"]["quality"])
        roadmap = next(x for x in e.pending_decisions() if x["kind"] == "approve_roadmap") if e.pending_decisions() \
            else None
        self.assertIsNone(roadmap, "already approved by the gates helper")
        # Steady breaks after calibration: its code fails verification
        self.srv.broken.add("Steady")
        run_journey(e, max_rounds=60)
        self.assertEqual(e.meta["phase"], "accepted", e.meta.get("notice"))
        ex = oe.query(e.store, objective_id=oid, tenant_id="local", stage="objective_execution")
        steady_code_fail = [x for x in ex if x["intelligence_id"] == "steady" and x["task_kind"] == "code"
                            and x["verified"] is False]
        self.assertTrue(steady_code_fail, "execution evidence against the intelligence that failed")
        self.assertTrue(all(x["clean"] and x["failure"]["kind"] == "intelligence" for x in steady_code_fail))
        types = [x["event_type"] for x in e.store.events()]
        for name in ("intelligence.calibration.started", "intelligence.calibration.completed",
                     "intelligence.candidate_set.created", "review.started", "rework.created",
                     "production.verification.completed", "objective.completed"):
            self.assertIn(name, types, name)
        # the evidence moved the work: replaced or reselected, with the seat kept
        moved = [x for x in e.store.all("replacement") if x["from"] == "steady"] + \
            [x for x in e.store.events() if x["event_type"] in ("intelligence.reselection.triggered",
                                                               "intelligence.rerouted")]
        self.assertTrue(moved)
        for t in code_tasks:
            done_by = {c["model_id"] for c in e.store.all("call") if c.get("task_id") == t["id"]
                       and c.get("purpose") == "work"}
            self.assertIn("careful", done_by, f"{t['id']} was finished by the intelligence the evidence favoured")
        workers = {w["id"] for w in e.workers()}
        self.assertTrue({t["owner_worker_id"] for t in code_tasks} <= workers, "every seat kept")
        # different workers and different tasks on different intelligence, by evidence
        used = {b["intelligence_id"] for b in binding.all_task_bindings(e.store).values()}
        self.assertGreaterEqual(len(used), 2)
        # every important decision explains itself and replays from its own inputs
        for t in code_tasks:
            x = e.explain(t["id"])
            self.assertTrue(x["complete"], (t["id"], x["missing"]))
            self.assertTrue(x["chain"]["objective_calibration"])
            self.assertTrue(len(x["chain"]["selection_decision"]) >= 1)
        bad = [d["decision_id"] for d in e.decisions() if not controller.replay(e, d["decision_id"])["reproduced"]]
        self.assertEqual(bad, [])
        self.assertTrue(e.store.get("production_verification", "pv_1")["passed"])
        self.assertEqual(objective.state(e), "OBJECTIVE_CLOSED")
        self.assertTrue(e.store.verify_event_chain())
        e.close()

    def test_a_provider_outage_is_not_an_intelligence_failure(self):
        e = live_engine(self.tmp.path / "run", self.sup)
        oid = e.objective()["objective_id"]
        t = next(t for t in e.tasks() if t["kind"] == "code")
        work = controller.work_for_task(e, t)
        before = {r["id"]: r for r in controller.decide(e, work, "probe-before")["ranking"]}
        e.registry.set_fault("steady", offline=True)
        from cynqra.intelligence import IntelligenceError
        from cynqra import replacement
        for i in range(3):
            replacement.model_failed(e, e.task(t["id"]), IntelligenceError(
                "HTTPError: HTTP 503: Service Unavailable", model_id="steady"))
        evs = [x for x in oe.query(e.store, objective_id=oid, tenant_id="local") if x.get("provenance", {}).get(
            "source") == "call_failure" or (x.get("failure") or {}).get("kind") == "provider"]
        self.assertTrue(evs and all(not x["clean"] and x["verified"] is None for x in evs))
        e.registry.set_fault("steady", offline=False)
        e.registry.clear_health("steady")
        after = {r["id"]: r for r in controller.decide(e, work, "probe-after")["ranking"]}
        self.assertEqual(before["steady"]["quality"], after["steady"]["quality"],
                         "HTTP 503 changed nothing about the intelligence's evidenced quality")
        self.assertFalse([o for o in e.registry.outcomes("steady") if o["run_id"] == e.cid and not o["verified"]
                          and o["source"] == "project"])
        e.close()

    def test_objective_a_evidence_never_becomes_objective_b_evidence(self):
        a = live_engine(self.tmp.path / "a", self.sup)
        b = live_engine(self.tmp.path / "b", self.sup)
        c = live_engine(self.tmp.path / "c", self.sup, tenant="enterprise_c")
        oa, ob = a.objective()["objective_id"], b.objective()["objective_id"]
        self.assertNotEqual(oa, ob)
        self.assertTrue(oe.query(a.store, objective_id=oa, tenant_id="local"))
        t = next(t for t in b.tasks() if t["kind"] == "code")
        snap = controller.snapshot(b, controller.work_for_task(b, t))
        objective_items = [r for r in snap["evidence"] if r["src"] == "objective"]
        self.assertTrue(all(r["objective_id"] == ob for r in objective_items), "only B's own objective evidence")
        res = router.select(snap)
        row = next(r for r in res["rows"] if r["id"] == "careful")
        hist = row["per_kind"][0]["levels"]["historical"]
        self.assertGreater(hist["items"], 0, "A's verified work is a prior for B: historical, capped, never objective")
        self.assertNotIn("objective_verified", [u["level"] for u in row["per_kind"][0]["used"]
                                                if u["id"].startswith("o_")])
        tc = next(t for t in c.tasks() if t["kind"] == "code")
        snap_c = controller.snapshot(c, controller.work_for_task(c, tc))
        res_c = router.select(snap_c)
        other = [x for r in res_c["rows"] for k in r["per_kind"] for x in k["excluded"] if x["why"] == "tenant_isolation"]
        self.assertTrue(other or not [r for r in snap_c["evidence"] if r.get("tenant_id") != "enterprise_c"])
        used_c = [u for r in res_c["rows"] for k in r["per_kind"] for u in k["used"]]
        self.assertFalse([u for u in used_c if u["level"] == "historical"],
                         "enterprise C sees none of the local tenant's history")
        for x in (a, b, c):
            x.close()

    def test_a_material_objective_change_makes_a_version_with_an_inheritance_boundary(self):
        e = live_engine(self.tmp.path / "run", self.sup)
        e.run_until_idle()
        v1 = e.objective()["version"]
        e.request_objective_change({"success_criteria": "Recruiters see every candidate's next step in one view."})
        self.assertEqual(objective.state(e), "OBJECTIVE_PAUSED")
        approve(e, "objective_change")
        obj = e.objective()
        self.assertEqual(obj["version"], v1 + 1)
        vs = {v["version"]: v for v in objective.versions(e)}
        self.assertEqual(vs[v1]["status"], "superseded")
        self.assertEqual(vs[v1 + 1]["inheritance"]["mode"], "prior_only")
        self.assertEqual(objective.inheritance_map(e)[str(v1)]["mode"], "prior_only")
        t = next(t for t in e.tasks() if t["kind"] == "code")
        snap = controller.snapshot(e, controller.work_for_task(e, t))
        res = router.select(snap)
        levels = {u["level"] for r in res["rows"] for k in r["per_kind"] for u in k["used"]
                  if not u["id"].startswith("o_")}
        self.assertNotIn("objective_verified", levels, "v1's evidence is a prior for v2, never v2's own")
        self.assertEqual(objective.state(e), "OBJECTIVE_EXECUTING")
        e.close()

    def test_a_calibration_candidate_cannot_move_its_own_bar(self):
        e = live_engine(self.tmp.path / "run", self.sup)
        p = e.store.get(calibration.KIND, calibration.plan_id(e))
        it = next(i for i in p["items"] if i["kind"] == "code")
        real = calibration.verifier.run_checks

        def lowering_bar(kind, cand, out, task, objective):  # the candidate rewrites the item while it is tested
            it["spec"]["acceptance_criteria"] = ["anything passes"]
            return real(kind, cand, out, task, objective)
        calibration.verifier.run_checks = lowering_bar
        try:
            trial = calibration._trial(e, p, it, "sloppy", 9)
        finally:
            calibration.verifier.run_checks = real
        self.assertIsNone(trial["verified"], "no verdict counts once the item moved")
        self.assertEqual(trial["attribution"], "specification")
        e.close()

    def test_human_assisted_success_is_never_autonomous(self):
        e = live_engine(self.tmp.path / "run", self.sup)
        t = next(t for t in e.tasks() if t["kind"] == "code")
        d = e.decision("escalation", problem="retry?", recommendation="retry", risk="LOW", confidence="low", cost="c",
                       evidence=[], change="c", task_id=t["id"], source=t["owner_worker_id"])
        d.update(status="approved", resolved_by="founder", outcome_label="approved")
        e.store.put("decision", d["id"], d)
        ev = controller.record_task_evidence(e, e.task(t["id"]), verified=True, idempotency_key="after-help")
        self.assertEqual(ev["autonomy"], "human_assisted")
        self.assertIn(d["id"], ev["human_interventions"])
        e.close()

    def test_independent_review_for_high_risk_work(self):
        e = live_engine(self.tmp.path / "run", self.sup)
        t = next(t for t in e.tasks() if t["kind"] == "deploy")
        lead = t.get("reviewed_by") or next(w["id"] for w in e.workers() if w["role"] == "CTO")
        prod = controller.producer(e, t)[0]
        binding.bind(e, lead, e.registry.get(prod), reason="the reviewer on the producer's intelligence", by="test")
        got = controller.reviewer(e, t, lead)
        self.assertIsNotNone(got)
        self.assertNotEqual(got[0], prod, "the producer's intelligence does not verify its own work")
        d = controller.get_decision(e, e.store.get("verification_binding", t["id"])["decision_id"])
        self.assertEqual(d["purpose"], "independent_verification")
        self.assertIn(prod, [x["id"] for x in d["excluded_candidates"]])
        e.close()


class AuditApiTests(unittest.TestCase):
    """The founder's screens and tools read the control plane's own records over the local API."""

    def test_explain_replay_decisions_and_policies_over_http(self):
        import urllib.request
        from cynqra.server import App, make_server
        saved = no_model_env()
        tmp = TempDir()
        app = App(tmp.path)
        srv = make_server(app, 0)
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        threading.Thread(target=srv.serve_forever, daemon=True).start()

        def get(path):
            with urllib.request.urlopen(base + path, timeout=30) as r:
                return json.loads(r.read())
        try:
            e = app.engine
            e.create_company("Harbor Recruiting", "demo", "candidate_tracker")
            e.draft_objective(SCENARIO["messy"])
            e.submit_objective()
            engine_to_gates(e)
            t = next(t for t in e.tasks() if t["kind"] == "code")
            x = get(f"/api/explain/{t['id']}")
            self.assertEqual(x["task_id"], t["id"])
            self.assertTrue(x["chain"]["selection_decision"])
            ds = get(f"/api/intelligence/decisions?work_item={t['id']}")["decisions"]
            self.assertTrue(ds and all(d["work_item_id"] == t["id"] for d in ds))
            r = get(f"/api/decisions/{ds[0]['decision_id']}/replay")
            self.assertTrue(r["reproduced"] and r["from_snapshot_only"])
            names = {p["name"] for p in get("/api/policies")["policies"]}
            self.assertIn("selection", names)
            st = get("/api/state")
            self.assertTrue(st["intelligence_control"]["decisions"])
            self.assertEqual(st["objective_lifecycle"]["state"], "OBJECTIVE_EXECUTING")
        finally:
            srv.shutdown()
            srv.server_close()
            app.close()
            tmp.cleanup()
            restore_env(saved)


class PolicyContractTests(unittest.TestCase):
    def test_policies_are_versioned_and_discoverable(self):
        names = {p["name"] for p in policies.catalog()}
        self.assertTrue({"system", "authority", "objective", "selection", "risk", "budget", "verification",
                         "replacement", "calibration", "evidence", "inheritance", "isolation", "retention"} <= names)
        self.assertTrue(all(p["version"] and p["hash"] for p in policies.catalog()))
        b = policies.body("selection")
        b["tiers"]["HIGH"]["quality_floor"] = 0
        self.assertNotEqual(policies.body("selection")["tiers"]["HIGH"]["quality_floor"], 0,
                            "a caller can never change the rules in place")
        from cynqra import performance, replacement
        self.assertIs(performance.THRESHOLDS["acceptance_rate"], policies.body("replacement")["thresholds"]["acceptance_rate"])
        self.assertEqual(replacement.MAX_REPLACEMENTS, policies.body("replacement")["max_replacements"])

    def test_the_documents_describe_the_implemented_loop(self):
        arch = (POC.parent / "docs" / "6_PHASED_ARCHITECTURE.md").read_text(encoding="utf-8")
        for word in ("SelectionDecision", "controller.py", "objective_evidence.py", "calibration.py", "policies.py"):
            self.assertIn(word, arch)


if __name__ == "__main__":
    unittest.main()
