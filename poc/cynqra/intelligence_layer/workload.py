"""Workload contracts used by intelligence selection.

A WorkloadContract describes what the worker is actually being asked to do.
It is deterministic platform metadata, not a model's recommendation.
"""
from __future__ import annotations

from .. import roles


_REQUIRED = {
    "document": ("structured_output",),
    "decision": ("reasoning",),
    "code": ("coding",),
    "forecast": ("coding", "reasoning"),
    "review_merge": ("reasoning", "coding"),
    "deploy": ("reasoning",),
    "assign": ("structured_output", "reasoning"),
    "review": ("reasoning",),
    "answer": ("reasoning",),
    "objective": ("structured_output", "reasoning"),
    "plan": ("structured_output", "reasoning"),
}


def compile_contract(task: dict, *, context_tokens: int = 8192) -> dict:
    kind = str(task.get("kind") or "objective")
    risk = roles.TASK_TYPES.get(kind, {}).get("risk", "LOW")
    return {
        "kind": kind,
        "objective": str(task.get("title") or kind),
        "required_capabilities": list(_REQUIRED.get(kind, ("reasoning",))),
        "min_context_tokens": max(1024, int(context_tokens)),
        "risk": risk,
        "verification": str(task.get("verification_gate") or ""),
        "acceptance": list(task.get("acceptance_criteria") or []),
        "policy": str(task.get("authority_policy_id") or ""),
    }
