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
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
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
  test_ids TEXT NOT NULL,
  prev_event_hash TEXT,
  event_hash TEXT NOT NULL
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
CREATE TABLE IF NOT EXISTS task_leases (
  task_id TEXT PRIMARY KEY,
  lease_id TEXT UNIQUE NOT NULL,
  holder_id TEXT NOT NULL,
  expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS counters (
  name TEXT PRIMARY KEY, value INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS events_aggregate ON events(aggregate_type, aggregate_id);
"""

# Payload keys that must never appear: D-22, events carry references only.
FORBIDDEN_PAYLOAD_KEYS = {"name", "email", "phone", "address", "candidate_name", "founder_name"}


def now() -> str:
    return datetime.now(IST).isoformat(timespec="milliseconds")


# What a key looks like. A key is never written to the database, whatever carried it there (a provider's error
# message quoting it, say): it is replaced before the write. The gateway refuses files that hold one.
SECRET = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-ant-[\w-]{20,}|\bsk-[A-Za-z0-9_-]{32,}"
                    r"|\bhf_[A-Za-z0-9]{30,}|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{36,}\b")
KEY_REMOVED = "[key removed]"


def scrub(text: str) -> str:
    return SECRET.sub(KEY_REMOVED, text)


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(obj) -> str:
    """Full SHA-256 digest. Short hashes are not sufficient for tamper evidence."""
    raw = obj if isinstance(obj, (bytes, bytearray)) else canonical(obj).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class ConcurrencyError(RuntimeError):
    """An optimistic write lost the race: the record changed since the writer read it. Nothing was written."""


class Store:
    def __init__(self, path: str):
        self.path = path
        self.lock = threading.RLock()
        self._depth = 0  # nesting of atomic(); only the thread holding the lock changes it
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self._migrate_events()

    # transactions ---------------------------------------------------------
    @contextmanager
    def atomic(self):
        """One read-modify-write as a unit: other threads wait on the lock, other processes on SQLite's write lock
        (BEGIN IMMEDIATE). Nested blocks join the outer one; an exception rolls the whole unit back."""
        with self.lock:
            outer = self._depth == 0
            if outer:
                self.conn.execute("BEGIN IMMEDIATE")
            self._depth += 1
            try:
                yield self
            except BaseException:
                self._depth -= 1
                if outer:
                    self.conn.execute("ROLLBACK")
                raise
            self._depth -= 1
            if outer:
                self.conn.execute("COMMIT")

    def next_seq(self, name: str, floor: int = 0) -> int:
        """The next number of a named sequence, never handed out twice, even to concurrent workers. floor seeds a
        sequence the first time it is used (the count of records an older database already holds)."""
        with self.atomic():
            r = self.conn.execute("SELECT value FROM counters WHERE name=?", (name,)).fetchone()
            value = max(int(r[0]) if r else 0, int(floor)) + 1
            self.conn.execute("INSERT INTO counters(name, value) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET "
                              "value=excluded.value", (name, value))
            return value

    def next_id(self, kind: str) -> int:
        """The next number for a record of this kind: seeded from the records already there."""
        with self.atomic():
            have = self.conn.execute("SELECT COUNT(*) FROM entities WHERE kind=?", (kind,)).fetchone()[0]
            return self.next_seq("entity:" + kind, floor=have)

    def compare_and_put(self, kind: str, id_: str, data: dict, expected_version: int, field: str = "_v") -> dict:
        """Optimistic concurrency: write only if the stored record is still at expected_version (0: absent). The
        written record carries expected_version + 1. Otherwise ConcurrencyError, and nothing is written."""
        with self.atomic():
            cur = self.get(kind, id_)
            have = int((cur or {}).get(field) or 0)
            if have != int(expected_version):
                raise ConcurrencyError(f"{kind} {id_} is at version {have}, not {expected_version}")
            data = dict(data)
            data[field] = int(expected_version) + 1
            return self.put(kind, id_, data)

    def _migrate_events(self) -> None:
        """Hash-chain legacy event rows once when opening an older POC database."""
        with self.lock:
            cols = {r[1] for r in self.conn.execute("PRAGMA table_info(events)").fetchall()}
            missing = {"prev_event_hash", "event_hash"} - cols
            if not missing:
                return
            self.conn.execute("DROP TRIGGER IF EXISTS events_no_update")
            self.conn.execute("DROP TRIGGER IF EXISTS events_no_delete")
            if "prev_event_hash" not in cols:
                self.conn.execute("ALTER TABLE events ADD COLUMN prev_event_hash TEXT")
            if "event_hash" not in cols:
                self.conn.execute("ALTER TABLE events ADD COLUMN event_hash TEXT")
            rows = self.conn.execute("SELECT * FROM events ORDER BY seq").fetchall()
            names = [d[0] for d in self.conn.execute("SELECT * FROM events LIMIT 0").description]
            prev = None
            for row in rows:
                d = dict(zip(names, row))
                body = {k: v for k, v in d.items() if k not in ("seq", "prev_event_hash", "event_hash")}
                body["prev_event_hash"] = prev
                eh = hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()
                self.conn.execute("UPDATE events SET prev_event_hash=?, event_hash=? WHERE seq=?",
                                   (prev, eh, d["seq"]))
                prev = eh
            self.conn.execute("CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'events are append only'); END;")
            self.conn.execute("CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'events are append only'); END;")

    def close(self) -> None:
        """Close the SQLite connection owned by this store."""
        with self.lock:
            if self.conn is not None:
                self.conn.close()
                self.conn = None

    def claim_task(self, task_id: str, holder_id: str, lease_seconds: float = 120.0) -> str | None:
        """Atomically claim a task. Expired leases are reclaimed; a live lease has exactly one holder."""
        now_ts = time.time()
        with self.atomic():
            self.conn.execute("DELETE FROM task_leases WHERE expires_at <= ?", (now_ts,))
            lease_id = "lease_" + uuid.uuid4().hex
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO task_leases(task_id, lease_id, holder_id, expires_at) VALUES (?,?,?,?)",
                (task_id, lease_id, holder_id, now_ts + max(1.0, lease_seconds)),
            )
            return lease_id if cur.rowcount == 1 else None

    def renew_task_lease(self, task_id: str, lease_id: str, lease_seconds: float = 120.0) -> bool:
        with self.lock:
            cur = self.conn.execute(
                "UPDATE task_leases SET expires_at=? WHERE task_id=? AND lease_id=? AND expires_at>?",
                (time.time() + max(1.0, lease_seconds), task_id, lease_id, time.time()),
            )
            return cur.rowcount == 1

    def release_task(self, task_id: str, lease_id: str) -> bool:
        with self.lock:
            cur = self.conn.execute("DELETE FROM task_leases WHERE task_id=? AND lease_id=?", (task_id, lease_id))
            return cur.rowcount == 1

    def task_lease(self, task_id: str) -> dict | None:
        with self.lock:
            r = self.conn.execute("SELECT task_id, lease_id, holder_id, expires_at FROM task_leases WHERE task_id=?",
                                  (task_id,)).fetchone()
            return dict(zip(("task_id", "lease_id", "holder_id", "expires_at"), r)) if r else None

    # events ---------------------------------------------------------------
    def append(self, *, company_id: str, event_type: str, aggregate_type: str, aggregate_id: str,
               actor_type: str, actor_id: str, payload: dict, correlation_id: str,
               authority_snapshot: str = "platform", policy_decision: str = "ALLOW",
               causation_id: str | None = None, context_refs: list | None = None,
               protocol_hash: str | None = None, test_ids: list | None = None,
               aggregate_version: int | None = 1, source_service: str = "cynqra_poc",
               command_id: str | None = None, idempotency_key: str | None = None) -> dict:
        bad = FORBIDDEN_PAYLOAD_KEYS & set(payload)
        if bad:
            raise ValueError(f"event payload may not carry personal data keys: {sorted(bad)}")
        with self.lock:
            if idempotency_key:
                existing = self.conn.execute("SELECT * FROM events WHERE idempotency_key=?", (idempotency_key,)).fetchone()
                if existing:
                    names = [d[0] for d in self.conn.execute("SELECT * FROM events LIMIT 0").description]
                    return dict(zip(names, existing))
            last = self.conn.execute("SELECT event_id, event_hash, seq FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            if aggregate_version is None:  # the aggregate's own sequence: its events in causal order
                top = self.conn.execute("SELECT MAX(aggregate_version) FROM events WHERE aggregate_type=? AND "
                                        "aggregate_id=?", (aggregate_type, aggregate_id)).fetchone()[0]
                aggregate_version = int(top or 0) + 1
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
                "command_id": command_id or ("cmd_" + uuid.uuid4().hex[:12]),
                "idempotency_key": idempotency_key or ("idem_" + uuid.uuid4().hex[:16]),
                "context_refs": json.dumps(context_refs or []),
                "payload": scrub(canonical(payload)),
                "payload_schema_version": 1,
                "source_service": source_service,
                "created_at": now(),
                "protocol_hash": protocol_hash,
                "test_ids": json.dumps(test_ids or []),
                "prev_event_hash": last[1] if last and last[1] else None,
            }
            row["event_hash"] = hashlib.sha256(canonical(row).encode("utf-8")).hexdigest()
            cols = ",".join(row)
            marks = ",".join("?" for _ in row)
            cur = self.conn.execute(f"INSERT INTO events ({cols}) VALUES ({marks})", list(row.values()))
            row["seq"] = cur.lastrowid
            return row

    def verify_event_chain(self) -> bool:
        """Recompute the event chain and detect mutation or deletion."""
        with self.lock:
            rows = self.conn.execute("SELECT * FROM events ORDER BY seq").fetchall()
            names = [d[0] for d in self.conn.execute("SELECT * FROM events LIMIT 0").description]
            prev = None
            for row in rows:
                d = dict(zip(names, row))
                if not d.get("event_hash") or d.get("prev_event_hash") != prev:
                    return False
                body = {k: v for k, v in d.items() if k not in ("seq", "event_hash")}
                if hashlib.sha256(canonical(body).encode("utf-8")).hexdigest() != d["event_hash"]:
                    return False
                prev = d["event_hash"]
            return True

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
                (kind, id_, scrub(json.dumps(data)), now()),
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
