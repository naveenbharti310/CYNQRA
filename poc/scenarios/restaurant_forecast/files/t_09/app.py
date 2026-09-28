"""The kitchen's covers forecast: one page and a small JSON API. Standard library only.

GET  /health          200 when the app is up
GET  /                the forecast page
GET  /api/forecast    the next 14 days: expected covers and the prep plan
GET  /api/history     the covers history
POST /api/covers      {"date": "YYYY-MM-DD", "covers": n}: record a day's covers
"""
import json
import math
import os
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from data import CoversError, CoversStore, parse_day
from forecast import forecast

HORIZON = 14
PREP_MARGIN = 0.10  # the founder's rule: prep for the forecast plus 10 percent, rounded up
PAGE = Path(__file__).resolve().parent / "index.html"


def prep(covers):
    return math.ceil(covers * (1 + PREP_MARGIN) - 1e-9)


def plan(store):
    run = store.recent_run()
    if not run:
        return {"days": [], "sample": store.sample, "history_days": 0}
    last = parse_day(run[-1]["date"])
    values = forecast(run, HORIZON)
    days = []
    for i, v in enumerate(values):
        d = last + timedelta(days=i + 1)
        days.append({"date": d.isoformat(), "weekday": d.strftime("%a"), "weekend": d.weekday() >= 5,
                     "covers": round(v), "prep": prep(v)})
    return {"days": days, "sample": store.sample, "history_days": len(run), "margin": PREP_MARGIN}


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def send(self, code, body, kind="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/health":
                return self.send(200, {"ok": True})
            if path == "/":
                return self.send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            if path == "/api/forecast":
                return self.send(200, plan(store))
            if path == "/api/history":
                return self.send(200, {"days": store.history(), "sample": store.sample})
            return self.send(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/api/covers":
                return self.send(404, {"error": "not found"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                if not isinstance(body, dict):
                    raise CoversError("send a JSON object")
                return self.send(201, store.add(body.get("date"), body.get("covers")))
            except (CoversError, ValueError) as exc:
                return self.send(400, {"error": str(exc)})
    return Handler


def make_server(port, data_file):
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(CoversStore(data_file)))


if __name__ == "__main__":
    server = make_server(int(os.environ.get("PORT", "8080")), os.environ.get("DATA_FILE", "covers.json"))
    server.serve_forever()
