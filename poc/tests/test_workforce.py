"""The workforce: workers bound to intelligence from the Intelligence Registry, every call metered, every
verification learned from, and a failing intelligence replaced by another that continues the work.

Three provider connections (OpenAI-compatible), each to its own fake_llama_server.py process on its own port (a
test double of llama-server: its answers come from tests/fake_model.py and are never a result), each offering one
model. The real demonstration runs the same code on real models (.github/workflows/cynqra-workforce.yml).
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import unittest
import urllib.request

from helpers import POC, SCENARIO, TempDir, engine_to_gates, no_model_env, restore_env, run_journey

from cynqra import binding
from cynqra.engine import Engine
from cynqra.intelligence_layer import IntelligenceSupply, SupplyError
from cynqra.intelligence_layer.router import estimate, rank

FAKE = POC / "tests" / "fake_llama_server.py"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Servers:
    def __init__(self, n: int, tmp):
        self.procs, self.urls = [], []
        model = tmp / "m.gguf"
        model.write_text("fake", encoding="utf-8")
        for _ in range(n):
            port = free_port()
            self.procs.append(subprocess.Popen([sys.executable, str(FAKE), "-m", str(model), "--port", str(port)],
                                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            self.urls.append(f"http://127.0.0.1:{port}")
        for u in self.urls:
            for _ in range(100):
                try:
                    urllib.request.urlopen(u + "/health", timeout=1)
                    break
                except OSError:
                    time.sleep(0.05)

    def close(self):
        for p in self.procs:
            p.kill()
            p.wait()


class WorkforceTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()
        self.srv = Servers(3, self.tmp.path)
        self.supply = IntelligenceSupply(self.tmp.path / "control")
        self.reg = self.supply.registry
        self.conns = []
        for i, (name, price) in enumerate([("Model A", 0.2), ("Model B", 0.6), ("Model C", 2.0)]):
            out = self.supply.connect({"type": "openai_compatible", "name": f"Server {i}",
                                       "endpoint": self.srv.urls[i] + "/v1", "auth": {"method": "none"},
                                       "models": [name], "price_per_m": [price, price * 4]})
            self.conns.append(out["connection"]["id"])

    def tearDown(self):
        self.srv.close()
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

    def test_the_registry_holds_facts_and_the_supply_refuses_what_it_cannot_run(self):
        m = self.reg.get("model-a")
        self.assertEqual((m["connection_id"], m["ref"], m["price_in"]), (self.conns[0], "Model A", 0.2))
        self.assertNotIn("capability", str(m).lower(), "no hand-made scores")
        self.assertNotIn("api_key", str(m), "an intelligence holds no credential")
        with self.assertRaises(SupplyError):
            self.supply.connect({"type": "mystery", "endpoint": "http://x"})
        with self.assertRaises(SupplyError):  # a local llama server needs the app's runtime
            self.supply.connect({"type": "local", "server": "llama", "models": ["not-in-the-catalog"]})
        self.assertEqual(self.reg.availability(m), (True, "available"))
        os.environ.pop("HF_TOKEN", None)
        hf = self.supply.connections.create({"type": "openai_compatible", "name": "Hugging Face",
                                             "endpoint": "https://router.huggingface.co/v1",
                                             "auth": {"method": "env", "env_var": "HF_TOKEN"}})
        glm = self.reg.register({"ref": "zai-org/GLM-4.7", "name": "GLM-4.7"}, connection_id=hf["id"])
        self.assertEqual(self.reg.availability(glm), (False, "HF_TOKEN is not set"))

    def test_selection_follows_measured_outcomes_not_names(self):
        rows = rank(self.reg, ["code"], 10.0)
        self.assertEqual([r["model"] for r in rows], ["Model A", "Model B", "Model C"], "no history: the cheapest first")
        self.assertTrue(all(r["by_kind"][0]["p_attempt"] == 0.5 for r in rows), "the same prior for every model")
        for i in range(4):  # A fails its code, C passes
            for mid, ok in (("model-a", False), ("model-c", True)):
                self.reg.record_outcome(mid, role="Engineer", task_kind="code", task_id=f"t{i}", run_id="r", attempt=1,
                                        verified=ok, usd=0.01, seconds=60, tokens=6000)
        e_a = estimate(self.reg, self.reg.get("model-a"), "code", 10.0)
        e_c = estimate(self.reg, self.reg.get("model-c"), "code", 10.0)
        self.assertLess(e_a["p_attempt"], 0.3)
        self.assertGreater(e_c["p_attempt"], 0.7)
        self.assertEqual(rank(self.reg, ["code"], 10.0)[0]["model"], "Model C", "measured success outweighs price")
        self.assertEqual(rank(self.reg, ["document"], 10.0)[0]["model"], "Model C",
                         "a kind never seen borrows the model's overall record")

    def test_live_mode_without_any_model_is_refused_before_anything_is_written(self):
        for cid in self.conns:
            self.supply.remove_connection(cid)
        self.assertFalse(self.reg.available(), "removing a connection retires what it offered")
        self.assertTrue(self.reg.models(include_retired=True), "their measured record is kept")
        e = Engine(self.tmp.path / "none", supply=self.supply)
        with self.assertRaises(Exception) as ctx:
            e.create_company("Harbor Recruiting", "live")
        self.assertIn("needs intelligence", str(ctx.exception))
        self.assertEqual(e.meta["phase"], "new")
        e.close()

    def test_a_run_staffs_workers_from_the_registry_and_meters_every_call(self):
        e = self.engine()
        view = e.workforce_view()
        self.assertTrue(view["active"])
        self.assertEqual({w["model"] for w in view["workers"]}, {"Model A"}, "no history: the cheapest model everywhere")
        self.assertTrue(all(len(w["candidates"]) == 3 for w in view["workers"]), "every choice keeps its table")
        self.assertEqual(len(view["ledger"]["allocated"]), len(e.tasks()))
        run_journey(e)
        self.assertEqual(e.meta["phase"], "accepted")
        calls = self.reg.calls("model-a")
        self.assertTrue(calls and all(c["usd"] > 0 for c in calls), "every call is priced from its real tokens")
        self.assertAlmostEqual(e.workforce_view()["ledger"]["spent_total"], sum(c["usd"] for c in calls), places=4)
        outs = self.reg.outcomes("model-a")
        self.assertEqual({o["task_kind"] for o in outs} >= {"document", "code"}, True)
        self.assertTrue(all(o["run_id"] == e.cid for o in outs))
        e.close()

    def test_a_model_that_goes_offline_is_diagnosed_not_replaced(self):
        """The provider's side is not the AI's fault: the worker keeps its AI, the CEO is asked once whether a
        stand-in may cover the wait, and each worker returns to its own AI when it answers again."""
        e = self.engine()
        before = sorted(w["id"] for w in e.workers())
        self.reg.set_fault("model-a", offline=True)  # after staffing: every worker is on Model A
        e.run_until_idle()
        stopped = [x for x in e.store.events() if x["event_type"] == "worker.stopped"]
        self.assertTrue(stopped and all(x["payload"]["cause"] == "outage" for x in stopped), "diagnosed first")
        pend = [d for d in e.pending_decisions() if d["kind"] == "provider_outage"]
        self.assertEqual(len(pend), 1, "the CEO is asked once, not once per worker")
        self.assertIn("not at fault", pend[0]["problem"])
        self.assertIn("per million tokens", pend[0]["recommendation"], "with what the stand-in costs")
        self.assertFalse(e.store.all("replacement"), "nothing was replaced")
        self.assertTrue(all(binding.intelligence_of(e.store, w["id"]) == "model-a" for w in e.workers()))
        self.assertTrue(any(t["status"] == "WAITING" for t in e.tasks()))
        e.decide(pend[0]["id"], "approve")  # the CEO lets a stand-in cover the wait
        covered = {r["worker_id"] for r in e.store.all("replacement")}
        self.assertTrue(covered and all(binding.intelligence_of(e.store, w) != "model-a" for w in covered))
        self.reg.set_fault("model-a", offline=False)  # the provider answers again
        e.step()
        self.assertTrue(all(binding.intelligence_of(e.store, w["id"]) == "model-a" for w in e.workers()),
                        "each worker is back on its own AI")
        self.reg.set_fault("model-a", offline=True)  # and down again: the CEO's answer still holds
        run_journey(e, max_rounds=40)
        self.assertEqual(e.meta["phase"], "accepted", e.meta.get("notice"))
        reps = e.store.all("replacement")
        self.assertTrue(reps and all(r["from"] == "model-a" and r["temporary"] for r in reps))
        self.assertTrue({r["to"] for r in reps} <= {"model-b", "model-c"})
        self.assertEqual(sorted(w["id"] for w in e.workers()), before, "every worker kept its identity")
        evals = [x for x in e.store.all("evaluation") if x["decision"] == "stand_in"]
        self.assertTrue(evals and all(x["regression_check"] for x in evals), "the stand-in passed a regression check")
        self.assertTrue(any(n["kind"] == "stand_in" for n in e.store.all("ceo_notice")), "and the CEO was told")
        self.assertEqual([d["kind"] for d in e.store.all("decision")].count("provider_outage"), 1,
                         "asked once for the whole run")
        e.close()

    def test_the_ceo_may_choose_to_wait_out_an_outage(self):
        e = self.engine()
        self.reg.set_fault("model-a", offline=True)
        e.run_until_idle()
        d = next(d for d in e.pending_decisions() if d["kind"] == "provider_outage")
        e.decide(d["id"], "reject", "wait for it")
        waiting = [t for t in e.tasks() if t["status"] == "WAITING"]
        self.assertTrue(waiting and all(t["waiting"]["until"] > time.time() for t in waiting))
        self.assertEqual(e.step()["did"], "idle")
        self.reg.set_fault("model-a", offline=False)  # the provider is back, and the wait is over
        for t in waiting:
            t["waiting"]["until"] = 0
            e.save_task(t)
        run_journey(e, max_rounds=40)
        self.assertEqual(e.meta["phase"], "accepted", e.meta.get("notice"))
        self.assertFalse(e.store.all("replacement"), "no AI was replaced or stood in")
        self.assertTrue(all(binding.intelligence_of(e.store, w["id"]) == "model-a" for w in e.workers()))
        e.close()

    def test_no_credit_goes_to_the_ceo_and_replaces_nothing(self):
        e = self.engine()
        gw = self.supply.gateway
        real = gw.invoke
        state = {"broke": True}

        def invoke(mid, request, pinned_version=None):
            if mid == "model-a" and state["broke"]:
                return {"text": "", "tokens_in": 0, "tokens_out": 0, "estimated": False, "latency_s": 0.1,
                        "model": "Model A", "model_id": mid,
                        "error": "HTTPError: HTTP 402: You have exceeded your monthly included credits"}
            return real(mid, request, pinned_version=pinned_version)

        gw.invoke = invoke
        try:
            e.run_until_idle()
            pend = [d for d in e.pending_decisions() if d["kind"] == "provider_account"]
            self.assertEqual(len(pend), 1)
            self.assertIn("no credit", pend[0]["problem"])
            self.assertFalse(e.store.all("replacement"))
            self.assertFalse([d for d in e.pending_decisions() if d["kind"] == "provider_outage"])
            state["broke"] = False  # the CEO added credit
            run_journey(e, max_rounds=40)
        finally:
            gw.invoke = real
        self.assertEqual(e.meta["phase"], "accepted", e.meta.get("notice"))
        self.assertFalse(e.store.all("replacement"), "nothing was replaced")
        self.assertTrue(all(binding.intelligence_of(e.store, w["id"]) == "model-a" for w in e.workers()))
        e.close()

    def test_why_a_call_failed(self):
        from cynqra.replacement import diagnose
        for text, cause in [("HTTP 402: You have exceeded your monthly included credits", "no_credit"),
                            ("You exceeded your current quota, please check your plan and billing", "no_credit"),
                            ("HTTP 401: Invalid API key", "access"), ("HTTP 429: Too Many Requests", "rate_limit"),
                            ("The read operation timed out", "timeout"), ("HTTP 503: Service Unavailable", "outage"),
                            ("could not reach https://router.huggingface.co: connection refused", "outage"),
                            ("Model A is offline (a fault set on it in the model registry)", "outage"),
                            ("Model A is retired: superseded", "withdrawn"),
                            ("Model A changed version to 2 and failed its regression check", "withdrawn"),
                            # found in the audit: a port number or a laptop's memory is not an account problem
                            ("network error: could not reach http://127.0.0.1:40312: connection refused", "outage"),
                            ("RuntimeError: the model on this machine could not start: insufficient memory", "outage"),
                            ("HTTP 429 from provider: You have exceeded your rate limit", "rate_limit"),
                            ("HTTP 429 from provider: insufficient_quota, check your plan and billing", "no_credit"),
                            ("HTTP 404 from provider: model claude-2 not found", "withdrawn"),
                            ("HTTP 504 from provider: gateway timeout", "timeout"),
                            ("HF_TOKEN is not set", "access")]:
            self.assertEqual(diagnose(text), cause, text)

    def test_a_task_is_rerouted_to_a_peer_on_a_better_model(self):
        e = self.engine()
        binding.bind(e, "w_eng_b", self.reg.get("model-c"), reason="the test's choice", by="test")  # two models
        self.supply.remove_connection(self.conns[1])  # Model B is gone
        self.reg.set_fault("model-a", max_reply=40)  # Engineer A's model cannot finish its code
        run_journey(e, max_rounds=40)
        self.assertEqual(e.meta["phase"], "accepted", e.meta.get("notice"))
        moved = [r for r in e.store.all("replacement") if r.get("rerouted")]
        self.assertTrue(moved, [x["decision"] for x in e.store.all("evaluation")])
        t = e.task(moved[0]["task_id"])
        self.assertEqual((moved[0]["worker_id"], t["owner_worker_id"]), ("w_eng_a", "w_eng_b"))
        ev = [x for x in e.store.all("evaluation") if x["decision"] == "reroute"][0]
        self.assertEqual((ev["model_id"], ev["to_worker"]), ("model-a", "w_eng_b"),
                         "the task moved to a peer; Engineer A kept its identity and, then, its model")
        e.close()

    def test_the_dollar_budget_is_the_hard_stop(self):
        e = self.engine(budget_usd=0.003)
        f = e.store.get("forecast", "current")
        self.assertGreater(f["layers"]["inference"]["usd"], 0)
        self.assertFalse(f["fits"], "the roadmap gate showed the overrun before any work started")
        run_journey(e, max_rounds=60)
        stops = [d for d in e.store.all("decision") if d["kind"] == "budget_breaker"]
        self.assertTrue(stops, "the breaker opened on dollars")
        self.assertEqual(e.meta["phase"], "accepted", "each approval raised the budget and work went on")
        ec = e.final_report()["economics"]
        self.assertGreater(ec["total_actual"], 0.003)
        self.assertEqual(set(ec["layers"]), {"inference", "tools", "infrastructure", "verification"})
        e.close()

    def test_evidence_decides_keep_or_replace(self):
        from cynqra import replacement
        e = self.engine()
        t = e.task("t_03")
        r = replacement.evaluate(e, t, "a test asks", forced=False)
        self.assertEqual(r["did"], "kept", "no alternative is expected to do better than the cheapest untried model")
        self.assertEqual(e.store.all("evaluation")[-1]["decision"], "keep")
        for i in range(4):  # Model A's code keeps failing verification; Model C's passes
            for mid, ok in (("model-a", False), ("model-c", True)):
                self.reg.record_outcome(mid, role="Engineer", task_kind="code", task_id=f"x{i}", run_id="r",
                                        attempt=1, verified=ok, usd=0.001, seconds=30, tokens=3000)
        r = replacement.evaluate(e, e.task("t_03"), "acceptance rate under the threshold", forced=False)
        self.assertEqual((r["did"], r["to"]), ("replaced", "model-c"))
        ev = e.store.all("evaluation")[-1]
        self.assertIn("verified code attempt(s) on record", ev["regression_check"], "its record was the evidence")
        e.close()

    def test_the_regression_gate(self):
        cid = self.conns[0]
        m = self.reg.register({"ref": "fake-v", "name": "Versioned", "version": "1"}, connection_id=cid)
        self.assertEqual(m["regression"]["status"], "unverified")
        self.reg.set_regression("versioned", False, "failed its calibration code")
        self.assertEqual(self.reg.availability(self.reg.get("versioned")), (False, "failed its regression check"))
        m = self.reg.register({"ref": "fake-v", "name": "Versioned", "version": "2"}, connection_id=cid)
        self.assertEqual((m["regression"]["status"], m["regression"]["previous_version"]), ("unverified", "1"))
        self.assertTrue(self.reg.availability(m)[0], "a new version gets its own chance")

    def test_a_model_that_cannot_finish_is_replaced_and_its_successor_inherits_the_work(self):
        e = self.engine()
        self.reg.set_fault("model-a", max_reply=40)  # replies cut to 40 tokens: its code never fits
        run_journey(e, max_rounds=40)
        self.assertEqual(e.meta["phase"], "accepted", e.meta.get("notice"))
        rep = e.store.all("replacement")[0]
        self.assertEqual(rep["from"], "model-a")
        self.assertIn("output limit", rep["reason"])
        self.assertIn("workspace files", rep["inherited"])
        t = e.task(rep["task_id"])
        self.assertEqual(t["status"], "VERIFIED")
        self.assertEqual(t["replacements"], 1)
        handover = [r for r in e.store.all("call") if r["task_id"] == t["id"]]
        self.assertTrue(any(c.get("model_id") == rep["to"] for c in handover), "the successor did the rest")
        failed = [o for o in self.reg.outcomes("model-a") if not o["verified"]]
        self.assertTrue(failed, "the failure is part of Model A's record")
        note = next(n for n in e.store.all("ceo_notice") if n["kind"] == "intelligence_replaced")
        self.assertIn("could not do this role's work", note["detail"], "the CEO is told why")
        self.assertIsNotNone(note["usd_difference"], "and what the better AI costs against the old one")
        self.assertIn("per million tokens, against", note["detail"], "its price against the old one's")
        self.assertFalse(e.pending_decisions(), "informed, not asked: the budget covered it")
        L = e.workforce_view()["ledger"]
        moved = [x for x in L["events"] if x["what"] == "reallocated"]
        self.assertTrue(moved and moved[0]["from"] == "model-a", "the budget moved with the work")
        e.close()


if __name__ == "__main__":
    unittest.main()
