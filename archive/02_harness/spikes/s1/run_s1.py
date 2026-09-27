#!/usr/bin/env python3
"""S1: can a model turn a messy founder objective into the Book 1 schema?

Bar: 8 of 10, one retry allowed per item.

Three ways to reach a model, all through model_adapter:
  1. OPENAI_API_KEY
  2. ANTHROPIC_API_KEY
  3. CYNQRA_S1_MODEL_CMD, a command reading the prompt on stdin

With no model this refuses to score. It does not fall back to a filler
result, because a filler that looks like a report is how a team ends up
reporting a number nobody earned.

If you only have a chat subscription and no key, do not use this file.
Use make_paste_pack.py and score_manual.py instead. Same scorer, same bar.

Change log
26 Sep 2026, acting CTO, before any S1 run. See RULINGS.md.
1. Any model error now stops the run and writes s1_unrun.json. It never
   writes s1_report.json. Before this, a bad key, a retired model name or a
   network failure produced "0 of 10, this is the S1 result".
2. Prompt v2 replaces prompt v1 (kept as prompt_v1_24aug.txt). v1 told the
   model to leave unstated fields empty while this scorer fails any empty
   field, so an obedient model scored 0 of 10. The corpus, the expected
   answers, the scorer and the bar of 8 of 10 are unchanged.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
IST = timezone(timedelta(hours=5, minutes=30))
PROMPT_VERSION = "v2_26sep2026"
SCORER_VERSION = "24aug2026_unchanged"


class ModelUnavailable(Exception):
    """A call failed. The spike is unrun, not failed."""
sys.path.insert(0, str(HERE.parent))

import model_adapter  # noqa: E402

FIELDS = [
    "product",
    "target_customer",
    "primary_outcome",
    "business_outcome",
    "success_criteria",
    "constraints",
    "priorities",
]

USAGE = {
    "calls": 0,
    "tokens_in": 0,
    "tokens_out": 0,
    "estimated": False,
    "errors": [],
}


def load_corpus():
    return json.loads((HERE / "corpus.json").read_text(encoding="utf-8"))


def normalize(text):
    return re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower()).split()


def parse_json(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    if fenced:
        raw = fenced.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def empty_result():
    out = {k: "" for k in FIELDS}
    out["missing_fields"] = list(FIELDS)
    return out


def complete(obj):
    out = empty_result()
    if not isinstance(obj, dict):
        return out
    missing = []
    for key in FIELDS:
        val = obj.get(key)
        if isinstance(val, list):
            val = ", ".join(str(v) for v in val)
        out[key] = val.strip() if isinstance(val, str) else ""
        if not out[key]:
            missing.append(key)
    listed = obj.get("missing_fields") or []
    if isinstance(listed, list):
        extra = [x for x in listed if isinstance(x, str)]
        out["missing_fields"] = sorted(set(missing + extra))
    else:
        out["missing_fields"] = missing
    return out


def overlap(pred, gold):
    pw, gw = set(normalize(pred)), set(normalize(gold))
    if not gw:
        return 1.0 if not pw else 0.0
    if not pw:
        return 0.0
    return len(pw & gw) / len(gw)


def score_one(pred, gold):
    pred = complete(pred)
    present = all(pred[k] for k in FIELDS)
    hits = {k: overlap(pred[k], gold[k]) for k in FIELDS}
    strong = sum(1 for v in hits.values() if v >= 0.5)
    passed = present and strong >= 4
    return {
        "passed": passed,
        "present": present,
        "strong_fields": strong,
        "overlaps": hits,
        "pred": pred,
    }


def prompt_for(messy, retry=False):
    base = (HERE / "prompt.txt").read_text(encoding="utf-8")
    extra = ""
    if retry:
        extra = (
            "\nRetry. Fill every field the text states or clearly implies, and list "
            "the keys you inferred in inferred_fields. Do not add facts the founder "
            "did not state or imply.\n"
        )
    return extra + base + messy + "\n"


def call_model(prompt):
    out = model_adapter.complete(prompt)
    USAGE["calls"] += 1
    USAGE["tokens_in"] += out["tokens_in"]
    USAGE["tokens_out"] += out["tokens_out"]
    if out["estimated"]:
        USAGE["estimated"] = True
    if out["error"]:
        USAGE["errors"].append(out["error"])
        raise ModelUnavailable(out["error"])
    return parse_json(out["text"])


def run_case(case):
    gold = case["gold"]
    attempts = []
    for attempt in (1, 2):
        raw = call_model(prompt_for(case["messy"], retry=attempt == 2))
        result = score_one(raw, gold)
        result["attempt"] = attempt
        attempts.append(result)
        if result["passed"]:
            break
    final = attempts[-1]
    final["id"] = case["id"]
    final["attempts"] = len(attempts)
    return final


def build_report(rows, source, model_label, usage):
    passed = sum(1 for r in rows if r["passed"])
    return {
        "spike": "S1",
        "source": source,
        "model": model_label,
        "passed": passed,
        "total": len(rows),
        "success_bar": 8,
        "met_bar": passed >= 8,
        "usage": usage,
        "prompt_version": PROMPT_VERSION,
        "scorer_version": SCORER_VERSION,
        "scored_at": datetime.now(IST).isoformat(timespec="seconds"),
        "note": "This is the S1 result.",
        "cases": [
            {
                "id": r["id"],
                "passed": r["passed"],
                "attempts": r["attempts"],
                "strong_fields": r["strong_fields"],
                "present": r["present"],
                "weakest": sorted(r["overlaps"], key=lambda k: r["overlaps"][k])[:2],
            }
            for r in rows
        ],
    }


def main():
    model = model_adapter.resolve()
    if model is None:
        print(
            json.dumps(
                {
                    "spike": "S1",
                    "scored": False,
                    "reason": "No model. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or CYNQRA_S1_MODEL_CMD.",
                    "manual_route": "Only have a chat subscription? Run make_paste_pack.py.",
                    "note": "An unrun spike is not a failed spike.",
                },
                indent=2,
            )
        )
        return 2
    try:
        rows = [run_case(case) for case in load_corpus()]
    except ModelUnavailable as exc:
        unrun = {
            "spike": "S1",
            "scored": False,
            "reason": "A model call failed. This run is unrun, not failed. Nothing was scored.",
            "error": str(exc),
            "model": model["label"],
            "calls_before_failure": USAGE["calls"],
            "at": datetime.now(IST).isoformat(timespec="seconds"),
            "fix": "Check the key, the model name in CYNQRA_MODEL, and the network, then run again.",
        }
        (HERE / "s1_unrun.json").write_text(json.dumps(unrun, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(unrun, indent=2))
        return 3
    report = build_report(rows, "model", model["label"], dict(USAGE))
    stale = HERE / "s1_unrun.json"
    if stale.exists():
        stale.unlink()
    out = HERE / "s1_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))
    print("wrote", out)
    return 0 if report["met_bar"] else 1


if __name__ == "__main__":
    sys.exit(main())
