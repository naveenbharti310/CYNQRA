#!/usr/bin/env python3
"""M1 control panel. Started by double clicking RUN_M1.bat in the handover root.

Written 26 September 2026 by the acting CTO so the M1 spikes can be run by the
founder on a Windows PC without typing commands. Standard library only.

The API key is typed into a hidden prompt, passed to the spike for that run
only, and never written to disk, a log, or a report.
"""
from __future__ import annotations

import getpass
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPIKES = HERE / "spikes"
EXPORTS = HERE.parent / "exports"
PY = sys.executable

MENU = """
Cynqra M1
  1  Show where things stand
  2  Run S1 with an API key        (about 2 minutes, a few cents)
  3  Run S2 with an API key        (about 15 minutes, under 3 dollars)
  4  Score S1 answers pasted by hand
  5  Run S3 v2 after the seeds are sealed
  6  Run all harness tests
  7  Run the whole POC against a real model  (about 10 minutes, capped at 3 dollars)
  Q  Quit
"""


def run(args: list[str], env: dict | None = None) -> int:
    full = dict(os.environ)
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CYNQRA_S1_MODEL_CMD"):
        full.pop(k, None)
    full.update(env or {})
    return subprocess.call([PY] + args, cwd=str(HERE), env=full)


def ask_key() -> dict | None:
    print("\nWhich provider is the key for?")
    print("  1  Anthropic (recommended, default model claude-sonnet-5)")
    print("  2  OpenAI (default model gpt-4o-mini)")
    choice = input("Choose 1 or 2: ").strip()
    if choice not in ("1", "2"):
        print("No provider chosen.")
        return None
    name = "ANTHROPIC_API_KEY" if choice == "1" else "OPENAI_API_KEY"
    key = getpass.getpass("Paste the key (it will not show on screen), then press Enter: ").strip()
    if not key:
        print("No key entered.")
        return None
    env = {name: key}
    model = input("Model id, or press Enter for the default: ").strip()
    if model:
        env["CYNQRA_MODEL"] = model
    return env


def export(label: str) -> None:
    """Standing rule since 25 Aug: every scored run exports a zip the same day."""
    EXPORTS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out = EXPORTS / f"Cynqra_M1_{label}_{stamp}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in SPIKES.rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts:
                z.write(p, p.relative_to(HERE.parent))
    print(f"Saved a copy of the results: {out}")


def export_live() -> None:
    EXPORTS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out = EXPORTS / f"Cynqra_POC_live_{stamp}.zip"
    reports = HERE.parent / "poc" / "live_reports"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in reports.glob("live_*"):
            z.write(p, p.relative_to(HERE.parent))
    print(f"Saved a copy of the results: {out}")


def show(path: Path, keys: list[str]) -> None:
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    print("\nResult file:", path)
    for k in keys:
        if k in data:
            print(f"  {k}: {data[k]}")


def main() -> int:
    print("Python", sys.version.split()[0], "found.")
    while True:
        print(MENU)
        c = input("Choose: ").strip().lower()
        if c in ("q", "quit", ""):
            return 0
        if c == "1":
            run(["spikes/preflight.py"])
        elif c == "2":
            env = ask_key()
            if env:
                code = run(["spikes/s1/run_s1.py"], env)
                if code in (0, 1):
                    show(SPIKES / "s1/s1_report.json", ["passed", "total", "met_bar", "model"])
                    export("S1")
                elif code == 3:
                    print("\nThe model could not be reached, so nothing was scored. Check the key and try again.")
        elif c == "3":
            env = ask_key()
            if env:
                code = run(["spikes/s2/run_s2.py"], env)
                if code in (0, 1):
                    show(SPIKES / "s2/s2_report.json", ["model", "tasks", "measured_median", "met_bar"])
                    export("S2")
                elif code == 3:
                    print("\nThe model could not be reached, so nothing was scored. Check the key and try again.")
        elif c == "4":
            code = run(["spikes/s1/score_manual.py"])
            if code in (0, 1):
                export("S1_manual")
        elif c == "5":
            env = ask_key()
            if env:
                code = run(["spikes/s3v2/run_s3_v2.py"], env)
                if code in (0, 1):
                    export("S3v2")
        elif c == "7":
            env = ask_key()
            if env:
                code = run(["../poc/live_check.py"], env)
                if code in (0, 1, 3):
                    export_live()
                if code == 3:
                    print("\nUnrun: the model could not be reached or the spend cap stopped it. Nothing was scored.")
        elif c == "6":
            run(["spikes/test_spikes.py"])
            run(["kit/test_kit.py"])
        else:
            print("Choose one of the numbers, or Q.")
        input("\nPress Enter to go back to the menu.")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        sys.exit(0)
