"""Provider Weather (R8 of the architecture review): each intelligence's recent health, from the calls on record.

Paid run 37589136743 lost about two hours learning, call by call, that Google's preview models were overloaded.
The weather is what the registry already saw in the last WINDOW_S seconds, across every run on this installation:
how many calls failed on the provider's side, how many were overloads (503, "high demand") or limits (429), and how
long answers took. It is clear, unsettled or stormy. The Router reads it from each candidate's facts (so a decision
replays with the weather it was made in): a stormy intelligence is ranked after every feasible one that is not, an
unsettled one's expected time includes the waiting its failures cost, and a stormy incumbent gives way.

report() is the shareable form: per provider and model, counts, rates and latency percentiles, never a prompt, a
reply, an objective or a credential. Shared between installations it becomes the network-wide map the review
describes; here it is this installation's own.
"""
from __future__ import annotations

import re
import time
from datetime import datetime

WINDOW_S = 1800  # the last half hour
MIN_CALLS = 3  # fewer calls say nothing either way
UNSETTLED = 0.2  # share of recent calls that failed on the provider's side
STORMY = 0.5
FAILED_CALL_S = 30.0  # what a failed call costs when its own time was not measured
_OVERLOAD = re.compile(r"\b(503|529)\b|overload|high demand|unavailable", re.I)
_LIMIT = re.compile(r"\b429\b|rate limit|quota|resource.?exhausted", re.I)


def _when(at) -> float | None:
    try:
        return datetime.fromisoformat(str(at)).timestamp()
    except (TypeError, ValueError):
        return None


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return round(s[min(len(s) - 1, int(q * len(s)))], 1)


def of(calls: list[dict], now: float | None = None) -> dict:
    """The weather from one intelligence's call records."""
    now = time.time() if now is None else now
    recent = [c for c in calls if (_when(c.get("at")) or 0) >= now - WINDOW_S]
    failed = [c for c in recent if c.get("error")]
    ok_secs = [float(c.get("seconds") or 0) for c in recent if not c.get("error") and float(c.get("seconds") or 0) > 0]
    fail_secs = [float(c.get("seconds") or 0) for c in failed if float(c.get("seconds") or 0) > 0]
    rate = round(len(failed) / len(recent), 3) if recent else 0.0
    state = "clear" if len(recent) < MIN_CALLS or rate < UNSETTLED else "unsettled" if rate < STORMY else "stormy"
    return {"state": state, "calls": len(recent), "errors": len(failed),
            "overloads": sum(1 for c in failed if _OVERLOAD.search(str(c.get("error")))),
            "limited": sum(1 for c in failed if _LIMIT.search(str(c.get("error")))),
            "error_rate": rate, "p50_s": _pct(ok_secs, 0.5), "p95_s": _pct(ok_secs, 0.95),
            "failed_call_s": round(sum(fail_secs) / len(fail_secs), 1) if fail_secs else FAILED_CALL_S,
            "window_min": WINDOW_S // 60}


def expected_wait_s(weather: dict | None) -> float:
    """Seconds of waiting one successful call is expected to cost on top of its own time: the failed calls before
    it (f / (1 - f) of them, at what a failed call takes). Nothing while the weather is clear."""
    w = weather or {}
    if w.get("state") not in ("unsettled", "stormy"):
        return 0.0
    f = min(0.9, float(w.get("error_rate") or 0))
    return f / (1 - f) * float(w.get("failed_call_s") or FAILED_CALL_S)


def stormy(c: dict) -> bool:
    return (c.get("weather") or {}).get("state") == "stormy"


def report(registry, now: float | None = None) -> list[dict]:
    """This installation's weather, shareable: per provider and model, no content and no credential."""
    out = []
    for m in registry.models():
        w = of(registry.calls(m["id"]), now)
        if w["calls"]:
            out.append({"provider": m.get("access_provider") or m.get("provider") or "", "model": m.get("ref"), **w})
    return sorted(out, key=lambda r: (r["provider"], str(r["model"])))
