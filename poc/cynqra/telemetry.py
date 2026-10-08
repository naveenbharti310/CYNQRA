"""OpenTelemetry traces of a run's model calls and selection decisions (R6 of the architecture review).

Each run writes traces.jsonl in its own folder: one OTLP/JSON export request per line (the OpenTelemetry Collector's
file format), so the run can be loaded into any OpenTelemetry backend (Jaeger, Grafana Tempo, Honeycomb, Langfuse,
Datadog) as it is, with no SDK and no network. A model call is a client span named and attributed by the GenAI
semantic conventions (gen_ai.operation.name, gen_ai.provider.name, gen_ai.request.model, gen_ai.usage.*, error.type);
a selection decision is an internal span. Every span of one task shares the task's trace, and the run's own work
(the objective, the plan) shares the run's.

Only measurements leave the call: no prompt, no reply, no credential (an error message is scrubbed).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path

from .db import scrub

SCOPE = {"name": "cynqra", "version": "p1"}
CLIENT, INTERNAL = 3, 1  # SpanKind
OK, ERROR = 1, 2  # Status code
_LOCK = threading.Lock()


def trace_id(run_id: str, task_id: str | None) -> str:
    return hashlib.sha256(f"{run_id}|{task_id or 'run'}".encode()).hexdigest()[:32]


def _span_id() -> str:
    return os.urandom(8).hex()


def _value(v) -> dict:
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    return {"stringValue": str(v)}


def _attrs(d: dict) -> list[dict]:
    return [{"key": k, "value": _value(v)} for k, v in d.items() if v is not None and v != ""]


def _write(path: Path | None, span: dict, run_id: str) -> None:
    if path is None:
        return
    line = {"resourceSpans": [{"resource": {"attributes": _attrs({"service.name": "cynqra", "cynqra.run_id": run_id})},
                               "scopeSpans": [{"scope": SCOPE, "spans": [span]}]}]}
    try:
        with _LOCK, open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, separators=(",", ":")) + "\n")
    except OSError:  # a trace that cannot be written never stops the work
        pass


def provider_name(entry: dict) -> str:
    """gen_ai.provider.name: the well-known value where the convention names one, else the access provider."""
    text = " ".join(str(entry.get(k) or "") for k in ("access_type", "access_provider", "provider", "ref")).lower()
    for needle, name in (("gemini", "gcp.gemini"), ("google", "gcp.gemini"), ("anthropic", "anthropic"),
                         ("claude", "anthropic"), ("openai", "openai"), ("mistral", "mistral_ai"), ("groq", "groq"),
                         ("deepseek", "deepseek"), ("nvidia", "nvidia"), ("ollama", "ollama")):
        if needle in text:
            return name
    return str(entry.get("access_provider") or entry.get("provider") or "unknown")


def call(path: Path | None, *, run_id: str, task_id: str | None, worker_id: str | None, entry: dict, request: dict,
         out: dict | None, start_ns: int, end_ns: int, error: str = "") -> None:
    """One model call as a GenAI client span."""
    out = out or {}
    model = str(entry.get("ref") or entry.get("name") or "")
    err = error or str(out.get("error") or "")
    attrs = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": provider_name(entry),
        "gen_ai.request.model": model,
        "gen_ai.response.model": str(out.get("model") or "") or None,
        "gen_ai.request.max_tokens": int(request.get("max_tokens") or 0) or None,
        "gen_ai.request.temperature": float(request["temperature"]) if request.get("temperature") is not None else None,
        "gen_ai.usage.input_tokens": int(out.get("tokens_in") or 0),
        "gen_ai.usage.output_tokens": int(out.get("tokens_out") or 0),
        "gen_ai.usage.cache_read.input_tokens": int(out.get("tokens_cached") or 0),
        "error.type": (err.split(":", 1)[0].strip() or "error") if err else None,
        "cynqra.task_id": task_id, "cynqra.worker_id": worker_id, "cynqra.intelligence_id": entry.get("id"),
        "cynqra.effort": request.get("effort"), "cynqra.journaled": bool(out.get("journaled")),
        "cynqra.tokens_estimated": bool(out.get("estimated")),
    }
    span = {"traceId": trace_id(run_id, task_id), "spanId": _span_id(), "name": f"chat {model}", "kind": CLIENT,
            "startTimeUnixNano": str(start_ns), "endTimeUnixNano": str(end_ns), "attributes": _attrs(attrs),
            "status": {"code": ERROR, "message": scrub(err)[:300]} if err else {"code": OK}}
    _write(path, span, run_id)


def decision(path: Path | None, *, run_id: str, rec: dict, at_ns: int) -> None:
    """One selection decision as an internal span in its work item's trace."""
    sel = rec.get("selected_intelligence") or {}
    task = rec.get("work_item_id") if str(rec.get("work_item_id") or "").startswith("t_") else None
    attrs = {"cynqra.decision_id": rec.get("decision_id"), "cynqra.purpose": rec.get("purpose"),
             "cynqra.work_item_id": rec.get("work_item_id"), "cynqra.selection_mode": rec.get("selection_mode"),
             "cynqra.selected": sel.get("id"), "cynqra.candidates": len(rec.get("candidate_set") or []),
             "cynqra.eligible": len(rec.get("eligible_candidates") or []),
             "cynqra.policy_version": rec.get("selection_policy_version"),
             "cynqra.evidence_version": rec.get("evidence_version")}
    span = {"traceId": trace_id(run_id, task), "spanId": _span_id(), "name": f"select {rec.get('purpose') or ''}".strip(),
            "kind": INTERNAL, "startTimeUnixNano": str(at_ns), "endTimeUnixNano": str(at_ns),
            "attributes": _attrs(attrs), "status": {"code": OK}}
    _write(path, span, run_id)
