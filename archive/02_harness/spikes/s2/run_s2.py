#!/usr/bin/env python3
"""S2: what does coordination in a four worker organization cost per task?

Written 26 September 2026 by the acting CTO, before any S2 run. Read
spikes/s2/RULINGS.md first: it fixes the meaning of the bar and of every
number this file reports.

What one task looks like here
1. Assignment. The PM assigns engineering tasks by writing a Handoff (a model
   call). The orchestrator assigns PM and CTO tasks with a fixed Handoff (no
   model call). The Handoff names which earlier artifacts the worker may see.
2. Work. The owner gets its role, the company context, the Handoff and only the
   artifacts the Handoff lists. It returns a result Handoff or a Blocker.
3. Blocker. The worker named in needs_from answers with a Handoff (a model
   call). The owner then gets one more try. Blocked twice means the task ends
   blocked and goes to the founder.
4. Review. MEDIUM work is reviewed by an independent worker (CTO, or PM when the
   CTO did the work), who writes an Approval for the founder. Under D-17 the
   founder reviews every MEDIUM action, so founder_touched is true.

Every message between workers is a protocol object checked against the
templates in 02_harness/protocols. Routing fields (from, to, task id) are set
by the runner, never taken from model text. Nothing here is free chat.

Refusals
No model: exit 2, nothing written. Any model error: stop, write s2_unrun.json,
exit 3. Token counts estimated from a shell command: the run is a wiring test,
written to s2_wiring_test.json, never to s2_report.json.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPIKES = HERE.parent
HARNESS = SPIKES.parent
sys.path.insert(0, str(SPIKES))
sys.path.insert(0, str(HARNESS / "kit"))

import model_adapter  # noqa: E402
from protocol import stamp  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
ESTIMATE_FILE = SPIKES / "S2_ESTIMATE.md"
PROTOCOL_DIR = HARNESS / "protocols"
RUNNER_VERSION = "s2_runner_v1_26sep2026"
MAX_OUT_TOKENS = 4000
TOKEN_CAP = 600_000
ENVELOPE = {"protocol", "protocol_version", "created_at", "correlation_id", "object_hash"}
ROUTING = {"from_worker", "to_worker", "task_id", "raised_by", "decision_id"}

# Content fields a model must fill. Routing and envelope fields are set by the runner.
REQUIRED_CONTENT = {
    "Handoff": ["acceptance_check"],
    "Blocker": ["category", "description", "needs_from"],
    "Approval": ["recommendation", "confidence", "what_would_change_this"],
}


class ModelUnavailable(Exception):
    pass


class CapReached(Exception):
    pass


def now() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def load_templates() -> dict:
    out = {}
    for name in ("handoff", "blocker", "approval", "escalation"):
        data = json.loads((PROTOCOL_DIR / f"{name}.json").read_text(encoding="utf-8"))
        out[data["protocol"]] = data
    return out


def parse_estimate(text: str) -> dict:
    def grab(pattern: str):
        m = re.search(pattern, text, re.I)
        return float(m.group(1).replace(",", "")) if m else None

    return {
        "tokens_low": grab(r"Tokens per LOW risk task:\s*([\d,]+)"),
        "tokens_medium": grab(r"Tokens per MEDIUM risk task:\s*([\d,]+)"),
        "tokens_message": grab(r"Tokens per protocol message:\s*([\d,]+)"),
        "minutes_low": grab(r"Wall minutes per LOW task:\s*([\d,]+)"),
        "minutes_medium": grab(r"Wall minutes per MEDIUM task:\s*([\d,]+)"),
    }


def parse_json(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.S)
    if fenced:
        raw = fenced.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None


class Org:
    def __init__(self, context: dict, plan: dict, templates: dict):
        self.ctx = context
        self.plan = plan
        self.templates = templates
        self.calls: list[dict] = []
        self.messages: list[dict] = []
        self.artifacts: dict[str, dict] = {}
        self.tokens_total = 0

    # ---- model access -------------------------------------------------
    def call(self, task_id: str, worker: str, purpose: str, prompt: str) -> dict | None:
        """One model call. Returns parsed JSON or None. One format retry."""
        parsed = None
        for attempt in (1, 2):
            text = prompt if attempt == 1 else (
                prompt + "\n\nYour last reply was not one valid JSON object. "
                "Reply again with only the JSON object, nothing before or after it."
            )
            out = model_adapter.complete(text, max_tokens=MAX_OUT_TOKENS)
            if out.get("error"):
                raise ModelUnavailable(out["error"])
            parsed = parse_json(out["text"])
            self.tokens_total += out["tokens_in"] + out["tokens_out"]
            self.calls.append(
                {
                    "task_id": task_id,
                    "worker": worker,
                    "purpose": purpose,
                    "attempt": attempt,
                    "tokens_in": out["tokens_in"],
                    "tokens_out": out["tokens_out"],
                    "latency_s": out["latency_s"],
                    "estimated": out["estimated"],
                    "parsed": isinstance(parsed, dict),
                }
            )
            if self.tokens_total > TOKEN_CAP:
                raise CapReached(f"token cap {TOKEN_CAP} passed after {len(self.calls)} calls")
            if isinstance(parsed, dict):
                return parsed
        return None

    # ---- protocol objects ---------------------------------------------
    def make(self, kind: str, content: dict | None, routing: dict, task_id: str) -> tuple[dict, bool]:
        """Build a protocol object from model content plus runner routing."""
        template = self.templates[kind]
        obj = {k: v for k, v in template.items() if k not in ENVELOPE}
        structured = isinstance(content, dict)
        if structured:
            for key in template:
                if key in ENVELOPE or key in ROUTING:
                    continue
                if key in content:
                    obj[key] = content[key]
            for key in REQUIRED_CONTENT.get(kind, []):
                if not str(obj.get(key, "")).strip():
                    structured = False
        obj.update(routing)
        obj["protocol"] = kind
        stamped = stamp(obj, correlation_id=task_id)
        self.messages.append({"object": stamped, "structured": structured})
        return stamped, structured

    # ---- prompts ------------------------------------------------------
    def company_layer(self) -> str:
        rules = "\n".join(f"* {r}" for r in self.ctx["decided_rules"])
        return f"Company objective: {self.ctx['objective']}\nDecided rules:\n{rules}\n"

    def role_layer(self, worker: str) -> str:
        w = self.ctx["workers"][worker]
        return (
            f"You are {w['role']} ({worker}) in a four worker organization: CTO, PM, "
            f"Engineer A, Engineer B. You {w['does']}. Your authority: {w['authority']}.\n"
        )

    def artifact_index(self) -> str:
        if not self.artifacts:
            return "No artifacts exist yet."
        lines = []
        for aid, a in self.artifacts.items():
            first = " ".join(str(a["content"]).split())[:110]
            lines.append(f"{aid} (by {a['by']}, task {a['task_id']}): {first}")
        return "\n".join(lines)

    def artifact_bodies(self, ids) -> str:
        parts = []
        for aid in ids or []:
            a = self.artifacts.get(str(aid))
            if a:
                parts.append(f"--- artifact {aid} ---\n{a['content']}")
        return "\n".join(parts) if parts else "No artifacts were handed to you."

    # ---- one task -----------------------------------------------------
    def assign(self, task: dict, ws_id: str) -> tuple[dict, bool, int]:
        owner = task["owner"]
        if owner in ("w_pm", "w_cto"):
            prior = [aid for aid, a in self.artifacts.items() if a["workstream"] == ws_id]
            content = {
                "artifacts": prior,
                "context_ref": f"workstream {ws_id}",
                "acceptance_check": task["ask"],
            }
            obj, ok = self.make(
                "Handoff", content,
                {"from_worker": "orchestrator", "to_worker": owner, "task_id": task["id"]}, task["id"],
            )
            return obj, ok, 0
        prompt = (
            self.role_layer("w_pm") + self.company_layer()
            + f"\nAssign task {task['id']} ({task['risk']} risk) to {owner}.\n"
            + f"Task: {task['ask']}\n\nArtifacts that exist:\n{self.artifact_index()}\n\n"
            + "Write the Handoff. List in artifacts only the artifact ids the engineer truly needs. "
            + "Put every closed list or rule the engineer must not invent into acceptance_check.\n"
            + 'Return one JSON object: {"artifacts": [ids], "context_ref": "...", "acceptance_check": "..."}'
        )
        content = self.call(task["id"], "w_pm", "assign", prompt)
        obj, ok = self.make(
            "Handoff", content, {"from_worker": "w_pm", "to_worker": owner, "task_id": task["id"]}, task["id"]
        )
        return obj, ok, 1

    def work(self, task: dict, handoff: dict, extra: dict | None) -> tuple[str, dict | None]:
        owner = task["owner"]
        more = ""
        ids = list(handoff.get("artifacts") or [])
        if extra:
            more = f"\nAnswer to your Blocker:\n{json.dumps({k: extra.get(k) for k in ('acceptance_check', 'context_ref', 'artifacts')}, indent=1)}\n"
            ids += [a for a in (extra.get("artifacts") or []) if a not in ids]
        prompt = (
            self.role_layer(owner) + self.company_layer()
            + f"\nYour Handoff for task {task['id']} ({task['risk']} risk):\n"
            + json.dumps({k: handoff.get(k) for k in ("from_worker", "acceptance_check", "context_ref", "artifacts")}, indent=1)
            + f"\n\nArtifacts handed to you:\n{self.artifact_bodies(ids)}\n{more}\n"
            + "Do the task. If a fact you need is missing and you would have to guess it, do not guess: raise a Blocker.\n"
            + "Return one JSON object, either\n"
            + '{"result": "done", "output": "<the complete work product>", "acceptance_check": "<how the receiver can check it>"}\n'
            + "or\n"
            + '{"result": "blocked", "category": "missing_input", "description": "<what is missing>", "needs_from": "w_pm or w_cto"}'
        )
        content = self.call(task["id"], owner, "work", prompt)
        if isinstance(content, dict) and content.get("result") == "blocked":
            return "blocked", content
        return "done", content

    def answer_blocker(self, task: dict, blocker: dict) -> tuple[dict, bool]:
        who = blocker.get("needs_from") if blocker.get("needs_from") in ("w_pm", "w_cto") else "w_pm"
        prompt = (
            self.role_layer(who) + self.company_layer()
            + f"\n{task['owner']} raised a Blocker on task {task['id']}: {blocker.get('description')}\n"
            + f"Task: {task['ask']}\n\nArtifacts that exist:\n{self.artifact_index()}\n\n"
            + "Clear the Blocker with facts from the objective, the decided rules or the artifacts. Do not invent product decisions.\n"
            + 'Return one JSON object: {"artifacts": [ids], "context_ref": "...", "acceptance_check": "<the missing facts>"}'
        )
        content = self.call(task["id"], who, "answer_blocker", prompt)
        return self.make(
            "Handoff", content, {"from_worker": who, "to_worker": task["owner"], "task_id": task["id"]}, task["id"]
        )

    def review(self, task: dict, output_ids: list[str]) -> tuple[dict, bool]:
        reviewer = "w_pm" if task["owner"] == "w_cto" else "w_cto"
        prompt = (
            self.role_layer(reviewer) + self.company_layer()
            + f"\nReview task {task['id']} ({task['risk']} risk) by {task['owner']}.\nTask: {task['ask']}\n\n"
            + f"Work product:\n{self.artifact_bodies(output_ids)}\n\n"
            + "You did not do this work. Check it against the objective and the decided rules. "
            + "Write an Approval for the founder.\n"
            + 'Return one JSON object: {"recommendation": "approve or reject, and why", "evidence_refs": [ids], '
            + '"cost": "...", "confidence": "low, medium or high", "what_would_change_this": "..."}'
        )
        content = self.call(task["id"], reviewer, "review", prompt)
        return self.make(
            "Approval", content,
            {"decision_id": f"dec_{task['id']}", "from_worker": reviewer, "to_worker": "founder",
             "task_id": task["id"], "risk": task["risk"]},
            task["id"],
        )

    def run_task(self, task: dict, ws_id: str) -> dict:
        started = time.time()
        first_msg = len(self.messages)
        first_call = len(self.calls)
        founder = task["risk"] == "MEDIUM"
        handoff, ok, _ = self.assign(task, ws_id)
        structured = ok
        state, content = self.work(task, handoff, None)
        blocker_rounds = 0
        if state == "blocked":
            blocker_rounds = 1
            blk, ok_b = self.make(
                "Blocker", content,
                {"raised_by": task["owner"], "task_id": task["id"]}, task["id"],
            )
            structured = structured and ok_b
            answer, ok_a = self.answer_blocker(task, blk)
            structured = structured and ok_a
            state, content = self.work(task, handoff, answer)
            if state == "blocked":
                blk2, ok_b2 = self.make(
                    "Blocker", content, {"raised_by": task["owner"], "task_id": task["id"]}, task["id"]
                )
                structured = structured and ok_b2
                founder = True
        output_ids: list[str] = []
        if state == "done":
            text = content.get("output") if isinstance(content, dict) else None
            if isinstance(text, (dict, list)):
                text = json.dumps(text, indent=1)
            aid = f"{task['id']}_out"
            self.artifacts[aid] = {"task_id": task["id"], "by": task["owner"], "workstream": ws_id, "content": text or ""}
            output_ids = [aid]
            to = "w_pm" if task["owner"] != "w_pm" else "orchestrator"
            result, ok_r = self.make(
                "Handoff",
                {"artifacts": output_ids, "context_ref": f"result of {task['id']}",
                 "acceptance_check": (content or {}).get("acceptance_check", "") if isinstance(content, dict) else ""},
                {"from_worker": task["owner"], "to_worker": to, "task_id": task["id"]}, task["id"],
            )
            structured = structured and ok_r and bool(text)
            if task["risk"] == "MEDIUM":
                _, ok_v = self.review(task, output_ids)
                structured = structured and ok_v
        task_calls = self.calls[first_call:]
        msgs = self.messages[first_msg:]
        return {
            "task_id": task["id"],
            "workstream": ws_id,
            "owner": task["owner"],
            "risk": task["risk"],
            "status": state,
            "protocol_count": len(msgs),
            "model_calls": len(task_calls),
            "tokens_in": sum(c["tokens_in"] for c in task_calls),
            "tokens_out": sum(c["tokens_out"] for c in task_calls),
            "tokens_total": sum(c["tokens_in"] + c["tokens_out"] for c in task_calls),
            "wall_minutes": round((time.time() - started) / 60.0, 3),
            "retries": sum(1 for c in task_calls if c["attempt"] == 2) + blocker_rounds,
            "blocker_rounds": blocker_rounds,
            "founder_touched": founder,
            "structured": structured,
        }


def median(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 3) if values else None


def ratio_check(measured, target):
    if measured is None or target in (None, 0):
        return None
    r = measured / target
    return {"measured": measured, "estimate": target, "ratio": round(r, 3), "within_2x": 0.5 <= r <= 2.0}


def main() -> int:
    model = model_adapter.resolve()
    if model is None:
        print(json.dumps({"spike": "S2", "scored": False,
                          "reason": "No model. Set OPENAI_API_KEY or ANTHROPIC_API_KEY.",
                          "note": "An unrun spike is not a failed spike."}, indent=2))
        return 2
    if not ESTIMATE_FILE.exists():
        print("S2_ESTIMATE.md is missing. The estimate must exist before scoring.")
        return 2
    estimate = parse_estimate(ESTIMATE_FILE.read_text(encoding="utf-8"))
    plan = json.loads((HERE / "tasks.json").read_text(encoding="utf-8"))
    context = json.loads((HERE / "company_context.json").read_text(encoding="utf-8"))
    org = Org(context, plan, load_templates())
    rows = []
    started_at = now()
    try:
        for ws in plan["workstreams"]:
            for task in ws["tasks"]:
                rows.append(org.run_task(task, ws["id"]))
                print(f"  {task['id']} {rows[-1]['status']} tokens {rows[-1]['tokens_total']}", flush=True)
    except ModelUnavailable as exc:
        unrun = {"spike": "S2", "scored": False, "reason": "A model call failed. Unrun, not failed.",
                 "error": str(exc), "model": model["label"], "tasks_finished": len(rows), "at": now()}
        (HERE / "s2_unrun.json").write_text(json.dumps(unrun, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(unrun, indent=2))
        return 3
    except CapReached as exc:
        rows.append({"task_id": "cap", "status": "stopped", "note": str(exc)})

    estimated = any(c["estimated"] for c in org.calls)
    capped = any(r.get("status") == "stopped" for r in rows)
    done_rows = [r for r in rows if r.get("status") in ("done", "blocked")]
    low = [r for r in done_rows if r["risk"] == "LOW"]
    med = [r for r in done_rows if r["risk"] == "MEDIUM"]
    coord = [c["tokens_in"] + c["tokens_out"] for c in org.calls if c["purpose"] in ("assign", "answer_blocker", "review")]
    measured = {
        "tokens_low": median([r["tokens_total"] for r in low]),
        "tokens_medium": median([r["tokens_total"] for r in med]),
        "tokens_message": median(coord),
        "minutes_low": median([r["wall_minutes"] for r in low]),
        "minutes_medium": median([r["wall_minutes"] for r in med]),
    }
    checks = {k: ratio_check(measured[k], estimate.get(k)) for k in measured}
    all_structured = all(r.get("structured") for r in done_rows) and all(m["structured"] for m in org.messages)
    lines_ok = all(c and c["within_2x"] for c in checks.values())
    met_bar = (not capped) and len(done_rows) == 12 and all_structured and lines_ok
    report = {
        "spike": "S2",
        "scored": True,
        "runner_version": RUNNER_VERSION,
        "model": model["label"],
        "provider": model["kind"],
        "token_source": "estimated" if estimated else "measured",
        "counts_as_measured_result": not estimated,
        "started_at": started_at,
        "finished_at": now(),
        "tasks": len(done_rows),
        "tasks_blocked": sum(1 for r in done_rows if r["status"] == "blocked"),
        "founder_touched": sum(1 for r in done_rows if r["founder_touched"]),
        "model_calls": len(org.calls),
        "tokens_total": org.tokens_total,
        "protocol_messages": len(org.messages),
        "all_messages_structured": all_structured,
        "stopped_at_token_cap": capped,
        "estimate": estimate,
        "measured_median": measured,
        "checks": checks,
        "bar": "Every estimate line within a factor of 2 (0.5x to 2x), all coordination as structured protocol objects, 12 tasks. See RULINGS.md.",
        "met_bar": met_bar,
        "context_only_upper_bound": {k: (c["ratio"] <= 2.0 if c else None) for k, c in checks.items()},
        "rows": rows,
        "calls": org.calls,
    }
    messages = {"messages": org.messages, "artifacts": org.artifacts}
    if estimated:
        report["met_bar"] = None
        report["note"] = "Wiring test. Token counts were estimated from characters. This is not an S2 result."
        (HERE / "s2_wiring_test.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (HERE / "s2_wiring_messages.json").write_text(json.dumps(messages, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k: report[k] for k in ("token_source", "tasks", "protocol_messages", "all_messages_structured", "note")}, indent=2))
        print("wrote", HERE / "s2_wiring_test.json")
        return 4
    report["note"] = "This is the S2 result. Token counts came from the provider API."
    (HERE / "s2_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (HERE / "s2_messages.json").write_text(json.dumps(messages, indent=2) + "\n", encoding="utf-8")
    stale = HERE / "s2_unrun.json"
    if stale.exists():
        stale.unlink()
    summary = {k: report[k] for k in ("model", "tasks", "tokens_total", "measured_median", "met_bar", "all_messages_structured")}
    print(json.dumps(summary, indent=2))
    print("wrote", HERE / "s2_report.json")
    return 0 if met_bar else 1


if __name__ == "__main__":
    sys.exit(main())
