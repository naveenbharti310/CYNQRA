"""Storage for the POC: one SQLite file per company run.

Three tables:
  events    the append only event log, envelope per D-18 plus protocol_hash and
            test_ids (D-32 proposal). Triggers reject every UPDATE and DELETE.
  entities  read models: current state of each object, rebuilt as events happen.
  objects   content addressed store for protocol objects and file snapshots, so
            an event can carry a hash and replay can fetch what it points at.

M2 target is Postgres with the same shape (IMPLEMENTATION_DECISIONS_LIVE.md).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT UNIQUE NOT NULL,
  event_type TEXT NOT NULL,
  event_version INTEGER NOT NULL,
  company_id TEXT NOT NULL,
  aggregate_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  aggregate_version INTEGER NOT NULL,
  actor_type TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  authority_snapshot TEXT NOT NULL,
  policy_decision TEXT NOT NULL,
  correlation_id TEXT NOT NULL,
  causation_id TEXT,
  command_id TEXT NOT NULL,
  idempotency_key TEXT UNIQUE NOT NULL,
  context_refs TEXT NOT NULL,
  payload TEXT NOT NULL,
  payload_schema_version INTEGER NOT NULL,
  source_service TEXT NOT NULL,
  created_at TEXT NOT NULL,
  protocol_hash TEXT,
  test_ids TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events are append only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events are append only'); END;
CREATE TABLE IF NOT EXISTS entities (
  kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY (kind, id)
);
CREATE TABLE IF NOT EXISTS objects (
  hash TEXT PRIMARY KEY, kind TEXT NOT NULL, body TEXT NOT NULL
);
"""

# Payload keys that must never appear: D-22, events carry references only.
FORBIDDEN_PAYLOAD_KEYS = {"name", "email", "phone", "address", "candidate_name", "founder_name"}


def now() -> str:
    return datetime.now(IST).isoformat(timespec="milliseconds")


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(obj) -> str:
    raw = obj if isinstance(obj, (bytes, bytearray)) else canonical(obj).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


class Store:
    def __init__(self, path: str):
        self.path = path
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    # events ---------------------------------------------------------------
    def append(self, *, company_id: str, event_type: str, aggregate_type: str, aggregate_id: str,
               actor_type: str, actor_id: str, payload: dict, correlation_id: str,
               authority_snapshot: str = "platform", policy_decision: str = "ALLOW",
               causation_id: str | None = None, context_refs: list | None = None,
               protocol_hash: str | None = None, test_ids: list | None = None,
               aggregate_version: int = 1, source_service: str = "cynqra_poc") -> dict:
        bad = FORBIDDEN_PAYLOAD_KEYS & set(payload)
        if bad:
            raise ValueError(f"event payload may not carry personal data keys: {sorted(bad)}")
        with self.lock:
            last = self.conn.execute("SELECT event_id FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            eid = "evt_" + uuid.uuid4().hex[:12]
            row = {
                "event_id": eid,
                "event_type": event_type,
                "event_version": 1,
                "company_id": company_id,
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "aggregate_version": aggregate_version,
                "actor_type": actor_type,
                "actor_id": actor_id,
                "authority_snapshot": authority_snapshot,
                "policy_decision": policy_decision,
                "correlation_id": correlation_id,
                "causation_id": causation_id or (last[0] if last else None),
                "command_id": "cmd_" + uuid.uuid4().hex[:12],
                "idempotency_key": "idem_" + uuid.uuid4().hex[:16],
                "context_refs": json.dumps(context_refs or []),
                "payload": canonical(payload),
                "payload_schema_version": 1,
                "source_service": source_service,
                "created_at": now(),
                "protocol_hash": protocol_hash,
                "test_ids": json.dumps(test_ids or []),
            }
            cols = ",".join(row)
            marks = ",".join("?" for _ in row)
            cur = self.conn.execute(f"INSERT INTO events ({cols}) VALUES ({marks})", list(row.values()))
            row["seq"] = cur.lastrowid
            return row

    def events(self, after: int = 0, correlation_id: str | None = None, limit: int = 100000) -> list[dict]:
        with self.lock:
            q = "SELECT * FROM events WHERE seq > ?"
            args: list = [after]
            if correlation_id:
                q += " AND correlation_id = ?"
                args.append(correlation_id)
            q += " ORDER BY seq LIMIT ?"
            args.append(limit)
            cur = self.conn.execute(q, args)
            cols = [c[0] for c in cur.description]
            out = []
            for r in cur.fetchall():
                d = dict(zip(cols, r))
                d["payload"] = json.loads(d["payload"])
                d["context_refs"] = json.loads(d["context_refs"])
                d["test_ids"] = json.loads(d["test_ids"])
                out.append(d)
            return out

    def last_events(self, n: int) -> list[dict]:
        """The newest n events, oldest first, without reading the whole log (the screen asks for them every poll)."""
        with self.lock:
            row = self.conn.execute("SELECT seq FROM events ORDER BY seq DESC LIMIT 1 OFFSET ?", (n,)).fetchone()
        return self.events(after=row[0] if row else 0)

    def count_events(self) -> int:
        with self.lock:
            return self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    # entities -------------------------------------------------------------
    def put(self, kind: str, id_: str, data: dict) -> dict:
        with self.lock:
            self.conn.execute(
                "INSERT INTO entities(kind,id,data,updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                (kind, id_, json.dumps(data), now()),
            )
            return data

    def get(self, kind: str, id_: str) -> dict | None:
        with self.lock:
            r = self.conn.execute("SELECT data FROM entities WHERE kind=? AND id=?", (kind, id_)).fetchone()
            return json.loads(r[0]) if r else None

    def delete(self, kind: str, id_: str) -> None:
        """Entities only; the event log stays append only."""
        with self.lock:
            self.conn.execute("DELETE FROM entities WHERE kind=? AND id=?", (kind, id_))

    def all(self, kind: str) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT data FROM entities WHERE kind=? ORDER BY rowid", (kind,)
            ).fetchall()
            return [json.loads(r[0]) for r in rows]

    # objects --------------------------------------------------------------
    def put_object(self, kind: str, body) -> str:
        text = body if isinstance(body, str) else canonical(body)
        h = digest(text.encode("utf-8"))
        with self.lock:
            self.conn.execute("INSERT OR IGNORE INTO objects(hash,kind,body) VALUES (?,?,?)", (h, kind, text))
        return h

    def get_object(self, h: str):
        with self.lock:
            r = self.conn.execute("SELECT kind, body FROM objects WHERE hash=?", (h,)).fetchone()
        if not r:
            return None
        kind, body = r
        if kind in ("protocol", "json"):
            return json.loads(body)
        return body
