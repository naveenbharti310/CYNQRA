"""Workers may only read their own home."""
from __future__ import annotations

import os
from pathlib import Path


def home() -> Path:
    h = Path(os.environ["CYNQRA_HOME"]).resolve()
    if not h.exists():
        raise SystemExit("worker home missing")
    return h


def assert_inside(path: Path):
    path = path.resolve()
    root = home()
    if root not in path.parents and path != root:
        raise SystemExit(f"refused path outside home: {path}")
    return path
