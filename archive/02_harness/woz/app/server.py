#!/usr/bin/env python3
"""Local only preview. Not a production deploy.
Open http://127.0.0.1:8765 after starting this file.
"""

from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import json
from urllib.parse import urlparse

from candidates import (
    CandidateError,
    create_candidate,
    list_candidates,
    list_flagged,
    list_stuck,
    new_store,
    set_stage,
    set_stuck_reason,
)

ROOT = Path(__file__).resolve().parent
STORE = new_store()


def seed():
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=8)
    create_candidate(STORE, "Priya Shah", "Engineer", "referral", now=now)
    flagged = create_candidate(STORE, "Jordan Lee", "PM", "inbound", now=old)
    stuck = create_candidate(STORE, "Sam Okoye", "Designer", "agency", now=old)
    set_stuck_reason(STORE, stuck["id"], "waiting_on_recruiter")
    return flagged["id"]


seed()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, content_type):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, payload):
        self._send(code, json.dumps(payload), "application/json")

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            html = (ROOT / "index.html").read_text(encoding="utf-8")
            self._send(200, html, "text/html; charset=utf-8")
            return
        if path == "/candidates":
            self._json(200, list_candidates(STORE))
            return
        if path == "/candidates/flagged":
            self._json(200, list_flagged(STORE))
            return
        if path == "/candidates/stuck":
            self._json(200, list_stuck(STORE))
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid json"})
            return
        path = urlparse(self.path).path
        try:
            if path == "/candidates":
                self._json(201, create_candidate(
                    STORE, data.get("name"), data.get("role"), data.get("source", "")
                ))
                return
            if path.startswith("/candidates/") and path.endswith("/stage"):
                cid = path.split("/")[2]
                self._json(200, set_stage(STORE, cid, data.get("stage")))
                return
            if path.startswith("/candidates/") and path.endswith("/reason"):
                cid = path.split("/")[2]
                self._json(200, set_stuck_reason(STORE, cid, data.get("reason")))
                return
        except CandidateError as exc:
            self._json(400, {"error": str(exc)})
            return
        self._json(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        return


def main():
    server = HTTPServer(("127.0.0.1", 8765), Handler)
    print("Open http://127.0.0.1:8765")
    server.serve_forever()


if __name__ == "__main__":
    main()
