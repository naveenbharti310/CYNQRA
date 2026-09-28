"""Robustness: answers with missing fields or fields of the wrong type. A team whose answers arrive with fields missing, or of the
wrong type (a number where text belongs, an object where a list belongs), must make Cynqra refuse, retry, rework,
escalate or stop with a clear reason; it must never crash the run. The second audit's fuzzing found five such
crashes, each of which would have stalled a live run; these tests keep them out."""
from __future__ import annotations

import copy
import random
import unittest

from helpers import TempDir, no_model_env, restore_env

from cynqra.db import Store
from cynqra.engine import Engine, EngineError
from cynqra.intelligence import IntelligenceError, ScriptedSource
from cynqra.protocol import build

JUNK = [None, 7, 3.5, True, [], {}, ["a", {"b": 1}], {"x": [1]}, "", "   ", "../../etc/passwd",
        "<script>x</script>", "x" * 5000]


def mutate(obj, rng, depth=0):
    if depth > 0 and rng.random() < 0.25:  # a model's reply is always a JSON object; what is inside may be anything
        return rng.choice(JUNK)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            r = rng.random()
            if r < 0.12:
                continue
            out[k] = mutate(v, rng, depth + 1) if r < 0.4 else v
        if rng.random() < 0.1:
            out[rng.choice(["weird", "result", "files", "needs_from"])] = rng.choice(JUNK)
        return out
    if isinstance(obj, list):
        return [mutate(x, rng, depth + 1) for x in obj if rng.random() > 0.1]
    return obj


class Garbled(ScriptedSource):
    """A demo team whose answers are corrupted at random, the same way for the same seed."""

    def __init__(self, scenario, seed, rate=0.35):
        super().__init__(scenario)
        self.rng, self.rate = random.Random(seed), rate

    def _maybe(self, pair):
        data, usage = pair
        return (mutate(copy.deepcopy(data), self.rng) if self.rng.random() < self.rate else data), usage


for _name in ("structure_objective", "decompose", "cofounders", "build_team", "plan", "assign", "work",
              "answer_blocker", "review"):
    setattr(Garbled, _name, (lambda n: lambda self, *a, **k: self._maybe(getattr(ScriptedSource, n)(self, *a, **k)))(_name))


class GarbledAnswersTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()

    def tearDown(self):
        restore_env(self.saved)

    def run_garbled(self, scenario, seed):
        tmp = TempDir()
        e = Engine(tmp.path, intelligence=Garbled(scenario, seed))
        try:
            e.create_company("C", "demo", scenario)
            e.draft_objective(ScriptedSource(scenario).data["messy"])
            e.submit_objective()
            for _ in range(60):
                if e.meta["phase"] in ("accepted", "stopped", "stopped_error"):
                    break
                r = e.step()
                pend = e.pending_decisions()
                if pend:
                    e.decide(pend[0]["id"], "approve")
                elif r["did"] in ("idle", "error"):
                    break
        except (EngineError, IntelligenceError):
            pass  # a clear refusal is the right outcome for a garbled answer
        finally:
            e.close()
            tmp.cleanup()

    def test_garbled_answers_never_crash_a_run(self):
        # seeds that, before the fix, reached each of the crashes: artifacts that were objects or numbers, a summary
        # that was not text, workstreams and milestones that were not lists, inferred fields that were a number,
        # evidence that was a boolean
        for scenario, seeds in (("candidate_tracker", range(0, 10)), ("bluedip", (58, 1, 2, 3, 4)),
                                ("restaurant_forecast", (35, 1, 2, 3))):
            for seed in seeds:
                with self.subTest(scenario=scenario, seed=seed):
                    self.run_garbled(scenario, seed)


class ProtocolShapeTests(unittest.TestCase):
    def test_content_takes_the_templates_shape(self):
        h = build("Handoff", {"artifacts": [{"a": 1}, "doc_1", 7], "acceptance_check": {"tests": 3},
                              "context_ref": 12}, {"from_worker": "w_a", "to_worker": "w_b", "task_id": "t_1"}, "t_1")
        self.assertEqual(h["artifacts"], ["doc_1"])
        self.assertEqual(h["acceptance_check"], '{"tests": 3}')
        self.assertEqual(h["context_ref"], "12")
        a = build("Approval", {"evidence_refs": "tests passed", "recommendation": "merge", "confidence": 0.8,
                               "what_would_change_this": "a failing test"},
                  {"decision_id": "d", "from_worker": "w_a", "task_id": "t", "risk": "R2"}, "t")
        self.assertEqual(a["evidence_refs"], ["tests passed"])
        self.assertEqual(a["confidence"], "0.8")

    def test_content_that_is_not_an_object_adds_nothing(self):
        with self.assertRaises(ValueError):  # nothing from the model, so the required acceptance check is missing
            build("Handoff", ["acceptance_check"], {"from_worker": "w_a", "to_worker": "w_b", "task_id": "t"}, "t")


class EngineInputTests(unittest.TestCase):
    def setUp(self):
        self.saved = no_model_env()
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()
        restore_env(self.saved)

    def test_only_a_prepared_demo_can_be_opened(self):
        e = Engine(self.tmp.path)
        try:
            for bad in ("../scenarios/bluedip", "nope", "bluedip/../bluedip"):
                with self.subTest(scenario=bad), self.assertRaises(EngineError):
                    e.create_company("C", "demo", bad)
        finally:
            e.close()

    def test_the_screen_reads_only_the_newest_events(self):
        s = Store(str(self.tmp.path / "t.db"))
        try:
            self.assertEqual(s.last_events(5), [])
            for i in range(12):
                s.append(company_id="c", event_type="x.y", aggregate_type="x", aggregate_id=str(i),
                         payload={"i": i}, actor_type="service", actor_id="t", correlation_id="c")
            got = [e["payload"]["i"] for e in s.last_events(5)]
            self.assertEqual(got, [7, 8, 9, 10, 11])
            self.assertEqual(len(s.last_events(50)), 12)
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()
