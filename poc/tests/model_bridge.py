#!/usr/bin/env python3
"""A command model that hands each prompt to whoever is answering, through files.

  CYNQRA_S1_MODEL_CMD="python poc/tests/model_bridge.py"  CYNQRA_BRIDGE_DIR=/some/dir

Each call writes <dir>/req_NNNN.txt and waits for <dir>/resp_NNNN.txt, then prints it.
The answerer can be a person with a chat window or a model in another process. Tokens are
estimated from characters and the run is labelled a command model, so nothing from it is a
measured cost result. Exit 1 after CYNQRA_BRIDGE_TIMEOUT seconds (default 3600) without an
answer, which the adapter treats as an unrun call. Writing <dir>/fail_NNNN.txt instead of
the response makes that call exit 1 with the file's text, to rehearse a provider outage.
"""
import os
import sys
import time
from pathlib import Path

d = Path(os.environ.get("CYNQRA_BRIDGE_DIR") or "bridge")
d.mkdir(parents=True, exist_ok=True)
prompt = sys.stdin.read()
n = len(list(d.glob("req_*.txt"))) + 1
req, resp = d / f"req_{n:04d}.txt", d / f"resp_{n:04d}.txt"
tmp = req.with_suffix(".tmp")
tmp.write_text(prompt, encoding="utf-8")
tmp.replace(req)
deadline = time.time() + float(os.environ.get("CYNQRA_BRIDGE_TIMEOUT") or 3600)
while time.time() < deadline:
    fail = d / f"fail_{n:04d}.txt"
    if fail.exists():
        sys.stderr.write(fail.read_text(encoding="utf-8") or "simulated provider error")
        sys.exit(1)
    if resp.exists():
        time.sleep(0.2)
        sys.stdout.write(resp.read_text(encoding="utf-8"))
        sys.exit(0)
    time.sleep(0.5)
sys.stderr.write(f"no answer in {resp} before the timeout\n")
sys.exit(1)
