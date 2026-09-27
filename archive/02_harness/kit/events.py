"""Event logger with protocol hash and test ids. Kit only. Not M2."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from protocol import now

FIELDS = [
    "event_id",
    "event_type",
    "event_version",
    "company_id",
    "aggregate_type",
    "aggregate_id",
    "aggregate_version",
    "actor_type",
    "actor_id",
    "authority_snapshot",
    "policy_decision",
    "correlation_id",
    "causation_id",
    "command_id",
    "idempotency_key",
    "context_refs",
    "payload",
    "payload_schema_version",
    "source_service",
    "created_at",
    "protocol_hash",
    "test_ids",
]


def _next_id(path: Path, prefix: str) -> str:
    if not path.exists():
        return f"{prefix}_001"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    return f"{prefix}_{len(rows)+1:03d}"


def append(
    path: Path,
    *,
    event_type: str,
    company_id: str,
    aggregate_type: str,
    aggregate_id: str,
    actor_type: str,
    actor_id: str,
    correlation_id: str,
    payload: dict,
    protocol_hash: str = "",
    test_ids: list[str] | None = None,
    policy_decision: str = "ALLOW",
    authority_snapshot: str = "platform",
    causation_id: str = "",
) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    n = 0 if new_file else sum(1 for _ in path.open(encoding="utf-8")) - 1
    rec = {k: "" for k in FIELDS}
    rec.update(
        {
            "event_id": f"evt_{n+1:03d}",
            "event_type": event_type,
            "event_version": "1",
            "company_id": company_id,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "aggregate_version": "1",
            "actor_type": actor_type,
            "actor_id": actor_id,
            "authority_snapshot": authority_snapshot,
            "policy_decision": policy_decision,
            "correlation_id": correlation_id,
            "causation_id": causation_id,
            "command_id": f"cmd_{n+1:03d}",
            "idempotency_key": f"idemp_{n+1:03d}",
            "context_refs": "[]",
            "payload": json.dumps(payload, separators=(",", ":")),
            "payload_schema_version": "1",
            "source_service": "cynqra_kit",
            "created_at": now(),
            "protocol_hash": protocol_hash,
            "test_ids": json.dumps(test_ids or []),
        }
    )
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerow(rec)
    return rec
