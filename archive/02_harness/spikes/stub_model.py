#!/usr/bin/env python3
"""Wiring test only. Not a model. Never a spike result.

Reads a prompt on stdin and prints a fixed, shape correct reply, so the S2 and
S3 v2 pipelines can be exercised end to end without a key. It refuses S1
prompts, because S1 treats any command as a model. Because it is reached
through CYNQRA_S1_MODEL_CMD, its token counts are marked estimated, which means
run_s2.py writes s2_wiring_test.json and never s2_report.json.

Usage: CYNQRA_S1_MODEL_CMD="python spikes/stub_model.py"
"""
import json
import sys

prompt = sys.stdin.read()

if "You are an independent reviewer" in prompt:
    reply = {"verdict": "PASS", "defects": []}
elif "Convert the founder objective" in prompt:
    # S1 counts any command as a model, so the stub refuses S1 outright.
    # A stub reply must never be able to become an S1 report.
    sys.stderr.write("stub_model refuses S1 prompts. It is not a model.\n")
    sys.exit(1)
elif "\nAssign task" in prompt:
    reply = {"artifacts": [], "context_ref": "STUB", "acceptance_check": "STUB acceptance check"}
elif "raised a Blocker" in prompt:
    reply = {"artifacts": [], "context_ref": "STUB", "acceptance_check": "STUB missing facts"}
elif "\nReview task" in prompt:
    reply = {"recommendation": "approve, STUB", "evidence_refs": [], "cost": "STUB",
             "confidence": "low", "what_would_change_this": "STUB"}
elif "Your Handoff for task t2_07" in prompt and "Answer to your Blocker" not in prompt:
    reply = {"result": "blocked", "category": "missing_input", "description": "STUB blocker",
             "needs_from": "w_pm"}
elif "Your Handoff for task" in prompt:
    reply = {"result": "done", "output": "STUB output", "acceptance_check": "STUB check"}
else:
    reply = {"note": "STUB"}

print(json.dumps(reply))
