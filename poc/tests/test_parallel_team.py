"""The team works at the same time, as a company does.

Each round every worker with work it can do now takes one piece of it; whoever finishes hands over, whoever is stuck
raises a Blocker to the colleague it concerns, and they pick those up in the next round. The slow part, the model
call, happens without holding the run, so workers on hosted intelligence think side by side; recording their results
is serialized.
"""
from __future__ import annotations

import os
import threading
import time
import unittest

from helpers import SCENARIO, TempDir, engine_to_gates, engine_to_running, no_model_env, restore_env, run_journey
from test_workforce import Servers

from cynqra.engine import Engine
from cynqra.intelligence_layer import IntelligenceSupply

THINK_S = 1.0


class ScriptedTeamTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_everyone_whose_inputs_are_ready_works_in_the_same_round(self):
        e = engine_to_running(self.tmp.path, scenario="restaurant_forecast")
        rounds = []
        for _ in range(200):
            r = e.step()
            if r["did"] == "idle":
                if not e.pending_decisions() or e.meta["phase"] == "accepted":
                    break
                e.decide(e.pending_decisions()[0]["id"], "approve")
                continue
            rounds.append(r)
        widest = max(rounds, key=lambda r: len(r.get("actions") or [r]))
        acting = {a["task"] for a in widest["actions"]}
        self.assertGreaterEqual(len(acting), 4, f"after the brief, several experts start at once: {widest}")
        owners = [e.task(t)["owner_worker_id"] for t in acting]
        self.assertEqual(len(owners), len(set(owners)), "each worker does one thing at a time")
        self.assertEqual(e.meta["phase"], "accepted", e.meta.get("notice"))
        e.close()


class ParallelCallsTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        os.environ["FAKE_LLAMA_THINK_S"] = str(THINK_S)
        self.tmp = TempDir()
        self.srv = Servers(1, self.tmp.path)
        self.supply = IntelligenceSupply(self.tmp.path / "control")
        self.supply.connect({"type": "openai_compatible", "name": "Server", "endpoint": self.srv.urls[0] + "/v1",
                             "auth": {"method": "none"}, "models": ["Model A"], "price_per_m": [0.2, 0.8]})

    def tearDown(self):
        self.srv.close()
        self.supply.close()
        self.tmp.cleanup()
        os.environ.pop("FAKE_LLAMA_THINK_S", None)
        restore_env(self.saved)

    def test_workers_think_side_by_side_and_the_run_stays_consistent(self):
        e = Engine(self.tmp.path / "run", supply=self.supply)
        e.create_company("Harbor Recruiting", "live")
        e.draft_objective(SCENARIO["messy"])
        e.set_guardrails(budget_usd=5, time_value_per_hour=10)
        e.submit_objective()
        engine_to_gates(e)
        spans = {}

        def call(wid):
            with e.lock:  # as a worker's piece of work holds the run, except while its model thinks
                t0 = time.time()
                out = e.invoke(wid, {"prompt": "Plan the work for this organization", "want_json": True})
                spans[wid] = (t0, time.time(), out["error"])

        threads = [threading.Thread(target=call, args=(w,)) for w in ("w_cto", "w_pm", "w_eng_a", "w_eng_b")]
        t0 = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        took = time.time() - t0
        self.assertTrue(all(err is None for _, _, err in spans.values()), spans)
        self.assertLess(took, 4 * THINK_S * 0.75, f"four calls of {THINK_S} s overlapped: {took:.1f} s")
        run_journey(e, max_rounds=40)
        self.assertEqual(e.meta["phase"], "accepted", e.meta.get("notice"))
        e.close()


if __name__ == "__main__":
    unittest.main()
