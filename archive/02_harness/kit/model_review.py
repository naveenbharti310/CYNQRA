"""MEDIUM tier verification: an independent model reviews a spec or other non code work.

Book 2 ADR-7 and S3_BRIEF: LOW gets automated checks, MEDIUM gets an independent
second model review, HIGH gets the founder. The second tier did not exist until
26 September 2026. This file is that tier, kept deliberately plain.

The reviewer sees only the confirmed objective, the decided rules and the work. It
never sees seed files, seed ids or the mechanical checks. It returns a verdict and a
list of defects, each tied to the rule it breaks.

A model error raises ReviewUnavailable. Callers must treat that as unrun.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "spikes"))
import model_adapter  # noqa: E402

PROMPT = """You are an independent reviewer. You did not write the work below.
Check it only against the objective and the decided rules. Flag anything that
contradicts them, adds something the founder ruled out, changes what success means,
or redefines a decided term. Do not flag style or wording that breaks no rule.

Objective:
{objective}

Decided rules:
{rules}

Work to review:
---
{work}
---

Return JSON only:
{{"verdict": "PASS or FAIL", "defects": [{{"rule": "which objective part or rule", "quote": "the words in the work", "why": "one sentence"}}]}}
"""


class ReviewUnavailable(Exception):
    pass


def _parse(raw: str):
    raw = (raw or "").strip()
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def review(work: str, objective: str, rules: list[str]) -> dict:
    prompt = PROMPT.format(objective=objective, rules="\n".join(f"* {r}" for r in rules), work=work.strip())
    out = model_adapter.complete(prompt, max_tokens=1200)
    if out.get("error"):
        raise ReviewUnavailable(out["error"])
    data = _parse(out["text"])
    if not isinstance(data, dict) or str(data.get("verdict", "")).upper() not in ("PASS", "FAIL"):
        return {
            "verdict": "INCONCLUSIVE",
            "defects": [],
            "raw": out["text"][:500],
            "tokens": out["tokens_in"] + out["tokens_out"],
            "model": out.get("model"),
        }
    return {
        "verdict": str(data["verdict"]).upper(),
        "defects": data.get("defects") or [],
        "tokens": out["tokens_in"] + out["tokens_out"],
        "estimated_tokens": out["estimated"],
        "model": out.get("model"),
    }
