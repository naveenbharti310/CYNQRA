"""A founder's first time: nothing chosen for them. The founder searches what a provider offers and picks the models
Cynqra may use; every new hosted model is evaluated on Cynqra's own work before a project relies on it; and each seat
goes to the model measured best at that seat's kind of work, never to a default or a name."""
from __future__ import annotations

import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from helpers import TempDir, no_model_env, restore_env

from cynqra import roles, server
from cynqra.intelligence_layer import IntelligenceSupply
from cynqra.intelligence_layer.router import staff


class _Lister:
    """A provider that lists models the way Google does ("models/..." ids), and records how it was asked."""

    def __init__(self, ids):
        self.ids, self.headers = ids, []
        lister = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                lister.headers.append(dict(self.headers))
                data = json.dumps({"data": [{"id": i, "object": "model"} for i in lister.ids]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class BrowseTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()
        self.p = _Lister(["models/gemini-flash-lite", "models/gemini-pro", "text-embedding-4", "kimi-k3"])
        self.supply = IntelligenceSupply(self.tmp.path / "control")

    def tearDown(self):
        self.p.close()
        self.supply.close()
        self.tmp.cleanup()
        restore_env(self.saved)

    def _connect(self, models):
        return self.supply.connect({"type": "openai_compatible", "name": "Provider", "endpoint": self.p.url,
                                    "auth": {"method": "secret", "secret": "AQ.test-not-real"}, "models": models,
                                    "price_per_m": [0, 0]})["connection"]["id"]

    def test_the_founder_sees_everything_the_provider_lists_and_what_is_offered(self):
        cid = self._connect(["kimi-k3"])
        cat = self.supply.catalog(cid)
        refs = {m["ref"]: m["offered"] for m in cat["models"]}
        self.assertEqual(refs, {"gemini-flash-lite": False, "gemini-pro": False, "kimi-k3": True},
                         "chat models only, Google's models/ prefix dropped, the chosen one marked")
        active = [m["ref"] for m in self.supply.registry.models() if m["status"] != "retired"]
        self.assertEqual(active, ["kimi-k3"], "looking registers nothing")

    def test_choosing_models_offers_those_and_retires_the_rest(self):
        cid = self._connect(["kimi-k3"])
        self.supply.connections.update(cid, {"models": ["gemini-flash-lite"]})
        self.supply.discover(cid)
        by = {m["ref"]: m["status"] for m in self.supply.registry.models(include_retired=True)}
        self.assertEqual(by["gemini-flash-lite"], "active")
        self.assertEqual(by["kimi-k3"], "retired", "its measured record is kept, but the Router no longer uses it")


class EvaluateTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()
        self.p = _Lister(["model-a", "model-b"])

    def tearDown(self):
        self.p.close()
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_every_new_hosted_model_is_evaluated_once_in_the_background(self):
        seen = []

        def fake_probe(sup, mid, log=print):
            seen.append(mid)
            log("evaluated")
            return {"ok": True}
        with mock.patch.object(server, "probe", fake_probe):
            app = server.App(self.tmp.path / "app", auto_evaluate=True)
            try:
                app.supply_call("connect", None, {"type": "openai_compatible", "name": "P", "endpoint": self.p.url,
                                                  "auth": {"method": "none"}, "price_per_m": [0, 0]})
                deadline = time.time() + 10
                while time.time() < deadline and not all(v.get("state") == "done" for v in app.probes.values()):
                    time.sleep(0.05)
                self.assertEqual(len(seen), 2, "both models evaluated")
                self.assertTrue(all(v["state"] == "done" and v["auto"] for v in app.probes.values()))
                seen.clear()
                app.evaluate_new([m for m in app.supply.registry.models()])
                self.assertEqual(seen, [], "a model already evaluated, or being evaluated, is not queued again")
            finally:
                app.close()

    def test_nothing_runs_when_evaluation_is_off(self):
        with mock.patch.object(server, "probe", side_effect=AssertionError("must not run")):
            app = server.App(self.tmp.path / "app", auto_evaluate=False)
            try:
                app.supply_call("connect", None, {"type": "openai_compatible", "name": "P", "endpoint": self.p.url,
                                                  "auth": {"method": "none"}, "price_per_m": [0, 0]})
                self.assertEqual(app.probes, {})
            finally:
                app.close()


class SeatTests(unittest.TestCase):
    """Two free models: one plans well and codes badly, the other the reverse. The cofounders' seats go to the
    planner and the engineers' to the coder, from their evaluations alone."""

    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()
        self.p = _Lister(["planner", "coder"])
        self.supply = IntelligenceSupply(self.tmp.path / "control")
        self.supply.connect({"type": "openai_compatible", "name": "P", "endpoint": self.p.url,
                             "auth": {"method": "none"}, "price_per_m": [0, 0]})
        self.reg = self.supply.registry
        ids = {m["ref"]: m["id"] for m in self.reg.models()}
        for ref, plans, codes in (("planner", True, False), ("coder", False, True)):
            for i in range(4):
                for kind, ok in (("objective", plans), ("code", codes)):
                    self.reg.record_outcome(ids[ref], role="probe", task_kind=kind, task_id=f"{kind}{i}",
                                            run_id="probe", attempt=1, verified=ok, usd=0, seconds=20, tokens=3000,
                                            source="probe")
        self.ids = ids

    def tearDown(self):
        self.p.close()
        self.supply.close()
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_cofounders_get_the_planner_and_engineers_the_coder(self):
        workers = [{"id": "w_cto", "role": "CTO"}, {"id": "w_cpo", "role": "CPO"}, {"id": "w_be", "role": "Engineer"}]
        settings = {"budget_usd": 5.0, "time_value_per_hour": 10}
        got = {w: v["model_id"] for w, v in staff(self.reg, settings, workers).items()}
        coord = [k for k in roles.staffing_kinds("CPO") if k not in roles.BUILD_TYPES]
        self.assertTrue(coord, "a cofounder's work is mostly planning, assigning and reviewing")
        self.assertEqual(got["w_cpo"], self.ids["planner"])
        self.assertEqual(got["w_be"], self.ids["coder"])


class _Catalogue(_Lister):
    """A public catalogue of release dates in OpenRouter's format: {data: [{id, created}]}."""

    def __init__(self, dated):
        super().__init__([])
        self.dated = dated
        cat = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                data = json.dumps({"data": [dict(t, id=i) if isinstance(t, dict) else {"id": i, "created": t}
                                            for i, t in cat.dated.items()]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass
        self.server.shutdown()
        self.server.server_close()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/api/v1/models"


class LatestOnlyTests(unittest.TestCase):
    """Connected with no models named, as a founder does: 111 models were offered, most of them years old. Only
    the models released within a year are offered, the newest of each family; the rest stay searchable."""

    DAY = 86400

    def setUp(self):
        import os
        from cynqra.intelligence_layer import normalize
        self.saved = no_model_env()
        self.tmp = TempDir()
        now = time.time()
        self.google = _Lister(["models/gemini-2.5-flash", "models/gemini-3.6-flash", "models/gemini-3.8-flash",
                               "models/gemini-3.5-flash-lite", "models/gemini-flash-latest", "models/veo-3.1-generate-preview",
                               "models/lyria-3-pro-preview", "models/gemini-robotics-er-2-preview", "models/gemma-4-31b-it"])
        self.nvidia = _Lister(["meta/llama2-70b", "01-ai/yi-large", "moonshotai/kimi-k2.6", "moonshotai/kimi-k3",
                               "z-ai/glm-5.3", "mistralai/mistral-7b-instruct-v0.3", "nvidia/nemotron-3.5-content-safety"])
        self.cat = _Catalogue({
            "google/gemini-2.5-flash": now - 470 * self.DAY, "google/gemini-3.6-flash": now - 60 * self.DAY,
            "google/gemini-3.8-flash-preview": now - 28 * self.DAY, "google/gemini-3.5-flash-lite": now - 90 * self.DAY,
            "google/gemma-4-31b-it": now - 150 * self.DAY, "meta-llama/llama-2-70b-chat": now - 1100 * self.DAY,
            "moonshotai/kimi-k2.6": now - 200 * self.DAY, "moonshotai/kimi-k3": now - 75 * self.DAY,
            "z-ai/glm-5.3": now - 47 * self.DAY, "mistralai/mistral-7b-instruct-v0.3": now - 800 * self.DAY})
        self.old_url = os.environ.get("CYNQRA_MODEL_DATES_URL")
        os.environ["CYNQRA_MODEL_DATES_URL"] = self.cat.url
        normalize._CACHE.update(at=0.0, url=None, map={})
        self.supply = IntelligenceSupply(self.tmp.path / "control")

    def tearDown(self):
        import os
        os.environ["CYNQRA_MODEL_DATES_URL"] = self.old_url or "0"
        for x in (self.google, self.nvidia, self.cat):
            x.close()
        self.supply.close()
        self.tmp.cleanup()
        restore_env(self.saved)

    def _offered(self, lister):
        out = self.supply.connect({"type": "openai_compatible", "name": "P", "endpoint": lister.url,
                                   "auth": {"method": "none"}, "price_per_m": [0, 0]})
        return out["connection"]["id"], sorted(m["ref"] for m in out["intelligence"])

    def test_only_this_years_models_are_offered_newest_of_each_family(self):
        _, g = self._offered(self.google)
        self.assertEqual(g, ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemma-4-31b-it"],
                         "no 2025 Flash, no older 3.6, no alias, no video, music or robotics model")
        _, n = self._offered(self.nvidia)
        self.assertEqual(n, ["moonshotai/kimi-k3", "z-ai/glm-5.3"], "Llama 2, Yi and Mistral 7B are years old")

    def test_the_rest_stay_searchable_with_their_dates(self):
        cid, _ = self._offered(self.nvidia)
        cat = self.supply.catalog(cid)
        rows = {r["ref"]: r for r in cat["models"]}
        self.assertTrue(cat["dates"])
        self.assertEqual(cat["models"][0]["ref"], "z-ai/glm-5.3", "newest first")
        self.assertFalse(rows["meta/llama2-70b"]["current"])
        self.assertIsNone(rows["01-ai/yi-large"]["released"], "no known date: listed last, never offered by itself")
        self.assertNotIn("nvidia/nemotron-3.5-content-safety", rows, "a safety filter is not a team member")


class NormalizedTests(LatestOnlyTests):
    """What discovery puts in the registry: the model, who published it, and who it is reached through, apart."""

    def setUp(self):
        super().setUp()
        now = time.time()
        self.cat.dated.update({
            "moonshotai/kimi-k3": {"created": now - 75 * self.DAY, "name": "MoonshotAI: Kimi K3",
                                   "description": "Frontier agentic model for long-horizon coding and tool use.",
                                   "context_length": 1048576, "architecture": {"input_modalities": ["text", "image"]},
                                   "supported_parameters": ["tools", "reasoning", "response_format"],
                                   "pricing": {"prompt": "0.000003", "completion": "0.000015"},
                                   "top_provider": {"max_completion_tokens": 131072}},
            "google/gemini-3.8-flash-preview": {"created": now - 28 * self.DAY, "name": "Google: Gemini 3.8 Flash",
                                                "description": "Fast multimodal model; reads documents and PDFs (OCR).",
                                                "context_length": 1048576,
                                                "architecture": {"input_modalities": ["text", "image", "audio", "file"]},
                                                "supported_parameters": ["tools", "structured_outputs"]}})

    def _entry(self, lister, ref, rpm):
        out = self.supply.connect({"type": "openai_compatible", "name": lister, "endpoint": getattr(self, lister).url,
                                   "auth": {"method": "none"}, "price_per_m": [0, 0],
                                   "rate_limits": {"calls_per_minute": rpm}})
        return next(m for m in out["intelligence"] if m["ref"] == ref)

    def test_publisher_access_provider_and_model_are_three_facts(self):
        k = self._entry("nvidia", "moonshotai/kimi-k3", 30)
        self.assertEqual((k["display_name"], k["publisher_name"], k["access_provider"]), ("Kimi K3", "MoonshotAI", "nvidia"))
        self.assertEqual(k["rate_limit_per_min"], 30, "the access provider's limit is a structured fact")
        self.assertEqual(set(k["capabilities"]) >= {"reasoning", "tool use", "coding", "agentic", "long context",
                                                     "multimodal", "structured output"}, True)
        self.assertEqual((k["context"], k["max_output"], k["list_price_in"]), (1048576, 131072, 3.0))
        g = self._entry("google", "gemini-3.8-flash", 8)
        self.assertEqual((g["display_name"], g["publisher"], g["access_provider"]), ("Gemini 3.8 Flash", "google", "google"),
                         "Google is both publisher and access provider here")
        self.assertIn("document reading", g["capabilities"], "a search for OCR finds it")
        self.assertEqual(g["speed"], "fast")

    def test_no_catalogue_still_gives_a_publisher_and_a_readable_name(self):
        import os
        os.environ["CYNQRA_MODEL_DATES_URL"] = "0"
        k = self._entry("nvidia", "z-ai/glm-5.3", 30)
        self.assertEqual((k["display_name"], k["publisher"]), ("Glm 5.3", "z-ai"))
        self.assertNotIn("tool use", k["capabilities"], "nothing is claimed that no source says")


if __name__ == "__main__":
    unittest.main()
