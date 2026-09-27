"""The model registry: which AI models Cynqra can staff workers with, and how each has actually performed.

A model entry holds identity and facts: runtime, provider, the model it serves, context length, licence, price,
hardware. It holds no capability scores. What a model is good at is learned only from Cynqra's own work: every
model call is metered (tokens, seconds, dollars) and every verification of a task is an outcome for the model
that did it, for that kind of task. The workforce engine reads these to choose, and replace, workers' models.

The registry lives beside the runs (registry.db), not inside one, so what Cynqra learns carries across projects.

Runtimes
  llama               a model from the desktop app's catalog on this machine (llama.cpp). One llama-server serves
                      one model; the registry swaps it in when a worker on that model needs it.
  hf                  Hugging Face Inference Providers (HF_TOKEN), e.g. zai-org/GLM-4.7 or moonshotai/Kimi-K2.5.
  openai_compatible   any server that speaks OpenAI's chat completions: base_url, and the name of the environment
                      variable that holds its key. The key itself is never stored.

Faults, for proving replacement on real models: offline (calls fail as if the model were unreachable) and
max_reply (the model's replies are capped, so its real output runs out of room). Both are recorded and shown.
"""
from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path

from .db import Store, now

RUNTIMES = ("llama", "hf", "openai_compatible")
DOWN_AFTER_ERRORS = 2  # consecutive failed calls before a model counts as unavailable
DOWN_FOR_S = 600


class RegistryError(ValueError):
    pass


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "model"


class Registry:
    def __init__(self, root: Path, runtime=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = Store(str(self.root / "registry.db"))
        self.runtime = runtime  # the desktop app's llama-server manager, for llama models
        self.lock = threading.RLock()

    def close(self) -> None:
        self.store.close()

    # --- models -------------------------------------------------------------------------------------
    def models(self, include_removed: bool = False) -> list[dict]:
        return [m for m in self.store.all("model") if include_removed or m.get("status") != "removed"]

    def get(self, model_id: str) -> dict:
        m = self.store.get("model", model_id)
        if m is None or m.get("status") == "removed":
            raise RegistryError(f"no model {model_id!r} in the registry")
        return m

    def register(self, spec: dict) -> dict:
        """Add a model. spec: runtime, ref (catalog id, HF model id or served model name), name, and the facts
        that are known: provider, version, context, license, params, hardware, price_in / price_out (USD per
        million tokens, for hosted models), compute_usd_per_hour (for a model on this machine), base_url and
        api_key_env (openai_compatible)."""
        runtime = spec.get("runtime")
        if runtime not in RUNTIMES:
            raise RegistryError(f"runtime must be one of {', '.join(RUNTIMES)}")
        ref = str(spec.get("ref") or "").strip()
        if not ref:
            raise RegistryError("ref is required: the catalog id, Hugging Face model id or served model name")
        facts: dict = {}
        if runtime == "llama":
            from .runtime import BY_ID
            if ref not in BY_ID:
                raise RegistryError(f"{ref} is not in the app's model catalog")
            c = BY_ID[ref]
            facts = {"name": c["name"], "provider": ref.split("-")[0].capitalize(), "context": c["ctx"],
                     "hardware": f"this machine, {c['min_gb']} GB of memory or more", "size_gb": c.get("size_gb"),
                     "license": c.get("license", ""), "local": True, "predict": c["predict"], "think": c["think"]}
        elif runtime == "openai_compatible" and not spec.get("base_url"):
            raise RegistryError("an openai_compatible model needs base_url")
        m = {"runtime": runtime, "ref": ref, "local": runtime == "llama", "provider": "", "version": "", "context": 0,
             "license": "", "params": "", "hardware": "hosted" if runtime != "llama" else "", "price_in": 0.0,
             "price_out": 0.0, "compute_usd_per_hour": 0.0, "base_url": "", "api_key_env": "", "effort": "",
             "json_schema": True, "tools": False}
        m.update(facts)
        for k in ("name", "provider", "version", "context", "license", "params", "hardware", "price_in", "price_out",
                  "compute_usd_per_hour", "base_url", "api_key_env", "effort", "json_schema", "tools"):
            if spec.get(k) not in (None, ""):
                m[k] = spec[k]
        for k in ("price_in", "price_out", "compute_usd_per_hour"):
            m[k] = float(m[k] or 0)
        m["context"] = int(m["context"] or 0)
        m["name"] = m.get("name") or ref
        m["id"] = spec.get("id") or slug(m["name"])
        with self.lock:
            old = self.store.get("model", m["id"])
            m.update({"status": "active", "fault": (old or {}).get("fault") or {}, "health": {"errors": 0, "down_until": 0},
                      "registered_at": (old or {}).get("registered_at") or now()})
            self.store.put("model", m["id"], m)
        return m

    def remove(self, model_id: str) -> None:
        with self.lock:
            m = self.get(model_id)
            m["status"] = "removed"
            self.store.put("model", model_id, m)

    def set_fault(self, model_id: str, offline: bool | None = None, max_reply: int | None = None) -> dict:
        with self.lock:
            m = self.get(model_id)
            f = dict(m.get("fault") or {})
            if offline is not None:
                f["offline"] = bool(offline)
            if max_reply is not None:
                f["max_reply"] = max(0, int(max_reply))
            m["fault"] = {k: v for k, v in f.items() if v}
            if not m["fault"]:
                m["health"] = {"errors": 0, "down_until": 0}
            self.store.put("model", model_id, m)
            return m

    # --- availability -------------------------------------------------------------------------------
    def availability(self, m: dict) -> tuple[bool, str]:
        """Can a worker on this model make a call now? Static checks, then recent call health."""
        if m.get("status") == "removed":
            return False, "removed"
        if m["runtime"] == "llama":
            if self.runtime is None:
                return False, "no model runtime in this process"
            if not self.runtime.installed(m["ref"]):
                return False, "not downloaded on this machine"
            if not self.runtime.servers:
                return False, "llama-server is missing"
        elif m["runtime"] == "hf" and not os.environ.get("HF_TOKEN"):
            return False, "HF_TOKEN is not set"
        elif m["runtime"] == "openai_compatible" and m.get("api_key_env") and not os.environ.get(m["api_key_env"]):
            return False, f"{m['api_key_env']} is not set"
        h = m.get("health") or {}
        if h.get("down_until", 0) > time.time():
            return False, f"down after {h.get('errors')} failed calls in a row"
        return True, "available"

    def available(self) -> list[dict]:
        return [m for m in self.models() if self.availability(m)[0]]

    # --- calling a model ----------------------------------------------------------------------------
    def route(self, model_id: str) -> dict:
        """The settings for one call to this model, for model_adapter.complete(route=...)."""
        m = self.get(model_id)
        base = {"label": m["name"], "local": m["local"], "CYNQRA_S1_MODEL_CMD": None, "CYNQRA_OLLAMA_MODEL": None,
                "CYNQRA_TEMPERATURE": "0", "CYNQRA_SEED": "42", "CYNQRA_NUM_PREDICT": None, "CYNQRA_THINK": None,
                "CYNQRA_EFFORT": m.get("effort") or None, "CYNQRA_LOCAL_API_KEY": None}
        if m["runtime"] == "llama":
            url = self._serve(m["ref"])
            base.update({"kind": "local", "CYNQRA_LOCAL_BASE_URL": url + "/v1", "CYNQRA_MODEL": m["name"],
                         "CYNQRA_NUM_PREDICT": str(m.get("predict") or 8192), "CYNQRA_THINK": m.get("think") or None})
        elif m["runtime"] == "hf":
            base.update({"kind": "hf", "CYNQRA_HF_MODEL": m["ref"]})
        else:
            base.update({"kind": "local", "local": False, "CYNQRA_LOCAL_BASE_URL": m["base_url"].rstrip("/"),
                         "CYNQRA_MODEL": m["ref"],
                         "CYNQRA_LOCAL_API_KEY": os.environ.get(m["api_key_env"]) if m.get("api_key_env") else None})
        fault = m.get("fault") or {}
        if fault.get("offline"):
            base["offline"] = True
        if fault.get("max_reply"):
            base["CYNQRA_MAX_REPLY"] = str(fault["max_reply"])
        return base

    def _serve(self, ref: str) -> str:
        """One llama-server serves one model: start this one if another is loaded (a swap takes seconds)."""
        rt = self.runtime
        if rt is None:
            raise RegistryError("no model runtime in this process")
        with self.lock:
            if rt.status.get("model") == ref and rt.status.get("state") == "ready" and rt.base:
                return rt.base
            rt.stop()
            return rt.start(ref)

    def cost(self, m: dict, tokens_in: int, tokens_out: int, seconds: float) -> float:
        if m["local"]:
            return round(seconds * float(m.get("compute_usd_per_hour") or 0) / 3600, 6)
        return round(tokens_in * m["price_in"] / 1e6 + tokens_out * m["price_out"] / 1e6, 6)

    # --- measurement --------------------------------------------------------------------------------
    def record_call(self, model_id: str, *, role: str, purpose: str, task_kind: str, usage: dict, run_id: str,
                    error: str = "") -> dict:
        """Every call, metered: what it cost and how long it took. A failed call counts toward being down."""
        with self.lock:
            m = self.get(model_id)
            secs = float(usage.get("latency_s") or 0)
            c = {"id": f"c_{self._n('call') + 1:06d}", "model_id": model_id, "role": role, "purpose": purpose,
                 "task_kind": task_kind, "run_id": run_id, "tokens_in": int(usage.get("tokens_in") or 0),
                 "tokens_out": int(usage.get("tokens_out") or 0), "seconds": round(secs, 1),
                 "usd": self.cost(m, int(usage.get("tokens_in") or 0), int(usage.get("tokens_out") or 0), secs),
                 "write_tps": usage.get("write_tps"), "error": error[:300], "at": now()}
            self.store.put("call", c["id"], c)
            h = m.get("health") or {"errors": 0, "down_until": 0}
            h["errors"] = h.get("errors", 0) + 1 if error else 0
            if h["errors"] >= DOWN_AFTER_ERRORS:
                h["down_until"] = time.time() + DOWN_FOR_S
            m["health"] = h
            self.store.put("model", model_id, m)
            return c

    def record_outcome(self, model_id: str, *, role: str, task_kind: str, task_id: str, run_id: str, attempt: int,
                       verified: bool, usd: float, seconds: float, tokens: int, failure: str = "",
                       source: str = "project") -> dict:
        """One verification of one attempt at a task: the unit Cynqra learns from."""
        with self.lock:
            o = {"id": f"o_{self._n('outcome') + 1:06d}", "model_id": model_id, "role": role, "task_kind": task_kind,
                 "task_id": task_id, "run_id": run_id, "attempt": attempt, "verified": bool(verified),
                 "first_pass": bool(verified and attempt == 1), "usd": round(usd, 6), "seconds": round(seconds, 1),
                 "tokens": int(tokens), "failure": failure[:400], "source": source, "at": now()}
            self.store.put("outcome", o["id"], o)
            return o

    def _n(self, kind: str) -> int:
        return len(self.store.all(kind))

    def outcomes(self, model_id: str | None = None, task_kind: str | None = None) -> list[dict]:
        return [o for o in self.store.all("outcome") if (model_id is None or o["model_id"] == model_id)
                and (task_kind is None or o["task_kind"] == task_kind)]

    def calls(self, model_id: str | None = None) -> list[dict]:
        return [c for c in self.store.all("call") if model_id is None or c["model_id"] == model_id]

    def stats(self, model_id: str, task_kind: str | None = None) -> dict:
        """Measured performance: attempts verified, first-pass rate, cost and time per attempt, speed."""
        outs = self.outcomes(model_id, task_kind)
        n = len(outs)
        ok = sum(1 for o in outs if o["verified"])
        tasks = {(o["run_id"], o["task_id"]) for o in outs}
        first = sum(1 for o in outs if o["first_pass"])
        firsts = {(o["run_id"], o["task_id"]) for o in outs if o["attempt"] == 1}
        calls = self.calls(model_id)
        tps = [c["write_tps"] for c in calls if c.get("write_tps")]
        return {"attempts": n, "verified": ok, "tasks": len(tasks),
                "success_rate": round(ok / n, 3) if n else None,
                "first_pass_rate": round(first / len(firsts), 3) if firsts else None,
                "usd_per_attempt": round(sum(o["usd"] for o in outs) / n, 4) if n else None,
                "seconds_per_attempt": round(sum(o["seconds"] for o in outs) / n, 1) if n else None,
                "tokens_per_attempt": round(sum(o["tokens"] for o in outs) / n) if n else None,
                "calls": len(calls), "call_errors": sum(1 for c in calls if c.get("error")),
                "usd_total": round(sum(c["usd"] for c in calls), 4),
                "write_tps": round(sum(tps) / len(tps), 1) if tps else None}

    def profile(self, model_id: str) -> dict:
        kinds = sorted({o["task_kind"] for o in self.outcomes(model_id)})
        return {"overall": self.stats(model_id), "by_task_kind": {k: self.stats(model_id, k) for k in kinds}}

    def snapshot(self) -> list[dict]:
        out = []
        for m in self.models():
            ok, why = self.availability(m)
            out.append({**{k: v for k, v in m.items() if k != "api_key_env" or v}, "available": ok,
                        "availability": why, "performance": self.profile(m["id"])})
        return out
