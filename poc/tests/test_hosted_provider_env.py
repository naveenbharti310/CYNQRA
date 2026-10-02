import json
import os
from pathlib import Path
import unittest
from unittest import mock

from cynqra.intelligence_layer.adapters import AnthropicAdapter, OpenAICompatibleAdapter
from cynqra.intelligence_layer.candidates import family_key
from cynqra import model_adapter


class HostedEnvironmentTests(unittest.TestCase):
    def test_gemini_and_nvidia_are_dynamic_openai_compatible_connections(self):
        adapter = OpenAICompatibleAdapter()
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "set", "NVIDIA_API_KEY": "set"},
                             clear=False):
            specs = adapter.environment_specs(None)

        by_name = {s["name"]: s for s in specs}
        self.assertEqual(
            by_name["Google Gemini (environment)"]["endpoint"],
            "https://generativelanguage.googleapis.com/v1beta/openai",
        )
        self.assertEqual(
            by_name["NVIDIA (environment)"]["endpoint"],
            "https://integrate.api.nvidia.com/v1",
        )
        self.assertEqual(by_name["Google Gemini (environment)"]["models"], [])
        self.assertEqual(by_name["NVIDIA (environment)"]["models"], [])

    def test_groq_and_mistral_are_paced_hosted_openai_compatible_connections(self):
        from cynqra import live_events
        from cynqra import run_hosted_examination as rhe
        adapter = OpenAICompatibleAdapter()
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "set", "MISTRAL_API_KEY": "set"}, clear=False):
            specs = {s["name"]: s for s in adapter.environment_specs(None)}
        groq, mistral = specs["Groq (environment)"], specs["Mistral (environment)"]
        self.assertEqual((groq["endpoint"], groq["auth"]), ("https://api.groq.com/openai/v1",
                                                            {"method": "env", "env_var": "GROQ_API_KEY"}))
        self.assertEqual((mistral["endpoint"], mistral["auth"]), ("https://api.mistral.ai/v1",
                                                                  {"method": "env", "env_var": "MISTRAL_API_KEY"}))
        self.assertEqual((groq["models"], mistral["models"]), ([], []), "every model they list is discovered")
        # paced below each free tier's stated limit (Groq 30 a minute, Mistral one a second)
        self.assertLess(groq["rate_limits"]["calls_per_minute"], 30)
        self.assertLess(mistral["rate_limits"]["calls_per_minute"], 60)
        for spec, flavor in ((groq, "groq"), (mistral, "mistral")):
            conn = dict(spec, origin="environment")
            self.assertEqual(adapter.flavor(conn), flavor)
            route = adapter.route(conn, "not-a-real-secret", {"ref": "model-x"})
            self.assertEqual((route["kind"], route["CYNQRA_LOCAL_BASE_URL"]), ("local", spec["endpoint"]))
            self.assertIn("CYNQRA_TIMEOUT", route, "a hosted call has the hosted time limit")
        self.assertEqual(rhe.parse_providers("nvidia+groq+mistral"), ["nvidia", "groq", "mistral"])
        self.assertEqual(rhe.PROVIDERS["groq"], ("GROQ_API_KEY", "Groq (environment)"))
        self.assertNotIn("gsk_" + "A" * 40, live_events.redact("key gsk_" + "A" * 40))
        self.assertIn("GROQ_API_KEY", live_events.SECRET_ENV)
        self.assertIn("MISTRAL_API_KEY", live_events.SECRET_ENV)

    def test_environment_discovery_keeps_the_complete_provider_chat_catalogue(self):
        adapter = OpenAICompatibleAdapter()
        listing = {"data": [
            {"id": "moonshotai/kimi-k2.6", "created": 1000},
            {"id": "moonshotai/kimi-k3", "created": 2000},
            {"id": "z-ai/glm-5.3-flash", "created": 3000},
        ]}
        with mock.patch("cynqra.intelligence_layer.adapters._get_json", return_value=listing):
            conn = {"endpoint": "https://integrate.api.nvidia.com/v1", "origin": "environment",
                    "metadata": {"flavor": "nvidia"}, "models": []}
            found = adapter.discover(conn, "not-a-real-secret")
        self.assertEqual({m["ref"] for m in found},
                         {"moonshotai/kimi-k2.6", "moonshotai/kimi-k3", "z-ai/glm-5.3-flash"})
    def test_hosted_routes_keep_the_provider_endpoint_and_key_per_connection(self):
        adapter = OpenAICompatibleAdapter()
        for endpoint, flavor in (
            ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini"),
            ("https://integrate.api.nvidia.com/v1", "nvidia"),
        ):
            conn = {"endpoint": endpoint, "metadata": {"flavor": flavor}, "origin": "environment"}
            self.assertEqual(adapter.flavor(conn), flavor)
            route = adapter.route(conn, "not-a-real-secret", {"ref": "model-x"})
            self.assertEqual(route["kind"], "local")
            self.assertEqual(route["CYNQRA_LOCAL_BASE_URL"], endpoint)
            self.assertEqual(route["CYNQRA_LOCAL_API_KEY"], "not-a-real-secret")

    def test_hosted_model_adapter_appends_chat_path_exactly_once(self):
        adapter = OpenAICompatibleAdapter()
        with mock.patch.object(model_adapter, "_post", return_value={
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }) as post:
            for endpoint, flavor in (
                ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini"),
                ("https://integrate.api.nvidia.com/v1", "nvidia"),
            ):
                conn = {"endpoint": endpoint, "metadata": {"flavor": flavor}, "origin": "environment"}
                route = adapter.route(conn, "not-a-real-secret", {"ref": "model-x"})
                model_adapter.complete("hello", max_tokens=1, route=route)
                self.assertEqual(post.call_args.args[0], endpoint + "/chat/completions")

    def test_an_anthropic_key_alone_discovers_its_models_rather_than_assuming_one(self):
        adapter = AnthropicAdapter()
        primary = {"kind": "anthropic", "label": "claude-default"}
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-not-real"}, clear=False):
            os.environ.pop("CYNQRA_MODEL", None)
            os.environ.pop("CYNQRA_ANTHROPIC_URL", None)
            spec = adapter.environment_specs(primary)[0]
            self.assertEqual(spec["name"], "Anthropic (environment)")
            self.assertEqual(spec["models"], [], "with no model named, every model the key can reach is discovered")
            self.assertEqual(spec["endpoint"], "")
            self.assertEqual(spec["auth"], {"method": "env", "env_var": "ANTHROPIC_API_KEY"})
            self.assertNotIn("sk-ant-test", str(spec), "the spec references the key, it never carries it")
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "set", "CYNQRA_MODEL": "claude-named",
                                          "CYNQRA_ANTHROPIC_URL": "http://127.0.0.1:9/v1/messages"}, clear=False):
            spec = adapter.environment_specs({"kind": "anthropic", "label": "claude-named"})[0]
            self.assertEqual(spec["models"], ["claude-named"], "a model the environment names narrows it")
            self.assertEqual(spec["endpoint"], "http://127.0.0.1:9", "listing and calls go to the same server")
            spec = adapter.environment_specs({"kind": "openai", "label": "gpt-x"})[0]
            self.assertEqual(spec["models"], [], "CYNQRA_MODEL names the primary provider's model, not this one's")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            self.assertEqual(adapter.environment_specs(primary), [])

    def test_anthropic_discovery_reads_every_page_with_release_dates(self):
        adapter = AnthropicAdapter()
        pages = [
            {"data": [{"id": "claude-a-5", "display_name": "A 5", "created_at": "2026-02-01T00:00:00Z",
                       "max_input_tokens": 1000000}], "has_more": True, "last_id": "claude-a-5"},
            {"data": [{"id": "claude-a-4-6", "created_at": "2025-08-01T00:00:00Z"},
                      {"id": "claude-b-4-5-20251001", "created_at": "not a date"}], "has_more": False},
        ]
        urls = []

        def listing(url, headers):
            urls.append(url)
            self.assertEqual(headers["x-api-key"], "not-a-real-secret")
            return pages[len(urls) - 1]

        with mock.patch("cynqra.intelligence_layer.adapters._get_json", side_effect=listing):
            conn = {"endpoint": "", "origin": "environment", "models": []}
            found = adapter.discover(conn, "not-a-real-secret")
        self.assertEqual(len(urls), 2)
        self.assertIn("after_id=claude-a-5", urls[1])
        by_ref = {m["ref"]: m for m in found}
        self.assertEqual(set(by_ref), {"claude-a-5", "claude-a-4-6", "claude-b-4-5-20251001"})
        self.assertEqual(by_ref["claude-a-5"]["released"], 1769904000.0)
        self.assertEqual(by_ref["claude-a-5"]["context"], 1000000)
        self.assertEqual(by_ref["claude-a-5"]["name"], "A 5")
        self.assertIsNone(by_ref["claude-b-4-5-20251001"]["released"], "an unreadable date is unknown, not invented")
        self.assertEqual(by_ref["claude-a-4-6"]["price_in"], 10.0, "an unlisted price is the safe default")
        from cynqra.intelligence_layer.adapters import LIST_PRICES, _price
        self.assertEqual(_price({}, "claude-haiku-4-5-20251001"), LIST_PRICES["claude-haiku-4-5"],
                         "a dated snapshot is priced as the model it pins")
        self.assertEqual(_price({}, "claude-unknown-20251001"), (10.0, 50.0))
        self.assertIn("3 model(s) discovered", conn["_listing_note"])
        self.assertNotIn("not-a-real-secret", str(found) + str(conn))

    def test_a_version_written_with_dashes_or_a_date_is_still_one_family(self):
        self.assertEqual(family_key("claude-a-4-6"), family_key("claude-a-5"))
        self.assertEqual(family_key("claude-b-4-5-20251001"), family_key("claude-b-5"))
        self.assertNotEqual(family_key("claude-a-5"), family_key("claude-b-5"))
        self.assertEqual(family_key("vendor/model-k2.6"), family_key("vendor/model-k3"))
        self.assertEqual(family_key("meta/llama-3.1-8b-instruct"), "llama-#-#b-instruct",
                         "a parameter size stays part of the name")

    def test_the_examination_can_be_limited_to_anthropic_and_requires_its_key(self):
        from cynqra import run_hosted_examination as rhe
        self.assertEqual(rhe.PROVIDERS["anthropic"], ("ANTHROPIC_API_KEY", "Anthropic (environment)"))
        keys = ("GEMINI_API_KEY", "NVIDIA_API_KEY", "ANTHROPIC_API_KEY")
        with mock.patch.dict(os.environ, {}, clear=False):
            for k in keys:
                os.environ.pop(k, None)
            with self.assertRaises(SystemExit) as ctx:
                rhe.main(["--provider", "anthropic"])
            self.assertIn("ANTHROPIC_API_KEY", str(ctx.exception))
            with self.assertRaises(SystemExit) as ctx:
                rhe.main(["--provider", "all"])
            self.assertIn("ANTHROPIC_API_KEY", str(ctx.exception))

    def test_a_saved_environment_connection_follows_what_the_environment_now_names(self):
        import tempfile
        from pathlib import Path
        from cynqra.intelligence_layer import IntelligenceSupply
        listing = {"data": [{"id": "claude-a-5", "created_at": "2026-02-01T00:00:00Z"},
                            {"id": "claude-b-5", "created_at": "2026-03-01T00:00:00Z"}], "has_more": False}
        with tempfile.TemporaryDirectory() as d, \
                mock.patch("cynqra.intelligence_layer.adapters._get_json", return_value=listing), \
                mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-not-real",
                                             "CYNQRA_MODEL": "claude-a-5"}, clear=False):
            for k in ("OPENAI_API_KEY", "GEMINI_API_KEY", "NVIDIA_API_KEY", "HF_TOKEN", "CYNQRA_LOCAL_BASE_URL",
                      "CYNQRA_OLLAMA_MODEL", "CYNQRA_S1_MODEL_CMD", "CYNQRA_ANTHROPIC_URL"):
                os.environ.pop(k, None)
            supply = IntelligenceSupply(Path(d))
            try:
                self.assertEqual({m["ref"] for m in supply.connect_environment()}, {"claude-a-5"})
                os.environ.pop("CYNQRA_MODEL")
                found = supply.connect_environment()
                self.assertEqual({m["ref"] for m in found}, {"claude-a-5", "claude-b-5"},
                                 "with no model named any more, every model the key reaches is discovered")
                conns = [c for c in supply.connections.all() if c["name"] == "Anthropic (environment)"]
                self.assertEqual(len(conns), 1, "the saved connection is updated, not duplicated")
                self.assertEqual(conns[0]["models"], [])
            finally:
                supply.close()

    def test_the_objective_run_is_summarised_for_the_job_log(self):
        from cynqra.run_hosted_examination import objective_summary
        run = {"stage": "first_bindings", "lifecycle": "active", "spent_usd": 0.12,
               "calibration": {"status": "complete", "trials": [
                   {"intelligence_id": "m1", "verified": True, "attribution": None},
                   {"intelligence_id": "m2", "verified": None, "attribution": "provider"},
                   {"intelligence_id": "m2", "verified": False, "attribution": "intelligence"}]},
               "decisions": [{"selection_mode": "calibrated", "replayed": True, "selected": "m1"},
                             {"selection_mode": "calibrated", "replayed": True, "selected": "m1"}]}
        s = objective_summary(run)
        self.assertEqual((s["calibration"]["trials"], s["calibration"]["verified"]), (3, 1))
        self.assertEqual(s["calibration"]["by_candidate"], {"m1": [True], "m2": [None, False]})
        self.assertEqual(s["calibration"]["failures_not_the_intelligence"], ["provider"],
                         "a provider failure is reported as one, never as the model's")
        self.assertEqual((s["decisions"], s["selection_modes"], s["all_replayed"], s["selected"]),
                         (2, {"calibrated": 2}, True, ["m1"]))
        self.assertIsNone(objective_summary({"stage": "objective", "error": "x"})["all_replayed"])

    def test_the_examination_reports_why_a_provider_offered_nothing(self):
        import io
        import tempfile
        from contextlib import redirect_stdout
        from cynqra import run_hosted_examination as rhe
        from cynqra.intelligence_layer.contracts import SupplyError
        refused = SupplyError("https://api.anthropic.com/v1/models?limit=100 answered HTTP 401: "
                              '{"type":"error","error":{"type":"authentication_error","message":"invalid x-api-key"}}')
        with tempfile.TemporaryDirectory() as d, \
                mock.patch("cynqra.intelligence_layer.adapters._get_json", side_effect=refused), \
                mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-not-real"}, clear=False):
            for k in ("OPENAI_API_KEY", "GEMINI_API_KEY", "NVIDIA_API_KEY", "HF_TOKEN", "CYNQRA_LOCAL_BASE_URL",
                      "CYNQRA_OLLAMA_MODEL", "CYNQRA_S1_MODEL_CMD", "CYNQRA_ANTHROPIC_URL", "CYNQRA_MODEL"):
                os.environ.pop(k, None)
            out = io.StringIO()
            with redirect_stdout(out):
                code = rhe.main(["--provider", "anthropic", "--data-root", d])
            manifest = json.loads((Path(d) / "manifest.json").read_text())
        self.assertEqual(code, 1, "nothing examined is not a pass")
        self.assertIn("Anthropic (environment): error", out.getvalue())
        self.assertIn("HTTP 401", out.getvalue())
        self.assertEqual(manifest["connections"][0]["status"], "error")
        self.assertNotIn("sk-ant-test", out.getvalue() + json.dumps(manifest), "the key never reaches the evidence")

    def test_a_key_for_several_workspaces_names_the_workspace_on_every_request(self):
        adapter = AnthropicAdapter()
        seen = []

        def listing(url, headers):
            seen.append(dict(headers))
            return {"data": [{"id": "claude-a-5"}], "has_more": False}

        with mock.patch("cynqra.intelligence_layer.adapters._get_json", side_effect=listing), \
                mock.patch.dict(os.environ, {"ANTHROPIC_WORKSPACE_ID": "wrkspc_01TESTWORKSPACE"}, clear=False):
            adapter.discover({"endpoint": "", "origin": "environment", "models": []}, "not-a-real-secret")
            route = adapter.route({"endpoint": "", "origin": "environment"}, "not-a-real-secret", {"ref": "claude-a-5"})
            self.assertNotIn("ANTHROPIC_WORKSPACE_ID", route, "the environment's calls read the environment's workspace")
            founder = {"endpoint": "", "origin": "founder", "models": [], "metadata": {"workspace_id": "wrkspc_01OWN"}}
            adapter.discover(founder, "not-a-real-secret")
            self.assertEqual(adapter.route(founder, "k", {"ref": "claude-a-5"})["ANTHROPIC_WORKSPACE_ID"], "wrkspc_01OWN")
            plain = {"endpoint": "", "origin": "founder", "models": []}
            adapter.discover(plain, "not-a-real-secret")
            self.assertIsNone(adapter.route(plain, "k", {"ref": "claude-a-5"})["ANTHROPIC_WORKSPACE_ID"],
                              "another key's workspace never reaches a connection that names none")
        self.assertEqual(seen[0]["anthropic-workspace-id"], "wrkspc_01TESTWORKSPACE")
        self.assertEqual(seen[1]["anthropic-workspace-id"], "wrkspc_01OWN")
        self.assertNotIn("anthropic-workspace-id", seen[2])

    def test_a_missing_workspace_is_explained(self):
        from cynqra.intelligence_layer.contracts import SupplyError
        adapter = AnthropicAdapter()
        refused = SupplyError("https://api.anthropic.com/v1/models?limit=100 answered HTTP 400: This API key is not "
                              "scoped to a workspace, so this request must include the anthropic-workspace-id header")
        with mock.patch("cynqra.intelligence_layer.adapters._get_json", side_effect=refused), \
                mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_WORKSPACE_ID", None)
            with self.assertRaises(SupplyError) as ctx:
                adapter.discover({"endpoint": "", "origin": "environment", "models": []}, "not-a-real-secret")
        self.assertIn("set ANTHROPIC_WORKSPACE_ID", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
