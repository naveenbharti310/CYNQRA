"""Bluedip's footfall forecast: expected covers a day, the input to every hourly and offer estimate.

A restaurant's covers follow the week (Fridays and Saturdays busy, the start of the week quiet), so each day ahead
is the average of the same weekday over the last four weeks: the weekly pattern is kept, and one-off nights are
smoothed. The platform backtests it on days it has not seen, against last week's numbers. See docs/method.md.
"""

WEEKS = 4


def forecast(history, horizon):
    """history: [{"date": "YYYY-MM-DD", "covers": n}, ...] for consecutive days, oldest first.
    Returns horizon non-negative numbers, one per following day."""
    if horizon < 0:
        raise ValueError("horizon cannot be negative")
    if not history:
        raise ValueError("no history to forecast from")
    ys = [float(h["covers"]) for h in history]
    n = len(ys)
    out = []
    for h in range(horizon):
        # day n + h falls on the same weekday as days n + h % 7 - 7k
        same = [ys[i] for i in (n + h % 7 - 7 * k for k in range(1, WEEKS + 1)) if 0 <= i < n]
        out.append(round(max(0.0, sum(same) / len(same)), 1) if same else round(ys[-1], 1))
    return out
