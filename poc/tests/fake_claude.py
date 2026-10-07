#!/usr/bin/env python3
"""Test double for the claude command (Claude Code's print mode). NOT a model and never a result.

It is called exactly as model_adapter._claude_cli calls the real one: the prompt on stdin, the options as arguments,
and it answers with the JSON the real command prints (result, usage, total_cost_usd, modelUsage, stop_reason). The
text is fake_model.answer's, so the live path (ModelSource, model_adapter, parse, engine) runs end to end.

FAKE_CLAUDE_LOG: a file each call's arguments, folder and environment names are appended to, as one JSON line.
FAKE_CLAUDE_NO_EFFORT=1: the model refuses --effort, as a model without that setting would.
FAKE_CLAUDE_CUT=1: the reply stops at its output limit.
FAKE_CLAUDE_ERROR: answer with this error instead.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fake_model import answer  # noqa: E402

SERVED = {"claude-haiku-4-5": "claude-haiku-4-5-20251001", "haiku": "claude-haiku-4-5-20251001"}


def main() -> int:
    argv = sys.argv[1:]
    prompt = sys.stdin.read()
    model = argv[argv.index("--model") + 1] if "--model" in argv else "default"
    if os.environ.get("FAKE_CLAUDE_LOG"):
        with open(os.environ["FAKE_CLAUDE_LOG"], "a", encoding="utf-8") as f:
            f.write(json.dumps({"argv": argv, "cwd": os.getcwd(), "env": sorted(os.environ),
                                "max_output": os.environ.get("CLAUDE_CODE_MAX_OUTPUT_TOKENS")}) + "\n")
    if os.environ.get("FAKE_CLAUDE_ERROR"):
        print(json.dumps({"is_error": True, "result": os.environ["FAKE_CLAUDE_ERROR"], "total_cost_usd": 0}))
        return 1
    if os.environ.get("FAKE_CLAUDE_NO_EFFORT") == "1" and "--effort" in argv:
        print(json.dumps({"is_error": True, "result": "API Error: 400 effort is not supported on this model",
                          "total_cost_usd": 0}))
        return 1
    text = answer(prompt)
    cut = os.environ.get("FAKE_CLAUDE_CUT") == "1"
    print(json.dumps({
        "type": "result", "is_error": False, "result": text[: len(text) // 2] if cut else text,
        "stop_reason": "max_tokens" if cut else "end_turn", "duration_ms": 1200, "total_cost_usd": 0.00321,
        "usage": {"input_tokens": 900, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 400,
                  "output_tokens": max(1, len(text) // 4)},
        "modelUsage": {SERVED.get(model, model): {"inputTokens": 900, "outputTokens": max(1, len(text) // 4)}}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
