"""What Bluedip keeps for one restaurant, in one JSON file (DATA_FILE). Standard library only.

- The restaurant: opening hours, seats, average bill and food cost. Until the owner enters their own food cost,
  35% of the bill is used and marked as an assumption (the Revenue Management Specialist's rule).
- Its history: covers a day, oldest first. A first start with no file seeds a marked sample, so the screen has
  something to show until the restaurant's own numbers arrive.
- Its offers, their redemptions, and what finished offers taught Bluedip about how its customers respond.
"""
from __future__ import annotations

import json
import os
import random
import threading
from datetime import date, timedelta

# Share of a day's covers in each opening hour: a lunch peak at noon, a quiet afternoon, a dinner peak at 8 pm.
HOURLY = {8: .02, 9: .05, 10: .06, 11: .06, 12: .14, 13: .05, 14: .03, 15: .03, 16: .04, 17: .05, 18: .06,
          19: .12, 20: .14, 21: .10, 22: .05}
SLOTS = {"breakfast": (8, 11), "lunch": (11, 16), "dinner": (16, 23)}
DEFAULT_RESTAURANT = {"name": "Sample restaurant", "open": 8, "close": 23, "seats": 60, "avg_bill": 600,
                      "food_cost": 0.35, "food_cost_assumed": True}


class StoreError(ValueError):
    """A request the store refuses: an unknown offer, one that is full or closed, or a bad figure."""


def sample_history(end: date, days: int = 112, seed: int = 11) -> list[dict]:
    """A fixed, plausible sample: busy Fridays and Saturdays, a quiet start of the week."""
    rng = random.Random(seed)
    week = [0.80, 0.85, 0.90, 1.00, 1.35, 1.55, 1.20]
    start = end - timedelta(days=days - 1)
    return [{"date": (start + timedelta(days=i)).isoformat(),
             "covers": max(0, round(120 * week[(start + timedelta(days=i)).weekday()] + rng.gauss(0, 6)))}
            for i in range(days)]


class Store:
    def __init__(self, path: str | None = None, today: date | None = None):
        self._path, self._lock = path, threading.Lock()
        data = {}
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        yesterday = (today or date.today()) - timedelta(days=1)
        self.restaurant = {**DEFAULT_RESTAURANT, **data.get("restaurant", {})}
        self.history = data.get("history") or sample_history(yesterday)
        self.sample = data.get("sample", not data.get("history"))
        self.offers: dict[str, dict] = {o["id"]: o for o in data.get("offers", [])}
        self.learned = data.get("learned", [])  # one observed response per finished offer
        self._n = int(data.get("next", len(self.offers)))
        self._save()

    def _save(self) -> None:
        if not self._path:
            return
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"restaurant": self.restaurant, "history": self.history, "sample": self.sample,
                       "offers": list(self.offers.values()), "learned": self.learned, "next": self._n}, fh, indent=1)
        os.replace(tmp, self._path)

    def set_restaurant(self, avg_bill=None, food_cost=None) -> dict:
        with self._lock:
            try:
                if avg_bill is not None:
                    if not 50 <= float(avg_bill) <= 100000:
                        raise StoreError("the average bill must be between ₹50 and ₹1,00,000")
                    self.restaurant["avg_bill"] = round(float(avg_bill))
                if food_cost is not None:
                    if not 0.05 <= float(food_cost) <= 0.9:
                        raise StoreError("food cost must be a share of the bill between 0.05 and 0.9")
                    self.restaurant.update(food_cost=float(food_cost), food_cost_assumed=False)
            except (TypeError, ValueError) as exc:
                raise StoreError(str(exc) if isinstance(exc, StoreError) else "figures must be numbers") from exc
            self._save()
            return dict(self.restaurant)

    def add_offer(self, offer: dict) -> dict:
        with self._lock:
            self._n += 1
            rec = {**offer, "id": f"of_{self._n:03d}", "redeemed": 0, "status": "live"}
            self.offers[rec["id"]] = rec
            self._save()
            return dict(rec)

    def redeem(self, oid: str) -> dict:
        """One customer uses the offer. The cap is a promise to the owner: it is never exceeded."""
        with self._lock:
            o = self.offers.get(oid)
            if o is None:
                raise StoreError("unknown offer")
            if o["status"] != "live":
                raise StoreError("this offer has closed")
            if o["redeemed"] >= o["cap"]:
                raise StoreError(f"this offer is full: {o['cap']} customers have used it")
            o["redeemed"] += 1
            self._save()
            return dict(o)

    def close(self, oid: str, covers: int, response: float) -> dict:
        """The offer's window is over: record the covers actually served, and what they say about the response."""
        with self._lock:
            o = self.offers.get(oid)
            if o is None:
                raise StoreError("unknown offer")
            if o["status"] != "live":
                raise StoreError("this offer has closed")
            o.update(status="closed", actual_covers=int(covers), observed_response=round(response, 3))
            self.learned.append(round(response, 3))
            self._save()
            return dict(o)

    def list_offers(self) -> list[dict]:
        with self._lock:
            return [dict(o) for o in self.offers.values()]
