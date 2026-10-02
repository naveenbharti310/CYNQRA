"""The run audit (P1 completion mandate, sections 3 to 7 and 10): every control read back from what a run persisted.

Two objectives are carried to delivery on test doubles against one Intelligence Layer, the way the hosted job runs
the p1-validation set, and the audit is read over their data root. It must pass every control those runs reached,
and catch each kind of record a broken control plane would leave behind: a decision rewritten after it was made, a
credential written anywhere, a provider's failure counted against the intelligence, an event that reports what never
happened. These tests prove the audit and the controls on test doubles, never the quality of a real model.
"""
from __future__ import annotations

import io
import json
import shutil
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from helpers import SCENARIO, TempDir, no_model_env, restore_env
from test_objective_intelligence import ModelsServer, supply_with

from cynqra import controller, objective_evidence as oe
from cynqra import run_audit
from cynqra import run_hosted_examination as rhe
from cynqra.db import Store


def checks(report: dict, name: str) -> list[dict]:
    return [c for c in report["checks"] + [c for r in report["runs"] for c in r["checks"]] if c["check"] == name]


class RunAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = no_model_env()
        cls.tmp = TempDir()
        cls.root = cls.tmp.path / "data"
        srv = ModelsServer()
        srv.broken.add("Sloppy")
        sup = supply_with(cls.root, [("Steady", 0.2), ("Sloppy", 0.4), ("Careful", 0.6)], srv)
        try:
            statements = [SCENARIO["messy"], SCENARIO["messy"] + " I also want a weekly summary of who moved stage."]
            cls.outs = [rhe.objective_run(sup, cls.root / f"objective-run-{i}", s, 5.0, to_delivery=True,
                                          max_minutes=10, log=lambda *_: None) for i, s in enumerate(statements, 1)]
        finally:
            sup.close()
            srv.close()
        (cls.root / "manifest.json").write_text(json.dumps({"results": []}), encoding="utf-8")
        cls.report = run_audit.audit(cls.root, {"FAKE_KEY": "not-a-key-but-secret-0123456789"})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        restore_env(cls.saved)

    def copy(self) -> Path:
        dst = self.tmp.path / f"copy_{self.id().rsplit('.', 1)[-1]}"
        shutil.copytree(self.root, dst)
        return dst

    def test_two_objectives_pass_every_control_they_reached(self):
        self.assertEqual([o["stage"] for o in self.outs], ["accepted", "accepted"])
        rep = self.report
        self.assertEqual(rep["failed"], [], "\n".join(rep["failed"]))
        self.assertEqual(len(rep["runs"]), 2)
        self.assertGreater(rep["summary"]["pass"], 50)
        # a control the runs never reached is reported as such, never as passed
        unreached = {c["check"] for c in rep["runs"][0]["checks"] + rep["runs"][1]["checks"]
                     if c["status"] == run_audit.NOT_EXERCISED}
        self.assertLessEqual(unreached, {"no replacement on one noisy failure",
                                         "worker identity survives an intelligence change"}, unreached)
        for name in ("objective A/B isolation", "each objective earned its own evidence",
                     "no credential in any persisted file", "every decision replays from its own snapshot",
                     "objective evidence reached real selections", "every evidence record carries its provenance",
                     "the founder-visible events were emitted", "no event reports what did not happen",
                     "only qualified intelligence was selected", "producer and verifier kept apart"):
            got = checks(rep, name)
            self.assertTrue(got and all(c["status"] == run_audit.PASS for c in got), (name, got))
        for r in rep["runs"]:
            self.assertEqual(r["lifecycle"], "OBJECTIVE_CLOSED")
            t = r["tables"]
            self.assertTrue(t["decisions"] and t["calibration_trials"] and t["candidates"] and t["tasks"])
            self.assertTrue(all(row["replayed"] for row in t["decisions"]))
        text = run_audit.render(rep)
        self.assertIn("RUN AUDIT", text)
        self.assertIn("objective A/B isolation", text)

    def test_every_committed_reselection_is_visible_once(self):
        seen = 0
        for i in (1, 2):
            s = Store(str(self.root / f"objective-run-{i}" / "cynqra.db"))
            try:
                events = [e for e in s.events() if e["event_type"] == "intelligence.reselection.triggered"]
                for d in s.all(controller.KIND):
                    if d.get("selection_mode") == "reselect" and d.get("status") == "committed":
                        seen += 1
                        n = sum(1 for e in events if e["payload"].get("decision_id") == d["decision_id"])
                        self.assertEqual(n, 1, f"{d['decision_id']} ({d['purpose']}) shown {n} times")
            finally:
                s.close()
        self.assertGreater(seen, 0, "the runs moved work off an incumbent on verified superiority at least once")

    def test_a_decision_rewritten_after_it_was_made_is_caught(self):
        root = self.copy()
        s = Store(str(root / "objective-run-1" / "cynqra.db"))
        try:
            d = next(x for x in s.all(controller.KIND) if x.get("status") == "committed" and x.get("scope") == "task")
            other = next(c["id"] for c in d["candidate_set"] if c["id"] != d["selected_intelligence"]["id"])
            s.put(controller.KIND, d["decision_id"], d | {"selected_intelligence": d["selected_intelligence"] |
                                                          {"id": other}})
        finally:
            s.close()
        rep = run_audit.audit(root)
        self.assertIn(run_audit.FAIL, [c["status"] for c in checks(rep, "decisions are immutable")])

    def test_a_credential_anywhere_fails_the_audit_and_is_never_printed(self):
        root = self.copy()
        secret = "zq-the-providers-key-9f8e7d6c5b4a"
        (root / "objective-run-2" / "notes.txt").write_text(f"token={secret}\n", encoding="utf-8")
        rep = run_audit.audit(root, {"PROVIDER_KEY": secret})
        c = checks(rep, "no credential in any persisted file")[0]
        self.assertEqual(c["status"], run_audit.FAIL)
        self.assertIn("PROVIDER_KEY in objective-run-2", c["detail"])
        self.assertNotIn(secret, run_audit.render(rep))
        self.assertNotIn(secret, json.dumps(rep, default=str))
        # a key whose variable was not named is still found by its shape
        (root / "objective-run-2" / "notes.txt").write_text("AIza" + "x" * 35, encoding="utf-8")
        self.assertEqual(checks(run_audit.audit(root), "no credential in any persisted file")[0]["status"],
                         run_audit.FAIL)

    def test_a_provider_failure_counted_against_the_intelligence_is_caught(self):
        root = self.copy()
        s = Store(str(root / "objective-run-1" / "cynqra.db"))
        try:
            e = next(x for x in s.all(oe.KIND) if x.get("verified") is True)
            s.put(oe.KIND, e["evidence_id"], e | {"verified": False, "clean": True,
                                                  "failure": {"kind": "provider", "detail": "HTTP 503"}})
        finally:
            s.close()
        rep = run_audit.audit(root)
        self.assertEqual(checks(rep, "only the intelligence's own failures carry quality")[0]["status"], run_audit.FAIL)
        self.assertEqual(checks(rep, "every evidence record carries its provenance")[0]["status"], run_audit.FAIL,
                         "the record no longer matches what was written")

    def test_an_event_reporting_what_never_happened_is_caught(self):
        root = self.copy()
        s = Store(str(root / "objective-run-2" / "cynqra.db"))
        try:
            meta = s.get("meta", "run")
            s.append(company_id=meta["company_id"], event_type="intelligence.rerouted", aggregate_type="task",
                     aggregate_id="t_01", actor_type="system", actor_id="ui", payload={"from": "a", "to": "b"},
                     correlation_id="t_01")
        finally:
            s.close()
        rep = run_audit.audit(root)
        c = [x for x in checks(rep, "no event reports what did not happen") if x["status"] == run_audit.FAIL]
        self.assertTrue(c and "intelligence.rerouted" in c[0]["detail"], c)

    def test_a_reroute_is_owed_by_a_committed_reselection(self):
        # real run 36972596704: controller.revalidate moved a planned task on new evidence, reporting the trigger
        # and the reroute; the reroute is backed by that committed reselection, not only by a replacement
        s = Store(str(self.tmp.path / f"reroute_{self.id()[-6:]}.db"))
        try:
            s.append(company_id="co", event_type="intelligence.rerouted", aggregate_type="task", aggregate_id="t_02",
                     actor_type="system", actor_id="intelligence_controller", payload={"from": "a", "to": "b"},
                     correlation_id="t_02")
            ctx = {"types": {"intelligence.rerouted": 1}, "store": s, "events": s.events(), "tasks": {},
                   "evidence": [], "meta": {}, "decisions": [{"decision_id": "sd_1", "purpose": "reselection",
                                                              "status": "committed"}]}
            out = []
            run_audit._events(out, ctx)
            got = {c["check"]: c["status"] for c in out}
            self.assertEqual(got["no event reports what did not happen"], run_audit.PASS)
            out = []
            run_audit._events(out, ctx | {"decisions": []})
            self.assertEqual({c["check"]: c["status"] for c in out}["no event reports what did not happen"],
                             run_audit.FAIL)
            self.assertEqual([r["event"] for r in ctx["tables"]["intelligence_timeline"]], ["intelligence.rerouted"])
        finally:
            s.close()

    def test_the_command_line_writes_the_report_and_says_how_it_ended(self):
        out = self.tmp.path / "audit.json"
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = run_audit.main([str(self.root), "--json", str(out)])
        self.assertEqual(code, 0, buf.getvalue()[-2000:])
        self.assertIn("summary: pass", buf.getvalue())
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["failed"], [])
        empty = self.tmp.path / "empty"
        empty.mkdir()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(run_audit.main([str(empty)]), 0)
        rep = run_audit.audit(empty)
        self.assertEqual(checks(rep, "objective A/B isolation")[0]["status"], run_audit.NOT_EXERCISED)


class ObjectiveSetTests(unittest.TestCase):
    def test_the_p1_validation_set_is_three_materially_different_objectives(self):
        got = rhe.objectives(["", "Build a thing"], "p1-validation")
        self.assertEqual([x[0] for x in got], ["objective_1", "location_tracking", "saas_platform",
                                                "research_analysis"])
        self.assertEqual(len({x[1] for x in got}), 4)
        with self.assertRaises(SystemExit):
            rhe.objectives([], "no-such-set")
        self.assertEqual(rhe.objectives([], "none"), [])
        text = json.dumps(got).lower()
        for name in ("kimi", "gemini", "claude", "gpt", "glm", "llama", "nemotron"):
            self.assertNotIn(name, text, "an objective names no model")

    def test_the_comparison_reports_choices_per_objective_never_a_ranking(self):
        runs = [{"label": "a", "selection_report": {"items": [
                    {"kind": "code", "first_choice": "m1", "verified_by": "m1"},
                    {"kind": "research", "first_choice": "m2", "verified_by": None}], "summary": {}}},
                {"label": "b", "selection_report": {"items": [
                    {"kind": "code", "first_choice": "m2", "verified_by": "m2"}], "summary": {}}}]
        cmp = rhe.comparison(runs)
        self.assertEqual(cmp["kinds_in_every_objective"], ["code"])
        self.assertEqual(cmp["kinds_chosen_differently"], ["code"])
        self.assertEqual(cmp["objectives"][0]["by_kind"]["code"]["first_choice"], {"m1": 1})
        self.assertNotIn("rank", json.dumps(cmp["objectives"]))


if __name__ == "__main__":
    unittest.main()
