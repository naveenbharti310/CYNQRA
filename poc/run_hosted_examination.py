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


def _candidate_score(m: dict) -> tuple:
    caps = {str(x).lower() for x in m.get("capabilities") or []}
    useful = {"reasoning", "coding", "agentic", "tool use", "long context", "structured output"}
    return (
        len(caps & useful),
        int(m.get("context") or 0),
        float(m.get("released") or 0),
        str(m.get("ref") or ""),
    )


def select(entries: list[dict], limit: int) -> list[dict]:
    """Keep the real examination bounded while retaining CYNQRA-relevant candidates.

    Kimi K3 is retained whenever NVIDIA actually exposes it. Other candidates are
    selected from the capability-rich current set; performance is determined only
    by the probe, never by this prefilter.
    """
    by_provider = {}
    for m in entries:
        if m.get("status") == "retired":
            continue
        conn = m.get("connection_id")
        by_provider.setdefault(conn, []).append(m)

    chosen = []
    per_provider = max(1, limit // max(1, len(by_provider)))
    for conn_entries in by_provider.values():
        k3 = next((m for m in conn_entries if m.get("ref") == "moonshotai/kimi-k3"), None)
        ranked = sorted(conn_entries, key=_candidate_score, reverse=True)
        local = []
        if k3:
            local.append(k3)
        for m in ranked:
            if m["id"] not in {x["id"] for x in local} and len(local) < per_provider:
                local.append(m)
        chosen.extend(local)

    # If the provider split left room, fill from the remaining highest-capability entries.
    chosen_ids = {m["id"] for m in chosen}
    for m in sorted(entries, key=_candidate_score, reverse=True):
        if m.get("status") == "retired" or m["id"] in chosen_ids:
            continue
        chosen.append(m)
        chosen_ids.add(m["id"])
        if len(chosen) >= limit:
            break
    return chosen[:limit]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-models", type=int, default=4)
    ap.add_argument("--provider", choices=("all", "google", "nvidia"), default="all")
    ap.add_argument("--data-root", default="")
    args = ap.parse_args()

    if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("NVIDIA_API_KEY"):
        raise SystemExit("no GEMINI_API_KEY or NVIDIA_API_KEY secret is available")

    root = Path(args.data_root or Path.cwd() / "hosted-examination")
    root.mkdir(parents=True, exist_ok=True)
    supply = IntelligenceSupply(root / "control")
    try:
        entries = supply.connect_environment()
        if args.provider != "all":
            needle = "Google Gemini (environment)" if args.provider == "google" else "NVIDIA (environment)"
            allowed = {c["id"] for c in supply.connections.all() if c["name"] == needle}
            entries = [m for m in entries if m["connection_id"] in allowed]

        selected = select(entries, max(1, args.max_models))
        manifest = {
            "candidates": [
                {"id": m["id"], "ref": m["ref"], "name": m["name"],
                 "provider": m.get("access_provider") or m.get("provider"),
                 "capabilities": m.get("capabilities") or []}
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
