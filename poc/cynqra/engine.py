"""The Cynqra POC engine: one company, one fixed organization, one run.

Book 0 core loop, first transition only: objective -> organization -> working product.
Everything a worker does passes the Gateway (identity, policy, budget, target check,
execute, audit). Everything the founder does is a decision with a label (D-10).
"""
from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from . import deploy, policy
from .db import IST, Store, digest, now
from .intelligence import IntelligenceError, make
from .protocol import ProtocolError, build
from .verification import lint_documents, run_unittests

OBJECTIVE_FIELDS = ["product", "target_customer", "primary_outcome", "business_outcome",
                    "success_criteria", "constraints", "priorities"]
TEMPLATE = [
    {"id": "w_cto", "role": "CTO", "title": "CTO", "capabilities": ["architecture", "review", "release"]},
    {"id": "w_pm", "role": "PM", "title": "PM", "capabilities": ["product", "specs", "planning"]},
    {"id": "w_eng_a", "role": "Engineer", "title": "Engineer A", "capabilities": ["backend", "testing"]},
    {"id": "w_eng_b", "role": "Engineer", "title": "Engineer B", "capabilities": ["backend", "frontend", "testing"]},
]
REPORTS_TO = {"w_cto": "founder", "w_pm": "w_cto", "w_eng_a": "w_pm", "w_eng_b": "w_pm"}
UNIT_COST = {"write_file": 1, "read_artifact": 0, "run_tests": 2, "merge_to_main": 2, "deploy_production": 4,
             "verify": 2, "integrate": 0}
ALLOWED_EXT = {".py", ".md", ".html", ".json", ".txt", ".css", ".js"}
ESCALATIONS_PER_DAY = 5  # D-29
MAX_ATTEMPTS = 3
TASK_STATES = ["PLANNED", "ASSIGNED", "IN_PROGRESS", "BLOCKED", "REVIEW", "REWORK", "AWAITING_FOUNDER",
               "APPROVED", "VERIFIED", "FAILED"]


class EngineError(RuntimeError):
    pass


class Engine:
    def __init__(self, data_dir: Path, intelligence=None, scenario: str = "candidate_tracker"):
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
            self._intel = make(self.meta.get("mode", "demo"), self.scenario)
        return self._intel

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
        if b["spent"] >= b["cap"] and b["state"] != "breaker":
            b["state"] = "breaker"
            self.event("budget.threshold_reached", "company", self.cid,
                       {"threshold": 100, "spent": b["spent"], "cap": b["cap"], "unit": "work_units"},
                       actor="budget", policy_decision="DENY", correlation_id=task_id or self.cid)
            self.store.put("budget", "company", b)
            self._decision("budget_breaker", problem="The company budget cap is reached. All work is paused.",
                           recommendation=f"Raise the cap from {b['cap']} to {b['cap'] + 60} work units, or stop the run.",
                           risk="HIGH", confidence="high", cost="none until work resumes",
                           evidence=[f"spent {b['spent']} of {b['cap']}"],
                           change="Nothing: the cap is yours to set.", severity="SEV-2", source="budget")
            return
        self.store.put("budget", "company", b)

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
                  "intelligence": w["intelligence_source_id"], "budget_before": b["spent"], "status": "",
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
            dest = (out_dir / rel).resolve()
            if out_dir.resolve() not in dest.parents:
                return self._deny_target(action, task_id, auth, "path escapes the workspace")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            result = {"file": target, "hash": digest(content.encode("utf-8")), "bytes": len(content.encode("utf-8"))}
        elif action_type == "run_tests":
            folder = cwd or self._ws(worker_id, task_id) / "out"
            report = run_unittests(folder)
            result = {"ran": report["ran"], "passed": report["passed"], "failed": report["failed"],
                      "test_ids": [t["id"] for t in report["tests"]]}
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
        return {"status": "executed", "action": action, "result": result, "policy": decision}

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
            self._intel = self._injected
            _ = self.intel  # live mode fails here, before anything is written, if no key
            company = {"id": self.cid, "name": name, "stage": "IDEA", "autonomy_level": "L1",
                       "budget_cap": 120, "risk_tolerance": "conservative", "status": "active", "created_at": now()}
            self.store.put("company", self.cid, company)
            self.store.put("budget", "company", {"cap": 120, "spent": 0, "warned": [], "state": "ok"})
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

    def set_guardrails(self, budget_cap: int | None = None, risk_tolerance: str | None = None) -> dict:
        with self.lock:
            self._require("objective")
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
            self.store.put("company", self.cid, company)
            return company

    def confirm_objective(self) -> dict:
        with self.lock:
            self._require("objective")
            obj = self.objective()
            if obj is None:
                raise EngineError("no objective to confirm")
            if obj["missing_fields"]:
                raise EngineError(f"fill these fields first: {', '.join(obj['missing_fields'])}")
            d = self._decision("confirm_objective", problem="The structured objective needs the founder's confirmation.",
                               recommendation="Confirm the objective as shown.", risk="LOW", confidence="high",
                               cost="none", evidence=["objective obj_1"], change="Any field that reads wrong.",
                               source="orchestrator")
            return self.decide(d["id"], "approve")

    def _after_confirm_objective(self, d: dict, action: str) -> None:
        obj = self.objective()
        obj.update({"status": "confirmed", "confirmed_by": "founder", "confirmed_at": now()})
        self.store.put("objective", "obj_1", obj)
        self.event("objective.changed", "objective", "obj_1", {"version": obj["version"], "status": "confirmed"},
                   actor="founder", actor_type="human", authority="founder")
        self._instantiate_org()
        self._plan()

    def _instantiate_org(self) -> None:
        label = self.intel.label
        org = {"id": "org_1", "company_id": self.cid, "template": "fixed_mvp_4", "version": 1, "status": "proposed",
               "workers": [w["id"] for w in TEMPLATE], "reports_to": REPORTS_TO,
               "services": [{"id": "verification", "title": "Verification Service",
                             "note": "Platform service, not a worker. Runs tests, lint and review tiers."}]}
        self.store.put("organization", "org_1", org)
        self.event("organization.changed", "organization", "org_1", {"template": "fixed_mvp_4", "worker_count": 4,
                   "version": 1})
        for t in TEMPLATE:
            w = dict(t)
            w.update({"company_id": self.cid, "intelligence_source_id": label,
                      "authority_policy_id": f"{policy.POLICY_VERSION}:{t['role']}", "cost_profile": "work units",
                      "status": "active", "reports_to": REPORTS_TO[t["id"]],
                      "performance_profile": {"verified": 0, "first_pass": 0, "reworks": 0, "blockers": 0}})
            self.store.put("worker", t["id"], w)
            self.event("worker.hired", "worker", t["id"], {"role": t["role"], "intelligence": label})

    def _plan(self) -> None:
        plan, usage = self.intel.plan(self.objective())
        self._record_call("plan", "w_pm", "plan", usage)
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
                       "owner_worker_id": task["owner_worker_id"], "dependencies": task["dependencies"]},
                       actor="w_pm", actor_type="worker", correlation_id=task["id"])
        self.store.put("plan", "plan_1", {"id": "plan_1", "workstreams": plan["workstreams"], "order": order})
        total = sum(int(self.task(t).get("budget") or 0) for t in order)
        self._decision("approve_plan", problem="Cynqra proposes the fixed organization and a plan for your objective.",
                       recommendation=f"Approve the four worker organization and the {len(order)} task plan.",
                       risk="LOW", confidence="high", cost=f"about {total} work units of {self.budget()['cap']}",
                       evidence=[f"{t}: {self.task(t)['title']}" for t in order],
                       change="A task that does not serve the objective, or a missing one.", source="orchestrator")
        self._set_meta(phase="planning")

    def _after_approve_plan(self, d: dict, action: str) -> None:
        if action == "approve":
            org = self.store.get("organization", "org_1")
            org.update({"status": "active", "approved_by": "founder", "approved_at": now()})
            self.store.put("organization", "org_1", org)
            company = self.store.get("company", self.cid)
            company["stage"] = "MVP"
            self.store.put("company", self.cid, company)
            self.event("state.changed", "company", self.cid, {"stage": "MVP", "phase": "running"}, actor="founder",
                       actor_type="human", authority="founder")
            self._set_meta(phase="running", started_at=time.time())
        else:
            self._plan()

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
                    if t["attempts"] >= MAX_ATTEMPTS:
                        return self._escalate(t, f"{t['id']}: the worker kept returning invalid protocol objects ({exc})")
                    t.update({"status": "REWORK", "feedback": f"Your reply was not a valid protocol object: {exc}"})
                    self._save_task(t)
                    return {"did": "rework", "task": t["id"], "why": str(exc)}
                except IntelligenceError as exc:
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
        self.store.put("call", f"call_{n:04d}", {"id": f"call_{n:04d}", "task_id": task_id, "worker": worker,
                       "purpose": purpose, **usage, "at": now()})
        self.charge(int(usage.get("units", 1)), "intelligence", task_id if task_id.startswith("t_") else None)

    def _artifact_index(self) -> list[str]:
        return [a["id"] for a in self.store.all("artifact")]

    def _assign(self, t: dict) -> dict:
        owner = t["owner_worker_id"]
        if owner in ("w_pm", "w_cto"):
            assigner = "orchestrator"
            arts = [a["id"] for a in self.store.all("artifact") if a["task_id"] in t.get("dependencies", [])]
            content = {"artifacts": arts, "context_ref": t["context"],
                       "acceptance_check": f"{t['title']}. Expected: {t['expected_output']}. Verified by: {t['verification_method']}."}
        else:
            assigner = "w_pm"
            g = self.gateway("w_pm", t["id"], "assign_task", target=t["id"])
            if g["status"] != "executed":
                return {"did": "blocked_by_policy", "task": t["id"]}
            content, usage = self.intel.assign(t, objective=self.objective()["structured"], rules=self.rules(),
                                               artifact_index=self._artifact_index())
            self._record_call(t["id"], "w_pm", "assign", usage)
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
        result, usage = self.intel.work(t, worker=owner, objective=self.objective()["structured"], rules=self.rules(),
                                        handoff=t.get("handoff") or {}, inbox=self._inbox(t), feedback=t.get("feedback", ""),
                                        answers=t.get("answers", []), call_index=t["work_calls"])
        t["work_calls"] += 1
        self._save_task(t)
        self._record_call(t["id"], owner, "work", usage)
        kind = t["kind"]
        if result.get("result") == "blocked":
            needs = result.get("needs_from") if result.get("needs_from") in ("w_pm", "w_cto") else "w_pm"
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
            files = result.get("files") or {}
            if not files:
                raise IntelligenceError(f"{t['id']}: work returned no files")
            out = self._ws(owner, t["id"]) / "out"
            for old in out.iterdir():
                if old.is_file():
                    old.unlink()
            written = []
            for name, text in files.items():
                g = self.gateway(owner, t["id"], "write_file", target=name, content=text)
                if g["status"] != "executed":
                    t.update({"status": "REWORK", "feedback": f"write refused: {g['policy']['reason']}"})
                    t["attempts"] += 1
                    self._save_task(t)
                    return {"did": "write_refused", "task": t["id"]}
                written.append(g["result"])
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
            if side:
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

    def _escalate(self, t: dict, why: str) -> dict:
        owner = t["owner_worker_id"]
        esc = self.send("Escalation", {"issue": why, "required_action": "Founder decides: retry the task or stop the run.",
                                       "severity": "SEV-2"},
                        {"raised_by": owner, "owner": "founder"}, t["id"], owner)
        d = self._decision("escalation", problem=why, recommendation="Retry the task once more with the failure as feedback.",
                           risk=t["risk_tier"], confidence="low", cost="one more attempt",
                           evidence=[f"escalation {esc['object_hash']}"], change="A fix that makes the checks pass.",
                           task_id=t["id"], source=owner, severity="SEV-2")
        t.update({"status": "FAILED", "decision_id": d["id"]})
        self._save_task(t)
        self.event("task.failed", "task", t["id"], {"reason": why[:200]}, correlation_id=t["id"], actor=owner,
                   actor_type="worker", protocol_hash=esc["object_hash"])
        return {"did": "escalated", "task": t["id"], "decision": d["id"]}

    def _answer(self, t: dict) -> dict:
        blocker = t["blocker"]
        who = blocker.get("needs_from", "w_pm")
        g = self.gateway(who, t["id"], "answer_blocker", target=t["id"])
        if g["status"] != "executed":
            return self._escalate(t, g["policy"]["reason"])
        content, usage = self.intel.answer_blocker(t, worker=who, objective=self.objective()["structured"],
                                                   rules=self.rules(), blocker=blocker, artifact_index=self._artifact_index())
        self._record_call(t["id"], who, "answer_blocker", usage)
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
        vdir = self.dir / "verify" / f"{t['id']}_{t['attempts'] + 1}"
        if vdir.exists():
            shutil.rmtree(vdir)
        shutil.copytree(self.paths["integration"], vdir)
        out = self._ws(owner, t["id"]) / "out"
        for p in out.iterdir():
            if p.is_file():
                shutil.copy2(p, vdir / p.name)
        n = self._count("verification") + 1
        vid = f"v_{n:03d}"
        if t["kind"] == "code":
            report = run_unittests(vdir)
            passed = report["passed"]
            test_ids = [x["id"] for x in report["tests"]]
            checks = {"ran": report["ran"], "failed": report["failed"], "prior_tests_rerun": True}
            feedback = ("Failing tests: " + ", ".join(report["failed"]) + "\n" + report["output"][-1500:]) if not passed else ""
            method = "automated tests, prior tests rerun"
        else:
            docs = {p.name: p.read_text(encoding="utf-8") for p in out.iterdir() if p.is_file()}
            lint = lint_documents(docs, self.objective()["structured"])
            passed = lint["passed"]
            test_ids = []
            checks = {"lint": lint["findings"]}
            feedback = "; ".join(f["why"] for f in lint["findings"])
            method = "coverage lint against the confirmed objective"
        verdict = "VERIFIED" if passed else ("REQUIRES_REWORK" if t["attempts"] + 1 < MAX_ATTEMPTS else "REQUIRES_HUMAN")
        self.charge(UNIT_COST["verify"], "verify", t["id"])
        v = {"id": vid, "company_id": self.cid, "task_id": t["id"], "attempt": t["attempts"] + 1,
             "risk_tier": t["risk_tier"], "method": method, "checks": checks, "reviewer_type": "service",
             "reviewer_id": "verification", "verdict": verdict, "test_ids": test_ids,
             "output_hash": digest(json.dumps(checks)), "created_at": now()}
        self.store.put("verification", vid, v)
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
            return self._escalate(t, f"{t['id']} failed verification {t['attempts']} times: {feedback[:200]}")
        t.update({"status": "REWORK", "feedback": feedback})
        self._save_task(t)
        self.event("task.failed", "task", t["id"], {"attempt": t["attempts"], "rework": True, "verification": vid},
                   actor="verification", correlation_id=t["id"], test_ids=test_ids)
        return {"did": "rework", "task": t["id"]}

    def _integrate(self, t: dict, out: Path) -> None:
        dest_root = self.paths["integration"]
        for p in sorted(out.iterdir()):
            if not p.is_file():
                continue
            rel = Path("docs") / p.name if p.suffix == ".md" else Path(p.name)
            (dest_root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest_root / rel)
            aid = f"{t['id']}/{p.name}"
            self.store.put("artifact", aid, {"id": aid, "task_id": t["id"], "path": str(rel).replace("\\", "/"),
                                             "hash": digest(p.read_bytes()), "by": t["owner_worker_id"]})
        self.event("action.executed", "action", f"integrate_{t['id']}", {"task_id": t["id"], "action_type": "integrate",
                   "files": sorted(p.name for p in out.iterdir() if p.is_file())}, actor="verification",
                   correlation_id=t["id"])

    def _smoke_checks(self, folder: Path) -> list[dict]:
        f = folder / "smoke.json"
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8")).get("checks", [])
            except (ValueError, AttributeError):
                return []
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
            t.update({"status": "REWORK" if t["kind"] in ("spec", "code") else "ASSIGNED", "attempts": 0})
            self._save_task(t)
        else:
            self._set_meta(phase="stopped", notice=f"Run stopped by the founder at {t['id']}.")

    def _after_budget_breaker(self, d: dict, action: str) -> None:
        if action == "approve":
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
                return self._escalate(t, "the live release failed its health or smoke check and was rolled back")
            self.event("deployment.verified", "deployment", dep["id"], {"url_port": res["url"].rsplit(":", 1)[-1],
                       "stages": [x["stage"] for x in dep["log"]]}, correlation_id=t["id"], actor="deployment")
            test_ids = dep.get("test_ids", [])
            verdict, method, checks = "VERIFIED", "health check and smoke test on the live URL", {"url": res["url"]}
        v = {"id": vid, "company_id": self.cid, "task_id": t["id"], "attempt": t["attempts"] + 1, "risk_tier": t["risk_tier"],
             "method": method, "checks": checks, "reviewer_type": "human" if t["kind"] == "decision" else "service",
             "reviewer_id": "founder" if t["kind"] == "decision" else "verification", "verdict": verdict,
             "test_ids": test_ids, "output_hash": digest(json.dumps(checks)), "created_at": now()}
        self.store.put("verification", vid, v)
        self.event("verification.completed", "verification", vid, {"task_id": t["id"], "verdict": verdict, "method": method},
                   actor="verification", correlation_id=t["id"], test_ids=test_ids)
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
              "proposed_change": "Create the fixed_mvp_4 organization and run the plan to a live release.",
              "expected_result": self.objective()["structured"]["success_criteria"],
              "cost": f"{self.budget()['spent']} work units", "risk": "HIGH (production deploy)",
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
        with self.lock:
            self._set_meta(frozen=bool(on))
            self._intervention("kill_switch", "on" if on else "off")
            self.event("state.changed", "company", self.cid, {"frozen": bool(on), "control": "kill_switch"},
                       actor="founder", actor_type="human", authority="founder", policy_decision="DENY" if on else "ALLOW")
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
            "worker_protocol_objects": len(protos),
            "protocol_objects_per_verified_task": round(len(protos) / len(verified), 1) if verified else None,
            "escalations_today": len([d for d in self.store.all("decision") if d.get("source", "").startswith("w_")
                                      and d.get("created_day") == datetime.now(IST).date().isoformat()]),
            "escalation_budget": ESCALATIONS_PER_DAY,
            "seconds_to_live": round(end - start, 1) if start and end else None,
            "events": self.store.count_events(),
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
            return {"task": subject, "owner": t["owner_worker_id"], "reports_to": REPORTS_TO[t["owner_worker_id"]]}
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

    def snapshot(self) -> dict:
        with self.lock:
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
                "metrics": self.metrics() if self.store.get("company", self.cid) else {},
                "evolution": self.evolution() if self.store.all("worker") else None,
                "rules": self.rules(),
                "live_url": self.live_url(),
                "events": self.store.events()[-60:],
                "exports": sorted(p.name for p in self.paths["exports"].glob("*.zip")),
            }

    def close(self) -> None:
        deploy.stop(self.live_proc)
        self.store.close()
