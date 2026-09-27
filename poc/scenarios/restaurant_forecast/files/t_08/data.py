"""Daily covers history, kept in one JSON file (DATA_FILE). Standard library only.

A day is {"date": "YYYY-MM-DD", "covers": n}. One number per day: a later entry for the same date replaces the
earlier one. A first start with no file seeds a sample history, marked as such, so the page has something to show
until the restaurant's own numbers are entered.
"""
import json
import os
import random
from datetime import date, timedelta

MAX_COVERS = 5000


class CoversError(ValueError):
    pass


def parse_day(text):
    try:
        return date.fromisoformat(str(text))
    except ValueError as exc:
        raise CoversError(f"date must be YYYY-MM-DD, got {text!r}") from exc


def sample_history(end, days=112, seed=11):
    """A plausible, fixed sample: a weekly pattern with busy Fridays and Saturdays."""
    rng = random.Random(seed)
    week = [0.80, 0.85, 0.90, 1.00, 1.35, 1.55, 1.20]
    start = end - timedelta(days=days - 1)
    return [{"date": (start + timedelta(days=i)).isoformat(),
             "covers": max(0, round(120 * week[(start + timedelta(days=i)).weekday()] + rng.gauss(0, 6)))}
            for i in range(days)]


class CoversStore:
    def __init__(self, path, today=None):
        self.path = path
        self.rows = {}
        self.sample = False
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.sample = bool(data.get("sample"))
            for r in data.get("days", []):
                self.rows[r["date"]] = int(r["covers"])
        else:
            yesterday = (today or date.today()) - timedelta(days=1)
            for r in sample_history(yesterday):
                self.rows[r["date"]] = r["covers"]
            self.sample = True
            self._save()

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"sample": self.sample, "days": self.history()}, fh)
        os.replace(tmp, self.path)

    def add(self, day, covers):
        d = parse_day(day)
        if isinstance(covers, bool) or not isinstance(covers, (int, float)) or covers != int(covers):
            raise CoversError("covers must be a whole number")
        if not 0 <= covers <= MAX_COVERS:
            raise CoversError(f"covers must be between 0 and {MAX_COVERS}")
        self.rows[d.isoformat()] = int(covers)
        self._save()
        return {"date": d.isoformat(), "covers": int(covers)}

    def history(self):
        return [{"date": k, "covers": self.rows[k]} for k in sorted(self.rows)]

    def recent_run(self):
        """The latest stretch of consecutive days: what the forecast is computed from."""
        days = self.history()
        run = []
        for r in reversed(days):
            if run and parse_day(run[-1]["date"]) - parse_day(r["date"]) != timedelta(days=1):
                break
            run.append(r)
        return list(reversed(run))
