#!/usr/bin/env python3
"""Which open models Hugging Face Inference Providers serves right now, and which ones Cynqra should race.

Reads the router's live model list (GET https://router.huggingface.co/v1/models, with HF_TOKEN), prints every
model with its providers, context and price, and writes the contenders to GITHUB_OUTPUT as a JSON matrix:
openai/gpt-oss-120b, the largest Qwen coder, the largest Qwen3.6, and the largest other open coding model the
router offers. A contender needs a live provider that supports structured output (Cynqra sends JSON Schemas);
a provider on dedicated inference chips (Cerebras, Groq, SambaNova) is
preferred for speed, else the cheapest, and its price goes to the spend caps.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

FAST = {"cerebras", "groq", "sambanova"}
ROUTER = (os.environ.get("HF_ROUTER_URL") or "https://router.huggingface.co/v1").rstrip("/")


def size_b(model_id: str) -> float:
    """Parameters in billions, read from the name (480B-A35B -> 480)."""
    m = re.search(r"(\d+(?:\.\d+)?)[bB](?![a-z])", model_id.split("/")[-1])
    return float(m.group(1)) if m else 0.0


def main() -> int:
    req = urllib.request.Request(ROUTER + "/models", headers={"Authorization": f"Bearer {os.environ['HF_TOKEN']}"})
    data = json.loads(urllib.request.urlopen(req, timeout=60).read())
    models = data.get("data") or []
    print(f"{len(models)} models on Hugging Face Inference Providers\n")
    usable = {}
    for m in sorted(models, key=lambda m: m.get("id", "")):
        rows = []
        for p in m.get("providers") or []:
            price = p.get("pricing") or {}
            pin, pout = price.get("input"), price.get("output")
            rows.append(p)
            print(f"  {m['id']:<60} {p.get('provider', '?'):<14} {p.get('status', '?'):<8} "
                  f"ctx {p.get('context_length', '?'):<7} json {str(p.get('supports_structured_output', '?')):<5} "
                  f"${pin}/{pout} per M")
        ok = [p for p in rows if p.get("status") == "live" and p.get("supports_structured_output") is not False
              and (p.get("pricing") or {}).get("input") is not None]
        if ok:
            fast = [p for p in ok if p.get("provider") in FAST]  # dedicated inference chips: several times faster
            best = min(fast or ok, key=lambda p: p["pricing"]["input"] + p["pricing"]["output"])
            usable[m["id"]] = best
    picks = []

    def add(model_id: str | None, why: str) -> None:
        if model_id and model_id in usable and model_id not in [p["base"] for p in picks]:
            b = usable[model_id]
            picks.append({"base": model_id, "model": f"{model_id}:{b['provider']}", "why": why,
                          "price": f"{b['pricing']['input']},{b['pricing']['output']}",
                          "ctx": b.get("context_length") or 0})

    def largest(pattern: str) -> str | None:
        found = [i for i in usable if re.search(pattern, i, re.I)]
        return max(found, key=size_b) if found else None

    add("openai/gpt-oss-120b", "OpenAI's open 120B reasoning model")
    add(largest(r"qwen.*coder"), "the largest Qwen coder")
    add(largest(r"qwen3\.6"), "the largest Qwen3.6")
    add(largest(r"(glm|kimi|deepseek|minimax|devstral)"), "the largest other open coding model")
    print("\nContenders:")
    for p in picks:
        print(f"  {p['model']:<70} {p['why']}, ${p['price'].replace(',', ' in / ')} out per M, ctx {p['ctx']}")
    if not picks:
        print("No usable model: nothing live with structured output and a price.")
        return 1
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write("matrix=" + json.dumps({"include": picks}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
