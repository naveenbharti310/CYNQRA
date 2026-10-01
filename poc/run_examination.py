#!/usr/bin/env python3
"""Run the fixed twenty-objective examination set against a real CYNQRA model.

This is intentionally an external harness: it does not alter product logic or select a winner. It records one
independent report per objective plus an aggregate manifest. Use a model explicitly with --model.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
OBJECTIVES = HERE / "scenarios" / "examination_20.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="CYNQRA runtime model id used for every examination run")
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--max-minutes", type=float, default=330)
    ap.add_argument("--data-root", default="")
    args = ap.parse_args()

    cases = json.loads(OBJECTIVES.read_text(encoding="utf-8"))
    cases = cases[:max(1, min(args.count, len(cases)))]
    root = Path(args.data_root) if args.data_root else Path.cwd() / "examination-data"
    root.mkdir(parents=True, exist_ok=True)
    results = []
    started = time.time()

    for case in cases:
        out = root / case["id"]
        out.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(HERE / "desktop.py"), "--e2e", args.model, case["objective"],
               "--company", f"CYNQRA Examination {case['id']}", "--data", str(out),
               "--max-minutes", str(args.max_minutes)]
        t0 = time.time()
        proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
        results.append({"id": case["id"], "domain": case["domain"], "returncode": proc.returncode,
                        "seconds": round(time.time() - t0, 1), "passed": proc.returncode == 0,
                        "stdout_tail": proc.stdout[-2000:], "stderr_tail": proc.stderr[-2000:]})
        print(f"{case['id']}: {'PASS' if proc.returncode == 0 else 'FAIL'}", flush=True)

    manifest = {"model": args.model, "count": len(results), "passed": sum(r["passed"] for r in results),
                "failed": sum(not r["passed"] for r in results), "seconds": round(time.time() - started, 1),
                "results": results}
    path = root / "examination_manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(path), "passed": manifest["passed"], "failed": manifest["failed"]}, indent=2))
    return 0 if manifest["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
