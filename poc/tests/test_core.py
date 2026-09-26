"""Unit tests: event store, policy, protocol objects, verification helpers."""
from __future__ import annotations

import os
import shutil
import sqlite3
import unittest

from helpers import POC, TempDir  # noqa: F401  (sets sys.path)

from cynqra import policy
from cynqra.db import Store, digest
from cynqra.protocol import ProtocolError, build
from cynqra.verification import clean_env, lint_documents, run_unittests

FILES = POC / "scenarios" / "candidate_tracker" / "files"


class EventStoreTests(unittest.TestCase):  # A11
    def setUp(self):
        self.tmp = TempDir()
        self.s = Store(str(self.tmp.path / "t.db"))

    def tearDown(self):
        self.s.close()
        self.tmp.cleanup()

    def _append(self, **kw):
        base = dict(company_id="c", event_type="task.created", aggregate_type="task", aggregate_id="t_01",
                    actor_type="worker", actor_id="w_pm", payload={"x": 1}, correlation_id="t_01")
        base.update(kw)
        return self.s.append(**base)

    def test_envelope_has_every_d18_field_plus_d32(self):
        row = self._append(protocol_hash="abc", test_ids=["m.t"])
        for f in ("event_id", "event_type", "event_version", "company_id", "aggregate_type", "aggregate_id",
                  "aggregate_version", "actor_type", "actor_id", "authority_snapshot", "policy_decision",
                  "correlation_id", "causation_id", "command_id", "idempotency_key", "context_refs", "payload",
                  "payload_schema_version", "source_service", "created_at", "protocol_hash", "test_ids"):
            self.assertIn(f, row)

    def test_events_cannot_be_updated_or_deleted(self):
        self._append()
        with self.assertRaises(sqlite3.DatabaseError):
            self.s.conn.execute("UPDATE events SET event_type='x'")
        with self.assertRaises(sqlite3.DatabaseError):
            self.s.conn.execute("DELETE FROM events")
        self.assertEqual(self.s.count_events(), 1)

    def test_causation_chains_to_the_previous_event(self):
        a = self._append()
        b = self._append()
        self.assertEqual(b["causation_id"], a["event_id"])

    def test_personal_data_keys_are_refused(self):  # D-22
        with self.assertRaises(ValueError):
            self._append(payload={"name": "Priya Shah"})

    def test_objects_are_content_addressed(self):
        h1 = self.s.put_object("protocol", {"a": 1})
        h2 = self.s.put_object("protocol", {"a": 1})
        self.assertEqual(h1, h2)
        self.assertEqual(self.s.get_object(h1), {"a": 1})
        self.assertIsNone(self.s.get_object("nope"))

    def test_filter_by_correlation(self):
        self._append(correlation_id="t_01")
        self._append(correlation_id="t_02")
        self.assertEqual(len(self.s.events(correlation_id="t_02")), 1)


class PolicyTests(unittest.TestCase):  # A13
    def ev(self, role, action, **kw):
        return policy.evaluate(role=role, action_type=action, **kw)["decision"]

    def test_low_work_in_workspace_is_allowed(self):
        self.assertEqual(self.ev("Engineer", "write_file"), "ALLOW")
        self.assertEqual(self.ev("Engineer", "run_tests"), "ALLOW")
        self.assertEqual(self.ev("PM", "assign_task"), "ALLOW")

    def test_medium_goes_to_the_founder_d17(self):
        for role, action in (("Engineer", "merge_to_main"), ("CTO", "merge_to_main"), ("PM", "product_rule_decision")):
            d = policy.evaluate(role=role, action_type=action)
            self.assertEqual(d["decision"], "REQUIRE_APPROVAL")
            self.assertEqual(d["required_approver"], "founder")

    def test_production_deploy_needs_the_founder_d21(self):
        d = policy.evaluate(role="CTO", action_type="deploy_production", autonomy_level="L3")
        self.assertEqual(d["decision"], "REQUIRE_APPROVAL")
        self.assertIn("D-21", d["reason"])

    def test_prohibited_is_denied_for_everyone(self):
        for role in ("Engineer", "PM", "CTO"):
            for action in ("external_message", "move_money", "change_objective", "change_budget", "change_authority"):
                self.assertEqual(self.ev(role, action), "DENY", (role, action))

    def test_roles_outside_the_matrix_are_denied(self):
        self.assertEqual(self.ev("Engineer", "deploy_production"), "DENY")
        self.assertEqual(self.ev("Engineer", "assign_task"), "DENY")
        self.assertEqual(self.ev("Intern", "write_file"), "DENY")
        self.assertEqual(self.ev("CTO", "launch_rockets"), "DENY")

    def test_kill_switch_and_breaker(self):
        self.assertEqual(self.ev("Engineer", "write_file", frozen=True), "DENY")
        self.assertEqual(self.ev("Engineer", "write_file", budget_state="breaker"), "DENY")
        self.assertEqual(self.ev("Engineer", "send_protocol", budget_state="breaker"), "ALLOW")

    def test_graph_query(self):
        q = policy.who_may("merge_to_main")
        self.assertEqual(q["approves"], "founder")
        self.assertEqual(q["proposes"], ["CTO", "Engineer"])
        self.assertIn("prohibited", policy.who_may("external_message")["approves"])
        self.assertEqual(policy.who_may("write_file")["approves"], "no approval needed at LOW")


class ProtocolTests(unittest.TestCase):  # A7
    def test_stamped_envelope(self):
        o = build("Handoff", {"acceptance_check": "x", "artifacts": ["a"]},
                  {"from_worker": "w_pm", "to_worker": "w_eng_a", "task_id": "t_01"}, "t_01")
        for k in ("protocol", "protocol_version", "created_at", "correlation_id", "object_hash"):
            self.assertTrue(o[k])
        self.assertEqual(o["object_hash"], digest({k: v for k, v in o.items() if k != "object_hash"}))

    def test_content_cannot_reroute(self):
        o = build("Handoff", {"acceptance_check": "x", "to_worker": "founder", "from_worker": "w_cto"},
                  {"from_worker": "w_pm", "to_worker": "w_eng_a", "task_id": "t_01"}, "t_01")
        self.assertEqual((o["from_worker"], o["to_worker"]), ("w_pm", "w_eng_a"))

    def test_missing_fields_are_refused(self):
        with self.assertRaises(ProtocolError):
            build("Blocker", {"description": ""}, {"raised_by": "w_eng_b", "task_id": "t_04"}, "t_04")
        with self.assertRaises(ProtocolError):
            build("Memo", {}, {}, "t_01")


class VerificationHelperTests(unittest.TestCase):  # A8
    def setUp(self):
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_tests_pass_and_ids_are_parsed(self):
        for f in ("t_03/store.py", "t_03/test_store.py"):
            shutil.copy(FILES / f, self.tmp.path)
        r = run_unittests(self.tmp.path)
        self.assertTrue(r["passed"])
        self.assertEqual(r["ran"], 10)
        self.assertIn("test_store.test_list_returns_all", [t["id"] for t in r["tests"]])

    def test_the_seeded_defect_fails(self):
        shutil.copy(FILES / "t_03/attempt1/store.py", self.tmp.path)
        shutil.copy(FILES / "t_03/test_store.py", self.tmp.path)
        r = run_unittests(self.tmp.path)
        self.assertFalse(r["passed"])
        self.assertEqual(r["failed"], ["test_store.test_list_returns_all"])

    def test_no_tests_is_not_a_pass(self):
        r = run_unittests(self.tmp.path)
        self.assertFalse(r["passed"])
        self.assertEqual(r["ran"], 0)

    def test_workers_never_see_keys(self):
        os.environ["ANTHROPIC_API_KEY"] = "sk-test-should-not-leak"
        try:
            env = clean_env()
            self.assertNotIn("ANTHROPIC_API_KEY", env)
            self.assertFalse(any("sk-test" in v for v in env.values()))
        finally:
            os.environ.pop("ANTHROPIC_API_KEY", None)

    def test_document_lint(self):
        obj = {"constraints": "No public careers site", "success_criteria": "A recruiter can create a candidate, set a stage, list all candidates, and filter stuck ones"}
        docs = {p.name: p.read_text(encoding="utf-8") for p in (FILES / "t_01").iterdir()}
        self.assertTrue(lint_documents(docs, obj)["passed"])
        bad = lint_documents({"spec.md": "A dashboard for investors."}, obj)
        self.assertFalse(bad["passed"])
        self.assertEqual({f["rule"] for f in bad["findings"]}, {"constraint_echoed", "success_covered"})
        self.assertFalse(lint_documents({"a.md": ""}, obj)["passed"])


if __name__ == "__main__":
    unittest.main()
