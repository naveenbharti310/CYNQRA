"""Intelligence sources. Book 0 section 10: a worker's identity stays when its intelligence changes.

ScriptedSource  demo mode. Every word comes from scenarios/<id>/scenario.json, and the
                product labels it. Code it hands over is real and gets tested for real.
ModelSource     live mode. Every call goes through model_adapter (ADR-4), the same
                adapter the spikes use. A model error stops the step; nothing is invented.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import model_adapter

HERE = Path(__file__).resolve().parent
SCENARIOS = HERE.parent / "scenarios"

KIND_TIER = {"spec": "LOW", "decision": "MEDIUM", "code": "LOW", "review_merge": "MEDIUM", "deploy": "HIGH"}
KIND_OWNERS = {"spec": {"w_pm"}, "decision": {"w_pm"}, "code": {"w_eng_a", "w_eng_b"},
               "review_merge": {"w_cto"}, "deploy": {"w_cto"}}
SCRIPTED_UNITS_PER_CALL = 3


class IntelligenceError(RuntimeError):
    """The source could not answer. The step stops; it is never papered over."""


def _parse_json(text: str):
    raw = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.S)
    if fenced:
        raw = fenced.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def validate_plan(plan: dict) -> dict:
    """The platform owns the rubric: a kind's risk tier and owner are not the model's call."""
    if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list) or not plan["tasks"]:
        raise IntelligenceError("plan has no tasks")
    ids = set()
    kinds = []
    for t in plan["tasks"]:
        for key in ("id", "workstream_id", "kind", "owner_worker_id", "title"):
            if not str(t.get(key) or "").strip():
                raise IntelligenceError(f"task is missing {key}")
        if t["kind"] not in KIND_TIER:
            raise IntelligenceError(f"unknown task kind {t['kind']}")
        if t["owner_worker_id"] not in KIND_OWNERS[t["kind"]]:
            raise IntelligenceError(f"{t['id']}: {t['kind']} cannot be owned by {t['owner_worker_id']}")
        t["risk_tier"] = KIND_TIER[t["kind"]]
        for dep in t.get("dependencies") or []:
            if dep not in ids:
                raise IntelligenceError(f"{t['id']} depends on {dep}, which is not an earlier task")
        ids.add(t["id"])
        kinds.append(t["kind"])
        t.setdefault("inputs", "")
        t.setdefault("expected_output", "")
        t.setdefault("tools", [])
        t.setdefault("budget", 10)
        t.setdefault("deadline_day", 1)
        t.setdefault("verification_method", "")
        t.setdefault("dependencies", [])
    for kind, n in (("review_merge", 1), ("deploy", 1)):
        if kinds.count(kind) != n:
            raise IntelligenceError(f"plan needs exactly {n} {kind} task")
    if kinds[-1] != "deploy":
        raise IntelligenceError("deploy must be the last task")
    if "code" not in kinds:
        raise IntelligenceError("plan has no code task")
    ws = plan.get("workstreams") or []
    known = {w.get("id") for w in ws}
    for t in plan["tasks"]:
        if t["workstream_id"] not in known:
            ws.append({"id": t["workstream_id"], "name": t["workstream_id"]})
            known.add(t["workstream_id"])
    plan["workstreams"] = ws
    return plan


class ScriptedSource:
    kind = "scripted"

    def __init__(self, scenario_id: str = "candidate_tracker"):
        self.dir = SCENARIOS / scenario_id
        self.data = json.loads((self.dir / "scenario.json").read_text(encoding="utf-8"))
        self.label = f"scripted, demo ({scenario_id})"

    def _usage(self) -> dict:
        return {"tokens_in": 0, "tokens_out": 0, "estimated": True, "label": self.label, "latency_s": 0.0,
                "units": SCRIPTED_UNITS_PER_CALL}

    def _resolve(self, obj):
        if isinstance(obj, str) and obj.startswith("@files/"):
            return (self.dir / obj[1:]).read_text(encoding="utf-8")
        if isinstance(obj, dict):
            return {k: self._resolve(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._resolve(v) for v in obj]
        return obj

    def structure_objective(self, messy: str) -> tuple[dict, dict]:
        out = json.loads(json.dumps(self.data["objective"]))
        if messy.strip() != self.data["messy"].strip():
            out["notice"] = ("Demo mode only knows its prepared scenario, so it returned that objective. "
                             "Switch to live mode to build your own.")
        return out, self._usage()

    def plan(self, objective: dict) -> tuple[dict, dict]:
        return validate_plan(json.loads(json.dumps(self.data["plan"]))), self._usage()

    def assign(self, task: dict, **_) -> tuple[dict, dict]:
        preset = self.data.get("assign", {}).get(task["id"])
        if preset is None:
            raise IntelligenceError(f"scenario has no assignment for {task['id']}")
        return json.loads(json.dumps(preset)), self._usage()

    def work(self, task: dict, call_index: int = 0, **_) -> tuple[dict, dict]:
        """call_index is how many times this task has already been worked; the engine persists it."""
        items = self.data.get("work", {}).get(task["id"])
        if not items:
            raise IntelligenceError(f"scenario has no work for {task['id']}")
        return self._resolve(items[min(call_index, len(items) - 1)]), self._usage()

    def answer_blocker(self, task: dict, **_) -> tuple[dict, dict]:
        preset = self.data.get("answer_blocker", {}).get(task["id"])
        if preset is None:
            raise IntelligenceError(f"scenario has no Blocker answer for {task['id']}")
        return json.loads(json.dumps(preset)), self._usage()


ROLE_TEXT = {
    "w_cto": "You are the CTO worker. You review work against the objective, decide the technical approach and propose merges and deploys. You never deploy or message anyone yourself.",
    "w_pm": "You are the PM worker. You write specs and acceptance checks, plan and assign tasks, and answer Blockers from the objective and decided rules. You never write product code.",
    "w_eng_a": "You are Engineer A. You write Python and unittest tests inside your own workspace only.",
    "w_eng_b": "You are Engineer B. You write Python and unittest tests inside your own workspace only.",
}

DELIVERY_CONTRACT = ("The product is a Python standard library web app: app.py serves on the port in the PORT "
                     "environment variable and answers GET /health with 200. Tests are unittest files named "
                     "test_*.py that pass with `python -m unittest discover`. No third party packages.")


class ModelSource:
    kind = "model"

    def __init__(self):
        resolved = model_adapter.resolve()
        if resolved is None:
            raise IntelligenceError("Live mode needs ANTHROPIC_API_KEY or OPENAI_API_KEY in the environment.")
        self.label = resolved["label"]
        self.prompt_v2 = (HERE / "objective_prompt.txt").read_text(encoding="utf-8")

    def _call(self, prompt: str, max_tokens: int = 4000) -> tuple[dict, dict]:
        out = model_adapter.complete(prompt, max_tokens=max_tokens)
        if out.get("error"):
            raise IntelligenceError(out["error"])
        data = _parse_json(out["text"])
        if not isinstance(data, dict):
            out2 = model_adapter.complete(prompt + "\n\nReply with only one JSON object.", max_tokens=max_tokens)
            if out2.get("error"):
                raise IntelligenceError(out2["error"])
            data = _parse_json(out2["text"])
            out["tokens_in"] += out2["tokens_in"]
            out["tokens_out"] += out2["tokens_out"]
        if not isinstance(data, dict):
            raise IntelligenceError("model did not return a JSON object")
        units = max(1, -(-(out["tokens_in"] + out["tokens_out"]) // 1000))
        return data, {"tokens_in": out["tokens_in"], "tokens_out": out["tokens_out"], "estimated": out["estimated"],
                      "label": out.get("model", self.label), "latency_s": out.get("latency_s", 0), "units": units}

    @staticmethod
    def _ctx(objective: dict, rules: list[str]) -> str:
        fields = {k: objective.get(k, "") for k in ("product", "target_customer", "primary_outcome", "business_outcome",
                                                     "success_criteria", "constraints", "priorities")}
        r = "\n".join(f"* {x}" for x in rules) or "* none yet"
        return f"Confirmed objective:\n{json.dumps(fields, indent=1)}\nDecided rules:\n{r}\n"

    def structure_objective(self, messy: str) -> tuple[dict, dict]:
        data, usage = self._call(self.prompt_v2 + messy + "\n", max_tokens=1500)
        return data, usage

    def plan(self, objective: dict) -> tuple[dict, dict]:
        prompt = (ROLE_TEXT["w_pm"] + "\n" + self._ctx(objective, []) + "\n" + DELIVERY_CONTRACT + "\n\n"
                  "Plan the work for the fixed organization: w_cto, w_pm, w_eng_a, w_eng_b. Use only these task kinds:\n"
                  "spec (owner w_pm): spec.md and acceptance.md.\n"
                  "decision (owner w_pm): exactly the one product rule the objective leaves open, for the founder.\n"
                  "code (owner w_eng_a or w_eng_b): 2 or 3 tasks, each producing Python files and test_*.py.\n"
                  "review_merge (owner w_cto): exactly one, after all code tasks.\n"
                  "deploy (owner w_cto): exactly one, the last task.\n"
                  "Ids t_01, t_02 and so on. dependencies may only name earlier tasks.\n"
                  'Return JSON: {"workstreams": [{"id", "name"}], "tasks": [{"id", "workstream_id", "kind", '
                  '"owner_worker_id", "title", "inputs", "expected_output", "dependencies", "tools", "budget", '
                  '"deadline_day", "verification_method"}]}')
        data, usage = self._call(prompt, max_tokens=3000)
        return validate_plan(data), usage

    def assign(self, task: dict, objective: dict, rules: list[str], artifact_index: list[str], **_) -> tuple[dict, dict]:
        prompt = (ROLE_TEXT["w_pm"] + "\n" + self._ctx(objective, rules) + "\n" + DELIVERY_CONTRACT + "\n\n"
                  f"Assign task {task['id']} ({task['title']}) to {task['owner_worker_id']}. Expected output: "
                  f"{task['expected_output']}.\nArtifacts that exist: {json.dumps(artifact_index)}\n"
                  "List only the artifacts the engineer needs. Put every closed list or rule they must not invent "
                  "into acceptance_check.\n"
                  'Return JSON: {"artifacts": [ids], "context_ref": "...", "acceptance_check": "..."}')
        return self._call(prompt, max_tokens=1500)

    def work(self, task: dict, worker: str, objective: dict, rules: list[str], handoff: dict,
             inbox: dict[str, str], feedback: str = "", answers: list[dict] | None = None, **_) -> tuple[dict, dict]:
        files = "\n".join(f"--- {k} ---\n{v}" for k, v in inbox.items()) or "none"
        extra = ""
        if answers:
            extra += "\nAnswers to your Blockers:\n" + "\n".join(a.get("acceptance_check", "") for a in answers)
        if feedback:
            extra += "\nVerification sent this back. Fix it:\n" + feedback
        kind = task["kind"]
        if kind in ("spec", "code"):
            shape = ('{"result": "done", "summary": "...", "files": {"name.ext": "full file content"}, '
                     '"acceptance_check": "..."} or {"result": "blocked", "category": "missing_input", '
                     '"description": "...", "needs_from": "w_pm"}')
        else:
            shape = ('{"result": "proposal", "problem": "...", "recommendation": "...", "evidence_refs": [], '
                     '"cost": "...", "confidence": "low, medium or high", "what_would_change_this": "..."}')
        prompt = (ROLE_TEXT.get(worker, "") + "\n" + self._ctx(objective, rules) + "\n" + DELIVERY_CONTRACT + "\n\n"
                  f"Task {task['id']}: {task['title']}. Expected output: {task['expected_output']}.\n"
                  f"Handoff: {json.dumps({k: handoff.get(k) for k in ('acceptance_check', 'context_ref', 'artifacts')})}\n"
                  f"Files handed to you:\n{files}\n{extra}\n"
                  "If a fact you need is missing and you would have to guess it, raise a Blocker instead.\n"
                  f"Return one JSON object: {shape}")
        return self._call(prompt, max_tokens=8000 if kind == "code" else 3000)

    def answer_blocker(self, task: dict, worker: str, objective: dict, rules: list[str], blocker: dict,
                       artifact_index: list[str], **_) -> tuple[dict, dict]:
        prompt = (ROLE_TEXT.get(worker, "") + "\n" + self._ctx(objective, rules) + "\n"
                  f"{blocker.get('raised_by')} raised a Blocker on {task['id']} ({task['title']}): "
                  f"{blocker.get('description')}\nArtifacts that exist: {json.dumps(artifact_index)}\n"
                  "Clear it using only the objective, the decided rules and the artifacts. If it needs a new product "
                  "decision, say so plainly and give the safest reading for now.\n"
                  'Return JSON: {"artifacts": [ids], "context_ref": "...", "acceptance_check": "the missing facts"}')
        return self._call(prompt, max_tokens=1500)


def make(mode: str, scenario_id: str = "candidate_tracker"):
    if mode == "live":
        return ModelSource()
    return ScriptedSource(scenario_id)
