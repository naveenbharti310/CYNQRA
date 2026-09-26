#!/usr/bin/env python3
"""S3 mechanical pass. Seeds sealed. Checks come from the objective contract.

26 Sep 2026: s3_report.json is the recorded v1 result and is never overwritten.
A rerun writes s3_rerun_<time>.json, which is not a result. S3 v1 is restated
in S3_V1_RESTATEMENT.md. The next S3 claim comes from spikes/s3v2.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent.parent / "kit"
sys.path.insert(0, str(KIT))
from contract_checks import check_store, lint_specs

SEED_MAP = {
    "s3_01": "empty_name",
    "s3_02": "unknown_stage",
    "s3_03": "starts_applied",
    "s3_04": "list_all",
    "s3_05": "unknown_id",
    "s3_06": "write_surfaces",
    "s3_07": "stuck_clock",
    "s3_08": "public_site",
    "s3_09": "dashboard_success",
    "s3_10": "applicant_login",
}


def main():
    seeds = json.loads((HERE / "seeds.json").read_text(encoding="utf-8"))
    tainted = HERE / "tainted"
    store_findings = check_store(tainted / "store.py")
    spec_hits = lint_specs(list(tainted.glob("*.md")))
    by_id = {f["id"]: f for f in store_findings}
    spec_ids = {h["id"] for h in spec_hits}
    caught, missed = [], []
    detail = []
    for seed in seeds["seeds"]:
        sid = seed["id"]
        key = SEED_MAP[sid]
        if seed["kind"] == "code":
            f = by_id.get(key)
            ok = bool(f and f.get("caught"))
            how = f["how"] if f else "no check"
        else:
            ok = key in spec_ids
            how = "spec lint" if ok else "spec lint missed"
        row = {"id": sid, "caught": ok, "how": how, "kind": seed["kind"]}
        detail.append(row)
        (caught if ok else missed).append(sid)
    n = len(seeds["seeds"])
    rate = round(len(caught) / n, 2)
    report = {
        "spike": "S3",
        "method": "objective contract checks plus spec lint. Not a second model.",
        "seeded": n,
        "caught": caught,
        "missed": missed,
        "catch_rate": rate,
        "bar": 0.8,
        "met_bar": rate >= 0.8,
        "detail": detail,
        "store_findings": store_findings,
        "spec_hits": spec_hits,
    }
    out = HERE / "s3_report.json"
    if out.exists():
        from datetime import datetime
        out = HERE / f"s3_rerun_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report["note"] = "Rerun on the v1 seeds. Not a result. The recorded v1 result is s3_report.json."
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"caught": len(caught), "missed": missed, "rate": rate, "met_bar": report["met_bar"]}, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    main()
