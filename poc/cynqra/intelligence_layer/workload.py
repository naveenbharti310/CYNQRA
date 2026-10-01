"""Workload contracts used by intelligence selection.

A WorkloadContract describes what the worker is actually being asked to do.
It is deterministic platform metadata, not a model's recommendation.
"""
from __future__ import annotations

from . import contracts


_REQUIRED = {
    "document": ("structured_output",),
    "decision": ("reasoning",),
    "code": ("code_generation",),
    "forecast": ("code_generation", "reasoning"),
    "review_merge": ("reasoning", "code_generation"),
    "deploy": ("reasoning",),
    "assign": ("structured_output", "reasoning"),
    "review": ("reasoning",),
    "answer": ("reasoning",),
    "objective": ("structured_output", "reasoning"),
    "plan": ("structured_output", "reasoning"),
}


def compile_contract(task: dict, *, context_tokens: int = 8192) -> dict:
    kind = str(task.get("kind") or "objective")
    risk = contracts.TASK_RISK.get(kind, "LOW")
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
