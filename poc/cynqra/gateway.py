"""The execution boundary (Stage 8): every worker action passes here.

The intelligence proposes or requests an action; Cynqra stays responsible for everything else:
identity -> authority and policy -> budget -> target validation -> execute -> sanitize -> audit.
A LOW action inside the worker's own workspace executes; MEDIUM and HIGH wait for the founder's approval; a
PROHIBITED one is refused whoever asks. The tools a worker can reach are exactly the ones implemented here.
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path

from . import binding, budget, policy, worker_runtime
from .db import SECRET, digest, now
from .testrunner import run_unittests

ALLOWED_EXT = {".py", ".md", ".html", ".json", ".txt", ".css", ".js"}
MAX_FILE = 200_000  # bytes
# Output a worker may never write: credentials. Found in a write, the write is refused and the refusal audited.
NO_COST = ("deploy_production", "product_rule_decision", "assign_task", "answer_blocker", "send_protocol",
           "read_artifact", "review_work")


class GatewayError(RuntimeError):
    pass


def execute(run, worker_id: str, task_id: str, action_type: str, target: str = "", *, content: str | None = None,
            approval: str | None = None, cwd: Path | None = None) -> dict:
    w = run.worker(worker_id)
    if w is None or w.get("status") != "active":
        raise GatewayError(f"unknown or inactive worker {worker_id}")
    state = budget.ledger(run.store)["state"]
    decision = policy.evaluate(role=w["role"], action_type=action_type, frozen=run.meta["frozen"], budget_state=state,
                               target=target)
    action = {"id": "a_" + uuid.uuid4().hex[:10], "company_id": run.cid, "task_id": task_id, "worker_id": worker_id,
              "role": w["role"], "model_id": binding.intelligence_of(run.store, worker_id), "action_type": action_type, "target": target,
              "risk_tier": decision["risk_tier"], "policy_decision": decision["decision"],
              "policy_reason": decision["reason"], "policy_version": decision["policy_version"],
              "authority_snapshot": dict(policy.MATRIX.get(w["role"], {})), "status": "", "created_at": now(),
              "approval": approval}
    auth = f"{w['role']}:{policy.MATRIX.get(w['role'], {}).get(action_type, 'none')}"
    if decision["decision"] == "DENY":
        return _refuse(run, action, task_id, auth, decision["reason"], decision)
    if decision["decision"] == "REQUIRE_APPROVAL":
        d = run.store.get("decision", approval) if approval else None
        approved_target = (d or {}).get("extra", {}).get("target")
        if (not d or d.get("status") != "approved" or d.get("action_type") != action_type
                or d.get("task_id") != task_id or (approved_target is not None and approved_target != target)):
            action["status"] = "proposed"
            run.store.put("action", action["id"], action)
            run.event("action.proposed", "action", action["id"], {"task_id": task_id, "action_type": action_type,
                      "risk_tier": decision["risk_tier"], "reason": decision["reason"]}, actor=worker_id,
                      actor_type="worker", correlation_id=task_id, policy_decision="REQUIRE_APPROVAL", authority=auth)
            return {"status": "requires_approval", "action": action, "policy": decision}
        action["status"] = "approved"
        action["approval_scope"] = {"decision_id": approval, "task_id": task_id, "target": target}
    out: dict = {}
    if action_type == "search_files":
        folder = run.workspace(worker_id, task_id) / "out"
        try:
            result = {"needle": target, "files": worker_runtime.search_files(folder, target)}
        except worker_runtime.WorkerRuntimeError as exc:
            return _refuse(run, action, task_id, auth, str(exc))
    elif action_type == "run_command":
        folder = run.workspace(worker_id, task_id) / "out"
        try:
            argv = json.loads(target)
            if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
                raise ValueError("command target must be a JSON string array")
            result = worker_runtime.run(folder, argv, timeout=120)
        except (ValueError, json.JSONDecodeError, worker_runtime.WorkerRuntimeError) as exc:
            return _refuse(run, action, task_id, auth, str(exc))
    elif action_type == "read_artifact":
        folder = run.workspace(worker_id, task_id) / "out"
        try:
            result = {"file": target, "content": worker_runtime.read_file(folder, target)} if target else {"files": worker_runtime.list_files(folder)}
        except worker_runtime.WorkerRuntimeError as exc:
            return _refuse(run, action, task_id, auth, str(exc))
    elif action_type == "write_file":
        folder = run.workspace(worker_id, task_id) / "out"
        rel = Path(target)
        if rel.is_absolute() or ".." in rel.parts or rel.suffix not in ALLOWED_EXT or len(rel.parts) > 3:
            return _refuse(run, action, task_id, auth, f"target {target!r} is outside the workspace rules")
        if content is None or len(content.encode("utf-8")) > MAX_FILE:
            return _refuse(run, action, task_id, auth, "content missing or larger than 200 KB")
        if SECRET.search(content):
            return _refuse(run, action, task_id, auth, "content holds what looks like a credential; keys belong in "
                                                       "environment variables, never in files")
        dest = (folder / rel).resolve()
        if folder.resolve() not in dest.parents:
            return _refuse(run, action, task_id, auth, "path escapes the workspace")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        result = {"file": target, "hash": digest(content.encode("utf-8")), "bytes": len(content.encode("utf-8"))}
    elif action_type == "delete_data":
        folder = run.workspace(worker_id, task_id) / "out"
        try:
            worker_runtime.delete_file(folder, target)
            result = {"deleted": target}
        except worker_runtime.WorkerRuntimeError as exc:
            return _refuse(run, action, task_id, auth, str(exc))
    elif action_type == "install_package":
        folder = run.workspace(worker_id, task_id) / "out"
        package = target.strip()
        if not package or any(x in package for x in (";", "&&", "||", "`", "$")):
            return _refuse(run, action, task_id, auth, "invalid package target")
        try:
            result = worker_runtime.run(folder, ["pip", "install", package], timeout=300)
        except worker_runtime.WorkerRuntimeError as exc:
            return _refuse(run, action, task_id, auth, str(exc))
    elif action_type == "run_tests":
        t0 = time.time()
        report = run_unittests(cwd or run.workspace(worker_id, task_id) / "out")
        seconds = round(time.time() - t0, 2)
        run.spend(worker_id, task_id, budget.machine_usd(run.store, seconds), "tools")
        result = {"ran": report["ran"], "passed": report["passed"], "failed": report["failed"],
                  "test_ids": [x["id"] for x in report["tests"]], "seconds": seconds}
        out["report"] = report  # the whole run, output included, for the caller; the audit keeps the summary
    elif action_type == "merge_to_main":
        main = run.paths["main"]
        if main.exists():
            shutil.rmtree(main)
        shutil.copytree(run.paths["integration"], main)
        files = sorted(str(p.relative_to(main)) for p in main.rglob("*") if p.is_file())
        result = {"files": len(files), "tree": digest({f: digest((main / f).read_bytes()) for f in files})}
    elif action_type in NO_COST:
        result = {"ok": True}
    else:
        return _refuse(run, action, task_id, auth, f"no tool implementation for {action_type}")
    stored_result = result
    if action_type == "read_artifact":
        stored_result = {"file": target, "bytes": len(result.get("content", "").encode("utf-8"))} if target else {"files": result.get("files", [])}
    elif action_type == "search_files":
        stored_result = {"needle": target[:100], "files": result.get("files", [])}
    elif action_type == "run_command":
        stored_result = {"argv": result.get("argv", []), "returncode": result.get("returncode"), "passed": result.get("passed")}
    elif action_type == "install_package":
        stored_result = {"argv": result.get("argv", []), "returncode": result.get("returncode"), "passed": result.get("passed")}
    action.update({"status": "executed", "result": stored_result})
    run.store.put("action", action["id"], action)
    run.event("action.executed", "action", action["id"], {"task_id": task_id, "action_type": action_type,
              "target": target, "approval": approval, "result": {k: v for k, v in stored_result.items() if k != "test_ids"}},
              actor=worker_id, actor_type="worker", correlation_id=task_id, policy_decision=decision["decision"],
              authority=auth, test_ids=result.get("test_ids"))
    return {"status": "executed", "action": action, "result": result, "policy": decision, **out}


def _refuse(run, action: dict, task_id: str, auth: str, why: str, decision: dict | None = None) -> dict:
    action.update({"status": "denied", "policy_decision": "DENY", "policy_reason": why})
    run.store.put("action", action["id"], action)
    run.event("action.denied", "action", action["id"], {"task_id": task_id, "action_type": action["action_type"],
              "reason": why, "risk_tier": action["risk_tier"]}, actor=action["worker_id"], actor_type="worker",
              correlation_id=task_id, policy_decision="DENY", authority=auth)
    return {"status": "denied", "action": action, "policy": decision or {"decision": "DENY", "reason": why}}
