"""The orchestrator: one company, one objective, one run, along the product definition's canonical flow
(Cynqra Product Flows and Architecture v1, section 3). It owns the run's state and the founder's gates; the work of
every stage is done by an engine that sees the run only through the run contract (run.py):

  Stage 0-1  objective.py     the founder's objective structured, then decomposed into requirements
  Stage 2-3  synthesis.py     the organization the objective needs, and the workforce approval gate
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
import threading
from concurrent.futures import ThreadPoolExecutor
import time
import uuid
from datetime import datetime
from pathlib import Path

from . import binding, budget, delivery, deploy, execution, gateway, objective, performance, planner, policy
from . import replacement, roles, synthesis
from . import settings as project_settings
from .db import IST, Store, now
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

    def __init__(self, data_dir: Path, intelligence=None, supply: IntelligenceSupply | None = None):
        self.dir = Path(data_dir).resolve()  # workers' tests run from inside it: a relative path would break them
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
        if self.store.get("meta", "run") is None:
            self.store.put("meta", "run", {"company_id": "co_" + uuid.uuid4().hex[:8], "phase": "new", "mode": "demo",
                                           "scenario": None, "frozen": False, "created_at": now(), "notice": ""})
        if self.meta["phase"] != "new":
            self._attach(strict=False)  # a run reopened after a restart opens even if its model is gone for now

    # --- the run's state ---------------------------------------------------------------------------------------
    @property
    def meta(self) -> dict:
        return self.store.get("meta", "run")

    def set_meta(self, **kw) -> dict:
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
                raise EngineError("live mode needs intelligence: connect a provider (OpenAI-compatible, Anthropic or "
                                  "a model on this machine), or name one in the environment")
            source = self._injected or ModelSource()
        source.bind(self)
        self.supply, self.intel = sup, source

    def intelligence_for(self, worker_id: str) -> str:
        """The intelligence bound to a worker. Work that belongs to no worker (structuring the objective,
        synthesizing the workforce) runs on the intelligence the Router bound to the control plane for it."""
        b = binding.current(self.store, worker_id) if worker_id.startswith("w_") else None
        if b is not None:
            return b["intelligence_id"]
        sys_ = binding.current(self.store, binding.SYSTEM)
        if sys_ is not None:
            try:
                if self.registry.availability(self.registry.get(sys_["intelligence_id"]))[0]:
                    return sys_["intelligence_id"]
            except RegistryError:
                pass
        best, rows = router.choose(self.registry, project_settings.get(self.store), ["objective"])
        if best is None:
            raise IntelligenceError("no available intelligence in the registry")
        binding.bind(self, binding.SYSTEM, self.registry.get(best["model_id"]), by="intelligence_router",
                     reason="objective intelligence and workforce synthesis", candidates=rows)
        return best["model_id"]

    def invoke(self, worker_id: str, request: dict) -> dict:
        """One call for a worker, through the Intelligence Gateway to the intelligence it is bound to, at the
        version its binding pinned. A new version continues only after its regression check passes."""
        who = worker_id if worker_id.startswith("w_") and binding.current(self.store, worker_id) else binding.SYSTEM
        mid = self.intelligence_for(worker_id)
        pin = (binding.current(self.store, who) or {}).get("version")
        try:
            return self._call(mid, request, pin)
        except VersionChanged as exc:
            replacement.version_changed(self, who, exc)  # kept after its regression check, or rebound
            b = binding.current(self.store, who)
            return self._call(b["intelligence_id"], request, b["version"])
        except SupplyError as exc:
            raise IntelligenceError(str(exc), model_id=mid) from exc

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
            a = self.assigner_id()
            if a and any(t["handoff_from"] == a for t in self.tasks()):
                workload.setdefault(a, []).append("assign")
        try:
            staffing = router.staff(self.registry, project_settings.get(self.store), self.workers(), workload)
        except router.RouterError as exc:
            raise IntelligenceError(str(exc)) from exc
        for wid, s in staffing.items():
            if refine and self.model_of(wid) == s["model_id"]:
                continue
            why = ("refined to the roadmap's workload: " if refine else
                   "lowest expected cost per verified task for its role's work: ") + ", ".join(s["kinds"])
            binding.bind(self, wid, self.registry.get(s["model_id"]), reason=why, by="intelligence_router",
                         candidates=s["candidates"])

    # --- the run contract: the audit trail and the founder's inbox ---------------------------------------------
    def event(self, event_type: str, aggregate_type: str, aggregate_id: str, payload: dict, *,
              actor: str = "orchestrator", actor_type: str = "service", correlation_id: str | None = None,
              policy_decision: str = "ALLOW", authority: str = "platform", protocol_hash: str | None = None,
              test_ids: list | None = None, context_refs: list | None = None) -> dict:
        return self.store.append(
            company_id=self.cid, event_type=event_type, aggregate_type=aggregate_type, aggregate_id=aggregate_id,
            actor_type=actor_type, actor_id=actor, payload=payload, correlation_id=correlation_id or aggregate_id,
            policy_decision=policy_decision, authority_snapshot=authority, protocol_hash=protocol_hash,
            test_ids=test_ids, context_refs=context_refs)

    def decision(self, kind: str, *, problem: str, recommendation: str, risk: str, confidence: str, cost: str,
                 evidence: list, change: str, task_id: str | None = None, action_type: str | None = None,
                 severity: str = "SEV-3", source: str = "orchestrator", extra: dict | None = None) -> dict:
        today = datetime.now(IST).date().isoformat()
        worker_raised = source.startswith("w_")
        todays = [d for d in self.store.all("decision")
                  if d.get("created_day") == today and d.get("source", "").startswith("w_")]
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
                   "in_digest": digest_it, "severity": severity}, actor=source,
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
        return roles.prompt_text(w) if w else ""

    def assigner_id(self) -> str | None:
        return roles.assigner(self.workers())

    def answerers(self) -> list[str]:
        return roles.answerers(self.workers()) or [self.assigner_id()]

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
                 "created_at": obj["created_at"], "summary": (obj.get("acceptance_check") or obj.get("description")
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
        role = (self.worker(worker) or {}).get("role", worker)
        c = self.registry.record_call(model_id, role=role, purpose=purpose, task_kind=kind, usage=usage,
                                      run_id=self.cid)
        n = self.count("call") + 1
        rec = {"id": f"call_{n:04d}", "task_id": task_id, "worker": worker, "purpose": purpose, **usage,
               "usd": c["usd"], "at": now()}
        self.store.put("call", rec["id"], rec)
        if task_id.startswith("t_") and purpose == "work":
            m = self.store.get("meter", task_id) or {"usd": 0.0, "seconds": 0.0, "tokens": 0}
            self.store.put("meter", task_id, {"usd": m["usd"] + c["usd"], "seconds": m["seconds"] + c["seconds"],
                                              "tokens": m["tokens"] + c["tokens_in"] + c["tokens_out"]})
        self.spend(worker, task_id, c["usd"], "inference")
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
            self.decision("budget_breaker", problem="The project's budget cap is reached. All work is paused.",
                          recommendation=f"Raise the budget from ${cap:.2f} to ${max(cap, L['spent_total']) * 1.5:.2f}, "
                                         "or stop the run.",
                          risk="HIGH", confidence="high", cost="none until work resumes",
                          evidence=[f"spent ${L['spent_total']:.4f} of ${cap:.2f}"],
                          change="Nothing: the cap is yours to set.", severity="SEV-2", source="budget_engine")

    # --- Stage 0: the founder's inputs ---------------------------------------------------------------------------
    def create_company(self, name: str, mode: str = "demo", scenario: str | None = None) -> dict:
        with self.lock:
            self._require("new")
            if mode not in ("demo", "live"):
                raise EngineError("mode must be demo or live")
            scenario = scenario or DEFAULT_SCENARIO
            if mode == "demo" and not (SCENARIOS / scenario / "scenario.json").exists():
                raise EngineError(f"no demo scenario {scenario!r}")
            self.set_meta(mode=mode, scenario=scenario if mode == "demo" else None)
            try:
                self._attach()  # live mode fails here, before anything is written, when no model is reachable
            except EngineError:
                self.set_meta(mode="demo", scenario=None)
                raise
            if mode == "demo":
                preset = json.loads((SCENARIOS / scenario / "scenario.json").read_text(encoding="utf-8"))
                project_settings.update(self.store, preset.get("settings") or {})
            company = {"id": self.cid, "name": (name or "").strip() or "My company", "stage": "IDEA",
                       "autonomy_level": "L1", "risk_tolerance": "conservative", "constraints": {}, "status": "active",
                       "created_at": now()}
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

    def submit_objective(self) -> dict:
        """Stage 0 ends: the founder hands over the outcome, not the team. Stage 1 decomposes it into requirements and
        Stage 2 proposes the organization; the founder's first decision is the workforce gate."""
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
        if d["kind"] == "approve_workforce" and edited.get("roles"):
            try:
                synthesis.override(self.proposal(), edited["roles"], self.requirements(),
                                   project_settings.get(self.store)["allow_workforce_override"])
            except (synthesis.OverrideRefused, IntelligenceError) as exc:
                raise EngineError(str(exc)) from exc
        elif d["kind"] == "budget_breaker" and "budget_usd" in edited:
            spent = budget.ledger(self.store)["spent_total"]
            try:
                new = float(edited["budget_usd"])
            except (TypeError, ValueError) as exc:
                raise EngineError("budget_usd must be a number") from exc
            if new <= spent:
                raise EngineError(f"the new budget must be above the ${spent:.4f} already spent")

    def _after_workforce(self, d: dict, action: str) -> None:
        if action != "approve":
            try:
                synthesis.reject(self, d.get("note") or "")
            except IntelligenceError as exc:
                self._stage_failed("workforce", exc)
            return
        synthesis.approve(self, (d.get("edited") or {}).get("roles"))
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

    def _roadmap(self, note: str = "") -> None:
        """Stage 5, then Stage 7: the roadmap for the approved organization and the budget built on it. Stage 6 puts
        both in front of the founder."""
        try:
            p = planner.plan(self, note)
            self._staff(refine=True)
        except IntelligenceError as exc:
            self._stage_failed("roadmap", exc)
        f = budget.construct(self.store, self.tasks(), self.workers(), self.registry, self.assigner_id())
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
               for t in self.tasks()]
        ev += [f"{k}: ${v['usd']:.4f} ({v['basis']})" for k, v in f["layers"].items()]
        ev += f["warnings"]
        if p["uncovered_requirements"]:
            ev.append("Requirements no task names: " + ", ".join(p["uncovered_requirements"]))
        self.decision("approve_roadmap",
                      problem=f"The roadmap for the approved organization: {len(p['milestones'])} milestones, "
                              f"{len(p['order'])} tasks, and the budget built on it.",
                      recommendation="Approve the roadmap and the budget. Work starts; MEDIUM and HIGH steps still "
                                     "come back to you.",
                      risk="LOW" if f["fits"] else "MEDIUM", confidence="high" if f["fits"] else "medium",
                      cost=f"${f['subtotal_usd']:.4f} forecast of the ${f['cap_usd']:.2f} cap, reserve "
                           f"${f['reserve_usd']:.4f}",
                      evidence=ev, change="A task that does not serve the objective, a missing one, or a budget line "
                                          "that looks wrong.", source="execution_planner")
        self.set_meta(phase="planning", failed_stage=None, notice="")

    def _after_roadmap(self, d: dict, action: str) -> None:
        if action != "approve":
            self._roadmap(note=d.get("note") or "The founder asked for a different roadmap.")
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

    def _after_breaker(self, d: dict, action: str) -> None:
        if action != "approve":
            self.set_meta(phase="stopped", notice="Run stopped at the budget cap by the founder.")
            return
        cap = project_settings.get(self.store)["budget_usd"]
        new = float(d["edited"].get("budget_usd") or max(cap, budget.ledger(self.store)["spent_total"]) * 1.5)
        budget.raise_cap(self.store, new)
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
               "BLOCKED": execution.answer, "REVIEW": execution.verify, "APPROVED": execution.execute_approved}

    def _round(self) -> list[str]:
        """The tasks that move this round: those whose inputs are ready, one per worker who has to act on them (the
        assigner hands a task over, the owner works on it, the colleague a Blocker names answers it)."""
        tasks = self.tasks()
        by_id = {t["id"]: t for t in tasks}
        busy: set[str] = set()
        out = []
        for t in tasks:
            s = t["status"]
            if s not in self.ACTIONS or (s == "PLANNED" and not all(
                    by_id[d]["status"] == "VERIFIED" for d in t["dependencies"])):
                continue
            actor = {"PLANNED": t.get("handoff_from"), "ASSIGNED": t["owner_worker_id"], "REWORK": t["owner_worker_id"],
                     "BLOCKED": (t.get("blocker") or {}).get("needs_from")}.get(s) or ""
            if actor.startswith("w_"):
                if actor in busy:
                    continue
                busy.add(actor)
            out.append(t["id"])
        return out

    def _act(self, tid: str) -> dict | None:
        """One worker's (or the platform's) piece of work on one task, as the step used to do it."""
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
            except ProtocolError as exc:
                return self._violation(self.task(tid), s, exc)
            except IntelligenceError as exc:
                handled = replacement.model_failed(self, self.task(tid), exc)
                if handled:
                    return handled
                self.set_meta(phase="stopped_error", failed_stage="run",
                              notice=f"Stopped on {tid}: the intelligence failed ({exc}). Nothing was invented.")
                self.event("task.failed", "task", tid, {"reason": "intelligence_error"}, correlation_id=tid)
                return {"did": "error", "task": tid, "why": str(exc)}

    def _violation(self, t: dict, state: str, exc: ProtocolError) -> dict:
        """A reply that is not a valid protocol object: counted against the worker whose reply it was."""
        t["attempts"] += 1
        self.save_task(t)
        culprit = (self.assigner_id() if state == "PLANNED" else (t.get("blocker") or {}).get("needs_from")
                   if state == "BLOCKED" else t["owner_worker_id"])
        n = self.count("violation") + 1
        self.store.put("violation", f"pv_{n:04d}", {"id": f"pv_{n:04d}", "worker_id": culprit,
                       "model_id": self.model_of(culprit) if culprit else None, "task_id": t["id"],
                       "error": str(exc)[:300], "at": now()})
        self.event("protocol.violation", "task", t["id"], {"worker": culprit, "error": str(exc)[:200]},
                   actor=culprit or "orchestrator", actor_type="worker", correlation_id=t["id"], policy_decision="DENY")
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
        self.event("state.changed", "company", self.cid, {"frozen": bool(on), "control": "kill_switch"},
                   actor="founder", actor_type="human", authority="founder", policy_decision="DENY" if on else "ALLOW")
        return self.meta

    def resume(self) -> dict:
        """After a model or network error: try the failed stage again. Nothing was written by the failed call."""
        with self.lock:
            self._require("stopped_error")
            stage = self.meta.get("failed_stage")
            self.intervention("resume", f"retry the {stage or 'run'} after an intelligence error")
            self.event("state.changed", "company", self.cid, {"control": "resume", "stage": stage}, actor="founder",
                       actor_type="human", authority="founder")
            if stage == "workforce":
                self.set_meta(phase="workforce", failed_stage=None, notice="")
                synthesis.propose(self, note="Retried after an intelligence error.")
            elif stage == "roadmap":
                if not any(self.model_of(w["id"]) for w in self.workers()):
                    self._staff()
                self._roadmap()
            else:
                self.set_meta(phase="running", failed_stage=None, notice="")
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
                          extra={"changes": changes, "previous_phase": self.meta["phase"]})
            self.set_meta(phase="paused_objective")
            return obj

    def _after_objective_change(self, d: dict, action: str) -> None:
        if action == "approve":
            obj = self.objective()
            obj["structured"].update(d["extra"]["changes"])
            obj["version"] += 1
            self.store.put("objective", "obj_1", obj)
            self.event("objective.changed", "objective", "obj_1", {"version": obj["version"], "status": "confirmed",
                       "fields_changed": sorted(d["extra"]["changes"])}, actor="founder", actor_type="human",
                       authority="founder")
        self.set_meta(phase=d["extra"].get("previous_phase", "running"))

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
                "settings": project_settings.get(self.store), "ledger": L, "system": bound.get(binding.SYSTEM),
                "replacements": self.store.all("replacement"), "models_in_use": in_use,
                "ceo_notices": self.store.all("ceo_notice"),
                "workers": [{"id": w["id"], "role": w["role"], "title": w["title"], "reports_to": w.get("reports_to"),
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
            "transition": self.store.get("transition", "tr_1"),
            "budget": {"settings": project_settings.get(self.store), "ledger": budget.ledger(self.store)},
            "forecast": forecast,
            "economics": budget.actual(self.store, forecast) if forecast else None,
            "workforce": self.workforce_view(),
            "supply": self.supply.snapshot() if self.supply else None,
            "performance": performance.all_cards(self.store, self.registry) if workers else [],
            "evaluations": self.store.all("evaluation"),
            "catalog": roles.catalog(),
            "final": self.final_report() if m["phase"] in ("delivered", "accepted") else None,
            "metrics": self.metrics() if company else {},
            "rules": self.rules(),
            "live_url": self.live_url(),
            "events": self.store.events()[-60:],
            "exports": sorted(p.name for p in self.paths["exports"].glob("*.zip")),
        }

    def close(self) -> None:
        deploy.stop(self.live_proc)
        self.store.close()
        if self._own is not None:
            self._own.close()
