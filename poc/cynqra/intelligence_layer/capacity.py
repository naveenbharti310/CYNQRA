"""Provider capacity and quota coordination.

Capacity is a resource just like money: it can be available, reserved by an in-flight
call, and consumed in a rolling quota window. Waiting happens without holding the
application lock.
"""
from __future__ import annotations

import time
import uuid

from .contracts import SupplyError


class CapacityError(SupplyError):
    pass


def _limits(conn: dict) -> tuple[int, int, int]:
    rl = conn.get("rate_limits") or {}
    calls = max(0, int(rl.get("calls_per_minute") or 0))
    tokens = max(0, int(rl.get("tokens_per_minute") or 0))
    concurrency = max(0, int(rl.get("max_concurrency") or 0))
    return calls, tokens, concurrency


def estimate_request_tokens(request: dict) -> int:
    prompt = str(request.get("prompt") or "")
    prompt_tokens = max(1, len(prompt) // 4)
    output_tokens = request.get("max_tokens") or request.get("max_completion_tokens") or 4000
    try:
        output_tokens = max(1, int(output_tokens))
    except (TypeError, ValueError):
        output_tokens = 4000
    return prompt_tokens + output_tokens


class CapacityManager:
    """Per-connection RPM/TPM/concurrency limiter backed by the run's Store."""

    WINDOW_S = 60.0

    def __init__(self, store):
        self.store = store

    def _state(self, conn_id: str) -> dict:
        return self.store.get("provider_capacity", conn_id) or {"id": conn_id, "active": 0, "events": []}

    def _clean(self, state: dict, now_ts: float) -> None:
        state["events"] = [e for e in state.get("events", []) if now_ts - float(e.get("at", 0)) < self.WINDOW_S]

    def acquire(self, conn: dict, estimated_tokens: int, timeout_s: float = 120.0) -> str:
        calls_limit, tokens_limit, concurrency_limit = _limits(conn)
        if not any((calls_limit, tokens_limit, concurrency_limit)):
            return ""

        started = time.time()
        reservation_id = "cap_" + uuid.uuid4().hex
        while True:
            with self.store.lock:
                ts = time.time()
                state = self._state(conn["id"])
                self._clean(state, ts)
                events = state["events"]
                call_count = len(events)
                token_count = sum(int(e.get("tokens", 0)) for e in events)
                blocked = (
                    bool(concurrency_limit) and int(state.get("active", 0)) >= concurrency_limit
                    or bool(calls_limit) and call_count >= calls_limit
                    or bool(tokens_limit) and token_count + estimated_tokens > tokens_limit
                )
                if not blocked:
                    state["active"] = int(state.get("active", 0)) + 1
                    events.append({"id": reservation_id, "at": ts, "tokens": int(max(0, estimated_tokens))})
                    self.store.put("provider_capacity", conn["id"], state)
                    return reservation_id

                waits = []
                if events:
                    waits.append(max(0.01, self.WINDOW_S - (ts - float(events[0]["at"]))))
                wait_s = min(waits or [0.25], 0.5)

            if time.time() - started >= timeout_s:
                raise CapacityError(f"provider capacity is exhausted for {conn.get('name') or conn['id']}")
            time.sleep(wait_s)

    def release(self, conn: dict, reservation_id: str, actual_tokens: int | None = None) -> None:
        if not reservation_id:
            return
        with self.store.lock:
            ts = time.time()
            state = self._state(conn["id"])
            self._clean(state, ts)
            state["active"] = max(0, int(state.get("active", 0)) - 1)
            if actual_tokens is not None:
                for event in reversed(state["events"]):
                    if event.get("id") == reservation_id:
                        event["tokens"] = max(int(event.get("tokens", 0)), int(actual_tokens))
                        break
            self.store.put("provider_capacity", conn["id"], state)

    def snapshot(self, conn: dict) -> dict:
        with self.store.lock:
            state = self._state(conn["id"])
            self._clean(state, time.time())
            events = state["events"]
            return {
                "connection_id": conn["id"],
                "active": int(state.get("active", 0)),
                "calls_last_minute": len(events),
                "tokens_last_minute": sum(int(e.get("tokens", 0)) for e in events),
                "limits": {
                    "calls_per_minute": _limits(conn)[0],
                    "tokens_per_minute": _limits(conn)[1],
                    "max_concurrency": _limits(conn)[2],
                },
            }
