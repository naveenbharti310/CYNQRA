"""Cold-start objective calibration: measure qualified candidates on representative work from this objective before
the real work is bound (mandate 10, 11, 41, 42).

    objective -> requirements -> acceptance criteria -> representative work items -> qualified candidates
              -> bounded calibration -> verified results -> initial objective evidence -> initial bindings

The calibration set is derived from the actual objective: one representative work item per class of work (kind of
work and the role that owns it) that the platform can verify before the work is real (code against its tests and
the delivery contract, a forecast against the platform's backtest, documents against their verifier), taken from
the approved plan's own tasks, important classes first. Proposals, merges and releases are verified by the founder
and the release pipeline, so they are not calibrated; they keep the global prior until execution evidence arrives.

Bounded: never every model on every objective. Candidates are the feasible ones (qualified, available, inside the
hard constraints), at most a policy number per class, chosen for provider and family diversity with the strongest
prior first (intelligence_layer/candidates.py); trials are priced at their upper bound and stop at the calibration
budget (a fraction of the cap, never more than is left).

Stopping, per class, after each round, only once every candidate in it has been tried (one success never stops it):
evidence sufficiency, candidate separation, information value (no remaining candidate can overtake), the risk
tier's round limit and the budget, and never on a best candidate whose verified work has not covered the item's
acceptance criteria (acceptance coverage). Task coverage is on the plan: every class of open work, and whether it was
calibrated, skipped with its reason, not verifiable before the work is real, or beyond the class limit. Then the run
moves from calibration to execution and keeps learning from verified production work.

Integrity: an item's work and acceptance criteria are frozen and content-addressed before any candidate sees them,
and its hash is checked again before each verdict, so a candidate can never adapt the difficulty or the bar. The
verdict comes from the platform's own verifier, never from the candidate; a candidate whose intelligence wrote the
item (it planned the roadmap) is marked, and its result counts for less.
"""
from __future__ import annotations

import json
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import binding, budget, controller, objective_evidence as oe, policies, roles, verifier
from . import attribution as attr
from .db import SECRET, digest, now
from .intelligence import IntelligenceError, ModelSource
from .intelligence_layer import router
from .intelligence_layer.candidates import select as bounded
from .intelligence_layer.registry import RegistryError, served_version

KIND = "calibration_plan"
ALLOWED_EXT = {".py", ".md", ".html", ".json", ".txt", ".css", ".js"}


class _Access:
    """One candidate's access point during a trial: every call goes to that candidate through the run's own call
    path (local models take turns), metered in the registry and charged to the run as verification work."""

    def __init__(self, run, model_id: str, item_id: str):
        self.run, self.model_id, self.item_id = run, model_id, item_id
        self.usd, self.seconds, self.tokens = 0.0, 0.0, 0

    def intelligence_for(self, worker: str) -> str:
        return self.model_id

    def invoke(self, worker: str, request: dict) -> dict:
        out = self.run._call(self.model_id, request, None)
        out.setdefault("model_id", self.model_id)
        return out

    def meter(self, usage: dict, kind: str) -> None:
        reg = self.run.registry
        c = reg.record_call(self.model_id, role="calibration", purpose="calibration", task_kind=kind, usage=usage,
                            run_id=self.run.cid)
        self.usd += c["usd"]
        self.seconds += c["seconds"]
        self.tokens += c["tokens_in"] + c["tokens_out"]
        with self.run.store.atomic():
            n = self.run.store.next_id("call")
            self.run.store.put("call", f"call_{n:04d}", {"id": f"call_{n:04d}", "task_id": f"calibration:{self.item_id}",
                               "worker": "platform", "purpose": "calibration", **usage, "usd": c["usd"],
                               "model_version": c.get("model_version"), "at": now(), **controller.stamp(self.run)})
        self.run.spend("platform", "calibration", c["usd"], "verification")


def plan_id(run) -> str:
    ctx = controller.context(run)
    return f"cal_{ctx['objective_id']}_v{ctx['objective_version']}_c{run.cycle()}"


def _author(run) -> str | None:
    """The intelligence that wrote the roadmap the items come from."""
    boss = run.planner_id()
    return run.model_of(boss) if boss else run.model_of(binding.SYSTEM)


def coverage(run, pol: dict, items: list[dict]) -> dict:
    """Task coverage (mandate 41): every class of open work in this cycle, and what calibration did about it:
    calibrated, skipped with its reason, not verifiable before the work is real, or beyond the class limit."""
    tasks = [t for t in run.tasks() if int(t.get("cycle") or 1) == run.cycle() and t["status"] != "VERIFIED"]
    classes = sorted({t.get("work_class") or f"{t['kind']}:" for t in tasks})
    kinds = {t.get("work_class") or f"{t['kind']}:": t["kind"] for t in tasks}
    mine = {i["work_class"]: i for i in items}
    out = {"work_classes": classes, "calibrated": [], "skipped": {}, "not_verifiable_before_execution": [],
           "beyond_class_limit": []}
    for cls in classes:
        if cls in mine:
            if mine[cls].get("skipped"):
                out["skipped"][cls] = mine[cls]["skipped"]
            else:
                out["calibrated"].append(cls)
        elif kinds[cls] not in pol["kinds"]:
            out["not_verifiable_before_execution"].append(cls)
        else:
            out["beyond_class_limit"].append(cls)
    return out


def _items(run, pol: dict) -> list[dict]:
    tasks = [t for t in run.tasks() if int(t.get("cycle") or 1) == run.cycle() and t["status"] != "VERIFIED"]
    done = {t["id"] for t in run.tasks() if t["status"] == "VERIFIED"}
    by_class: dict[str, list[dict]] = {}
    for t in tasks:
        if t["kind"] not in pol["kinds"]:
            continue
        by_class.setdefault(t.get("work_class") or f"{t['kind']}:", []).append(t)
    builds = {t["id"] for t in tasks if t["kind"] in roles.BUILD_TYPES}
    items = []
    for cls, ts in by_class.items():
        ts.sort(key=lambda t: t["seq"])
        free = [t for t in ts if not (set(t["dependencies"]) & builds - done)]
        src = (free or ts)[0]
        tier, importance = controller._tier([src["kind"]], src.get("requirement_ids") or [], run)
        spec = {k: src.get(k) for k in ("id", "kind", "title", "inputs", "expected_output", "acceptance_criteria",
                                         "requirement_ids", "documents", "owner_worker_id", "acceptance_hash")}
        spec["acceptance"] = src.get("acceptance") or []
        items.append({"item_id": f"ci_{src['id']}", "work_class": cls, "kind": src["kind"],
                      "role": (run.worker(src["owner_worker_id"]) or {}).get("role"), "source_task_id": src["id"],
                      "spec": spec, "spec_hash": digest(spec), "tier": tier, "importance": importance,
                      "dependencies_unmet": not free, "verifier": roles.TASK_TYPES[src["kind"]]["verifier"]})
    items.sort(key=lambda i: (i["importance"] != "critical", controller._RISK_ORDER.index(i["tier"]) * -1,
                              i["spec"]["id"]))
    return items[: int(pol["max_classes"])]


def _feasible(run, t: dict, prefer_n: int) -> tuple[list[dict], dict]:
    work = controller.work_for_task(run, t)
    snap = controller.snapshot(run, work)
    res = router.select(snap)
    rows = {r["id"]: r for r in res["rows"]}
    eligible = [run.registry.get(i) for i in res["ranking"]]
    prefer = res["ranking"][:1]  # the strongest prior is always among the candidates
    pool = bounded(eligible, prefer_n, prefer=prefer)
    return pool, {"ranking": res["ranking"], "excluded": res["excluded"], "rows": rows}


def plan(run) -> dict:
    """The calibration plan for this objective version and cycle: its items, candidates and budget, persisted, or
    the reason there is nothing to calibrate."""
    eff = policies.effective(run.store)
    pol = eff["calibration"]["body"]
    pid = plan_id(run)
    ctx = controller.context(run)
    base = {"plan_id": pid, "objective_id": ctx["objective_id"], "objective_version": ctx["objective_version"],
            "cycle": run.cycle(), "policy_version": eff["calibration"]["version"], "items": [], "trials": [],
            "stopping": {}, "spent_usd": 0.0, "created_at": now()}
    old = run.store.get(KIND, pid)
    if old and old.get("status") in ("completed", "skipped"):
        return old
    if not pol["enabled"]:
        return _skip(run, base, "calibration is turned off in the project's governance")
    cap = budget.headroom(run.store)
    limit = round(min(float(pol["budget_fraction"]) * cap["cap"], max(0.0, cap["headroom"])), 6)
    base["budget_usd"] = limit
    author = _author(run)
    items = []
    for it in _items(run, pol):
        t = run.task(it["source_task_id"])
        pool, info = _feasible(run, t, int(pol["max_candidates"]))
        if len(pool) < 2:
            it["skipped"] = ("a single feasible candidate: nothing to compare; its execution evidence decides"
                             if pool else "no feasible candidate")
            it["candidates"] = [m["id"] for m in pool]
            items.append(it)
            continue
        mature = [m["id"] for m in pool if info["rows"][m["id"]]["quality"]["maturity"] in ("developing", "mature")]
        if len(mature) == len(pool):
            it["skipped"] = "evidence sufficiency: every candidate already has mature objective evidence for this work"
            it["candidates"] = [m["id"] for m in pool]
            items.append(it)
            continue
        out_tokens = max(policies.body("selection")["output_tokens"].get(it["kind"], 3000), 3000)
        it["candidates"] = [m["id"] for m in pool]
        it["upper_bound_usd"] = {m["id"]: budget.call_upper_bound(m, {"prompt": "x" * 12000, "max_tokens": out_tokens})
                                 * 2 for m in pool}  # a trial may take a second call (a reply without files)
        it["author_conflict"] = [m for m in it["candidates"] if m == author]
        items.append(it)
    planned = sum(sum(i.get("upper_bound_usd", {}).values()) for i in items if not i.get("skipped"))
    while planned > limit + 1e-12 and any(not i.get("skipped") for i in items):
        last = [i for i in items if not i.get("skipped")][-1]  # the least important class gives way first
        if len(last["candidates"]) > 2:
            drop = max(last["candidates"][1:], key=lambda c: (last["upper_bound_usd"][c], c))
            last["candidates"].remove(drop)
            last["upper_bound_usd"].pop(drop)
        else:
            # said with its figures, so a skip that comes from a price (paid run 37589136743: hosted models at the
            # worst-case price skipped calibration in both objectives) can be seen for what it is
            need = sum(last["upper_bound_usd"].values())
            last["skipped"] = (f"budget: its trials do not fit the calibration budget (${need:.2f} at most for "
                               f"{len(last['candidates'])} candidates, ${limit:.2f} for all calibration)")
        planned = sum(sum(i.get("upper_bound_usd", {}).values()) for i in items if not i.get("skipped"))
    base.update(items=items, planned_upper_bound_usd=round(planned, 6), author_intelligence=author,
                coverage=coverage(run, pol, items))
    if not any(not i.get("skipped") for i in items):
        return _skip(run, base, "; ".join(sorted({i["skipped"] for i in items})) or "no work the platform can verify "
                     "before it is real")
    base["status"] = "planned"
    run.store.put(KIND, pid, base)
    return base


def _skip(run, base: dict, why: str) -> dict:
    base.update(status="skipped", reason=why[:400], completed_at=now())
    run.store.put(KIND, base["plan_id"], base)
    run.event("intelligence.calibration.completed", "calibration", base["plan_id"], {
        "status": "skipped", "reason": why[:200], "trials": 0}, actor="intelligence_controller")
    return base


def run_plan(run, p: dict) -> dict:
    """Run a planned calibration, round by round, until every class has stopped."""
    if p.get("status") != "planned":
        return p
    pol = policies.effective(run.store)["calibration"]["body"]
    p.update(status="running", started_at=now())
    run.store.put(KIND, p["plan_id"], p)
    run.event("intelligence.calibration.started", "calibration", p["plan_id"], {
        "items": [i["item_id"] for i in p["items"] if not i.get("skipped")],
        "candidates": {i["item_id"]: i["candidates"] for i in p["items"] if not i.get("skipped")},
        "budget_usd": p["budget_usd"], "policy": p["policy_version"]}, actor="intelligence_controller")
    lock = threading.Condition()
    held = {"usd": 0.0}  # the upper bounds of trials in flight: items run side by side within one budget

    def item(it: dict) -> None:
        if it.get("skipped"):
            with lock:
                p["stopping"][it["item_id"]] = {"stopped": True, "reason": it["skipped"]}
            return
        rounds = int(pol["max_rounds"].get(it["tier"], 1))
        todo = list(it["candidates"])
        for rnd in range(1, rounds + 1):
            if not todo:
                break
            with lock:
                while True:  # what does not fit now may fit once the trials in flight have cost what they cost
                    room = p["budget_usd"] - p["spent_usd"] - held["usd"]
                    fit = [c for c in todo if it["upper_bound_usd"][c] <= room + 1e-12]
                    if fit or held["usd"] <= 0:
                        break
                    lock.wait()
                todo = fit
                if not todo:
                    p["stopping"][it["item_id"]] = {"stopped": True, "reason": "budget", "round": rnd}
                    break
                reserve = sum(it["upper_bound_usd"][c] for c in todo)
                held["usd"] += reserve
            try:
                trials = _round(run, p, it, todo, rnd)
            finally:
                with lock:
                    held["usd"] -= reserve
                    lock.notify_all()
            with lock:
                p["trials"] += trials
                p["spent_usd"] = round(p["spent_usd"] + sum(t["usd"] for t in trials), 6)
                run.store.put(KIND, p["plan_id"], p)
                seen = list(p["trials"])
            stop, why, todo = _stop(run, it, rnd, rounds, pol, seen)
            if stop:
                with lock:
                    p["stopping"][it["item_id"]] = {"stopped": True, "reason": why, "round": rnd}
                break
        with lock:
            p["stopping"].setdefault(it["item_id"], {"stopped": True, "reason": "max_rounds", "round": rounds})

    # items side by side when every candidate is hosted (the real run of 7 Oct: three items one after another took 10
    # of the objective's first 14 minutes, each round waiting on its slowest model); a model on this machine is
    # still asked one thing at a time
    hosted = all(not run.registry.get(c).get("local") for it in p["items"] for c in it.get("candidates") or [])
    if hosted and len(p["items"]) > 1:
        with ThreadPoolExecutor(max_workers=len(p["items"]), thread_name_prefix="calibration-item") as pool:
            list(pool.map(item, p["items"]))
    else:
        for it in p["items"]:
            item(it)
    p.update(status="completed", completed_at=now())
    run.store.put(KIND, p["plan_id"], p)
    verified = sum(1 for t in p["trials"] if t.get("verified"))
    cov = p.get("coverage") or {}
    run.event("intelligence.calibration.completed", "calibration", p["plan_id"], {
        "status": "completed", "trials": len(p["trials"]), "verified": verified, "spent_usd": p["spent_usd"],
        "stopping": {k: v["reason"] for k, v in p["stopping"].items()},
        "coverage": {"work_classes": len(cov.get("work_classes") or []), "calibrated": len(cov.get("calibrated") or []),
                     "acceptance_covered": sorted(i["item_id"] for i in p["items"] if not i.get("skipped") and any(
                         covered(i, p["trials"], c) for c in i.get("candidates") or []))}},
        actor="intelligence_controller")
    return p


def _round(run, p: dict, it: dict, todo: list[str], rnd: int) -> list[dict]:
    hosted = [c for c in todo if not run.registry.get(c).get("local")]
    local = [c for c in todo if c not in hosted]
    out = []
    if len(hosted) > 1:
        with ThreadPoolExecutor(max_workers=min(len(hosted), 4), thread_name_prefix="calibration") as pool:
            out += list(pool.map(lambda c: _trial(run, p, it, c, rnd), hosted))
    else:
        out += [_trial(run, p, it, c, rnd) for c in hosted]
    out += [_trial(run, p, it, c, rnd) for c in local]
    return out


def _write(out: Path, files: dict) -> list[str]:
    """A candidate's files, under the same rules a worker's writes meet at the gateway."""
    refused = []
    for name, text in (files or {}).items():
        rel = Path(str(name))
        if (not isinstance(text, str) or rel.is_absolute() or ".." in rel.parts or rel.suffix not in ALLOWED_EXT
                or len(rel.parts) > 3 or len(text.encode("utf-8")) > 200_000 or SECRET.search(text)):
            refused.append(str(name))
            continue
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    return refused


def _trial(run, p: dict, it: dict, cand: str, rnd: int) -> dict:
    """One candidate on one representative item: its answer, checked by the platform's verifier for the item's
    kind, recorded as objective calibration evidence."""
    tid = f"{it['item_id']}_{cand}_r{rnd}"
    folder = run.dir / "calibration" / tid
    shutil.rmtree(folder, ignore_errors=True)
    out = folder / "out"
    out.mkdir(parents=True, exist_ok=True)
    access = _Access(run, cand, it["item_id"])
    src = ModelSource()
    src.bind(access)
    spec = json.loads(json.dumps(it["spec"]))  # the candidate works on a copy; the frozen spec stays as it is
    owner = spec["owner_worker_id"]
    crit = "; ".join(spec.get("acceptance_criteria") or [])
    handoff = {"acceptance_check": f"{spec['title']}. Expected: {spec.get('expected_output')}. Acceptance criteria: "
                                   f"{crit}. Return the files themselves: tools are not available in this step.",
               "context_ref": "objective calibration", "artifacts": []}
    trial = {"trial_id": tid, "item_id": it["item_id"], "intelligence_id": cand, "round": rnd, "at": now(),
             "verified": None, "usd": 0.0}
    try:
        entry = run.registry.get(cand)
        trial["served_version"] = served_version(entry)
        result, usage = src.work(spec, worker=owner, objective=run.objective_ctx(), rules=run.rules(), handoff=handoff,
                                 inbox={}, feedback="", previous={}, repo_files=[], persona=run.persona(owner),
                                 answerers=[(run.worker(owner) or {}).get("reports_to") or "founder"])
        access.meter(usage, it["kind"])
        failure, verified, method, checks = None, None, "", {}
        if digest(it["spec"]) != it["spec_hash"]:  # the item moved: no verdict counts
            failure = attr.failure("specification", "the calibration item changed after it was frozen")
        elif isinstance(result, dict) and result.get("result") == "blocked":
            failure = attr.failure("specification", "the candidate raised a Blocker: a fact it needed is missing",
                                   str(result.get("description") or ""))
        else:
            files = result.get("files") if isinstance(result, dict) else None
            refused = _write(out, files if isinstance(files, dict) else {})
            if refused:
                trial["refused_files"] = refused[:10]
            cand_dir = folder / "candidate"
            if cand_dir.exists():
                shutil.rmtree(cand_dir)
            shutil.copytree(run.paths["integration"], cand_dir)
            for f in out.rglob("*"):
                if f.is_file():
                    target = cand_dir / verifier.repo_path(f.relative_to(out))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, target)
            r = verifier.run_checks(it["kind"], cand_dir, out, spec, run.objective()["structured"])
            if digest(it["spec"]) != it["spec_hash"]:
                failure = attr.failure("specification", "the calibration item changed during the trial")
            else:
                verified, method, checks = bool(r["passed"]), r["method"], r["checks"]
                if not verified:
                    failure = attr.verification_failure(r["feedback"], checks)
                    if failure["kind"] != attr.INTELLIGENCE:
                        verified = None
        owned = any(k in method for k in ("backtest", "delivery contract", "document verifier"))
        vk = "deterministic_platform" if owned or it["kind"] == "document" else "deterministic_with_own_tests"
        trial.update(verified=verified, method=method, attribution=(failure or {}).get("kind"))
        t_like = {**spec, "id": it["source_task_id"], "attempts": 0, "outputs": [
            {"file": f.relative_to(out).as_posix(), "hash": digest(f.read_bytes())} for f in sorted(out.rglob("*"))
            if f.is_file()], "acceptance_hash": it["spec"].get("acceptance_hash"),
            "work_class": it["work_class"], "requirement_ids": spec.get("requirement_ids") or []}
        ev = controller.record_task_evidence(
            run, t_like, verified=verified, failure=failure, verifier_kind=vk, stage="objective_calibration",
            intelligence=(cand, trial["served_version"]), idempotency_key=f"calibration:{p['plan_id']}:{tid}",
            extra={"source": "calibration", "calibration_item": it["item_id"], "calibration_plan": p["plan_id"],
                   "spec_hash": it["spec_hash"], "author_conflict": cand in (it.get("author_conflict") or []),
                   "dependencies_unmet": bool(it.get("dependencies_unmet")), "attempt_kind": "calibration",
                   "cost_usd": round(access.usd, 6), "latency_s": round(access.seconds, 2), "tokens": access.tokens,
                   "verification": {"verification_id": None, "method": method, "verifier_kind": vk, "independent": True,
                                    "quality": policies.body("verification")["quality"][vk],
                                    "checks_hash": digest(checks), "record_hash": None, "verifier_intelligence": None,
                                    "test_ids_count": len((checks or {}).get("failed") or [])}})
        trial["evidence_id"] = (ev or {}).get("evidence_id")
        if verified is not None:
            run.registry.record_outcome(cand, role="calibration", task_kind=it["kind"], task_id=tid, run_id=run.cid,
                                        attempt=rnd, verified=verified, usd=access.usd, seconds=access.seconds,
                                        tokens=access.tokens, failure=(failure or {}).get("detail") or "",
                                        source="objective_calibration",
                                        tenant_id=controller.context(run)["tenant_id"],
                                        workspace_id=controller.context(run)["workspace_id"],
                                        objective_id=controller.objective_id(run),
                                        model_version=trial["served_version"])
    except (IntelligenceError, RegistryError, OSError) as exc:
        failure = attr.call_failure(str(exc)) if isinstance(exc, IntelligenceError) else \
            attr.failure("environment", "the trial could not run on this machine", str(exc))
        trial.update(verified=None, attribution=failure["kind"], error=str(exc)[:300])
        try:  # a provider failure is recorded, contaminated: inconclusive, never an intelligence failure
            ev = controller.record_task_evidence(
                run, {**it["spec"], "id": it["source_task_id"], "attempts": 0, "outputs": []}, verified=None,
                failure=failure, stage="objective_calibration", intelligence=(cand, trial.get("served_version")),
                idempotency_key=f"calibration:{p['plan_id']}:{tid}", extra={"source": "calibration",
                                                                           "calibration_item": it["item_id"],
                                                                           "attempt_kind": "calibration"})
            trial["evidence_id"] = (ev or {}).get("evidence_id")
        except oe.EvidenceError:
            pass
    finally:
        trial["usd"] = round(access.usd, 6)
        shutil.rmtree(folder, ignore_errors=True)
    return trial


def covered(it: dict, trials: list[dict], intelligence_id: str) -> bool:
    """Acceptance coverage (mandate 41): a verified trial of this intelligence on this item, which means the
    platform's verifier passed every mandatory acceptance criterion of the item."""
    return any(t.get("item_id") == it["item_id"] and t.get("intelligence_id") == intelligence_id and t.get("verified")
               for t in trials)


def _stop(run, it: dict, rnd: int, rounds: int, pol: dict, trials: list[dict] | None = None
          ) -> tuple[bool, str, list[str]]:
    """Whether this class's calibration stops after round rnd, why, and who is still worth another trial. It never
    settles on a best candidate whose verified work has not yet covered the item's acceptance criteria."""
    t = run.task(it["source_task_id"])
    work = controller.work_for_task(run, t)
    pool = [run.registry.get(c) for c in it["candidates"]]
    res = router.select(controller.snapshot(run, work, pool=pool))
    rows = sorted([r for r in res["rows"] if not r["violations"]], key=lambda r: (-r["quality"]["lcb"], r["id"]))
    if not rows:
        return True, "no feasible candidate is left", []
    best, others = rows[0], rows[1:]
    if not others:
        return True, "a single feasible candidate is left", []
    alive = [r["id"] for r in others if r["quality"]["ucb"] >= best["quality"]["lcb"]]
    if not covered(it, trials or [], best["id"]):
        if rnd >= rounds:
            return True, ("max_rounds: no verified trial covered the item's acceptance criteria within the bounded "
                          "rounds; execution evidence decides from here"), []
        return False, "", [best["id"]] + alive
    second = max(others, key=lambda r: r["quality"]["ucb"])
    if best["quality"]["lcb"] >= second["quality"]["ucb"]:
        return True, "candidate_separation", []
    if router._rank(best["quality"]["maturity"]) >= router._rank(pol["sufficient_maturity"]) and \
            best["quality"]["mean"] >= 0.5:
        return True, "evidence_sufficiency", []
    if not alive:
        return True, "information_value: no other candidate can overtake the best", []
    if rnd >= rounds:
        return True, "max_rounds: not separated within the bounded rounds; execution evidence decides from here", []
    return False, "", [best["id"]] + alive


def calibrate(run) -> dict:
    """Plan and run this objective version's calibration. Returns the plan with its trials and stopping reasons."""
    p = plan(run)
    return run_plan(run, p) if p.get("status") == "planned" else p


def summary(p: dict | None) -> list[str]:
    """The roadmap gate's lines about calibration: what was measured, what it cost, why it stopped."""
    if not p:
        return []
    if p.get("status") == "skipped":
        return [f"Calibration on this objective's own work: skipped ({p.get('reason')})."]
    lines = [f"Calibration on this objective's own work: {len(p['trials'])} trial(s) on "
             f"{sum(1 for i in p['items'] if not i.get('skipped'))} kind(s) of work, ${p['spent_usd']:.4f} of its "
             f"${p['budget_usd']:.4f} budget."]
    for it in p["items"]:
        mine = [t for t in p["trials"] if t["item_id"] == it["item_id"]]
        if it.get("skipped"):
            lines.append(f"  {it['work_class']}: not calibrated ({it['skipped']}).")
            continue
        res = ", ".join(f"{t['intelligence_id']} {'passed' if t['verified'] else 'failed' if t['verified'] is False else 'inconclusive'}"
                        for t in mine)
        lines.append(f"  {it['work_class']} on {it['source_task_id']}: {res}; stopped: "
                     f"{(p['stopping'].get(it['item_id']) or {}).get('reason')}.")
    return lines
