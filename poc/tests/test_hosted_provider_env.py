import os
import unittest
from unittest import mock

from cynqra.intelligence_layer.adapters import OpenAICompatibleAdapter


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


if __name__ == "__main__":
    unittest.main()
