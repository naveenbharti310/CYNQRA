"""Bluedip for one restaurant owner. Python standard library only.

Run: PORT=8000 DATA_FILE=bluedip.json python app.py
Routes:
  GET  /health, GET /                       the service and the owner's screen
  GET  /api/restaurant, POST /api/restaurant the owner's figures (average bill, food cost)
  GET  /api/day?date=YYYY-MM-DD             expected covers and revenue by hour and by meal, with recommendations
  POST /api/nowcast                         {"date", "now_hour", "seen": {hour: covers}}: the rest of the day, corrected
  POST /api/offers/estimate                 {"date", "start", "end", "discount", "cap"}: what an offer would do
  POST /api/offers, GET /api/offers         create an offer (within the rule on record) and list them
  POST /api/offers/<id>/redeem              one customer uses it; never beyond its cap
  POST /api/offers/<id>/close               {"covers": served in the window}: Bluedip learns from it
There is no diner-facing route and no payment in release 1.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import demand
import offers
from store import Store, StoreError

HERE = Path(__file__).resolve().parent
ROUTE = re.compile(r"^/api/offers/(of_\d{3,})/(redeem|close)$")


class RequestError(ValueError):
    pass


def make_server(port: int, data_file: str | None = None) -> ThreadingHTTPServer:
    store = Store(data_file)

    def response() -> float:
        return offers.learn(store.learned)

    def expected_for(day_text: str | None) -> tuple[date, dict]:
        try:
            day = date.fromisoformat(day_text) if day_text else date.today()
            total = demand.day_total(store.history, day)
        except ValueError as exc:
            raise RequestError(f"date must be YYYY-MM-DD after the history: {exc}") from exc
        return day, demand.by_hour(total, store.restaurant)

    def view(day: date, expected: dict) -> dict:
        v = demand.day_view(expected, store.restaurant)
        for s in v["slots"]:
            s["quiet_covers"] = demand.window(expected, *s["quiet"]) if s["quiet"] else 0.0
        return {"date": day.isoformat(), "sample": store.sample, "restaurant": store.restaurant, **v,
                "recommendations": offers.recommend(v["slots"], store.restaurant, response()),
                "response": round(response(), 3), "offers_learned_from": len(store.learned)}

    def offer_input(b: dict) -> tuple[date, dict, int, int, float, int]:
        day, expected = expected_for(b.get("date"))
        try:
            start, end, disc, cap = int(b["start"]), int(b["end"]), float(b["discount"]), int(b["cap"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RequestError("start, end, discount and cap are required numbers") from exc
        offers.check(start, end, disc, cap, store.restaurant)
        return day, expected, start, end, disc, cap

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def _send(self, code: int, body, kind: str = "application/json") -> None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict:
            size = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(size).decode("utf-8")) if size else {}
            except (ValueError, UnicodeDecodeError) as exc:
                raise RequestError("body must be JSON") from exc
            if not isinstance(data, dict):
                raise RequestError("body must be a JSON object")
            return data

        def do_GET(self):
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/health":
                    return self._send(200, {"ok": True})
                if url.path in ("/", "/index.html"):
                    return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
                if url.path == "/api/restaurant":
                    return self._send(200, store.restaurant)
                if url.path == "/api/day":
                    return self._send(200, view(*expected_for(q.get("date"))))
                if url.path == "/api/offers":
                    return self._send(200, store.list_offers())
            except RequestError as exc:
                return self._send(400, {"error": str(exc)})
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            try:
                b = self._body()
                if self.path == "/api/restaurant":
                    return self._send(200, store.set_restaurant(b.get("avg_bill"), b.get("food_cost")))
                if self.path == "/api/nowcast":
                    day, expected = expected_for(b.get("date"))
                    seen = {int(h): float(c) for h, c in (b.get("seen") or {}).items()}
                    now, factor = demand.nowcast(expected, seen, int(b.get("now_hour", 0)))
                    return self._send(200, {**view(day, now), "correction": round(factor, 2)})
                if self.path == "/api/offers/estimate":
                    day, expected, start, end, disc, cap = offer_input(b)
                    exp = demand.window(expected, start, end)
                    return self._send(200, {"estimate": offers.estimate(exp, disc, cap, store.restaurant, response()),
                                            "better": offers.best(exp, cap, store.restaurant, response())})
                if self.path == "/api/offers":
                    day, expected, start, end, disc, cap = offer_input(b)
                    exp = demand.window(expected, start, end)
                    rec = store.add_offer({"date": day.isoformat(), "start": start, "end": end, "discount": disc,
                                           "cap": cap, "expected": exp,
                                           "estimate": offers.estimate(exp, disc, cap, store.restaurant, response())})
                    return self._send(201, rec)
                m = ROUTE.match(self.path)
                if not m:
                    return self._send(404, {"error": "not found"})
                oid, what = m.groups()
                if what == "redeem":
                    return self._send(200, store.redeem(oid))
                o = next((x for x in store.list_offers() if x["id"] == oid), None)
                if o is None:
                    raise StoreError("unknown offer")
                covers = int(b.get("covers", -1))
                if covers < 0:
                    raise RequestError("covers served in the window is required")
                rec = store.close(oid, covers, offers.observed_response(o["expected"], covers, o["discount"]))
                return self._send(200, {**rec, "response_now": round(response(), 3)})
            except (RequestError, offers.OfferError) as exc:
                return self._send(400, {"error": str(exc)})
            except StoreError as exc:
                msg = str(exc)
                return self._send(404 if "unknown" in msg else 409 if "full" in msg or "closed" in msg else 400,
                                  {"error": msg})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    server = make_server(int(os.environ.get("PORT", "8000")), os.environ.get("DATA_FILE") or None)
    print(f"Bluedip on http://127.0.0.1:{server.server_address[1]}", flush=True)
    server.serve_forever()
