"""Running the code the team wrote with the limits the host allows (R5 of the architecture review).

Generated code runs as host processes when its tests run, when a worker runs a command and when the product is
deployed. Each such process already gets a scrubbed environment (no keys, no tokens, no home: testrunner.clean_env,
worker_runtime.run) and a process group of its own that is stopped as a whole. On top of that, here:

* resource limits, where the OS has them (POSIX): no core dumps, a cap on any one file it writes, on open files, on
  memory (Linux) and on CPU seconds, so a runaway loop, a memory bomb or a disk filler stops at the limit;
* no network for tests and commands, where Linux lets a process take a network namespace of its own (as root, or
  through an unprivileged user namespace): the code sees only its own loopback, so a test server on 127.0.0.1 still
  works and nothing it does reaches another host. A deployed product keeps the host's loopback, where it is checked.

isolation() says which of these this host gives; it is recorded with each run. This is hardening, not a security
sandbox: the code runs as the same user on the same kernel and can read what that user can. A microVM or gVisor per
workspace is the design for running untrusted code for customers (architecture review, P3).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading

MiB = 1024 * 1024
LIMITS = {"RLIMIT_CORE": 0, "RLIMIT_FSIZE": 256 * MiB, "RLIMIT_NOFILE": 1024}
LINUX_LIMITS = {"RLIMIT_AS": 4096 * MiB}  # macOS does not enforce an address-space limit

# Runs in a fresh interpreter (-I: no environment, no user site), sets the limits, takes a network namespace when
# asked, then becomes the command: the parent's threads are never involved (no preexec_fn).
LAUNCHER = r"""
import ctypes, fcntl, json, os, resource, socket, struct, sys
spec, argv = json.loads(sys.argv[1]), sys.argv[2:]
for name, value in spec.get("limits", {}).items():
    which = getattr(resource, name, None)
    if which is None:
        continue
    soft, hard = resource.getrlimit(which)
    value = value if hard == resource.RLIM_INFINITY else min(value, hard)
    try:
        resource.setrlimit(which, (value, value))
    except (ValueError, OSError):
        pass
if spec.get("no_network"):
    libc = ctypes.CDLL(None, use_errno=True)
    NEWNET, NEWUSER = 0x40000000, 0x10000000
    uid, gid = os.getuid(), os.getgid()
    ok = libc.unshare(NEWNET) == 0
    if not ok and libc.unshare(NEWUSER | NEWNET) == 0:
        for path, text in (("/proc/self/setgroups", "deny"), ("/proc/self/uid_map", f"{uid} {uid} 1"),
                           ("/proc/self/gid_map", f"{gid} {gid} 1")):
            try:
                with open(path, "w") as f:
                    f.write(text)
            except OSError:
                pass
        ok = True
    if ok:
        try:
            s = socket.socket()
            flags = struct.unpack("16sh", fcntl.ioctl(s.fileno(), 0x8913, struct.pack("16sh22x", b"lo", 0))[:18])[1]
            fcntl.ioctl(s.fileno(), 0x8914, struct.pack("16sh22x", b"lo", flags | 0x1 | 0x40))  # up, running
            s.close()
        except OSError as exc:
            sys.stderr.write(f"[sandbox: the loopback could not be brought up: {exc}]\n")
    else:
        sys.stderr.write("[sandbox: no network namespace on this host: the code keeps the host's network]\n")
os.execvp(argv[0], argv)
"""

_PROBE = ("import os, socket; s = socket.socket(); s.bind(('127.0.0.1', 0)); s.listen(1); "
          "c = socket.create_connection(s.getsockname(), timeout=2); c.close(); "
          "print(os.readlink('/proc/self/ns/net'))")
_STATE: dict = {}
_LOCK = threading.Lock()


def _python() -> str:
    from .testrunner import python_exe
    return python_exe()


def _limits(cpu_s: int | None) -> dict:
    out = dict(LIMITS)
    if sys.platform.startswith("linux"):
        out.update(LINUX_LIMITS)
    if cpu_s:
        out["RLIMIT_CPU"] = int(cpu_s)
    return out


def isolation() -> dict:
    """What this host gives the code the team wrote, probed once: resource limits, and whether a test or a command
    runs with no network of its own."""
    with _LOCK:
        if _STATE:
            return dict(_STATE)
        limits = os.name == "posix"
        network = False
        if sys.platform.startswith("linux") and os.environ.get("CYNQRA_SANDBOX_NETWORK", "1") != "0":
            try:
                spec = json.dumps({"limits": {}, "no_network": True})
                out = subprocess.run([_python(), "-I", "-c", LAUNCHER, spec, _python(), "-I", "-c", _PROBE],
                                     capture_output=True, text=True, timeout=20)
                child = (out.stdout or "").strip().splitlines()[-1:] or [""]
                network = out.returncode == 0 and child[0].startswith("net:") \
                    and child[0] != os.readlink("/proc/self/ns/net")
            except (OSError, subprocess.SubprocessError, ValueError):
                network = False
        parts = ["scrubbed environment", "own process group"]
        if limits:
            parts.append("resource limits")
        parts.append("no network for tests and commands" if network else "host network")
        _STATE.update(level=", ".join(parts), resource_limits=limits, network_isolated=network,
                      security_sandbox=False,
                      note="hardening, not a security sandbox: the code runs as the same user on the same kernel")
        return dict(_STATE)


def wrap(argv: list[str], *, network: bool = False, cpu_s: int | None = None) -> list[str]:
    """argv run under the launcher: the limits, and no network unless network is True and the host allows it.
    Unchanged where the OS has no resource limits (Windows)."""
    if os.name != "posix":
        return list(argv)
    spec = {"limits": _limits(cpu_s), "no_network": not network and isolation()["network_isolated"]}
    return [_python(), "-I", "-c", LAUNCHER, json.dumps(spec), *argv]
