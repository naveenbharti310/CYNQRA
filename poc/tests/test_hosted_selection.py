import unittest

import helpers  # noqa: F401  - puts poc/ on the path, as every test module does

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


# The 19 models Google's API listed for the founder's paid key in run 37587595496
GEMINI = ("gemini-2.5-flash gemini-2.5-flash-lite gemini-2.5-pro gemini-3.1-flash-lite gemini-3.1-flash-lite-preview "
          "gemini-3.1-pro-preview gemini-3.5-flash gemini-3.5-flash-lite gemini-3.6-flash gemini-3.7-flash "
          "gemini-3.8-flash gemini-3-flash-preview gemini-flash-latest gemini-flash-lite-latest gemini-omni-1.1-flash "
          "gemini-omni-flash-preview gemini-pro-latest gemma-4-26b-a4b-it gemma-4-31b-it").split()


class NewestOfEachLineTests(unittest.TestCase):
    """Run 37587595496: of the 19 models on the founder's paid Google key, the three examined were Gemini 3 Flash
    Preview, Gemini 2.5 Pro and Gemini 3.1 Pro Preview. A "-preview" name counted as a family of its own, so the old
    2.5 Pro took a place beside 3.1 Pro Preview (and Google then refused it as no longer available to new users), and
    3 Flash Preview stood apart from 3.5 to 3.8 Flash. Inside a family a release date the public catalogue lacks
    counted as the oldest. A preview or a moving alias is now a release of its family, and the newest version stands
    for it."""

    def test_the_newest_of_each_gemini_line_is_examined(self):
        chosen = [m["ref"] for m in select([model(r, r, "google") for r in GEMINI], 3)]
        self.assertEqual(sorted(chosen), ["gemini-3.1-pro-preview", "gemini-3.5-flash-lite", "gemini-3.8-flash"])
        for old in ("gemini-2.5-pro", "gemini-3-flash-preview", "gemini-2.5-flash", "gemini-pro-latest"):
            self.assertNotIn(old, chosen)

    def test_one_place_per_line_however_the_names_are_written(self):
        from cynqra.intelligence_layer.candidates import family_key
        self.assertEqual(family_key("gemini-3.1-pro-preview"), family_key("gemini-2.5-pro"))
        self.assertEqual(family_key("gemini-3-flash-preview"), family_key("gemini-3.8-flash"))
        self.assertEqual(family_key("gemini-2.5-flash-preview-05-20"), family_key("gemini-3.8-flash"))
        self.assertNotEqual(family_key("gemini-3.8-flash"), family_key("gemini-3.5-flash-lite"))
        chosen = [m["ref"] for m in select([model(r, r, "google") for r in GEMINI], len(GEMINI))]
        self.assertEqual(len({family_key(r) for r in chosen[:6]}), 6, "six lines, one place each, before any repeat")
        self.assertEqual(sorted(chosen[:6]), ["gemini-3.1-pro-preview", "gemini-3.5-flash-lite", "gemini-3.8-flash",
                                              "gemini-omni-1.1-flash", "gemma-4-26b-a4b-it", "gemma-4-31b-it"])

    def test_a_release_date_the_catalogue_lacks_never_puts_an_old_release_first(self):
        entries = [model("old", "gemini-2.5-flash", "google", released=1_750_000_000),
                   model("new", "gemini-3.8-flash", "google", released=0)]
        self.assertEqual(select(entries, 1)[0]["id"], "new")

    def test_a_pinned_release_before_a_moving_alias_and_a_stable_one_before_its_preview(self):
        entries = [model("alias", "gemini-flash-lite-latest", "google"),
                   model("preview", "gemini-3.1-flash-lite-preview", "google"),
                   model("stable", "gemini-3.1-flash-lite", "google")]
        self.assertEqual(select(entries, 1)[0]["id"], "stable")
        self.assertEqual(select(entries[:2], 1)[0]["id"], "preview", "a pinned preview before the moving alias")

    def test_a_model_its_provider_no_longer_serves_gives_its_place_to_the_next(self):
        from cynqra.intelligence_layer.candidates import examine
        entries = [model(r, r, "google") for r in ("a-1", "b-1", "c-1", "d-1", "e-1", "f-1")]
        gone = {"a-1"}
        run = lambda m: {"model_id": m["id"], "error": "HTTP 404 from provider: no longer available"} \
            if m["id"] in gone else {"model_id": m["id"], "passed": True}  # noqa: E731
        served = lambda r: "HTTP 404" not in (r.get("error") or "")  # noqa: E731
        tried, results = examine(entries, 2, run, served)
        self.assertEqual([m["id"] for m in tried], ["a-1", "b-1", "c-1"], "two models that can be used")
        self.assertEqual([r["model_id"] for r in results], ["a-1", "b-1", "c-1"])
        gone = {m["id"] for m in entries}
        tried, _ = examine(entries, 2, run, served)
        self.assertEqual(len(tried), 4, "at most twice the limit are tried")

    def test_the_examination_counts_a_404_as_not_served_and_an_empty_account_as_served(self):
        from cynqra.run_hosted_examination import served
        self.assertFalse(served({"error": 'RuntimeError: HTTP 404 from provider: [{"error": {"code": 404, "message": '
                                          '"This model models/gemini-2.5-pro is no longer available to new users."}}]'}))
        self.assertTrue(served({"error": "RuntimeError: HTTP 402 from provider: Your prepayment credits are depleted."}),
                        "another model on the same empty account would only be refused again")
        self.assertTrue(served({"passed": True}))


if __name__ == "__main__":
    unittest.main()
