"""The orchestrator: one company, one objective, one run, along the product definition's canonical flow
(Cynqra Product Flows and Architecture v1, section 3). It owns the run's state and the founder's gates; the work of
every stage is done by an engine that sees the run only through the run contract (run.py):

  Stage 0-1  objective.py     the founder's objective structured, then decomposed into outcomes, requirements and
                              risks: the list the team is built from
  Stage 2-3  synthesis.py     the organization the objective needs, and the workforce approval gate
             seats.py         every seat earns its place: seat cards, the independent challenge, the lean team,
                              and the check of the plan's work
  Stage 4    intelligence_layer  the Intelligence Router binds an intelligence to every worker, from the
                              registry's evidence; every call goes through the Intelligence Gateway
  Stage 5    planner.py       milestones, tasks, acceptance criteria, owners, accountability
  Stage 6-7  budget.py        the roadmap gate, with the budget in layers against the hard cap (US dollars only)
  Stage 8    gateway.py       every worker action: identity, policy, budget, target check, execute, sanitize, audit
             execution.py     each task's lifecycle, Handoff to verified
  Stage 9    verifier.py      completed is not verified: every task type has its verifier
  Stage 10   performance.py   intelligence measured per worker and task
             replacement.py   kept, rerouted or replaced while the worker's identity stays
  Delivery   delivery.py      the release, the final report, replay and the export

WORKER is not INTELLIGENCE is not PROVIDER CONNECTION is not CREDENTIAL. Workers hold no model: each is bound to an
intelligence (binding.py). A live run is staffed from the app's Intelligence Layer (the providers the founder
connected, or the intelligence the environment names); a demo run stands its scenario's script in an Intelligence
Layer of its own. Everything the founder does is a labelled decision (D-10).
"""
from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
import time
import uuid
from datetime import datetime
from pathlib import Path

from . import binding, budget, calibration, controller, delivery, deploy, execution, gateway, numbers, objective
from . import objective_evidence, people, performance, planner, policies, policy, replacement, roles, seats, synthesis
from . import settings as project_settings
from .db import IST, Store, digest, now
from .intelligence import SCENARIOS, IntelligenceError, ModelSource, ScriptedSource
from .intelligence_layer import IntelligenceSupply, SupplyError, VersionChanged, router
from .intelligence_layer.registry import RegistryError
from .protocol import ProtocolError, build

DEFAULT_SCENARIO = "candidate_tracker"  # the smallest demo, for self-tests; the app opens on Bluedip (ui/app.js)
# One model on this machine answers one call at a time: local calls take turns; hosted ones run side by side.
_LOCAL_CALLS = threading.Lock()


# Decisions the proposer can revise with the CEO's note. For the others (an escalation, the budget cap, a provider
# account, an outage, the delivery, a change of objective) "request more evidence" would act as a rejection, which
# can stop the run, so it is refused: those take approve or reject.
EVIDENCE_KINDS = ("decision", "review_merge", "deploy", "approve_workforce", "approve_roadmap")


class EngineError(RuntimeError):
    pass


class BudgetHold(RuntimeError):
    """A model call did not start: spent plus in-flight reservations plus its own upper bound would pass the cap.
    The work waits; it is not a failure of anyone's intelligence."""

    def __init__(self, message: str, reservation: dict):
        super().__init__(message)
        self.reservation = reservation


def scenarios() -> list[dict]:
    """The prepared demos: each one a scenario folder with a scenario.json."""
    out = []
    for p in sorted(SCENARIOS.glob("*/scenario.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        out.append({"id": p.parent.name, "title": d.get("title") or p.parent.name, "about": d.get("about", ""),
                    "messy": d["messy"]})
    return out


class Engine:
    """The run. It implements the run contract (run.Run) for the engines, and the founder's controls for the app."""

    def __init__(self, data_dir: Path, intelligence=None, supply: IntelligenceSupply | None = None,
                 memory: Path | None = None, tenant: str | None = None, workspace: str | None = None):
        self.dir = Path(data_dir).resolve()  # workers' tests run from inside it: a relative path would break them
        # what Cynqra learns across projects (lessons.py): the app keeps it beside every run; a lone run keeps its own
        self.memory = Path(memory) if memory else self.dir / "lessons.json"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.store = Store(str(self.dir / "cynqra.db"))
        self.paths = {k: self.dir / k for k in ("workspaces", "integration", "main", "releases", "live", "exports",
                                                 "verify")}
        for p in self.paths.values():
            p.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self._injected = intelligence  # a test's source; it is bound to this run like any other
        self._shared = supply  # the app's Intelligence Layer, for live runs
        self._own: IntelligenceSupply | None = None  # a run's own: the demo's script, or a run without an app
        self.supply: IntelligenceSupply | None = None
        self.intel = None
        self.live_proc = None
        self._tls = threading.local()  # the task a worker thread is acting on, and the budget it has reserved
        if self.store.get("meta", "run") is None:
            # the tenant and workspace this run's evidence belongs to: another tenant's evidence is never this one's
            self.store.put("meta", "run", {"company_id": "co_" + uuid.uuid4().hex[:8], "phase": "new", "mode": "demo",
                                           "scenario": None, "frozen": False, "created_at": now(), "notice": "",
                                           "objective_id": "obj_" + uuid.uuid4().hex[:12],
                                           "tenant_id": tenant or os.environ.get("CYNQRA_TENANT_ID") or "local",
                                           "workspace_id": workspace or os.environ.get("CYNQRA_WORKSPACE_ID") or "local"})
        if self.meta["phase"] != "new":
            self._attach(strict=False)  # a run reopened after a restart opens even if its model is gone for now
            self._refuse_outdated()

    OUTDATED = ("This project was made by an earlier version of Cynqra, whose team had roles that no longer exist "
                "(such as the Business Lead: you are the CEO now, with cofounders). It can be read and exported, but "
                "not continued. Start a new run; this one is kept in the archive.")

    LEAN_IN_DEMO = ("The demo's script has a plan for the recommended team only. In live mode Cynqra plans the work "
                    "for whichever team you choose.")

    def _refuse_outdated(self) -> None:
        """A run saved before the catalog changed can hold a worker whose role is gone. It is stopped with a plain
        reason instead of failing on that worker's first step, again and again."""
        unknown = sorted({w["role"] for w in self.workers() if w.get("role") not in roles.ROLES})
        if unknown and self.meta["phase"] not in ("accepted", "delivered"):
            self.set_meta(phase="stopped_error", failed_stage="outdated", notice=self.OUTDATED)

    # --- the run's state ---------------------------------------------------------------------------------------
    @property
    def meta(self) -> dict:
        return self.store.get("meta", "run")

    def set_meta(self, **kw) -> dict:
        with self.store.lock:  # read, change and write as one: the kill switch from another request is never lost
            m = self.meta
            m.update(kw)
            return self.store.put("meta", "run", m)

    @property
    def cid(self) -> str:
        return self.meta["company_id"]

    def _require(self, *phases: str) -> None:
        if self.meta["phase"] not in phases:
            raise EngineError(f"not allowed in phase {self.meta['phase']}; needs {' or '.join(phases)}")

    # --- intelligence: the Intelligence Layer, through each worker's binding ----------------------------------
    @property
    def registry(self):
        return self.supply.registry if self.supply else None

    def _local_supply(self) -> IntelligenceSupply:
        if self._own is None:
            self._own = IntelligenceSupply(self.dir / "intelligence")
        return self._own

    def _attach(self, strict: bool = True) -> None:
        """Bind the run to its Intelligence Layer and its source. A demo stands its scenario's script in an
        Intelligence Layer of its own; a live run uses the app's, and when nothing connected there is available,
        the intelligence the environment names. strict: a new live run with no intelligence is refused; a reopened
        one opens, and its next call fails like any model error."""
        m = self.meta
        if m["mode"] == "demo":
            sup = self._local_supply()
            title = f"Demo script ({m['scenario']})"
            conn = sup.connections.find(origin="demo", name=title) or sup.connections.create(
                {"type": "demo_script", "name": title, "auth": {"method": "none"}, "models": [m["scenario"]]},
                origin="demo")
            sup.discover(conn["id"])
            source = self._injected or ScriptedSource(m["scenario"])
        else:
            sup = self._shared or self._local_supply()
            if not sup.registry.available():
                sup.connect_environment()
            if strict and not sup.registry.available():
                # discovered is not qualified: what is connected does its qualification work first (bounded), and
                # only what passes may be assigned
                sup.qualify()
            if strict and not sup.registry.available():
                raise EngineError("live mode needs intelligence: connect a provider (OpenAI-compatible, Anthropic or "
                                  "a model on this machine), or name one in the environment; what is connected must "
                                  "pass its qualification work first")
            source = self._injected or ModelSource()
        source.bind(self)
        self.supply, self.intel = sup, source
        reg = sup.registry
        models = reg.models()
        found = {"available": sorted(m["id"] for m in models if reg.availability(m)[0]),
                 "unverified": sorted(m["id"] for m in models if (m.get("regression") or {}).get("status") == "unverified"),
                 "failed": sorted(m["id"] for m in models if (m.get("regression") or {}).get("status") == "failed")}
        self.event("intelligence.discovered", "company", self.cid, {"models": len(models), **{k: v[:40] for k, v in
                   found.items()}, "counts": {k: len(v) for k, v in found.items()}}, actor="intelligence_supply",
                   idempotency_key=f"discovered:{self.cid}:{digest(found)}")

    def _task_ctx(self) -> str | None:
        return getattr(self._tls, "task_id", None)

    def _resolve(self, worker_id: str) -> tuple[str, str | None]:
        """The intelligence and pinned version for a worker's call now: the task's own binding when the worker owns
        the task being worked on and it is the newer decision, else the worker's binding; a review the policy wants
        independent goes to an intelligence other than the producer's (controller.reviewer)."""
        tid = self._task_ctx()
        review = getattr(self._tls, "review_for", None)
        if review and worker_id.startswith("w_"):
            got = controller.reviewer(self, self.task(review), worker_id)
            if got:
                return got
        if worker_id.startswith("w_") and binding.current(self.store, worker_id):
            eff = binding.effective(self, worker_id, tid)
            if eff:
                return eff
        sys_ = binding.current(self.store, binding.SYSTEM)
        if sys_ is not None:
            try:
                if self.registry.availability(self.registry.get(sys_["intelligence_id"]))[0]:
                    return sys_["intelligence_id"], sys_.get("version")
            except RegistryError:
                pass
        mid = controller.system_intelligence(self)
        return mid, (binding.current(self.store, binding.SYSTEM) or {}).get("version")

    def intelligence_for(self, worker_id: str) -> str:
        """The intelligence that does a worker's call now (its task's binding, or its own). Work that belongs to no
        worker (structuring the objective, synthesizing the workforce) runs on the intelligence the controller
        decided for the control plane."""
        return self._resolve(worker_id)[0]

    def model_for(self, worker_id: str, task_id: str | None) -> str | None:
        eff = binding.effective(self, worker_id, task_id)
        return eff[0] if eff else self.model_of(worker_id)

    def invoke(self, worker_id: str, request: dict) -> dict:
        """One call for a worker, through the Intelligence Gateway to the intelligence it is bound to, at the
        version its binding pinned. A new version continues only after its regression check passes. During
        governed execution the call first reserves its upper-bound cost: one that would pass the cap with what is
        already spent and in flight does not start."""
        who = worker_id if worker_id.startswith("w_") and binding.current(self.store, worker_id) else binding.SYSTEM
        mid, pin = self._resolve(worker_id)
        self._reserve(worker_id, mid, request)
        try:
            out = self._call(mid, request, pin)
        except VersionChanged as exc:
            replacement.version_changed(self, who, exc, task_id=self._task_ctx())  # kept after its check, or rebound
            mid, pin = self._resolve(worker_id)
            out = self._call(mid, request, pin)
        except SupplyError as exc:
            raise IntelligenceError(str(exc), model_id=mid) from exc
        if who == binding.SYSTEM and out.get("error"):
            out = self._system_failover(request, mid, out)
        return out

    def _system_failover(self, request: dict, mid: str, out: dict) -> dict:
        """The control plane's call failed on the provider's or the account's side: the next qualified intelligence
        takes the control plane's work (controller.system_failover), each at most once for this call. A failure the
        intelligence caused, or no alternative left, comes back as it was."""
        from . import attribution as attr
        tried = [mid]
        while out.get("error") and not attr.clean(attr.call_failure(out["error"])):
            alt = controller.system_failover(self, tried[-1], out["error"], tried=tried)
            if alt is None or alt in tried:
                break
            tried.append(alt)
            try:
                out = self._call(alt, request, (binding.current(self.store, binding.SYSTEM) or {}).get("version"))
            except SupplyError as exc:
                raise IntelligenceError(str(exc), model_id=alt) from exc
        return out

    def _reserve(self, worker_id: str, mid: str, request: dict) -> None:
        tid = self._task_ctx()
        if not tid or self.meta["phase"] not in policies.body("budget")["reserve_in_phases"]:
            return
        entry = self.registry.get(mid)
        usd = budget.call_upper_bound(entry, request, self.registry.stats(mid).get("write_tps"))
        res = budget.reserve(self.store, worker_id=worker_id, task_id=tid, model_id=mid, usd=usd,
                             purpose="model_call")
        if res["status"] == "held":
            self._tls.reservations = getattr(self._tls, "reservations", []) + [res["id"]]
            return
        self._budget_hold(res)
        raise BudgetHold(res["why"], res)

    def _budget_hold(self, res: dict) -> None:
        """A refused reservation: while other work is in flight, this work waits for it to settle; when nothing is in
        flight, the breaker opens and the founder decides, as when the cap is reached."""
        self.event("budget.reservation_refused", "company", self.cid, {"task_id": res["task_id"], "usd": res["usd"],
                   "spent_usd": res["spent_before"], "reserved_usd": res["reserved_before"],
                   "in_flight": res.get("in_flight", 0)}, actor="budget_engine", policy_decision="DENY",
                   correlation_id=res["task_id"])
        if res.get("in_flight"):
            return
        with self.store.atomic():
            L = budget.ledger(self.store)
            if L["state"] == "breaker" or any(d["kind"] == "budget_breaker" for d in self.pending_decisions()):
                return
            L["state"] = "breaker"
            self.store.put("budget", "ledger", L)
        cap = project_settings.get(self.store)["budget_usd"]
        need = round((res["spent_before"] + res["usd"]) * 1.5, 4)
        self.decision("budget_breaker", problem="The next AI call would take spending past the budget cap. All work is "
                      "paused before it is spent.",
                      recommendation=f"Raise the budget from ${cap:.2f} to ${max(cap * 1.5, need):.2f}, or stop the run.",
                      risk="HIGH", confidence="high", cost="none until work resumes",
                      evidence=[f"spent {budget.dollars(res['spent_before'])}, in flight "
                                f"{budget.dollars(res['reserved_before'])}, the next call up to "
                                f"{budget.dollars(res['usd'])}, cap {budget.dollars(cap)}"],
                      change="Nothing: the cap is yours to set.", severity="SEV-2", source="budget_engine",
                      extra={"needed_cap": max(cap * 1.5, need), "reservation": res["id"]})
        objective.transition(self, "OBJECTIVE_BLOCKED", "the budget cap would be passed", by="budget_engine")

    def _call(self, mid: str, request: dict, pin: str | None) -> dict:
        """The model call itself, the slow part, made without holding the run: while one worker waits for its
        intelligence, the others record their results. Everything before and after the call is serialized."""
        local = bool(self.registry.get(mid).get("local"))
        owned = self.lock._is_owned()
        state = self.lock._release_save() if owned else None
        try:
            if local:
                with _LOCAL_CALLS:
                    return self.supply.gateway.invoke(mid, request, pinned_version=pin)
            return self.supply.gateway.invoke(mid, request, pinned_version=pin)
        finally:
            if owned:
                self.lock._acquire_restore(state)

    def _staff(self, refine: bool = False) -> None:
        """Stage 4: an intelligence for every worker; once the roadmap exists, refined to the kinds of the tasks
        each worker owns (one intelligence can power many workers, and two workers of one role can run on
        different ones). Every choice is a binding with the Router's whole table."""
        workload = None
        if refine:
            workload = {}
            for t in self.tasks():
                kinds = workload.setdefault(t["owner_worker_id"], [])
                if t["kind"] not in kinds:
                    kinds.append(t["kind"])
            for t in self.tasks():  # cofounders hand out and review their team's work: that is work too
                for who, kind in ((t.get("handoff_from"), "assign"), (t.get("reviewed_by"), "review")):
                    if who and who.startswith("w_") and kind not in workload.setdefault(who, []):
                        workload[who].append(kind)
        try:
            staffing = controller.staff(self, self.workers(), workload, refine=refine)
        except router.RouterError as exc:
            raise IntelligenceError(str(exc)) from exc
        for wid, s in staffing.items():
            if refine and self.model_of(wid) == s["model_id"]:
                controller.bind_worker(self, self.worker(wid), s, "")
                continue
            why = ("refined to the roadmap's workload: " if refine else
                   "the strongest evidenced intelligence for its role's work: ") + ", ".join(s["kinds"]) + ". " + \
                s["decision"]["selection_reason"]
            controller.bind_worker(self, self.worker(wid), s, why)

    # --- the run contract: the audit trail and the founder's inbox ---------------------------------------------
    def event(self, event_type: str, aggregate_type: str, aggregate_id: str, payload: dict, *,
              actor: str = "orchestrator", actor_type: str = "service", correlation_id: str | None = None,
              policy_decision: str = "ALLOW", authority: str = "platform", protocol_hash: str | None = None,
              test_ids: list | None = None, context_refs: list | None = None, causation_id: str | None = None,
              idempotency_key: str | None = None, aggregate_version: int | None = 1) -> dict:
        """An event in the run's log: its causation (the event that caused it, else the one before), an idempotency
        key (a retried write returns the event already there) and the aggregate's own version when asked for."""
        return self.store.append(
            company_id=self.cid, event_type=event_type, aggregate_type=aggregate_type, aggregate_id=aggregate_id,
            actor_type=actor_type, actor_id=actor, payload=payload, correlation_id=correlation_id or aggregate_id,
            policy_decision=policy_decision, authority_snapshot=authority, protocol_hash=protocol_hash,
            test_ids=test_ids, context_refs=context_refs, causation_id=causation_id, idempotency_key=idempotency_key,
            aggregate_version=aggregate_version)

    def decision(self, kind: str, *, problem: str, recommendation: str, risk: str, confidence: str, cost: str,
                 evidence: list, change: str, task_id: str | None = None, action_type: str | None = None,
                 severity: str = "SEV-3", source: str = "orchestrator", extra: dict | None = None) -> dict:
        # what a model wrote is shown to the CEO as text, whatever type it arrived as
        problem, recommendation, confidence, cost, change = (
            v if isinstance(v, str) else "" if v is None else json.dumps(v, ensure_ascii=False)
            for v in (problem, recommendation, confidence, cost, change))
        today = datetime.now(IST).date().isoformat()
        worker_raised = source.startswith("w_")
        todays = [d for d in self.store.all("decision")  # what a cofounder settled never interrupted the founder
                  if d.get("created_day") == today and d.get("source", "").startswith("w_")
                  and d.get("outcome_label") != "settled_by_cofounder"]
        digest_it = worker_raised and len(todays) >= delivery.ESCALATIONS_PER_DAY and severity != "SEV-1"
        base = "dec_" + (task_id or kind)
        did = base + ("_" + uuid.uuid4().hex[:4] if self.store.get("decision", base) else "")
        d = {"id": did, "company_id": self.cid, "kind": kind, "task_id": task_id, "action_type": action_type,
             "problem": problem, "evidence_refs": evidence, "recommendation": recommendation, "cost": cost,
             "risk": risk, "confidence": confidence, "what_would_change_this": change, "status": "pending",
             "outcome_label": None, "labeled_by": None, "labeled_at": None, "resolved_by": None, "resolved_at": None,
             "created_at": now(), "created_day": today, "source": source, "severity": severity,
             "in_digest": digest_it, "extra": extra or {}}
        self.store.put("decision", did, d)
        self.event("decision.created", "decision", did, {"kind": kind, "risk": risk, "task_id": task_id,
                   "in_digest": digest_it, "severity": severity,
                   "settled_by": (extra or {}).get("settled_by")}, actor=source,
                   actor_type="worker" if worker_raised else "service", correlation_id=task_id or did,
                   policy_decision="REQUIRE_APPROVAL")
        return d

    def intervention(self, ref: str, what: str) -> None:
        n = self.count("intervention") + 1
        self.store.put("intervention", f"int_{n:03d}", {"id": f"int_{n:03d}", "ref": ref, "action": what,
                                                        "counts": True, "at": now()})

    def count(self, kind: str) -> int:
        return len(self.store.all(kind))

    # --- the run contract: the objective, the organization, the work ------------------------------------------
    def objective(self) -> dict | None:
        return self.store.get("objective", "obj_1")

    def objective_ctx(self) -> dict:
        obj = self.objective()
        return {**obj["structured"], "_constraints": obj.get("founder_constraints") or {}}

    def requirements(self) -> dict | None:
        return self.store.get("requirements", "req_1")

    def founder(self) -> dict:
        """What the founder brings: the seats they lead themselves, their stage and their time."""
        company = self.store.get("company", self.cid) or {}
        return objective.founder_profile(company.get("founder") or objective.FOUNDER_DEFAULT)

    def proposal(self) -> dict | None:
        return synthesis.current(self)

    def rules(self) -> list[str]:
        return (self.store.get("memory", "decided_rules") or {}).get("rules", [])

    def worker(self, wid: str) -> dict | None:
        return self.store.get("worker", wid)

    def workers(self) -> list[dict]:
        return self.store.all("worker")

    def model_of(self, wid: str) -> str | None:
        return binding.intelligence_of(self.store, wid)

    def persona(self, wid: str) -> str:
        w = self.worker(wid)
        return roles.prompt_text(w, self.workers()) if w else ""

    def planner_id(self) -> str | None:
        """Who writes the roadmap: the Project Manager, else a cofounder."""
        return roles.planner(self.workers())

    def tasks(self) -> list[dict]:
        return [self.store.get("task", t) for t in (self.store.get("plan", "plan_1") or {}).get("order", [])]

    def task(self, tid: str) -> dict:
        t = self.store.get("task", tid)
        if t is None:
            raise EngineError(f"unknown task {tid}")
        return t

    def save_task(self, t: dict) -> dict:
        return self.store.put("task", t["id"], t)

    def workspace(self, wid: str, tid: str) -> Path:
        p = self.paths["workspaces"] / wid / tid
        (p / "inbox").mkdir(parents=True, exist_ok=True)
        (p / "out").mkdir(parents=True, exist_ok=True)
        return p

    def send(self, kind: str, content: dict | None, routing: dict, task_id: str, sender: str) -> dict:
        obj = build(kind, content, routing, task_id)
        h = self.store.put_object("protocol", obj)
        entry = {"id": obj["object_hash"], "hash": h, "kind": kind, "task_id": task_id, "sender": sender,
                 "to": obj.get("to_worker") or obj.get("needs_from") or obj.get("owner") or "",
                 "created_at": obj["created_at"], "summary": str(obj.get("acceptance_check") or obj.get("description")
                                                                  or obj.get("recommendation") or obj.get("issue") or "")[:300],
                 "artifacts": obj.get("artifacts", [])}
        self.store.put("protocol", obj["object_hash"], entry)
        self.event("protocol.sent", "protocol", obj["object_hash"], {"kind": kind, "from": sender, "to": entry["to"],
                   "task_id": task_id, "artifacts": entry["artifacts"]}, actor=sender,
                   actor_type="worker" if sender.startswith("w_") else "service", correlation_id=task_id,
                   protocol_hash=h)
        return obj

    def gateway(self, worker_id: str, task_id: str, action_type: str, target: str = "", **kw) -> dict:
        return gateway.execute(self, worker_id, task_id, action_type, target, **kw)

    def escalate(self, t: dict, why: str) -> dict:
        return execution.escalate(self, t, why)

    # --- the run contract: money and intelligence ---------------------------------------------------------------
    def record_call(self, task_id: str, worker: str, purpose: str, usage: dict) -> dict:
        """One model call: measured in the registry for the model that made it, charged in dollars to the worker,
        the task and the inference layer, and kept in the run's record."""
        model_id = usage.get("model_id")
        if not model_id:
            raise EngineError(f"a call for {purpose} came back without the model that made it")
        kind = self.store.get("task", task_id)["kind"] if task_id.startswith("t_") else task_id  # objective, plan
        if purpose in ("assign", "review", "answer_blocker"):  # coordination on a task is not the task's own kind
            kind = {"answer_blocker": "answer"}.get(purpose, purpose)
        role = (self.worker(worker) or {}).get("role", worker)
        c = self.registry.record_call(model_id, role=role, purpose=purpose, task_kind=kind, usage=usage,
                                      run_id=self.cid)
        with self.store.atomic():  # numbered and metered as one: concurrent workers never share a record
            n = self.store.next_id("call")
            rec = {"id": f"call_{n:04d}", "task_id": task_id, "worker": worker, "purpose": purpose, **usage,
                   "usd": c["usd"], "model_version": c.get("model_version"), "at": now(),
                   **controller.stamp(self, self.store.get("task", task_id) if task_id.startswith("t_") else None)}
            self.store.put("call", rec["id"], rec)
            if task_id.startswith("t_") and purpose == "work":
                m = self.store.get("meter", task_id) or {"usd": 0.0, "seconds": 0.0, "tokens": 0}
                self.store.put("meter", task_id, {"usd": m["usd"] + c["usd"], "seconds": m["seconds"] + c["seconds"],
                                                  "tokens": m["tokens"] + c["tokens_in"] + c["tokens_out"]})
        self.spend(worker, task_id, c["usd"], "inference")
        held = getattr(self._tls, "reservations", None)
        if held:  # what the call really cost is charged: its reservation ends
            budget.release(self.store, held)
            self._tls.reservations = []
        return rec

    def spend(self, worker_id: str, task_id: str, usd: float, layer: str) -> None:
        crossed = budget.charge(self.store, worker_id, task_id, usd, layer)
        L = budget.ledger(self.store)
        cap = project_settings.get(self.store)["budget_usd"]
        corr = task_id if task_id.startswith("t_") else self.cid
        for mark in crossed["warned"]:
            self.event("budget.threshold_reached", "company", self.cid, {"threshold": mark, "spent_usd": L["spent_total"],
                       "cap_usd": cap}, actor="budget_engine", correlation_id=corr)
        if crossed["breaker"]:
            self.event("budget.threshold_reached", "company", self.cid, {"threshold": 100, "spent_usd": L["spent_total"],
                       "cap_usd": cap}, actor="budget_engine", policy_decision="DENY", correlation_id=corr)
            objective.transition(self, "OBJECTIVE_BLOCKED", "the budget cap is reached", by="budget_engine")
            self.decision("budget_breaker", problem="The project's budget cap is reached. All work is paused.",
                          recommendation=f"Raise the budget from ${cap:.2f} to ${max(cap, L['spent_total']) * 1.5:.2f}, "
                                         "or stop the run.",
                          risk="HIGH", confidence="high", cost="none until work resumes",
                          evidence=[f"spent {budget.dollars(L['spent_total'])} of {budget.dollars(cap)}"],
                          change="Nothing: the cap is yours to set.", severity="SEV-2", source="budget_engine")

    # --- Stage 0: the founder's inputs ---------------------------------------------------------------------------
    def create_company(self, name: str, mode: str = "demo", scenario: str | None = None) -> dict:
        with self.lock:
            self._require("new")
            if mode not in ("demo", "live"):
                raise EngineError("mode must be demo or live")
            scenario = scenario or DEFAULT_SCENARIO
            if mode == "demo" and scenario not in {x["id"] for x in scenarios()}:
                raise EngineError(f"no demo scenario {scenario!r}")
            self.set_meta(mode=mode, scenario=scenario if mode == "demo" else None)
            try:
                self._attach()  # live mode fails here, before anything is written, when no model is reachable
            except EngineError:
                self.set_meta(mode="demo", scenario=None)
                raise
            founder = dict(objective.FOUNDER_DEFAULT)
            if mode == "demo":
                preset = json.loads((SCENARIOS / scenario / "scenario.json").read_text(encoding="utf-8"))
                project_settings.update(self.store, preset.get("settings") or {})
                founder = objective.founder_profile(preset.get("founder") or founder)
            company = {"id": self.cid, "name": (name or "").strip() or "My company", "stage": "IDEA",
                       "autonomy_level": "L1", "risk_tolerance": "conservative", "constraints": {}, "status": "active",
                       "founder": founder, "created_at": now()}
            self.store.put("company", self.cid, company)
            self.event("company.created", "company", self.cid, {"stage": "IDEA", "autonomy_level": "L1", "mode": mode,
                       "scenario": self.meta["scenario"]}, actor="founder", actor_type="human", authority="founder")
            self.set_meta(phase="objective")
            return company

    def draft_objective(self, messy: str) -> dict:
        with self.lock:
            self._require("objective")
            try:
                obj = objective.draft(self, messy)
            except objective.ObjectiveError as exc:
                raise EngineError(str(exc)) from exc
            if not obj["founder_constraints"] and self.store.get("company", self.cid).get("constraints"):
                obj = objective.set_constraints(self, self.store.get("company", self.cid)["constraints"])
            return obj

    def edit_objective(self, fields: dict) -> dict:
        with self.lock:
            obj = self.objective()
            if obj is None:
                raise EngineError("no objective yet")
            if obj["status"] != "draft":
                return self.request_objective_change(fields)
            return objective.edit(self, fields)

    def set_guardrails(self, budget_usd: float | None = None, time_value_per_hour: float | None = None,
                       constraints: dict | None = None, governance: dict | None = None) -> dict:
        """Stage 0: the budget in US dollars, what an hour is worth, the explicit constraints (deadline, geography,
        technology, compliance, risk tolerance) and the governance settings."""
        with self.lock:
            self._require("objective")
            try:
                s = project_settings.update(self.store, {"budget_usd": budget_usd,
                                                          "time_value_per_hour": time_value_per_hour,
                                                          **(governance or {})})
            except project_settings.SettingsError as exc:
                raise EngineError(str(exc)) from exc
            if budget_usd is not None or time_value_per_hour is not None:
                self.event("budget.changed", "company", self.cid, {"budget_usd": s["budget_usd"],
                           "time_value_per_hour": s["time_value_per_hour"]}, actor="founder", actor_type="human",
                           authority="founder")
            company = self.store.get("company", self.cid)
            if constraints is not None:
                clean = {k: str(v).strip() for k, v in constraints.items()
                         if k in objective.CONSTRAINT_KEYS and str(v or "").strip()}
                company["constraints"] = clean
                if clean.get("risk_tolerance"):
                    company["risk_tolerance"] = clean["risk_tolerance"]
                if self.objective() is not None:
                    objective.set_constraints(self, clean)
            self.store.put("company", self.cid, company)
            return {"company": company, "settings": s}

    def set_founder(self, profile: dict) -> dict:
        """What the founder brings: their background and the seats they lead themselves. Given before the objective is
        submitted, those seats get no cofounder in the proposal; given at step 3 (define_founder), a cofounder seat
        the founder leads becomes a lead that reports to the founder. The stage sets how many seats each cofounder
        may hire."""
        with self.lock:
            self._require("objective", "founder")
            company = self.store.get("company", self.cid)
            fixed = company.get("founder") or {}
            given = {k: v for k, v in (profile or {}).items() if v is not None and v != ""}
            try:  # what the form does not send is kept as it was
                clean = objective.founder_profile({**fixed, **given})
            except objective.ObjectiveError as exc:
                raise EngineError(str(exc)) from exc
            if "CTO" in clean["leads"] and self.meta["phase"] == "objective":
                raise EngineError("In this version the CTO's seat reviews, merges and releases the code, which only a "
                                  "team member can do. You can lead product, money or compliance yourself.")
            if self.meta["mode"] == "demo" and (clean["leads"], clean["stage"]) != (fixed.get("leads"), fixed.get("stage")):
                raise EngineError("In a demo your part is scripted: its team was written for that part. "
                                  "In live mode Cynqra builds the team around what you bring.")
            company["founder"] = clean
            self.store.put("company", self.cid, company)
            self.event("company.founder_set", "company", self.cid, {"leads": clean["leads"], "stage": clean["stage"],
                       "hours_per_week": clean["hours_per_week"]}, actor="founder", actor_type="human",
                       authority="founder")
            return clean

    def submit_objective(self) -> dict:
        """Stage 0 ends: the founder hands over the outcome, not the team. Stage 1 decomposes it into outcomes,
        requirements and risks, and Stage 2 builds the organization from that list; the founder's first decision is
        the workforce gate, where the list, the team and the checks on it are shown together. No step is added for
        the founder: the checks run by themselves."""
        with self.lock:
            self._require("objective")
            if self.objective() is None:
                raise EngineError("write the objective first")
            objective.submit(self)
            self.intervention("objective", "submitted")
            try:
                objective.decompose(self)
                synthesis.propose(self)
            except IntelligenceError as exc:
                obj = self.objective()
                obj["status"] = "draft"
                self.store.put("objective", "obj_1", obj)
                objective.transition(self, "OBJECTIVE_CREATED", f"returned to draft: {exc}"[:200])
                self.set_meta(notice=f"Objective intelligence failed: {exc}. Nothing was invented. Submit again to retry.")
                raise
            self.set_meta(phase="workforce", notice="")
            return self.objective()

    # --- the founder's decisions ---------------------------------------------------------------------------------
    def pending_decisions(self) -> list[dict]:
        return [d for d in self.store.all("decision") if d["status"] == "pending"]

    def _handlers(self) -> dict:
        return {"approve_workforce": self._after_workforce, "approve_roadmap": self._after_roadmap,
                "decision": lambda d, a: execution.after_proposal(self, d, a),
                "review_merge": lambda d, a: execution.after_proposal(self, d, a),
                "deploy": lambda d, a: execution.after_proposal(self, d, a),
                "escalation": lambda d, a: execution.after_escalation(self, d, a),
                "provider_outage": lambda d, a: replacement.after_outage(self, d, a),
                "provider_account": lambda d, a: replacement.after_account(self, d, a),
                "budget_breaker": self._after_breaker, "objective_change": self._after_objective_change,
                "accept_delivery": lambda d, a: delivery.after_accept(self, d, a)}

    def decide(self, decision_id: str, action: str, note: str = "", edited: dict | None = None) -> dict:
        with self.lock:
            d = self.store.get("decision", decision_id)
            if d is None:
                raise EngineError(f"unknown decision {decision_id}")
            if d["status"] != "pending":
                raise EngineError(f"decision {decision_id} is already {d['status']}")
            if action not in ("approve", "reject", "request_evidence"):
                raise EngineError(f"unknown action {action}")
            if action == "request_evidence" and d["kind"] not in EVIDENCE_KINDS:
                raise EngineError("this decision takes approve or reject; there is no proposal to revise")
            edited = {k: v for k, v in (edited or {}).items() if v not in (None, "", [])}
            if action == "approve" and edited:
                self._check_edit(d, edited)  # a refused edit leaves the decision pending, nothing recorded
            if action == "approve":
                label = "approved_edited" if edited else "approved"
            elif action == "reject":
                label = "rejected_with_reason" if note else "rejected"
            else:
                label = "more_evidence_requested"
            d.update({"status": "approved" if action == "approve" else "rejected", "outcome_label": label,
                      "labeled_by": "founder", "labeled_at": now(), "resolved_by": "founder", "resolved_at": now(),
                      "note": note, "edited": edited})
            self.store.put("decision", decision_id, d)
            self.intervention(decision_id, label)
            self.event("decision.approved" if action == "approve" else "decision.rejected", "decision", decision_id,
                       {"kind": d["kind"], "outcome_label": label, "task_id": d.get("task_id")}, actor="founder",
                       actor_type="human", authority="founder", correlation_id=d.get("task_id") or decision_id)
            self._handlers()[d["kind"]](d, action)
            return d

    def _check_edit(self, d: dict, edited: dict) -> None:
        if d["kind"] == "approve_workforce" and edited.get("option") not in (None, "recommended", "lean"):
            raise EngineError("option must be recommended or lean")
        if d["kind"] == "approve_workforce" and edited.get("option") == "lean" and edited.get("roles"):
            raise EngineError("choose the lean team or edit the team, not both")
        if d["kind"] == "approve_workforce" and edited.get("option") == "lean" and self.meta["mode"] == "demo":
            raise EngineError(self.LEAN_IN_DEMO)
        if d["kind"] == "approve_workforce" and edited.get("roles"):
            try:
                synthesis.override(self.proposal(), edited["roles"], self.requirements(),
                                   project_settings.get(self.store)["allow_workforce_override"], self.founder())
            except (synthesis.OverrideRefused, IntelligenceError) as exc:
                raise EngineError(str(exc)) from exc

        elif d["kind"] == "budget_breaker" and "budget_usd" in edited:
            spent = budget.ledger(self.store)["spent_total"]
            try:
                new = float(edited["budget_usd"])
            except (TypeError, ValueError) as exc:
                raise EngineError("budget_usd must be a number") from exc
            if new <= spent:
                raise EngineError(f"the new budget must be above the {budget.dollars(spent)} already spent")

    def _after_workforce(self, d: dict, action: str) -> None:
        """Step 2, the plan, approved: the founder defines themselves next (step 3), and the team and budget are drawn
        up around them (step 4)."""
        if action != "approve":
            try:
                synthesis.reject(self, d.get("note") or "")
            except IntelligenceError as exc:
                self._stage_failed("workforce", exc)
            return
        edited = d.get("edited") or {}
        synthesis.approve(self, edited.get("roles"), edited.get("option") or "recommended")
        self.set_meta(phase="founder", notice="")
        self.event("state.changed", "company", self.cid, {"phase": "founder"})

    def rename_worker(self, worker_id: str, name: str) -> dict:
        """The founder names a team member as they like. The seat, the record and the history stay."""
        with self.lock:
            try:
                return people.rename(self, worker_id, name)
            except ValueError as exc:
                raise EngineError(str(exc)) from exc

    def define_founder(self, profile: dict | None = None) -> dict:
        """Step 3: the founder says who they are and what they bring. In live mode, when their background or stage
        is not what the plan's organization was built around, the organization is built again around them (a demo's
        organization is part of its script). Every cofounder seat the founder leads becomes a lead reporting to the
        founder, since the founder is that cofounder; then the team is staffed and the roadmap and budget are drawn
        up for step 4."""
        if profile:
            self.set_founder(profile)
        with self.lock:
            self._require("founder")
            founder = self.founder()
            if self.meta["mode"] != "demo" and synthesis.needs_refit(self.proposal(), founder):
                try:
                    synthesis.refit(self, founder)
                except IntelligenceError as exc:
                    self._stage_failed("founder", exc)
            self._fit_founder(founder)
            self.event("company.founder_defined", "company", self.cid, {"leads": self.founder().get("leads", [])},
                       actor="founder", actor_type="human", authority="founder")
            self._build_team()
            return self.founder()

    def _fit_founder(self, founder: dict) -> None:
        """A cofounder seat the founder leads is theirs: its worker stays to do the work, as a lead reporting to the
        founder, and what a cofounder settles on its own comes to the founder instead."""
        org = self.store.get("organization", "org_1")
        leads = set((founder or {}).get("leads") or [])
        for w in self.workers():
            if w.get("tier") != "cofounder" or w["role"] not in leads:
                continue
            w.update({"tier": "team", "reports_to": "founder", "led_by_founder": True,
                      "title": f"{w['title']} (you lead this area)"})
            self.store.put("worker", w["id"], w)
            org["cofounders"] = [x for x in org["cofounders"] if x != w["id"]]
            org["reports_to"][w["id"]] = "founder"
            self.event("worker.reports_to_founder", "worker", w["id"], {"role": w["role"]})
        self.store.put("organization", "org_1", org)

    def _build_team(self) -> None:
        try:
            self._staff()
        except IntelligenceError as exc:
            self._stage_failed("roadmap", exc)
        self._roadmap()

    def _stage_failed(self, stage: str, exc: Exception) -> None:
        self.set_meta(phase="stopped_error", failed_stage=stage,
                      notice=f"The {stage} failed: {exc}. Nothing was invented. Resume to try again.")
        self.event("state.changed", "company", self.cid, {"phase": "stopped_error", "failed_stage": stage,
                   "why": str(exc)[:200]})
        raise exc

    def cycle(self) -> int:
        return int(self.meta.get("cycle") or 1)

    def _roadmap(self, note: str = "") -> None:
        """Stage 5, then Stage 7: the roadmap for the approved organization and the budget built on it. Stage 6 puts
        both in front of the founder. In a later cycle, only the new work is planned and priced."""
        n = self.cycle()
        try:
            p = planner.plan(self, note, cycle=n)
            wc = self._work_check(p, release=n == 1)
            cal = self._calibrate()  # representative work from this objective, before the initial bindings
            self._staff(refine=True)
            controller.bind_tasks(self, [t for t in self.tasks() if int(t.get("cycle") or 1) == n])
        except IntelligenceError as exc:
            self._stage_failed("roadmap", exc)
        new = [t for t in self.tasks() if int(t.get("cycle") or 1) == n]
        f = budget.construct(self.store, new, self.workers(), self.registry)
        f["at"] = now()
        self.store.put("forecast", "current", f)
        for r in f["tasks"]:  # every task carries its budget: the forecast of its own work, in dollars
            t = self.task(r["task_id"])
            t["budget_usd"] = round(r["inference"] + r["coordination"] + r["tools"] + r["verification"], 6)
            self.save_task(t)
        self.event("budget.constructed", "company", self.cid, {"subtotal_usd": f["subtotal_usd"],
                   "cap_usd": f["cap_usd"], "reserve_usd": f["reserve_usd"], "fits": f["fits"]}, actor="budget_engine")
        ev = ["Milestones: " + "; ".join(f"{m['name']} (day {m['due_day']})" for m in p["milestones"]),
              f"Critical path: {' > '.join(p['critical_path'])}"]
        ev += [f"{t['id']}: {t['title']} ({t['kind']}), {t['owner_worker_id']} on {self.model_of(t['owner_worker_id'])}"
               for t in new]
        ev += [f"{k}: {budget.dollars(v['usd'])} ({v['basis']})" for k, v in f["layers"].items()]
        ev += f["warnings"]
        if p["uncovered_requirements"]:
            ev.append("Requirements no task names: " + ", ".join(p["uncovered_requirements"]))
        for a in p.get("assumption_tests") or []:  # the riskiest guesses, tested before what depends on them
            ev.append(f"Guess {a['id']} ({a['risk']} risk): {a['text']} "
                      + (f"Tested first by {a['task']} in {a['milestone']}." if a["task"] else "No task tests it.")
                      + ("" if a["early"] or a["risk"] != "high" else " It is tested late: a wrong answer here is found "
                         "only after most of the money is spent.")
                      + (f" Only you can test the rest: {a['founder_step']}" if a["founder_step"] else ""))
        ev += calibration.summary(cal)
        ev += [f"{t['id']} on {(binding.task_binding(self.store, t['id']) or {}).get('intelligence') or '?'}: "
               f"{(controller.get_decision(self, (binding.task_binding(self.store, t['id']) or {}).get('decision_id') or '') or {}).get('selection_mode', '')}"
               for t in new if binding.task_binding(self.store, t["id"])][:30]
        ev += [f"{people.label(self.worker(wid))} joins with {j['task']} ({j['milestone']})" for wid, j in wc["joins"].items()]
        ev += ([f"{people.label(x)} had no work in this plan and was removed before anything started" for x in wc["idle"]]
               if n == 1 else [f"{people.label(x)} has no work in this cycle and costs nothing in it" for x in wc["idle"]])
        self.decision("approve_roadmap",
                      problem=(f"The roadmap for the approved organization: {len(p['milestones'])} milestones, "
                               f"{len(new)} tasks, and the budget built on it.") if n == 1 else
                              (f"Cycle {n} on the live product: {len(new)} tasks for what you asked ({note[:160]}), "
                               "and the budget built on it."),
                      recommendation="Approve the roadmap and the budget. Work starts; MEDIUM and HIGH steps still "
                                     "come back to you.",
                      risk="LOW" if f["fits"] else "MEDIUM", confidence="high" if f["fits"] else "medium",
                      cost=f"{budget.dollars(f['subtotal_usd'])} forecast of the {budget.dollars(f['cap_usd'])} cap, "
                           f"reserve {budget.dollars(f['reserve_usd'])}",
                      evidence=ev, change="A task that does not serve the objective, a missing one, or a budget line "
                                          "that looks wrong.", source="execution_planner",
                      extra={"released": [x["worker"] for x in wc["idle"]] if n == 1 else [], "cycle": n})
        self.set_meta(phase="planning", failed_stage=None, notice="")

    def _calibrate(self) -> dict:
        """Cold-start objective calibration (calibration.py). A trial that cannot run is recorded and the roadmap
        goes on from the global prior; nothing is invented."""
        try:
            return calibration.calibrate(self)
        except (IntelligenceError, objective_evidence.EvidenceError, OSError, RegistryError, SupplyError) as exc:
            p = calibration.plan_id(self)
            rec = {"plan_id": p, "objective_id": controller.objective_id(self), "status": "skipped", "items": [],
                   "trials": [], "stopping": {}, "spent_usd": 0.0, "reason": f"calibration could not run: {exc}"[:300]}
            self.store.put(calibration.KIND, p, rec)
            self.event("intelligence.calibration.completed", "calibration", p, {"status": "skipped",
                       "reason": rec["reason"][:200]}, actor="intelligence_controller")
            return rec

    def _work_check(self, p: dict, release: bool = True) -> dict:
        """Every member joins with its first task; a member with no work in the plan leaves before anything starts,
        and the founder is told at the roadmap gate instead of being asked. In a later cycle a member with no work in
        it stays, and costs nothing in it."""
        n = int(p.get("cycle") or 1)
        wc = seats.work_check([t for t in self.tasks() if int(t.get("cycle") or 1) == n], self.workers(), p["milestones"])
        p["work_check"] = wc
        self.store.put("plan", "plan_1", p)
        for w in self.workers():
            j = wc["joins"].get(w["id"])
            if j and w.get("joins") != j:
                w["joins"] = j
                self.store.put("worker", w["id"], w)
        if wc["idle"] and release:
            self._release([x["worker"] for x in wc["idle"]])
        return wc

    def _release(self, wids: list[str]) -> None:
        """Members with no work in the plan leave before any work starts. The founder is told in the roadmap gate."""
        org = self.store.get("organization", "org_1")
        for wid in wids:
            w = self.worker(wid)
            self.store.delete("worker", wid)
            org["workers"] = [x for x in org["workers"] if x != wid]
            org["reports_to"].pop(wid, None)
            org["released"] = org.get("released", []) + [{"id": wid, "title": w["title"], "why": "no work in the plan"}]
            self.event("worker.released", "worker", wid, {"role": w["role"], "why": "no work in the plan"},
                       actor="execution_planner")
        org["cofounders"] = [x for x in org["cofounders"] if x not in wids]
        org["roles"] = {}
        for w in self.workers():
            org["roles"][w["role"]] = org["roles"].get(w["role"], 0) + 1
        self.store.put("organization", "org_1", org)
        for t in self.tasks():  # nobody may be asked for help, hand work out or review it once they have left
            ask = [x for x in t.get("blockers_to") or [] if x not in wids]
            if ask != t.get("blockers_to"):
                t["blockers_to"] = ask or [x for x in org["cofounders"]] or ["founder"]
                self.save_task(t)
        plan = self.store.get("plan", "plan_1")
        if plan:
            coord = plan.get("coordination") or {}
            coord["answers_blockers"] = [x for x in coord.get("answers_blockers") or [] if x not in wids]
            if coord.get("planner") in wids:
                coord["planner"] = roles.planner(self.workers())
            plan["coordination"] = coord
            self.store.put("plan", "plan_1", plan)

    def _after_roadmap(self, d: dict, action: str) -> None:
        if action != "approve":
            self._roadmap(note=d.get("note") or "You asked for a different roadmap.")
            return
        org = self.store.get("organization", "org_1")
        org.update({"status": "active", "approved_by": "founder", "approved_at": now()})
        self.store.put("organization", "org_1", org)
        company = self.store.get("company", self.cid)
        company["stage"] = "MVP"
        self.store.put("company", self.cid, company)
        budget.allocate(self.store, self.store.get("forecast", "current"))
        self.event("state.changed", "company", self.cid, {"stage": "MVP", "phase": "running"}, actor="founder",
                   actor_type="human", authority="founder")
        self.set_meta(phase="running", started_at=time.time(), notice="")
        objective.transition(self, "OBJECTIVE_EXECUTING", "the founder approved the roadmap and budget", by="founder")

    def _after_breaker(self, d: dict, action: str) -> None:
        if action != "approve":
            self.set_meta(phase="stopped", notice="You stopped the run at the budget cap.")
            objective.transition(self, "OBJECTIVE_CANCELLED", "the founder stopped the run at the budget cap",
                                 by="founder")
            return
        cap = project_settings.get(self.store)["budget_usd"]
        new = float(d["edited"].get("budget_usd") or (d.get("extra") or {}).get("needed_cap")
                    or max(cap, budget.ledger(self.store)["spent_total"]) * 1.5)
        budget.raise_cap(self.store, new)
        objective.transition(self, "OBJECTIVE_EXECUTING", "the founder raised the budget", by="founder")
        self.event("budget.changed", "company", self.cid, {"budget_usd": round(new, 4)}, actor="founder",
                   actor_type="human", authority="founder")

    # --- Stage 8: the run ------------------------------------------------------------------------------------------
    def step(self) -> dict:
        """One round of the run. Every worker with work it can do now takes one piece of it (a person does one
        thing at a time), and they work at the same time: each hands its result on, or raises a Blocker, when it is
        done, and the colleague it concerns picks that up in the next round. Verification and approved actions are
        the platform's and run in the same round. Model calls overlap; recording their results is serialized."""
        with self.lock:
            m = self.meta
            if m["frozen"]:
                return {"did": "idle", "why": "kill switch is on"}
            if m["phase"] != "running":
                return {"did": "idle", "why": f"phase {m['phase']}"}
            if budget.ledger(self.store)["state"] == "breaker":
                return {"did": "idle", "why": "budget breaker open"}
            replacement.resume_waiting(self)
            actions = self._round()
            if not actions:
                tasks = self.tasks()
                if tasks and all(t["status"] == "VERIFIED" for t in tasks):
                    return delivery.deliver(self)
                waiting = [t for t in tasks if t["status"] == "WAITING" and not t["waiting"].get("decision_id")]
                if waiting:
                    return {"did": "idle", "why": f"waiting for the provider: {waiting[0]['waiting']['why']}"}
                return {"did": "idle", "why": "waiting on the founder"}
        if len(actions) == 1 or not isinstance(self.intel, ModelSource):
            # a prepared script answers at once: its round runs in plan order, so a demo replays the same way
            results = [self._act(tid) for tid in actions]
        else:
            with ThreadPoolExecutor(max_workers=min(len(actions), project_settings.get(self.store)["parallel_workers"]),
                                    thread_name_prefix="worker") as pool:
                results = list(pool.map(self._act, actions))
        results = [r for r in results if r]
        if not results:
            return {"did": "idle", "why": "nothing could proceed"}
        if len(results) == 1:
            return results[0]
        errors = [r for r in results if r["did"] == "error"]
        return {"did": "error" if errors else "round", "task": results[0].get("task"), "actions": results,
                "why": errors[0]["why"] if errors else f"{len(results)} pieces of work at the same time"}

    ACTIONS = {"PLANNED": execution.assign, "ASSIGNED": execution.work, "REWORK": execution.work,
               "BLOCKED": execution.answer, "REVIEW": execution.verify, "LEAD_REVIEW": execution.lead_review,
               "APPROVED": execution.execute_approved}

    def _round(self) -> list[str]:
        """Select ready work and atomically lease it before any slow model call can start."""
        tasks = self.tasks()
        by_id = {t["id"]: t for t in tasks}
        busy: set[str] = set()
        out = []
        for t in tasks:
            s = t["status"]
            if s not in self.ACTIONS or (s == "PLANNED" and not all(
                    by_id[d]["status"] == "VERIFIED" for d in t["dependencies"])):
                continue
            actor = execution.actor(t)
            if actor.startswith("w_"):
                if actor in busy:
                    continue
                busy.add(actor)
            if self.store.claim_task(t["id"], actor):
                out.append(t["id"])
            elif actor in busy:
                busy.discard(actor)
        return out

    def _act(self, tid: str) -> dict | None:
        """One leased task's piece of work. The lease prevents two concurrent step callers from acting on it."""
        lease = self.store.task_lease(tid)
        if not lease:
            return None
        self._tls.task_id, self._tls.reservations, self._tls.review_for = tid, [], None
        try:
            with self.lock:
                m = self.meta
            if m["frozen"] or m["phase"] != "running" or budget.ledger(self.store)["state"] == "breaker":
                return None
            t = self.task(tid)
            s = t["status"]
            if s not in self.ACTIONS:
                return None
            try:
                return self.ACTIONS[s](self, t)
            except BudgetHold as exc:  # nothing was spent and nothing failed: the work waits for the budget
                return {"did": "paused", "task": tid, "why": f"budget: {exc}"}
            except ProtocolError as exc:
                return self._violation(self.task(tid), s, exc)
            except IntelligenceError as exc:
                handled = replacement.model_failed(self, self.task(tid), exc)
                if handled:
                    return handled
                self.set_meta(phase="stopped_error", failed_stage="run",
                              notice=f"Stopped on {tid}: the intelligence failed ({exc}). Nothing was invented.")
                self.event("task.failed", "task", tid, {"reason": "intelligence_error"}, correlation_id=tid)
                objective.transition(self, "OBJECTIVE_BLOCKED", "the intelligence failed and nothing could replace it")
                return {"did": "error", "task": tid, "why": str(exc)}
        finally:
            left = getattr(self._tls, "reservations", None)
            if left:  # a call that failed or never recorded: its reservation ends, nothing was charged for it
                budget.release(self.store, left, outcome="released")
            self._tls.task_id, self._tls.reservations, self._tls.review_for = None, [], None
            self.store.release_task(tid, lease["lease_id"])

    def _violation(self, t: dict, state: str, exc: ProtocolError) -> dict:
        """A reply that is not a valid protocol object: counted against the worker whose reply it was."""
        t["attempts"] += 1
        self.save_task(t)
        culprit = execution.actor(t) or t["owner_worker_id"]
        n = self.store.next_id("violation")
        self.store.put("violation", f"pv_{n:04d}", {"id": f"pv_{n:04d}", "worker_id": culprit,
                       "model_id": self.model_of(culprit) if culprit else None, "task_id": t["id"],
                       "error": str(exc)[:300], "at": now()})
        self.event("protocol.violation", "task", t["id"], {"worker": culprit, "error": str(exc)[:200]},
                   actor=culprit or "orchestrator", actor_type="worker", correlation_id=t["id"], policy_decision="DENY")
        # protocol compliance is intelligence evidence: three on the same work make it ineligible for that work
        controller.record_attempt_failure(self, t, controller.attr.failure(controller.attr.INTELLIGENCE,
                                          "the reply was not a valid protocol object", str(exc)),
                                          kind="protocol_violation", protocol_violation=True, caller=culprit,
                                          idempotency_key=f"violation:{self.cid}:pv_{n:04d}",
                                          intelligence=(self.model_for(culprit, t["id"]), None) if culprit else None)
        if t["attempts"] >= execution.MAX_ATTEMPTS:
            return replacement.evaluate(self, t, f"{t['id']}: the worker kept returning invalid protocol objects "
                                                 f"({exc})", forced=True)
        if state in ("PLANNED", "BLOCKED"):  # the Handoff or the Blocker answer failed: retry that step, not the work
            return {"did": "retry", "task": t["id"], "why": str(exc)}
        t.update({"status": "REWORK", "feedback": f"Your reply was not a valid protocol object: {exc}"})
        self.save_task(t)
        return {"did": "rework", "task": t["id"], "why": str(exc)}

    def run_until_idle(self, max_steps: int = 200) -> list[dict]:
        out = []
        for _ in range(max_steps):
            r = self.step()
            out.append(r)
            if r["did"] in ("idle", "error"):
                break
        return out

    # --- the founder's controls ----------------------------------------------------------------------------------
    def kill_switch(self, on: bool) -> dict:
        # Not behind self.lock: a step can hold it for a whole model call, and the kill switch must work during one.
        # The store serializes the writes; the step checks frozen when its call returns and discards the result.
        self.set_meta(frozen=bool(on))
        self.intervention("kill_switch", "on" if on else "off")
        if on:
            objective.transition(self, "OBJECTIVE_PAUSED", "the kill switch is on", by="founder")
        elif self.meta["phase"] == "running":
            objective.transition(self, "OBJECTIVE_EXECUTING", "the kill switch is off", by="founder")
        self.event("state.changed", "company", self.cid, {"frozen": bool(on), "control": "kill_switch"},
                   actor="founder", actor_type="human", authority="founder", policy_decision="DENY" if on else "ALLOW")
        return self.meta

    def resume(self) -> dict:
        """After a model or network error: try the failed stage again. Nothing was written by the failed call."""
        with self.lock:
            self._require("stopped_error")
            stage = self.meta.get("failed_stage")
            if stage == "outdated":
                raise EngineError(self.OUTDATED)
            self.intervention("resume", f"retry the {stage or 'run'} after an intelligence error")
            self.event("state.changed", "company", self.cid, {"control": "resume", "stage": stage}, actor="founder",
                       actor_type="human", authority="founder")
            if stage == "workforce":
                self.set_meta(phase="workforce", failed_stage=None, notice="")
                synthesis.propose(self, note="Retried after an intelligence error.")
            elif stage == "founder":  # the founder defines themselves again; nothing was replaced
                self.set_meta(phase="founder", failed_stage=None, notice="")
            elif stage == "roadmap":
                if not any(self.model_of(w["id"]) for w in self.workers()):
                    self._staff()
                self._roadmap(note=self.meta.get("cycle_note", "") if self.cycle() > 1 else "")
            else:
                self.set_meta(phase="running", failed_stage=None, notice="")
                objective.transition(self, "OBJECTIVE_EXECUTING", "resumed after an intelligence error", by="founder")
            return self.meta

    def request_objective_change(self, fields: dict) -> dict:
        """D-30: a change during a run pauses it for an impact summary, then reconfirm or keep."""
        with self.lock:
            obj = self.objective()
            changes = {k: str(v).strip() for k, v in (fields or {}).items()
                       if k in objective.FIELDS and str(v).strip() and str(v).strip() != obj["structured"][k]}
            if not changes:
                return obj
            if self.meta["phase"] == "paused_objective":  # a second change would remember "paused" as the phase to
                raise EngineError("a change of objective is already waiting for your answer; answer it first")
            affected = [t["id"] for t in self.tasks() if t["status"] != "VERIFIED"]
            self.decision("objective_change", problem="You changed the objective during a run. The run is paused.",
                          recommendation="Reconfirm with the change. Verified work stays; open tasks continue against "
                                         "the new version.",
                          risk="HIGH", confidence="medium", cost="depends on the change",
                          evidence=[f"fields: {', '.join(changes)}", f"open tasks affected: {', '.join(affected) or 'none'}"],
                          change="Keep the old version if the change was a mistake.", source="orchestrator",
                          extra={"changes": changes, "previous_phase": self.meta["phase"],
                                 "previous_state": objective.state(self),
                                 "classification": objective.classify_change(obj["structured"],
                                                                             {**obj["structured"], **changes})})
            self.set_meta(phase="paused_objective")
            objective.transition(self, "OBJECTIVE_PAUSED", "a change of objective waits for the founder", by="founder")
            return obj

    def _after_objective_change(self, d: dict, action: str) -> None:
        """Approved: a new objective version. Work in flight keeps the version it started under, so its evidence
        is that version's; open work continues against the new one, and earlier evidence carries over only as the
        inheritance policy allows. Rejected: the version stays."""
        if action == "approve":
            rec = objective.new_version(self, d["extra"]["changes"], by="founder")
            obj = self.objective()
            self.event("objective.changed", "objective", "obj_1", {"version": obj["version"], "status": "confirmed",
                       "fields_changed": sorted(d["extra"]["changes"]), "inheritance": rec["inheritance"]["mode"]},
                       actor="founder", actor_type="human", authority="founder")
            for t in self.tasks():
                if t["status"] != "VERIFIED":
                    t.update(objective_version=obj["version"], context=f"objective v{obj['version']}")
                    self.save_task(t)
        self.set_meta(phase=d["extra"].get("previous_phase", "running"))
        back = d["extra"].get("previous_state") or "OBJECTIVE_EXECUTING"
        objective.transition(self, back if back != "OBJECTIVE_PAUSED" else "OBJECTIVE_EXECUTING",
                             "the founder answered the change of objective", by="founder")

    # --- after launch: the company keeps running --------------------------------------------------------------
    def feedback(self, text: str, source: str = "founder") -> dict:
        """What users said, in the founder's words. It is kept and goes into the next cycle's plan."""
        text = (text or "").strip()
        if not text:
            raise EngineError("write what users said first")
        with self.store.lock:  # numbered and written as one: two notes at once never share an id
            n = self.count("feedback") + 1
            rec = {"id": f"fb_{n:03d}", "text": text[:1000], "source": source, "cycle": self.cycle(), "used_in": None,
                   "at": now()}
            self.store.put("feedback", rec["id"], rec)
        self.event("feedback.recorded", "company", self.cid, {"id": rec["id"], "cycle": rec["cycle"]}, actor="founder",
                   actor_type="human", authority="founder")
        return rec

    def check_live(self) -> dict:
        """Cynqra looks at the live product: is it up, and how fast does it answer. Kept as a record the next cycle
        and the founder's update read."""
        url = self.live_url()
        if not url:
            raise EngineError("nothing is live yet")
        h = deploy.health(url, wait=3)  # outside any lock: a slow product never holds up the run
        with self.store.lock:
            n = self.count("live_check") + 1
            rec = {"id": f"lc_{n:03d}", "url": url, "ok": bool(h.get("ok")), "detail": {k: v for k, v in h.items()
                   if k in ("status", "ms", "why")}, "cycle": self.cycle(), "at": now()}
            self.store.put("live_check", rec["id"], rec)
        self.event("live.checked", "deployment", "live", {"ok": rec["ok"]}, actor="deployment")
        return rec

    def start_cycle(self, note: str, budget_usd: float | None = None) -> dict:
        """After launch, the next piece of work on the live product: what the founder asks for, with what users said.
        The same team plans only the new work; the founder approves its roadmap and budget once, then the team builds,
        checks and releases it, and the release before it stays as the way back."""
        with self.lock:
            self._require("accepted", "delivered")
            self._can_plan_cycle(self.cycle() + 1)
            unused = [f for f in self.store.all("feedback") if not f.get("used_in")]
            ask = ((note or "").strip() or "; ".join(f["text"] for f in unused))[:2000]
            if not ask:
                raise EngineError("say what the next cycle should do, or record what users said first")
            if budget_usd:
                try:
                    extra = float(budget_usd)
                except (TypeError, ValueError) as exc:
                    raise EngineError("budget_usd must be a number") from exc
                if extra <= 0:
                    raise EngineError("the added budget must be above zero")
                budget.raise_cap(self.store, project_settings.get(self.store)["budget_usd"] + extra)
            n = self.cycle() + 1
            full = ask + ("\nWhat users said: " + " | ".join(f["text"] for f in unused) if unused and note else "")
            for f in unused:
                f["used_in"] = n
                self.store.put("feedback", f["id"], f)
            self.set_meta(cycle=n, cycle_note=full)  # kept: a failed plan is retried with the same ask
            self.intervention("cycle", f"started cycle {n}")
            objective.transition(self, "OBJECTIVE_REOPENED", f"cycle {n}: {ask[:120]}", by="founder")
            self.event("cycle.started", "company", self.cid, {"cycle": n, "feedback": [f["id"] for f in unused]},
                       actor="founder", actor_type="human", authority="founder")
            self._roadmap(note=full)
            return self.meta

    def audit(self) -> dict:
        """Step 7: the delivered product against the original objective. Every requirement, the work that answers
        it and whether that work passed its checks; the tests in the live release; whether it is up."""
        req = self.requirements() or {}
        tasks = self.tasks()
        rows = []
        for r in req.get("requirements", []):
            mine = [t for t in tasks if r["id"] in (t.get("requirement_ids") or [])]
            rows.append({"id": r["id"], "text": r["text"], "area": r.get("area"),
                         "work": [{"id": t["id"], "title": t["title"], "verified": t["status"] == "VERIFIED"} for t in mine],
                         "met": bool(mine) and all(t["status"] == "VERIFIED" for t in mine)})
        dep = (self.store.all("deployment") or [{}])[-1]
        live = self.store.all("live_check")
        return {"objective": (self.objective() or {}).get("structured", {}).get("success_criteria", ""),
                "requirements": rows, "met": sum(x["met"] for x in rows), "total": len(rows),
                "tests": len(dep.get("test_ids") or []), "live": bool(self.live_url()),
                "up": live[-1]["ok"] if live else None}

    NO_DEMO_CYCLE = ("This demo's script covers the first release only, so it cannot build a rework. In live mode "
                     "the same team plans, builds and releases what you ask for. Nothing was changed.")

    def rework_available(self) -> bool:
        plans = getattr(self.intel, "plans_cycle", None)
        return not (self.meta.get("mode") == "demo" and plans and not plans(self.cycle() + 1))

    def _can_plan_cycle(self, n: int) -> None:
        """A demo without a scripted plan for the next cycle says so plainly, and nothing changes."""
        plans = getattr(self.intel, "plans_cycle", None)
        if self.meta.get("mode") == "demo" and plans and not plans(n):
            raise EngineError(self.NO_DEMO_CYCLE)

    def rework(self, note: str, budget_usd: float | None = None) -> dict:
        """Step 7: what the founder wants changed. A delivery not yet accepted is turned down with the note on record;
        then the same team plans the rework, and the founder approves its plan and budget as in step 4."""
        note = (note or "").strip()
        if not note:
            raise EngineError("say what needs to change")
        self._can_plan_cycle(self.cycle() + 1)  # refused before the delivery is turned down
        pend = [d for d in self.pending_decisions() if d["kind"] == "accept_delivery"]
        if pend:
            self.decide(pend[0]["id"], "reject", note=note)
        return self.start_cycle(note, budget_usd)

    @staticmethod
    def _caught(v: dict) -> str:
        """What one failed check found, in a line."""
        c = v.get("checks") or {}
        if c.get("documents"):
            return numbers.plain(c["documents"][0].get("why", ""))
        bt = c.get("backtest") or {}
        if bt.get("model_mae") is not None and bt.get("baseline_mae") is not None and not bt.get("passed"):
            return (f"on days it had not seen, the forecast was off by {bt['model_mae']} covers a day; repeating the "
                    f"same weekday of the week before was off by {bt['baseline_mae']}")
        if bt.get("why"):
            return bt["why"]
        failed = c.get("failed") or []
        if failed:
            name = failed[0].get("id") if isinstance(failed[0], dict) else str(failed[0])
            name = name.rsplit(".", 1)[-1].removeprefix("test_").replace("_", " ")
            return f"the test \"{name}\" failed" + (f", and {len(failed) - 1} more" if len(failed) > 1 else "")
        return "a check failed and the work was fixed"

    def update(self) -> dict:
        """The founder's update, in plain words: the numbers, what was learned, what was decided, what is at risk, and
        what is waiting for them. Built from the record; no model writes it."""
        tasks = self.tasks()
        title = lambda tid: (self.store.get("task", tid) or {}).get("title") or tid  # noqa: E731
        L = budget.ledger(self.store)
        cap = project_settings.get(self.store)["budget_usd"]
        caught = [v for v in self.store.all("verification") if v["verdict"] != "VERIFIED"]
        decided = [d for d in self.store.all("decision") if d["status"] != "pending"]
        pend = self.pending_decisions()
        risk = []
        if L.get("state") in ("warning", "breaker") or (cap and L["spent_total"] >= 0.8 * cap):
            risk.append(f"Spending is at ${L['spent_total']:.2f} of the ${cap:.2f} budget.")
        risk += [f"{t['id']} ({t['title']}) is stuck and needs a decision." for t in tasks if t["status"] == "FAILED"]
        plan = self.store.get("plan", "plan_1") or {}
        risk += [f"The high-risk guess \"{a['text']}\" is not tested yet." for a in plan.get("assumption_tests") or []
                 if a["risk"] == "high" and a.get("task") and self.store.get("task", a["task"])
                 and self.task(a["task"])["status"] != "VERIFIED"]
        live = self.store.all("live_check")
        if live and not live[-1]["ok"]:
            risk.append("The live product did not answer its last health check.")
        return {"cycle": self.cycle(), "phase": self.meta["phase"],
                "numbers": {"tasks_done": sum(t["status"] == "VERIFIED" for t in tasks), "tasks": len(tasks),
                            "spent_usd": round(L["spent_total"], 4), "budget_usd": cap,
                            "live": bool(self.live_url()), "live_checks_ok": sum(1 for x in live if x["ok"]),
                            "live_checks": len(live)},
                "learned": [f"{title(v['task_id'])}: {self._caught(v)}" for v in caught][-5:],
                "decided": [{"what": d["problem"][:140], "by": "you" if d.get("resolved_by") == "founder" else
                             people.label(self.worker(d["resolved_by"])) or d.get("resolved_by"),
                             "outcome": d["outcome_label"], "status": d["status"], "kind": d["kind"],
                             "task": title(d["task_id"]) if d.get("task_id") else ""} for d in decided][-8:],
                "at_risk": risk,
                "waiting_for_you": [{"id": d["id"], "what": d["problem"][:160]} for d in pend if not d.get("in_digest")],
                "feedback": [f["text"] for f in self.store.all("feedback") if not f.get("used_in")]}

    # --- reading --------------------------------------------------------------------------------------------------
    def live_url(self) -> str | None:
        return delivery.live_url(self)

    def metrics(self) -> dict:
        return delivery.metrics(self)

    def final_report(self) -> dict:
        return delivery.final_report(self)

    def replay(self, task_id: str) -> dict:
        return delivery.replay(self, task_id)

    def graph(self, question: str, subject: str) -> dict:
        try:
            return delivery.graph(self, question, subject)
        except delivery.GraphError as exc:
            raise EngineError(str(exc)) from exc

    def export(self) -> str:
        with self.lock:
            return delivery.export(self)

    # --- the intelligence control plane, read --------------------------------------------------------------------
    def explain(self, task_id: str) -> dict:
        """Why this task's intelligence was selected, and why it changed: the causal audit from persisted records."""
        self.task(task_id)
        return controller.explain(self, task_id)

    def replay_decision(self, decision_id: str) -> dict:
        try:
            return controller.replay(self, decision_id)
        except controller.ControlError as exc:
            raise EngineError(str(exc)) from exc

    def decisions(self, work_item_id: str | None = None) -> list[dict]:
        return controller.decisions(self, work_item_id)

    def workforce_view(self) -> dict:
        """Which intelligence each worker is bound to and why, what each may spend and has spent, and every change
        to a binding. Workers and intelligence stay separate records; the binding joins them."""
        if self.supply is None:
            return {"active": False, "why": "no company yet"}
        L = budget.ledger(self.store)
        bound = binding.all_bindings(self.store)
        workers = self.workers()
        in_use: dict[str, list[str]] = {}
        for w in workers:
            if w["id"] in bound:
                in_use.setdefault(bound[w["id"]]["intelligence_id"], []).append(w["id"])
        return {"active": bool(workers), "registry": self.registry.snapshot(),
                "task_bindings": binding.all_task_bindings(self.store),
                "settings": project_settings.get(self.store), "ledger": L, "system": bound.get(binding.SYSTEM),
                "replacements": self.store.all("replacement"), "models_in_use": in_use,
                "ceo_notices": self.store.all("ceo_notice"),
                "workers": [{"id": w["id"], "role": w["role"], "title": w["title"], "reports_to": w.get("reports_to"),
                             "name": w.get("name"), "seat": people.seat(w), "former": w.get("former") or [],
                             "binding": bound.get(w["id"]),
                             "model_id": (bound.get(w["id"]) or {}).get("intelligence_id"),
                             "model": (bound.get(w["id"]) or {}).get("intelligence"),
                             "why": (bound.get(w["id"]) or {}).get("reason", ""),
                             "candidates": (bound.get(w["id"]) or {}).get("candidates", []),
                             "budget": L["by_worker"].get(w["id"], {"allocated": 0.0, "spent": 0.0}),
                             "performance": w.get("performance_profile")} for w in workers]}

    def snapshot(self) -> dict:
        # Read without self.lock so the UI stays live while a step waits on a model call.
        m = self.meta
        decisions = self.store.all("decision")
        forecast = self.store.get("forecast", "current")
        workers = self.workers()
        company = self.store.get("company", self.cid)
        cards = performance.all_cards(self.store, self.registry) if workers else []
        control = controller.summary(self) if company else None
        return {
            "meta": m,
            "scenarios": scenarios(),
            "policy": {"version": policy.POLICY_VERSION, "matrix": policy.MATRIX, "risk": policy.RISK},
            "intelligence": getattr(self.intel, "kind", None),
            "company": company,
            "objective": self.objective(),
            "requirements": self.requirements(),
            "proposal": self.proposal(),
            "organization": self.store.get("organization", "org_1"),
            "workers": workers,
            "plan": self.store.get("plan", "plan_1"),
            "tasks": self.tasks(),
            "decisions": {"pending": [d for d in decisions if d["status"] == "pending"],
                          "answered": [d for d in decisions if d["status"] != "pending"]},
            "protocols": self.store.all("protocol")[-40:],
            "denied": [a for a in self.store.all("action") if a["status"] == "denied"],
            "verifications": self.store.all("verification"),
            "deployments": self.store.all("deployment"),
            "transition": self.store.get("transition", f"tr_{self.cycle()}") or self.store.get("transition", "tr_1"),
            "update": self.update() if company and self.meta["phase"] not in ("new", "objective") else None,
            "audit": self.audit() if self.meta["phase"] in ("delivered", "accepted") else None,
            "rework_available": self.rework_available() if self.meta["phase"] in ("delivered", "accepted") else None,
            "feedback": self.store.all("feedback"), "live_checks": self.store.all("live_check")[-10:],
            "budget": {"settings": project_settings.get(self.store), "ledger": budget.ledger(self.store)},
            "forecast": forecast,
            "economics": budget.actual(self.store, forecast) if forecast else None,
            "workforce": self.workforce_view(),
            "supply": self.supply.snapshot() if self.supply else None,
            "performance": cards,
            "evaluations": self.store.all("evaluation"),
            "intelligence_control": control,
            "objective_lifecycle": (self.objective() or {}).get("lifecycle"),
            "catalog": roles.catalog(),
            "final": delivery.final_report(self, cards=cards, control=control)
            if m["phase"] in ("delivered", "accepted") else None,
            "metrics": self.metrics() if company else {},
            "rules": self.rules(),
            "live_url": self.live_url(),
            "events": self.store.last_events(60),
            "exports": sorted(p.name for p in self.paths["exports"].glob("*.zip")),
        }

    def close(self) -> None:
        deploy.stop(self.live_proc)
        self.store.close()
        if self._own is not None:
            self._own.close()
