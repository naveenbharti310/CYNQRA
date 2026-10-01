"""Bounded candidate sets: which intelligence to spend a limited qualification or calibration budget on.

This decides priority, never quality. Not every available model is called for every objective (mandate 11): a
bounded set is chosen that is fair across providers and diverse across model families, and inside each family the
newest release stands for it. Metadata (stated capabilities, context, whether a public catalogue knows it) orders
the set; a release date only picks the newest member of a family and never ranks one family above another, and
nothing here says which model is better. What a candidate can do is learned from its verified work.
"""
from __future__ import annotations

import re

USEFUL = {"reasoning", "coding", "agentic", "tool use", "long context", "structured output"}


def family_key(ref: str) -> str:
    """A model's family: its name without publisher, serving suffix or version numbers, so vendor/model-k2.6 and
    vendor/model-k3 are one family, as are vendor-model-4-6 and vendor-model-5 (a version written with dashes, or
    with a release date after it), and only the newest of them takes a place in a bounded set."""
    value = str(ref or "").lower().split("/")[-1].split(":")[0]
    return re.sub(r"#(?:-#)+(?![a-z])", "#", re.sub(r"\d+(?:\.\d+)*", "#", value))


def provider_key(m: dict) -> str:
    return str(m.get("connection_id") or m.get("access_provider") or m.get("provider") or "unknown")


def priority(m: dict) -> tuple:
    """Calibration priority across families, highest first: still to be qualified, more of the capabilities Cynqra's
    work uses stated, known to the public catalogue, a larger context. Never the release date, never the provider."""
    caps = {str(x).lower() for x in m.get("capabilities") or []}
    regression = (m.get("regression") or {}).get("status", "unverified")
    qualification = {"unverified": 2, "passed": 1, "not applicable": 1, "failed": 0}.get(regression, 2)
    return (qualification, len(caps & USEFUL), int(bool(m.get("catalogued"))), int(m.get("context") or 0))


def _order(models: list[dict]) -> list[dict]:
    """Newest of each family first inside it; families by priority, then by name for a stable order."""
    fams: dict[str, list[dict]] = {}
    for m in models:
        fams.setdefault(family_key(m.get("ref") or m.get("id")), []).append(m)
    heads, tails = [], []
    for members in fams.values():
        members.sort(key=lambda m: (-float(m.get("released") or 0), str(m.get("ref") or m.get("id"))))
        heads.append(members[0])
        tails.extend(members[1:])
    key = lambda m: (tuple(-x for x in priority(m)), str(m.get("ref") or m.get("id")))  # noqa: E731
    return sorted(heads, key=key) + sorted(tails, key=key)


def select(entries: list[dict], limit: int, prefer: list[str] | None = None) -> list[dict]:
    """A bounded set of at most limit candidates: the preferred ones first (an incumbent with evidence), then one per
    provider in turn, one per family, by priority; then the remaining capacity by priority."""
    limit = max(1, int(limit))
    active = [m for m in entries if m.get("status") != "retired"]
    chosen: list[dict] = []
    ids: set[str] = set()
    for pid in prefer or []:
        m = next((x for x in active if x["id"] == pid), None)
        if m is not None and m["id"] not in ids and len(chosen) < limit:
            chosen.append(m)
            ids.add(m["id"])
    families = {family_key(m.get("ref") or m["id"]) for m in chosen}
    groups: dict[str, list[dict]] = {}
    for m in active:
        groups.setdefault(provider_key(m), []).append(m)
    for p in groups:
        groups[p] = _order(groups[p])
    while len(chosen) < limit:
        progressed = False
        for p in sorted(groups):
            pick = next((m for m in groups[p] if m["id"] not in ids
                         and family_key(m.get("ref") or m["id"]) not in families), None)
            if pick is None:
                continue
            chosen.append(pick)
            ids.add(pick["id"])
            families.add(family_key(pick.get("ref") or pick["id"]))
            progressed = True
            if len(chosen) >= limit:
                break
        if not progressed:
            break
    rest = [m for m in _order(active) if m["id"] not in ids]
    chosen.extend(rest[: max(0, limit - len(chosen))])
    return chosen[:limit]


def details(entries: list[dict], selected: list[dict], limit: int) -> dict:
    """Why each model was or was not chosen: enough to explain the bounded set later."""
    ids = {m["id"] for m in selected}
    active = [m for m in entries if m.get("status") != "retired"]
    providers: dict[str, int] = {}
    for m in active:
        providers[provider_key(m)] = providers.get(provider_key(m), 0) + 1
    return {
        "discovered_models": len(entries), "active_models": len(active), "provider_counts": providers,
        "discovered_refs": sorted(str(m.get("ref") or "") for m in active), "selected_count": len(selected),
        "requested_limit": limit,
        "selection_policy": "metadata-only calibration priority; provider/family diversity; newest of each family; "
                            "no model-quality ranking",
        "unselected_top": [{"id": m["id"], "ref": m.get("ref"), "provider": provider_key(m),
                            "regression": (m.get("regression") or {}).get("status", "unverified"),
                            "capabilities": m.get("capabilities") or [], "context": m.get("context"),
                            "released": m.get("released")}
                           for m in _order([m for m in active if m["id"] not in ids])[:20]],
    }
