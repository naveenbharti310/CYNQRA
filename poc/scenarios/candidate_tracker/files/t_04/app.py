"""Web app for the internal candidate tracker. Python standard library only.

Run: PORT=8000 DATA_FILE=candidates.json python app.py
Routes: GET /health, GET /, GET /api/meta, GET /api/candidates,
POST /api/candidates, POST /api/candidates/<id>/stage, POST /api/candidates/<id>/reason
"""
from __future__ import annotations

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from store import REASONS, STAGES, CandidateError, CandidateStore

HERE = Path(__file__).resolve().parent
ROUTE = re.compile(r"^/api/candidates/(c_\d{3,})/(stage|reason)$")


def make_server(port: int, data_file: str | None = None) -> ThreadingHTTPServer:
    store = CandidateStore(data_file)

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
            if not size:
                return {}
            try:
                data = json.loads(self.rfile.read(size).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                raise CandidateError("body must be JSON")
            if not isinstance(data, dict):
                raise CandidateError("body must be a JSON object")
            return data

        def _view(self, rec: dict) -> dict:
            out = dict(rec)
            out["flagged"] = store.is_flagged(rec)
            out["stuck"] = store.is_stuck(rec)
            return out

        def do_GET(self):
            if self.path == "/health":
                return self._send(200, {"ok": True})
            if self.path in ("/", "/index.html"):
                return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
            if self.path == "/api/meta":
                return self._send(200, {"stages": list(STAGES), "reasons": list(REASONS)})
            if self.path == "/api/candidates":
                return self._send(200, [self._view(r) for r in store.list()])
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            try:
                body = self._body()
                if self.path == "/api/candidates":
                    rec = store.create(body.get("name", ""), body.get("applied_at") or None)
                    return self._send(201, self._view(rec))
                m = ROUTE.match(self.path)
                if not m:
                    return self._send(404, {"error": "not found"})
                cid, what = m.groups()
                if what == "stage":
                    rec = store.set_stage(cid, body.get("stage", ""))
                else:
                    rec = store.set_reason(cid, body.get("reason", ""))
                return self._send(200, self._view(rec))
            except CandidateError as exc:
                code = 404 if "unknown candidate" in str(exc) else 400
                return self._send(code, {"error": str(exc)})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    server = make_server(int(os.environ.get("PORT", "8000")), os.environ.get("DATA_FILE") or None)
    print(f"Candidate tracker on http://127.0.0.1:{server.server_address[1]}", flush=True)
    server.serve_forever()
