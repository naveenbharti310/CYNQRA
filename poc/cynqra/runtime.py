"""The model on this machine: an open-weight model served by llama.cpp's llama-server.

The desktop app ships llama-server. On first use this module downloads the model's GGUF file
from Hugging Face (resumable, checked against the published size and SHA-256), starts
llama-server with the settings from the research (poc/research/local_open_models_2026-09.md),
and points model_adapter at its OpenAI-compatible endpoint on 127.0.0.1. Prompts and answers
never leave the machine; the only network traffic is the one-time model download.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import platform
import re
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HF = os.environ.get("CYNQRA_HF_BASE", "https://huggingface.co").rstrip("/")
NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW: no console flashes up on Windows
GB = 1024 ** 3

# The research's picks. Each model names the exact file at its publisher, then mirrors of the same
# quantization. size_gb is the download in GiB; min_gb the machine memory it needs to run beside the app.
CATALOG = [
    {"id": "qwen3.6-35b-a3b", "name": "Qwen3.6 35B-A3B", "size_gb": 20.6, "min_gb": 28,
     "ctx": 32768, "predict": 8192, "think": "false",
     "files": [("unsloth/Qwen3.6-35B-A3B-GGUF", "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"),
               ("bartowski/Qwen_Qwen3.6-35B-A3B-GGUF", "Qwen_Qwen3.6-35B-A3B-Q4_K_M.gguf")],
     "about": "The best choice with 32 GB of memory or more. The strongest open coding model that fits a "
              "laptop; only 3B of its 35B parameters work on each word, so it is fast even without a GPU."},
    {"id": "qwen3.5-9b", "name": "Qwen3.5 9B", "size_gb": 5.3, "min_gb": 12,
     "ctx": 24576, "predict": 6144, "think": "false",
     "files": [("unsloth/Qwen3.5-9B-GGUF", "Qwen3.5-9B-Q4_K_M.gguf"),
               ("lmstudio-community/Qwen3.5-9B-GGUF", "Qwen3.5-9B-Q4_K_M.gguf"),
               ("bartowski/Qwen_Qwen3.5-9B-GGUF", "Qwen_Qwen3.5-9B-Q4_K_M.gguf")],
     "about": "The choice for 16 to 24 GB. Good at following Cynqra's formats; a run takes one to a few "
              "hours on a laptop without a GPU."},
    {"id": "qwen3.6-27b", "name": "Qwen3.6 27B", "size_gb": 15.7, "min_gb": 32,
     "ctx": 32768, "predict": 8192, "think": "false",
     "files": [("unsloth/Qwen3.6-27B-GGUF", "Qwen3.6-27B-Q4_K_M.gguf")],
     "about": "Stronger than 35B-A3B on hard code but three to four times slower: every parameter works on "
              "every word. For a Mac with 32 GB or more, or a GPU with 24 GB."},
    {"id": "qwen3.5-4b", "name": "Qwen3.5 4B", "size_gb": 2.6, "min_gb": 6,
     "ctx": 24576, "predict": 6144, "think": "false",
     "files": [("unsloth/Qwen3.5-4B-GGUF", "Qwen3.5-4B-Q4_K_M.gguf")],
     "about": "The smallest. Quick to download and run; checks that everything works on a weak machine, "
              "but its code fails Cynqra's checks more often."},
]
BY_ID = {m["id"]: m for m in CATALOG}
DEFAULT_BIG, DEFAULT_SMALL = "qwen3.6-35b-a3b", "qwen3.5-9b"


class ModelRuntimeError(RuntimeError):
    pass


def total_ram_gb() -> float | None:
    try:
        if sys.platform.startswith("linux"):
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 1024 / 1024
        if sys.platform == "darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout
            return int(out) / GB
        if sys.platform == "win32":
            import ctypes

            class MEM(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + \
                           [(n, ctypes.c_ulonglong) for n in ("total", "avail", "tp", "ap", "tv", "av", "ae")]
            m = MEM()
            m.dwLength = ctypes.sizeof(MEM)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.total / GB
    except (OSError, ValueError, AttributeError):
        return None
    return None


def recommended(ram_gb: float | None) -> str:
    return DEFAULT_BIG if (ram_gb or 0) >= BY_ID[DEFAULT_BIG]["min_gb"] else DEFAULT_SMALL


_TLS: list = []  # the TLS context that works on this machine, once found


def _tls_contexts() -> list:
    """The system's certificates first; then the certifi bundle shipped with the app, for machines where the
    bundled Python cannot find the system's (some Linux distributions, some macOS setups)."""
    out = [ssl.create_default_context()]
    try:
        import certifi
        out.append(ssl.create_default_context(cafile=certifi.where()))
    except ImportError:
        pass
    return out


def _request(url: str, method: str = "GET", headers: dict | None = None, timeout: float = 30.0):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": "cynqra-desktop", **(headers or {})})
    if not url.startswith("https:"):
        return urllib.request.urlopen(req, timeout=timeout)
    tries = _TLS or _tls_contexts()
    for i, ctx in enumerate(tries):
        try:
            r = urllib.request.urlopen(req, timeout=timeout, context=ctx)
            if not _TLS:
                _TLS.append(ctx)
            return r
        except urllib.error.URLError as exc:
            if not isinstance(exc.reason, ssl.SSLCertVerificationError) or i == len(tries) - 1:
                raise
    raise ModelRuntimeError("no TLS context")


def resolve(model: dict) -> dict:
    """The model's file at its publisher, or a mirror: {repo, path, size, sha256}.

    Size and SHA-256 come from Hugging Face's file listing (the LFS object id is the SHA-256 of
    the file), or from the download's own headers when the listing cannot be read.
    """
    errors = []
    for repo, path in model["files"]:
        try:
            with _request(f"{HF}/api/models/{repo}/tree/main") as r:
                tree = json.loads(r.read())
            for f in tree:
                if f.get("path") == path and f.get("type") == "file":
                    return {"repo": repo, "path": path, "size": int(f.get("size") or 0),
                            "sha256": (f.get("lfs") or {}).get("oid", "")}
            errors.append(f"{repo}: {path} is not in the repository")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            errors.append(f"{repo}: {exc}")
            try:
                with _request(f"{HF}/{repo}/resolve/main/{urllib.parse.quote(path)}", method="HEAD") as r:
                    size = int(r.headers.get("X-Linked-Size") or r.headers.get("Content-Length") or 0)
                    etag = (r.headers.get("X-Linked-Etag") or "").strip('"')
                    return {"repo": repo, "path": path, "size": size,
                            "sha256": etag if re.fullmatch(r"[0-9a-f]{64}", etag) else ""}
            except (urllib.error.URLError, OSError, ValueError) as exc2:
                errors.append(f"{repo} (download headers): {exc2}")
    raise ModelRuntimeError(f"{model['name']} could not be found on Hugging Face: " + "; ".join(errors)[:600])


class Runtime:
    """One model server for this app. state: none, downloading, checking, starting, ready, error."""

    def __init__(self, root: Path, servers: dict | None = None):
        self.root = Path(root)
        self.models_dir = self.root / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.servers = servers if servers is not None else find_servers()
        self.proc: subprocess.Popen | None = None
        self.base = ""
        self.lock = threading.RLock()
        self.status = {"state": "none", "model": None, "done": 0, "total": 0, "rate": 0, "error": "", "log": "",
                       "accel": "", "started_at": None}
        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None
        self._slots = {"t": 0.0, "data": None}
        self.ram_gb = total_ram_gb()
        self.settings_file = self.root / "settings.json"
        self._gpus: list[dict] | None = None
        if "vulkan" in self.servers:  # ask the Vulkan build which cards it sees, once, off the UI's path
            threading.Thread(target=self.gpus, daemon=True).start()

    # --- settings: the model and acceleration the founder chose, kept across launches -----------
    def settings(self) -> dict:
        try:
            s = json.loads(self.settings_file.read_text(encoding="utf-8"))
            return s if isinstance(s, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_settings(self, **kw) -> None:
        s = self.settings()
        s.update(kw)
        self.settings_file.write_text(json.dumps(s, indent=1), encoding="utf-8")

    # --- what is on disk --------------------------------------------------------------------------
    def model_path(self, model_id: str) -> Path:
        return self.models_dir / model_id / "model.gguf"

    def installed(self, model_id: str) -> Path | None:
        path, manifest = self.model_path(model_id), self.models_dir / model_id / "manifest.json"
        try:
            size = json.loads(manifest.read_text(encoding="utf-8"))["size"]
            return path if path.exists() and path.stat().st_size == size else None
        except (OSError, ValueError, KeyError):
            return None

    def remove(self, model_id: str) -> None:
        with self.lock:
            if self.status["model"] == model_id and self.status["state"] in ("downloading", "checking", "starting", "ready"):
                raise ModelRuntimeError("stop this model before removing it")
        shutil.rmtree(self.models_dir / model_id, ignore_errors=True)

    def catalog(self) -> list[dict]:
        rec = recommended(self.ram_gb)
        out = []
        for m in CATALOG:
            part = self.model_path(m["id"]).with_suffix(".gguf.part")
            out.append({k: m[k] for k in ("id", "name", "size_gb", "min_gb", "about", "ctx")} | {
                "installed": bool(self.installed(m["id"])), "recommended": m["id"] == rec,
                "fits": self.ram_gb is None or self.ram_gb >= m["min_gb"],
                "partial_gb": round(part.stat().st_size / GB, 2) if part.exists() else 0})
        return out

    def snapshot(self) -> dict:
        with self.lock:
            s = dict(self.status)
        s.update({"servers": sorted(self.servers), "ram_gb": round(self.ram_gb, 1) if self.ram_gb else None,
                  "catalog": self.catalog(), "recommended": recommended(self.ram_gb),
                  "gpu": self.settings().get("gpu", "auto"), "gpus": self._gpus or [],
                  "gpu_pick": (self.discrete_gpu() or {}).get("name") if self._gpus is not None else None,
                  "platform": f"{platform.system()} {platform.machine()}",
                  "busy": self.activity(), "model_name": BY_ID[s["model"]]["name"] if s["model"] in BY_ID else ""})
        return s

    def _set(self, **kw) -> None:
        with self.lock:
            self.status.update(kw)

    # --- download ---------------------------------------------------------------------------------
    def download(self, model_id: str) -> Path:
        model = BY_ID[model_id]
        have = self.installed(model_id)
        if have:
            return have
        self._set(state="downloading", model=model_id, done=0, total=0, rate=0, error="", log="")
        spec = resolve(model)
        dest = self.models_dir / model_id
        dest.mkdir(parents=True, exist_ok=True)
        part = self.model_path(model_id).with_suffix(".gguf.part")
        have = part.stat().st_size if part.exists() else 0
        self._set(total=spec["size"], done=have)
        free = shutil.disk_usage(dest).free
        if spec["size"] - have > free - 512 * 1024 ** 2:
            raise ModelRuntimeError(f"not enough disk space: {model['name']} needs {(spec['size'] - have) / GB:.1f} GB "
                                    f"more and {free / GB:.1f} GB is free")
        self._fetch(spec, part)
        part.replace(self.model_path(model_id))
        (dest / "manifest.json").write_text(json.dumps({"model": model_id, **spec}, indent=1), encoding="utf-8")
        self._set(done=spec["size"])
        return self.model_path(model_id)

    def _fetch(self, spec: dict, part: Path) -> None:
        url = f"{HF}/{spec['repo']}/resolve/main/{urllib.parse.quote(spec['path'])}"
        size = spec["size"]
        window: list[tuple[float, int]] = []
        for attempt in range(8):
            have = part.stat().st_size if part.exists() else 0
            if size and have >= size:
                break
            try:
                with _request(url, headers={"Range": f"bytes={have}-"}, timeout=60) as r:
                    if r.status != 206:
                        have = 0
                    with part.open("ab" if r.status == 206 else "wb") as out:
                        while True:
                            if self._cancel.is_set():
                                raise ModelRuntimeError("download paused; start it again to resume where it stopped")
                            chunk = r.read(1 << 20)
                            if not chunk:
                                break
                            out.write(chunk)
                            have += len(chunk)
                            now = time.time()
                            window.append((now, have))
                            while len(window) > 2 and now - window[0][0] > 8:
                                window.pop(0)
                            dt = now - window[0][0]
                            self._set(done=have, rate=int((have - window[0][1]) / dt) if dt > 0.5 else 0)
                if not size or have >= size:
                    break
            except ModelRuntimeError:
                raise
            except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as exc:
                if attempt == 7:
                    raise ModelRuntimeError(f"download failed after 8 attempts: {exc}") from exc
                time.sleep(min(30, 2 ** attempt))
        got = part.stat().st_size
        if size and got != size:
            raise ModelRuntimeError(f"the download is {got} bytes, expected {size}; start it again to resume")
        if spec.get("sha256"):
            self._set(state="checking")
            h = hashlib.sha256()
            with part.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 24), b""):
                    h.update(chunk)
            if h.hexdigest() != spec["sha256"]:
                part.unlink()
                raise ModelRuntimeError("the downloaded file failed its SHA-256 check and was deleted; download it again")

    # --- the server -------------------------------------------------------------------------------
    def gpus(self) -> list[dict]:
        """Graphics cards the Vulkan build of llama-server can use: [{id, name, mib, free_mib}]."""
        if self._gpus is None:
            self._gpus = []
            if "vulkan" in self.servers:
                try:
                    out = subprocess.run([*argv(self.servers["vulkan"]), "--list-devices"], capture_output=True,
                                         encoding="utf-8", errors="replace", timeout=60, creationflags=NO_WINDOW)
                    self._gpus = parse_devices(out.stdout + out.stderr)
                except (OSError, subprocess.SubprocessError):
                    pass
        return self._gpus

    def discrete_gpu(self) -> dict | None:
        """A card worth using without being asked: a discrete NVIDIA, AMD or Intel Arc card with 6 GB or more.
        Integrated graphics share the processor's memory and are often slower than the processor alone."""
        for d in self.gpus():
            name = d["name"].lower()
            integrated = ("intel" in name and not re.search(r"arc\S* [ab]\d{3}", name)) or \
                any(k in name for k in ("llvmpipe", "swiftshader", "microsoft basic"))
            if not integrated and d["mib"] >= 6000:
                return d
        return None

    def plan_accel(self, gpu: str) -> list[tuple[str, list[str]]]:
        """Which llama-server build to try, with which GPU layers, in order. The last is the processor alone.
        "-ngl auto" lets llama.cpp fit as many layers as the card's free memory holds."""
        tries = []
        if "metal" in self.servers and gpu != "off":
            tries.append(("metal", ["-ngl", "auto"]))
        if "vulkan" in self.servers and (gpu == "on" or (gpu == "auto" and self.discrete_gpu())):
            tries.append(("vulkan", ["-ngl", "auto"]))
        cpu = "cpu" if "cpu" in self.servers else ("metal" if "metal" in self.servers else None)
        if cpu:
            tries.append((cpu, ["-ngl", "0"]))
        return tries

    def start(self, model_id: str, wait: float = 900.0) -> str:
        if not self.servers:
            raise ModelRuntimeError("llama-server is missing from this installation. Reinstall Cynqra, "
                                    "or set CYNQRA_LLAMA_SERVER to a llama-server you trust.")
        model = BY_ID[model_id]
        path = self.installed(model_id) or self.download(model_id)
        self.stop()
        errors = []
        for accel, gpu_args in self.plan_accel(self.settings().get("gpu", "auto")):
            self._set(state="starting", model=model_id, error="", accel=accel)
            port = _free_port()
            cmd = [*argv(self.servers[accel]), "-m", str(path), "--host", "127.0.0.1", "--port", str(port),
                   "-c", str(model["ctx"]), "-np", "1", "--jinja", *gpu_args]
            with open(self.root / "llama-server.log", "wb") as log:
                log.write(("$ " + " ".join(cmd) + "\n").encode())
                log.flush()
                self.proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                             creationflags=NO_WINDOW)
            base = f"http://127.0.0.1:{port}"
            why = self._wait_ready(base, wait)
            if not why:
                self.base = base
                self.use(model, base)
                self._set(state="ready", model=model_id, started_at=time.time())
                self.save_settings(model=model_id)
                return base
            errors.append(f"{accel}: {why}")
            tail = self.log_tail()
            self.stop()
            if why == "stopped":
                break
        self._set(state="error", error="the model server did not start. " + " | ".join(errors), log=tail)
        raise ModelRuntimeError("the model server did not start. " + " | ".join(errors) + "\n" + tail[-800:])

    def _wait_ready(self, base: str, wait: float) -> str:
        deadline = time.time() + wait
        while time.time() < deadline:
            if self._cancel.is_set():
                return "stopped"
            if self.proc.poll() is not None:
                return f"llama-server exited with code {self.proc.returncode}"
            try:
                with _request(base + "/health", timeout=3) as r:
                    if r.status == 200:
                        return ""
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(0.5)
        return f"not ready after {int(wait)} s"

    def use(self, model: dict, base: str) -> None:
        """Point model_adapter at the running server, with the research's request settings. Only the
        model on this machine is used: API keys in the environment are ignored by this process."""
        os.environ.update({"CYNQRA_LOCAL_BASE_URL": base + "/v1", "CYNQRA_MODEL": model["name"],
                           "CYNQRA_NUM_PREDICT": str(model["predict"]), "CYNQRA_THINK": model["think"],
                           "CYNQRA_TEMPERATURE": "0", "CYNQRA_SEED": "42"})
        os.environ.setdefault("CYNQRA_TIMEOUT", "3600")
        for k in ("CYNQRA_OLLAMA_MODEL", "CYNQRA_S1_MODEL_CMD", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            os.environ.pop(k, None)

    def activity(self) -> dict | None:
        """What the model is doing now, from llama-server's /slots: the prompt it is reading, the tokens it has written."""
        if self.status.get("state") != "ready" or not self.base:
            return None
        now = time.time()
        if now - self._slots["t"] < 1.0:
            return self._slots["data"]
        data = None
        try:
            with _request(self.base + "/slots", timeout=0.4) as r:
                slots = json.loads(r.read())
            for s in slots if isinstance(slots, list) else []:
                if s.get("is_processing"):
                    nt = s.get("next_token")
                    nt = nt[0] if isinstance(nt, list) and nt else nt if isinstance(nt, dict) else {}
                    data = {"tokens": int(nt.get("n_decoded") or 0), "prompt": int(s.get("n_prompt_tokens") or 0)}
        except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError):
            data = None
        self._slots = {"t": now, "data": data}
        return data

    def log_tail(self, n: int = 2500) -> str:
        try:
            return (self.root / "llama-server.log").read_text(encoding="utf-8", errors="replace")[-n:]
        except OSError:
            return ""

    def install_and_start(self, model_id: str) -> None:
        """For the app: download if needed, then start, in the background. Progress is in snapshot()."""
        if model_id not in BY_ID:
            raise ModelRuntimeError(f"unknown model {model_id}")
        with self.lock:
            if self._worker and self._worker.is_alive():
                raise ModelRuntimeError("the model is already being prepared")

            def work():
                try:
                    self.download(model_id)
                    self.start(model_id)
                except Exception as exc:  # noqa: BLE001 - shown in the app, never swallowed
                    self._set(state="error", error=str(exc)[:600], log=self.log_tail())

            self._cancel.clear()
            self._set(state="downloading" if not self.installed(model_id) else "starting", model=model_id, error="")
            self._worker = threading.Thread(target=work, daemon=True)
            self._worker.start()

    def cancel(self) -> None:
        self._cancel.set()

    def stop(self) -> None:
        proc, self.proc = self.proc, None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        self.base = ""
        with self.lock:
            if self.status.get("state") == "ready":
                self.status["state"] = "none"
        os.environ.pop("CYNQRA_LOCAL_BASE_URL", None)


def parse_devices(text: str) -> list[dict]:
    """llama-server --list-devices: lines like "  Vulkan0: NVIDIA GeForce RTX 4060 Laptop GPU (8188 MiB, 7934 MiB free)"."""
    out = []
    for m in re.finditer(r"^\s*(\w+\d+): (.+?) \((\d+) MiB, (\d+) MiB free\)\s*$", text, re.M):
        out.append({"id": m.group(1), "name": m.group(2), "mib": int(m.group(3)), "free_mib": int(m.group(4))})
    return out


def argv(server) -> list[str]:
    """A server is a path to llama-server, or (in tests) a command as a list."""
    return [str(x) for x in server] if isinstance(server, (list, tuple)) else [str(server)]


def find_servers() -> dict:
    """llama-server builds bundled with the app ({"cpu", "vulkan", "metal"} -> path), or one named by
    CYNQRA_LLAMA_SERVER, or one on PATH."""
    exe = "llama-server.exe" if os.name == "nt" else "llama-server"
    own = "metal" if sys.platform == "darwin" else "cpu"
    if os.environ.get("CYNQRA_LLAMA_SERVER"):
        p = Path(os.environ["CYNQRA_LLAMA_SERVER"])
        return {own: str(p)} if p.exists() else {}
    found = {}
    here = Path(__file__).resolve()
    for root in (here.parents[2] / "llama", here.parents[1] / "llama", Path(sys.executable).resolve().parents[1] / "llama"):
        for accel in ("cpu", "vulkan", "metal"):
            cand = root / accel / exe
            if cand.exists() and accel not in found:
                found[accel] = str(cand)
    if not found and shutil.which(exe):
        found[own] = shutil.which(exe)
    return found


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
