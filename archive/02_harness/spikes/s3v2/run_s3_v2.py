#!/usr/bin/env python3
"""S3 v2: does tiered verification catch defects it was not built around?

Written 26 September 2026 by the acting CTO. Read SEED_GUIDE.md and
spikes/s3/S3_V1_RESTATEMENT.md first.

Tiers
LOW, code: the store probes in kit/contract_checks.py.
MEDIUM, non code: the spec lint, then an independent model review
(kit/model_review.py). A spec is caught if either tier flags it.

Refusals
No SEAL.json, a seal that admits reading the checks, or fewer than 6 code and
4 non code seeds: exit 2. No model: exit 2, because v2 is defined as both tiers.
A model error: s3v2_unrun.json, exit 3. Estimated tokens: wiring test only.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent.parent
sys.path.insert(0, str(HARNESS / "kit"))
sys.path.insert(0, str(HARNESS / "spikes"))

import model_adapter  # noqa: E402
from contract_checks import check_store, lint_specs  # noqa: E402
from model_review import ReviewUnavailable, review  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
BAR = 0.8


def refuse(reason: str, code: int = 2) -> int:
    print(json.dumps({"spike": "S3 v2", "scored": False, "reason": reason}, indent=2))
    return code


def code_flags(path: Path) -> list[str]:
    try:
        findings = check_store(path)
    except Exception as exc:  # a store that cannot even load is a caught defect
        return [f"load_failed: {type(exc).__name__}"]
    return [f["id"] + ": " + f["how"] for f in findings if f.get("caught") is True]


def main() -> int:
    seal_path = HERE / "SEAL.json"
    if not seal_path.exists():
        return refuse("No SEAL.json. Seeds must be written and sealed first. See SEED_GUIDE.md.")
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    if seal.get("has_read_checks") is not False:
        return refuse("The seal does not state has_read_checks: false. Seeds must be blind.")
    seeds = seal.get("seeds") or []
    controls = seal.get("controls") or []
    n_code = sum(1 for s in seeds if s.get("kind") == "code")
    n_spec = sum(1 for s in seeds if s.get("kind") == "non_code")
    if n_code < 6 or n_spec < 4:
        return refuse(f"Need at least 6 code and 4 non code seeds, found {n_code} and {n_spec}.")
    missing = [x["file"] for x in seeds + controls if not (HERE / x["file"]).exists()]
    if missing:
        return refuse("Fixture files missing: " + ", ".join(missing))
    model = model_adapter.resolve()
    if model is None:
        return refuse("No model. S3 v2 includes the MEDIUM model tier. Set a key.")

    ctx = json.loads((HARNESS / "spikes" / "s2" / "company_context.json").read_text(encoding="utf-8"))
    estimated = False
    tokens = 0

    def judge(item: dict) -> dict:
        nonlocal estimated, tokens
        path = HERE / item["file"]
        row = {"id": item["id"], "kind": item["kind"], "file": item["file"]}
        if item["kind"] == "code":
            flags = code_flags(path)
            row.update({"tier": "LOW", "flags": flags, "flagged": bool(flags)})
            return row
        lint = [h["what"] for h in lint_specs([path])]
        verdict = review(path.read_text(encoding="utf-8"), ctx["objective"], ctx["decided_rules"])
        tokens += verdict.get("tokens", 0)
        estimated = estimated or bool(verdict.get("estimated_tokens"))
        flagged = bool(lint) or verdict["verdict"] == "FAIL"
        row.update({"tier": "MEDIUM", "lint": lint, "model_verdict": verdict["verdict"],
                    "model_defects": verdict.get("defects", []), "flagged": flagged})
        return row

    try:
        seed_rows = [judge(s) for s in seeds]
        control_rows = [judge(c) for c in controls]
    except ReviewUnavailable as exc:
        out = {"spike": "S3 v2", "scored": False, "reason": "Model review failed. Unrun, not failed.",
               "error": str(exc), "at": datetime.now(IST).isoformat(timespec="seconds")}
        (HERE / "s3v2_unrun.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(out, indent=2))
        return 3

    caught = [r["id"] for r in seed_rows if r["flagged"]]
    rate = round(len(caught) / len(seed_rows), 3)
    false_rej = [r["id"] for r in control_rows if r["flagged"]]
    inconclusive = [r["id"] for r in seed_rows + control_rows if r.get("model_verdict") == "INCONCLUSIVE"]
    report = {
        "spike": "S3 v2",
        "sealed_by": seal.get("sealed_by"),
        "sealed_at": seal.get("sealed_at"),
        "model": model["label"],
        "scored_at": datetime.now(IST).isoformat(timespec="seconds"),
        "seeded": len(seed_rows),
        "caught": caught,
        "missed": [r["id"] for r in seed_rows if not r["flagged"]],
        "catch_rate": rate,
        "bar": BAR,
        "met_bar": rate >= BAR,
        "controls": len(control_rows),
        "false_rejections": false_rej,
        "model_inconclusive": inconclusive,
        "review_tokens": tokens,
        "seeds": seed_rows,
        "control_results": control_rows,
        "note": "Bar is catch rate only, as Book 2 wrote it. False rejections are reported beside it and must be read with it.",
    }
    name = "s3v2_report.json"
    if estimated:
        report["met_bar"] = None
        report["note"] = "Wiring test. The model tier ran through a shell command. Not an S3 result."
        name = "s3v2_wiring_test.json"
    (HERE / name).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("seeded", "caught", "missed", "catch_rate", "met_bar", "false_rejections")}, indent=2))
    print("wrote", HERE / name)
    return 0 if report["met_bar"] else 1


if __name__ == "__main__":
    sys.exit(main())
