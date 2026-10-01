"""Qualification Engine for real CYNQRA intelligence.

Discovery is only discovery. A model becomes assignable after CYNQRA has produced
current, workload-relevant evidence for its exact execution profile.
"""
from __future__ import annotations

from ..db import digest, now
from ..intelligence import IntelligenceError
from ..probe import _Run, probe
from .identity import ensure_identity


class QualificationError(RuntimeError):
    pass


class QualificationEngine:
    def __init__(self, supply):
        self.supply = supply
        self.registry = supply.registry

    def eligibility(self, model_id: str, workload: dict | None = None) -> dict:
        m = self.registry.get(model_id)
        required = set((workload or {}).get("required_capabilities") or [])
        available = {str(x).lower() for x in (m.get("capabilities") or [])}
        missing = sorted(required - available) if available else []
        context = int(m.get("context") or 0)
        need = int((workload or {}).get("min_context_tokens") or 8192)
        ok = not missing and (not context or context >= need)
        return {
            "model_id": model_id,
            "execution_profile_id": m.get("execution_profile_id"),
            "eligible": ok,
            "missing_capabilities": missing,
            "context": context,
            "required_context": need,
        }

    def _save(self, model_id: str, status: str, depth: str, workload_kind: str, evidence: dict) -> dict:
        m = self.registry.get(model_id)
        qid = f"qual_{digest({'model_id': model_id, 'profile': m.get('execution_profile_id'), 'depth': depth, 'kind': workload_kind, 'at': now()})[:24]}"
        q = {
            "id": qid,
            "model_id": model_id,
            "execution_profile_id": m.get("execution_profile_id"),
            "model_version": m.get("version") or "",
            "workload_kind": workload_kind,
            "depth": depth,
            "status": status,
            "evidence": evidence,
            "at": now(),
        }
        self.supply.store.put("qualification", qid, q)
        self.supply.store.put_object("qualification", q)
        return q

    def cheap_probe(self, model_id: str, workload_kind: str = "objective") -> dict:
        """One real structured call. Cheap probe never makes the model assignable by itself."""
        elig = self.eligibility(model_id, {"kind": workload_kind})
        if not elig["eligible"]:
            return self._save(model_id, "ineligible", "cheap", workload_kind, elig)

        run = _Run(self.supply, model_id, "qualification_cheap")
        try:
            ok, info = run.objective(lambda _msg: None)
        except IntelligenceError as exc:
            return self._save(model_id, "failed", "cheap", workload_kind, {"error": str(exc), "usd": run.usd})
        return self._save(model_id, "candidate" if ok else "failed", "cheap", workload_kind,
                          {"objective_passed": ok, "filled": info["filled"], "usd": run.usd})

    def deep_probe(self, model_id: str, log=lambda _msg: None) -> dict:
        """Run the existing real objective+code qualification suite and record exact-profile evidence."""
        result = probe(self.supply, model_id, log=log)
        status = "qualified" if result.get("passed") else "failed"
        return self._save(model_id, status, "deep", "mixed", {
            "passed": bool(result.get("passed")),
            "objective_passed": bool(result.get("objective_passed")),
            "code_passed": bool(result.get("code_passed")),
            "usd": sum(float(x.get("usage", {}).get("tokens_in", 0) or 0) * 0 for x in result.get("code_rounds", [])),
            "profile": result.get("performance"),
        })

    def qualify(self, model_id: str, *, deep: bool = False, log=lambda _msg: None) -> dict:
        m = self.registry.get(model_id)
        entry = ensure_identity(self.supply.store, m,
                                self.supply.connections.get(m["connection_id"]))
        m.update(entry)
        self.supply.store.put("intelligence", model_id, m)
        cheap = self.cheap_probe(model_id)
        if not deep or cheap.get("status") != "candidate":
            return cheap
        return self.deep_probe(model_id, log=log)

    def history(self, model_id: str | None = None) -> list[dict]:
        rows = self.supply.store.all("qualification")
        return [r for r in rows if model_id is None or r.get("model_id") == model_id]
