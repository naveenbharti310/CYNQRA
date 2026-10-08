"""Which files a worker may write: the same rule at the gateway (every real write), in calibration (its trial
files) and in what each task is told before it writes. A build or deployment needs a few files whose names are the
convention and have no extension: the real run of 8 Oct on Claude wrote a Dockerfile 74 times, and every write was
refused, with a reason that did not say what the rule allows."""
from __future__ import annotations

from pathlib import Path

ALLOWED_EXT = {".py", ".md", ".html", ".json", ".txt", ".css", ".js", ".yml", ".yaml", ".toml", ".ini", ".cfg"}
ALLOWED_NAMES = {"Dockerfile", "Makefile", "Procfile", ".dockerignore", ".gitignore"}
MAX_DEPTH = 3
RULE = ("inside the task's own folder, at most three folders deep, named *" + ", *".join(sorted(ALLOWED_EXT))
        + ", or " + ", ".join(sorted(ALLOWED_NAMES)))


def allowed(target) -> bool:
    rel = Path(str(target))
    if rel.is_absolute() or ".." in rel.parts or len(rel.parts) > MAX_DEPTH or not rel.parts:
        return False
    return rel.suffix in ALLOWED_EXT or rel.name in ALLOWED_NAMES
