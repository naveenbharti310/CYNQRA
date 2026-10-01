"""P1 Intelligence Plane regression tests."""
from __future__ import annotations

import unittest

from helpers import TempDir

from cynqra import binding
from cynqra.intelligence_layer.capacity import CapacityManager
from cynqra.intelligence_layer.qualification import QualificationEngine
from test_intelligence_supply import SupplyBase


class IdentityAndBindingTests(SupplyBase):
    def test_discovery_creates_artifact_offering_and_execution_profile(self):
        entry = self.reg.get("model-a")
        self.assertTrue(entry["artifact_id"])
        self.assertTrue(entry["provider_offering_id"])
        self.assertTrue(entry["execution_profile_id"])
        artifact = self.supply.store.get("intelligence_artifact", entry["artifact_id"])
        offering = self.supply.store.get("provider_offering", entry["provider_offering_id"])
        profile = self.supply.store.get("execution_profile", entry["execution_profile_id"])
        self.assertEqual(artifact["publisher"], entry.get("publisher_name") or entry.get("publisher") or entry.get("provider"))
        self.assertEqual(offering["access_provider"], entry["access_provider"])
        self.assertEqual(profile["artifact_id"], artifact["id"])

    def test_new_profile_is_not_misattributed_to_the_old_profile(self):
        entry = self.reg.get("model-a")
        old_profile = entry["execution_profile_id"]
        self.reg.record_call("model-a", role="Engineer", purpose="work", task_kind="code",
                             usage={"tokens_in": 10, "tokens_out": 5, "latency_s": 1, "execution_profile_id": old_profile},
                             run_id="r1")
        self.reg.record_outcome("model-a", role="Engineer", task_kind="code", task_id="t1", run_id="r1",
                                attempt=1, verified=True, usd=0.01, seconds=1, tokens=15,
                                execution_profile_id=old_profile)
        self.reg.register({"ref": entry["ref"], "name": entry["name"], "version": "p1-new"},
                           connection_id=entry["connection_id"])
        fresh = self.reg.get("model-a")
        self.assertNotEqual(fresh["execution_profile_id"], old_profile)
        self.assertEqual(self.reg.stats("model-a")["attempts"], 0)
        hist = self.reg.outcomes("model-a")
        self.assertEqual(hist[0]["execution_profile_id"], old_profile)

    def test_binding_epochs_preserve_worker_identity(self):
        e = self.engine()
        wid = "w_eng_a"
        first = binding.current(e.store, wid)
        e.model_of(wid)
        other = next(m for m in self.reg.available() if m["id"] != first["intelligence_id"])
        b2 = binding.bind(e, wid, other, reason="P1 test replacement", by="test")
        self.assertEqual(b2["worker_id"], wid)
        self.assertGreater(b2["epoch"], first["epoch"])
        self.assertEqual(b2["history"][-1]["epoch"], first["epoch"])
        epoch = e.store.get("binding_epoch", b2["binding_epoch_id"])
        self.assertEqual(epoch["previous_binding_epoch_id"], first["binding_epoch_id"])
        e.close()


class CapacityTests(unittest.TestCase):
    def test_connection_capacity_tracks_active_and_consumed_calls(self):
        tmp = TempDir()
        try:
            from cynqra.db import Store
            store = Store(str(tmp.path / "cap.db"))
            manager = CapacityManager(store)
            conn = {"id": "conn_1", "name": "test", "rate_limits": {"max_concurrency": 1, "calls_per_minute": 10}}
            lease = manager.acquire(conn, 100)
            snap = manager.snapshot(conn)
            self.assertEqual(snap["active"], 1)
            self.assertEqual(snap["calls_last_minute"], 1)
            manager.release(conn, lease, actual_tokens=80)
            snap = manager.snapshot(conn)
            self.assertEqual(snap["active"], 0)
            self.assertEqual(snap["tokens_last_minute"], 100)
            store.close()
        finally:
            tmp.cleanup()


class QualificationTests(SupplyBase):
    def test_unqualified_model_is_blocked_for_normal_calls_but_allowed_for_calibration(self):
        entry = self.reg.get("model-a")
        self.reg.set_regression("model-a", False, "P1 test: awaiting qualification")
        blocked = self.supply.gateway.invoke("model-a", {"prompt": "x", "max_tokens": 16})
        self.assertIn("not qualified", blocked["error"])
        calibrated = self.supply.gateway.invoke(
            "model-a", {"prompt": "Convert the founder objective: a bakery tracker", "max_tokens": 512},
            mode="qualification")
        self.assertFalse(calibrated.get("error"))
        self.assertEqual(calibrated["execution_profile_id"], entry["execution_profile_id"])

    def test_cheap_qualification_produces_candidate_evidence_without_assigning(self):
        self.reg.set_regression("model-a", False, "P1 test: awaiting qualification")
        q = QualificationEngine(self.supply).cheap_probe("model-a")
        self.assertIn(q["status"], ("candidate", "failed"))
        self.assertTrue(q["execution_profile_id"])
        self.assertNotEqual(self.reg.get("model-a")["regression"]["status"], "passed",
                            "cheap qualification alone cannot make a model assignable")

    def test_deep_qualification_qualifies_a_real_provider_profile(self):
        q = QualificationEngine(self.supply).deep_probe("model-a")
        self.assertEqual(q["status"], "qualified")
        self.assertTrue(self.reg.availability(self.reg.get("model-a"))[0])
        self.assertTrue(any(x["depth"] == "deep" for x in QualificationEngine(self.supply).history("model-a")))


if __name__ == "__main__":
    unittest.main()
