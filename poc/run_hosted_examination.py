#!/usr/bin/env python3
"""Discover and examine current hosted intelligence exposed by CI credentials (cynqra/run_hosted_examination.py).

Run from the repository root or from poc/: python3 poc/run_hosted_examination.py --provider all --max-models 4
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cynqra.run_hosted_examination import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
