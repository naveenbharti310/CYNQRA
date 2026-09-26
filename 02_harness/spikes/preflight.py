#!/usr/bin/env python3
"""What is ready, what is blocked, and what is missing. One screen, no jargon.

Run this first, and run it again whenever you are not sure where you stand.
It reads the report files on disk, so it cannot flatter you.

26 Sep 2026: knows about unrun attempts (s1_unrun.json, s2_unrun.json), about
S2 wiring tests that never count, about the S3 v1 restatement, and about S3 v2.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import model_adapter  # noqa: E402

BAR_S1 = 8
BAR_S3 = 0.8


def line(name, state, detail):
    print(f"{name:<7}{state:<10}{detail}")


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def newer(a: Path, b: Path) -> bool:
    return a.exists() and (not b.exists() or a.stat().st_mtime > b.stat().st_mtime)


def answers_progress():
    folder = HERE / "s1" / "answers"
    corpus = read_json(HERE / "s1" / "corpus.json") or []
    bundle = (read_json(folder / "s1_answers.json") or {}).get("answers", {})
    done = 0
    for c in corpus:
        f = folder / f"{c['id']}.txt"
        if (f.exists() and f.read_text(encoding="utf-8").strip()) or str(bundle.get(c["id"], "")).strip():
            done += 1
    return done, len(corpus)


def main():
    model = model_adapter.resolve()
    blocked = []

    if model is None:
        line("model", "BLOCKED", "No key. Set ANTHROPIC_API_KEY or OPENAI_API_KEY, or use RUN_M1.bat.")
        blocked.append("model")
    else:
        line("model", "READY", f"{model['label']}, tokens {model['tokens']}")

    s1_dir = HERE / "s1"
    s1 = read_json(s1_dir / "s1_report.json")
    done, total = answers_progress()
    if newer(s1_dir / "s1_unrun.json", s1_dir / "s1_report.json"):
        err = (read_json(s1_dir / "s1_unrun.json") or {}).get("error", "")
        line("S1", "UNRUN", f"last attempt hit a model error, nothing scored: {err[:90]}")
        blocked.append("S1")
    elif s1 and s1.get("passed") is not None:
        verdict = "met bar" if s1.get("met_bar") else "below bar"
        how = s1.get("model", "")
        line("S1", "DONE", f"{s1['passed']} of {s1['total']}, bar {BAR_S1}, {verdict}, {how}, prompt {s1.get('prompt_version', 'v1')}")
    elif done:
        line("S1", "IN PROG", f"paste pack {done} of {total} answered, then score it")
        blocked.append("S1")
    elif model is None:
        line("S1", "BLOCKED", f"needs a key, or do it by hand with 03_pages/cynqra-s1-paste-pack.html, bar {BAR_S1} of 10")
        blocked.append("S1")
    else:
        line("S1", "READY", f"10 items, bar {BAR_S1} of 10, a few cents")

    s2_dir = HERE / "s2"
    s2 = read_json(s2_dir / "s2_report.json")
    if newer(s2_dir / "s2_unrun.json", s2_dir / "s2_report.json"):
        err = (read_json(s2_dir / "s2_unrun.json") or {}).get("error", "")
        line("S2", "UNRUN", f"last attempt hit a model error, nothing scored: {err[:90]}")
        blocked.append("S2")
    elif s2 and s2.get("counts_as_measured_result"):
        verdict = "met bar" if s2.get("met_bar") else "below bar"
        line("S2", "DONE", f"{s2.get('tasks')} tasks, {verdict}, measured tokens, {s2.get('model')}")
    elif model is None:
        line("S2", "BLOCKED", "needs a metered key. Cannot be done by hand, it measures cost.")
        blocked.append("S2")
    elif model["tokens"] != "measured":
        line("S2", "BLOCKED", "model found but tokens are estimated. S2 needs an API key to count.")
        blocked.append("S2")
    else:
        line("S2", "READY", "12 tasks against the estimate locked 25 Aug, under three dollars")

    s3v2 = read_json(HERE / "s3v2" / "s3v2_report.json")
    if s3v2:
        verdict = "met bar" if s3v2.get("met_bar") else "below bar"
        line("S3", "DONE", f"v2 {len(s3v2.get('caught', []))} of {s3v2.get('seeded')} caught, bar {BAR_S3}, {verdict}, "
             f"false rejections {len(s3v2.get('false_rejections', []))}")
    elif (HERE / "s3" / "S3_V1_RESTATEMENT.md").exists():
        sealed = (HERE / "s3v2" / "SEAL.json").exists()
        if not sealed:
            line("S3", "OPEN", "v1 9 of 10 is restated and does not count. v2 needs blind seeds, see s3v2/SEED_GUIDE.md")
            blocked.append("S3")
        elif model is None:
            line("S3", "BLOCKED", "v2 seeds sealed, needs a key for the model review tier")
            blocked.append("S3")
        else:
            line("S3", "READY", "v2 seeds sealed, both tiers ready")
    else:
        s3 = read_json(HERE / "s3" / "s3_report.json")
        if s3:
            line("S3", "DONE", f"v1 {len(s3.get('caught', []))} of 10, mechanical only")

    print()
    print("Blocked: " + ", ".join(blocked) if blocked else "Nothing blocked.")
    print("An unrun spike is not a failed spike.")
    print("M2 does not start until S1 and S2 have real scores and someone writes the go or no go.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
