"""The live view (cynqra/live_events.py): a read-only projection of a run's persisted events, printed as they are saved.

The run is the closed loop of test_objective_intelligence on test doubles: calibration, initial bindings, then the
cheapest model breaking, so the work is replaced, reselected and rerouted on evidence. Every check compares what was
printed with what the store holds, which stays the source of truth.
"""
from __future__ import annotations

import collections
import os
import re
import threading
import time
import unittest
from unittest import mock

from helpers import SCENARIO, TempDir, engine_to_gates, no_model_env, restore_env, run_journey
from test_objective_intelligence import ModelsServer, supply_with

from cynqra import binding, controller, live_events
from cynqra.db import Store
from cynqra.engine import Engine

LINE = re.compile(r"  live #(\d+) (\S+) (\S+)")
MANDATED = ("objective.created", "requirements.created", "workgraph.created", "workforce.created",
            "intelligence.discovered", "intelligence.candidate_set.created", "intelligence.calibration.started",
            "intelligence.calibration.completed", "intelligence.selection.proposed", "intelligence.selection.committed",
            "worker.bound", "task.started", "review.started", "verification.completed", "rework.created",
            "intelligence.evidence.updated", "intelligence.reselection.triggered", "intelligence.rerouted",
            "production.verification.started", "production.verification.completed", "objective.completed")


class ReadOnly:
    """The store as the live view may see it: reading only. Anything else is recorded as a violation."""

    def __init__(self, store):
        self._store, self.violations = store, []

    def events(self, *a, **k):
        return self._store.events(*a, **k)

    def get(self, *a, **k):
        return self._store.get(*a, **k)

    def __getattr__(self, name):
        self.violations.append(name)
        raise AttributeError(f"the live view may not use the store's {name}")


def closed_loop(folder, sup, srv, live: bool):
    """The closed-loop run, with or without the live view. Returns (engine, printed lines, read-only proxy)."""
    out, ro = [], None
    e = Engine(folder, supply=sup)
    tail = None
    if live:
        ro = ReadOnly(e.store)
        tail = live_events.EventTail(ro, log=out.append, every=0.05).start()
    e.create_company("Harbor Recruiting", "live")
    e.draft_objective(SCENARIO["messy"])
    e.set_guardrails(budget_usd=5.0, time_value_per_hour=10)
    e.submit_objective()
    engine_to_gates(e)
    srv.broken.add("Steady")  # after calibration the cheapest model breaks: replacement, reselection, reroute
    run_journey(e, max_rounds=60)
    if tail is not None:
        tail.stop()
    return e, out, ro


def summary(e) -> dict:
    """What the control plane did, without ids or times: the decisions, the bindings, the tasks, the events."""
    return {"decisions": sorted((d["purpose"], d["work_item_id"], (d.get("selected_intelligence") or {}).get("id"),
                                 d["selection_mode"], d["status"]) for d in e.decisions()),
            "tasks": sorted((t["id"], t["status"], t["attempts"]) for t in e.tasks()),
            "bindings": sorted((k, v["intelligence_id"]) for k, v in binding.all_task_bindings(e.store).items()),
            "events": collections.Counter(x["event_type"] for x in e.store.events()), "phase": e.meta["phase"]}


class LiveViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = no_model_env()
        cls.tmp = TempDir()
        cls.srv = ModelsServer()
        cls.srv.broken.add("Sloppy")
        cls.sup = supply_with(cls.tmp.path, [("Steady", 0.2), ("Sloppy", 0.4), ("Careful", 0.6)], cls.srv)
        cls.e, cls.lines, cls.ro = closed_loop(cls.tmp.path / "live", cls.sup, cls.srv, live=True)
        cls.events = cls.e.store.events()
        cls.parsed = [(int(m.group(1)), m.group(2), m.group(3), x) for x in cls.lines if (m := LINE.match(x))]

    @classmethod
    def tearDownClass(cls):
        cls.e.close()
        cls.sup.close()
        cls.srv.close()
        cls.tmp.cleanup()
        restore_env(cls.saved)

    def first(self, event_type, aggregate=None) -> int:
        return next(n for n, t, a, _ in self.parsed if t == event_type and (aggregate is None or a == aggregate))

    def test_1_events_are_printed_in_the_order_they_were_saved(self):
        self.assertEqual(self.e.meta["phase"], "accepted")
        seqs = [n for n, *_ in self.parsed]
        self.assertEqual(seqs, [x["seq"] for x in self.events], "every saved event, in the order saved")
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual([t for _, t, *_ in self.parsed], [x["event_type"] for x in self.events])
        present = {t for _, t, *_ in self.parsed}
        self.assertEqual([m for m in MANDATED if m not in present], [], "the run reached every mandated event")
        # the order of cause and effect, as the run lived it
        for a, b in (("objective.created", "requirements.created"), ("requirements.created", "workgraph.created"),
                     ("intelligence.calibration.started", "intelligence.calibration.completed"),
                     ("intelligence.calibration.completed", "task.started"),
                     ("production.verification.started", "production.verification.completed"),
                     ("production.verification.completed", "objective.completed")):
            self.assertLess(self.first(a), self.first(b), (a, b))
        for d in self.e.decisions():  # each decision: its candidates, then its proposal, then its commitment
            mine = [(n, t) for n, t, a, x in self.parsed if f"decision={d['decision_id']} " in x + " "]
            order = [t for _, t in mine if t in ("intelligence.candidate_set.created", "intelligence.selection.proposed",
                                                  "intelligence.selection.committed")]
            want = ["intelligence.candidate_set.created", "intelligence.selection.proposed"] + \
                (["intelligence.selection.committed"] if any(t == "intelligence.selection.committed" for t in order)
                 else [])
            self.assertEqual(order, want, d["decision_id"])
        for t in self.e.tasks():  # a task starts before it is verified
            started = [n for n, ty, a, _ in self.parsed if ty == "task.started" and a == t["id"]]
            verified = [x["seq"] for x in self.events if x["event_type"] == "verification.completed"
                        and x["payload"].get("task_id") == t["id"]]
            if verified:
                self.assertTrue(started and started[0] < verified[0], t["id"])

    def test_2_only_real_state_transitions_are_printed(self):
        saved = {x["seq"]: x for x in self.events}
        self.assertTrue(all(n in saved and saved[n]["event_type"] == t for n, t, *_ in self.parsed))
        st = self.e.store
        for n, t, a, x in self.parsed:  # every printed transition is backed by the state it reports
            p = saved[n]["payload"]
            if t == "intelligence.selection.committed":
                self.assertEqual(controller.get_decision(self.e, a)["status"], "committed", x)
            elif t == "worker.bound":
                self.assertTrue(st.get("binding", p.get("worker_id") or a) or st.get("work_binding", a)
                                or st.get("verification_binding", a) or binding.current(st, a), x)
            elif t == "verification.completed":
                self.assertIsNotNone(st.get("verification", a), x)
            elif t == "rework.created":
                self.assertTrue(self.e.task(a).get("rework_history"), x)
            elif t == "intelligence.reselection.triggered":
                self.assertEqual(controller.get_decision(self.e, p["decision_id"])["selection_mode"], "reselect", x)
            elif t == "production.verification.completed":
                self.assertTrue(st.all("production_verification"), x)

    def test_2b_a_write_that_rolls_back_or_has_not_committed_prints_nothing(self):
        tmp = TempDir()
        s = Store(str(tmp.path / "x.db"))
        out = []
        tail = live_events.EventTail(s, log=out.append, every=3600)
        try:
            ev = dict(company_id="co", event_type="task.started", aggregate_type="task", aggregate_id="t_01",
                      actor_type="system", actor_id="execution", payload={"task_id": "t_01"}, correlation_id="t_01")
            with self.assertRaises(RuntimeError):
                with s.atomic():
                    s.append(**ev)
                    raise RuntimeError("the transition failed")
            self.assertEqual((tail.flush(), out), (0, []), "a rolled-back event never happened")
            reader = threading.Thread(target=tail.flush)
            with s.atomic():
                s.append(**ev)
                reader.start()
                time.sleep(0.3)
                self.assertEqual(out, [], "not shown while its transaction is open")
            reader.join(5)
            self.assertEqual(len(out), 1, "shown once it committed")
        finally:
            s.close()
            tmp.cleanup()

    def test_3_no_event_is_printed_twice(self):
        seqs = [n for n, *_ in self.parsed]
        self.assertEqual(len(seqs), len(set(seqs)))
        tail = live_events.EventTail(self.e.store, log=[].append, every=3600)
        self.assertEqual(tail.flush(), len(self.events))
        self.assertEqual((tail.flush(), tail.flush()), (0, 0), "a second flush shows nothing again")
        tmp = TempDir()
        s = Store(str(tmp.path / "x.db"))
        try:  # the same event sent twice (a retry) is saved once, so printed once
            for _ in range(2):
                s.append(company_id="co", event_type="rework.created", aggregate_type="task", aggregate_id="t_02",
                         actor_type="system", actor_id="verification", payload={"attempt": 1}, correlation_id="t_02",
                         idempotency_key="rework:t_02:1")
            out = []
            live_events.EventTail(s, log=out.append, every=3600).flush()
            self.assertEqual(len(out), 1)
        finally:
            s.close()
            tmp.cleanup()

    def test_4_selection_lines_name_the_right_decision_and_evidence_version(self):
        saved = {x["seq"]: x for x in self.events}
        seen = collections.Counter()
        for n, t, a, x in self.parsed:
            if t not in live_events.SELECTION_EVENTS or t == "worker.bound":
                continue
            p = saved[n]["payload"]
            did = p.get("decision_id") or a
            d = controller.get_decision(self.e, did)
            self.assertIsNotNone(d, x)
            self.assertIn(f"decision={did} ", x + " ")
            self.assertIn(f"evidence_version={d['evidence_version']} ", x + " ")
            if p.get("evidence_version") is not None:
                self.assertEqual(p["evidence_version"], d["evidence_version"], x)
            self.assertIn(f"work_item={d['work_item_id']} ", x + " ")
            if t != "intelligence.candidate_set.created":
                self.assertIn(f"selected={(d.get('selected_intelligence') or {}).get('id')} ", x + " ")
            else:
                self.assertIn(f"candidates={len(d['candidate_set'])} ", x + " ")
            if t in ("intelligence.selection.proposed", "intelligence.reselection.triggered"):
                self.assertIn("reason=", x)
            seen[t] += 1
        self.assertTrue(seen["intelligence.reselection.triggered"] and seen["intelligence.rerouted"], seen)
        rer = next(x for _, t, _, x in self.parsed if t == "intelligence.rerouted")
        self.assertRegex(rer, r"from=\S+ to=\S+")

    def test_5_secrets_never_appear(self):
        key = "nvapi-" + "Q" * 40
        sentinel = "s3cret-value-from-the-environment"
        text = "\n".join(self.lines)
        self.assertIsNone(live_events.KEY_SHAPES.search(text))
        tmp = TempDir()
        s = Store(str(tmp.path / "x.db"))
        try:
            s.append(company_id="co", event_type="worker.stopped", aggregate_type="worker", aggregate_id="w_be",
                     actor_type="system", actor_id="replacement_engine", correlation_id="t_03",
                     payload={"why": f"HTTP 401 for key {key} and {sentinel}", "cause": "access",
                              "token": sentinel, "authorization": f"Bearer {key}"})
            with mock.patch.dict(os.environ, {"NVIDIA_API_KEY": sentinel}):
                out = []
                live_events.EventTail(s, log=out.append, every=3600).flush()
                rebuilt = live_events.lines(s)
            for line in out + rebuilt:
                self.assertNotIn(key, line)
                self.assertNotIn(sentinel, line)
            self.assertIn("[redacted]", out[0])
            self.assertNotIn("authorization", out[0], "fields not on the list are never printed")
        finally:
            s.close()
            tmp.cleanup()

    def test_6_the_live_view_changes_nothing_the_control_plane_does(self):
        self.assertEqual(self.ro.violations, [], "the live view only read the store")
        tmp = TempDir()
        srv = ModelsServer()
        srv.broken.add("Sloppy")
        sup = supply_with(tmp.path, [("Steady", 0.2), ("Sloppy", 0.4), ("Careful", 0.6)], srv)
        try:
            e, out, _ = closed_loop(tmp.path / "quiet", sup, srv, live=False)
            try:
                self.assertEqual(out, [])
                self.assertEqual(summary(e), summary(self.e), "the same run, watched or not")
            finally:
                e.close()
        finally:
            sup.close()
            srv.close()
            tmp.cleanup()

    def test_7_a_finished_run_rebuilds_the_same_view_from_its_store(self):
        rebuilt = live_events.lines(self.e.store)
        self.assertEqual(rebuilt, self.lines, "the console is a projection: the store alone reproduces it")


if __name__ == "__main__":
    unittest.main()
