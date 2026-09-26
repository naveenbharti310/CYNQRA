"""Candidate store for the internal candidate tracker.

Stages are a closed list. A card is flagged when it has sat in applied or screen
for seven days. It is stuck only when it is flagged and has a named reason.
Moving the stage clears both marks. Storage errors are raised, never hidden.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone

STAGES = ("applied", "screen", "interview", "offer", "hired", "rejected")
EARLY_STAGES = ("applied", "screen")
REASONS = (
    "waiting_on_recruiter",
    "waiting_on_candidate",
    "waiting_on_founder",
    "missing_document",
    "no_owner",
)
FLAG_AFTER_DAYS = 7


class CandidateError(ValueError):
    """A request the store refuses: bad name, unknown id, stage or reason."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class CandidateStore:
    def __init__(self, path: str | None = None):
        self._path = path
        self._lock = threading.Lock()
        self._items: dict[str, dict] = {}
        self._n = 0
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            self._items = {c["id"]: c for c in data.get("candidates", [])}
            self._n = int(data.get("next", len(self._items)))

    def _save(self) -> None:
        if not self._path:
            return
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"next": self._n, "candidates": list(self._items.values())}, fh, indent=1)
        os.replace(tmp, self._path)

    def create(self, name: str, applied_at=None) -> dict:
        name = (name or "").strip()
        if not name:
            raise CandidateError("name is required")
        stamp = _parse(applied_at).isoformat() if applied_at else _now().isoformat()
        with self._lock:
            self._n += 1
            cid = f"c_{self._n:03d}"
            rec = {"id": cid, "name": name, "stage": "applied", "reason": "", "last_moved_at": stamp}
            self._items[cid] = rec
            self._save()
            return dict(rec)

    def list(self) -> list[dict]:
        with self._lock:
            values = [dict(v) for v in self._items.values()]
            return values[-1:]

    def get(self, cid: str) -> dict:
        with self._lock:
            if cid not in self._items:
                raise CandidateError("unknown candidate")
            return dict(self._items[cid])

    def set_stage(self, cid: str, stage: str, now=None) -> dict:
        if stage not in STAGES:
            raise CandidateError("unknown stage")
        with self._lock:
            if cid not in self._items:
                raise CandidateError("unknown candidate")
            rec = self._items[cid]
            rec["stage"] = stage
            rec["last_moved_at"] = _parse(now).isoformat() if now else _now().isoformat()
            if stage not in EARLY_STAGES:
                rec["reason"] = ""
            self._save()
            return dict(rec)

    def set_reason(self, cid: str, reason: str) -> dict:
        if reason and reason not in REASONS:
            raise CandidateError("unknown reason")
        with self._lock:
            if cid not in self._items:
                raise CandidateError("unknown candidate")
            rec = self._items[cid]
            if reason and rec["stage"] not in EARLY_STAGES:
                raise CandidateError("only applied or screen cards can be stuck")
            rec["reason"] = reason
            self._save()
            return dict(rec)

    def is_flagged(self, rec: dict, now=None) -> bool:
        if rec["stage"] not in EARLY_STAGES:
            return False
        current = _parse(now) if now else _now()
        return current - _parse(rec["last_moved_at"]) >= timedelta(days=FLAG_AFTER_DAYS)

    def is_stuck(self, rec: dict, now=None) -> bool:
        return bool(rec.get("reason")) and self.is_flagged(rec, now)

    def flagged(self, now=None) -> list[dict]:
        return [r for r in self.list() if self.is_flagged(r, now)]

    def stuck(self, now=None) -> list[dict]:
        return [r for r in self.list() if self.is_stuck(r, now)]
