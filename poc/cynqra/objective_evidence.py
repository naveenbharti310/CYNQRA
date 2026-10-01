"""Objective evidence: how each intelligence actually performed on this objective, persisted (mandate 8).

The record is first-class, in the run's own store beside its event log:

    objective -> objective version -> work item -> attempt -> intelligence -> artifact -> verification -> outcome
              -> evidence update

Three stages are kept apart and never collapsed into one score:

  global_qualification   is this intelligence safe and reliable enough to take part at all (probe.py, in the
                         Intelligence Registry, across objectives)
  objective_calibration  a qualified intelligence measured on representative work derived from this objective,
                         before the real work (calibration.py)
  objective_execution    what it did on the live objective's real work

A record is immutable: its body is a content-addressed object, and the index row beside it carries only its lifecycle
(active, archived, invalidated, redacted). It holds references and hashes, never file contents, prompts or
credentials (mandate 54). Recording is idempotent (the same verification never counts twice) and each accepted record
advances the objective's evidence version atomically, so a selection made against version N can tell that N+1 exists
(mandate 52). Every record names its tenant and workspace, and a query outside them returns nothing (mandate 53).
"""
from __future__ import annotations

import time

from . import attribution as attr
from .db import ConcurrencyError, digest, now

STAGES = ("global_qualification", "objective_calibration", "objective_execution")
STATUSES = ("active", "archived", "invalidated", "redacted")
KIND, STATE, IDEM = "intel_evidence", "evidence_state", "evidence_idem"
# what an evidence record may never carry: the content of the work, the prompt, or anything secret
FORBIDDEN = {"content", "text", "prompt", "files_content", "body", "secret", "api_key", "key", "token", "credentials"}


class EvidenceError(ValueError):
    """A record that would corrupt the evidence: false, misleading, or about the wrong objective, tenant or
    intelligence. Nothing is written."""


def _check(rec: dict) -> None:
    bad = FORBIDDEN & set(rec)
    if bad:
        raise EvidenceError(f"objective evidence may not carry {sorted(bad)}: it holds references and hashes only")
    for k in ("objective_id", "objective_version", "tenant_id", "workspace_id", "intelligence_id", "stage",
              "work_item_id", "idempotency_key"):
        if rec.get(k) in (None, ""):
            raise EvidenceError(f"objective evidence needs {k}")
    if rec["stage"] not in STAGES:
        raise EvidenceError(f"unknown evidence stage {rec['stage']!r}")
    a = rec.get("failure")
    if a is not None and a.get("kind") not in attr.CAUSES:
        raise EvidenceError("a failure must carry its attribution")
    if rec.get("clean") != attr.clean(a) and rec.get("verified") is False:
        raise EvidenceError("a failure's causal cleanliness must follow its attribution")


def state(store, objective_id: str) -> dict:
    return store.get(STATE, objective_id) or {"objective_id": objective_id, "version": 0, "by_version": {},
                                              "last_evidence_id": None, "_v": 0}


def evidence_version(store, objective_id: str) -> int:
    return int(state(store, objective_id)["version"])


def record(store, rec: dict, *, event=None) -> tuple[dict, bool]:
    """Persist one evidence record. Returns (record, created). The same idempotency key returns the record already
    there and changes nothing, so a retried or duplicated event never counts twice."""
    rec = {k: v for k, v in rec.items() if v is not None or k in ("verified",)}
    rec.setdefault("verified", None)
    rec.setdefault("clean", attr.clean(rec.get("failure")))
    rec.setdefault("autonomy", "autonomous")
    rec.setdefault("recorded_at", now())
    rec.setdefault("at", time.time())
    _check(rec)
    with store.atomic():
        known = store.get(IDEM, rec["idempotency_key"])
        if known:
            return store.get(KIND, known["evidence_id"]), False
        st = state(store, rec["objective_id"])
        seq = store.next_seq("evidence:" + rec["objective_id"])
        body = dict(rec, seq=seq, evidence_version=st["version"] + 1)
        h = store.put_object("json", body)
        eid = f"ev_{seq:05d}_{h[:8]}"
        body.update(evidence_id=eid, content_hash=h, status="active")
        store.put(KIND, eid, body)
        store.put(IDEM, rec["idempotency_key"], {"evidence_id": eid})
        by = dict(st.get("by_version") or {})
        by[str(rec["objective_version"])] = int(by.get(str(rec["objective_version"])) or 0) + 1
        try:
            store.compare_and_put(STATE, rec["objective_id"], {"objective_id": rec["objective_id"],
                                  "version": st["version"] + 1, "by_version": by, "last_evidence_id": eid,
                                  "updated_at": now()}, int(st.get("_v") or 0))
        except ConcurrencyError:  # cannot happen inside the transaction; refuse rather than lose an update
            raise
    if event is not None:
        event(body)
    return body, True


def query(store, *, objective_id: str, tenant_id: str, workspace_id: str | None = None,
          objective_version: int | None = None, intelligence_id: str | None = None, task_kind: str | None = None,
          work_item_id: str | None = None, stage: str | None = None, include_inactive: bool = False) -> list[dict]:
    """Evidence for one objective, inside one tenant (and workspace, when named). Nothing outside them is returned,
    whatever else matches."""
    if not objective_id or not tenant_id:
        raise EvidenceError("an evidence query names its objective and tenant")
    out = []
    for r in store.all(KIND):
        if r.get("objective_id") != objective_id or r.get("tenant_id") != tenant_id:
            continue
        if workspace_id is not None and r.get("workspace_id") != workspace_id:
            continue
        if objective_version is not None and int(r.get("objective_version") or 0) != int(objective_version):
            continue
        if intelligence_id is not None and r.get("intelligence_id") != intelligence_id:
            continue
        if task_kind is not None and r.get("task_kind") != task_kind:
            continue
        if work_item_id is not None and r.get("work_item_id") != work_item_id:
            continue
        if stage is not None and r.get("stage") != stage:
            continue
        if not include_inactive and r.get("status") != "active":
            continue
        out.append(r)
    out.sort(key=lambda r: r.get("seq") or 0)
    return out


def get(store, evidence_id: str) -> dict | None:
    return store.get(KIND, evidence_id)


def verify_integrity(store, evidence_id: str) -> bool:
    """The record still matches the immutable body it was written as."""
    r = store.get(KIND, evidence_id)
    if r is None:
        return False
    body = store.get_object(r["content_hash"])
    if body is None:
        return False
    keep = {k: v for k, v in r.items() if k not in ("evidence_id", "content_hash", "status", "status_note",
                                                     "status_at", "redacted_refs")}
    return digest(keep) == digest(body)


def annotate(store, evidence_id: str, status: str, why: str) -> dict:
    """A lifecycle change on the index only: the immutable body, its hash and the causal links stay. An invalidated
    record (its verification was a false rejection, say) and an archived one lose their selection authority."""
    if status not in STATUSES:
        raise EvidenceError(f"unknown evidence status {status!r}")
    with store.atomic():
        r = store.get(KIND, evidence_id)
        if r is None:
            raise EvidenceError(f"no evidence {evidence_id}")
        r.update(status=status, status_note=why[:300], status_at=now())
        store.put(KIND, evidence_id, r)
        return r


def redact_artifact(store, artifact_hash: str, why: str) -> list[str]:
    """A sensitive artifact was deleted. Every record that referenced it keeps its hash, its verification result and
    its causal links; the record says the artifact is gone and why (mandate 55)."""
    hit = []
    with store.atomic():
        for r in store.all(KIND):
            refs = r.get("artifact_hashes") or {}
            hashes = {refs.get("work_hash")} | {f.get("hash") for f in refs.get("files") or []}
            if artifact_hash in hashes:
                r["redacted_refs"] = sorted(set(r.get("redacted_refs") or []) | {artifact_hash})
                r["status_note"] = f"artifact {artifact_hash[:12]} deleted: {why[:200]}"
                store.put(KIND, r["evidence_id"], r)
                hit.append(r["evidence_id"])
    return hit


def archive_older_than(store, objective_id: str, days: float, now_ts: float | None = None) -> list[str]:
    """Retention: records older than the policy's window are archived, kept for audit and replay, and no longer
    selection authority."""
    cutoff = (now_ts or time.time()) - days * 86400
    out = []
    for r in store.all(KIND):
        if r.get("objective_id") == objective_id and r.get("status") == "active" and float(r.get("at") or 0) < cutoff:
            annotate(store, r["evidence_id"], "archived", f"older than {days:g} days")
            out.append(r["evidence_id"])
    return out


def raw(r: dict) -> dict:
    """A record as a selection snapshot keeps it: what the evidence model reads, and its content hash."""
    return {"src": "objective", "id": r["evidence_id"], "content_hash": r.get("content_hash"),
            "intelligence_id": r["intelligence_id"], "served_version": r.get("served_version") or "",
            "objective_id": r["objective_id"], "objective_version": r["objective_version"],
            "tenant_id": r["tenant_id"], "stage": r["stage"], "work_item_id": r["work_item_id"],
            "task_kind": r.get("task_kind"), "role": r.get("role"), "verified": r.get("verified"),
            "clean": r.get("clean"), "attribution": (r.get("failure") or {}).get("kind"),
            "autonomy": r.get("autonomy"), "vq": (r.get("verification") or {}).get("quality"),
            "severity": r.get("max_severity"), "at": r.get("at"), "env": (r.get("environment") or {}).get("fingerprint"),
            "author_conflict": bool(r.get("author_conflict")), "dependencies_unmet": bool(r.get("dependencies_unmet")),
            "status": r.get("status")}


def registry_raw(o: dict, entry_version: str | None = None) -> dict:
    """An outcome in the Intelligence Registry (other work, other objectives, qualification), as a raw item."""
    import datetime as _dt
    try:
        at = _dt.datetime.fromisoformat(o.get("at")).timestamp()
    except (TypeError, ValueError):
        at = None
    return {"src": "registry", "id": o["id"], "intelligence_id": o["model_id"],
            "served_version": o.get("model_version") or "", "task_kind": o.get("task_kind"), "role": o.get("role"),
            "verified": bool(o.get("verified")), "source": o.get("source") or "project", "run_id": o.get("run_id"),
            "tenant_id": o.get("tenant_id") or "local", "at": at, "clean": o.get("clean", True),
            "attribution": o.get("attribution"), "vq": 0.8 if o.get("source") == "probe" and o.get("task_kind") ==
            "code" else 1.0, "objective_id": o.get("objective_id"), "status": "active"}
