"""Worker intelligence bindings: which intelligence powers each worker now, and every change to that.

A worker is a persistent organizational identity (role, authority, reporting line, responsibilities, task ownership,
history). Its intelligence is replaceable, so the worker record holds none of it; the binding does:

    worker ── binding ──▶ intelligence (registry entry, pinned version) ──▶ provider connection ──▶ credential

Two kinds of binding, both versioned and both made by a persisted selection decision (controller.py):

  worker binding   the intelligence for the worker's work in general: its coordination, its answers to Blockers
                   and any task that has no binding of its own
  work binding     the intelligence for one task: the same worker can do different tasks on different intelligence
                   when the evidence for each piece of work says so

The newest decision wins: a work binding made after the worker's binding governs that task; a worker binding made
later (a replacement, a stand-in while a provider is down, the return to its own AI) governs every task of the worker
until the task is decided again. Each change keeps the previous binding in the history, carries its decision, the
objective version and the evidence version it was decided against, and is an event in the run's audit trail.
A binding is written with a compare-and-set on its version, so two concurrent workers can never silently overwrite
one another's binding (db.ConcurrencyError). Changing the intelligence never creates a new worker.

"system" is the control plane's own work that belongs to no worker: structuring the objective and synthesizing the
workforce.
"""
from __future__ import annotations

from .db import ConcurrencyError, now
from .intelligence_layer.registry import RegistryError, served_version

SYSTEM = "system"
HISTORY_KEYS = ("intelligence_id", "intelligence", "version", "reason", "by", "bound_at", "decision_id", "_v", "seq")


def current(store, worker_id: str) -> dict | None:
    return store.get("binding", worker_id)


def intelligence_of(store, worker_id: str) -> str | None:
    return (store.get("binding", worker_id) or {}).get("intelligence_id")


def all_bindings(store) -> dict[str, dict]:
    return {b["worker_id"]: b for b in store.all("binding")}


def task_binding(store, task_id: str) -> dict | None:
    return store.get("work_binding", task_id)


def all_task_bindings(store) -> dict[str, dict]:
    return {b["task_id"]: b for b in store.all("work_binding")}


def _decision(run, kind: str, key: str, worker_id: str, entry: dict, reason: str, by: str, candidates, task_id):
    from . import controller  # a binding without a decision gets one: no binding exists unexplained
    return controller.record_direct(run, target_kind=kind, target_id=key, worker_id=worker_id, entry=entry,
                                    reason=reason, by=by, rows=candidates, task_id=task_id)


def _write(run, kind: str, key: str, b: dict, old: dict | None, expected_version: int | None) -> dict:
    have = int((old or {}).get("_v") or 0)
    if expected_version is not None and have != int(expected_version):
        raise ConcurrencyError(f"{kind} {key} is at version {have}, not {expected_version}: decided against a binding "
                               "that has changed since")
    b["_v"] = have + 1
    b["seq"] = run.store.next_seq("binding")
    run.store.put(kind, key, b)
    return b


def bind(run, worker_id: str, entry: dict, *, reason: str, by: str, candidates: list | None = None,
         task_id: str | None = None, decision: dict | None = None, expected_version: int | None = None) -> dict:
    """Bind a worker to an intelligence (a registry entry), pinning its current version."""
    with run.store.atomic():
        old = current(run.store, worker_id)
        if old and old["intelligence_id"] == entry["id"] and old.get("version") == served_version(entry):
            return old
        if decision is None:
            decision = _decision(run, "binding", worker_id, worker_id, entry, reason, by, candidates, task_id)
        history = list((old or {}).get("history") or [])
        if old:
            history.append({k: old.get(k) for k in HISTORY_KEYS})
        b = {"worker_id": worker_id, "intelligence_id": entry["id"], "intelligence": entry["name"],
             "version": served_version(entry), "reason": reason[:400], "by": by,
             "candidates": candidates if candidates is not None else (old or {}).get("candidates", []),
             "decision_id": decision["decision_id"], "objective_id": decision.get("objective_id"),
             "objective_version": decision.get("objective_version"), "work_item_id": decision.get("work_item_id"),
             "evidence_version": decision.get("evidence_version"), "expected_usd": decision.get("expected_cost"),
             "expected_minutes": decision.get("expected_latency_minutes"), "bound_at": now(), "history": history}
        b = _write(run, "binding", worker_id, b, old, expected_version)
    role = (run.worker(worker_id) or {}).get("role", "control plane")
    run.event("worker.intelligence_bound", "worker", worker_id, {
        "role": role, "intelligence_id": entry["id"], "model": entry["name"], "version": b["version"],
        "previous": (old or {}).get("intelligence_id"), "reason": reason[:200], "by": by,
        "candidates": [{k: r.get(k) for k in ("model", "score", "p_task", "expected_usd", "expected_minutes")}
                       for r in (candidates or [])]},
        actor=by, correlation_id=task_id or worker_id)
    run.event("worker.bound", "binding", worker_id, {"scope": "worker", "intelligence_id": entry["id"],
              "version": b["version"], "decision_id": b["decision_id"], "binding_version": b["_v"],
              "previous": (old or {}).get("intelligence_id"), "worker_identity_unchanged": True},
              actor=by, correlation_id=task_id or worker_id)
    return b


def bind_task(run, task_id: str, worker_id: str, entry: dict, *, reason: str, by: str, decision: dict | None = None,
              candidates: list | None = None, expected_version: int | None = None) -> dict:
    """Bind one task's work to an intelligence. The worker who owns the task does not change."""
    with run.store.atomic():
        old = task_binding(run.store, task_id)
        if decision is None:
            decision = _decision(run, "work_binding", task_id, worker_id, entry, reason, by, candidates, task_id)
        history = list((old or {}).get("history") or [])
        if old:
            history.append({k: old.get(k) for k in HISTORY_KEYS} | {"worker_id": old.get("worker_id")})
        t = run.store.get("task", task_id) or {}
        b = {"task_id": task_id, "worker_id": worker_id, "intelligence_id": entry["id"], "intelligence": entry["name"],
             "version": served_version(entry), "reason": reason[:400], "by": by,
             "candidates": candidates or [], "decision_id": decision["decision_id"],
             "objective_id": decision.get("objective_id"), "objective_version": decision.get("objective_version"),
             "task_kind": t.get("kind"), "acceptance_hash": t.get("acceptance_hash"),
             "evidence_version": decision.get("evidence_version"), "expected_usd": decision.get("expected_cost"),
             "expected_minutes": decision.get("expected_latency_minutes"), "bound_at": now(), "history": history}
        b = _write(run, "work_binding", task_id, b, old, expected_version)
    run.event("worker.bound", "binding", task_id, {"scope": "task", "task_id": task_id, "worker_id": worker_id,
              "intelligence_id": entry["id"], "version": b["version"], "decision_id": b["decision_id"],
              "binding_version": b["_v"], "previous": (old or {}).get("intelligence_id"),
              "worker_identity_unchanged": True}, actor=by, correlation_id=task_id)
    return b


def effective(run, worker_id: str, task_id: str | None) -> tuple[str, str] | None:
    """The intelligence that does this worker's work on this task now, at its pinned version: the newest decision
    of the task's binding and the worker's binding, when it can be called; else the other one."""
    wb = current(run.store, worker_id)
    tb = task_binding(run.store, task_id) if task_id else None
    if tb is not None and tb.get("worker_id") != worker_id:
        tb = None  # the task moved to another worker since; its binding was for the one before
    options = sorted([b for b in (tb, wb) if b], key=lambda b: -int(b.get("seq") or 0))
    for b in options:
        try:
            if run.registry.availability(run.registry.get(b["intelligence_id"]))[0]:
                return b["intelligence_id"], b.get("version")
        except (RegistryError, AttributeError):
            continue
    return (options[0]["intelligence_id"], options[0].get("version")) if options else None
