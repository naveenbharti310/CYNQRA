"""The workforce: workers staffed from the model registry, every call metered, every verification learned from,
and a failing model replaced by another that continues the work.

Three models are registered as openai_compatible servers, each one its own fake_llama_server.py process on its
own port (a test double of llama-server: its answers come from tests/fake_model.py and are never a result). The
real demonstration runs the same code on real models (.github/workflows/cynqra-workforce.yml).
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import unittest
import urllib.request

from helpers import POC, SCENARIO, TempDir, no_model_env, restore_env, run_journey

from cynqra.engine import Engine
from cynqra.registry import Registry, RegistryError
from cynqra.workforce import Workforce, estimate, rank

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
        self.reg = Registry(self.tmp.path / "registry")
        for i, (name, price) in enumerate([("Model A", 0.2), ("Model B", 0.6), ("Model C", 2.0)]):
            self.reg.register({"runtime": "openai_compatible", "ref": f"fake-{i}", "name": name,
                               "base_url": self.srv.urls[i] + "/v1", "price_in": price, "price_out": price * 4,
                               "context": 32768, "provider": "test double", "license": "none"})
        self.wf = Workforce(self.reg)

    def tearDown(self):
        self.srv.close()
        self.reg.close()
        self.tmp.cleanup()
        restore_env(self.saved)

    def engine(self, budget_usd=5.0) -> Engine:
        e = Engine(self.tmp.path / "run", workforce=self.wf)
        e.create_company("Harbor Recruiting", "live")
        e.draft_objective(SCENARIO["messy"])
        e.set_guardrails(budget_cap=600, budget_usd=budget_usd, time_value_per_hour=10)
        e.confirm_objective()
        plan = [d for d in e.pending_decisions() if d["kind"] == "approve_plan"][0]
        e.decide(plan["id"], "approve")
        return e

    def test_registry_holds_facts_and_refuses_what_it_cannot_run(self):
        m = self.reg.get("model-a")
        self.assertEqual((m["runtime"], m["context"], m["price_in"]), ("openai_compatible", 32768, 0.2))
        self.assertNotIn("capability", str(m).lower(), "no hand-made scores")
        with self.assertRaises(RegistryError):
            self.reg.register({"runtime": "mystery", "ref": "x"})
        with self.assertRaises(RegistryError):
            self.reg.register({"runtime": "llama", "ref": "not-in-the-catalog"})
        self.assertEqual(self.reg.availability(m), (True, "available"))
        os.environ.pop("HF_TOKEN", None)
        hf = self.reg.register({"runtime": "hf", "ref": "zai-org/GLM-4.7", "name": "GLM-4.7"})
        self.assertEqual(self.reg.availability(hf), (False, "HF_TOKEN is not set"))
        self.reg.remove("glm-4-7")

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
        self.assertEqual(rank(self.reg, ["spec"], 10.0)[0]["model"], "Model C",
                         "a kind never seen borrows the model's overall record")

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
        self.assertEqual({o["task_kind"] for o in outs} >= {"spec", "code"}, True)
        self.assertTrue(all(o["run_id"] == e.cid for o in outs))
        e.close()

    def test_a_model_that_goes_offline_is_detected_and_replaced(self):
        e = self.engine()
        self.reg.set_fault("model-a", offline=True)  # after staffing: every worker is on Model A
        run_journey(e, max_rounds=40)
        self.assertEqual(e.meta["phase"], "accepted", e.meta.get("notice"))
        reps = e.store.all("replacement")
        self.assertTrue(reps and all(r["from"] == "model-a" for r in reps))
        self.assertTrue({r["to"] for r in reps} <= {"model-b", "model-c"})
        self.assertFalse(any(w["model_id"] == "model-a" for w in e.store.all("worker")), "nobody left on it")
        self.assertFalse(self.reg.availability(self.reg.get("model-a"))[0])
        errors = [c for c in self.reg.calls("model-a") if c["error"]]
        self.assertGreaterEqual(len(errors), 2, "detected from its own failed calls")
        e.close()

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
        L = e.workforce_view()["ledger"]
        moved = [x for x in L["events"] if x["what"] == "reallocated"]
        self.assertTrue(moved and moved[0]["from"] == "model-a", "the budget moved with the work")
        e.close()


if __name__ == "__main__":
    unittest.main()
