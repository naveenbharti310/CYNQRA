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
DEADLINE_SPEED_MIN_TOKENS = 500  # replies long enough to measure writing speed by
DEADLINE_WRITE_FACTOR = 1.25  # the reply limit at the model's slower measured speed, with room
DEADLINE_THINK_S = 120  # before the first token: thinking and the provider's queue


class IntelligenceGateway:
    def __init__(self, registry, connections, credentials, adapters):
        self.registry, self.connections, self.credentials, self.adapters = registry, connections, credentials, adapters
        self._calls: dict[str, deque] = {}
        self.lock = threading.Lock()

    def invoke(self, model_id: str, request: dict, pinned_version: str | None = None,
               limit_s: float | None = None) -> dict:
        """One call to an intelligence. limit_s caps a deadline the gateway sets from the model's record (never one a
        connection set): a qualification probe's first, short answer is not given the 15 minutes an unknown model
        otherwise gets."""
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
            from ..model_adapter import reply_limit
            reply = reply_limit(int(request.get("max_tokens") or 0), bool(entry.get("local")), route.get("kind") or "")
            route["CYNQRA_TIMEOUT"] = str(int(min(self.deadline(model_id, reply), limit_s or float("inf"))))
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

    def route_kind(self, model_id: str) -> str:
        """Which transport a call to this intelligence goes through (model_adapter's kind), read without its key; ""
        when that cannot be told, which the budget then treats as the most a hosted call may write."""
        entry = self.registry.get(model_id)
        conn = self.connections.find_id(entry.get("connection_id"))
        if conn is None or conn.get("type") not in self.adapters:
            return ""
        try:
            return str(self.adapters[conn["type"]].route(conn, None, entry).get("kind") or "")
        except Exception:  # noqa: BLE001 - a route that needs its key to be built: the safe upper bound applies
            return ""

    def deadline(self, model_id: str, reply_tokens: int = 0) -> int:
        """Seconds a call to this model may take: from its own answers on record (see DEADLINE_FACTOR), so a hung
        call fails in minutes on a model that answers in one, and a slow model keeps the time it needs. A call that
        may write a long reply also gets the time that reply takes at the model's slower measured writing speeds
        (the real run of 7 Oct: a model whose record was all short documents was cut off twice at 468 s writing
        code at 52 to 86 tokens a second, replies up to 31,000 tokens)."""
        from .adapters import HOSTED_TIMEOUT_S
        calls = [c for c in self.registry.calls(model_id) if not c.get("error") and float(c.get("seconds") or 0) > 0]
        secs = sorted(float(c["seconds"]) for c in calls)
        if len(secs) < DEADLINE_SAMPLES:
            base = DEADLINE_DEFAULT_S
        else:
            base = max(DEADLINE_FLOOR_S, DEADLINE_FACTOR * secs[min(len(secs) - 1, int(0.95 * len(secs)))])
        speeds = sorted(int(c.get("tokens_out") or 0) / float(c["seconds"]) for c in calls
                        if int(c.get("tokens_out") or 0) >= DEADLINE_SPEED_MIN_TOKENS)
        if reply_tokens and len(speeds) >= DEADLINE_SAMPLES:
            slow = speeds[int(0.1 * len(speeds))]  # its slower answers, not its average
            base = max(base, DEADLINE_WRITE_FACTOR * reply_tokens / max(slow, 1.0) + DEADLINE_THINK_S)
        return int(min(HOSTED_TIMEOUT_S, base))

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
