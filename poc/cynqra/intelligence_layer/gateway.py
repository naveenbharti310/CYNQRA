"""The Intelligence Gateway: the one execution interface between workers and providers.

    worker's call ──▶ (intelligence id, request)
                          │
                    Intelligence Registry   the entry, its version and its connection
                          │
                    Provider Connection     how Cynqra may reach the provider
                          │
                    Credential              resolved for this call only
                          │
                    Provider Adapter        the provider's form of the call
                          │
                    transport               cynqra/model_adapter.py: the wire formats
                          │
                    provider ─▶ model ─▶ response (text, tokens, seconds, error)

A worker never knows whether its intelligence is OpenAI, Anthropic or a model on this machine, nor how it
authenticates. The gateway also enforces what belongs to access rather than to the work: the binding's version pin
(a changed version must pass its regression check before the worker continues), faults set on an intelligence for
proving replacement, a connection's rate limit, and that a retired intelligence, or one that failed its regression
check, is not called. A failure is returned as the response's error, never invented
around.
"""
from __future__ import annotations

import threading
import time
from collections import deque

from .. import model_adapter
from .contracts import REQUEST_KEYS, SupplyError
from .registry import served_version


class VersionChanged(SupplyError):
    """The intelligence bound to a worker now reports another version than the binding pinned."""

    def __init__(self, model_id: str, pinned: str, current: str):
        super().__init__(f"{model_id} changed version from {pinned or 'unversioned'} to {current or 'unversioned'}")
        self.model_id, self.pinned, self.current = model_id, pinned, current


# How long a hosted call may take before it fails as the provider's (a timeout), when nobody set a limit: four times
# the model's own 95th-percentile answer time, between DEADLINE_FLOOR_S and the hosted ceiling; with fewer than
# DEADLINE_SAMPLES answers on record, DEADLINE_DEFAULT_S. Paid run 37589136743 waited the full 20 minutes on calls
# that had hung, twice, on a model whose answers took three to five minutes.
DEADLINE_SAMPLES = 5
DEADLINE_FACTOR = 4
DEADLINE_FLOOR_S = 240
DEADLINE_DEFAULT_S = 900


class IntelligenceGateway:
    def __init__(self, registry, connections, credentials, adapters):
        self.registry, self.connections, self.credentials, self.adapters = registry, connections, credentials, adapters
        self._calls: dict[str, deque] = {}
        self.lock = threading.Lock()

    def invoke(self, model_id: str, request: dict, pinned_version: str | None = None) -> dict:
        req = {k: request[k] for k in REQUEST_KEYS if k in request}
        entry = self.registry.get(model_id)
        if entry.get("status") == "retired":
            return self._failed(entry, f"{entry['name']} is retired: {entry.get('status_note') or 'retired'}")
        if (entry.get("regression") or {}).get("status") == "failed":
            return self._failed(entry, f"{entry['name']} failed its regression check")
        if pinned_version is not None and served_version(entry) != str(pinned_version):
            raise VersionChanged(model_id, pinned_version, served_version(entry))
        conn = self.connections.find_id(entry.get("connection_id"))
        if conn is None:
            return self._failed(entry, "its provider connection was removed")
        try:
            secret = self.credentials.resolve(conn["credential_id"])
            route = self.adapters[conn["type"]].route(conn, secret, entry)
        except SupplyError as exc:
            return self._failed(entry, str(exc))
        if route.pop("_deadline_from_record", False):
            route["CYNQRA_TIMEOUT"] = str(self.deadline(model_id))
        fault = entry.get("fault") or {}
        if fault.get("offline"):
            route["offline"] = True
        if fault.get("max_reply"):
            route["CYNQRA_MAX_REPLY"] = str(fault["max_reply"])
        self._pace(conn)
        out = model_adapter.complete(req.pop("prompt"), route=route, **req)
        out["model_id"] = model_id
        out["connection_id"] = conn["id"]
        return out

    def deadline(self, model_id: str) -> int:
        """Seconds a call to this model may take: from its own answers on record (see DEADLINE_FACTOR), so a hung
        call fails in minutes on a model that answers in one, and a slow model keeps the time it needs."""
        from .adapters import HOSTED_TIMEOUT_S
        secs = sorted(float(c["seconds"]) for c in self.registry.calls(model_id)
                      if not c.get("error") and float(c.get("seconds") or 0) > 0)
        if len(secs) < DEADLINE_SAMPLES:
            return int(min(DEADLINE_DEFAULT_S, HOSTED_TIMEOUT_S))
        p95 = secs[min(len(secs) - 1, int(0.95 * len(secs)))]
        return int(min(HOSTED_TIMEOUT_S, max(DEADLINE_FLOOR_S, DEADLINE_FACTOR * p95)))

    def _pace(self, conn: dict) -> None:
        """A connection's rate limit (calls per minute), kept by waiting, not by failing the work."""
        limit = int((conn.get("rate_limits") or {}).get("calls_per_minute") or 0)
        if not limit:
            return
        with self.lock:
            q = self._calls.setdefault(conn["id"], deque())
            while True:
                t = time.time()
                while q and t - q[0] >= 60:
                    q.popleft()
                if len(q) < limit:
                    q.append(t)
                    return
                time.sleep(max(0.05, 60 - (t - q[0])))

    @staticmethod
    def _failed(entry: dict, why: str) -> dict:
        return {"text": "", "tokens_in": 0, "tokens_out": 0, "estimated": False, "latency_s": 0.0,
                "model": entry.get("name"), "model_id": entry["id"], "error": f"RuntimeError: {why}"}
