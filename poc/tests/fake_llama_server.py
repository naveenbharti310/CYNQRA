#!/usr/bin/env python3
"""A stand-in for llama.cpp's llama-server in tests. NOT a model and never a result.

It takes llama-server's own arguments and speaks the endpoints the desktop app uses:
/health (503 while "loading"), /v1/chat/completions and /slots. Answers come from fake_model;
work replies go back as file blocks, the layout local models are asked for. Every request body
is appended to FAKE_LLAMA_REQUESTS (a file) so tests can check what the app sent.

Knobs (environment): FAKE_LLAMA_FAIL_GPU=1 exits like a failed GPU allocation unless -ngl is 0;
FAKE_LLAMA_DEVICES is what --list-devices prints; FAKE_LLAMA_STUCK_GPU seconds of silence per answer
unless -ngl is 0;
FAKE_LLAMA_EXIT=1 exits at once like a model that cannot load; FAKE_LLAMA_LOAD_S seconds of
loading before /health answers 200.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fake_model  # noqa: E402
from fake_ollama import as_blocks  # noqa: E402


def main() -> int:
    if "--list-devices" in sys.argv:
        print("Available devices:\n" + (os.environ.get("FAKE_LLAMA_DEVICES") or "  (none)"))
        return 0
    if "--version" in sys.argv:
        print("version: 11201 (fake0000)\nbuilt with a test double; not llama.cpp")
        return 0
    ap = argparse.ArgumentParser()
    ap.add_argument("-m", required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("-c", type=int, default=4096)
    ap.add_argument("-np", type=int, default=1)
    ap.add_argument("--jinja", action="store_true")
    ap.add_argument("-ngl", default="0")
    args = ap.parse_args()
    print(f"fake llama-server: model {args.m}, ctx {args.c}, ngl {args.ngl}", flush=True)
    if os.environ.get("FAKE_LLAMA_EXIT"):
        print("llama_model_load: error loading model: tensor data is not within file bounds", flush=True)
        return 1
    if os.environ.get("FAKE_LLAMA_FAIL_GPU") and args.ngl != "0":
        print("ggml_backend_alloc: failed to allocate GPU buffer of size 21474836480", flush=True)
        return 1
    if not Path(args.m).exists():
        print(f"error: model file not found: {args.m}", flush=True)
        return 1
    ready_at = time.time() + float(os.environ.get("FAKE_LLAMA_LOAD_S") or 0)
    log = os.environ.get("FAKE_LLAMA_REQUESTS")
    busy = {"on": False, "n": 0}
    lock = threading.Lock()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            raw = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path == "/health":
                if time.time() < ready_at:
                    return self._send(503, {"error": {"code": 503, "message": "Loading model"}})
                return self._send(200, {"status": "ok"})
            if self.path == "/slots":
                return self._send(200, [{"id": 0, "is_processing": busy["on"], "n_prompt_tokens": busy.get("p", 0),
                                         "next_token": [{"n_decoded": busy["n"]}]}])
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if log:
                with lock, open(log, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"path": self.path, "body": body}) + "\n")
            if self.path != "/v1/chat/completions":
                return self._send(404, {"error": "not found"})
            prompt = body["messages"][-1]["content"]
            if os.environ.get("FAKE_LLAMA_STUCK_GPU") and args.ngl != "0":
                time.sleep(float(os.environ["FAKE_LLAMA_STUCK_GPU"]))  # a GPU that loads but cannot compute
            busy.update(on=True, n=0, p=len(prompt) // 4)
            try:
                text = fake_model.answer(prompt)
                if "=== FILE:" in prompt:
                    text = as_blocks(text)
                busy["n"] = len(text) // 4
                time.sleep(float(os.environ.get("FAKE_LLAMA_THINK_S") or 0))
            finally:
                busy["on"] = False
            return self._send(200, {"choices": [{"index": 0, "finish_reason": "stop",
                                                 "message": {"role": "assistant", "content": text}}],
                                    "usage": {"prompt_tokens": max(1, len(prompt) // 4),
                                              "completion_tokens": max(1, len(text) // 4)},
                                    "timings": {"prompt_per_second": 250.0, "predicted_per_second": 20.0}})

    srv = ThreadingHTTPServer((args.host, args.port), H)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
