#!/usr/bin/env python3
"""Cost model v0, the M1 exit item Book 3 section 6 says S2 seeds.

Reads s2_report.json and turns measured tokens into money for the model inference
line of Book 3 section 6. Refuses to run on anything but a measured S2 report.

Prices are per million tokens, input and output, from the Claude pricing page as
read on 26 September 2026. Add a row for any other model before running. Prices
change; the printed output names the table it used.

Only the model inference line is computed. Worker runtime compute, tools and
infrastructure, and our own human attention are the other three lines of the
Book 3 table and stay "tracked, not yet measured" until M2 has a runtime.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

PRICES_USD_PER_MTOK = {  # as read 26 Sep 2026, platform.claude.com models overview
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-fable-5-1": (10.0, 50.0),
}


def main() -> int:
    path = HERE / "s2_report.json"
    if not path.exists():
        print("No s2_report.json. Cost model v0 waits for a measured S2 run.")
        return 2
    rep = json.loads(path.read_text(encoding="utf-8"))
    if not rep.get("counts_as_measured_result"):
        print("s2_report.json is not a measured result. Refusing.")
        return 2
    model = rep.get("model")
    if model not in PRICES_USD_PER_MTOK:
        print(f"No price row for {model}. Add it to PRICES_USD_PER_MTOK with its date and source.")
        return 2
    p_in, p_out = PRICES_USD_PER_MTOK[model]
    rows = [r for r in rep["rows"] if r.get("status") in ("done", "blocked")]

    def usd(r):
        return r["tokens_in"] / 1e6 * p_in + r["tokens_out"] / 1e6 * p_out

    by_tier = {}
    for tier in ("LOW", "MEDIUM"):
        costs = [usd(r) for r in rows if r["risk"] == tier]
        if costs:
            by_tier[tier] = {"tasks": len(costs), "median_usd": round(statistics.median(costs), 4),
                             "total_usd": round(sum(costs), 4)}
    run_total = round(sum(usd(r) for r in rows), 4)
    out = {
        "cost_model": "v0",
        "source": "s2_report.json",
        "model": model,
        "price_table": {"input_per_mtok": p_in, "output_per_mtok": p_out, "as_of": "2026-09-26"},
        "model_inference_per_task": by_tier,
        "model_inference_per_12_task_run_usd": run_total,
        "not_yet_measured": ["worker runtime compute", "tools and infrastructure", "human attention (ours)"],
        "book3_target": "Total cost per company month under 30 percent of a freelance team for the same output. "
                        "Needs the freelance benchmark (D-8 three quote median) before it can be checked.",
    }
    (HERE / "cost_model_v0.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
