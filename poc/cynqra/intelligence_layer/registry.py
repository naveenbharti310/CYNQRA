"""The Intelligence Registry: what each available intelligence is, and how well it has actually performed.

It answers "what is this intelligence and how well does it perform?", never "which secret reaches it": an entry
names the provider connection that offers it, and holds no endpoint, no key and no worker.

An entry is registered by discovery (a provider connection lists what it offers) or by hand, with the facts the
provider states: provider, model name and version, capabilities (context, tool calling, structured output,
modalities, MCP), cost, licence, hardware. Scores are never typed in. What an intelligence is good at is learned
only from Cynqra's own work: every call is metered (tokens, seconds, dollars, speed, errors) and every
verification of an attempt at a task is an outcome for the intelligence that did it, on that kind of work. The
Intelligence Router reads these to choose, and the Replacement Engine to reassign.

Lifecycle: a new intelligence, or a new version of one, is "unverified" until its calibration work passes
(probe.py); a failed regression check, repeated call failures (down for ten minutes after two in a row), an
unreachable connection or retirement makes it unavailable to the Router. fallback_id names the intelligence to
prefer when this one fails. Faults, for proving replacement on real models: offline and max_reply.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Callable

from ..db import now
from .contracts import SupplyError

DOWN_AFTER_ERRORS = 2  # consecutive failed calls before an intelligence counts as unavailable
DOWN_FOR_S = 600  # how long it is left untried the first time it goes down
# Each time it goes down again without having answered in between, the wait doubles, to at most an hour: a provider
# still limiting calls after one wait is likely to keep doing so. On a fixed wait, real run 36972596704 moved seven
# workers back to a rate-limited model three times, and each time it refused again within two minutes.
DOWN_MAX_S = 3600
# An overloaded model (HTTP 503 or 529, "high demand") lacks capacity for a moment; it has not gone away. It is left
# untried a minute, doubling to five, not ten doubling to an hour: paid run 37589136743 lost an hour of one objective
# waiting out Google's "high demand" on preview models as if they had gone down
OVERLOAD_DOWN_S = 60
OVERLOAD_MAX_S = 300
_OVERLOAD = re.compile(r"HTTP (503|529)\b|high demand|overloaded", re.I)
FACTS = ("name", "provider", "ref", "runtime", "version", "context", "tools", "json_schema", "modalities", "mcp",
         "local", "price_in", "price_out", "compute_usd_per_hour", "license", "commercial_use", "params", "hardware",
         "size_gb", "predict", "think", "served_by", "released",
         # normalized at discovery (normalize.py): who made it, who serves it, what it can do
         "display_name", "publisher", "publisher_name", "capabilities", "input_modalities", "type", "speed", "description",
         "max_output", "list_price_in", "list_price_out", "access_provider", "access_type", "rate_limit_per_min",
         "catalogued", "price_source")


def served_version(m: dict) -> str:
    """What was actually measured and what a binding pins: the model's version and, for intelligence reached through
    an aggregator (Hugging Face's router), the company serving it. The same model served by another company can
    differ in speed, price and quantization, so a change of either is a change of version: a worker continues on it
    only after its regression check, and its evidence is kept apart."""
    v, sb = str(m.get("version") or ""), str(m.get("served_by") or "")
    return f"{v}@{sb}" if sb else v


class RegistryError(SupplyError):
    pass


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "model"


class IntelligenceRegistry:
    def __init__(self, store, reachable: Callable[[dict], tuple[bool, str]]):
        self.store = store
        self.reachable = reachable  # asked of the intelligence's provider connection; the registry holds none
        self.lock = threading.RLock()

    # --- entries ---------------------------------------------------------------------------------------------
    def models(self, include_retired: bool = False) -> list[dict]:
        return [m for m in self.store.all("intelligence") if include_retired or m.get("status") != "retired"]

    def get(self, model_id: str) -> dict:
        """An entry, retired or not: a worker may still be bound to a retired intelligence until the Replacement
        Engine moves it, and its record is kept. Whether it may be called is availability's answer."""
        m = self.store.get("intelligence", model_id)
        if m is None:
            raise RegistryError(f"no intelligence {model_id!r} in the registry")
        return m

    def register(self, facts: dict, connection_id: str, source: str = "discovered") -> dict:
        """Add or refresh an intelligence offered by a connection. Its measured record is kept across refreshes; a
        new version starts unverified again."""
        ref = str(facts.get("ref") or "").strip()
        if not ref:
            raise RegistryError("an intelligence needs the provider's name for it (ref)")
        with self.lock:
            old = next((m for m in self.store.all("intelligence")
                        if m.get("connection_id") == connection_id and m.get("ref") == ref), None)
            mid = old["id"] if old else self._new_id(str(facts.get("name") or ref), connection_id)
            m = {"id": mid, "connection_id": connection_id, "source": source, "version": "", "context": 0,
                 "tools": False, "json_schema": True, "modalities": ["text"], "mcp": False, "local": False,
                 "price_in": 0.0, "price_out": 0.0, "compute_usd_per_hour": 0.0, "license": "", "commercial_use": "",
                 "params": "", "hardware": "", "provider": "", "runtime": "", "capabilities": [], "fallback_id": (old or {}).get("fallback_id", "")}
            m.update({k: facts[k] for k in FACTS if facts.get(k) not in (None, "")})
            m["ref"], m["name"] = ref, str(m.get("name") or ref)
            for k in ("price_in", "price_out", "compute_usd_per_hour"):
                m[k] = float(m[k] or 0)
            m["context"] = int(m["context"] or 0)
            same = old is not None and served_version(old) == served_version(m)
            regression = (old or {}).get("regression") if same and (old or {}).get("regression") else {
                "status": "unverified", "version": served_version(m), "at": now(),
                "previous_version": served_version(old) if old and not same else None}
            if m.get("runtime") == "scripted":  # a replay of a prepared script has no version to check
                regression = {"status": "not applicable", "version": "", "at": now(), "previous_version": None}
            m.update({"status": "active", "status_note": "", "fault": (old or {}).get("fault") or {},
                      "health": (old or {}).get("health") or {"errors": 0, "down_until": 0},
                      "registered_at": (old or {}).get("registered_at") or now(), "regression": regression})
            self.store.put("intelligence", mid, m)
            if old is None or not same:
                self._audit("intelligence.registered", mid, {"model": m["name"], "provider": m["provider"],
                            "connection_id": connection_id, "version": m["version"], "source": source,
                            "served_by": m.get("served_by") or "",
                            "previous": served_version(old) if old else None})
            return m

    def _new_id(self, name: str, connection_id: str) -> str:
        mid = slug(name)
        taken = self.store.get("intelligence", mid)
        return mid if taken is None or taken.get("connection_id") == connection_id else f"{mid}-{connection_id[-4:]}"

    def retire(self, model_id: str, why: str) -> None:
        with self.lock:
            m = self.store.get("intelligence", model_id)
            if m is None:
                return
            m.update({"status": "retired", "status_note": why})
            self.store.put("intelligence", model_id, m)
            self._audit("intelligence.retired", model_id, {"why": why[:200]})

    def set_fallback(self, model_id: str, fallback_id: str) -> dict:
        with self.lock:
            m = self.get(model_id)
            if fallback_id:
                self.get(fallback_id)
                if fallback_id == model_id:
                    raise RegistryError("an intelligence cannot be its own fallback")
            m["fallback_id"] = fallback_id or ""
            self.store.put("intelligence", model_id, m)
            return m

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
            self.store.put("intelligence", model_id, m)
            self._audit("intelligence.fault_set", model_id, {"fault": m["fault"]})
            return m

    # --- availability ----------------------------------------------------------------------------------------
    def clear_health(self, model_id: str) -> dict:
        """The cause of its failed calls was fixed (the account has credit again, a new key): it may be called."""
        with self.lock:
            m = self.get(model_id)
            m["health"] = {"errors": 0, "down_until": 0}
            self.store.put("intelligence", model_id, m)
            self._audit("intelligence.health_cleared", model_id, {})
            return m

    def availability(self, m: dict) -> tuple[bool, str]:
        """Can a worker bound to this intelligence make a call now? Its own state, its connection's, then the
        global qualification gate: a discovered intelligence is unknown, not usable, until it qualifies. A missing
        key is said before the gate, because nothing can be qualified without it."""
        if m.get("status") == "retired":
            return False, m.get("status_note") or "retired"
        regression = (m.get("regression") or {}).get("status")
        if regression == "failed":
            return False, "failed its regression check"
        h = m.get("health") or {}
        if h.get("down_until", 0) > time.time():
            return False, f"down after {h.get('errors')} failed calls in a row"
        ok, why = self.reachable(m)
        if not ok:
            return ok, why
        if regression == "unverified":
            return False, "not qualified for assignment yet"
        return ok, why

    @staticmethod
    def qualified_for(m: dict, kind: str) -> tuple[bool, str]:
        """Global qualification for one family of work: building work (code) or the rest (structured planning). A
        model that passed one family and failed the other takes part only in the one it passed."""
        reg = m.get("regression") or {}
        if reg.get("status") in ("not applicable",):
            return True, ""
        if reg.get("status") != "passed":
            return False, f"not qualified ({reg.get('status') or 'unverified'})"
        family = "code" if kind in ("code", "forecast") else "objective"
        verdict = (reg.get("by_kind") or {}).get(family)
        if verdict == "failed":
            return False, f"failed its {family} qualification"
        return True, ""

    def available(self) -> list[dict]:
        return [m for m in self.models() if self.availability(m)[0]]

    def cost(self, m: dict, tokens_in: int, tokens_out: int, seconds: float) -> float:
        if m["local"]:
            return round(seconds * float(m.get("compute_usd_per_hour") or 0) / 3600, 6)
        return round(tokens_in * m["price_in"] / 1e6 + tokens_out * m["price_out"] / 1e6, 6)

    # --- measurement -----------------------------------------------------------------------------------------
    def record_call(self, model_id: str, *, role: str, purpose: str, task_kind: str, usage: dict, run_id: str,
                    error: str = "") -> dict:
        """Every call, metered: what it cost and how long it took. A failed call counts toward being down."""
        with self.lock:
            m = self.store.get("intelligence", model_id)
            if m is None:
                raise RegistryError(f"no intelligence {model_id!r} in the registry")
            secs = float(usage.get("latency_s") or 0)
            tin, tout = int(usage.get("tokens_in") or 0), int(usage.get("tokens_out") or 0)
            c = {"id": f"c_{self.store.next_id('call'):06d}", "model_id": model_id, "role": role, "purpose": purpose,
                 "task_kind": task_kind, "run_id": run_id, "tokens_in": tin, "tokens_out": tout,
                 "seconds": round(secs, 1), "usd": self.cost(m, tin, tout, secs), "write_tps": usage.get("write_tps"),
                 "error": error[:300], "served_by": m.get("served_by") or "", "model_version": served_version(m),
                 "tenant_id": usage.get("tenant_id") or "local", "at": now()}
            self.store.put("call", c["id"], c)
            h = m.get("health") or {"errors": 0, "down_until": 0}
            h["errors"] = h.get("errors", 0) + 1 if error else 0
            if h["errors"] >= DOWN_AFTER_ERRORS and h.get("down_until", 0) <= time.time():
                # it goes down (again): a call in flight that fails while it is down changes nothing
                h["trips"] = int(h.get("trips") or 0) + 1
                first, most = (OVERLOAD_DOWN_S, OVERLOAD_MAX_S) if _OVERLOAD.search(error) else (DOWN_FOR_S, DOWN_MAX_S)
                h["down_until"] = time.time() + min(most, first * 2 ** (h["trips"] - 1))
            elif not error:  # it answered: it is up, whatever the last failures said
                h.update(down_until=0, trips=0)
            m["health"] = h
            self.store.put("intelligence", model_id, m)
            return c

    def record_outcome(self, model_id: str, *, role: str, task_kind: str, task_id: str, run_id: str, attempt: int,
                       verified: bool, usd: float, seconds: float, tokens: int, failure: str = "",
                       source: str = "project", tenant_id: str = "local", objective_id: str | None = None,
                       objective_version: int | None = None, attribution: str | None = None,
                       model_version: str | None = None, workspace_id: str = "local") -> dict:
        """One verification of one attempt at a task: the unit Cynqra learns from. Every outcome names its tenant
        and workspace, so another tenant's (or, by the isolation policy, another workspace's) work never becomes this
        one's evidence, and the version that actually did the work."""
        with self.lock:
            version = model_version if model_version is not None else \
                served_version(self.store.get("intelligence", model_id) or {})
            o = {"id": f"o_{self.store.next_id('outcome'):06d}", "model_id": model_id, "model_version": version,
                 "role": role, "task_kind": task_kind, "task_id": task_id, "run_id": run_id, "attempt": attempt,
                 "verified": bool(verified), "first_pass": bool(verified and attempt == 1), "usd": round(usd, 6),
                 "seconds": round(seconds, 1), "tokens": int(tokens), "failure": failure[:400], "source": source,
                 "tenant_id": tenant_id or "local", "workspace_id": workspace_id or "local",
                 "objective_id": objective_id, "objective_version": objective_version,
                 "attribution": attribution or ("intelligence" if not verified else None), "clean": True,
                 "at": now()}
            self.store.put("outcome", o["id"], o)
            return o

    def set_regression(self, model_id: str, passed: bool, evidence: str, by_kind: dict | None = None) -> dict:
        """Settle the global qualification gate for the current served version. by_kind: the verdict per family of
        work ({"objective": "passed", "code": "failed"}): it takes part only in the families it passed."""
        with self.lock:
            m = self.get(model_id)
            m["regression"] = {"status": "passed" if passed else "failed", "version": served_version(m),
                               "at": now(), "evidence": evidence[:300]}
            if by_kind:
                m["regression"]["by_kind"] = {k: v for k, v in by_kind.items() if v in ("passed", "failed")}
            self.store.put("intelligence", model_id, m)
            self._audit("intelligence.regression_checked", model_id, {"passed": passed, "evidence": evidence[:200],
                        "version": served_version(m)})
            return m

    def _n(self, kind: str) -> int:
        return len(self.store.all(kind))

    def outcomes(self, model_id: str | None = None, task_kind: str | None = None,
                 tenant_id: str | None = None) -> list[dict]:
        return [o for o in self.store.all("outcome") if (model_id is None or o["model_id"] == model_id)
                and (task_kind is None or o["task_kind"] == task_kind)
                and (tenant_id is None or (o.get("tenant_id") or "local") == tenant_id)]

    def calls(self, model_id: str | None = None) -> list[dict]:
        return [c for c in self.store.all("call") if model_id is None or c["model_id"] == model_id]

    def stats(self, model_id: str, task_kind: str | None = None) -> dict:
        """Measured performance: attempts verified, first-pass rate, cost and time per attempt, speed, reliability."""
        outs = self.outcomes(model_id, task_kind)
        calls = self.calls(model_id)
        sb = (self.store.get("intelligence", model_id) or {}).get("served_by")
        if sb:  # evidence belongs to the company that served it: another company's record is not this one's
            outs = [o for o in outs if str(o.get("model_version") or "").endswith("@" + sb)]
            calls = [c for c in calls if c.get("served_by") == sb]
        n = len(outs)
        ok = sum(1 for o in outs if o["verified"])
        tasks = {(o["run_id"], o["task_id"]) for o in outs}
        first = sum(1 for o in outs if o["first_pass"])
        firsts = {(o["run_id"], o["task_id"]) for o in outs if o["attempt"] == 1}
        tps = [c["write_tps"] for c in calls if c.get("write_tps")]
        errors = sum(1 for c in calls if c.get("error"))
        return {"attempts": n, "verified": ok, "tasks": len(tasks),
                "success_rate": round(ok / n, 3) if n else None,
                "first_pass_rate": round(first / len(firsts), 3) if firsts else None,
                "usd_per_attempt": round(sum(o["usd"] for o in outs) / n, 4) if n else None,
                "seconds_per_attempt": round(sum(o["seconds"] for o in outs) / n, 1) if n else None,
                "tokens_per_attempt": round(sum(o["tokens"] for o in outs) / n) if n else None,
                "calls": len(calls), "call_errors": errors,
                "reliability": round(1 - errors / len(calls), 3) if calls else None,
                "latency_s": round(sum(c["seconds"] for c in calls) / len(calls), 1) if calls else None,
                "usd_total": round(sum(c["usd"] for c in calls), 4),
                "write_tps": round(sum(tps) / len(tps), 1) if tps else None}

    def profile(self, model_id: str) -> dict:
        """Measured record: overall, per kind of work (its suitability), the benchmark (calibration and regression
        work outside projects) and the record per version."""
        outs = self.outcomes(model_id)
        kinds = sorted({o["task_kind"] for o in outs})
        bench = [o for o in outs if o.get("source") in ("probe", "regression")]
        by_version: dict[str, list] = {}
        for o in outs:
            by_version.setdefault(o.get("model_version") or "", []).append(o["verified"])
        return {"overall": self.stats(model_id), "by_task_kind": {k: self.stats(model_id, k) for k in kinds},
                "benchmark": {k: {"attempts": sum(1 for o in bench if o["task_kind"] == k),
                                  "verified": sum(1 for o in bench if o["task_kind"] == k and o["verified"])}
                              for k in sorted({o["task_kind"] for o in bench})},
                "by_version": {v: {"attempts": len(x), "verified": sum(x)} for v, x in by_version.items()}}

    def snapshot(self) -> list[dict]:
        out = []
        for m in self.models():
            ok, why = self.availability(m)
            out.append({**m, "available": ok, "availability": why, "performance": self.profile(m["id"])})
        return out

    def _audit(self, event_type: str, model_id: str, payload: dict) -> None:
        self.store.append(company_id="control_plane", event_type=event_type, aggregate_type="intelligence",
                          aggregate_id=model_id, actor_type="service", actor_id="intelligence_registry",
                          payload=payload, correlation_id=model_id)
