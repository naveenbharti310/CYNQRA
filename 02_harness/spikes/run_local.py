#!/usr/bin/env python3
"""Run S1 or S2 on an open-weight model on this machine, with no API key.

Written 27 September 2026. The spike runners, their corpus, tasks, estimate, scorers and bars
are unchanged: this file only gives them a model. It starts the Cynqra desktop app's own
llama-server for one model from its catalog (downloaded once from Hugging Face and checked
against its published SHA-256), points model_adapter at it with the app's request settings
(temperature 0, seed 42, thinking off or low), and runs the spike's own runner, whose exit code
it returns. Token counts come from llama-server, so they are measured, not estimated.

    python spikes/run_local.py s1 qwen3.6-35b-a3b-q2 --app ../poc
    python spikes/run_local.py s2 gpt-oss-20b --app ../poc

A cost result belongs to the model and machine that produced it (S2 RULINGS R5). This file
prints both and writes them to local_run.json beside the spike's report.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
IST = timezone(timedelta(hours=5, minutes=30))


def machine() -> dict:
    ram = None
    try:
        ram = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1)
    except (ValueError, OSError, AttributeError):
        pass
    cpu = ""
    try:
        cpu = next(ln.split(":", 1)[1].strip() for ln in open("/proc/cpuinfo") if ln.startswith("model name"))
    except (OSError, StopIteration):
        pass
    return {"platform": platform.platform(), "cpu": cpu or platform.processor(), "threads": os.cpu_count(),
            "ram_gb": ram, "gpu": "none used"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("spike", choices=["s1", "s2"])
    ap.add_argument("model", help="a model id from the desktop app's catalog, e.g. qwen3.6-35b-a3b-q2")
    ap.add_argument("--app", required=True, help="the folder holding the app's desktop.py (poc/, or an installed app/)")
    ap.add_argument("--data", default=str(HERE / "local_model_data"), help="where the model file and server log go")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(args.app).resolve()))
    from desktop import Desktop, prepare_model  # noqa: E402
    from cynqra.runtime import BY_ID  # noqa: E402

    desk = Desktop(Path(args.data))
    info = {"spike": args.spike.upper(), "model_id": args.model, "model": BY_ID[args.model]["name"],
            "file": BY_ID[args.model].get("file"), "server": "llama.cpp llama-server, the desktop app's build",
            "machine": machine(), "started_at": datetime.now(IST).isoformat(timespec="seconds")}
    try:
        prepare_model(desk, args.model, "off")
        info["settings"] = {k: os.environ.get(k) for k in ("CYNQRA_MODEL", "CYNQRA_NUM_PREDICT", "CYNQRA_THINK",
                                                            "CYNQRA_TEMPERATURE", "CYNQRA_SEED")}
        print(json.dumps(info, indent=1), flush=True)
        code = subprocess.run([sys.executable, str(HERE / args.spike / f"run_{args.spike}.py")], env=os.environ).returncode
    finally:
        desk.close()
    info.update(exit_code=code, finished_at=datetime.now(IST).isoformat(timespec="seconds"))
    (HERE / args.spike / "local_run.json").write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
