"""The intelligence behind the workers: prompts and transport, nothing else.

ModelSource     real intelligence per worker. Every call goes to the Intelligence Gateway (intelligence_layer) for
                the intelligence the worker is bound to; the source never knows the provider. A model error stops
                the step; nothing is invented.
ScriptedSource  the demo. Every word comes from scenarios/<id>/scenario.json and is labelled as scripted; the code it
                hands over is real and is tested and deployed for real.

Both are bound to an access point (the run, or the probe) that answers two questions:
    intelligence_for(worker) -> the id of the intelligence bound to that worker
    invoke(worker, request)  -> the Gateway's response for one call, with the intelligence id that answered

Both answer the same questions with raw answers. Checking an answer is the engines' job (objective.py,
synthesis.py, planner.py, execution.py): they validate it, and ask() gives the source one retry with the reason.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from . import roles

HERE = Path(__file__).resolve().parent
SCENARIOS = HERE.parent / "scenarios"


class IntelligenceError(RuntimeError):
    """The source could not answer. The step stops; it is never papered over. model_id names the model that
    failed, so the workforce engine can count the failure against it and staff the worker with another."""

    def __init__(self, message: str, model_id: str | None = None, usage: dict | None = None):
        super().__init__(message)
        self.model_id = model_id
        self.usage = usage or {}


def _parse_json(text: str):
    """The first JSON object in the reply: fenced, bare, or followed by file blocks."""
    raw = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for m in re.finditer(r"\{", raw):
        try:
            obj, _ = decoder.raw_decode(raw, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def as_int(value, default: int) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return default


def _add(usage: dict, more: dict) -> dict:
    for k in ("tokens_in", "tokens_out", "latency_s"):
        usage[k] = (usage.get(k) or 0) + (more.get(k) or 0)
    return usage


def ask(call, check):
    """One question whose answer the platform checks. Refused once, it is asked again with the reason; refused
    twice, IntelligenceError: the step stops and nothing is invented. call(feedback) -> (data, usage)."""
    data, usage = call("")
    try:
        return check(data), usage
    except IntelligenceError as exc:
        data2, usage2 = call(str(exc))
        return check(data2), _add(usage, usage2)


FILE_HEAD = re.compile(r"^[ \t>*#`]*={2,}[ \t]*FILE[ \t]*:?[ \t]*`?(?P<name>[\w./ -]+?)`?[ \t]*={2,}[ \t*`]*$", re.M | re.I)
FILE_END = re.compile(r"^[ \t>*#`]*={2,}[ \t]*END\b[^\n]*$", re.M | re.I)
FENCED = re.compile(r"^```[\w+-]*[ \t]*\n(?P<body>.*?)\n```[ \t]*$", re.S | re.M)
NAME = re.compile(r"(?<![\w/.-])(?P<name>[\w-]+(?:/[\w-]+)*\.(?:py|md|html|css|js|json|txt|toml|cfg|ini|yaml|yml))\b")


def files_layout(needs_from: str) -> str:
    return ("Return your answer in exactly this layout and nothing else. First one JSON object on its own:\n"
            '{"result": "done", "summary": "...", "acceptance_check": "..."}\n'
            "Then each file you write, exactly like this:\n"
            "=== FILE: name.ext ===\n"
            "the complete file content, exactly as it should be saved\n"
            "=== END FILE ===\n"
            "Write file contents as plain text, not escaped and not inside code fences. "
            'If a fact you need is missing, return only: {"result": "blocked", "category": "missing_input", '
            f'"description": "...", "needs_from": "{needs_from}"}}')


S = {"type": "string"}
LIST = {"type": "array", "items": S}
OBJECTIVE_KEYS = ["product", "target_customer", "primary_outcome", "business_outcome", "success_criteria",
                  "constraints", "priorities"]
SCHEMAS = {
    "objective": {"type": "object", "properties": {**{k: S for k in OBJECTIVE_KEYS}, "inferred_fields": LIST,
                                                   "missing_fields": LIST},
                  "required": OBJECTIVE_KEYS + ["inferred_fields", "missing_fields"]},
    "requirements": {"type": "object", "required": ["outcomes", "requirements", "risks", "assumptions", "measures",
                                                     "workstreams"], "properties": {
        "outcomes": LIST,
        "assumptions": {"type": "array", "items": {"type": "object", "properties": {
            "text": S, "kind": {"type": "string", "enum": ["desirability", "viability", "feasibility"]},
            "risk": {"type": "string", "enum": ["high", "medium", "low"]}, "tested_by": LIST, "founder_step": S},
            "required": ["text", "kind", "risk", "tested_by", "founder_step"]}},
        "measures": {"type": "array", "items": {"type": "object", "properties": {
            "measure": S, "target": S, "rethink_below": S}, "required": ["measure", "target", "rethink_below"]}},
        "risks": {"type": "array", "items": {"type": "object", "properties": {
            "area": {"type": "string", "enum": roles.AREAS}, "text": S}, "required": ["area", "text"]}},
        "requirements": {"type": "array", "items": {"type": "object", "properties": {
            "id": S, "area": {"type": "string", "enum": roles.AREAS}, "text": S, "verification": S},
            "required": ["id", "area", "text", "verification"]}},
        "workstreams": {"type": "array", "items": {"type": "object", "properties": {
            "id": S, "name": S, "requirement_ids": LIST, "depends_on": LIST},
            "required": ["id", "name", "requirement_ids", "depends_on"]}}}},
    "cofounders": {"type": "object", "required": ["summary", "cofounders"], "properties": {
        "summary": S,
        "cofounders": {"type": "array", "items": {"type": "object", "properties": {
            "role": {"type": "string", "enum": roles.COFOUNDERS}, "why": S, "requirement_ids": LIST, "risk_ids": LIST},
            "required": ["role", "why", "requirement_ids", "risk_ids"]}}}},
    "team": {"type": "object", "required": ["summary", "roles"], "properties": {
        "summary": S,
        "roles": {"type": "array", "items": {"type": "object", "properties": {
            "role": {"type": "string", "enum": [n for n in roles.ROLES if n not in roles.COFOUNDERS]},
            "quantity": {"type": "integer"}, "why": S, "requirement_ids": LIST, "supports": LIST, "risk_ids": LIST,
            "field": S, "title": S},
            "required": ["role", "quantity", "why", "requirement_ids", "supports", "risk_ids"]}}}},
    "challenge": {"type": "object", "required": ["seats", "failure_stories"], "properties": {
        "seats": {"type": "array", "items": {"type": "object", "properties": {
            "seat": S, "verdict": {"type": "string", "enum": ["keep", "cut", "merge", "advisor", "later"]},
            "into": S, "why": S}, "required": ["seat", "verdict", "why"]}},
        "failure_stories": LIST}},
    "review": {"type": "object", "properties": {"verdict": {"type": "string", "enum": ["approve", "revise"]},
                                                 "note": S}, "required": ["verdict", "note"]},
    "handoff": {"type": "object", "properties": {"artifacts": LIST, "context_ref": S, "acceptance_check": S},
                "required": ["artifacts", "context_ref", "acceptance_check"]},
    "proposal": {"type": "object", "properties": {
        "result": {"type": "string", "enum": ["proposal"]}, "problem": S, "recommendation": S, "evidence_refs": LIST,
        "cost": S, "confidence": {"type": "string", "enum": ["low", "medium", "high"]}, "what_would_change_this": S},
        "required": ["result", "problem", "recommendation", "evidence_refs", "cost", "confidence",
                     "what_would_change_this"]},
}


def _closed(schema):
    """additionalProperties false on every object: Ollama assumes it, llama-server needs it said."""
    if isinstance(schema, dict):
        out = {k: _closed(v) for k, v in schema.items()}
        if out.get("type") == "object":
            out["additionalProperties"] = False
        return out
    if isinstance(schema, list):
        return [_closed(v) for v in schema]
    return schema


SCHEMAS = {k: _closed(v) for k, v in SCHEMAS.items()}


def plan_schema(worker_ids: list[str]) -> dict:
    """The roadmap's shape, with the owners this organization actually has and the catalog's task types."""
    return _closed({"type": "object", "required": ["workstreams", "milestones", "tasks"], "properties": {
        "workstreams": {"type": "array", "items": {"type": "object", "properties": {"id": S, "name": S},
                                                   "required": ["id", "name"]}},
        "milestones": {"type": "array", "items": {"type": "object", "properties": {
            "id": S, "name": S, "due_day": {"type": "integer"}}, "required": ["id", "name", "due_day"]}},
        "tasks": {"type": "array", "items": {"type": "object", "properties": {
            "id": S, "workstream_id": S, "milestone_id": S, "kind": {"type": "string", "enum": list(roles.TASK_TYPES)},
            "owner_worker_id": {"type": "string", "enum": list(worker_ids)}, "title": S, "inputs": S,
            "expected_output": S, "acceptance_criteria": LIST, "requirement_ids": LIST, "documents": LIST,
            "dependencies": LIST, "deadline_day": {"type": "integer"}},
            "required": ["id", "workstream_id", "milestone_id", "kind", "owner_worker_id", "title", "inputs",
                         "expected_output", "acceptance_criteria", "requirement_ids", "documents", "dependencies",
                         "deadline_day"]}}}})


def _unfence(body: str) -> str:
    """A file body a model wrapped in a Markdown code fence, unwrapped."""
    lines = body.strip("\n").split("\n")
    if len(lines) >= 2 and lines[0].lstrip().startswith("```") and lines[-1].strip() == "```":
        lines = lines[1:-1]
    return "\n".join(lines).rstrip() + "\n"


def _file_blocks(text: str) -> dict[str, str]:
    """Files in a reply. The layout asked for is === FILE: name === ... === END FILE ===; plain text survives far
    better than code escaped inside JSON. Local models drift from it, so the common variants are read too: a
    missing or longer END line, a Markdown fence inside a block, and Markdown alone (a file name, then a fenced
    block, or a fenced block whose first line names the file)."""
    text = text or ""
    heads = list(FILE_HEAD.finditer(text))
    files: dict[str, str] = {}
    for i, h in enumerate(heads):
        stop = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        end = FILE_END.search(text, h.end(), stop)
        body = text[h.end():end.start() if end else stop]
        name = h.group("name").strip()
        if name and body.strip():
            files[name] = _unfence(body)
    if files:
        return files
    for m in FENCED.finditer(text):
        body = m.group("body")
        first = body.split("\n", 1)[0]
        before = [ln for ln in text[:m.start()].split("\n")[-3:] if ln.strip() and not ln.strip().startswith("```")]
        named = (NAME.search(first) if first.lstrip().startswith(("#", "//", "<!--")) else None) or \
            (NAME.search(before[-1]) if before else None)
        if named and body.strip():
            files[named.group("name")] = body.rstrip() + "\n"
    return files


def _cut_file(text: str) -> str:
    """The file a reply cut off at the output limit was writing: its last file block, when no END line closes it."""
    heads = list(FILE_HEAD.finditer(text or ""))
    if heads and not FILE_END.search(text, heads[-1].end()):
        return heads[-1].group("name").strip()
    return ""



DELIVERY_CONTRACT = ("Delivery contract. The product is a Python 3.10 standard library web app. No third party "
                     "packages. app.py sits at the repository root and starts its HTTP server only under "
                     "`if __name__ == \"__main__\":`, on 127.0.0.1 and the port in the PORT environment variable. "
                     "It answers GET /health with 200 and GET / with 200 and the product's web page. It keeps its "
                     "data in the JSON file named by the DATA_FILE environment variable. Tests are unittest files "
                     "named test_*.py at the repository root; they must not need the network. A test that starts a "
                     "server uses port 0, runs serve_forever() in a daemon thread, gives every request a timeout, "
                     "and shuts the server down when it is done. Every test in the repository is rerun with "
                     "`python -m unittest discover` on each change. File names are paths relative to the "
                     "repository root; Markdown documents are filed under docs/.")
FORECAST_CONTRACT = ("Forecast contract. forecast.py at the repository root defines forecast(history, horizon): history "
                     "is a list of {\"date\": \"YYYY-MM-DD\", \"covers\": number} for consecutive days, oldest first; "
                     "horizon is how many following days to forecast; it returns a list of horizon non-negative numbers. "
                     "Standard library only. The platform backtests it on held-out days of its own data and requires "
                     "its mean absolute error to be no worse than forecasting each day with the same weekday of the "
                     "week before.")


def task_brief(task: dict) -> str:
    """What a task's type asks of its owner, from the catalog."""
    kind = task["kind"]
    out = f"Task type {kind}: {roles.TASK_TYPES[kind]['about']}.\n"
    if kind == "document":
        out += ("Write these documents, one Markdown file each, and cite in them the requirement ids this task covers ("
                + (", ".join(task.get("requirement_ids") or []) or "none") + "):\n"
                + "\n".join("* " + roles.doc_rules(d) for d in task.get("documents") or []) + "\n")
    if kind == "forecast":
        out += FORECAST_CONTRACT + "\n"
    return out


class ScriptedSource:
    """The demo's prepared script. It answers the same questions a model does, with the scenario's words, and
    stands for the scripted model in the run's registry, so every call is staffed and metered like any other."""
    kind = "scripted"

    def __init__(self, scenario_id: str):
        self.dir = SCENARIOS / scenario_id
        self.data = json.loads((self.dir / "scenario.json").read_text(encoding="utf-8"))
        self.access = None

    def bind(self, access) -> None:
        """The run: which intelligence (the demo script, in the run's registry) is bound to each worker."""
        self.access = access

    def _usage(self, worker: str = "system") -> dict:
        model_id = self.access.intelligence_for(worker)
        return {"tokens_in": 0, "tokens_out": 0, "estimated": True, "label": f"scripted ({self.dir.name})",
                "latency_s": 0.0, "model_id": model_id}

    def _resolve(self, obj):
        if isinstance(obj, str) and obj.startswith("@files/"):
            return (self.dir / obj[1:]).read_text(encoding="utf-8")
        if isinstance(obj, dict):
            return {k: self._resolve(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._resolve(v) for v in obj]
        return obj

    def _copy(self, key: str):
        return json.loads(json.dumps(self.data[key]))

    def structure_objective(self, messy: str) -> tuple[dict, dict]:
        out = self._copy("objective")
        if messy.strip() != self.data["messy"].strip():
            out["notice"] = ("Demo mode only knows its prepared scenario, so it returned that objective. "
                             "Switch to live mode to build your own.")
        return out, self._usage()

    def decompose(self, objective: dict, feedback: str = "", note: str = "") -> tuple[dict, dict]:
        return self._copy("requirements"), self._usage()

    def cofounders(self, objective: dict, requirements: dict, note: str = "", feedback: str = "", **_) -> tuple[dict, dict]:
        wf = self._copy("workforce")
        return {"summary": wf.get("summary", ""), "cofounders": wf.get("cofounders", [])}, self._usage()

    def build_team(self, objective: dict, requirements: dict, cofounder: str = "", **_) -> tuple[dict, dict]:
        team = (self._copy("workforce").get("teams") or {}).get(cofounder)
        return (team if isinstance(team, dict) else {"summary": "", "roles": []}), self._usage()

    def challenge(self, objective: dict, requirements: dict, seats: list[dict], **_) -> tuple[dict, dict]:
        """The independent challenge of the proposed team: the scenario's words, else no objection."""
        return (self._copy("challenge") if "challenge" in self.data else {"seats": [], "failure_stories": []}), \
            self._usage()

    def plan(self, objective: dict, workers: list[dict], requirements: dict, note: str = "", feedback: str = "",
             planner: str = "system", persona: str = "", cycle: int = 1, **_) -> tuple[dict, dict]:
        if cycle > 1:
            later = (self.data.get("cycles") or {}).get(str(cycle))
            if not later:
                raise IntelligenceError(f"the demo's script has no plan for cycle {cycle}; in live mode the team plans it")
            return json.loads(json.dumps(later["plan"])), self._usage(planner)
        return self._copy("plan"), self._usage(planner)

    def assign(self, task: dict, worker: str = "system", **_) -> tuple[dict, dict]:
        preset = self.data.get("assign", {}).get(task["id"])
        if preset is None:
            raise IntelligenceError(f"scenario has no assignment for {task['id']}")
        return json.loads(json.dumps(preset)), self._usage(worker)

    def work(self, task: dict, worker: str = "system", call_index: int = 0, **_) -> tuple[dict, dict]:
        """call_index is how many times this task has already been worked; the engine keeps it."""
        items = self.data.get("work", {}).get(task["id"])
        if not items:
            raise IntelligenceError(f"scenario has no work for {task['id']}")
        return self._resolve(items[min(call_index, len(items) - 1)]), self._usage(worker)

    def answer_blocker(self, task: dict, worker: str = "system", **_) -> tuple[dict, dict]:
        preset = self.data.get("answer_blocker", {}).get(task["id"])
        if preset is None:
            raise IntelligenceError(f"scenario has no Blocker answer for {task['id']}")
        return json.loads(json.dumps(preset)), self._usage(worker)

    def review(self, task: dict, worker: str = "system", round_index: int = 0, **_) -> tuple[dict, dict]:
        """A cofounder's review of its team's work: the scenario's words for this task and round, else its default."""
        items = self.data.get("review", {}).get(task["id"]) or [self.data.get("review_default")]
        preset = items[min(round_index, len(items) - 1)]
        if not isinstance(preset, dict):
            raise IntelligenceError(f"scenario has no review for {task['id']}")
        return json.loads(json.dumps(preset)), self._usage(worker)


class ModelSource:
    """Real intelligence: each call goes through the Intelligence Gateway to what the worker is bound to now."""
    kind = "model"

    def __init__(self):
        self.access = None
        self.last_text = ""  # the last raw reply, kept to show what a model wrote when it could not be read
        self.answered: dict[str, int] = {}  # prompt digest -> replies already received for exactly that prompt
        self.objective_prompt = (HERE / "objective_prompt.txt").read_text(encoding="utf-8")

    def bind(self, access) -> None:
        """The run (or the probe): intelligence_for(worker) and invoke(worker, request)."""
        self.access = access

    def _call(self, prompt: str, max_tokens: int = 4000, files: bool = False, schema: dict | None = None,
              worker: str = "system", needs_from: str = "") -> tuple[dict, dict]:
        """One model call. files=True: a JSON header followed by file blocks, so no constrained JSON mode."""

        def parse(text: str):
            data = _parse_json(text)
            if files:
                blocks = _file_blocks(text)
                if blocks and not (isinstance(data, dict) and isinstance(data.get("files"), dict) and data["files"]):
                    data = dict(data) if isinstance(data, dict) else {"result": "done"}
                    data["files"] = blocks
            return data

        # A local model gives the same reply to the same prompt (temperature 0, fixed seed). A rework whose feedback and
        # previous files are exactly those of an attempt already answered would get the same failing reply again, so a
        # repeated prompt is sent with some temperature: 0.3 the second time, 0.6 the third, then 0.9.
        model_id = self.access.intelligence_for(worker)
        key = hashlib.sha256(f"{model_id}|{prompt}".encode("utf-8")).hexdigest()
        repeats = self.answered.get(key, 0)
        out = self.access.invoke(worker, {"prompt": prompt, "max_tokens": max_tokens, "want_json": not files,
                                          "schema": schema, "partial": files,
                                          "temperature": round(min(0.3 * repeats, 0.9), 1) if repeats else None})
        model_id = out.get("model_id") or model_id
        if out.get("error"):
            raise IntelligenceError(out["error"], model_id=model_id, usage=out)
        self.answered[key] = repeats + 1
        self.last_text = out["text"]
        data = parse(out["text"])
        if files and out.get("truncated"):
            # Cut off at the output limit: the files finished before the cut are kept, the one being written is
            # dropped, and the engine asks for the rest instead of the whole reply again.
            data = dict(data) if isinstance(data, dict) else {"result": "done"}
            cut = _cut_file(out["text"])
            data["files"] = {k: v for k, v in (data.get("files") or {}).items() if k != cut}
            data["cut_off"] = cut or "a file"
        no_files = files and isinstance(data, dict) and data.get("result") != "blocked" and not data.get("files") \
            and "cut_off" not in data
        if not isinstance(data, dict) or no_files:
            again = ("\n\nYour reply had no files in the required layout. " + files_layout(needs_from)) if files else \
                "\n\nReply with only one JSON object."
            out2 = self.access.invoke(worker, {"prompt": prompt + again, "max_tokens": max_tokens,
                                               "want_json": not files, "schema": schema, "temperature": 0.4})
            if out2.get("error"):
                raise IntelligenceError(out2["error"], model_id=model_id, usage=out2)
            self.last_text = out2["text"]
            data = parse(out2["text"])
            out["tokens_in"] += out2["tokens_in"]
            out["tokens_out"] += out2["tokens_out"]
        if not isinstance(data, dict):
            raise IntelligenceError("model did not return a JSON object")
        usage = {"tokens_in": out["tokens_in"], "tokens_out": out["tokens_out"], "estimated": out["estimated"],
                 "label": out.get("model") or model_id, "latency_s": out.get("latency_s", 0), "model_id": model_id}
        if out.get("speed"):
            usage.update(out["speed"])
        return data, usage

    @staticmethod
    def _head(persona: str, objective: dict, rules: list[str]) -> str:
        """The start of every role's prompt. What stays the same through a run comes first (the contract, the
        objective, then the rules, which only grow), the role after it: a local server reuses its cache for the
        part a prompt shares with the one before, so a change of speaker does not mean reading it all again."""
        return DELIVERY_CONTRACT + "\n\n" + ModelSource._ctx(objective, rules) + "\n" + (persona or "") + "\n\n"

    @staticmethod
    def _ctx(objective: dict, rules: list[str]) -> str:
        fields = {k: objective.get(k, "") for k in OBJECTIVE_KEYS}
        stated = {k: v for k, v in (objective.get("_constraints") or {}).items() if v}
        r = "\n".join(f"* {x}" for x in rules) or "* none yet"
        return (f"Objective:\n{json.dumps(fields, indent=1)}\n"
                + (f"Constraints the founder set: {json.dumps(stated)}\n" if stated else "")
                + f"Decided rules:\n{r}\n")

    @staticmethod
    def _refused(feedback: str) -> str:
        return f"\n\nYour previous answer was refused: {feedback}. Return a corrected one." if feedback else ""

    def structure_objective(self, messy: str) -> tuple[dict, dict]:
        """Stage 0: the founder's words as the seven objective fields."""
        data, usage = self._call(self.objective_prompt + messy + "\n", max_tokens=1500, schema=SCHEMAS["objective"])
        empty = [k for k in OBJECTIVE_KEYS if not str(data.get(k) or "").strip()]
        if not empty:
            return data, usage
        # Small models leave implied fields blank instead of inferring them. One short follow-up for just those
        # fields gives the founder a reading to check instead of a blank to fill.
        fields = {k: str(data.get(k) or "") for k in OBJECTIVE_KEYS}
        prompt = ("A founder described what they want built:\n" + messy.strip() + "\n\nThe structured objective so "
                  "far:\n" + json.dumps(fields, indent=1) + "\n\nThese fields are still empty: " + ", ".join(empty) +
                  ". For each one, write the most reasonable reading of the founder's words, one or two sentences, "
                  "without adding features, users or constraints they did not state or clearly imply. The founder "
                  "will review each one. Return JSON with exactly these keys.")
        schema = _closed({"type": "object", "properties": {k: S for k in empty}, "required": empty})
        try:
            more, usage2 = self._call(prompt, max_tokens=600, schema=schema)
        except IntelligenceError:
            return data, usage  # the blanks stay blank; the founder fills them before submitting
        filled = [k for k in empty if str(more.get(k) or "").strip()]
        data = dict(data)
        for k in filled:
            data[k] = str(more[k]).strip()
        data["inferred_fields"] = list(dict.fromkeys(list(data.get("inferred_fields") or []) + filled))
        return data, _add(usage, usage2)

    def decompose(self, objective: dict, feedback: str = "", note: str = "") -> tuple[dict, dict]:
        """Stage 1: the objective as outcomes, requirements, risks, workstreams and their dependencies."""
        prompt = (self._head("You are Cynqra's Objective Intelligence.", objective, []) +
                  "Decompose the objective into requirements. Cover, where the objective calls for them: product "
                  "outcomes and success criteria, functional and non-functional requirements, AI/ML and data "
                  "requirements, design, security, QA, DevOps and deployment. When the founder wants to build a "
                  "company or a business, its foundation is implied too: the market and competitors (market), costs, "
                  "pricing and funding (finance), the regulations and legal risks that apply (legal), and the "
                  "business direction (business), as far as this company calls for them. Expertise particular to "
                  "this company's field that no general role holds is its own requirement (domain). Each "
                  "requirement has an area, one of "
                  f"{', '.join(roles.AREAS)}, a sentence, and how it will be verified. Group the requirements into "
                  "workstreams and say which workstreams depend on which. List the outcomes: what must be true when "
                  "the work is done, a few short sentences. List the risks: what must not go wrong for this company "
                  "(customer data leaking, an offer losing money, a forecast owners stop trusting), each with its "
                  "area; only the ones this company really faces. List the assumptions: the guesses the idea depends "
                  "on (people want it, it makes money, it can be built), how bad it is if each is wrong (high, "
                  "medium, low), the requirement ids whose work tests it, and, when only a person can test it (for "
                  "example by showing it to five customers), the founder's step in one sentence. List two or three "
                  "measures: how the founder will know it worked, each with a target and the line below which to "
                  "rethink. Add nothing the founder did not state or clearly imply. The team is built from this list.\n"
                  + (f"The founder asked for changes to the previous list: {note}\n" if note else "") +
                  'Return JSON: {"outcomes": ["..."], "requirements": [{"id": "r_01", "area", "text", '
                  '"verification"}], "risks": [{"area", "text"}], "assumptions": [{"text", "kind", "risk", '
                  '"tested_by", "founder_step"}], "measures": [{"measure", "target", "rethink_below"}], '
                  '"workstreams": [{"id", "name", "requirement_ids", "depends_on"}]}' + self._refused(feedback))
        # the list now carries risks, guesses and measures as well: room for them, so the answer is not cut off
        return self._call(prompt, max_tokens=4500, schema=SCHEMAS["requirements"])

    @staticmethod
    def _catalog(names) -> str:
        return "\n".join(f"* {r['role']}: {r['title']}. {r['charter']} Covers: {', '.join(r['areas'])}. "
                         f"Owns: {', '.join(r['owns'])}. At most {r['max']}." for r in roles.catalog() if r["role"] in names)

    @staticmethod
    def _lists(requirements: dict) -> str:
        """The confirmed requirements and risks, as every team prompt shows them. The founder's own are marked."""
        reqs = "\n".join(f"* {r['id']} ({r['area']}): {r['text']}" + (" [the founder's own]" if r.get("owner") ==
                         "founder" else "") for r in requirements["requirements"])
        risks = "\n".join(f"* {k['id']} ({k['area']}): {k['text']}" for k in requirements.get("risks") or []) or "* none"
        return f"Requirements:\n{reqs}\nRisks the company must control:\n{risks}\n"

    @staticmethod
    def _founder(founder: dict | None) -> str:
        f = founder or {}
        from .objective import STAGES
        leads = ", ".join(roles.role(c)["title"] for c in f.get("leads") or []) or "none"
        return (f"The founder: stage {STAGES.get(f.get('stage'), f.get('stage') or 'not stated')}; "
                f"{f.get('hours_per_week', 'unknown')} hours a week; leads themselves: {leads}"
                + (f"; background: {f['background']}" if f.get("background") else "") + ".\n")

    def cofounders(self, objective: dict, requirements: dict, note: str = "", feedback: str = "",
                   founder: dict | None = None) -> tuple[dict, dict]:
        """Stage 2, step one: the cofounders the company needs, as a founder would choose them."""
        prompt = (self._head("You are Cynqra's Workforce Synthesizer.", objective, []) +
                  "The founder is the CEO. Like a founder starting a real company, choose the cofounders this company "
                  "needs to lead it with the founder. Choose only the ones this company needs, each with the reason: "
                  "a product that is software needs a CTO; a company whose customers and product must be defined "
                  "needs a Chief Product Officer; a company whose value depends on money (pricing, margins, funding) "
                  "needs a CFO; a regulated business (payments, lending, insurance, health, children's data) needs "
                  "a Chief Compliance Officer. A simple internal tool may need only two. A cofounder fills a gap the "
                  "founder cannot fill: never propose one for an area the founder leads themselves. Each cofounder "
                  "proposes its own team next, so name only cofounders here, each with the requirement ids it is "
                  "accountable for and the risk ids it watches.\n" + self._founder(founder) +
                  f"Cofounder roles:\n{self._catalog(roles.COFOUNDERS)}\n{self._lists(requirements)}"
                  + (f"The founder rejected the previous proposal: {note}\n" if note else "") +
                  'Return JSON: {"summary": "...", "cofounders": [{"role", "why", "requirement_ids", "risk_ids"}]}'
                  + self._refused(feedback))
        return self._call(prompt, max_tokens=1500, schema=SCHEMAS["cofounders"])

    def build_team(self, objective: dict, requirements: dict, cofounder: str, cofounders: list[str],
                   hired: dict[str, str], note: str = "", feedback: str = "", persona: str = "",
                   founder: dict | None = None, limit: int = 0) -> tuple[dict, dict]:
        """Stage 2, step two: one cofounder proposes the team for its own area."""
        from .synthesis import hireable  # the platform's rule on who may hire whom, stated to the model
        may = hireable(cofounder, cofounders)
        others = ", ".join(roles.role(c)["title"] for c in cofounders if c != cofounder) or "none"
        prompt = (self._head(persona, objective, []) +
                  f"You are a cofounder of this company; the founder is the CEO. The other cofounders: {others}. "
                  "Propose the team you need for your own area: which roles, how many of each, why each is needed, "
                  "the requirement ids each one owns (requirement_ids: the work it is answerable for), the ones it "
                  "only helps with (supports), and the risk ids it watches (risk_ids). Every hire must own something "
                  "no one else on the team owns, or watch a risk no one else watches: an independent check will try "
                  "to cut every seat that does not. Hire only for work in your area, and propose the smallest team "
                  f"that covers it, at most {limit or 'a few'} seats; an empty team is fine if you can do your part "
                  "yourself. For expertise "
                  "particular to this company's field that no role holds, propose a Specialist with its field and "
                  'title (one per field, such as {"role": "Specialist", "field": "food safety", "title": "Food '
                  'Safety Specialist"}).\n'
                  f"Roles you may hire:\n{self._catalog(may)}\n"
                  + (f"Already hired by the other cofounders, do not hire again: {json.dumps(hired)}\n" if hired else "")
                  + self._founder(founder) + self._lists(requirements)
                  + (f"The founder rejected the previous proposal: {note}\n" if note else "") +
                  'Return JSON: {"summary": "...", "roles": [{"role", "quantity", "why", "requirement_ids", '
                  '"supports", "risk_ids"}]}' + self._refused(feedback))
        return self._call(prompt, max_tokens=1500, schema=SCHEMAS["team"])

    def challenge(self, objective: dict, requirements: dict, seats: list[dict], founder: dict | None = None,
                  feedback: str = "", **_) -> tuple[dict, dict]:
        """The independent challenge: a reviewer outside the team whose only job is to make it smaller."""
        lines = "\n".join(f"* {s['seat']}: {s['title']} x{s['quantity']}, hired by {s['requested_by']}. Why: {s['why']} "
                          f"Owns: {', '.join(s['owns']) or 'nothing'}. Helps with: {', '.join(s['supports']) or 'nothing'}. "
                          f"Watches: {', '.join(s['controls']) or 'nothing'}." for s in seats)
        prompt = (self._head("You are the independent challenger of a proposed team. You are not part of it and gain "
                             "nothing from its size.", objective, []) + self._founder(founder)
                  + self._lists(requirements) + f"The proposed team:\n{lines}\n"
                  "Try to make this team smaller without leaving any requirement or risk without an owner. For each "
                  "seat that should change, give a verdict: cut (it is not needed), merge (another seat, named in "
                  "into, can do its work), advisor (needed only for a few questions, not as a full member) or later "
                  "(not needed until a later stage). Seats you would keep need no entry. Then imagine this company "
                  "has failed a year from now and write, in one sentence each, the one or two most likely reasons: "
                  "they show what the team is missing. Be concrete; give the reason for every verdict.\n"
                  'Return JSON: {"seats": [{"seat", "verdict", "into", "why"}], "failure_stories": ["..."]}'
                  + self._refused(feedback))
        return self._call(prompt, max_tokens=1500, schema=SCHEMAS["challenge"])

    def plan(self, objective: dict, workers: list[dict], requirements: dict, note: str = "", feedback: str = "",
             planner: str = "system", persona: str = "", cycle: int = 1, done: list[str] | None = None) -> tuple[dict, dict]:
        """Stage 5: the roadmap for this organization, or a later cycle's work on the live product."""
        def line(w):
            r = roles.role(w["role"])
            place = "cofounder, reports to the founder" if r["tier"] == "cofounder" else f"reports to {w.get('reports_to')}"
            return (f"* {w['id']}: {w['title']} ({w['role']}; {place}), may own {', '.join(r['owns'])}"
                    + (f"; writes {', '.join(r['documents'])}" if r["documents"] else ""))
        org = "\n".join(line(w) for w in workers)
        rlist = "\n".join(f"* {r['id']} ({r['area']}): {r['text']}" for r in requirements["requirements"]
                          if r.get("owner") != "founder") or "* none"
        types = "\n".join(f"{k}: {v['about']}." for k, v in roles.TASK_TYPES.items())
        prompt = (self._head(persona, objective, []) +
                  f"Plan the work for this organization:\n{org}\nRequirements:\n{rlist}\n"
                  "Break the objective into milestones and workstreams, and the workstreams into tasks. Give each task "
                  "to the worker best positioned to do it (each cofounder hands out and reviews its own team's work, "
                  "so a team's tasks belong in its cofounder's area), with acceptance criteria that can be checked and the "
                  "requirement ids it satisfies; a document task names the document types it writes, from those its "
                  f"owner writes. Task types:\n{types}\n"
                  "A task's owner must be a worker who may own its type. Ids t_01, t_02 and so on; dependencies may "
                  "only name earlier tasks.\n"
                  + (f"This is cycle {cycle}: the product is live. Done in earlier cycles, not to plan again:\n"
                     + "\n".join(f"* {x}" for x in done or []) + "\nPlan only the new work the founder asks for, "
                     "ending with one review_merge and one deploy, with at least one code task.\nThe founder asks: "
                     f"{note}\n" if cycle > 1 else
                     (f"The founder rejected the previous roadmap: {note}\n" if note else "")) +
                  'Return JSON: {"workstreams": [{"id", "name"}], "milestones": [{"id", "name", "due_day"}], '
                  '"tasks": [{"id", "workstream_id", "milestone_id", "kind", "owner_worker_id", "title", "inputs", '
                  '"expected_output", "acceptance_criteria", "requirement_ids", "documents", "dependencies", '
                  '"deadline_day"}]}' + self._refused(feedback))
        return self._call(prompt, max_tokens=4000, schema=plan_schema([w["id"] for w in workers]), worker=planner)

    def assign(self, task: dict, objective: dict, rules: list[str], artifact_index: list[str], worker: str = "system",
               persona: str = "", **_) -> tuple[dict, dict]:
        crit = "; ".join(task.get("acceptance_criteria") or [])
        prompt = (self._head(persona, objective, rules) +
                  f"Assign task {task['id']} ({task['title']}) to {task['owner_worker_id']}. Expected output: "
                  f"{task['expected_output']}.\n" + (f"Acceptance criteria: {crit}\n" if crit else "") +
                  f"Artifacts that exist: {json.dumps(artifact_index)}\n"
                  "List only the artifacts the worker needs. Put every closed list or rule they must not invent "
                  "into acceptance_check.\n"
                  'Return JSON: {"artifacts": [ids], "context_ref": "...", "acceptance_check": "..."}')
        return self._call(prompt, max_tokens=1500, schema=SCHEMAS["handoff"], worker=worker)

    def work(self, task: dict, worker: str, objective: dict, rules: list[str], handoff: dict,
             inbox: dict[str, str], feedback: str = "", answers: list[dict] | None = None,
             previous: dict[str, str] | None = None, repo_files: list[str] | None = None, persona: str = "",
             answerers: list[str] | None = None, **_) -> tuple[dict, dict]:
        files = "".join(f"=== FILE: {k} ===\n{v.rstrip()}\n=== END FILE ===\n" for k, v in inbox.items()) or "none"
        extra = ""
        if answers:
            extra += "\nAnswers to your Blockers:\n" + "\n".join(a.get("acceptance_check", "") for a in answers)
        if feedback:
            extra += "\nYour last attempt failed a check. Fix it:\n" + feedback
        if previous:
            extra += ("\nYour files so far. They are kept as they are: send only the files you change or add, each one "
                      'complete. To remove a file, add "delete": ["name"] to the JSON object.\n'
                      + "".join(f"=== FILE: {k} ===\n{v.rstrip()}\n=== END FILE ===\n" for k, v in previous.items()))
        kind = task["kind"]
        delivers_files = kind in roles.FILE_TYPES
        shape = None if delivers_files else (
            '{"result": "proposal", "problem": "...", "recommendation": "...", "evidence_refs": [], '
            '"cost": "...", "confidence": "low, medium or high", "what_would_change_this": "..."}')
        repo = f"Files already in the repository: {json.dumps(repo_files or [])}\n" if kind in roles.BUILD_TYPES else ""
        limit = as_int(os.environ.get("CYNQRA_NUM_PREDICT"), 0) if delivers_files else 0
        if limit:  # a local model's reply is capped; a longer one is cut off, and the files it finished are kept
            extra += (f"\nA reply holds at most about {limit} tokens. If the work needs more, send the most important "
                      "files first and keep each file short; you will be asked for the rest.")
        crit = "; ".join(task.get("acceptance_criteria") or [])
        who = answerers or []
        prompt = (self._head(persona, objective, rules) +
                  f"Task {task['id']}: {task['title']}. Expected output: {task['expected_output']}.\n"
                  + task_brief(task) + (f"Acceptance criteria: {crit}\n" if crit else "") +
                  f"Handoff: {json.dumps({k: handoff.get(k) for k in ('acceptance_check', 'context_ref', 'artifacts')})}\n"
                  f"{repo}Files handed to you:\n{files}\n{extra}\n"
                  "If a fact you need is missing and you would have to guess it, raise a Blocker instead; "
                  f"needs_from names who can answer it: {', '.join(who)}.\n"
                  + (files_layout(who[0] if who else "") if delivers_files else f"Return one JSON object: {shape}"))
        return self._call(prompt, max_tokens=8000 if kind in roles.BUILD_TYPES else 3000, files=delivers_files,
                          schema=None if delivers_files else SCHEMAS["proposal"], worker=worker,
                          needs_from=who[0] if who else "")

    def review(self, task: dict, worker: str, objective: dict, rules: list[str], owner: str, work: dict,
               persona: str = "", **_) -> tuple[dict, dict]:
        """A cofounder reviews its team member's work before it counts: files that passed the platform's checks, or
        a proposal before it goes to the founder."""
        crit = "; ".join(task.get("acceptance_criteria") or [])
        body, left = "", 14000
        for name, text in (work.get("files") or {}).items():
            piece = f"=== FILE: {name} ===\n{text[:left].rstrip()}\n=== END FILE ===\n"
            body += piece
            left -= len(piece)
            if left <= 0:
                body += "(the rest of the files are not shown)\n"
                break
        if work.get("proposal"):
            body += "Proposal for the founder:\n" + json.dumps(work["proposal"], indent=1) + "\n"
        prompt = (self._head(persona, objective, rules) +
                  f"{owner}, on your team, finished task {task['id']} ({task['title']}). Expected output: "
                  f"{task['expected_output']}.\n" + (f"Acceptance criteria: {crit}\n" if crit else "") +
                  f"{work.get('checks') or ''}\n{body}"
                  "Review it as the cofounder accountable for this area, before it counts. Approve it if it does what "
                  "was asked and is right for this company. Send it back only for a concrete problem, and say exactly "
                  "what to change; the platform has already run its automatic checks.\n"
                  'Return JSON: {"verdict": "approve" or "revise", "note": "..."}')
        return self._call(prompt, max_tokens=800, schema=SCHEMAS["review"], worker=worker)

    def answer_blocker(self, task: dict, worker: str, objective: dict, rules: list[str], blocker: dict,
                       artifact_index: list[str], persona: str = "", **_) -> tuple[dict, dict]:
        prompt = (self._head(persona, objective, rules) +
                  f"{blocker.get('raised_by')} raised a Blocker on {task['id']} ({task['title']}): "
                  f"{blocker.get('description')}\nArtifacts that exist: {json.dumps(artifact_index)}\n"
                  "Clear it using only the objective, the decided rules and the artifacts. If it needs a new product "
                  "decision, say so plainly and give the safest reading for now.\n"
                  'Return JSON: {"artifacts": [ids], "context_ref": "...", "acceptance_check": "the missing facts"}')
        return self._call(prompt, max_tokens=1500, schema=SCHEMAS["handoff"], worker=worker)

