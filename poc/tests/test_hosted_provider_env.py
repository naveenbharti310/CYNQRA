import os
import unittest
from unittest import mock

from cynqra.intelligence_layer.adapters import OpenAICompatibleAdapter
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

if __name__ == "__main__":
    unittest.main()
