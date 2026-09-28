"""Bluedip's footfall forecast: expected covers a day, the input to every hourly and offer estimate.

First attempt: the average of the last four weeks, for every day ahead.
"""


def forecast(history, horizon):
    """history: [{"date": "YYYY-MM-DD", "covers": n}, ...] for consecutive days, oldest first.
    Returns horizon non-negative numbers, one per following day."""
    if horizon < 0:
        raise ValueError("horizon cannot be negative")
    if not history:
        raise ValueError("no history to forecast from")
    recent = [float(h["covers"]) for h in history[-28:]]
    level = max(0.0, sum(recent) / len(recent))
    return [round(level, 1) for _ in range(horizon)]
