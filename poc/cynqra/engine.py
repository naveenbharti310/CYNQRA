"""The Cynqra engine: one company, one objective, one run, following the product definition's canonical flow
(Cynqra Product Flows and Architecture v1, section 3):

  Stage 0  the founder submits a project name, an objective, a budget and any constraints
  Stage 1  Objective Intelligence: the objective structured, then decomposed into requirements and workstreams
  Stage 2  Workforce Synthesizer (synthesis.py): the organization this objective needs, from the role catalog
  Stage 3  Workforce approval gate: approve, reject (revised against the feedback), or edit where governance allows
  Stage 4  Intelligence Router (workforce.py): a model for each worker, from the registry's evidence
  Stage 5  Execution Planner (planner.py): milestones, tasks, acceptance criteria, owners, accountability
  Stage 6  Roadmap approval gate, with
  Stage 7  Budget Engine (budget.py): the budget in layers against the hard cap
  Stage 8  Governed execution: everything a worker does passes the Gateway (identity, policy, budget, target
           check, execute, sanitize, audit)
  Stage 9  Verification: completed is not verified
  Stage 10 Performance Engine (performance.py) and Replacement Engine (replacement.py): intelligence measured per
           worker and task, and kept, rerouted or replaced while the worker's identity stays

Everything the founder does is a decision with a label (D-10). The M1 build's fixed four-worker organization is a
test fixture (roles.FIXTURE_M1), not the product.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

import re

from . import budget as budget_engine
from . import deploy, performance, planner, policy, replacement, roles, synthesis
from .db import IST, Store, digest, now
from .intelligence import IntelligenceError, ModelSource, make
from .protocol import ProtocolError, build
from .verification import failure_summary, lint_documents, run_unittests
from .workforce import Workforce

OBJECTIVE_FIELDS = ["product", "target_customer", "primary_outcome", "business_outcome",
                    "success_criteria", "constraints", "priorities"]
CONSTRAINT_KEYS = ["deadline", "geography", "technology", "compliance", "risk_tolerance"]  # Stage 0, optional
# Output a worker may never write into the workspace: credentials. Found in a write, the write is refused (Stage 8,
# "output is sanitized and recorded"); the refusal is audited like any policy decision.
SECRET = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-ant-[\w-]{20,}|\bsk-[A-Za-z0-9]{32,}|\bhf_[A-Za-z0-9]{30,}"
                    r"|\bAKIA[0-9A-Z]{16}\b|\bghp_[A-Za-z0-9]{36}\b")
UNIT_COST = {"write_file": 1, "read_artifact": 0, "run_tests": 2, "merge_to_main": 2, "deploy_production": 4,
             "verify": 2, "integrate": 0}
ALLOWED_EXT = {".py", ".md", ".html", ".json", ".txt", ".css", ".js"}
ESCALATIONS_PER_DAY = 5  # D-29
MAX_ATTEMPTS = 3
MAX_CUT_OFFS = 3  # replies in a row cut off at the model's output limit before a task is escalated
TASK_STATES = ["PLANNED", "ASSIGNED", "IN_PROGRESS", "BLOCKED", "REVIEW", "REWORK", "AWAITING_FOUNDER",
               "APPROVED", "VERIFIED", "FAILED"]


DEMO_DEFAULT_CAP = 120
LIVE_DEFAULT_CAP = 600


class EngineError(RuntimeError):
    pass


class Engine:
    def __init__(self, data_dir: Path, intelligence=None, scenario: str = "candidate_tracker",
                 workforce: Workforce | None = None):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.store = Store(str(self.dir / "cynqra.db"))
        self.paths = {k: self.dir / k for k in ("workspaces", "integration", "main", "releases", "live", "exports")}
        for p in self.paths.values():
            p.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.scenario = scenario
        scen = Path(__file__).resolve().parent.parent / "scenarios" / scenario / "scenario.json"
        self.demo_messy = json.loads(scen.read_text(encoding="utf-8"))["messy"] if scen.exists() else ""
        self._injected = intelligence  # tests pass a source here; it survives create_company
        self._intel = intelligence
        self.wf = workforce  # the model registry and workforce engine; None: one model for every worker
        self.live_proc = None
        meta = self.store.get("meta", "run")
        if meta is None:
            meta = {"company_id": "co_" + uuid.uuid4().hex[:8], "phase": "new", "mode": "demo", "frozen": False,
                    "created_at": now(), "notice": ""}
            self.store.put("meta", "run", meta)

    # --- small helpers ------------------------------------------------------
    @property
    def meta(self) -> dict:
        return self.store.get("meta", "run")

    def _set_meta(self, **kw) -> dict:
        m = self.meta
        m.update(kw)
        return self.store.put("meta", "run", m)

    @property
    def cid(self) -> str:
        return self.meta["company_id"]

    @property
    def intel(self):
        if self._intel is None:
            if self.staffed_by_registry():
                self._intel = ModelSource(router=self._route)
            else:
                self._intel = make(self.meta.get("mode", "demo"), self.scenario)
        return self._intel

    # --- the workforce: which model each worker runs on (workforce.py, registry.py) -------------------
    def staffed_by_registry(self) -> bool:
        """A live run staffs its workers from the model registry when the registry has a model to offer."""
        if self.meta.get("mode") != "live" or self.wf is None:
            return False
        if "registry" not in self.meta:
            self._set_meta(registry=self.wf.usable())
        return bool(self.meta["registry"])

    def _route(self, worker_id: str) -> tuple[str, dict]:
        if worker_id == "system" or self.worker(worker_id) is None:
            sys_ = self.store.get("workforce", "system")
            if not (sys_ and sys_.get("model_id")) or not self.wf.reg.availability(self.wf.reg.get(sys_["model_id"]))[0]:
                best, rows = self.wf.choose(self.store, ["objective"])
                if best is None:
                    raise IntelligenceError("no available model in the registry")
                sys_ = {"model_id": best["model_id"], "candidates": rows}
                self.store.put("workforce", "system", sys_)
            model_id = sys_["model_id"]
        else:
            model_id = self.worker(worker_id)["model_id"]
        return model_id, self.wf.reg.route(model_id)

    def _staff(self, refine: bool = False) -> None:
        """Stage 4: a model for every worker. First over its role's kinds of work; once the roadmap exists, refined to
        the kinds of the tasks the worker actually owns (two workers with the same title can end up on different
        models when their workloads differ, and one model can power many workers)."""
        workers = self.store.all("worker")
        workload = None
        if refine:
            workload = {}
            for t in self.tasks():
                workload.setdefault(t["owner_worker_id"], [])
                if t["kind"] not in workload[t["owner_worker_id"]]:
                    workload[t["owner_worker_id"]].append(t["kind"])
            a = self.assigner_id()
            if a and any(t["owner_worker_id"] != a for t in self.tasks()):
                workload.setdefault(a, []).append("assign")
        staffing = self.wf.staff(self.store, workers, workload)
        for wid, s in staffing.items():
            w = self.worker(wid)
            if refine and w.get("model_id") == s["model_id"]:
                continue
            before = w.get("model_id")
            w.update({"model_id": s["model_id"], "intelligence_source_id": s["model"], "cost_profile": "USD, metered"})
            self.store.put("worker", wid, w)
            why = ("refined to the roadmap's workload: " + ", ".join(s["kinds"]) if refine else
                   "lowest expected cost per verified task for its role's work: " + ", ".join(s["kinds"]))
            self.store.put("staffing", wid, {"worker_id": wid, "model_id": s["model_id"], "candidates": s["candidates"],
                                              "at": now(), "why": why, "kinds": s["kinds"], "previous": before})
            self.event("worker.model_assigned", "worker", wid, {"role": w["role"], "model_id": s["model_id"],
                       "model": s["model"], "why": why, "candidates": [{k: r[k] for k in ("model", "score", "p_task",
                       "expected_usd", "expected_minutes")} for r in s["candidates"]]}, actor="intelligence_router")

    def model_of(self, wid: str) -> str | None:
        w = self.worker(wid)
        return (w or {}).get("model_id")

    def _meter(self, task_id: str) -> dict:
        return self.store.get("meter", task_id) or {"usd": 0.0, "seconds": 0.0, "tokens": 0}

    def _outcome(self, t: dict, verified: bool, failure: str = "") -> None:
        """One verification of one attempt: counted for the model that did it, for its kind of task."""
        if not self.staffed_by_registry():
            return
        model_id = self.model_of(t["owner_worker_id"])
        m = self._meter(t["id"])
        self.wf.reg.record_outcome(model_id, role=self.worker(t["owner_worker_id"])["role"], task_kind=t["kind"],
                                   task_id=t["id"], run_id=self.cid, attempt=t["attempts"] + 1, verified=verified,
                                   usd=m["usd"], seconds=m["seconds"], tokens=m["tokens"], failure=failure)
        self.store.put("meter", t["id"], {"usd": 0.0, "seconds": 0.0, "tokens": 0})

    def _replace_or_escalate(self, t: dict, why: str) -> dict:
        """A worker keeps failing a task: the Replacement Engine gives the work another intelligence that passes its
        regression check (another model for this worker, or a peer of the same role), or the founder decides."""
        return replacement.evaluate(self, t, why, forced=True)

    # --- the organization, read from the store ---------------------------------------------------------
    def workers(self) -> list[dict]:
        return self.store.all("worker")

    def assigner_id(self) -> str | None:
        return roles.assigner(self.workers())

    def answerers(self) -> list[str]:
        return roles.answerers(self.workers()) or [self.assigner_id()]

    def persona(self, wid: str) -> str:
        w = self.worker(wid)
        return roles.prompt_text(w) if w else ""

    def objective_ctx(self) -> dict:
        obj = self.objective()
        return {**obj["structured"], "_constraints": obj.get("founder_constraints") or {}}

    def _model_failed(self, t: dict, exc: IntelligenceError) -> dict | None:
        """A call to a worker's model failed. Counted against the model; a model down after repeated failures is
        replaced in every worker that runs on it, and the step is tried again."""
        if not (self.staffed_by_registry() and exc.model_id):
            return None
        n = self._count("call_error") + 1
        involved = [t.get("owner_worker_id"), self.assigner_id(), (t.get("blocker") or {}).get("needs_from")]
        caller = next((w for w in involved if w and self.model_of(w) == exc.model_id), t.get("owner_worker_id"))
        self.store.put("call_error", f"ce_{n:04d}", {"id": f"ce_{n:04d}", "worker_id": caller,
                       "model_id": exc.model_id, "task_id": t.get("id"), "error": str(exc)[:300], "at": now()})
        self.wf.reg.record_call(exc.model_id, role="", purpose="error", task_kind=t.get("kind", ""), usage=exc.usage,
                                run_id=self.cid, error=str(exc))
        m = self.wf.reg.get(exc.model_id)
        if self.wf.reg.availability(m)[0]:
            return {"did": "model_error_retry", "task": t["id"], "model": exc.model_id, "why": str(exc)}
        out = None
        for w in self.store.all("worker"):
            if w.get("model_id") == exc.model_id:
                mine = [x for x in self.tasks() if x["owner_worker_id"] == w["id"] and x["status"] not in ("VERIFIED",)]
                target = t if t["owner_worker_id"] == w["id"] else (mine[0] if mine else None)
                if target is not None:
                    out = self._replace_or_escalate(target, f"{m['name']} stopped answering: {exc}")
                w = self.worker(w["id"])
                if w.get("model_id") == exc.model_id:  # no open task, or its task was rerouted to a peer
                    best, _ = self.wf.choose(self.store, roles.staffing_kinds(w["role"]), exclude={exc.model_id},
                                             role_name=w["role"])
                    if best:
                        w.update({"model_id": best["model_id"], "intelligence_source_id": best["model"]})
                        self.store.put("worker", w["id"], w)
                        self.event("worker.model_assigned", "worker", w["id"], {"role": w["role"],
                                   "model_id": best["model_id"], "model": best["model"],
                                   "why": f"{m['name']} is down"}, actor="intelligence_router")
        sys_ = self.store.get("workforce", "system")
        if sys_ and sys_.get("model_id") == exc.model_id:
            self.store.put("workforce", "system", {"model_id": None})  # chosen again on the next call
        return out or {"did": "model_replaced", "task": t["id"], "model": exc.model_id}

    def event(self, event_type: str, aggregate_type: str, aggregate_id: str, payload: dict, *,
              actor: str = "orchestrator", actor_type: str = "service", correlation_id: str | None = None,
              policy_decision: str = "ALLOW", authority: str = "platform", protocol_hash: str | None = None,
              test_ids: list | None = None, context_refs: list | None = None) -> dict:
        return self.store.append(
            company_id=self.cid, event_type=event_type, aggregate_type=aggregate_type, aggregate_id=aggregate_id,
            actor_type=actor_type, actor_id=actor, payload=payload,
            correlation_id=correlation_id or aggregate_id, policy_decision=policy_decision,
            authority_snapshot=authority, protocol_hash=protocol_hash, test_ids=test_ids, context_refs=context_refs)

    def _require(self, phase: str | tuple) -> None:
        phases = (phase,) if isinstance(phase, str) else phase
        if self.meta["phase"] not in phases:
            raise EngineError(f"not allowed in phase {self.meta['phase']}; needs {' or '.join(phases)}")

    def objective(self) -> dict | None:
        return self.store.get("objective", "obj_1")

    def rules(self) -> list[str]:
        return (self.store.get("memory", "decided_rules") or {}).get("rules", [])

    def tasks(self) -> list[dict]:
        order = (self.store.get("plan", "plan_1") or {}).get("order", [])
        return [self.store.get("task", t) for t in order]

    def task(self, tid: str) -> dict:
        t = self.store.get("task", tid)
        if t is None:
            raise EngineError(f"unknown task {tid}")
        return t

    def _save_task(self, t: dict) -> dict:
        return self.store.put("task", t["id"], t)

    def worker(self, wid: str) -> dict:
        return self.store.get("worker", wid)

    def _count(self, kind: str) -> int:
        return len(self.store.all(kind))

    # --- budget (Book 1 P0 10, Book 3 section 2) -----------------------------
    def budget(self) -> dict:
        return self.store.get("budget", "company") or {"cap": 120, "spent": 0, "warned": [], "state": "ok"}

    def charge(self, units: int, reason: str, task_id: str | None = None) -> None:
        if units <= 0:
            return
        b = self.budget()
        b["spent"] += units
        pct = 100 * b["spent"] / max(1, b["cap"])
        for mark in (50, 80, 95):
            if pct >= mark and mark not in b["warned"]:
                b["warned"].append(mark)
                self.event("budget.threshold_reached", "company", self.cid,
                           {"threshold": mark, "spent": b["spent"], "cap": b["cap"], "unit": "work_units"},
                           actor="budget", correlation_id=task_id or self.cid)
        self.store.put("budget", "company", b)
        if b["spent"] >= b["cap"] and b["state"] != "breaker":
            self._breaker(f"{b['spent']} of {b['cap']} work units", unit="work_units", task_id=task_id)

    def _breaker(self, what: str, unit: str, task_id: str | None = None) -> None:
        """The hard stop: the dollar cap (a run staffed from the registry) or the work-unit cap. All work pauses."""
        b = self.budget()
        b.update({"state": "breaker", "breaker_unit": unit})
        self.store.put("budget", "company", b)
        self.event("budget.threshold_reached", "company", self.cid, {"threshold": 100, "spent": what, "unit": unit},
                   actor="budget", policy_decision="DENY", correlation_id=task_id or self.cid)
        if unit == "USD":
            cap = float(self.wf.settings(self.store)["budget_usd"])
            rec = f"Raise the budget from ${cap:.2f} to ${cap * 1.5:.2f}, or stop the run."
        else:
            rec = f"Raise the cap from {b['cap']} to {b['cap'] + 60} work units, or stop the run."
        self._decision("budget_breaker", problem="The project's budget cap is reached. All work is paused.",
                       recommendation=rec, risk="HIGH", confidence="high", cost="none until work resumes",
                       evidence=[f"spent {what}"], change="Nothing: the cap is yours to set.", severity="SEV-2",
                       source="budget", extra={"unit": unit})

    # --- gateway ------------------------------------------------------------
    def gateway(self, worker_id: str, task_id: str, action_type: str, target: str = "", *,
                content: str | None = None, approval: str | None = None, cwd: Path | None = None) -> dict:
        """request -> identity -> policy -> budget -> target validation -> execute -> sanitize -> audit."""
        w = self.worker(worker_id)
        if w is None or w.get("status") != "active":
            raise EngineError(f"unknown or inactive worker {worker_id}")
        b = self.budget()
        decision = policy.evaluate(role=w["role"], action_type=action_type, frozen=self.meta["frozen"],
                                   budget_state=b["state"], target=target)
        action_id = "a_" + uuid.uuid4().hex[:10]
        action = {"id": action_id, "company_id": self.cid, "task_id": task_id, "worker_id": worker_id,
                  "role": w["role"], "action_type": action_type, "target": target, "risk_tier": decision["risk_tier"],
                  "policy_decision": decision["decision"], "policy_reason": decision["reason"],
                  "policy_version": decision["policy_version"],
                  "authority_snapshot": {k: v for k, v in policy.MATRIX.get(w["role"], {}).items()},
                  "intelligence": w["intelligence_source_id"], "model_id": w.get("model_id"),
                  "budget_before": b["spent"], "status": "",
                  "created_at": now(), "approval": approval}
        auth = f"{w['role']}:{policy.MATRIX.get(w['role'], {}).get(action_type, 'none')}"
        if decision["decision"] == "DENY":
            action["status"] = "denied"
            self.store.put("action", action_id, action)
            self.event("action.denied", "action", action_id, {"task_id": task_id, "action_type": action_type,
                       "reason": decision["reason"], "risk_tier": decision["risk_tier"]},
                       actor=worker_id, actor_type="worker", correlation_id=task_id, policy_decision="DENY", authority=auth)
            return {"status": "denied", "action": action, "policy": decision}
        if decision["decision"] == "REQUIRE_APPROVAL":
            d = self.store.get("decision", approval) if approval else None
            if not d or d.get("status") != "approved" or d.get("action_type") != action_type:
                action["status"] = "proposed"
                self.store.put("action", action_id, action)
                self.event("action.proposed", "action", action_id, {"task_id": task_id, "action_type": action_type,
                           "risk_tier": decision["risk_tier"], "reason": decision["reason"]},
                           actor=worker_id, actor_type="worker", correlation_id=task_id,
                           policy_decision="REQUIRE_APPROVAL", authority=auth)
                return {"status": "requires_approval", "action": action, "policy": decision}
            action["status"] = "approved"
        # target validation and execution
        result: dict = {}
        if action_type == "write_file":
            out_dir = self._ws(worker_id, task_id) / "out"
            rel = Path(target)
            if rel.is_absolute() or ".." in rel.parts or rel.suffix not in ALLOWED_EXT or len(rel.parts) > 3:
                return self._deny_target(action, task_id, auth, f"target {target!r} is outside the workspace rules")
            if content is None or len(content.encode("utf-8")) > 200_000:
                return self._deny_target(action, task_id, auth, "content missing or larger than 200 KB")
            if SECRET.search(content):
                return self._deny_target(action, task_id, auth, "content holds what looks like a credential; "
                                         "keys belong in environment variables, never in files")
            dest = (out_dir / rel).resolve()
            if out_dir.resolve() not in dest.parents:
                return self._deny_target(action, task_id, auth, "path escapes the workspace")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            result = {"file": target, "hash": digest(content.encode("utf-8")), "bytes": len(content.encode("utf-8"))}
        elif action_type == "run_tests":
            folder = cwd or self._ws(worker_id, task_id) / "out"
            t0 = time.time()
            report = run_unittests(folder)
            result = {"ran": report["ran"], "passed": report["passed"], "failed": report["failed"],
                      "test_ids": [t["id"] for t in report["tests"]], "seconds": round(time.time() - t0, 2)}
        elif action_type == "merge_to_main":
            main = self.paths["main"]
            if main.exists():
                shutil.rmtree(main)
            shutil.copytree(self.paths["integration"], main)
            files = sorted(str(p.relative_to(main)) for p in main.rglob("*") if p.is_file())
            result = {"files": len(files), "tree": digest({f: digest((main / f).read_bytes()) for f in files})}
        elif action_type in ("deploy_production", "product_rule_decision", "assign_task", "answer_blocker",
                             "send_protocol", "read_artifact", "review_work"):
            result = {"ok": True}
        else:
            return self._deny_target(action, task_id, auth, f"no tool implementation for {action_type}")
        self.charge(UNIT_COST.get(action_type, 1), action_type, task_id)
        action.update({"status": "executed", "result": result, "budget_after": self.budget()["spent"]})
        self.store.put("action", action_id, action)
        self.event("action.executed", "action", action_id, {"task_id": task_id, "action_type": action_type,
                   "target": target, "approval": approval, "result": {k: v for k, v in result.items() if k != "test_ids"}},
                   actor=worker_id, actor_type="worker", correlation_id=task_id,
                   policy_decision=decision["decision"], authority=auth, test_ids=result.get("test_ids"))
        out = {"status": "executed", "action": action, "result": result, "policy": decision}
        if action_type == "run_tests":
            out["report"] = report  # the whole run, output included, for the caller; the audit log keeps the summary
        return out

    def _deny_target(self, action: dict, task_id: str, auth: str, why: str) -> dict:
        action.update({"status": "denied", "policy_decision": "DENY", "policy_reason": why})
        self.store.put("action", action["id"], action)
        self.event("action.denied", "action", action["id"], {"task_id": task_id, "action_type": action["action_type"],
                   "reason": why}, actor=action["worker_id"], actor_type="worker", correlation_id=task_id,
                   policy_decision="DENY", authority=auth)
        return {"status": "denied", "action": action, "policy": {"decision": "DENY", "reason": why}}

    def _ws(self, worker_id: str, task_id: str) -> Path:
        p = self.paths["workspaces"] / worker_id / task_id
        (p / "inbox").mkdir(parents=True, exist_ok=True)
        (p / "out").mkdir(parents=True, exist_ok=True)
        return p

    # --- protocol -----------------------------------------------------------
    def send(self, kind: str, content: dict | None, routing: dict, task_id: str, sender: str) -> dict:
        obj = build(kind, content, routing, task_id)
        h = self.store.put_object("protocol", obj)
        entry = {"id": obj["object_hash"], "hash": h, "kind": kind, "task_id": task_id, "sender": sender,
                 "to": obj.get("to_worker") or obj.get("needs_from") or obj.get("owner") or "",
                 "created_at": obj["created_at"], "summary": (obj.get("acceptance_check") or obj.get("description")
                                                              or obj.get("recommendation") or obj.get("issue") or "")[:300],
                 "artifacts": obj.get("artifacts", [])}
        self.store.put("protocol", obj["object_hash"], entry)
        is_worker = sender.startswith("w_")
        self.event("protocol.sent", "protocol", obj["object_hash"], {"kind": kind, "from": sender, "to": entry["to"],
                   "task_id": task_id, "artifacts": entry["artifacts"]},
                   actor=sender, actor_type="worker" if is_worker else "service", correlation_id=task_id,
                   protocol_hash=h)
        return obj

    # --- decisions (the founder's inbox) --------------------------------------
    def _decision(self, kind: str, *, problem: str, recommendation: str, risk: str, confidence: str, cost: str,
                  evidence: list, change: str, task_id: str | None = None, action_type: str | None = None,
                  severity: str = "SEV-3", source: str = "orchestrator", extra: dict | None = None) -> dict:
        today = datetime.now(IST).date().isoformat()
        worker_raised = source.startswith("w_")
        todays = [d for d in self.store.all("decision")
                  if d.get("created_day") == today and d.get("source", "").startswith("w_")]
        digest_it = worker_raised and len(todays) >= ESCALATIONS_PER_DAY and severity != "SEV-1"
        did = "dec_" + (task_id or kind) + ("_" + uuid.uuid4().hex[:4] if self.store.get("decision", "dec_" + (task_id or kind)) else "")
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

    def pending_decisions(self) -> list[dict]:
        return [d for d in self.store.all("decision") if d["status"] == "pending"]

    def decide(self, decision_id: str, action: str, note: str = "", edited: dict | None = None) -> dict:
        with self.lock:
            d = self.store.get("decision", decision_id)
            if d is None:
                raise EngineError(f"unknown decision {decision_id}")
            if d["status"] != "pending":
                raise EngineError(f"decision {decision_id} is already {d['status']}")
            if action not in ("approve", "reject", "request_evidence"):
                raise EngineError(f"unknown action {action}")
            edited = {k: v for k, v in (edited or {}).items() if v not in (None, "")}
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
            self._intervention(decision_id, label)
            self.event("decision.approved" if action == "approve" else "decision.rejected", "decision", decision_id,
                       {"kind": d["kind"], "outcome_label": label, "task_id": d.get("task_id")}, actor="founder",
                       actor_type="human", authority="founder", correlation_id=d.get("task_id") or decision_id,
                       policy_decision="ALLOW")
            handler = getattr(self, "_after_" + d["kind"], None)
            if handler:
                handler(d, action)
            return d

    def _intervention(self, ref: str, what: str) -> None:
        n = self._count("intervention") + 1
        self.store.put("intervention", f"int_{n:03d}", {"id": f"int_{n:03d}", "ref": ref, "action": what,
                                                        "counts": True, "at": now()})

    # --- founder journey ------------------------------------------------------
    def create_company(self, name: str, mode: str = "demo") -> dict:
        with self.lock:
            self._require("new")
            if mode not in ("demo", "live"):
                raise EngineError("mode must be demo or live")
            name = (name or "").strip() or "My company"
            self._set_meta(mode=mode)
            if mode == "live" and self.wf is not None:
                self._set_meta(registry=self.wf.usable())  # staffed from the registry for the whole run, or not at all
            self._intel = self._injected
            _ = self.intel  # live mode fails here, before anything is written, if no key
            # Live mode charges one unit per 1000 real tokens, so a whole run needs far more room than demo mode.
            cap = LIVE_DEFAULT_CAP if mode == "live" else DEMO_DEFAULT_CAP
            company = {"id": self.cid, "name": name, "stage": "IDEA", "autonomy_level": "L1",
                       "budget_cap": cap, "risk_tolerance": "conservative", "status": "active", "created_at": now()}
            self.store.put("company", self.cid, company)
            self.store.put("budget", "company", {"cap": cap, "spent": 0, "warned": [], "state": "ok"})
            self.event("company.created", "company", self.cid, {"stage": "IDEA", "autonomy_level": "L1", "mode": mode},
                       actor="founder", actor_type="human", authority="founder")
            self._set_meta(phase="objective")
            return company

    def draft_objective(self, messy: str) -> dict:
        with self.lock:
            self._require("objective")
            if not (messy or "").strip():
                raise EngineError("write the objective first")
            data, usage = self.intel.structure_objective(messy)
            self._record_call("objective", "objective_system", "structure_objective", usage)
            structured = {k: str(data.get(k) or "").strip() for k in OBJECTIVE_FIELDS}
            inferred = [k for k in (data.get("inferred_fields") or []) if k in OBJECTIVE_FIELDS]
            missing = [k for k in OBJECTIVE_FIELDS if not structured[k]]
            prev = self.objective()
            version = (prev or {}).get("version", 0) + 1 if prev and prev["status"] == "draft" else 1
            obj = {"id": "obj_1", "company_id": self.cid, "statement": messy.strip(), "structured": structured,
                   "inferred_fields": inferred, "missing_fields": missing, "priority": "primary",
                   "constraints": structured["constraints"], "status": "draft", "version": version,
                   "notice": data.get("notice", ""), "intelligence": usage["label"], "created_at": now()}
            self.store.put("objective", "obj_1", obj)
            self.event("objective.created" if version == 1 else "objective.changed", "objective", "obj_1",
                       {"version": version, "status": "draft", "statement_hash": digest(messy.strip()),
                        "inferred_fields": inferred, "missing_fields": missing}, actor="objective_system")
            return obj

    def edit_objective(self, fields: dict) -> dict:
        with self.lock:
            obj = self.objective()
            if obj is None:
                raise EngineError("no objective yet")
            if obj["status"] != "draft":
                return self.request_objective_change(fields)
            changed = []
            for k, v in (fields or {}).items():
                if k in OBJECTIVE_FIELDS and str(v).strip() and str(v).strip() != obj["structured"][k]:
                    obj["structured"][k] = str(v).strip()
                    changed.append(k)
            obj["inferred_fields"] = [k for k in obj["inferred_fields"] if k not in changed]
            obj["missing_fields"] = [k for k in OBJECTIVE_FIELDS if not obj["structured"][k]]
            obj["constraints"] = obj["structured"]["constraints"]
            self.store.put("objective", "obj_1", obj)
            if changed:
                self.event("objective.changed", "objective", "obj_1", {"version": obj["version"], "status": "draft",
                           "fields_changed": changed}, actor="founder", actor_type="human", authority="founder")
            return obj

    def set_guardrails(self, budget_cap: int | None = None, risk_tolerance: str | None = None,
                       budget_usd: float | None = None, time_value_per_hour: float | None = None,
                       constraints: dict | None = None, governance: dict | None = None) -> dict:
        """Stage 0: the allocated budget and any explicit constraints (deadline, geography, technology, compliance,
        risk tolerance)."""
        with self.lock:
            self._require("objective")
            if budget_usd is not None or time_value_per_hour is not None or governance:
                s = Workforce.settings(self.store)
                if budget_usd is not None:
                    if float(budget_usd) < 0:
                        raise EngineError("the budget cannot be negative")
                    s["budget_usd"] = round(float(budget_usd), 4)
                if time_value_per_hour is not None:
                    s["time_value_per_hour"] = max(0.0, float(time_value_per_hour))
                for k in ("compute_usd_per_hour", "infra_usd_per_day", "reserve_min_pct"):
                    if (governance or {}).get(k) is not None:
                        s[k] = max(0.0, float(governance[k]))
                if (governance or {}).get("allow_workforce_override") is not None:
                    s["allow_workforce_override"] = bool(governance["allow_workforce_override"])
                self.store.put("workforce", "settings", s)
                self.event("budget.changed", "company", self.cid, {"budget_usd": s["budget_usd"],
                           "time_value_per_hour": s["time_value_per_hour"], "unit": "USD"},
                           actor="founder", actor_type="human", authority="founder")
            b = self.budget()
            company = self.store.get("company", self.cid)
            if budget_cap is not None:
                cap = int(budget_cap)
                if cap < 20:
                    raise EngineError("budget cap must be at least 20 work units")
                b["cap"] = cap
                company["budget_cap"] = cap
                self.store.put("budget", "company", b)
                self.event("budget.changed", "company", self.cid, {"cap": cap, "unit": "work_units"},
                           actor="founder", actor_type="human", authority="founder")
            if risk_tolerance:
                company["risk_tolerance"] = risk_tolerance
            if constraints:
                obj = self.objective()
                clean = {k: str(v).strip() for k, v in constraints.items() if k in CONSTRAINT_KEYS and str(v or "").strip()}
                if obj is not None:
                    obj["founder_constraints"] = clean
                    self.store.put("objective", "obj_1", obj)
                company["constraints"] = clean
                if clean.get("risk_tolerance"):
                    company["risk_tolerance"] = clean["risk_tolerance"]
            self.store.put("company", self.cid, company)
            return company

    def submit_objective(self) -> dict:
        """Stage 0 ends: the founder hands over the outcome, not the team. Stages 1 and 2 run at once: the objective
        is decomposed into requirements and Cynqra proposes the organization. The founder's first decision is the
        workforce gate."""
        with self.lock:
            self._require("objective")
            obj = self.objective()
            if obj is None:
                raise EngineError("write the objective first")
            for k in obj["missing_fields"]:
                obj["structured"][k] = "not stated in the brief"
            company = self.store.get("company", self.cid)
            obj.update({"status": "submitted", "submitted_at": now(), "project": company["name"],
                        "founder_constraints": obj.get("founder_constraints") or company.get("constraints") or {}})
            self.store.put("objective", "obj_1", obj)
            self._intervention("objective", "submitted")
            self.event("objective.changed", "objective", "obj_1", {"version": obj["version"], "status": "submitted",
                       "constraints": sorted(obj["founder_constraints"])}, actor="founder", actor_type="human",
                       authority="founder")
            try:
                pkg, usage = self.intel.decompose(self.objective_ctx())
                self._record_call("objective", "objective_system", "decompose", usage)
                self.store.put("requirements", "req_1", {"id": "req_1", **pkg, "objective_version": obj["version"],
                                                         "intelligence": usage["label"], "created_at": now()})
                self.event("objective.decomposed", "objective", "obj_1", {"requirements": len(pkg["requirements"]),
                           "workstreams": len(pkg["workstreams"]), "critical_path": pkg["critical_path"]},
                           actor="objective_intelligence")
                self._synthesize()
            except IntelligenceError as exc:
                obj["status"] = "draft"
                self.store.put("objective", "obj_1", obj)
                self._set_meta(notice=f"Objective intelligence failed: {exc}. Nothing was invented. Submit again to retry.")
                raise
            return self.objective()

    confirm_objective = submit_objective  # the M1 name of the same step

    def requirements(self) -> dict | None:
        return self.store.get("requirements", "req_1")

    def proposal(self) -> dict | None:
        cur = (self.store.get("workforce", "proposal") or {}).get("id")
        return self.store.get("proposal", cur) if cur else None

    def _synthesize(self, note: str = "") -> dict:
        """Stage 2: the Workforce Synthesizer proposes the organization; Stage 3 puts it in front of the founder."""
        req = self.requirements()
        prop, usage = self.intel.synthesize(self.objective_ctx(), req, note=note)
        self._record_call("objective", "workforce_synthesizer", "synthesize", usage)
        n = self._count("proposal") + 1
        prop.update({"id": f"wp_{n}", "version": n, "note": note, "intelligence": usage["label"], "created_at": now(),
                     "status": "proposed"})
        costs = synthesis.cost_by_role(self.wf, self.store, prop) if self.staffed_by_registry() else None
        prop["cost_by_role"] = costs
        self.store.put("proposal", prop["id"], prop)
        self.store.put("workforce", "proposal", {"id": prop["id"]})
        self.event("workforce.proposed", "organization", "org_1", {"proposal": prop["id"], "roles": {
            r["role"]: r["quantity"] for r in prop["roles"]}, "workers": len(prop["workers"])},
            actor="workforce_synthesizer")
        total = sum(r["quantity"] for r in prop["roles"])
        self._decision("approve_workforce",
                       problem=f"Cynqra proposes a {total}-worker organization for your objective. {prop['summary']}",
                       recommendation="Approve the proposed organization. Cynqra then assigns a model to every worker "
                                      "and builds the roadmap and the budget for your second approval.",
                       risk="LOW", confidence="medium",
                       cost=(f"about ${sum(costs.values()):.4f} of model work per unit of each role's work" if costs
                             else "priced in the roadmap and budget, next"),
                       evidence=synthesis.evidence(prop, req, costs),
                       change="A role the requirements do not need, a missing one, or a quantity that is wrong.",
                       source="workforce_synthesizer", extra={"proposal": prop["id"]})
        self._set_meta(phase="workforce", notice="")
        return prop

    def _after_approve_workforce(self, d: dict, action: str) -> None:
        prop = self.proposal()
        if action != "approve":
            prop["status"] = "rejected"
            self.store.put("proposal", prop["id"], prop)
            self._synthesize(note=d.get("note") or "The founder rejected the proposal.")
            return
        edited = (d.get("edited") or {}).get("roles")
        if edited:
            prop = dict(prop, **synthesis.override(prop, edited, self.requirements(),
                                                   bool(Workforce.settings(self.store)["allow_workforce_override"])))
            self.event("workforce.overridden", "organization", "org_1", {"proposal": prop["id"], "roles": {
                r["role"]: r["quantity"] for r in prop["roles"]}}, actor="founder", actor_type="human",
                authority="founder")
        prop["status"] = "approved"
        self.store.put("proposal", prop["id"], prop)
        self._instantiate_org(prop)
        try:
            self._plan()
        except IntelligenceError as exc:
            self._set_meta(notice=f"Planning failed: {exc}. Nothing was invented.", phase="stopped_error",
                           failed_stage="plan")
            raise

    def _instantiate_org(self, prop: dict) -> None:
        """The approved proposal becomes the organization: workers with identities, roles, authority and reporting
        lines generated from who is present (roles.instantiate). Then Stage 4: a model for each worker."""
        if self.store.get("organization", "org_1"):
            return
        label = self.intel.label
        workers = prop["workers"]
        org = {"id": "org_1", "company_id": self.cid, "template": "synthesized", "proposal": prop["id"], "version": 1,
               "status": "approved", "workers": [w["id"] for w in workers],
               "roles": {r["role"]: r["quantity"] for r in prop["roles"]},
               "reports_to": {w["id"]: w["reports_to"] for w in workers},
               "services": [{"id": "verification", "title": "Verification Service",
                             "note": "Platform service, not a worker. Runs tests, lint and review tiers."}]}
        self.store.put("organization", "org_1", org)
        self.event("organization.changed", "organization", "org_1", {"template": "synthesized", "proposal": prop["id"],
                   "worker_count": len(workers), "version": 1})
        for t in workers:
            w = dict(t)
            w.update({"company_id": self.cid, "intelligence_source_id": label,
                      "authority_policy_id": f"{policy.POLICY_VERSION}:{t['role']}", "cost_profile": "work units",
                      "status": "active",
                      "performance_profile": {"verified": 0, "first_pass": 0, "reworks": 0, "blockers": 0}})
            self.store.put("worker", t["id"], w)
            self.event("worker.hired", "worker", t["id"], {"role": t["role"], "intelligence": label,
                                                            "reports_to": t["reports_to"]})
        if self.staffed_by_registry():
            self._staff()

    def _plan(self, note: str = "") -> None:
        """Stage 5, then Stage 7: the roadmap for the approved organization, and the budget built on it. Stage 6
        puts both in front of the founder."""
        workers = self.workers()
        planner_id = self.assigner_id()
        plan, usage = self.intel.plan(self.objective_ctx(), note=note, workers=workers, requirements=self.requirements(),
                                      planner=planner_id, persona=self.persona(planner_id))
        self._record_call("plan", planner_id, "plan", usage)
        plan = planner.enrich(plan, workers)
        order = []
        for i, t in enumerate(plan["tasks"]):
            task = dict(t)
            task.update({"company_id": self.cid, "objective_id": "obj_1", "context": f"objective v{self.objective()['version']}",
                         "authority_policy_id": f"{policy.POLICY_VERSION}:{self.worker(t['owner_worker_id'])['role']}",
                         "status": "PLANNED", "attempts": 0, "work_calls": 0, "blockers": 0, "feedback": "",
                         "handoff_hash": None, "answers": [], "outputs": [], "decision_id": None, "seq": i})
            self._save_task(task)
            order.append(task["id"])
            self.event("task.created", "task", task["id"], {"kind": task["kind"], "risk_tier": task["risk_tier"],
                       "owner_worker_id": task["owner_worker_id"], "dependencies": task["dependencies"],
                       "milestone": task["milestone_id"]}, actor=planner_id, actor_type="worker", correlation_id=task["id"])
        self.store.put("plan", "plan_1", {"id": "plan_1", "workstreams": plan["workstreams"], "order": order,
                                          "milestones": plan["milestones"], "critical_path": plan["critical_path"],
                                          "escalation_conditions": plan["escalation_conditions"],
                                          "reporting": plan["reporting"], "coordination": plan["coordination"],
                                          "uncovered_requirements": plan["uncovered_requirements"]})
        if self.staffed_by_registry():
            self._staff(refine=True)
        f = self._forecast()
        units = sum(int(self.task(t).get("budget") or 0) for t in order)
        L = f["layers"]
        cost = (f"${f['subtotal_usd']:.4f} forecast of the ${f['cap_usd']:.2f} cap, reserve ${f['reserve_usd']:.4f}"
                if f["priced"] else f"about {units} work units of {self.budget()['cap']}; no model cost (scripted demo)")
        ev = ["Milestones: " + "; ".join(f"{m['name']} (day {m['due_day']})" for m in plan["milestones"]),
              f"Critical path: {' > '.join(plan['critical_path'])}"]
        ev += [f"{t}: {self.task(t)['title']}, {self.task(t)['owner_worker_id']}" for t in order]
        ev += [f"{k}: ${v['usd']:.4f} ({v['basis']})" for k, v in L.items()]
        ev += f["warnings"]
        if plan["uncovered_requirements"]:
            ev.append("Requirements no task names: " + ", ".join(plan["uncovered_requirements"]))
        self._decision("approve_roadmap",
                       problem=f"The roadmap for the approved organization: {len(plan['milestones'])} milestones, "
                               f"{len(order)} tasks, and the budget built on it.",
                       recommendation="Approve the roadmap and the budget. Work starts; MEDIUM and HIGH steps still "
                                      "come back to you.",
                       risk="LOW" if f["fits"] else "MEDIUM", confidence="high" if f["fits"] else "medium", cost=cost,
                       evidence=ev, change="A task that does not serve the objective, a missing one, or a budget line "
                                           "that looks wrong.", source="execution_planner")
        self._set_meta(phase="planning")

    def _forecast(self) -> dict:
        """Stage 7: the Budget Engine's forecast for the current roadmap, kept for reconciliation."""
        reg = self.wf.reg if self.staffed_by_registry() else None
        f = budget_engine.construct(self.store, self.tasks(), self.workers(), reg, self.assigner_id())
        f["at"] = now()
        self.store.put("forecast", "current", f)
        self.event("budget.constructed", "company", self.cid, {"subtotal_usd": f["subtotal_usd"], "cap_usd": f["cap_usd"],
                   "reserve_usd": f["reserve_usd"], "fits": f["fits"], "units": f["units_total"]}, actor="budget_engine")
        return f

    def _after_approve_roadmap(self, d: dict, action: str) -> None:
        if action == "approve":
            org = self.store.get("organization", "org_1")
            org.update({"status": "active", "approved_by": "founder", "approved_at": now()})
            self.store.put("organization", "org_1", org)
            company = self.store.get("company", self.cid)
            company["stage"] = "MVP"
            self.store.put("company", self.cid, company)
            self.event("state.changed", "company", self.cid, {"stage": "MVP", "phase": "running"}, actor="founder",
                       actor_type="human", authority="founder")
            self._set_meta(phase="running", started_at=time.time(), notice="")
            if self.staffed_by_registry():
                self.wf.allocate(self.store, self.tasks(), {w["id"]: w["model_id"] for w in self.workers()})
        else:
            self._plan(note=d.get("note") or "The founder asked for a different roadmap.")

    # --- the run --------------------------------------------------------------
    def step(self) -> dict:
        with self.lock:
            m = self.meta
            if m["frozen"]:
                return {"did": "idle", "why": "kill switch is on"}
            if m["phase"] != "running":
                return {"did": "idle", "why": f"phase {m['phase']}"}
            if self.budget()["state"] == "breaker":
                return {"did": "idle", "why": "budget breaker open"}
            tasks = self.tasks()
            by_id = {t["id"]: t for t in tasks}
            for t in tasks:
                s = t["status"]
                deps_ok = all(by_id[d]["status"] == "VERIFIED" for d in t.get("dependencies", []))
                try:
                    if s == "PLANNED" and deps_ok:
                        return self._assign(t)
                    if s in ("ASSIGNED", "REWORK"):
                        return self._work(t)
                    if s == "BLOCKED":
                        return self._answer(t)
                    if s == "REVIEW":
                        return self._verify(t)
                    if s == "APPROVED":
                        return self._execute_approved(t)
                except ProtocolError as exc:
                    t = self.task(t["id"])
                    t["attempts"] += 1
                    self._save_task(t)
                    culprit = self.assigner_id() if s == "PLANNED" else (t.get("blocker") or {}).get("needs_from") \
                        if s == "BLOCKED" else t["owner_worker_id"]
                    n = self._count("violation") + 1
                    self.store.put("violation", f"pv_{n:04d}", {"id": f"pv_{n:04d}", "worker_id": culprit,
                                   "model_id": self.model_of(culprit) if culprit else None, "task_id": t["id"],
                                   "error": str(exc)[:300], "at": now()})
                    self.event("protocol.violation", "task", t["id"], {"worker": culprit, "error": str(exc)[:200]},
                               actor=culprit or "orchestrator", actor_type="worker", correlation_id=t["id"],
                               policy_decision="DENY")
                    if t["attempts"] >= MAX_ATTEMPTS:
                        return self._escalate(t, f"{t['id']}: the worker kept returning invalid protocol objects ({exc})")
                    if s in ("PLANNED", "BLOCKED"):
                        # assignment or a Blocker answer failed: retry that same step, not the work
                        return {"did": "retry", "task": t["id"], "why": str(exc)}
                    t.update({"status": "REWORK", "feedback": f"Your reply was not a valid protocol object: {exc}"})
                    self._save_task(t)
                    return {"did": "rework", "task": t["id"], "why": str(exc)}
                except IntelligenceError as exc:
                    handled = self._model_failed(t, exc)
                    if handled:
                        return handled
                    self._set_meta(notice=f"Stopped on {t['id']}: the intelligence source failed ({exc}). Nothing was invented.")
                    self._set_meta(phase="stopped_error")
                    self.event("task.failed", "task", t["id"], {"reason": "intelligence_error"}, correlation_id=t["id"])
                    return {"did": "error", "task": t["id"], "why": str(exc)}
            if tasks and all(t["status"] == "VERIFIED" for t in tasks):
                return self._deliver()
            return {"did": "idle", "why": "waiting on the founder"}

    def run_until_idle(self, max_steps: int = 200) -> list[dict]:
        out = []
        for _ in range(max_steps):
            r = self.step()
            out.append(r)
            if r["did"] in ("idle", "error"):
                break
        return out

    def _record_call(self, task_id: str, worker: str, purpose: str, usage: dict) -> None:
        n = self._count("call") + 1
        if usage.get("model_id") and self.staffed_by_registry():
            kind = (self.task(task_id) or {}).get("kind", purpose) if task_id.startswith("t_") else purpose
            c = self.wf.reg.record_call(usage["model_id"], role=(self.worker(worker) or {}).get("role", worker),
                                        purpose=purpose, task_kind=kind, usage=usage, run_id=self.cid)
            usage = dict(usage, usd=c["usd"])
            L = self.wf.charge(self.store, worker, task_id, c["usd"])
            cap_usd = float(self.wf.settings(self.store)["budget_usd"])
            if L["spent_total"] >= cap_usd and self.budget()["state"] != "breaker":
                self._breaker(f"${L['spent_total']:.4f} of ${cap_usd:.2f}", unit="USD", task_id=task_id)
            if task_id.startswith("t_") and purpose == "work":
                m = self._meter(task_id)
                self.store.put("meter", task_id, {"usd": m["usd"] + c["usd"], "seconds": m["seconds"] + c["seconds"],
                                                  "tokens": m["tokens"] + c["tokens_in"] + c["tokens_out"]})
        self.store.put("call", f"call_{n:04d}", {"id": f"call_{n:04d}", "task_id": task_id, "worker": worker,
                       "purpose": purpose, **usage, "at": now()})
        self.charge(int(usage.get("units", 1)), "intelligence", task_id if task_id.startswith("t_") else None)

    def _artifact_index(self) -> list[str]:
        return [a["id"] for a in self.store.all("artifact")]

    def _assign(self, t: dict) -> dict:
        owner = t["owner_worker_id"]
        boss = self.assigner_id()
        if owner == boss or roles.role(self.worker(owner)["role"])["assigns"]:
            assigner = "orchestrator"
            arts = [a["id"] for a in self.store.all("artifact") if a["task_id"] in t.get("dependencies", [])]
            crit = "; ".join(t.get("acceptance_criteria") or [])
            content = {"artifacts": arts, "context_ref": t["context"],
                       "acceptance_check": f"{t['title']}. Expected: {t['expected_output']}. "
                                           + (f"Acceptance criteria: {crit}. " if crit else "")
                                           + f"Verified by: {t.get('verification_gate') or t['verification_method']}."}
        else:
            assigner = boss
            g = self.gateway(boss, t["id"], "assign_task", target=t["id"])
            if g["status"] != "executed":
                return {"did": "blocked_by_policy", "task": t["id"]}
            content, usage = self.intel.assign(t, objective=self.objective_ctx(), rules=self.rules(),
                                               artifact_index=self._artifact_index(), worker=boss,
                                               persona=self.persona(boss))
            self._record_call(t["id"], boss, "assign", usage)
            if self.meta["frozen"]:
                return self._frozen_during_call(t)
            known = set(self._artifact_index())
            content["artifacts"] = [a for a in (content.get("artifacts") or []) if a in known]
        handoff = self.send("Handoff", content, {"from_worker": assigner, "to_worker": owner, "task_id": t["id"]},
                            t["id"], assigner)
        inbox = self._ws(owner, t["id"]) / "inbox"
        for aid in handoff["artifacts"]:
            a = self.store.get("artifact", aid)
            (inbox / Path(a["path"]).name).write_text((self.paths["integration"] / a["path"]).read_text(encoding="utf-8"),
                                                     encoding="utf-8")
        t.update({"status": "ASSIGNED", "handoff_hash": handoff["object_hash"], "handoff": handoff})
        self._save_task(t)
        self.event("worker.assigned", "worker", owner, {"task_id": t["id"], "handoff": handoff["object_hash"]},
                   correlation_id=t["id"], actor=assigner, actor_type="worker" if assigner.startswith("w_") else "service")
        return {"did": "assigned", "task": t["id"], "to": owner}

    def _inbox(self, t: dict) -> dict[str, str]:
        inbox = self._ws(t["owner_worker_id"], t["id"]) / "inbox"
        return {p.name: p.read_text(encoding="utf-8") for p in sorted(inbox.iterdir()) if p.is_file()}

    def _work(self, t: dict) -> dict:
        owner = t["owner_worker_id"]
        if t["work_calls"] == 0:
            self.event("task.started", "task", t["id"], {"owner": owner}, actor=owner, actor_type="worker",
                       correlation_id=t["id"])
        out = self._ws(owner, t["id"]) / "out"
        previous = {p.relative_to(out).as_posix(): p.read_text(encoding="utf-8", errors="replace")
                    for p in sorted(out.rglob("*")) if p.is_file()}
        repo = sorted(p.relative_to(self.paths["integration"]).as_posix()
                      for p in self.paths["integration"].rglob("*") if p.is_file() and "__pycache__" not in p.parts)
        who = [w for w in self.answerers() if w != owner] or [self.assigner_id()]
        result, usage = self.intel.work(t, worker=owner, objective=self.objective_ctx(), rules=self.rules(),
                                        handoff=t.get("handoff") or {}, inbox=self._inbox(t), feedback=t.get("feedback", ""),
                                        answers=t.get("answers", []), call_index=t["work_calls"], previous=previous,
                                        repo_files=repo, persona=self.persona(owner), answerers=who)
        t["work_calls"] += 1
        self._save_task(t)
        self._record_call(t["id"], owner, "work", usage)
        if self.meta["frozen"]:
            return self._frozen_during_call(t)
        kind = t["kind"]
        if result.get("result") == "blocked":
            needs = result.get("needs_from") if result.get("needs_from") in who else who[0]
            blocker = self.send("Blocker", {"category": result.get("category", "missing_input"),
                                            "description": result.get("description", ""), "needs_from": needs},
                                {"raised_by": owner, "task_id": t["id"]}, t["id"], owner)
            t.update({"status": "BLOCKED", "blocker": blocker, "blockers": t["blockers"] + 1})
            self._save_task(t)
            self._perf(owner, "blockers")
            self.event("task.blocked", "task", t["id"], {"needs_from": needs}, actor=owner, actor_type="worker",
                       correlation_id=t["id"], protocol_hash=blocker["object_hash"])
            return {"did": "blocked", "task": t["id"]}
        if kind in ("spec", "code"):
            files = result.get("files")
            cut = result.get("cut_off")
            if not isinstance(files, dict) or (not files and not cut):
                raise ProtocolError("a done result needs files: an object of file name to full file content")
            bad = [k for k, v in files.items() if not isinstance(v, str)]
            if bad:
                raise ProtocolError(f"file content must be text: {', '.join(map(str, bad))}")
            # A reply carries the files it writes or changes; the worker's other files stay as they were, so a
            # rework rewrites one file instead of all of them.
            for name in result.get("delete") or []:
                target = (out / str(name)).resolve()
                if out.resolve() in target.parents and target.is_file():
                    target.unlink()
            written = []
            for name, text in files.items():
                g = self.gateway(owner, t["id"], "write_file", target=str(name), content=text)
                if g["status"] != "executed":
                    if self.budget()["state"] == "breaker":
                        return {"did": "paused", "task": t["id"], "why": "budget breaker open"}
                    t["attempts"] += 1
                    t.update({"status": "REWORK", "feedback": f"write refused: {g['policy']['reason']}"})
                    self._save_task(t)
                    if t["attempts"] >= MAX_ATTEMPTS:
                        return self._escalate(t, f"{t['id']}: writes kept being refused ({g['policy']['reason']})")
                    return {"did": "write_refused", "task": t["id"]}
                written.append(g["result"])
            if cut:
                return self._cut_off(t, cut, sorted(files))
            t["cut_offs"] = 0
            written = [{"file": p.relative_to(out).as_posix(), "hash": digest(p.read_bytes()), "bytes": p.stat().st_size}
                       for p in sorted(out.rglob("*")) if p.is_file()]  # the whole result: kept files and new ones
            if kind == "code" and t.get("self_checks_used", 0) < self._self_checks():
                check = self._self_check(t, out)
                if not check["passed"]:
                    return check["step"]
            t["self_checks_used"] = 0
            done = self.send("Handoff", {"artifacts": [w["file"] for w in written], "context_ref": f"result of {t['id']}",
                                         "acceptance_check": result.get("acceptance_check") or result.get("summary") or "done"},
                             {"from_worker": owner, "to_worker": "verification", "task_id": t["id"]}, t["id"], owner)
            t.update({"status": "REVIEW", "outputs": written, "summary": result.get("summary", ""),
                      "completed_hash": done["object_hash"]})
            self._save_task(t)
            self.event("task.completed", "task", t["id"], {"files": [w["file"] for w in written],
                       "note": "completed by the worker, not yet verified"}, actor=owner, actor_type="worker",
                       correlation_id=t["id"], protocol_hash=done["object_hash"])
            return {"did": "completed", "task": t["id"]}
        # proposals: decision, review_merge, deploy
        return self._propose(t, result)

    def _cut_off(self, t: dict, cut: str, saved: list[str]) -> dict:
        """The reply stopped at the model's output limit. The files it finished are saved; the worker is asked for
        the rest. Replies that keep overflowing are escalated rather than retried without end."""
        t["cut_offs"] = t.get("cut_offs", 0) + 1
        if t["cut_offs"] > MAX_CUT_OFFS:
            self._outcome(t, False, "replies kept running past the model's output limit")
            return self._replace_or_escalate(t, f"{t['id']}: {MAX_CUT_OFFS + 1} replies in a row were longer than the "
                                                "model's output limit.")
        t.update({"status": "REWORK", "feedback": (
            f"Your last reply was longer than the model's output limit and was cut off while writing {cut}, which was "
            "not saved. " + (f"These files were saved: {', '.join(saved)}. " if saved else "No file was finished. ")
            + "Send only the files still missing or unfinished, each one complete and short.")})
        self._save_task(t)
        self.event("task.reply_cut_off", "task", t["id"], {"file": cut, "saved": saved, "round": t["cut_offs"]},
                   actor=t["owner_worker_id"], actor_type="worker", correlation_id=t["id"])
        return {"did": "cut_off", "task": t["id"], "saved": saved}

    def _self_checks(self) -> int:
        """How many times an engineer may test and fix its own work before handing it over.

        A real model works like an engineer: it runs its own tests, reads the failures and fixes
        them. Verification is still independent and reruns everything afterwards. The scripted
        demo keeps its story (verification catches the defect), so it defaults to none.
        """
        default = "2" if getattr(self.intel, "kind", "") == "model" else "0"
        try:
            return max(0, int(os.environ.get("CYNQRA_SELF_CHECKS", default)))
        except ValueError:
            return int(default)

    def _candidate(self, t: dict, dest: Path) -> Path:
        """The repository as it would be with this task's files merged in."""
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(self.paths["integration"], dest)
        out = self._ws(t["owner_worker_id"], t["id"]) / "out"
        for p in out.rglob("*"):
            if p.is_file():
                target = dest / self._repo_path(p.relative_to(out))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, target)
        return dest

    def _self_check(self, t: dict, out: Path) -> dict:
        owner = t["owner_worker_id"]
        folder = self._candidate(t, self._ws(owner, t["id"]) / "check")
        g = self.gateway(owner, t["id"], "run_tests", target="own workspace", cwd=folder)
        res = g.get("result") or {}
        passed = g["status"] == "executed" and bool(res.get("passed"))
        why = ""
        syntax = []
        for p in sorted(out.rglob("*.py")):
            try:
                compile(p.read_text(encoding="utf-8", errors="replace"), p.name, "exec")
            except SyntaxError as exc:
                syntax.append(f"{p.relative_to(out).as_posix()} line {exc.lineno}: {exc.msg}")
        if syntax:
            passed, why = False, "Python syntax errors: " + "; ".join(syntax)
        elif g["status"] != "executed":
            why = "the test run was refused: " + g["policy"]["reason"]
        elif not passed:
            report = g["report"]  # the run just made; running every test again only to read its failures cost minutes
            why = failure_summary(report) + "\n" + report["output"][-1500:]
        elif (out / "app.py").exists():
            contract = deploy.contract_check(folder, self._smoke_checks(folder))
            if not contract["ok"]:
                passed, why = False, "the app breaks the delivery contract: " + contract["why"]
        t["self_checks_used"] = t.get("self_checks_used", 0) + (0 if passed else 1)
        self.event("worker.self_checked", "task", t["id"], {"task_id": t["id"], "passed": passed,
                   "round": t.get("self_checks_used", 0), "tests_ran": res.get("ran", 0)},
                   actor=owner, actor_type="worker", correlation_id=t["id"], test_ids=res.get("test_ids"))
        shutil.rmtree(folder, ignore_errors=True)
        if passed:
            return {"passed": True}
        t.update({"feedback": f"Your own check before handing over failed. {why}"})
        self._save_task(t)
        return {"passed": False, "step": {"did": "self_check_failed", "task": t["id"], "round": t["self_checks_used"]}}

    def _propose(self, t: dict, result: dict) -> dict:
        owner = t["owner_worker_id"]
        kind = t["kind"]
        missing = [k for k in ("recommendation", "confidence", "what_would_change_this") if not str(result.get(k) or "").strip()]
        if missing:
            raise ProtocolError(f"proposal is missing {', '.join(missing)}")
        evidence = list(result.get("evidence_refs") or [])
        extra: dict = {}
        if kind == "decision":
            action_type = "product_rule_decision"
        elif kind == "review_merge":
            action_type = "merge_to_main"
            g = self.gateway(owner, t["id"], "run_tests", target="integration", cwd=self.paths["integration"])
            report = g.get("result", {})
            extra["tests"] = report
            evidence.append(f"{report.get('ran', 0)} tests on the release candidate, "
                            f"{'all passed' if report.get('passed') else 'failures: ' + ', '.join(report.get('failed', []))}")
            if not report.get("passed"):
                self._escaped(report.get("failed", []), "release candidate", t["id"])
                return self._escalate(t, "The release candidate fails its tests, so there is nothing safe to merge.")
        else:
            action_type = "deploy_production"
            smoke_checks = self._smoke_checks(self.paths["main"])
            rid = f"release_{self._count('deployment') + 1}"
            pre = deploy.build_to_verify(self.paths["main"], self.paths["releases"], rid, smoke_checks)
            dep = {"id": rid, "company_id": self.cid, "task_id": t["id"], "status": "awaiting_approval" if pre["ok"] else "failed",
                   "log": pre["log"], "folder": pre["folder"], "url": None, "test_ids": pre.get("test_ids", []),
                   "created_at": now()}
            self.store.put("deployment", rid, dep)
            self.event("deployment.created", "deployment", rid, {"stages": [x["stage"] for x in pre["log"]], "ok": pre["ok"]},
                       correlation_id=t["id"], actor="deployment", test_ids=pre.get("test_ids"))
            if not pre["ok"]:
                self.event("deployment.failed", "deployment", rid, {"stage": pre["log"][-1]["stage"]}, correlation_id=t["id"],
                           actor="deployment")
                return self._escalate(t, "The release failed before approval: " + pre["log"][-1]["stage"])
            extra["deployment_id"] = rid
            evidence.append(f"{len(pre.get('test_ids', []))} tests passed in the build, preview health and smoke passed")
            side = result.get("side_action")
            if isinstance(side, dict) and side:
                g = self.gateway(owner, t["id"], side.get("action_type", ""), target=side.get("target", ""))
                extra["side_action"] = {"summary": side.get("summary", ""), "status": g["status"],
                                        "reason": g["policy"]["reason"]}
        g = self.gateway(owner, t["id"], action_type, target=t["id"])
        if g["status"] == "denied":
            return self._escalate(t, g["policy"]["reason"])
        d = self._decision(t["kind"], problem=result.get("problem", t["title"]),
                           recommendation=result.get("recommendation", ""), risk=t["risk_tier"],
                           confidence=result.get("confidence", "medium"), cost=result.get("cost", ""),
                           evidence=evidence, change=result.get("what_would_change_this", ""), task_id=t["id"],
                           action_type=action_type, source=owner, extra=extra)
        approval = self.send("Approval", {"recommendation": d["recommendation"], "evidence_refs": evidence,
                                          "cost": d["cost"], "confidence": d["confidence"],
                                          "what_would_change_this": d["what_would_change_this"]},
                             {"decision_id": d["id"], "from_worker": owner, "task_id": t["id"], "risk": t["risk_tier"]},
                             t["id"], owner)
        t.update({"status": "AWAITING_FOUNDER", "decision_id": d["id"], "approval_hash": approval["object_hash"]})
        self._save_task(t)
        return {"did": "proposed", "task": t["id"], "decision": d["id"]}

    def _frozen_during_call(self, t: dict) -> dict:
        """The kill switch went on while the model was answering: the answer is dropped, the task stays where it was."""
        self.event("action.denied", "task", t["id"], {"task_id": t["id"], "reason": "kill switch on when the model answered; "
                   "the answer was discarded"}, actor="policy", correlation_id=t["id"], policy_decision="DENY")
        return {"did": "paused", "task": t["id"], "why": "kill switch"}

    def _escalate(self, t: dict, why: str) -> dict:
        owner = t["owner_worker_id"]
        esc = self.send("Escalation", {"issue": why, "required_action": "Founder decides: retry the task or stop the run.",
                                       "severity": "SEV-2"},
                        {"raised_by": owner, "owner": "founder"}, t["id"], owner)
        d = self._decision("escalation", problem=why, recommendation="Retry the task once more with the failure as feedback.",
                           risk=t["risk_tier"], confidence="low", cost="one more attempt",
                           evidence=[f"escalation {esc['object_hash']}"], change="A fix that makes the checks pass.",
                           task_id=t["id"], source=owner, severity="SEV-2")
        t.update({"status": "FAILED", "failed_from": t["status"], "decision_id": d["id"]})
        self._save_task(t)
        self.event("task.failed", "task", t["id"], {"reason": why[:200]}, correlation_id=t["id"], actor=owner,
                   actor_type="worker", protocol_hash=esc["object_hash"])
        return {"did": "escalated", "task": t["id"], "decision": d["id"]}

    def _answer(self, t: dict) -> dict:
        blocker = t["blocker"]
        who = blocker.get("needs_from") or self.assigner_id()
        g = self.gateway(who, t["id"], "answer_blocker", target=t["id"])
        if g["status"] != "executed":
            return self._escalate(t, g["policy"]["reason"])
        content, usage = self.intel.answer_blocker(t, worker=who, objective=self.objective_ctx(), rules=self.rules(),
                                                   blocker=blocker, artifact_index=self._artifact_index(),
                                                   persona=self.persona(who))
        self._record_call(t["id"], who, "answer_blocker", usage)
        if self.meta["frozen"]:
            return self._frozen_during_call(t)
        known = set(self._artifact_index())
        content["artifacts"] = [a for a in (content.get("artifacts") or []) if a in known]
        answer = self.send("Handoff", content, {"from_worker": who, "to_worker": t["owner_worker_id"], "task_id": t["id"]},
                           t["id"], who)
        inbox = self._ws(t["owner_worker_id"], t["id"]) / "inbox"
        for aid in answer["artifacts"]:
            a = self.store.get("artifact", aid)
            (inbox / Path(a["path"]).name).write_text((self.paths["integration"] / a["path"]).read_text(encoding="utf-8"),
                                                     encoding="utf-8")
        t["answers"] = t.get("answers", []) + [{"from": who, "acceptance_check": answer["acceptance_check"],
                                                  "hash": answer["object_hash"]}]
        t["status"] = "ASSIGNED"
        self._save_task(t)
        n = self._count("blocker_cleared") + 1
        self.store.put("blocker_cleared", f"bc_{n}", {"task_id": t["id"], "by": who, "founder_involved": False})
        return {"did": "blocker_cleared", "task": t["id"], "by": who}

    def _verify(self, t: dict) -> dict:
        owner = t["owner_worker_id"]
        t0 = time.time()
        vdir = self._candidate(t, self.dir / "verify" / f"{t['id']}_{t['attempts'] + 1}")
        out = self._ws(owner, t["id"]) / "out"
        n = self._count("verification") + 1
        vid = f"v_{n:03d}"
        if t["kind"] == "code":
            report = run_unittests(vdir)
            passed = report["passed"]
            test_ids = [x["id"] for x in report["tests"]]
            checks = {"ran": report["ran"], "failed": report["failed"], "prior_tests_rerun": True}
            if not passed:
                feedback = failure_summary(report) + "\n" + report["output"][-1500:]
            else:
                feedback = ""
            method = "automated tests, prior tests rerun"
            if passed and (out / "app.py").exists():
                contract = deploy.contract_check(vdir, self._smoke_checks(vdir))
                checks["delivery_contract"] = contract["results"]
                if not contract["ok"]:
                    passed = False
                    feedback = "The app breaks the delivery contract: " + contract["why"]
                method += ", delivery contract"
        else:
            docs = {p.name: p.read_text(encoding="utf-8", errors="replace") for p in out.rglob("*") if p.is_file()}
            lint = lint_documents(docs, self.objective()["structured"])
            passed = lint["passed"]
            test_ids = []
            checks = {"lint": lint["findings"], "acceptance_criteria": t.get("acceptance_criteria") or []}
            feedback = "; ".join(f["why"] for f in lint["findings"])
            method = "coverage lint against the objective"
        verdict = "VERIFIED" if passed else ("REQUIRES_REWORK" if t["attempts"] + 1 < MAX_ATTEMPTS else "REQUIRES_HUMAN")
        self._outcome(t, passed, "" if passed else feedback)
        self.charge(UNIT_COST["verify"], "verify", t["id"])
        work = digest({p.relative_to(out).as_posix(): digest(p.read_bytes()) for p in sorted(out.rglob("*")) if p.is_file()})
        v = {"id": vid, "company_id": self.cid, "task_id": t["id"], "attempt": t["attempts"] + 1,
             "risk_tier": t["risk_tier"], "method": method, "checks": checks, "reviewer_type": "service",
             "reviewer_id": "verification", "verdict": verdict, "test_ids": test_ids,
             "output_hash": digest(json.dumps(checks)), "work_hash": work, "worker_id": owner,
             "model_id": self.model_of(owner), "seconds": round(time.time() - t0, 2), "created_at": now()}
        self.store.put("verification", vid, v)
        if passed:  # the same work failed before and passes now: that earlier verdict was a false rejection
            for old in self.store.all("verification"):
                if old["task_id"] == t["id"] and old["id"] != vid and old.get("work_hash") == work \
                        and old["verdict"] != "VERIFIED" and not old.get("false_rejection"):
                    old["false_rejection"] = True
                    self.store.put("verification", old["id"], old)
                    self.event("verification.false_rejection", "verification", old["id"], {"task_id": t["id"],
                               "confirmed_by": vid}, actor="verification", correlation_id=t["id"])
        self.event("verification.completed", "verification", vid, {"task_id": t["id"], "verdict": verdict,
                   "method": method, "attempt": v["attempt"]}, actor="verification", correlation_id=t["id"],
                   test_ids=test_ids)
        if passed:
            self._integrate(t, out)
            first_pass = t["attempts"] == 0
            t["status"] = "VERIFIED"
            self._save_task(t)
            self._perf(owner, "verified")
            if first_pass:
                self._perf(owner, "first_pass")
            self.event("task.verified", "task", t["id"], {"verification": vid, "attempt": v["attempt"]},
                       actor="verification", correlation_id=t["id"], test_ids=test_ids)
            return {"did": "verified", "task": t["id"]}
        t["attempts"] += 1
        self._perf(owner, "reworks")
        if verdict == "REQUIRES_HUMAN":
            self._save_task(t)
            return self._replace_or_escalate(t, f"{t['id']} failed verification {t['attempts']} times: {feedback[:200]}")
        t.update({"status": "REWORK", "feedback": feedback})
        self._save_task(t)
        self.event("task.failed", "task", t["id"], {"attempt": t["attempts"], "rework": True, "verification": vid},
                   actor="verification", correlation_id=t["id"], test_ids=test_ids)
        moved = replacement.check_thresholds(self, t)  # Stage 10: evidence, not only the third failure, can move it
        if moved and moved["did"] in ("replaced", "rerouted"):
            return moved
        return {"did": "rework", "task": t["id"]}

    def _escaped(self, failed_ids: list[str], where: str, source_task: str) -> None:
        """Stage 9: a defect found after verification (in the release candidate, on main or live) escaped it. It is
        counted against the verified task that owns the failing tests, and the model that did that task."""
        mods = {i.split(".")[0] for i in failed_ids or []}
        hit = []
        for x in self.tasks():
            files = {Path(o.get("file", "")).stem for o in x.get("outputs") or [] if isinstance(o, dict)}
            if x["status"] == "VERIFIED" and x["kind"] == "code" and (files & mods or (not mods and "app" in files)):
                hit.append(x)
        for x in hit:
            v = [y for y in self.store.all("verification") if y["task_id"] == x["id"] and y["verdict"] == "VERIFIED"]
            n = self._count("escape") + 1
            rec = {"id": f"esc_{n:03d}", "task_id": x["id"], "worker_id": x["owner_worker_id"],
                   "model_id": v[-1].get("model_id") if v else None, "where": where, "found_by": source_task,
                   "tests": sorted(failed_ids or [])[:20], "at": now()}
            self.store.put("escape", rec["id"], rec)
            self.event("verification.defect_escaped", "task", x["id"], {"where": where, "found_by": source_task},
                       actor="verification", correlation_id=x["id"])

    def _integrate(self, t: dict, out: Path) -> None:
        dest_root = self.paths["integration"]
        for p in sorted(out.rglob("*")):
            if not p.is_file():
                continue
            rel = self._repo_path(p.relative_to(out))
            (dest_root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest_root / rel)
            aid = f"{t['id']}/{p.relative_to(out).as_posix()}"
            self.store.put("artifact", aid, {"id": aid, "task_id": t["id"], "path": str(rel).replace("\\", "/"),
                                             "hash": digest(p.read_bytes()), "by": t["owner_worker_id"]})
        self.event("action.executed", "action", f"integrate_{t['id']}", {"task_id": t["id"], "action_type": "integrate",
                   "files": sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())}, actor="verification",
                   correlation_id=t["id"])

    @staticmethod
    def _repo_path(rel: Path) -> Path:
        """Markdown is filed under docs/, everything else keeps its path from the repository root."""
        if rel.suffix == ".md" and rel.parts[0] != "docs":
            return Path("docs") / rel
        return rel

    def _smoke_checks(self, folder: Path) -> list[dict]:
        f = folder / "smoke.json"
        if f.exists():
            try:
                checks = json.loads(f.read_text(encoding="utf-8")).get("checks", [])
            except (ValueError, AttributeError):
                return []
            return [c for c in checks if isinstance(c, dict) and isinstance(c.get("path"), str)
                    and c["path"].startswith("/")] if isinstance(checks, list) else []
        return [{"method": "GET", "path": "/health", "expect": 200}]

    # --- after founder decisions on proposals -----------------------------------
    def _after_task_proposal(self, d: dict, action: str) -> None:
        t = self.task(d["task_id"])
        if action == "approve":
            t["status"] = "APPROVED"
        else:
            t["attempts"] += 1
            t.update({"status": "REWORK", "feedback": f"Founder: {d['outcome_label']}. {d.get('note', '')}".strip()})
        self._save_task(t)

    _after_decision = _after_task_proposal
    _after_review_merge = _after_task_proposal
    _after_deploy = _after_task_proposal

    def _after_escalation(self, d: dict, action: str) -> None:
        t = self.task(d["task_id"])
        if action == "approve":
            back = t.get("failed_from")
            if back not in ("PLANNED", "BLOCKED"):
                back = "REWORK" if t["kind"] in ("spec", "code") else "ASSIGNED"
            t.update({"status": back, "attempts": 0, "cut_offs": 0})
            self._save_task(t)
        else:
            self._set_meta(phase="stopped", notice=f"Run stopped by the founder at {t['id']}.")

    def _after_budget_breaker(self, d: dict, action: str) -> None:
        if action == "approve" and (d.get("extra") or {}).get("unit") == "USD":
            s = Workforce.settings(self.store)
            spent = Workforce.ledger(self.store)["spent_total"]
            s["budget_usd"] = round(float(d.get("edited", {}).get("budget_usd") or max(s["budget_usd"], spent) * 1.5), 4)
            self.store.put("workforce", "settings", s)
            b = self.budget()
            b["state"] = "ok"
            self.store.put("budget", "company", b)
            self.event("budget.changed", "company", self.cid, {"budget_usd": s["budget_usd"], "unit": "USD"},
                       actor="founder", actor_type="human", authority="founder")
        elif action == "approve":
            b = self.budget()
            new_cap = int(d.get("edited", {}).get("cap") or b["cap"] + 60)
            b.update({"cap": new_cap, "state": "ok"})
            b["warned"] = [m for m in b["warned"] if 100 * b["spent"] / new_cap >= m]
            self.store.put("budget", "company", b)
            self.event("budget.changed", "company", self.cid, {"cap": new_cap, "unit": "work_units"}, actor="founder",
                       actor_type="human", authority="founder")
        else:
            self._set_meta(phase="stopped", notice="Run stopped at the budget cap by the founder.")

    def _execute_approved(self, t: dict) -> dict:
        d = self.store.get("decision", t["decision_id"])
        owner = t["owner_worker_id"]
        n = self._count("verification") + 1
        vid = f"v_{n:03d}"
        test_ids: list = []
        if t["kind"] == "decision":
            rule = d.get("edited", {}).get("recommendation") or d["recommendation"]
            mem = self.store.get("memory", "decided_rules") or {"rules": []}
            mem["rules"].append(rule)
            self.store.put("memory", "decided_rules", mem)
            doc = self.paths["integration"] / "docs" / "DECISIONS.md"
            doc.parent.mkdir(parents=True, exist_ok=True)
            with doc.open("a", encoding="utf-8") as fh:
                fh.write(f"## {t['title']} ({d['id']}, {d['outcome_label']} by the founder)\n\n{rule}\n\n")
            aid = f"{t['id']}/DECISIONS.md"
            self.store.put("artifact", aid, {"id": aid, "task_id": t["id"], "path": "docs/DECISIONS.md",
                                             "hash": digest(doc.read_bytes()), "by": owner})
            verdict, method, checks = "VERIFIED", "founder review (D-17)", {"decision": d["id"], "label": d["outcome_label"]}
        elif t["kind"] == "review_merge":
            g = self.gateway(owner, t["id"], "merge_to_main", target="main", approval=d["id"])
            if g["status"] != "executed":
                return self._escalate(t, "merge refused: " + g["policy"]["reason"])
            report = run_unittests(self.paths["main"])
            test_ids = [x["id"] for x in report["tests"]]
            if not report["passed"]:
                self._escaped(report.get("failed", []), "main after the merge", t["id"])
                return self._escalate(t, "main fails its tests after the merge")
            verdict, method, checks = "VERIFIED", "full test run on main", {"ran": report["ran"], "tree": g["result"]["tree"]}
        else:
            g = self.gateway(owner, t["id"], "deploy_production", target="production", approval=d["id"])
            if g["status"] != "executed":
                return self._escalate(t, "deploy refused: " + g["policy"]["reason"])
            dep = self.store.get("deployment", d["extra"]["deployment_id"])
            res = deploy.deploy_live(Path(dep["folder"]), self.paths["live"], self._smoke_checks(Path(dep["folder"])),
                                     self.live_proc)
            dep["log"] = dep["log"] + res["log"]
            dep["status"] = "live" if res["ok"] else "rolled_back"
            dep["url"] = res["url"]
            dep["approved_by"] = "founder"
            self.store.put("deployment", dep["id"], dep)
            self.live_proc = res["proc"]
            if not res["ok"]:
                self.event("deployment.failed", "deployment", dep["id"], {"stage": "SMOKE_TEST"}, correlation_id=t["id"],
                           actor="deployment")
                self.event("deployment.rolled_back", "deployment", dep["id"], {}, correlation_id=t["id"], actor="deployment")
                self._escaped([], "live health or smoke check", t["id"])
                return self._escalate(t, "the live release failed its health or smoke check and was rolled back")
            self.event("deployment.verified", "deployment", dep["id"], {"url_port": res["url"].rsplit(":", 1)[-1],
                       "stages": [x["stage"] for x in dep["log"]]}, correlation_id=t["id"], actor="deployment")
            test_ids = dep.get("test_ids", [])
            verdict, method, checks = "VERIFIED", "health check and smoke test on the live URL", {"url": res["url"]}
        v = {"id": vid, "company_id": self.cid, "task_id": t["id"], "attempt": t["attempts"] + 1, "risk_tier": t["risk_tier"],
             "method": method, "checks": checks, "reviewer_type": "human" if t["kind"] == "decision" else "service",
             "reviewer_id": "founder" if t["kind"] == "decision" else "verification", "verdict": verdict,
             "test_ids": test_ids, "output_hash": digest(json.dumps(checks)), "worker_id": owner,
             "model_id": self.model_of(owner), "seconds": None, "created_at": now()}
        self.store.put("verification", vid, v)
        self.event("verification.completed", "verification", vid, {"task_id": t["id"], "verdict": verdict, "method": method},
                   actor="verification", correlation_id=t["id"], test_ids=test_ids)
        self._outcome(t, True)
        t["status"] = "VERIFIED"
        self._save_task(t)
        self._perf(owner, "verified")
        if t["attempts"] == 0:
            self._perf(owner, "first_pass")
        self.event("task.verified", "task", t["id"], {"verification": vid}, actor="verification", correlation_id=t["id"],
                   test_ids=test_ids)
        return {"did": "verified", "task": t["id"]}

    def _perf(self, wid: str, key: str) -> None:
        w = self.worker(wid)
        if w:
            w["performance_profile"][key] = w["performance_profile"].get(key, 0) + 1
            self.store.put("worker", wid, w)

    # --- delivery --------------------------------------------------------------
    def _deliver(self) -> dict:
        export = self.export()
        m = self.metrics()
        tr = {"id": "tr_1", "company_id": self.cid, "problem": self.objective()["statement"],
              "evidence_refs": [v["id"] for v in self.store.all("verification")],
              "proposed_change": "Synthesize the organization the objective needs, staff it with intelligence and run "
                                 "the approved roadmap to a live release.",
              "expected_result": self.objective()["structured"]["success_criteria"],
              "cost": (f"${budget_engine.actual(self.store, self.store.get('forecast', 'current'))['total_actual']:.4f}, "
                       if self.staffed_by_registry() else "") + f"{self.budget()['spent']} work units",
              "risk": "HIGH (production deploy)",
              "reversibility": "Stop the live process; the export holds everything.",
              "authority_check": "every MEDIUM and HIGH step approved by the founder",
              "approval": None, "actual_result": f"Live at {self.live_url()}", "confidence": "high",
              "metrics": m, "export": Path(export).name}
        self.store.put("transition", "tr_1", tr)
        self.event("transition.proposed", "transition", "tr_1", {"tasks": len(self.tasks()), "cost_units": self.budget()["spent"]})
        self._decision("accept_delivery", problem="Every task is verified and the product is live.",
                       recommendation="Accept delivery. The export bundle is ready to download.", risk="LOW",
                       confidence="high", cost="none", evidence=[self.live_url() or "", Path(export).name],
                       change="Anything in the live product that does not meet the objective.", source="orchestrator")
        self._set_meta(phase="delivered", delivered_at=time.time())
        return {"did": "delivered"}

    def _after_accept_delivery(self, d: dict, action: str) -> None:
        tr = self.store.get("transition", "tr_1")
        if action == "approve":
            tr["approval"] = {"by": "founder", "at": now(), "decision": d["id"]}
            self.store.put("transition", "tr_1", tr)
            self.event("transition.approved", "transition", "tr_1", {}, actor="founder", actor_type="human", authority="founder")
            self.event("transition.executed", "transition", "tr_1", {})
            self.event("outcome.recorded", "outcome", "out_1", {"transition": "tr_1", "live": bool(self.live_url())})
            company = self.store.get("company", self.cid)
            company["stage"] = "PILOT"
            self.store.put("company", self.cid, company)
            self._set_meta(phase="accepted")
        else:
            self.event("transition.rejected", "transition", "tr_1", {"label": d["outcome_label"]}, actor="founder",
                       actor_type="human", authority="founder")
            self._set_meta(phase="delivered", notice="Delivery not accepted. The product stays live and your note is on "
                           "record. Iterating on a delivered product is outside this proof of concept.")

    def live_url(self) -> str | None:
        live = [d for d in self.store.all("deployment") if d["status"] == "live"]
        return live[-1]["url"] if live else None

    # --- founder controls ------------------------------------------------------
    def kill_switch(self, on: bool) -> dict:
        # Not behind self.lock: a step can hold it for a whole model call, and the kill switch
        # must work during one. The store serializes the writes; the step checks frozen when
        # its call returns and discards the result.
        self._set_meta(frozen=bool(on))
        self._intervention("kill_switch", "on" if on else "off")
        self.event("state.changed", "company", self.cid, {"frozen": bool(on), "control": "kill_switch"},
                   actor="founder", actor_type="human", authority="founder", policy_decision="DENY" if on else "ALLOW")
        return self.meta

    def resume(self) -> dict:
        """After a model or network error: try the same step again. Nothing was written by the failed call."""
        with self.lock:
            self._require("stopped_error")
            if self.meta.get("failed_stage") == "plan":
                self._set_meta(failed_stage=None, notice="")
                self._intervention("resume", "retry the roadmap after an intelligence error")
                self._plan()
                return self.meta
            self._set_meta(phase="running", notice="")
            self._intervention("resume", "retry after an intelligence error")
            self.event("state.changed", "company", self.cid, {"phase": "running", "control": "resume"},
                       actor="founder", actor_type="human", authority="founder")
            return self.meta

    def request_objective_change(self, fields: dict) -> dict:
        """D-30: a change during a run pauses it for an impact summary, then reconfirm or keep."""
        with self.lock:
            obj = self.objective()
            changes = {k: str(v).strip() for k, v in (fields or {}).items()
                       if k in OBJECTIVE_FIELDS and str(v).strip() and str(v).strip() != obj["structured"][k]}
            if not changes:
                return obj
            affected = [t["id"] for t in self.tasks() if t["status"] != "VERIFIED"]
            self._decision("objective_change", problem="You changed the objective during a run. The run is paused.",
                           recommendation="Reconfirm with the change. Verified work stays; open tasks continue against the new version.",
                           risk="HIGH", confidence="medium", cost="depends on the change",
                           evidence=[f"fields: {', '.join(changes)}", f"open tasks affected: {', '.join(affected) or 'none'}"],
                           change="Keep the old version if the change was a mistake.", source="orchestrator",
                           extra={"changes": changes, "previous_phase": self.meta["phase"]})
            self._set_meta(phase="paused_objective")
            return obj

    def _after_objective_change(self, d: dict, action: str) -> None:
        if action == "approve":
            obj = self.objective()
            obj["structured"].update(d["extra"]["changes"])
            obj["version"] += 1
            self.store.put("objective", "obj_1", obj)
            self.event("objective.changed", "objective", "obj_1", {"version": obj["version"], "status": "confirmed",
                       "fields_changed": sorted(d["extra"]["changes"])}, actor="founder", actor_type="human", authority="founder")
        self._set_meta(phase=d["extra"].get("previous_phase", "running"))

    # --- reading ------------------------------------------------------------------
    def metrics(self) -> dict:
        tasks = self.tasks()
        verified = [t for t in tasks if t["status"] == "VERIFIED"]
        protos = [p for p in self.store.all("protocol") if p["sender"].startswith("w_")]
        denied = [a for a in self.store.all("action") if a["status"] == "denied"]
        caught = [v for v in self.store.all("verification") if v["verdict"] in ("REQUIRES_REWORK", "REQUIRES_HUMAN", "REJECTED")]
        m = self.meta
        start, end = m.get("started_at"), m.get("delivered_at")
        return {
            "founder_interventions": self._count("intervention"),
            "tasks_total": len(tasks),
            "tasks_verified": len(verified),
            "defects_caught_before_verified": len(caught),
            "blockers_cleared_without_founder": len([b for b in self.store.all("blocker_cleared") if not b["founder_involved"]]),
            "actions_stopped_by_policy": len(denied),
            "fixed_by_workers_own_checks": len([e for e in self.store.events() if e["event_type"] == "worker.self_checked"
                                                 and not e["payload"].get("passed")]),
            "worker_protocol_objects": len(protos),
            "protocol_objects_per_verified_task": round(len(protos) / len(verified), 1) if verified else None,
            "escalations_today": len([d for d in self.store.all("decision") if d.get("source", "").startswith("w_")
                                      and d.get("created_day") == datetime.now(IST).date().isoformat()]),
            "escalation_budget": ESCALATIONS_PER_DAY,
            "seconds_to_live": round(end - start, 1) if start and end else None,
            "events": self.store.count_events(),
            # Stage 9: what verification itself achieved
            "first_pass_rate": round(sum(1 for t in verified if not t["attempts"]) / len(verified), 3) if verified else None,
            "reworks": len([v for v in self.store.all("verification") if v["verdict"] == "REQUIRES_REWORK"]),
            "defect_escapes": self._count("escape"),
            "false_rejections": len([v for v in self.store.all("verification") if v.get("false_rejection")]),
            "verification_seconds": round(sum(float(v.get("seconds") or 0) for v in self.store.all("verification")), 1),
            "protocol_violations": self._count("violation"),
            "intelligence_changes": self._count("replacement"),
        }

    def evolution(self) -> dict:
        workers = self.store.all("worker")
        perf = [{"id": w["id"], "title": w["title"], **w["performance_profile"]} for w in workers]
        worst = max(perf, key=lambda p: p.get("reworks", 0), default=None)
        if worst and worst.get("reworks", 0) >= 2:
            rec = {"title": f"Review {worst['title']}", "recommendation":
                   f"{worst['title']} needed {worst['reworks']} reworks. Consider a different intelligence source for its tasks.",
                   "change": "Its next two tasks verified first pass."}
        else:
            reworks = sum(p.get("reworks", 0) for p in perf)
            rec = {"title": "Keep the organization as it is", "recommendation":
                   f"No transition. {reworks} rework(s) across {len(self.tasks())} tasks, all caught before verified.",
                   "change": "Two reworks in a row on the same capability, or an escaped defect."}
        return {"workers": perf, **rec, "status": "recommendation only, view only in the MVP"}

    def replay(self, task_id: str) -> dict:
        t = self.task(task_id)
        events = self.store.events(correlation_id=task_id)
        actions = [a for a in self.store.all("action") if a["task_id"] == task_id]
        calls = [c for c in self.store.all("call") if c["task_id"] == task_id]
        verifs = [v for v in self.store.all("verification") if v["task_id"] == task_id]
        protos = [self.store.get_object(e["protocol_hash"]) for e in events if e.get("protocol_hash")]
        w = self.worker(t["owner_worker_id"])
        facts = {
            "actor": f"{w['id']}, role {w['role']}",
            "authority": w["authority_policy_id"],
            "policy_decisions": [f"{a['action_type']}: {a['policy_decision']}" for a in actions],
            "context": t.get("handoff_hash"),
            "intelligence": sorted({c["label"] for c in calls}),
            "tools": (sorted({a["action_type"] for a in actions if a["status"] in ("executed", "approved")})
                      or (["none: a founder decision, no tool runs"] if t["kind"] == "decision" else [])),
            "result": [o.get("file") or o for o in (t.get("outputs") or [])] or ([t["decision_id"]] if t.get("decision_id") else []),
            "verification": [f"{v['verdict']} by {v['method']}, {len(v['test_ids'])} test ids" for v in verifs],
        }
        missing = [k for k, v in facts.items() if not v]
        return {"task_id": task_id, "facts": facts, "missing": missing, "complete": not missing,
                "events": len(events), "protocols": [p for p in protos if p],
                "test_ids": sorted({i for v in verifs for i in v["test_ids"]})}

    def graph(self, question: str, subject: str) -> dict:
        if question == "approves":
            return policy.who_may(subject)
        t = self.task(subject)
        if question == "owns":
            return {"task": subject, "owner": t["owner_worker_id"],
                    "reports_to": (self.worker(t["owner_worker_id"]) or {}).get("reports_to", "founder")}
        if question == "depends":
            return {"task": subject, "depends_on": t.get("dependencies", []),
                    "needed_by": [x["id"] for x in self.tasks() if subject in x.get("dependencies", [])]}
        raise EngineError("ask owns, depends or approves")

    def export(self) -> str:
        with self.lock:
            ts = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
            path = self.paths["exports"] / f"cynqra_export_{ts}.zip"
            manifest = {"format": "cynqra-export-1", "company_id": self.cid, "created_at": now(), "categories": {}, "files": {}}
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                def add(arc: str, data: bytes, cat: str):
                    z.writestr(arc, data)
                    manifest["files"][arc] = digest(data)
                    manifest["categories"].setdefault(cat, 0)
                    manifest["categories"][cat] += 1
                src = self.paths["main"] if any(self.paths["main"].iterdir()) else self.paths["integration"]
                for p in sorted(src.rglob("*")):
                    if p.is_file() and "__pycache__" not in p.parts:
                        rel = p.relative_to(src).as_posix()
                        add(f"repository/{rel}", p.read_bytes(), "documents_and_designs" if rel.startswith("docs/") else "repository")
                add("decisions.json", json.dumps(self.store.all("decision"), indent=1).encode(), "decision_history")
                add("events.jsonl", "\n".join(json.dumps(e) for e in self.store.events()).encode(), "event_log")
                org = {"organization": self.store.get("organization", "org_1"), "workers": self.store.all("worker"),
                       "policy_version": policy.POLICY_VERSION, "matrix": policy.MATRIX, "risk": policy.RISK}
                add("organization.json", json.dumps(org, indent=1).encode(), "organization_configuration")
                add("objective.json", json.dumps(self.objective(), indent=1).encode(), "organization_configuration")
                protos = [self.store.get_object(p["hash"]) for p in self.store.all("protocol")]
                add("protocols.json", json.dumps(protos, indent=1).encode(), "decision_history")
                infra = {"run": "python app.py", "env": {"PORT": "port to serve on", "DATA_FILE": "path to the JSON data file"},
                         "deployments": [{k: d[k] for k in ("id", "status", "url")} for d in self.store.all("deployment")]}
                add("infrastructure.json", json.dumps(infra, indent=1).encode(), "infrastructure_configuration")
                manifest["non_portable"] = ["The POC deploys to a local process only. There are no cloud resources to move."]
                z.writestr("manifest.json", json.dumps(manifest, indent=1))
            self.event("state.changed", "company", self.cid, {"export": path.name, "files": len(manifest["files"])},
                       actor="export")
            return str(path)

    def final_report(self) -> dict:
        """Section 8, the last screen: what was delivered, the budget forecast against the actual, how every worker
        and intelligence performed, and every intelligence change."""
        src = self.paths["main"] if any(self.paths["main"].iterdir()) else self.paths["integration"]
        files = sorted(p.relative_to(src).as_posix() for p in src.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
        reg = self.wf.reg if self.staffed_by_registry() else None
        return {"artifacts": files, "live_url": self.live_url(),
                "exports": sorted(p.name for p in self.paths["exports"].glob("*.zip")),
                "requirements": {"total": len((self.requirements() or {}).get("requirements", [])),
                                 "uncovered_by_tasks": (self.store.get("plan", "plan_1") or {}).get("uncovered_requirements", [])},
                "economics": budget_engine.actual(self.store, self.store.get("forecast", "current")),
                "forecast": self.store.get("forecast", "current"),
                "performance": performance.all_cards(self.store, reg),
                "intelligence_changes": self.store.all("replacement"), "evaluations": self.store.all("evaluation"),
                "metrics": self.metrics()}

    def snapshot(self) -> dict:
        # Read without self.lock so the UI stays live while a step waits on a model call.
        m = self.meta
        decisions = self.store.all("decision")
        protocols = self.store.all("protocol")
        return {
            "meta": m,
            "demo_messy": self.demo_messy,
            "policy": {"version": policy.POLICY_VERSION, "matrix": policy.MATRIX, "risk": policy.RISK},
            "intelligence": self._intel.label if self._intel else None,
            "company": self.store.get("company", self.cid),
            "objective": self.objective(),
            "organization": self.store.get("organization", "org_1"),
            "workers": self.store.all("worker"),
            "plan": self.store.get("plan", "plan_1"),
            "tasks": self.tasks() if self.store.get("plan", "plan_1") else [],
            "decisions": {"pending": [d for d in decisions if d["status"] == "pending"],
                          "answered": [d for d in decisions if d["status"] != "pending"]},
            "protocols": protocols[-40:],
            "denied": [a for a in self.store.all("action") if a["status"] == "denied"],
            "verifications": self.store.all("verification"),
            "deployments": self.store.all("deployment"),
            "transition": self.store.get("transition", "tr_1"),
            "budget": self.budget(),
            "workforce": self.workforce_view(),
            "catalog": roles.catalog(),
            "requirements": self.requirements(),
            "proposal": self.proposal(),
            "forecast": self.store.get("forecast", "current"),
            "economics": budget_engine.actual(self.store, self.store.get("forecast", "current"))
            if self.store.get("forecast", "current") else None,
            "performance": performance.all_cards(self.store, self.wf.reg if self.staffed_by_registry() else None)
            if self.store.all("worker") else [],
            "evaluations": self.store.all("evaluation"),
            "final": self.final_report() if m.get("phase") in ("delivered", "accepted") else None,
            "metrics": self.metrics() if self.store.get("company", self.cid) else {},
            "evolution": self.evolution() if self.store.all("worker") else None,
            "rules": self.rules(),
            "live_url": self.live_url(),
            "events": self.store.events()[-60:],
            "exports": sorted(p.name for p in self.paths["exports"].glob("*.zip")),
        }

    def workforce_view(self) -> dict:
        """Who runs on which model, why, what each may spend and has spent, and every replacement."""
        if self.wf is None:
            return {"active": False, "why": "no model registry in this app"}
        view = {"registry": self.wf.reg.snapshot(), "settings": Workforce.settings(self.store)}
        if not self.staffed_by_registry():
            view.update(active=False, why="demo mode, or no available model in the registry")
            return view
        L = Workforce.ledger(self.store)
        staffing = {s["worker_id"]: s for s in self.store.all("staffing")}
        view.update(active=True, ledger=L, replacements=self.store.all("replacement"),
                    system=self.store.get("workforce", "system"),
                    workers=[{"id": w["id"], "role": w["role"], "title": w["title"], "model_id": w.get("model_id"),
                              "model": w.get("intelligence_source_id"), "reports_to": w.get("reports_to"),
                              "budget": L["by_worker"].get(w["id"], {"allocated": 0.0, "spent": 0.0}),
                              "candidates": (staffing.get(w["id"]) or {}).get("candidates", []),
                              "performance": w.get("performance_profile")} for w in self.store.all("worker")])
        return view

    def close(self) -> None:
        deploy.stop(self.live_proc)
        self.store.close()
