#!/usr/bin/env python3
"""Score a hand pasted S1 run. Same scorer as run_s1.py, same bar.

Reads s1/answers/T01.txt through T10.txt, and T0X_retry.txt where present.
Refuses to report a score if answers are missing, because a partial run
reported as 10 of 10 is the exact failure this project keeps voiding.

26 Sep 2026: also reads answers/s1_answers.json, the file the browser page
03_pages/cynqra-s1-paste-pack.html downloads, and answers/model.txt, one line
naming the chat app and model used. Text files win if both exist.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from run_s1 import build_report, load_corpus, parse_json, score_one  # noqa: E402

ANSWERS = HERE / "answers"


def _bundle():
    path = ANSWERS / "s1_answers.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data.get("answers", {}) if isinstance(data, dict) else {}


def read(name):
    path = ANSWERS / name
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    text = str(_bundle().get(name.replace(".txt", ""), "")).strip()
    return text or None


def model_used():
    path = ANSWERS / "model.txt"
    if path.exists() and path.read_text(encoding="utf-8").strip():
        return path.read_text(encoding="utf-8").strip()[:120]
    bundle_path = ANSWERS / "s1_answers.json"
    if bundle_path.exists():
        try:
            return str(json.loads(bundle_path.read_text(encoding="utf-8")).get("model", "")).strip()[:120] or "not recorded"
        except json.JSONDecodeError:
            pass
    return "not recorded"


def main():
    corpus = load_corpus()
    missing = [c["id"] for c in corpus if read(f"{c['id']}.txt") is None]
    if missing:
        print(
            json.dumps(
                {
                    "spike": "S1",
                    "scored": False,
                    "reason": "Answers missing. A partial run is not a score.",
                    "missing": missing,
                    "next": "Paste the remaining items, then run this again.",
                },
                indent=2,
            )
        )
        return 2

    rows = []
    unparsed = []
    retried = []
    for case in corpus:
        first = parse_json(read(f"{case['id']}.txt"))
        result = score_one(first, case["gold"])
        attempts = 1
        if not result["passed"]:
            retry_raw = read(f"{case['id']}_retry.txt")
            if retry_raw is not None:
                attempts = 2
                retried.append(case["id"])
                result = score_one(parse_json(retry_raw), case["gold"])
        if first is None:
            unparsed.append(case["id"])
        result["id"] = case["id"]
        result["attempts"] = attempts
        rows.append(result)

    usage = {
        "calls": len(rows) + len(retried),
        "tokens_in": None,
        "tokens_out": None,
        "estimated": True,
        "note": "Hand carried. Tokens and latency not measured and not claimed.",
        "errors": [],
    }
    report = build_report(rows, "manual_paste", "hand carried: " + model_used(), usage)
    report["note"] = (
        "This is a valid S1 accuracy result. It is not a cost or latency result. "
        "S2 still needs a metered model."
    )
    report["retried"] = retried
    report["replies_that_were_not_json"] = unparsed
    out = HERE / "s1_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary = {k: v for k, v in report.items() if k != "cases"}
    print(json.dumps(summary, indent=2))
    print("wrote", out)
    for row in report["cases"]:
        mark = "pass" if row["passed"] else "FAIL"
        print(f"  {row['id']}  {mark}  strong {row['strong_fields']} of 7  weakest {row['weakest']}")
    return 0 if report["met_bar"] else 1


if __name__ == "__main__":
    sys.exit(main())
