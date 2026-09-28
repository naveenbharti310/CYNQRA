"""Expected footfall and revenue for one day, hour by hour and meal by meal, updated as the day goes.

The day's covers come from the Data Scientist's forecast (forecast.py, backtested by the platform). They are spread
over the opening hours by the restaurant's hourly pattern. During the day, the covers already served correct the
rest of the day: if lunch ran 20% busy, the afternoon is expected 20% busier too (within half and one and a half
times the forecast, so one odd hour cannot swing the whole day).
"""
from __future__ import annotations

from datetime import date

from forecast import forecast
from store import HOURLY, SLOTS

QUIET = 0.6  # an hour is quiet when it expects under 60% of its meal's busiest hour


def day_total(history: list[dict], day: date) -> float:
    """Covers expected on a day after the history ends."""
    last = date.fromisoformat(history[-1]["date"])
    ahead = (day - last).days
    if ahead < 1:
        raise ValueError("the day must come after the history")
    return forecast(history, ahead)[-1]


def by_hour(total: float, restaurant: dict) -> dict[int, float]:
    hours = {h: s for h, s in HOURLY.items() if restaurant["open"] <= h < restaurant["close"]}
    norm = sum(hours.values()) or 1.0
    return {h: round(total * s / norm, 1) for h, s in hours.items()}


def nowcast(expected: dict[int, float], seen: dict[int, float], now_hour: int) -> tuple[dict[int, float], float]:
    """The covers served so far replace the forecast for past hours and correct the hours still to come."""
    past = [h for h in expected if h < now_hour]
    exp_past = sum(expected[h] for h in past)
    factor = 1.0
    if past and exp_past > 0:
        factor = min(1.5, max(0.5, sum(float(seen.get(h, 0)) for h in past) / exp_past))
    return {h: float(seen.get(h, 0)) if h < now_hour else round(expected[h] * factor, 1) for h in expected}, factor


def window(expected: dict[int, float], start: int, end: int) -> float:
    return round(sum(c for h, c in expected.items() if start <= h < end), 1)


def quiet_window(expected: dict[int, float], slot: str) -> tuple[int, int] | None:
    """The longest run of quiet hours in a meal, as (start, end)."""
    lo, hi = SLOTS[slot]
    hours = [h for h in sorted(expected) if lo <= h < hi]
    if not hours:
        return None
    peak = max(expected[h] for h in hours)
    best, run = None, []
    for h in hours + [None]:
        if h is not None and expected[h] < QUIET * peak:
            run.append(h)
            continue
        if run and (best is None or len(run) > best[1] - best[0]):
            best = (run[0], run[-1] + 1)
        run = []
    return best


def day_view(expected: dict[int, float], restaurant: dict) -> dict:
    bill = restaurant["avg_bill"]
    slots = []
    for name, (lo, hi) in SLOTS.items():
        covers = window(expected, lo, hi)
        slots.append({"slot": name, "from": lo, "to": hi, "covers": covers, "revenue": round(covers * bill),
                      "quiet": quiet_window(expected, name)})
    total = round(sum(expected.values()), 1)
    return {"hours": [{"hour": h, "covers": c, "revenue": round(c * bill)} for h, c in sorted(expected.items())],
            "slots": slots, "covers": total, "revenue": round(total * bill)}
