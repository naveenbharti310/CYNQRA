"""Governed execution (Stage 8): each task's lifecycle, from Handoff to verified.

Cofounders run their areas. A team member's task is handed over by its cofounder; the owner works on it (files
through the gateway, or a proposal for the founder); files are checked by the task type's verifier, then reviewed by
the cofounder before they count; a proposal is reviewed by the cofounder before it reaches the founder.

PLANNED -> ASSIGNED (a Handoff from the owner's cofounder, or from the roadmap for a cofounder's own task)
  -> the owner works -> REVIEW (the platform's checks) -> LEAD_REVIEW (the cofounder) -> VERIFIED, or back for
     REWORK with the failure or the cofounder's note named
  -> a proposal: LEAD_REVIEW (the cofounder) -> AWAITING_FOUNDER -> APPROVED -> carried out and verified
A worker who would have to guess raises a Blocker instead: to its cofounder, or to the colleague who knows. A task
that keeps failing goes to the Replacement Engine, and to the founder only when no other intelligence can take it.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import attribution as attr
from . import budget, controller, deploy, objective, people, replacement, roles, verifier
from . import settings as project_settings
from .db import digest, now
from .protocol import ProtocolError
from .testrunner import failure_summary

MAX_ATTEMPTS = verifier.MAX_ATTEMPTS
MAX_CUT_OFFS = 3  # replies in a row cut off at the model's output limit before the task goes to the Replacement Engine
MAX_SEND_BACKS = 2  # times a cofounder may send the same task back; after that the platform's checks decide
MAX_REVIEW_ERRORS = 2  # unreadable reviews in a row before the work goes on without one, and it is said
PROPOSAL_ACTIONS = {"decision": "product_rule_decision", "review_merge": "merge_to_main", "deploy": "deploy_production"}


actor = replacement.actor  # whose move it is on a task, in its current state


def artifact_index(run) -> list[str]:
    return [a["id"] for a in run.store.all("artifact")]


def _as_list(value) -> list:
    """A model may name one artifact as text, or answer with something that is not a list at all."""
    return [value] if isinstance(value, str) else value if isinstance(value, list) else []


def _deliver_artifacts(run, t: dict, ids: list[str]) -> None:
    inbox = run.workspace(t["owner_worker_id"], t["id"]) / "inbox"
    for aid in ids:
        a = run.store.get("artifact", aid)
        (inbox / Path(a["path"]).name).write_text((run.paths["integration"] / a["path"]).read_text(encoding="utf-8"),
                                                 encoding="utf-8")


def perf(run, wid: str, key: str) -> None:
    w = run.worker(wid)
    if w:
        w["performance_profile"][key] = w["performance_profile"].get(key, 0) + 1
        run.store.put("worker", wid, w)


def frozen_during_call(run, t: dict) -> dict:
    """The kill switch went on while the model was answering: the answer is dropped, the task stays where it was.
    A cancellation, recorded as such: never a failure of the intelligence that was answering."""
    run.event("action.denied", "task", t["id"], {"task_id": t["id"], "reason": "kill switch on when the model answered; "
              "the answer was discarded"}, actor="policy", correlation_id=t["id"], policy_decision="DENY")
    controller.record_attempt_failure(run, t, attr.failure("cancelled", "the kill switch stopped the work mid-call"),
                                      kind="cancelled", idempotency_key=f"cancel:{t['id']}:{t.get('work_calls')}:"
                                      f"{run.count('intervention')}")
    return {"did": "paused", "task": t["id"], "why": "kill switch"}


def assign(run, t: dict) -> dict:
    # the work is about to start: when the objective's evidence moved on since its intelligence was chosen, the
    # choice is checked again (a challenger takes it only on verified superiority); history is never rewritten
    controller.revalidate(run, t)
    t = run.task(t["id"])
    owner, sender = t["owner_worker_id"], t["handoff_from"]
    if sender == "orchestrator":  # a cofounder's own task: the platform hands it over from the approved roadmap
        arts = [a["id"] for a in run.store.all("artifact") if a["task_id"] in t["dependencies"]]
        crit = "; ".join(t["acceptance_criteria"])
        content = {"artifacts": arts, "context_ref": t["context"],
                   "acceptance_check": f"{t['title']}. Expected: {t['expected_output']}. Acceptance criteria: {crit}. "
                                       f"Verified by: {t['verification_gate']}."}
    else:
        g = run.gateway(sender, t["id"], "assign_task", target=t["id"])
        if g["status"] != "executed":
            return {"did": "blocked_by_policy", "task": t["id"], "why": g["policy"]["reason"]}
        content, usage = run.intel.assign(t, objective=run.objective_ctx(), rules=run.rules(),
                                          artifact_index=artifact_index(run), worker=sender, persona=run.persona(sender))
        run.record_call(t["id"], sender, "assign", usage)
        if run.meta["frozen"]:
            return frozen_during_call(run, t)
        known = set(artifact_index(run))
        content["artifacts"] = [a for a in _as_list(content.get("artifacts")) if isinstance(a, str) and a in known]
    handoff = run.send("Handoff", content, {"from_worker": sender, "to_worker": owner, "task_id": t["id"]}, t["id"], sender)
    _deliver_artifacts(run, t, handoff["artifacts"])
    t.update({"status": "ASSIGNED", "handoff_hash": handoff["object_hash"], "handoff": handoff})
    run.save_task(t)
    run.event("worker.assigned", "worker", owner, {"task_id": t["id"], "handoff": handoff["object_hash"]},
              correlation_id=t["id"], actor=sender, actor_type="worker" if sender.startswith("w_") else "service")
    return {"did": "assigned", "task": t["id"], "to": owner}


def _inbox(run, t: dict) -> dict[str, str]:
    inbox = run.workspace(t["owner_worker_id"], t["id"]) / "inbox"
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(inbox.iterdir()) if p.is_file()}


def work(run, t: dict) -> dict:
    owner = t["owner_worker_id"]
    if t["work_calls"] == 0:
        run.event("task.started", "task", t["id"], {"owner": owner, "intelligence": run.model_for(owner, t["id"]),
                  "objective_version": (run.objective() or {}).get("version")}, actor=owner, actor_type="worker",
                  correlation_id=t["id"])
    if not t.get("attempt_open"):  # the attempt keeps the objective version it started under
        t.update(attempt_open=True, attempt_objective_version=(run.objective() or {}).get("version"))
        run.save_task(t)
    out = run.workspace(owner, t["id"]) / "out"
    previous = {p.relative_to(out).as_posix(): p.read_text(encoding="utf-8", errors="replace")
                for p in sorted(out.rglob("*")) if p.is_file()}
    repo = sorted(p.relative_to(run.paths["integration"]).as_posix()
                  for p in run.paths["integration"].rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    who = t["blockers_to"]
    tool_feedback = ""
    result = {}
    for tool_round in range(6):
        result, usage = run.intel.work(
            t, worker=owner, objective=run.objective_ctx(), rules=run.rules(),
            handoff=t.get("handoff") or {}, inbox=_inbox(run, t),
            feedback=(t.get("feedback", "") + tool_feedback),
            answers=t.get("answers", []), call_index=t["work_calls"], previous=previous,
            repo_files=repo, persona=run.persona(owner), answerers=who)
        t["work_calls"] += 1
        run.save_task(t)
        run.record_call(t["id"], owner, "work", usage)
        if run.meta["frozen"]:
            return frozen_during_call(run, t)
        calls = result.get("tool_calls") if isinstance(result, dict) else None
        if not calls:
            break
        if t["kind"] not in roles.FILE_TYPES:
            raise ProtocolError("tool calls are currently supported only for build and file tasks")
        if not isinstance(calls, list) or len(calls) > 8:
            raise ProtocolError("a worker may request at most eight tools in one round")
        observations = []
        use = t.setdefault("tool_use", {"calls": 0, "executed": 0, "denied_intelligence": 0, "denied_environment": 0,
                                        "malformed": 0, "failed_runs": 0, "recovered": 0})
        for call in calls:
            use["calls"] += 1
            if not isinstance(call, dict) or not isinstance(call.get("action"), str):
                use["malformed"] += 1
                run.save_task(t)
                raise ProtocolError("every tool call needs an action")
            action = call["action"]
            if action not in {"read_artifact", "search_files", "write_file", "delete_data", "install_package", "run_command",
                              "run_tests"}:
                use["malformed"] += 1
                run.save_task(t)
                raise ProtocolError(f"worker requested an unsupported tool: {action}")
            target = str(call.get("target") or "")
            content = call.get("content")
            if content is not None and not isinstance(content, str):
                use["malformed"] += 1
                run.save_task(t)
                raise ProtocolError("tool write content must be text")
            g = run.gateway(owner, t["id"], action, target=target, content=content)
            # tool use is evidence too: a request the rules refuse is the intelligence's; a broken tool is not
            if g.get("status") == "executed":
                use["executed"] += 1
                if use.get("_last_failed"):
                    use["recovered"] += 1
                use["_last_failed"] = bool((g.get("result") or {}).get("passed") is False)
                use["failed_runs"] += int(use["_last_failed"])
            else:
                cause = attr.tool_failure(g.get("status"), (g.get("policy") or {}).get("reason") or "")
                use["denied_intelligence" if cause["attributable_to_intelligence"] else "denied_environment"] += 1
                use["_last_failed"] = True
            observations.append({"action": action, "target": target,
                                 "status": g.get("status"), "result": g.get("result"),
                                 "policy": g.get("policy")})
        run.save_task(t)
        tool_feedback = "\n\nTool results from Cynqra:\n" + json.dumps(observations, ensure_ascii=False)[:12000]
        previous = {p.relative_to(out).as_posix(): p.read_text(encoding="utf-8", errors="replace")
                    for p in sorted(out.rglob("*")) if p.is_file()}
    else:
        raise ProtocolError("worker exhausted its six tool rounds without producing a final result")
    if result.get("result") == "blocked":
        # a fact it needed is missing: a specification failure, recorded and never learned as the AI's fault
        controller.record_attempt_failure(run, t, attr.failure("specification", "a fact the work needs is missing",
                                          str(result.get("description") or "")), kind="blocker",
                                          idempotency_key=f"blocker:{t['id']}:{t['work_calls']}")
        needs = result.get("needs_from") if result.get("needs_from") in who else who[0]
        blocker = run.send("Blocker", {"category": result.get("category", "missing_input"),
                                       "description": result.get("description", ""), "needs_from": needs},
                           {"raised_by": owner, "task_id": t["id"]}, t["id"], owner)
        t.update({"status": "BLOCKED", "blocker": blocker, "blockers": t["blockers"] + 1})
        run.save_task(t)
        perf(run, owner, "blockers")
        run.event("task.blocked", "task", t["id"], {"needs_from": needs}, actor=owner, actor_type="worker",
                  correlation_id=t["id"], protocol_hash=blocker["object_hash"])
        return {"did": "blocked", "task": t["id"]}
    if t["kind"] not in roles.FILE_TYPES:
        return propose(run, t, result)
    files, cut = result.get("files"), result.get("cut_off")
    if not isinstance(files, dict) or (not files and not cut):
        raise ProtocolError("a done result needs files: an object of file name to full file content")
    bad = [k for k, v in files.items() if not isinstance(v, str)]
    if bad:
        raise ProtocolError(f"file content must be text: {', '.join(map(str, bad))}")
    # A reply carries the files it writes or changes; the worker's other files stay as they were.
    for name in result.get("delete") or []:
        target = (out / str(name)).resolve()
        if out.resolve() in target.parents and target.is_file():
            target.unlink()
    for name, text in files.items():
        g = run.gateway(owner, t["id"], "write_file", target=str(name), content=text)
        if g["status"] != "executed":
            if budget.ledger(run.store)["state"] == "breaker":
                return {"did": "paused", "task": t["id"], "why": "budget breaker open"}
            cause = attr.tool_failure(g["status"], g["policy"]["reason"])
            controller.record_attempt_failure(run, t, cause, kind="write_refused", severity="major",
                                              idempotency_key=f"write:{t['id']}:{t['work_calls']}:{name}")
            t["attempts"] += 1
            t.update({"status": "REWORK", "feedback": f"write refused: {g['policy']['reason']}"})
            run.save_task(t)
            if t["attempts"] >= MAX_ATTEMPTS:
                return escalate(run, t, f"{t['id']}: writes kept being refused ({g['policy']['reason']})")
            return {"did": "write_refused", "task": t["id"]}
    if cut:
        return _cut_off(run, t, cut, sorted(files))
    t["cut_offs"] = 0
    if t["kind"] in roles.BUILD_TYPES and t.get("self_checks_used", 0) < project_settings.get(run.store)["self_checks"]:
        check = _self_check(run, t)
        if not check["passed"]:
            return check["step"]
    t["self_checks_used"] = 0
    written = [{"file": p.relative_to(out).as_posix(), "hash": digest(p.read_bytes()), "bytes": p.stat().st_size}
               for p in sorted(out.rglob("*")) if p.is_file()]  # the whole result: kept files and new ones
    done = run.send("Handoff", {"artifacts": [w["file"] for w in written], "context_ref": f"result of {t['id']}",
                                "acceptance_check": result.get("acceptance_check") or result.get("summary") or "done"},
                    {"from_worker": owner, "to_worker": "verification", "task_id": t["id"]}, t["id"], owner)
    t.update({"status": "REVIEW", "outputs": written, "summary": result.get("summary", ""),
              "completed_hash": done["object_hash"], "attempt_open": False})
    run.save_task(t)
    run.event("task.completed", "task", t["id"], {"files": [w["file"] for w in written],
              "note": "completed by the worker, not yet verified"}, actor=owner, actor_type="worker",
              correlation_id=t["id"], protocol_hash=done["object_hash"])
    return {"did": "completed", "task": t["id"]}


def _cut_off(run, t: dict, cut: str, saved: list[str]) -> dict:
    """The reply stopped at the model's output limit. The files it finished are saved; the worker is asked for the
    rest. Replies that keep overflowing go to the Replacement Engine rather than being retried without end."""
    t["cut_offs"] = t.get("cut_offs", 0) + 1
    if t["cut_offs"] > MAX_CUT_OFFS:
        verifier.outcome(run, t, False, "replies kept running past the model's output limit")
        return replacement.evaluate(run, t, f"{t['id']}: {MAX_CUT_OFFS + 1} replies in a row were longer than the "
                                            "model's output limit.", forced=True)
    t.update({"status": "REWORK", "feedback": (
        f"Your last reply was longer than the model's output limit and was cut off while writing {cut}, which was "
        "not saved. " + (f"These files were saved: {', '.join(saved)}. " if saved else "No file was finished. ")
        + "Send only the files still missing or unfinished, each one complete and short.")})
    run.save_task(t)
    run.event("task.reply_cut_off", "task", t["id"], {"file": cut, "saved": saved, "round": t["cut_offs"]},
              actor=t["owner_worker_id"], actor_type="worker", correlation_id=t["id"])
    return {"did": "cut_off", "task": t["id"], "saved": saved}


def _self_check(run, t: dict) -> dict:
    """An engineer runs its own checks and fixes failures before handing over, as an engineer does. Verification
    still runs everything again, independently, afterwards."""
    owner = t["owner_worker_id"]
    out = run.workspace(owner, t["id"]) / "out"
    folder = verifier.candidate(run, t, run.workspace(owner, t["id"]) / "check")
    g = run.gateway(owner, t["id"], "run_tests", target="own workspace", cwd=folder)
    res = g.get("result") or {}
    passed, why = g["status"] == "executed" and bool(res.get("passed")), ""
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
        why = failure_summary(g["report"]) + "\n" + g["report"]["output"][-1500:]
    elif t["kind"] == "forecast":
        bt = verifier.backtest(folder)
        passed, why = bt["passed"], "" if bt["passed"] else "the platform's backtest would fail: " + bt["why"]
    if passed and (out / "app.py").exists():
        contract = deploy.contract_check(folder, verifier.smoke_checks(folder))
        if not contract["ok"]:
            passed, why = False, "the app breaks the delivery contract: " + contract["why"]
    t["self_checks_used"] = t.get("self_checks_used", 0) + (0 if passed else 1)
    run.event("worker.self_checked", "task", t["id"], {"task_id": t["id"], "passed": passed,
              "round": t.get("self_checks_used", 0), "tests_ran": res.get("ran", 0)}, actor=owner, actor_type="worker",
              correlation_id=t["id"], test_ids=res.get("test_ids"))
    shutil.rmtree(folder, ignore_errors=True)
    if passed:
        return {"passed": True}
    t.update({"feedback": f"Your own check before handing over failed. {why}"})
    run.save_task(t)
    return {"passed": False, "step": {"did": "self_check_failed", "task": t["id"], "round": t["self_checks_used"]}}


def propose(run, t: dict, result: dict) -> dict:
    owner = t["owner_worker_id"]
    missing = [k for k in ("recommendation", "confidence", "what_would_change_this") if not str(result.get(k) or "").strip()]
    if missing:
        raise ProtocolError(f"proposal is missing {', '.join(missing)}")
    evidence, extra = [str(e) for e in _as_list(result.get("evidence_refs")) if isinstance(e, (str, int, float))], {}
    action_type = PROPOSAL_ACTIONS[t["kind"]]
    if t["kind"] == "review_merge":
        g = run.gateway(owner, t["id"], "run_tests", target="integration", cwd=run.paths["integration"])
        report = g.get("result", {})
        extra["tests"] = report
        evidence.append(f"{report.get('ran', 0)} tests on the release candidate, "
                        f"{'all passed' if report.get('passed') else 'failures: ' + ', '.join(report.get('failed', []))}")
        if not report.get("passed"):
            verifier.escaped(run, report.get("failed", []), "release candidate", t["id"])
            return escalate(run, t, "The release candidate fails its tests, so there is nothing safe to merge.")
    elif t["kind"] == "deploy":
        checks = verifier.smoke_checks(run.paths["main"])
        rid = f"release_{run.count('deployment') + 1}"
        pre = deploy.build_to_verify(run.paths["main"], run.paths["releases"], rid, checks)
        dep = {"id": rid, "company_id": run.cid, "task_id": t["id"], "status": "awaiting_approval" if pre["ok"] else "failed",
               "log": pre["log"], "folder": pre["folder"], "url": None, "test_ids": pre.get("test_ids", [])}
        run.store.put("deployment", rid, dep)
        run.event("deployment.created", "deployment", rid, {"stages": [x["stage"] for x in pre["log"]], "ok": pre["ok"]},
                  correlation_id=t["id"], actor="deployment", test_ids=pre.get("test_ids"))
        if not pre["ok"]:
            run.event("deployment.failed", "deployment", rid, {"stage": pre["log"][-1]["stage"]}, correlation_id=t["id"],
                      actor="deployment")
            return escalate(run, t, "The release failed before approval: " + pre["log"][-1]["stage"])
        extra["deployment_id"] = rid
        evidence.append(f"{len(pre.get('test_ids', []))} tests passed in the build, preview health and smoke passed")
        side = result.get("side_action")
        if isinstance(side, dict) and side:
            g = run.gateway(owner, t["id"], str(side.get("action_type") or ""), target=str(side.get("target") or ""))
            extra["side_action"] = {"summary": str(side.get("summary") or ""), "status": g["status"],
                                    "reason": g["policy"]["reason"]}
    g = run.gateway(owner, t["id"], action_type, target=t["id"])
    if g["status"] == "denied":
        return escalate(run, t, g["policy"]["reason"])
    pending = {"problem": result.get("problem") or t["title"], "recommendation": result.get("recommendation", ""),
               "confidence": result.get("confidence") or "medium", "cost": result.get("cost", ""),
               "what_would_change_this": result.get("what_would_change_this", ""), "evidence": evidence,
               "extra": extra, "action_type": action_type}
    if t.get("reviewed_by"):  # a team member's proposal reaches the founder through its cofounder
        t.update({"status": "LEAD_REVIEW", "pending_proposal": pending})
        run.save_task(t)
        return {"did": "to_cofounder", "task": t["id"], "reviewer": t["reviewed_by"]}
    return bring_to_founder(run, t, pending)


def door(run, t: dict) -> tuple[str, str]:
    """How hard a decision is to undo. A one-way door (going live, a rule on money or law, a rule whose subject is
    not known) is the founder's; a two-way door (a merge, which every test reruns and nothing is live until the
    founder approves going live; a product rule outside money and law) can be settled by the cofounder accountable
    for it."""
    if t["kind"] == "deploy":
        return "one_way", "customers see it the moment it is live"
    if t["kind"] == "review_merge":
        return "two_way", "a merge can be undone; every test reruns on main, and nothing is live until you approve going live"
    ids = set(t.get("requirement_ids") or [])
    areas = {r["area"] for r in (run.requirements() or {}).get("requirements", []) if r["id"] in ids}
    owner = (run.worker(t["owner_worker_id"]) or {}).get("role")
    if not areas or areas & {"finance", "legal"} or owner in ("CFO", "CCO"):
        return "one_way", "a rule on money or law, or one whose subject is not clear, binds the company"
    return "two_way", "a product rule can be changed later without cost"


def _settler(run, t: dict, endorsed_by: str | None) -> str | None:
    """The cofounder who may settle a decision: the one that reviewed and approved its team member's proposal, or the
    cofounder whose own proposal it is. A proposal its cofounder did not approve (a concern kept on record, a review
    that could not be read) goes to the founder."""
    if endorsed_by:
        w = run.worker(endorsed_by)
        return endorsed_by if w and w.get("tier") == "cofounder" else None
    if t.get("reviewed_by"):
        return None
    w = run.worker(t["owner_worker_id"])
    return w["id"] if w and w.get("tier") == "cofounder" else None


def bring_to_founder(run, t: dict, pending: dict, endorsed_by: str | None = None) -> dict:
    """The proposal becomes a decision for the founder, with the cofounder who endorsed it, when there is one. A
    decision that is easy to undo is settled by the cofounder accountable for it instead, when governance allows, and
    the founder is told: the founder's time goes to what cannot be undone."""
    owner = t["owner_worker_id"]
    extra = dict(pending.get("extra") or {})
    if endorsed_by:
        extra["endorsed_by"] = endorsed_by
    kind, why = door(run, t)
    extra["door"] = kind
    settler = _settler(run, t, endorsed_by)
    if kind == "two_way" and settler and project_settings.get(run.store)["cofounders_settle_reversible"]:
        return settle(run, t, pending, extra, settler, why)
    d = run.decision(t["kind"], problem=pending["problem"], recommendation=pending["recommendation"],
                     risk=t["risk_tier"], confidence=pending["confidence"], cost=pending["cost"],
                     evidence=pending["evidence"], change=pending["what_would_change_this"], task_id=t["id"],
                     action_type=pending["action_type"], source=owner, extra=extra)
    approval = run.send("Approval", {"recommendation": d["recommendation"], "evidence_refs": pending["evidence"],
                                     "cost": d["cost"], "confidence": d["confidence"],
                                     "what_would_change_this": d["what_would_change_this"]},
                        {"decision_id": d["id"], "from_worker": owner, "task_id": t["id"], "risk": t["risk_tier"]},
                        t["id"], owner)
    t.update({"status": "AWAITING_FOUNDER", "decision_id": d["id"], "approval_hash": approval["object_hash"],
              "pending_proposal": None})
    run.save_task(t)
    return {"did": "proposed", "task": t["id"], "decision": d["id"]}


def settle(run, t: dict, pending: dict, extra: dict, settler: str, why: str) -> dict:
    """A cofounder settles a decision that is easy to undo. It is on the record like the founder's, labelled as the
    cofounder's, and the founder is told instead of asked."""
    owner = t["owner_worker_id"]
    text = lambda v: v if isinstance(v, str) else "" if v is None else str(v)  # noqa: E731  a model's field may be anything
    pending = {**pending, "problem": text(pending.get("problem")) or t["title"],
               "recommendation": text(pending.get("recommendation"))}
    d = run.decision(t["kind"], problem=pending["problem"], recommendation=pending["recommendation"],
                     risk=t["risk_tier"], confidence=pending["confidence"], cost=pending["cost"],
                     evidence=pending["evidence"], change=pending["what_would_change_this"], task_id=t["id"],
                     action_type=pending["action_type"], source=owner, extra=dict(extra, settled_by=settler))
    who = run.worker(settler)
    d.update({"status": "approved", "outcome_label": "settled_by_cofounder", "labeled_by": settler, "in_digest": False,
              "labeled_at": now(), "resolved_by": settler, "resolved_at": now()})
    run.store.put("decision", d["id"], d)
    run.event("decision.approved", "decision", d["id"], {"kind": d["kind"], "outcome_label": d["outcome_label"],
              "task_id": t["id"], "by": settler}, actor=settler, actor_type="worker", correlation_id=t["id"])
    replacement.inform(run, "settled_by_cofounder", worker_id=settler, task_id=t["id"],
                       headline=f"{people.label(who)} approved: {t['title']}",
                       detail=f"{pending['recommendation'][:300]} Settled by {who.get('name') or people.seat(who)} "
                              f"because {why}. You can change it later.")
    t.update({"status": "APPROVED", "decision_id": d["id"], "pending_proposal": None})
    run.save_task(t)
    return {"did": "settled", "task": t["id"], "decision": d["id"], "by": settler}


def escalate(run, t: dict, why: str) -> dict:
    owner = t["owner_worker_id"]
    esc = run.send("Escalation", {"issue": why, "required_action": "Founder decides: retry the task or stop the run.",
                                  "severity": "SEV-2"}, {"raised_by": owner, "owner": "founder"}, t["id"], owner)
    d = run.decision("escalation", problem=why, recommendation="Retry the task once more with the failure as feedback.",
                     risk=t["risk_tier"], confidence="low", cost="one more attempt",
                     evidence=[f"escalation {esc['object_hash']}"], change="A fix that makes the checks pass.",
                     task_id=t["id"], source=owner, severity="SEV-2")
    t.update({"status": "FAILED", "failed_from": t["status"], "decision_id": d["id"]})
    run.save_task(t)
    run.event("task.failed", "task", t["id"], {"reason": why[:200]}, correlation_id=t["id"], actor=owner,
              actor_type="worker", protocol_hash=esc["object_hash"])
    return {"did": "escalated", "task": t["id"], "decision": d["id"]}


def answer(run, t: dict) -> dict:
    blocker = t["blocker"]
    who = blocker["needs_from"]
    if not who.startswith("w_"):  # nobody in the company can answer it: the founder is asked
        return escalate(run, t, f"No colleague can answer {t['owner_worker_id']}'s Blocker: "
                                f"{blocker.get('description', '')[:300]}")
    g = run.gateway(who, t["id"], "answer_blocker", target=t["id"])
    if g["status"] != "executed":
        return escalate(run, t, g["policy"]["reason"])
    content, usage = run.intel.answer_blocker(t, worker=who, objective=run.objective_ctx(), rules=run.rules(),
                                              blocker=blocker, artifact_index=artifact_index(run), persona=run.persona(who))
    run.record_call(t["id"], who, "answer_blocker", usage)
    if run.meta["frozen"]:
        return frozen_during_call(run, t)
    known = set(artifact_index(run))
    content["artifacts"] = [a for a in _as_list(content.get("artifacts")) if isinstance(a, str) and a in known]
    reply = run.send("Handoff", content, {"from_worker": who, "to_worker": t["owner_worker_id"], "task_id": t["id"]},
                     t["id"], who)
    _deliver_artifacts(run, t, reply["artifacts"])
    t["answers"] = t.get("answers", []) + [{"from": who, "acceptance_check": reply["acceptance_check"],
                                            "hash": reply["object_hash"]}]
    t["status"] = "ASSIGNED"
    run.save_task(t)
    n = run.count("blocker_cleared") + 1
    run.store.put("blocker_cleared", f"bc_{n}", {"task_id": t["id"], "by": who, "founder_involved": False})
    return {"did": "blocker_cleared", "task": t["id"], "by": who}


def _rework(run, t: dict, why: str, by: str, ref: str | None) -> None:
    """Structured rework: what failed, by which check, on which attempt, kept with the task."""
    t["rework_history"] = (t.get("rework_history") or []) + [{"attempt": t["attempts"], "by": by, "ref": ref,
                                                              "why": why[:300], "at": now()}]
    run.save_task(t)
    run.event("rework.created", "task", t["id"], {"attempt": t["attempts"], "by": by, "ref": ref,
              "why": why[:200]}, actor=by, correlation_id=t["id"])


def verify(run, t: dict) -> dict:
    owner = t["owner_worker_id"]
    r = verifier.verify(run, t)
    if r.get("integrity") is False:  # the bar moved after it was frozen: the founder decides, nothing is measured
        return escalate(run, t, f"{t['id']}: {r['feedback']}")
    if r["passed"]:
        t["verification_id"] = r["verification"]["id"]
        if t.get("reviewed_by"):  # checked by the platform; now its cofounder reviews it before it counts
            t["status"] = "LEAD_REVIEW"
            run.save_task(t)
            return {"did": "checked", "task": t["id"], "reviewer": t["reviewed_by"]}
        return accept(run, t)
    t["attempts"] += 1
    perf(run, owner, "reworks")
    if r["verdict"] == "REQUIRES_HUMAN":
        run.save_task(t)
        return replacement.evaluate(run, t, f"{t['id']} failed verification {t['attempts']} times: {r['feedback'][:200]}",
                                    forced=True)
    t.update({"status": "REWORK", "feedback": r["feedback"]})
    run.save_task(t)
    run.event("task.failed", "task", t["id"], {"attempt": t["attempts"], "rework": True,
              "verification": r["verification"]["id"]}, actor="verification", correlation_id=t["id"],
              test_ids=r["verification"]["test_ids"])
    _rework(run, t, r["feedback"], "verification", r["verification"]["id"])
    moved = replacement.check_thresholds(run, t)  # evidence, not only the third failure, can move the work
    if moved and moved["did"] in ("replaced", "rerouted"):
        return moved
    return {"did": "rework", "task": t["id"]}


def accept(run, t: dict, reviewer: str | None = None) -> dict:
    """The work counts: its files join the repository and the task is verified."""
    owner = t["owner_worker_id"]
    verifier.integrate(run, t)
    perf(run, owner, "verified")
    if t["attempts"] == 0 and not t.get("review_rounds"):
        perf(run, owner, "first_pass")
    t["status"] = "VERIFIED"
    run.save_task(t)
    v = run.store.get("verification", t.get("verification_id") or "") or {}
    run.event("task.verified", "task", t["id"], {"verification": v.get("id"), "attempt": v.get("attempt"),
              "reviewed_by": reviewer}, actor="verification", correlation_id=t["id"], test_ids=v.get("test_ids"))
    return {"did": "verified", "task": t["id"]}


def _review_material(run, t: dict) -> dict:
    """What the cofounder reviews: the files that passed the platform's checks, or the proposal for the founder."""
    if t.get("pending_proposal"):
        p = t["pending_proposal"]
        return {"proposal": {k: p[k] for k in ("problem", "recommendation", "evidence", "cost", "confidence",
                                                "what_would_change_this")}}
    out = run.workspace(t["owner_worker_id"], t["id"]) / "out"
    v = run.store.get("verification", t.get("verification_id") or "") or {}
    return {"files": {p.relative_to(out).as_posix(): p.read_text(encoding="utf-8", errors="replace")
                      for p in sorted(out.rglob("*")) if p.is_file()},
            "checks": f"The platform's checks passed: {v.get('method', 'its verifier')}."}


def lead_review(run, t: dict) -> dict:
    """The cofounder reviews its team member's work before it counts, or its proposal before it reaches the founder.
    It approves, or sends it back with what to change. After MAX_SEND_BACKS the platform's checks decide and the
    cofounder's last concern is kept on the record for the founder."""
    lead, owner = t["reviewed_by"], t["owner_worker_id"]
    g = run.gateway(lead, t["id"], "review_work", target=t["id"])
    if g["status"] != "executed":
        return _after_review(run, t, lead, "skipped", f"the review was not allowed: {g['policy']['reason']}")
    rounds = t.get("review_rounds", 0)
    producer, _ = controller.producer(run, t)
    run._tls.review_for = t["id"]  # an independent review where the policy asks for one (controller.reviewer)
    try:
        reviewer = run.intelligence_for(lead)
        run.event("review.started", "task", t["id"], {"by": lead, "round": rounds, "reviewer_intelligence": reviewer,
                  "producer_intelligence": producer, "independent": reviewer != producer}, actor=lead,
                  actor_type="worker", correlation_id=t["id"])
        content, usage = run.intel.review(t, worker=lead, objective=run.objective_ctx(), rules=run.rules(),
                                          owner=(run.worker(owner) or {}).get("title", owner),
                                          work=_review_material(run, t), persona=run.persona(lead), round_index=rounds)
    finally:
        run._tls.review_for = None
    run.record_call(t["id"], lead, "review", usage)
    if run.meta["frozen"]:
        return frozen_during_call(run, t)
    content = content if isinstance(content, dict) else {}
    verdict = str(content.get("verdict") or "").strip().lower()
    note = content.get("note") if isinstance(content.get("note"), str) else ""
    if verdict not in ("approve", "revise") or not note.strip():
        t["review_errors"] = t.get("review_errors", 0) + 1
        run.save_task(t)
        if t["review_errors"] < MAX_REVIEW_ERRORS:
            return {"did": "retry", "task": t["id"], "why": "the review needs a verdict (approve or revise) and a note"}
        return _after_review(run, t, lead, "skipped", "the cofounder's review could not be read twice in a row")
    t["review_errors"] = 0
    rec = run.send("Review", {"verdict": verdict, "note": note.strip()},
                   {"reviewed_by": lead, "owner": owner, "task_id": t["id"]}, t["id"], lead)
    t["reviews"] = t.get("reviews", []) + [{"by": lead, "verdict": verdict, "note": rec["note"],
                                           "hash": rec["object_hash"], "reviewer_intelligence": usage.get("model_id"),
                                           "independent": usage.get("model_id") != producer}]
    # the review is evidence about the producer; one by its own intelligence is not independent and counts little
    independent = usage.get("model_id") != producer
    controller.record_task_evidence(
        run, t, verified=verdict == "approve", verifier_kind="independent_intelligence" if independent else "self_review",
        failure=None if verdict == "approve" else attr.failure(attr.INTELLIGENCE, "the accountable cofounder sent it "
                                                               "back", rec["note"]),
        idempotency_key=f"review:{t['id']}:{rec['object_hash']}",
        extra={"source": "lead_review", "reviewer": lead, "reviewer_intelligence": usage.get("model_id"),
               "verification": {"verification_id": None, "method": "cofounder review", "independent": independent,
                                "verifier_kind": "independent_intelligence" if independent else "self_review",
                                "verifier_intelligence": usage.get("model_id"), "record_hash": None,
                                "test_ids_count": 0, "quality": controller.policies.body("verification")["quality"][
                                    "independent_intelligence" if independent else "self_review"]}})
    if verdict == "approve":
        return _after_review(run, t, lead, "approved", rec["note"])
    if rounds >= MAX_SEND_BACKS:  # the platform's checks decide; the concern stays on the record
        return _after_review(run, t, lead, "concern_recorded", rec["note"])
    t["review_rounds"] = rounds + 1
    perf(run, owner, "sent_back")
    title = (run.worker(lead) or {}).get("title", lead)
    t.update({"status": "REWORK" if t["kind"] in roles.FILE_TYPES else "ASSIGNED",
              "feedback": f"Your cofounder, the {title}, sent it back: {rec['note']}", "pending_proposal": None})
    run.save_task(t)
    _rework(run, t, rec["note"], lead, rec["object_hash"])
    run.event("task.sent_back", "task", t["id"], {"by": lead, "round": t["review_rounds"]}, actor=lead,
              actor_type="worker", correlation_id=t["id"], protocol_hash=rec["object_hash"])
    return {"did": "sent_back", "task": t["id"], "by": lead}


def _after_review(run, t: dict, lead: str, outcome: str, note: str) -> dict:
    """approved: the work counts, or the proposal goes to the founder, endorsed. skipped or concern_recorded: the
    same, on the platform's checks alone, and the record says so."""
    run.event("task.reviewed", "task", t["id"], {"by": lead, "outcome": outcome, "note": note[:300]}, actor=lead,
              actor_type="worker", correlation_id=t["id"])
    if outcome != "approved":
        t["review_concern"] = {"by": lead, "outcome": outcome, "note": note[:600]}
        run.save_task(t)
    if t.get("pending_proposal"):
        return bring_to_founder(run, t, t["pending_proposal"], endorsed_by=lead if outcome == "approved" else None)
    return accept(run, t, reviewer=lead if outcome == "approved" else None)


def execute_approved(run, t: dict) -> dict:
    """The founder approved a proposal: carry it out through the gateway, then verify the result."""
    d = run.store.get("decision", t["decision_id"])
    owner = t["owner_worker_id"]
    test_ids: list = []
    if t["kind"] == "decision":
        rule = d.get("edited", {}).get("recommendation") or d["recommendation"]
        mem = run.store.get("memory", "decided_rules") or {"rules": []}
        mem["rules"].append(rule)
        run.store.put("memory", "decided_rules", mem)
        doc = run.paths["integration"] / "docs" / "DECISIONS.md"
        doc.parent.mkdir(parents=True, exist_ok=True)
        with doc.open("a", encoding="utf-8") as fh:
            by = "you" if d.get("resolved_by") == "founder" else people.label(run.worker(d["resolved_by"]))
            fh.write(f"## {t['title']} ({d['id']}, {d['outcome_label']} by {by})\n\n{rule}\n\n")
        aid = f"{t['id']}/DECISIONS.md"
        run.store.put("artifact", aid, {"id": aid, "task_id": t["id"], "path": "docs/DECISIONS.md",
                                        "hash": digest(doc.read_bytes()), "by": owner})
        who = "founder" if d.get("resolved_by") == "founder" else d.get("resolved_by")
        method = "your review (MEDIUM)" if who == "founder" else "settled by the accountable cofounder (two-way door)"
        checks, reviewer = {"decision": d["id"], "label": d["outcome_label"]}, who
    elif t["kind"] == "review_merge":
        g = run.gateway(owner, t["id"], "merge_to_main", target="main", approval=d["id"])
        if g["status"] != "executed":
            return escalate(run, t, "merge refused: " + g["policy"]["reason"])
        g = run.gateway(owner, t["id"], "run_tests", target="main", cwd=run.paths["main"])
        report = g["report"]
        test_ids = [x["id"] for x in report["tests"]]
        if not report["passed"]:
            verifier.escaped(run, report["failed"], "main after the merge", t["id"])
            return escalate(run, t, "main fails its tests after the merge")
        method, checks, reviewer = "full test run on main", {"ran": report["ran"]}, "verification"
    else:
        g = run.gateway(owner, t["id"], "deploy_production", target="production", approval=d["id"])
        if g["status"] != "executed":
            return escalate(run, t, "deploy refused: " + g["policy"]["reason"])
        dep = run.store.get("deployment", d["extra"]["deployment_id"])
        res = deploy.deploy_live(Path(dep["folder"]), run.paths["live"], verifier.smoke_checks(Path(dep["folder"])),
                                 run.live_proc)
        dep.update({"log": dep["log"] + res["log"], "status": "live" if res["ok"] else "rolled_back", "url": res["url"],
                    "approved_by": "founder"})
        run.store.put("deployment", dep["id"], dep)
        run.live_proc = res["proc"]
        if not res["ok"]:
            run.event("deployment.failed", "deployment", dep["id"], {"stage": "SMOKE_TEST"}, correlation_id=t["id"],
                      actor="deployment")
            run.event("deployment.rolled_back", "deployment", dep["id"], {}, correlation_id=t["id"], actor="deployment")
            verifier.escaped(run, [], "live health or smoke check", t["id"])
            return escalate(run, t, "the live release failed its health or smoke check and was rolled back")
        run.event("deployment.verified", "deployment", dep["id"], {"url_port": res["url"].rsplit(":", 1)[-1],
                  "stages": [x["stage"] for x in dep["log"]]}, correlation_id=t["id"], actor="deployment")
        test_ids = dep.get("test_ids", [])
        method, checks, reviewer = "health check and smoke test on the live URL", {"url": res["url"]}, "verification"
    v = verifier.record(run, t, verdict="VERIFIED", method=method, checks=checks, test_ids=test_ids, reviewer=reviewer,
                        seconds=None)
    verifier.outcome(run, t, True, verification=v)
    t["status"] = "VERIFIED"
    run.save_task(t)
    perf(run, owner, "verified")
    if t["attempts"] == 0:
        perf(run, owner, "first_pass")
    run.event("task.verified", "task", t["id"], {"verification": v["id"]}, actor="verification", correlation_id=t["id"],
              test_ids=test_ids)
    return {"did": "verified", "task": t["id"]}


def after_proposal(run, d: dict, action: str) -> None:
    t = run.task(d["task_id"])
    if action == "approve":
        t["status"] = "APPROVED"
    else:
        # a person's verdict on the proposal: a rejection is evidence about the intelligence that wrote it; asking
        # for more evidence is a human request, not a failure
        cause = attr.failure(attr.INTELLIGENCE, "the founder rejected the proposal", d.get("note") or "") \
            if action == "reject" else attr.failure("human", "the founder asked for more evidence", d.get("note") or "")
        controller.record_task_evidence(run, t, verified=False if action == "reject" else None, failure=cause,
                                        verifier_kind="human", idempotency_key=f"founder:{d['id']}",
                                        extra={"source": "founder_decision", "autonomy": "human_rejected"
                                               if action == "reject" else "autonomous"})
        t["attempts"] += 1
        t.update({"status": "REWORK", "feedback": f"Founder: {d['outcome_label']}. {d.get('note', '')}".strip()})
        run.save_task(t)
        _rework(run, t, t["feedback"], "founder", d["id"])
        return
    run.save_task(t)


def after_escalation(run, d: dict, action: str) -> None:
    t = run.task(d["task_id"])
    if action == "approve":
        back = t.get("failed_from")
        if back not in ("PLANNED", "BLOCKED", "LEAD_REVIEW"):
            back = "REWORK" if t["kind"] in roles.FILE_TYPES else "ASSIGNED"
        t.update({"status": back, "attempts": 0, "cut_offs": 0, "human_retry": True})  # human-directed retry
        run.save_task(t)
    else:
        run.set_meta(phase="stopped", notice=f"You stopped the run at {t['id']}.")
        objective.transition(run, "OBJECTIVE_CANCELLED", f"the founder stopped the run at {t['id']}", by="founder")
