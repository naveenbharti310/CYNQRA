"""Worker intelligence bindings: which intelligence powers each worker now, and every change to that.

A worker is a persistent organizational identity (role, authority, reporting line, responsibilities, task ownership,
history). Its intelligence is replaceable, so the worker record holds none of it; the binding does:

    worker ── binding ──▶ intelligence (registry entry, pinned version) ──▶ provider connection ──▶ credential

A binding is made by the Intelligence Router at staffing, and changed by the Replacement Engine (replace, fallback,
a new version that passed its regression check) or refined when the roadmap's workload is known. Each change keeps
the previous binding in the history and is an event in the run's audit trail. Changing the intelligence never
creates a new worker.

"system" is the control plane's own work that belongs to no worker: structuring the objective and synthesizing the
workforce.
"""
from __future__ import annotations

from .db import now
from .intelligence_layer.registry import served_version

SYSTEM = "system"


def current(store, worker_id: str) -> dict | None:
    return store.get("binding", worker_id)


def intelligence_of(store, worker_id: str) -> str | None:
    return (store.get("binding", worker_id) or {}).get("intelligence_id")


def all_bindings(store) -> dict[str, dict]:
    return {b["worker_id"]: b for b in store.all("binding")}


def bind(run, worker_id: str, entry: dict, *, reason: str, by: str, candidates: list | None = None,
         task_id: str | None = None) -> dict:
    """Bind a worker to an intelligence (a registry entry), pinning its current version."""
    old = current(run.store, worker_id)
    if old and old["intelligence_id"] == entry["id"] and old.get("version") == served_version(entry):
        return old
    history = list((old or {}).get("history") or [])
    epoch = int((old or {}).get("epoch") or 0) + 1
    profile_id = entry.get("execution_profile_id")
    binding_epoch_id = f"be_{worker_id}_{epoch}"
    if old:
        history.append({k: old.get(k) for k in (
            "worker_id", "intelligence_id", "intelligence", "version", "execution_profile_id",
            "binding_epoch_id", "epoch", "reason", "by", "bound_at")})
    epoch_record = {
        "id": binding_epoch_id,
        "worker_id": worker_id,
        "epoch": epoch,
        "intelligence_id": entry["id"],
        "execution_profile_id": profile_id,
        "version": served_version(entry),
        "previous_binding_epoch_id": (old or {}).get("binding_epoch_id"),
        "bound_at": now(),
        "reason": reason[:400],
        "by": by,
    }
    run.store.put("binding_epoch", binding_epoch_id, epoch_record)
    b = {"worker_id": worker_id, "intelligence_id": entry["id"], "intelligence": entry["name"],
         "version": served_version(entry), "execution_profile_id": profile_id,
         "binding_epoch_id": binding_epoch_id, "epoch": epoch,
         "reason": reason[:400], "by": by,
         "candidates": candidates if candidates is not None else (old or {}).get("candidates", []),
         "bound_at": epoch_record["bound_at"], "history": history}
    run.store.put("binding", worker_id, b)
    role = (run.worker(worker_id) or {}).get("role", "control plane")
    run.event("worker.intelligence_bound", "worker", worker_id, {
        "role": role, "intelligence_id": entry["id"], "model": entry["name"], "version": b["version"],
        "execution_profile_id": profile_id, "binding_epoch_id": binding_epoch_id, "epoch": epoch,
        "previous": (old or {}).get("intelligence_id"), "reason": reason[:200], "by": by,
        "candidates": [{k: r.get(k) for k in ("model", "score", "p_task", "expected_usd", "expected_minutes")}
                       for r in (candidates or [])]},
        actor=by, correlation_id=task_id or worker_id)
    return b
