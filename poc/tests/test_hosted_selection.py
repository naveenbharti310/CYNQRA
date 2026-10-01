import unittest

from cynqra.run_hosted_examination import select


def model(mid, ref, provider, caps=(), context=100000, released=0):
    return {
        "id": mid,
        "ref": ref,
        "name": ref,
        "connection_id": provider,
        "provider": provider,
        "status": "active",
        "regression": {"status": "unverified"},
        "capabilities": list(caps),
        "context": context,
        "released": released,
        "catalogued": True,
    }


class HostedSelectionTests(unittest.TestCase):
    def test_selection_does_not_hardcode_kimi_and_keeps_latest_family_candidate(self):
        entries = [
            model("k2", "moonshotai/kimi-k2.6", "nvidia", ("reasoning", "coding"), 200000, 1),
            model("k3", "moonshotai/kimi-k3", "nvidia", ("reasoning", "coding", "tool use"), 1000000, 2),
            model("glm", "z-ai/glm-5.3-flash", "nvidia", ("reasoning", "coding", "tool use"), 1000000, 3),
            model("gem", "gemini-3.8-flash", "google", ("reasoning", "tool use"), 1000000, 4),
        ]
        chosen = select(entries, 2)
        refs = [m["ref"] for m in chosen]
        self.assertIn("moonshotai/kimi-k3", refs)
        self.assertNotIn("moonshotai/kimi-k2.6", refs)

    def test_selection_is_provider_fair_without_treating_provider_as_quality(self):
        entries = [
            model("g1", "gemini-a", "google", ("reasoning",)),
            model("g2", "gemini-b", "google", ("reasoning",)),
            model("n1", "nvidia-a", "nvidia", ("reasoning",)),
            model("n2", "nvidia-b", "nvidia", ("reasoning",)),
        ]
        chosen = select(entries, 2)
        providers = {m["connection_id"] for m in chosen}
        self.assertEqual(providers, {"google", "nvidia"})

    def test_selection_uses_metadata_only_to_prioritize_calibration(self):
        entries = [
            model("a", "a", "google", ("reasoning", "coding", "agentic")),
            model("b", "b", "google", ("reasoning",)),
        ]
        chosen = select(entries, 1)
        self.assertEqual(chosen[0]["id"], "a")


if __name__ == "__main__":
    unittest.main()
