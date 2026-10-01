#!/usr/bin/env python3
"""Discover and examine current hosted intelligence exposed by CI credentials.

This is deliberately separate from the deterministic phase gate. It makes real provider
calls, so it is run manually and records the evidence CYNQRA uses to qualify intelligence.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from cynqra.intelligence_layer import IntelligenceSupply
from cynqra.probe import probe


def _family_key(ref: str) -> str:
    """Normalize a model reference enough to avoid spending a bounded probe budget on one release family."""
    import re
    value = str(ref or "").lower().split("/")[-1].split(":")[0]
    value = re.sub(r"(?<![a-z])\\d+(?:\\.\\d+)*(?![a-z])", "#", value)
    return value


def _candidate_score(m: dict) -> tuple:
    """Metadata is a probe-priority signal only, never a quality score."""
    caps = {str(x).lower() for x in m.get("capabilities") or []}
    useful = {"reasoning", "coding", "agentic", "tool use", "long context", "structured output"}
    regression = (m.get("regression") or {}).get("status", "unverified")
    qualification_priority = {"unverified": 2, "passed": 1, "failed": 0}.get(regression, 2)
    return (
        qualification_priority,
        len(caps & useful),
        int(bool(m.get("catalogued"))),
        float(m.get("released") or 0),
        int(m.get("context") or 0),
        str(m.get("ref") or ""),
    )


def _provider_key(m: dict) -> str:
    return str(m.get("connection_id") or m.get("access_provider") or m.get("provider") or "unknown")


def select(entries: list[dict], limit: int) -> list[dict]:
    """Select a bounded, provider/family-diverse calibration set.

    This function deliberately does not rank models by presumed intelligence. Provider metadata only decides
    calibration priority. The actual probe determines qualification and later measured outcomes determine routing.
    """
    limit = max(1, int(limit))
    active = [m for m in entries if m.get("status") != "retired"]
    groups: dict[str, list[dict]] = {}
    for m in active:
        groups.setdefault(_provider_key(m), []).append(m)
    for values in groups.values():
        values.sort(key=_candidate_score, reverse=True)

    chosen: list[dict] = []
    chosen_ids: set[str] = set()
    used_families: set[str] = set()

    # First pass: provider fairness and family diversity. This prevents one provider or one model family
    # consuming the whole bounded calibration budget.
    while len(chosen) < limit:
        progressed = False
        for provider in sorted(groups):
            candidates = groups[provider]
            pick = next((m for m in candidates
                         if m["id"] not in chosen_ids and _family_key(m["ref"]) not in used_families), None)
            if pick is None:
                continue
            chosen.append(pick)
            chosen_ids.add(pick["id"])
            used_families.add(_family_key(pick["ref"]))
            progressed = True
            if len(chosen) >= limit:
                break
        if not progressed:
            break

    # Second pass: fill remaining capacity with the highest-priority untested candidates.
    remaining = sorted((m for m in active if m["id"] not in chosen_ids), key=_candidate_score, reverse=True)
    chosen.extend(remaining[: max(0, limit - len(chosen))])
    return chosen[:limit]


def selection_details(entries: list[dict], selected: list[dict], limit: int) -> dict:
    """Persist enough discovery evidence to explain why a model was or was not probed."""
    selected_ids = {m["id"] for m in selected}
    active = [m for m in entries if m.get("status") != "retired"]
    top_unselected = sorted(
        (m for m in active if m["id"] not in selected_ids),
        key=_candidate_score,
        reverse=True,
    )[:20]
    providers = {}
    for m in active:
        providers.setdefault(_provider_key(m), 0)
        providers[_provider_key(m)] += 1
    return {
        "discovered_models": len(entries),
        "active_models": len(active),
        "provider_counts": providers,
        "selected_count": len(selected),
        "requested_limit": limit,
        "selection_policy": "metadata-only calibration priority; provider/family diversity; no model-quality ranking",
        "unselected_top": [
            {"id": m["id"], "ref": m["ref"], "provider": _provider_key(m),
             "regression": (m.get("regression") or {}).get("status", "unverified"),
             "capabilities": m.get("capabilities") or [], "context": m.get("context"),
             "released": m.get("released")}
            for m in top_unselected
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-models", type=int, default=4)
    ap.add_argument("--provider", choices=("all", "google", "nvidia"), default="all")
    ap.add_argument("--data-root", default="")
    args = ap.parse_args()

    if args.provider == "google" and not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("provider=google requires GEMINI_API_KEY")
    if args.provider == "nvidia" and not os.environ.get("NVIDIA_API_KEY"):
        raise SystemExit("provider=nvidia requires NVIDIA_API_KEY")
    if args.provider == "all" and not os.environ.get("GEMINI_API_KEY") and not os.environ.get("NVIDIA_API_KEY"):
        raise SystemExit("provider=all requires GEMINI_API_KEY and/or NVIDIA_API_KEY")

    root = Path(args.data_root or Path.cwd() / "hosted-examination")
    root.mkdir(parents=True, exist_ok=True)
    supply = IntelligenceSupply(root / "control")
    try:
        entries = supply.connect_environment()
        if args.provider != "all":
            needle = "Google Gemini (environment)" if args.provider == "google" else "NVIDIA (environment)"
            allowed = {c["id"] for c in supply.connections.all() if c["name"] == needle}
            entries = [m for m in entries if m["connection_id"] in allowed]

        limit = max(1, args.max_models)
        selected = select(entries, limit)
        manifest = {
            "discovery": selection_details(entries, selected, limit),
            "candidates": [
                {"id": m["id"], "ref": m["ref"], "name": m["name"],
                 "provider": m.get("access_provider") or m.get("provider"),
                 "capabilities": m.get("capabilities") or [], "context": m.get("context"),
                 "released": m.get("released"), "regression": (m.get("regression") or {}).get("status", "unverified")}
                for m in selected
            ],
            "results": [],
        }
        print("Candidates:")
        for m in selected:
            print(f"  {m['id']}  {m['ref']}")

        for m in selected:
            print(f"\nExamining {m['ref']}...", flush=True)
            result = probe(supply, m["id"], log=print)
            manifest["results"].append(result)

        (root / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
        passed = sum(bool(r.get("passed")) for r in manifest["results"])
        print(json.dumps({"models_examined": len(selected), "passed": passed,
                          "manifest": str(root / "manifest.json")}, indent=2))
        return 0 if selected and passed else 1
    finally:
        supply.close()


if __name__ == "__main__":
    raise SystemExit(main())
