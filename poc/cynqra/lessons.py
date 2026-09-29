"""What Cynqra learns across projects: after each accepted delivery, what the company needed and how it went.

A founder who has built a company before knows what the next one will need. Cynqra keeps the same memory, on this
computer, next to the projects themselves (lessons.json in the app's data folder, beside every run): the areas the idea
covered, the seats it ended with and the ones the challenge cut, the mistakes the checks caught, how many times the
founder was needed, and what it cost. When a new team is proposed, the projects that covered the same kinds of work
become its track record: "in 3 earlier projects like this one, 3 were delivered and accepted". Nothing in it names a
person, and nothing leaves this computer.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from . import budget
from .db import now

_LOCK = threading.Lock()
SIMILAR = 0.6  # share of requirement areas two projects must have in common to count as alike


def path(run) -> Path:
    return Path(run.memory)


def load(run) -> list[dict]:
    try:
        data = json.loads(path(run).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []


def record(run) -> dict:
    """One accepted delivery, kept for the next project."""
    req = run.requirements() or {}
    prop = run.proposal() or {}
    metrics = run.metrics()
    entry = {"company": run.cid, "cycle": int(run.meta.get("cycle") or 1), "at": now(),
             "areas": sorted({r["area"] for r in req.get("requirements", [])}),
             "seats": sorted(r.get("title") or r["role"] for r in prop.get("roles", [])),
             "cut_by_challenge": [r["title"] for r in (prop.get("challenge") or {}).get("removed", [])],
             "mistakes_caught": metrics.get("defects_caught_before_verified", 0),
             "founder_decisions": metrics.get("founder_interventions", 0),
             "cost_usd": round(float(budget.ledger(run.store).get("spent_total") or 0), 4),
             "accepted": True}
    with _LOCK:
        data = [x for x in load(run) if not (x.get("company") == entry["company"] and x.get("cycle") == entry["cycle"])]
        data.append(entry)
        try:
            path(run).write_text(json.dumps(data[-500:], indent=1), encoding="utf-8")
        except OSError:
            pass  # a read-only folder costs the memory, never the delivery
    return entry


def track_record(run, areas: set[str]) -> dict | None:
    """The earlier projects that covered the same kinds of work, and how they went."""
    alike = [x for x in load(run) if x.get("company") != run.cid and x.get("areas")
             and len(areas & set(x["areas"])) / max(1, len(areas | set(x["areas"]))) >= SIMILAR]
    if not alike:
        return None
    return {"projects": len(alike), "accepted": sum(1 for x in alike if x.get("accepted")),
            "mistakes_caught": sum(int(x.get("mistakes_caught") or 0) for x in alike),
            "seats_seen": sorted({s for x in alike for s in x.get("seats", [])})}
