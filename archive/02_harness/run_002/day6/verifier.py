#!/usr/bin/env python3
"""Platform verifier. May read submission and held t_002 tests only."""
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
work = HERE / "work"
if work.exists():
    shutil.rmtree(work)
work.mkdir()
shutil.copy2(HERE / "submission" / "store.py", work / "store.py")
shutil.copy2(HERE / "held" / "test_store.py", work / "test_store.py")
proc = subprocess.run(
    [sys.executable, str(work / "test_store.py")],
    cwd=str(work),
    capture_output=True,
    text=True,
    check=False,
)
print(proc.stdout)
print(proc.stderr)
(HERE / "work" / "verifier_stdout.txt").write_text(proc.stdout + "\n" + proc.stderr, encoding="utf-8")
raise SystemExit(proc.returncode)
