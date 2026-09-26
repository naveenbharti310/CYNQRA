#!/usr/bin/env python3
"""LOW risk sandbox: internal candidate tracker.

A clock can only flag a card. A card is stuck only when a named reason
exists. If the stage has already moved, the card cannot stay flagged or stuck.
That last rule is a freshness invariant, not a product decision.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

STAGES = ("applied", "screen", "interview", "offer", "hired", "rejected")
EARLY_STAGES = ("applied", "screen")
STUCK_REASONS = (
    "waiting_on_recruiter",
    "waiting_on_candidate",
    "waiting_on_founder",
    "missing_document",
    "no_owner",
)
DEFAULT_FLAG_AFTER_DAYS = 7


class CandidateError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc)


def _parse(ts):
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def new_store():
    return {"candidates": [], "next_id": 1}


def create_candidate(store, name, role, source="", now=None):
    name = (name or "").strip()
    role = (role or "").strip()
    if not name or not role:
        raise CandidateError("name and role are required")
    stamp = (now or _now()).isoformat()
    item = {
        "id": "c_%03d" % store["next_id"],
        "name": name,
        "role": role,
        "source": (source or "").strip(),
        "stage": "applied",
        "stuck_reason": "",
        "created_at": stamp,
        "last_moved_at": stamp,
    }
    store["next_id"] += 1
    store["candidates"].append(item)
    return dict(item)


def list_candidates(store):
    return [dict(c) for c in store["candidates"]]


def _get(store, candidate_id):
    for item in store["candidates"]:
        if item["id"] == candidate_id:
            return item
    raise CandidateError("candidate not found")


def set_stage(store, candidate_id, stage, now=None):
    if stage not in STAGES:
        raise CandidateError("unknown stage")
    item = _get(store, candidate_id)
    item["stage"] = stage
    item["last_moved_at"] = (now or _now()).isoformat()
    if stage not in EARLY_STAGES:
        item["stuck_reason"] = ""
    return dict(item)


def set_stuck_reason(store, candidate_id, reason):
    if reason not in STUCK_REASONS:
        raise CandidateError("unknown stuck reason")
    item = _get(store, candidate_id)
    if item["stage"] not in EARLY_STAGES:
        raise CandidateError("cannot mark stuck after the early stages")
    item["stuck_reason"] = reason
    return dict(item)


def is_flagged(item, now=None, flag_after_days=DEFAULT_FLAG_AFTER_DAYS):
    if item["stage"] not in EARLY_STAGES:
        return False
    current = now or _now()
    moved = _parse(item["last_moved_at"])
    return current - moved >= timedelta(days=flag_after_days)


def is_stuck(item, now=None, flag_after_days=DEFAULT_FLAG_AFTER_DAYS):
    return bool(item.get("stuck_reason")) and is_flagged(
        item, now=now, flag_after_days=flag_after_days
    )


def list_flagged(store, now=None, flag_after_days=DEFAULT_FLAG_AFTER_DAYS):
    return [
        dict(item)
        for item in store["candidates"]
        if is_flagged(item, now=now, flag_after_days=flag_after_days)
    ]


def list_stuck(store, now=None, flag_after_days=DEFAULT_FLAG_AFTER_DAYS):
    return [
        dict(item)
        for item in store["candidates"]
        if is_stuck(item, now=now, flag_after_days=flag_after_days)
    ]
