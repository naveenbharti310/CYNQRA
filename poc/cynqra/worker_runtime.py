"""Scoped worker execution runtime.

This is the execution substrate behind the governed Tool Gateway. It deliberately does not grant a worker the
parent process environment or an unrestricted working directory.

The runtime is a capability boundary, not a claim that the host is a security sandbox. Production deployment must
place this runtime inside an OS/container sandbox before untrusted generated code is executed.
"""
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Iterable

MAX_OUTPUT = 200_000
DEFAULT_TIMEOUT = 60
COMMANDS = {
    "python": ("python", "python3"),
    "pytest": ("pytest", "-m", "pytest"),
    "git": ("git",),
    "npm": ("npm",),
    "node": ("node",),
}


class RuntimeError(RuntimeError):
    pass


def workspace_root(root: Path) -> Path:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_path(root: Path, relative: str) -> Path:
    p = Path(relative)
    if p.is_absolute() or ".." in p.parts:
        raise RuntimeError("path must remain relative to the worker workspace")
    dest = (workspace_root(root) / p).resolve()
    if workspace_root(root) not in dest.parents and dest != workspace_root(root):
        raise RuntimeError("path escapes the worker workspace")
    return dest


def list_files(root: Path, relative: str = "") -> list[str]:
    base = safe_path(root, relative)
    if not base.exists():
        raise RuntimeError(f"path does not exist: {relative}")
    if not base.is_dir():
        raise RuntimeError("list_files requires a directory")
    return sorted(str(p.relative_to(workspace_root(root))) for p in base.rglob("*") if p.is_file())


def read_file(root: Path, relative: str, max_bytes: int = 200_000) -> str:
    p = safe_path(root, relative)
    if not p.is_file():
        raise RuntimeError(f"file does not exist: {relative}")
    if p.stat().st_size > max_bytes:
        raise RuntimeError("file exceeds the runtime read limit")
    return p.read_text(encoding="utf-8", errors="replace")


def write_file(root: Path, relative: str, content: str, max_bytes: int = 200_000) -> dict:
    data = content.encode("utf-8")
    if len(data) > max_bytes:
        raise RuntimeError("file exceeds the runtime write limit")
    p = safe_path(root, relative)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return {"path": relative, "bytes": len(data)}


def delete_file(root: Path, relative: str) -> None:
    p = safe_path(root, relative)
    if not p.is_file():
        raise RuntimeError(f"file does not exist: {relative}")
    p.unlink()


def search_files(root: Path, needle: str, relative: str = "") -> list[str]:
    if not needle:
        raise RuntimeError("search text is required")
    base = safe_path(root, relative)
    if not base.is_dir():
        raise RuntimeError("search_files requires a directory")
    hits = []
    for p in base.rglob("*"):
        if p.is_file() and p.stat().st_size <= 1_000_000:
            try:
                if needle in p.read_text(encoding="utf-8", errors="replace"):
                    hits.append(str(p.relative_to(workspace_root(root))))
            except OSError:
                continue
    return sorted(hits)


def _command(argv: Iterable[str]) -> list[str]:
    argv = list(argv)
    if not argv or argv[0] not in COMMANDS:
        raise RuntimeError("command is not in the runtime allowlist")
    if argv[0] == "python":
        return ["python3", *argv[1:]]
    return argv


def run(root: Path, argv: list[str], *, timeout: int = DEFAULT_TIMEOUT,
        env_allowlist: Iterable[str] = ()) -> dict:
    if timeout <= 0 or timeout > 900:
        raise RuntimeError("timeout must be between 1 and 900 seconds")
    root = workspace_root(root)
    command = _command(argv)
    allowed_env = {"PATH", "HOME", "LANG", "LC_ALL", *env_allowlist}
    env = {k: v for k, v in os.environ.items() if k in allowed_env}
    try:
        proc = subprocess.run(command, cwd=root, env=env, text=True, capture_output=True,
                              timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"command timed out after {timeout}s") from exc
    stdout = (proc.stdout or "")[-MAX_OUTPUT:]
    stderr = (proc.stderr or "")[-MAX_OUTPUT:]
    return {"argv": command, "returncode": proc.returncode, "passed": proc.returncode == 0,
            "stdout": stdout, "stderr": stderr}
