"""Discover and examine current hosted intelligence exposed by CI credentials (global qualification).

Deliberately separate from the deterministic phase gate: it makes real provider calls, so it is run on request
(.github/workflows/cynqra-hosted-intelligence.yml) and records the evidence Cynqra uses to qualify intelligence. A
model not chosen for the bounded set stays untested, not failed; a provider outage stays inconclusive, never an
intelligence failure. The bounded set is chosen by intelligence_layer/candidates.py: priority, never quality.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .intelligence_layer import IntelligenceSupply
from .intelligence_layer.candidates import details, family_key, priority, provider_key
from .intelligence_layer.candidates import select as _select
from .probe import probe

_family_key, _candidate_score, _provider_key = family_key, priority, provider_key


# The hosted providers an examination can be limited to: the key each needs and the environment connection it makes
PROVIDERS = {"google": ("GEMINI_API_KEY", "Google Gemini (environment)"),
             "nvidia": ("NVIDIA_API_KEY", "NVIDIA (environment)"),
             "anthropic": ("ANTHROPIC_API_KEY", "Anthropic (environment)")}


def select(entries: list[dict], limit: int) -> list[dict]:
    """A bounded, provider-fair, family-diverse calibration set. Metadata decides priority only."""
    return _select(entries, limit)


def selection_details(entries: list[dict], selected: list[dict], limit: int) -> dict:
    return details(entries, selected, limit)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-models", type=int, default=4)
    ap.add_argument("--provider", choices=("all", *PROVIDERS), default="all")
    ap.add_argument("--data-root", default="")
    ap.add_argument("--objective", default="", help="after qualification, run this objective through the objective "
                    "intelligence loop to its first bindings: requirements, workforce, plan, calibration, decisions")
    ap.add_argument("--budget-usd", type=float, default=1.0, help="the objective run's hard cap")
    args = ap.parse_args(argv)

    keys = {p: env for p, (env, _) in PROVIDERS.items()}
    if args.provider != "all" and not os.environ.get(keys[args.provider]):
        raise SystemExit(f"provider={args.provider} requires {keys[args.provider]}")
    if args.provider == "all" and not any(os.environ.get(k) for k in keys.values()):
        raise SystemExit("provider=all requires at least one of " + ", ".join(keys.values()))

    root = Path(args.data_root or Path.cwd() / "hosted-examination")
    root.mkdir(parents=True, exist_ok=True)
    supply = IntelligenceSupply(root / "control")
    try:
        entries = supply.connect_environment()
        if args.provider != "all":
            needle = PROVIDERS[args.provider][1]
            allowed = {c["id"] for c in supply.connections.all() if c["name"] == needle}
            entries = [m for m in entries if m["connection_id"] in allowed]
        connections = connection_report(supply)
        print("Connections:")
        for c in connections:  # a listing that failed says why here: the key refused, the provider down
            print(f"  {c['name']}: {c['status']} ({c['note']})")
        limit = max(1, args.max_models)
        selected = select(entries, limit)
        manifest = {
            "connections": connections,
            "discovery": selection_details(entries, selected, limit),
            "candidates": [{"id": m["id"], "ref": m["ref"], "name": m["name"],
                            "provider": m.get("access_provider") or m.get("provider"),
                            "capabilities": m.get("capabilities") or [], "context": m.get("context"),
                            "released": m.get("released"),
                            "regression": (m.get("regression") or {}).get("status", "unverified")} for m in selected],
            "results": [],
        }
        print("Candidates:")
        for m in selected:
            print(f"  {m['id']}  {m['ref']}")
        for m in selected:
            print(f"\nExamining {m['ref']}...", flush=True)
            manifest["results"].append(probe(supply, m["id"], log=print))
        if args.objective:
            manifest["objective_run"] = objective_run(supply, root / "objective-run", args.objective, args.budget_usd)
            print("\nObjective run:\n" + json.dumps(objective_summary(manifest["objective_run"]), indent=2, default=str))
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
        passed = sum(bool(r.get("passed")) for r in manifest["results"])
        print(json.dumps({"models_examined": len(selected), "passed": passed,
                          "manifest": str(root / "manifest.json")}, indent=2))
        return 0 if selected and passed else 1
    finally:
        supply.close()


def connection_report(supply) -> list[dict]:
    """Each environment connection's state after discovery: connected with what it offers, or the error its
    provider gave. The credential is described by reference only (credentials.public), never its value."""
    return [{"name": c["name"], "type": c["type"], "status": c.get("status"), "note": c.get("status_note") or "",
             "offered": len(c.get("offered") or [])}
            for c in (supply.connections.public(x["id"]) for x in supply.connections.all())
            if c.get("origin") == "environment"]


def objective_summary(run: dict) -> dict:
    """What the objective run did, short enough for the job log (the manifest holds the whole record): how far it
    got, calibration's trials and outcome, every decision's mode and whether it replays, and the spend."""
    cal = run.get("calibration") or {}
    trials = cal.get("trials") or []
    decisions = run.get("decisions") or []
    modes: dict[str, int] = {}
    for d in decisions:
        modes[str(d.get("selection_mode"))] = modes.get(str(d.get("selection_mode")), 0) + 1
    by_candidate: dict[str, list] = {}  # each trial's outcome: True verified, False failed, None not measured
    for t in trials:
        by_candidate.setdefault(str(t.get("intelligence_id")), []).append(t.get("verified"))
    return {"stage": run.get("stage"), "lifecycle": run.get("lifecycle"), "error": run.get("error"),
            "notice": run.get("notice"),
            "calibration": {"status": cal.get("status"), "reason": cal.get("reason"), "spent_usd": cal.get("spent_usd"),
                            "trials": len(trials), "verified": sum(1 for t in trials if t.get("verified")),
                            "failures_not_the_intelligence": sorted({str(t["attribution"]) for t in trials
                                                                     if t.get("attribution")
                                                                     and t["attribution"] != "intelligence"}),
                            "by_candidate": by_candidate},
            "decisions": len(decisions), "selection_modes": modes,
            "all_replayed": all(d.get("replayed") for d in decisions) if decisions else None,
            "selected": sorted({str(d.get("selected")) for d in decisions if d.get("selected")}),
            "spent_usd": run.get("spent_usd")}


def objective_run(supply, folder: Path, statement: str, budget_usd: float) -> dict:
    """A real objective through the control plane, with the qualified hosted intelligence, to its first bindings:
    the objective structured and decomposed, the workforce synthesized, the roadmap planned, objective calibration on
    representative work items, and a persisted selection decision for every worker and work item. Real calls, a hard
    cap. What it shows is what these providers did on this objective in this run, nothing more."""
    from . import calibration, controller
    from .engine import Engine
    out = {"objective": statement, "budget_usd": budget_usd, "stage": "start"}
    e = Engine(folder, supply=supply)
    try:
        e.create_company("Hosted objective examination", "live")
        e.set_guardrails(budget_usd=budget_usd, time_value_per_hour=10)
        out["stage"] = "objective"
        e.draft_objective(statement)
        e.submit_objective()
        out["stage"] = "workforce"
        d = next(x for x in e.pending_decisions() if x["kind"] == "approve_workforce")
        e.decide(d["id"], "approve")
        out["stage"] = "roadmap"
        e.define_founder()
        p = e.store.get(calibration.KIND, calibration.plan_id(e)) or {}
        out.update(stage="first_bindings", lifecycle=(e.objective() or {}).get("lifecycle", {}).get("state"),
                   calibration={k: p.get(k) for k in ("status", "reason", "spent_usd", "budget_usd", "stopping")}
                   | {"trials": [{k: t.get(k) for k in ("item_id", "intelligence_id", "verified", "attribution",
                                                         "usd")} for t in p.get("trials") or []],
                      "items": [{k: i.get(k) for k in ("work_class", "source_task_id", "candidates", "skipped")}
                                for i in p.get("items") or []]},
                   decisions=[{k: x.get(k) for k in ("decision_id", "work_item_id", "purpose", "selection_mode",
                                                      "status", "selection_reason")}
                              | {"selected": (x.get("selected_intelligence") or {}).get("id"),
                                 "replayed": controller.replay(e, x["decision_id"])["reproduced"]}
                              for x in e.decisions()],
                   spent_usd=e.snapshot()["budget"]["ledger"]["spent_total"])
    except Exception as exc:  # noqa: BLE001 - a real provider can fail at any stage: recorded as it happened
        out.update(error=f"{type(exc).__name__}: {exc}"[:600], notice=e.meta.get("notice"))
    finally:
        e.close()
    return out
