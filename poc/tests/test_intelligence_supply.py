"""The Intelligence Supply Architecture V1, held to its locked decisions and its ten demonstrations.

    worker ≠ intelligence ≠ provider connection ≠ credential

Three provider connections of three types: an OpenAI-compatible API and a local/self-hosted server (each its own
fake_llama_server.py process) and the Anthropic API (tests/test_adapter.py's FakeProvider, which speaks the Messages
API). The test doubles' answers come from tests/fake_model.py and are never a result; the real demonstration runs
the same code on real models (.github/workflows/cynqra-workforce.yml).

  1 connect multiple sources            test_three_provider_types_connect_and_discover
  2 discover and register models        test_three_provider_types_connect_and_discover, ..._retires_what_is_gone
  3 create workers                      test_workers_hold_no_intelligence_and_many_can_share_one
  4 evaluate                            test_a_better_intelligence_is_detected_and_the_worker_rebound
  5 different models, different workers test_different_workers_are_bound_to_different_intelligence_by_evidence
  6 execute real tasks                  test_a_run_executes_through_the_gateway_and_is_metered
  7 record metrics                      test_a_run_executes_through_the_gateway_and_is_metered
  8 detect a better model               test_a_better_intelligence_is_detected_and_the_worker_rebound
  9 reassign preserving identity        test_a_better_..., test_a_new_version_..., test_the_fallback_...
 10 audit events                        test_every_supply_decision_is_an_audit_event
"""
from __future__ import annotations

import json
import os
import stat
import unittest

from helpers import SCENARIO, TempDir, engine_to_gates, no_model_env, restore_env, run_journey
from test_adapter import FakeProvider
from test_workforce import Servers

from cynqra import binding, replacement
from cynqra.engine import Engine
from cynqra.intelligence_layer import IntelligenceSupply, SupplyError
from cynqra.intelligence_layer.adapters import ProviderAdapter
from cynqra.intelligence_layer.router import rank

KEY = "sk-ant-test-not-real-7f3a"  # a test value, kept in the secrets file like a founder's key


class SupplyBase(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()
        self.srv = Servers(2, self.tmp.path)
        self.anthropic = FakeProvider()
        self.supply = IntelligenceSupply(self.tmp.path / "control")
        self.reg = self.supply.registry
        self.c_api = self.supply.connect({"type": "openai_compatible", "name": "Fast API",
                                          "endpoint": self.srv.urls[0] + "/v1", "auth": {"method": "none"},
                                          "models": ["Model A"], "price_per_m": [0.2, 0.8]})
        self.c_ant = self.supply.connect({"type": "anthropic", "name": "Anthropic", "endpoint": self.anthropic.base,
                                          "auth": {"method": "secret", "secret": KEY},
                                          "models": ["claude-sonnet-5"], "price_per_m": [3.0, 15.0]})
        self.c_loc = self.supply.connect({"type": "local", "server": "endpoint", "name": "Team server",
                                          "endpoint": self.srv.urls[1] + "/v1", "auth": {"method": "none"},
                                          "models": ["Local B"], "machine_usd_per_hour": 0.1})

    def tearDown(self):
        self.srv.close()
        self.anthropic.close()
        self.supply.close()
        self.tmp.cleanup()
        restore_env(self.saved)

    def engine(self, budget_usd=5.0) -> Engine:
        e = Engine(self.tmp.path / "run", supply=self.supply)
        e.create_company("Harbor Recruiting", "live")
        e.draft_objective(SCENARIO["messy"])
        e.set_guardrails(budget_usd=budget_usd, time_value_per_hour=10)
        e.submit_objective()
        return engine_to_gates(e)

    def record(self, model_id, kind, ok, n=5):
        for i in range(n):
            self.reg.record_outcome(model_id, role="Engineer", task_kind=kind, task_id=f"{kind}{i}", run_id="history",
                                    attempt=1, verified=ok, usd=0.001, seconds=30, tokens=3000)


class SupplyTests(SupplyBase):
    def test_three_provider_types_connect_and_discover(self):
        conns = {c["type"]: c for c in self.supply.snapshot()["connections"]}
        self.assertEqual(set(conns), {"openai_compatible", "anthropic", "local"})
        self.assertTrue(all(c["status"] == "connected" for c in conns.values()), conns)
        by_conn = {m["connection_id"]: m for m in self.reg.models()}
        self.assertEqual(by_conn[self.c_api["connection"]["id"]]["name"], "Model A")
        self.assertEqual(by_conn[self.c_ant["connection"]["id"]]["price_in"], 3.0)
        self.assertTrue(by_conn[self.c_loc["connection"]["id"]]["local"])
        self.assertEqual(len(self.reg.available()), 3)

    def test_credentials_live_only_in_the_secrets_layer(self):
        db = (self.tmp.path / "control" / "control.db").read_bytes()
        self.assertNotIn(KEY.encode(), db, "the control plane's database never holds a key")
        self.assertNotIn(KEY, json.dumps(self.supply.snapshot()), "nothing the product shows reveals it")
        secrets = self.tmp.path / "control" / "secrets" / "credentials.json"
        self.assertIn(KEY, secrets.read_text())
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(secrets.stat().st_mode), 0o600)
        m = next(x for x in self.reg.models() if x["name"] == "claude-sonnet-5")
        self.assertNotIn("credential", json.dumps(m), "an intelligence refers to its connection, not a key")
        out = self.supply.gateway.invoke(m["id"], {"prompt": "Plan the work for this organization", "want_json": True})
        self.assertIsNone(out["error"])
        req = self.anthropic.requests[-1]
        self.assertEqual((req["path"], req["headers"]["x-api-key"]), ("/v1/messages", KEY),
                         "the gateway resolved the key for this one call")

    def test_bedrock_is_designed_for_not_implemented(self):
        types = {t["type"]: t for t in self.supply.snapshot()["provider_types"]}
        self.assertEqual({t for t, d in types.items() if d["implemented"]}, {"openai_compatible", "anthropic", "local"})
        self.assertFalse(types["bedrock"]["implemented"])
        with self.assertRaises(SupplyError):
            self.supply.connect({"type": "bedrock", "region": "us-east-1"})
        with self.assertRaises(SupplyError):
            self.supply.connect({"type": "demo_script"})  # a demo script is not a provider

    def test_a_new_adapter_plugs_in_without_touching_workers_registry_or_router(self):
        url = self.srv.urls[0] + "/v1"

        class Mirror(ProviderAdapter):  # a provider type this build never shipped
            type, title, auth_methods = "mirror", "Mirror", ("none",)

            def discover(self, conn, secret):
                return [{"ref": "mirror-1", "name": "Mirror 1", "provider": "mirror", "price_in": 0.05, "price_out": 0.1}]

            def route(self, conn, secret, entry):
                return {"kind": "local", "label": entry["ref"], "local": False, "CYNQRA_LOCAL_BASE_URL": url}

        self.supply.adapters["mirror"] = Mirror()
        out = self.supply.connect({"type": "mirror", "name": "Mirror", "auth": {"method": "none"}})
        mid = out["intelligence"][0]["id"]
        self.assertIsNone(self.supply.gateway.invoke(mid, {"prompt": "Plan the work for this organization"})["error"])
        self.assertIn("Mirror 1", [r["model"] for r in rank(self.reg, ["code"], 10.0)], "the router ranks it as is")

    def test_discovery_retires_what_is_gone_and_keeps_its_record(self):
        cid = self.c_api["connection"]["id"]
        self.record("model-a", "code", True, n=2)
        self.supply.connections.update(cid, {"models": ["Model A2"]})
        self.supply.discover(cid)
        old = self.reg.get("model-a")
        self.assertEqual(old["status"], "retired")
        self.assertFalse(self.reg.availability(old)[0])
        self.assertEqual(len(self.reg.outcomes("model-a")), 2, "its measured record is kept")
        self.assertIn("Model A2", [m["name"] for m in self.reg.available()])
        out = self.supply.gateway.invoke("model-a", {"prompt": "x"})
        self.assertIn("retired", out["error"], "the gateway does not call a retired intelligence")


class WorkforceOnTheSupplyTests(SupplyBase):
    def test_workers_hold_no_intelligence_and_many_can_share_one(self):
        e = self.engine()
        for w in e.workers():
            self.assertFalse({"model_id", "model", "api_key", "credentials", "intelligence_id"} & set(w), w)
        bound = binding.all_bindings(e.store)
        workers = [w["id"] for w in e.workers()]
        self.assertEqual(set(workers) <= set(bound), True, "every worker is bound")
        shared = {}
        for wid in workers:
            shared.setdefault(bound[wid]["intelligence_id"], []).append(wid)
        self.assertTrue(any(len(ws) > 1 for ws in shared.values()), "one intelligence powers several workers")
        self.assertTrue(all(bound[w]["candidates"] for w in workers), "each binding keeps the router's table")
        e.close()

    def test_different_workers_are_bound_to_different_intelligence_by_evidence(self):
        self.record("model-a", "code", True)
        self.record("model-a", "document", False)
        self.record("claude-sonnet-5", "document", True)
        self.record("claude-sonnet-5", "code", False)
        self.record("local-b", "document", False)
        self.record("local-b", "code", False)
        e = self.engine()
        bound = {w["id"]: e.model_of(w["id"]) for w in e.workers()}
        self.assertEqual({bound["w_eng_a"], bound["w_eng_b"]}, {"model-a"}, "the engineers write code")
        self.assertEqual(bound["w_pm"], "claude-sonnet-5", "the PM writes documents")
        self.assertGreaterEqual(len(set(bound.values())), 2)
        e.close()

    def test_a_run_executes_through_the_gateway_and_is_metered(self):
        self.record("model-a", "code", True)
        self.record("model-a", "document", False)
        self.record("claude-sonnet-5", "document", True)
        self.record("claude-sonnet-5", "code", False)
        e = self.engine()
        run_journey(e, max_rounds=40)
        self.assertEqual(e.meta["phase"], "accepted", e.meta.get("notice"))
        used = {c["model_id"] for c in self.reg.calls() if c["run_id"] == e.cid}
        self.assertGreaterEqual(len(used), 2, "real calls on more than one intelligence")
        self.assertTrue(any(r["path"] == "/v1/messages" for r in self.anthropic.requests), "through the Anthropic adapter")
        outs = [o for o in self.reg.outcomes() if o["run_id"] == e.cid]
        self.assertTrue(outs and {o["model_id"] for o in outs} <= used, "every verification is on the record")
        spent = sum(c["usd"] for c in self.reg.calls() if c["run_id"] == e.cid)
        self.assertAlmostEqual(e.workforce_view()["ledger"]["spent_total"], spent, places=4)
        e.close()

    def test_a_better_intelligence_is_detected_and_the_worker_rebound(self):
        e = self.engine()
        eng = e.worker("w_eng_a")
        first = e.model_of("w_eng_a")
        better = next(m["id"] for m in self.reg.available() if m["id"] != first)
        self.record(first, "code", False)
        self.record(better, "code", True)
        r = replacement.evaluate(e, e.task("t_03"), "acceptance rate under the threshold", forced=False)
        self.assertEqual((r["did"], r["to"]), ("replaced", better))
        b = binding.current(e.store, "w_eng_a")
        self.assertEqual((b["intelligence_id"], b["history"][-1]["intelligence_id"]), (better, first))
        self.assertEqual(e.worker("w_eng_a"), eng, "the worker's identity, role and history are untouched")
        ev = [x for x in e.store.events() if x["event_type"] == "worker.intelligence_bound"
              and x["aggregate_id"] == "w_eng_a"][-1]
        self.assertEqual((ev["payload"]["previous"], ev["payload"]["intelligence_id"]), (first, better))
        e.close()

    def test_a_new_version_is_regression_checked_before_the_worker_continues(self):
        e = self.engine()
        mid = e.model_of("w_eng_a")
        entry = self.reg.get(mid)
        self.reg.register({"ref": entry["ref"], "name": entry["name"], "version": "2"},
                          connection_id=entry["connection_id"])
        self.assertEqual(self.reg.get(mid)["regression"]["status"], "unverified")
        out = e.invoke("w_eng_a", {"prompt": "Plan the work for this organization", "want_json": True})
        self.assertIsNone(out["error"])
        b = binding.current(e.store, "w_eng_a")
        self.assertEqual((b["intelligence_id"], b["version"]), (mid, "2"), "the same worker, pinned to the new version")
        changed = [x for x in e.store.events() if x["event_type"] == "intelligence.version_changed"]
        self.assertTrue(changed and changed[-1]["payload"]["passed"])
        e.close()

    def test_the_fallback_is_preferred_when_an_intelligence_goes_down(self):
        e = self.engine()
        before = sorted(w["id"] for w in e.workers())
        primary = e.model_of("w_eng_a")
        fallback = next(m["id"] for m in self.reg.available() if m["id"] != primary and m["name"] == "Local B"
                        ) if primary != "local-b" else "model-a"
        self.reg.set_fallback(primary, fallback)
        self.reg.set_fault(primary, offline=True)
        run_journey(e, max_rounds=40)
        self.assertEqual(e.meta["phase"], "accepted", e.meta.get("notice"))
        reps = [r for r in e.store.all("replacement") if r["from"] == primary]
        self.assertTrue(reps and all(r["to"] == fallback for r in reps), reps)
        self.assertEqual(sorted(w["id"] for w in e.workers()), before, "no worker was created or lost")
        e.close()

    def test_every_supply_decision_is_an_audit_event(self):
        e = self.engine()
        control = {x["event_type"] for x in self.supply.store.events()}
        self.assertTrue({"connection.created", "connection.checked", "intelligence.registered"} <= control, control)
        self.supply.registry.set_fault("model-a", offline=True)
        self.assertIn("intelligence.fault_set", {x["event_type"] for x in self.supply.store.events()})
        run = {x["event_type"] for x in e.store.events()}
        self.assertIn("worker.intelligence_bound", run)
        e.close()


if __name__ == "__main__":
    unittest.main()
