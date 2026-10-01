"""Unit tests: event store, policy, protocol objects, the test runner and the verifiers."""
from __future__ import annotations

import os
import shutil
import sqlite3
import unittest

from helpers import POC, TempDir  # noqa: F401  (sets sys.path)

from cynqra import policy
from cynqra.db import Store, digest
from cynqra.protocol import ProtocolError, build
from cynqra.testrunner import clean_env, failure_summary, run_unittests
from cynqra.verifier import backtest, check_documents, lint_documents

FILES = POC / "scenarios" / "candidate_tracker" / "files"
RESTAURANT = POC / "scenarios" / "restaurant_forecast" / "files"


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

    def test_event_chain_is_verifiable_and_uses_full_sha256(self):
        a = self._append()
        b = self._append()
        self.assertEqual(len(a["event_hash"]), 64)
        self.assertEqual(b["prev_event_hash"], a["event_hash"])
        self.assertTrue(self.s.verify_event_chain())

    def test_event_append_is_idempotent_when_key_reused(self):
        a = self._append(idempotency_key="same-command")
        b = self._append(idempotency_key="same-command", payload={"x": 999})
        self.assertEqual(a["event_id"], b["event_id"])
        self.assertEqual(self.s.count_events(), 1)

    def test_task_lease_allows_one_live_holder(self):
        first = self.s.claim_task("t_01", "w_eng_a", lease_seconds=60)
        second = self.s.claim_task("t_01", "w_eng_b", lease_seconds=60)
        self.assertTrue(first)
        self.assertIsNone(second)
        self.assertEqual(self.s.task_lease("t_01")["holder_id"], "w_eng_a")
        self.assertTrue(self.s.release_task("t_01", first))
        self.assertTrue(self.s.claim_task("t_01", "w_eng_b", lease_seconds=60))


class PolicyTests(unittest.TestCase):  # A13
    def ev(self, role, action, **kw):
        return policy.evaluate(role=role, action_type=action, **kw)["decision"]

    def test_low_work_in_workspace_is_allowed(self):
        self.assertEqual(self.ev("Engineer", "write_file"), "ALLOW")
        self.assertEqual(self.ev("Engineer", "run_tests"), "ALLOW")
        self.assertEqual(self.ev("CTO", "assign_task"), "ALLOW", "a cofounder hands out its team's work")
        self.assertEqual(self.ev("PM", "assign_task"), "DENY", "a team member does not hand out work")

    def test_medium_needs_an_approval_on_record_d17(self):
        for role, action in (("Engineer", "merge_to_main"), ("CTO", "merge_to_main"), ("PM", "product_rule_decision")):
            d = policy.evaluate(role=role, action_type=action)
            self.assertEqual(d["decision"], "REQUIRE_APPROVAL")
            self.assertEqual(d["required_approver"], "founder or accountable cofounder",
                             "one that can be undone may be settled by its cofounder (execution.door)")

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
        self.assertEqual(q["proposes"], ["BackendEngineer", "CTO", "DataScientist", "Engineer", "FrontendEngineer"],
                         "every role in the catalog that writes code proposes its merge; none executes it")
        self.assertEqual(q["executes"], [])
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

    def test_results_are_read_through_the_request_log_of_a_server_under_test(self):
        # http.server logs each request to stderr in the middle of unittest's "name (id) ... ok" line. The first
        # real Windows journey lost a named failure this way and told the engineer only "did not complete".
        (self.tmp.path / "test_web.py").write_text(
            "import threading, unittest\n"
            "from http.client import HTTPConnection\n"
            "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
            "class H(BaseHTTPRequestHandler):\n"
            "    def do_GET(self):\n"
            "        self.send_response(200 if self.path == '/health' else 500)\n"
            "        self.end_headers()\n"
            "class T(unittest.TestCase):\n"
            "    @classmethod\n"
            "    def setUpClass(cls):\n"
            "        cls.s = HTTPServer(('127.0.0.1', 0), H)\n"
            "        threading.Thread(target=cls.s.serve_forever, daemon=True).start()\n"
            "    @classmethod\n"
            "    def tearDownClass(cls):\n"
            "        cls.s.shutdown()\n"
            "    def get(self, path):\n"
            "        c = HTTPConnection('127.0.0.1', self.s.server_address[1], timeout=5)\n"
            "        c.request('GET', path)\n"
            "        return c.getresponse().status\n"
            "    def test_health(self):\n"
            "        self.assertEqual(self.get('/health'), 200)\n"
            "    def test_orders(self):\n"
            "        \"\"\"The order list answers.\"\"\"\n"
            "        self.assertEqual(self.get('/orders'), 200)\n", encoding="utf-8")
        r = run_unittests(self.tmp.path)
        self.assertIn('"GET /health HTTP/1.1" 200', r["output"])
        self.assertEqual([(x["id"], x["status"]) for x in r["tests"]],
                         [("test_web.test_health", "ok"), ("test_web.test_orders", "FAIL")])
        self.assertEqual(r["failed"], ["test_web.test_orders"])
        self.assertEqual(failure_summary(r), "Failing tests: test_web.test_orders.")

    def test_a_test_that_hangs_is_named_with_what_usually_causes_it(self):
        (self.tmp.path / "test_wait.py").write_text(
            "import time, unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_a(self):\n"
            "        pass\n"
            "    def test_b_server(self):\n"
            "        time.sleep(60)\n", encoding="utf-8")
        r = run_unittests(self.tmp.path, timeout=3)
        self.assertFalse(r["passed"])
        self.assertIn("did not finish within 3 s and were stopped while test_wait.test_b_server was running", r["problem"])
        self.assertIn("daemon thread", r["problem"])
        self.assertEqual(failure_summary(r), r["problem"])

    def test_a_test_process_that_dies_is_named(self):
        (self.tmp.path / "test_exit.py").write_text(
            "import os, unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_a(self):\n"
            "        pass\n"
            "    def test_b(self):\n"
            "        os._exit(3)\n", encoding="utf-8")
        r = run_unittests(self.tmp.path)
        self.assertFalse(r["passed"])
        self.assertIn("ended during test_exit.test_b (exit code 3)", failure_summary(r))

    def test_failure_summary_for_class_fixtures_and_missing_tests(self):
        (self.tmp.path / "test_fix.py").write_text(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    @classmethod\n"
            "    def setUpClass(cls):\n"
            "        raise OSError('address already in use')\n"
            "    def test_a(self):\n"
            "        pass\n", encoding="utf-8")
        self.assertEqual(failure_summary(run_unittests(self.tmp.path)), "Failing tests: test_fix.setUpClass.")
        (self.tmp.path / "test_fix.py").unlink()
        self.assertEqual(failure_summary(run_unittests(self.tmp.path)), "There is no test_*.py at the repository root.")

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


class VerifierTests(unittest.TestCase):  # Stage 9: each task type's verifier
    def setUp(self):
        self.tmp = TempDir()

    def tearDown(self):
        self.tmp.cleanup()

    OBJ = {"constraints": "No public careers site",
           "success_criteria": "A recruiter can create a candidate, set a stage, list all candidates, and filter stuck ones"}

    def test_documents_need_their_sections_numbered_checks_and_requirement_ids(self):
        task = {"documents": ["product_spec", "acceptance"], "requirement_ids": ["r_01", "r_06"]}
        docs = {p.name: p.read_text(encoding="utf-8") for p in (FILES / "t_01").iterdir()}
        self.assertTrue(check_documents(docs, task, self.OBJ)["passed"])
        spec = docs["spec.md"].replace("## Out of scope", "## Later")
        r = check_documents({"spec.md": spec, "acceptance.md": "1. one\n2. two\n"}, task, self.OBJ)
        self.assertEqual({f["rule"] for f in r["findings"]}, {"product_spec_sections", "acceptance_sections"})
        r = check_documents(docs, {**task, "requirement_ids": ["r_01", "r_09"]}, self.OBJ)
        self.assertEqual([f["why"] for f in r["findings"]], ["requirements not cited: r_09"])

    def test_the_objective_lint_applies_only_to_briefs_and_specifications(self):
        method = "## Method\nWeekday means.\n## Evaluation\nBacktest. r_03"
        task = {"documents": ["method"], "requirement_ids": ["r_03"]}
        self.assertTrue(check_documents({"method.md": method}, task, self.OBJ)["passed"])

    def test_no_document_is_not_a_pass(self):
        self.assertFalse(check_documents({"x.py": "print(1)"}, {"documents": ["design"]}, self.OBJ)["passed"])

    def test_the_backtest_rejects_a_flat_forecast_and_accepts_the_weekday_mean(self):
        shutil.copy(RESTAURANT / "t_07/attempt1/forecast.py", self.tmp.path)
        flat = backtest(self.tmp.path)
        self.assertFalse(flat["passed"])
        self.assertGreater(flat["model_mae"], flat["baseline_mae"])
        shutil.copy(RESTAURANT / "t_07/attempt2/forecast.py", self.tmp.path)
        weekday = backtest(self.tmp.path)
        self.assertTrue(weekday["passed"], weekday)
        self.assertLess(weekday["model_mae"], weekday["baseline_mae"])

    def test_the_backtest_refuses_a_missing_or_broken_forecast(self):
        self.assertIn("missing", backtest(self.tmp.path)["why"])
        (self.tmp.path / "forecast.py").write_text("def forecast(history, horizon):\n    return [-1] * horizon\n")
        self.assertIn("non-negative", backtest(self.tmp.path)["why"])
        (self.tmp.path / "forecast.py").write_text("def forecast(history, horizon):\n    raise RuntimeError('x')\n")
        self.assertIn("forecast() failed", backtest(self.tmp.path)["why"])


if __name__ == "__main__":
    unittest.main()
