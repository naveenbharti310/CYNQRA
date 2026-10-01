"""Immutable intelligence identity records.

An intelligence has three distinct identities:

IntelligenceArtifact
    what the model is, independent of who serves it.

ProviderOffering
    how a particular provider/account exposes that artifact.

ExecutionProfile
    the exact non-secret runtime configuration CYNQRA used for a call.

The records are content addressed. Historical execution points at the exact profile rather
than at a mutable registry row.
"""
from __future__ import annotations

from copy import deepcopy

from ..db import digest, now

_SECRET_WORDS = ("secret", "key", "token", "password", "credential", "authorization")


def _safe(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if any(word in str(k).lower() for word in _SECRET_WORDS):
                continue
            out[str(k)] = _safe(v)
        return out
    if isinstance(value, list):
        return [_safe(v) for v in value]
    return value


def _id(prefix: str, payload: dict) -> str:
    return f"{prefix}_{digest(payload)[:24]}"


def ensure_identity(store, entry: dict, connection: dict) -> dict:
    """Create immutable artifact/offering/profile records and return their ids."""
    publisher = str(entry.get("publisher_name") or entry.get("publisher") or entry.get("provider") or "").strip()
    ref = str(entry.get("ref") or entry.get("name") or "").strip()

    artifact_payload = {
        "publisher": publisher,
        "ref": ref,
        "model_type": entry.get("type") or "chat",
    }
    artifact_id = _id("ia", artifact_payload)
    artifact = store.get("intelligence_artifact", artifact_id)
    if artifact is None:
        artifact = {
            "id": artifact_id,
            **artifact_payload,
            "name": str(entry.get("display_name") or entry.get("name") or ref),
            "created_at": now(),
        }
        store.put("intelligence_artifact", artifact_id, artifact)

    offering_payload = {
        "artifact_id": artifact_id,
        "connection_id": connection.get("id"),
        "access_provider": connection.get("name") or entry.get("access_provider") or entry.get("provider") or "",
        "access_type": entry.get("access_type") or connection.get("type") or "",
        "served_by": entry.get("served_by") or "",
    }
    offering_id = _id("po", offering_payload)
    offering = store.get("provider_offering", offering_id)
    if offering is None:
        offering = {
            "id": offering_id,
            **offering_payload,
            "region": str(connection.get("region") or ""),
            "account": str(connection.get("account") or ""),
            "created_at": now(),
        }
        store.put("provider_offering", offering_id, offering)

    settings = _safe(deepcopy(connection.get("settings") or {}))
    profile_payload = {
        "artifact_id": artifact_id,
        "provider_offering_id": offering_id,
        "connection_id": connection.get("id"),
        "ref": ref,
        "version": str(entry.get("version") or ""),
        "served_by": str(entry.get("served_by") or ""),
        "runtime": entry.get("runtime") or "",
        "context": int(entry.get("context") or 0),
        "price_in": float(entry.get("price_in") or 0),
        "price_out": float(entry.get("price_out") or 0),
        "compute_usd_per_hour": float(entry.get("compute_usd_per_hour") or 0),
        "tools": bool(entry.get("tools")),
        "json_schema": bool(entry.get("json_schema")),
        "modalities": list(entry.get("modalities") or []),
        "mcp": bool(entry.get("mcp")),
        "local": bool(entry.get("local")),
        "settings": settings,
        "route_fingerprint": {
            "endpoint": str(connection.get("endpoint") or ""),
            "server": str(connection.get("server") or ""),
            "type": str(connection.get("type") or ""),
        },
    }
    profile_id = _id("ep", profile_payload)
    profile = store.get("execution_profile", profile_id)
    if profile is None:
        profile = {
            "id": profile_id,
            **profile_payload,
            "fingerprint": digest(profile_payload),
            "created_at": now(),
        }
        store.put("execution_profile", profile_id, profile)

    return {
        "artifact_id": artifact_id,
        "provider_offering_id": offering_id,
        "execution_profile_id": profile_id,
        "profile_fingerprint": profile["fingerprint"],
    }
