"""Fill protocol envelope fields. Does not start M2."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
REQUIRED = ("protocol", "protocol_version", "created_at", "correlation_id")


def now():
    return datetime.now(IST).isoformat()


def canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def object_hash(obj: dict) -> str:
    body = {k: v for k, v in obj.items() if k != "object_hash"}
    return hashlib.sha256(canonical(body)).hexdigest()[:16]


def stamp(obj: dict, correlation_id: str, created_at: str | None = None) -> dict:
    out = dict(obj)
    out.setdefault("protocol_version", 1)
    out["created_at"] = created_at or now()
    out["correlation_id"] = correlation_id
    out["object_hash"] = object_hash(out)
    missing = [k for k in REQUIRED if not out.get(k) and out.get(k) != 0]
    if missing:
        raise ValueError("protocol missing " + ", ".join(missing))
    return out


def write(path: Path, obj: dict, correlation_id: str) -> dict:
    stamped = stamp(obj, correlation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stamped, indent=2) + "\n", encoding="utf-8")
    return stamped
