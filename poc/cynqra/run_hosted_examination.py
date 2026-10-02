"""Discover and examine current hosted intelligence exposed by CI credentials (global qualification), and prove the
objective loop on real models (roadmap 1).

Deliberately separate from the deterministic phase gate: it makes real provider calls, so it is run on request
(.github/workflows/cynqra-hosted-intelligence.yml) and records the evidence Cynqra uses to qualify intelligence. A
model not chosen for the bounded set stays untested, not failed; a provider outage stays inconclusive, never an
intelligence failure. The bounded set is chosen by intelligence_layer/candidates.py: priority, never quality.

With an objective, the run goes through the control loop: to its first bindings, or (--to-delivery) on through the
work to delivery, an examination founder answering each decision as recommended except those that would spend more
or need a person (the budget breaker, an account to fix: refused, so the run stops). The selection report compares
every work item's choice with what the global prior alone would have chosen from the same snapshot
(controller.prior_choice), next to the verified outcomes. It shows what these models did on this objective in this
run, nothing more.
"""
from __future__ import annotations

import argparse
import json
import os
import time
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


def parse_providers(value: str) -> list[str] | None:
    """--provider: all, or one or more of the providers joined with + (google+nvidia). None means all."""
    if value == "all":
        return None
    names = [x for x in str(value or "").split("+") if x]
    bad = [x for x in names if x not in PROVIDERS]
    if not names or bad:
        raise SystemExit(f"--provider is all or one or more of {', '.join(PROVIDERS)} joined with +"
                         + (f" (unknown: {', '.join(bad)})" if bad else ""))
    return names


def select(entries: list[dict], limit: int) -> list[dict]:
    """A bounded, provider-fair, family-diverse calibration set. Metadata decides priority only."""
    return _select(entries, limit)


def selection_details(entries: list[dict], selected: list[dict], limit: int) -> dict:
    return details(entries, selected, limit)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-models", type=int, default=4)
    ap.add_argument("--provider", default="all", help="all, or providers joined with +: "
                    + ", ".join(PROVIDERS) + " (google+nvidia)")
    ap.add_argument("--data-root", default="")
    ap.add_argument("--objective", action="append", default=[], help="after qualification, run this objective "
                    "through the objective intelligence loop: requirements, workforce, plan, calibration, decisions "
                    "(repeat for several, run one after another against the same Intelligence Layer)")
    ap.add_argument("--objective-set", default="", help="a named set of objectives (scenarios/objective_sets/<name>"
                    ".json), run after any --objective: " + ", ".join(objective_sets()))
    ap.add_argument("--budget-usd", type=float, default=1.0, help="the objective run's hard cap")
    ap.add_argument("--to-delivery", action="store_true", help="carry the objective on through the work to delivery")
    ap.add_argument("--max-minutes", type=float, default=300.0, help="time limit for the work after first bindings")
    args = ap.parse_args(argv)

    keys = {p: env for p, (env, _) in PROVIDERS.items()}
    wanted = parse_providers(args.provider)
    if wanted is not None:
        missing = [p for p in wanted if not os.environ.get(keys[p])]
        if len(missing) == len(wanted):
            raise SystemExit(f"provider={args.provider} requires " + " or ".join(keys[p] for p in wanted))
        for p in missing:
            print(f"provider {p} skipped: {keys[p]} is not set")
        wanted = [p for p in wanted if p not in missing]
    elif not any(os.environ.get(k) for k in keys.values()):
        raise SystemExit("provider=all requires at least one of " + ", ".join(keys.values()))

    root = Path(args.data_root or Path.cwd() / "hosted-examination")
    root.mkdir(parents=True, exist_ok=True)
    supply = IntelligenceSupply(root / "control")
    try:
        entries = supply.connect_environment()
        if wanted is not None:
            needles = {PROVIDERS[p][1] for p in wanted}
            allowed = {c["id"] for c in supply.connections.all() if c["name"] in needles}
            entries = [m for m in entries if m["connection_id"] in allowed]
            for m in supply.registry.models():  # an examination limited to some providers uses only theirs
                if m["connection_id"] not in allowed and m.get("status") != "retired":
                    supply.registry.retire(m["id"], "not among the providers this examination is limited to")
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
        statements = objectives(args.objective, args.objective_set)
        runs = []
        for i, (label, statement) in enumerate(statements, 1):
            folder = root / ("objective-run" if len(statements) == 1 else f"objective-run-{i}")
            print(f"\nObjective {i} of {len(statements)} ({label}), in {folder.name}:", flush=True)
            r = objective_run(supply, folder, statement, args.budget_usd, to_delivery=args.to_delivery,
                              max_minutes=args.max_minutes)
            runs.append(r | {"label": label, "folder": folder.name})
            print("\nObjective run:\n" + json.dumps(objective_summary(r), indent=2, default=str))
            print("\nSelection report:\n" + json.dumps((r.get("selection_report") or {}).get("summary"), indent=2,
                                                       default=str))
        if runs:
            manifest["objective_run"] = runs[0]  # the first, where earlier manifests kept their only one
            manifest["objective_runs"] = runs
        if len(runs) > 1:
            manifest["comparison"] = comparison(runs)
            print("\nAcross objectives:\n" + json.dumps(manifest["comparison"], indent=2, default=str))
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
        passed = sum(bool(r.get("passed")) for r in manifest["results"])
        print(json.dumps({"models_examined": len(selected), "passed": passed,
                          "manifest": str(root / "manifest.json")}, indent=2))
        return 0 if selected and passed else 1
    finally:
        supply.close()


SETS = Path(__file__).resolve().parent.parent / "scenarios" / "objective_sets"


def objective_sets() -> list[str]:
    return sorted(json.loads(p.read_text(encoding="utf-8"))["name"] for p in SETS.glob("*.json"))


def objectives(given: list[str] | str | None, set_name: str = "") -> list[tuple[str, str]]:
    """The objectives to run, in order, each with a label: those given on the command line, then a named set's."""
    given = [given] if isinstance(given, str) else list(given or [])
    out = [(f"objective_{i}", s) for i, s in enumerate((x.strip() for x in given if x and x.strip()), 1)]
    if set_name and set_name != "none":
        found = [json.loads(p.read_text(encoding="utf-8")) for p in SETS.glob("*.json")]
        chosen = next((x for x in found if x["name"] == set_name), None)
        if chosen is None:
            raise SystemExit(f"--objective-set is one of {', '.join(objective_sets())} (unknown: {set_name})")
        out += [(o["id"], o["statement"]) for o in chosen["objectives"]]
    return out


def comparison(runs: list[dict]) -> dict:
    """Each objective's own choices, side by side: by kind of work, which intelligence its controller chose first and
    which produced the verified work. Read per objective; nothing here ranks one intelligence above another across
    objectives, and a choice that differs between objectives is reported, not explained away."""
    per = []
    for r in runs:
        items = (r.get("selection_report") or {}).get("items") or []
        kinds: dict[str, dict] = {}
        for x in items:
            k = kinds.setdefault(x["kind"], {"first_choice": {}, "verified_by": {}, "work_items": 0})
            k["work_items"] += 1
            k["first_choice"][str(x["first_choice"])] = k["first_choice"].get(str(x["first_choice"]), 0) + 1
            if x.get("verified_by"):
                k["verified_by"][x["verified_by"]] = k["verified_by"].get(x["verified_by"], 0) + 1
        per.append({"label": r.get("label"), "folder": r.get("folder"), "stage": r.get("stage"),
                    "calibration": (r.get("calibration") or {}).get("status"),
                    "evidence_by_intelligence": ((r.get("selection_report") or {}).get("summary") or {}).get(
                        "evidence_by_intelligence"), "by_kind": kinds})
    shared = sorted(set.intersection(*[set(p["by_kind"]) for p in per])) if per else []
    differs = [k for k in shared if len({json.dumps(p["by_kind"][k]["first_choice"], sort_keys=True)
                                         for p in per}) > 1]
    return {"objectives": per, "kinds_in_every_objective": shared, "kinds_chosen_differently": differs,
            "reading": "each objective's choices come from its own evidence over a shared global prior; a kind chosen "
                       "differently is selection conditional on the work, and the same choice everywhere is not a "
                       "ranking either"}


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
    jr = run.get("journey") or {}
    return {"stage": run.get("stage"), "lifecycle": run.get("lifecycle"), "phase": run.get("phase"),
            "error": run.get("error"), "notice": run.get("notice"),
            "journey": {"ended": jr.get("ended"), "minutes": jr.get("minutes"),
                        "founder_answers": len(jr.get("answers") or []),
                        "refused": [a["kind"] for a in jr.get("answers") or [] if a["answer"] == "reject"]}
            if jr else None,
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


# What an examination founder answers: the recommendation, except a decision that would spend more than the cap
# or that only a person can settle (an account to top up or a key to replace): refused, so the run stops there.
REFUSED = {"budget_breaker", "provider_account"}


def examination_answer(d: dict) -> str:
    return "reject" if d.get("kind") in REFUSED else "approve"


def objective_run(supply, folder: Path, statement: str, budget_usd: float, *, to_delivery: bool = False,
                  max_minutes: float = 300.0, log=print) -> dict:
    """A real objective through the control plane, with the qualified hosted intelligence: the objective structured
    and decomposed, the workforce synthesized, the roadmap planned, objective calibration on representative work
    items and a persisted selection decision for every worker and work item; with to_delivery, on through the work,
    its verification, rework and reselection, to production verification and delivery. Real calls, a hard cap. What
    it shows is what these providers did on this objective in this run, nothing more."""
    from . import calibration, controller
    from .engine import Engine
    out = {"objective": statement, "budget_usd": budget_usd, "stage": "start", "to_delivery": to_delivery}
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
        out["stage"] = "first_bindings"
        if to_delivery:
            out["journey"] = journey(e, max_minutes, log)
            out["stage"] = out["journey"]["ended"]
        p = e.store.get(calibration.KIND, calibration.plan_id(e)) or {}
        out.update(lifecycle=(e.objective() or {}).get("lifecycle", {}).get("state"),
                   calibration={k: p.get(k) for k in ("status", "reason", "spent_usd", "budget_usd", "stopping",
                                                       "coverage")}
                   | {"trials": [{k: t.get(k) for k in ("item_id", "intelligence_id", "verified", "attribution",
                                                         "usd")} for t in p.get("trials") or []],
                      "items": [{k: i.get(k) for k in ("item_id", "work_class", "source_task_id", "candidates",
                                                        "skipped")} for i in p.get("items") or []]},
                   decisions=[{k: x.get(k) for k in ("decision_id", "work_item_id", "purpose", "selection_mode",
                                                      "status", "selection_reason")}
                              | {"selected": (x.get("selected_intelligence") or {}).get("id"),
                                 "replayed": controller.replay(e, x["decision_id"])["reproduced"]}
                              for x in e.decisions()],
                   selection_report=selection_report(e, p),
                   spent_usd=e.snapshot()["budget"]["ledger"]["spent_total"], phase=e.meta.get("phase"),
                   notice=e.meta.get("notice"))
    except Exception as exc:  # noqa: BLE001 - a real provider can fail at any stage: recorded as it happened
        out.update(error=f"{type(exc).__name__}: {exc}"[:600], notice=e.meta.get("notice"))
        try:
            out["selection_report"] = selection_report(e, None)
        except Exception:  # noqa: BLE001 - a report that cannot be built leaves the error to speak
            pass
    finally:
        e.close()
    return out


def journey(e, max_minutes: float, log=print, idle_wait: float = 30.0, max_idle: int = 10) -> dict:
    """The work after the first bindings, to delivery: step until idle, answer the first pending decision as an
    examination founder would, repeat; stop when delivered and accepted, when the run stops, or at the time limit.
    Work waiting for a provider to answer again is waited for, a bounded number of times."""
    deadline = time.time() + max_minutes * 60
    answers, idle = [], 0
    ended = "time_limit"
    while time.time() < deadline:
        e.run_until_idle(max_steps=10)  # short bursts, so the time limit is checked between them
        if e.meta.get("phase") in ("accepted", "stopped"):
            ended = e.meta["phase"]
            break
        pend = e.pending_decisions()
        if not pend:
            if any(t["status"] == "WAITING" for t in e.tasks()) and idle < max_idle:
                idle += 1
                time.sleep(idle_wait)
                continue
            if e.step()["did"] == "idle":
                ended = "idle"
                break
            continue
        idle = 0
        d = pend[0]
        action = examination_answer(d)
        answers.append({"decision": d["id"], "kind": d["kind"], "task_id": d.get("task_id"), "answer": action})
        log(f"  examination founder: {action} {d['kind']} {d.get('task_id') or ''}".rstrip())
        e.decide(d["id"], action)
        if e.meta.get("phase") == "founder":
            e.define_founder()
        if e.meta.get("phase") in ("accepted", "stopped"):
            ended = e.meta["phase"]
            break
    return {"ended": ended, "answers": answers, "minutes": round(max_minutes - max(0.0, deadline - time.time()) / 60, 1)}


def selection_report(e, plan: dict | None) -> dict:
    """Every work item: the intelligence the controller chose (its latest decision and mode), what the global prior
    alone would have chosen from the same snapshot, and what happened: verified or not, after how many attempts, and
    which intelligence produced the verified work. Calibration's head-to-head on representative items sits beside it:
    the one place both choices were run on the same work. Outcomes are observed only for the choice that ran; what the
    prior's choice would have done elsewhere is not known, and is not guessed."""
    from . import controller, objective_evidence as oe
    oid = controller.objective_id(e)
    tasks = {t["id"]: t for t in e.tasks()}
    latest: dict[str, dict] = {}
    first: dict[str, dict] = {}
    for d in controller.decisions(e):
        if d.get("scope") == "task" and d.get("work_item_id") in tasks and d.get("selected_intelligence"):
            first.setdefault(d["work_item_id"], d)
            latest[d["work_item_id"]] = d
    ver = {}
    for v in e.store.all("verification"):
        ver.setdefault(v["task_id"], []).append(v)
    items = []
    for tid, d in sorted(latest.items()):
        t = tasks[tid]
        pc = controller.prior_choice(e, first[tid]["decision_id"])
        vs = sorted(ver.get(tid, []), key=lambda v: v["id"])
        done = next((v for v in vs if v["verdict"] == "VERIFIED"), None)
        evs = oe.query(e.store, objective_id=oid, tenant_id=controller.context(e)["tenant_id"], work_item_id=tid,
                       stage="objective_execution")
        items.append({"work_item_id": tid, "kind": t["kind"], "status": t["status"],
                      "first_choice": (first[tid].get("selected_intelligence") or {}).get("id"),
                      "first_mode": first[tid].get("selection_mode"), "prior_choice": pc.get("prior"),
                      "agrees_with_prior": pc.get("agrees"),
                      "latest_choice": (d.get("selected_intelligence") or {}).get("id"),
                      "latest_mode": d.get("selection_mode"), "decisions": sum(1 for x in controller.decisions(e, tid)),
                      "verified": done is not None, "verified_by": (done or {}).get("model_id"),
                      "verifications": [{"verdict": v["verdict"], "model": v.get("model_id")} for v in vs],
                      "clean_failures": sum(1 for x in evs if x["verified"] is False and x["clean"]),
                      "inconclusive": sum(1 for x in evs if x["verified"] is None)})
    head = []
    for it in (plan or {}).get("items") or []:
        if it.get("skipped"):
            continue
        trials = [t for t in plan.get("trials") or [] if t.get("item_id") == it["item_id"]]
        verdicts: dict[str, list] = {}
        for tr in trials:
            verdicts.setdefault(tr["intelligence_id"], []).append(tr.get("verified"))
        row = next((x for x in items if x["work_item_id"] == it["source_task_id"]), None)
        head.append({"item_id": it["item_id"], "work_class": it["work_class"], "verdicts": verdicts,
                     "controller_choice": (row or {}).get("first_choice"), "prior_choice": (row or {}).get("prior_choice"),
                     "controller_choice_verified": any(verdicts.get((row or {}).get("first_choice")) or []),
                     "prior_choice_verified": any(verdicts.get((row or {}).get("prior_choice")) or [])})
    per: dict[str, dict] = {}
    for x in oe.query(e.store, objective_id=oid, tenant_id=controller.context(e)["tenant_id"]):
        if x["stage"] not in ("objective_execution", "objective_calibration") or x["verified"] is None:
            continue
        r = per.setdefault(x["intelligence_id"], {"verified": 0, "failed": 0})
        r["verified" if x["verified"] else "failed"] += 1
    differ = [x for x in items if x["agrees_with_prior"] is False]
    summary = {"work_items": len(items), "agree_with_prior": sum(1 for x in items if x["agrees_with_prior"]),
               "differ_from_prior": len(differ),
               "differ_and_verified": sum(1 for x in differ if x["verified"]),
               "verified": sum(1 for x in items if x["verified"]),
               "verified_first_attempt": sum(1 for x in items if x["verifications"]
                                             and x["verifications"][0]["verdict"] == "VERIFIED"),
               "reselected_or_replaced": sum(1 for x in items if x["latest_choice"] != x["first_choice"]),
               "calibration_head_to_head": [{k: h[k] for k in ("work_class", "controller_choice", "prior_choice",
                                                                "controller_choice_verified", "prior_choice_verified")}
                                            for h in head],
               "evidence_by_intelligence": per,
               "reading": "agreement shows the objective's evidence confirmed the prior; a difference is where this "
                          "objective's evidence changed the choice. Outcomes are observed only for the choice that ran."}
    return {"items": items, "calibration_head_to_head": head, "summary": summary}
