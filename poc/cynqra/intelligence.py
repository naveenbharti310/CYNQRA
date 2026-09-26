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


FILE_HEAD = re.compile(r"^[ \t>*#`]*={2,}[ \t]*FILE[ \t]*:?[ \t]*`?(?P<name>[\w./ -]+?)`?[ \t]*={2,}[ \t*`]*$", re.M | re.I)
FILE_END = re.compile(r"^[ \t>*#`]*={2,}[ \t]*END\b[^\n]*$", re.M | re.I)
FENCED = re.compile(r"^```[\w+-]*[ \t]*\n(?P<body>.*?)\n```[ \t]*$", re.S | re.M)
NAME = re.compile(r"(?<![\w/.-])(?P<name>[\w-]+(?:/[\w-]+)*\.(?:py|md|html|css|js|json|txt|toml|cfg|ini|yaml|yml))\b")
FILES_LAYOUT = ("Return your answer in exactly this layout and nothing else. First one JSON object on its own:\n"
                '{"result": "done", "summary": "...", "acceptance_check": "..."}\n'
                "Then every file, each one exactly like this:\n"
                "=== FILE: name.ext ===\n"
                "the complete file content, exactly as it should be saved\n"
                "=== END FILE ===\n"
                "Write file contents as plain text, not escaped and not inside code fences. "
                'If a fact you need is missing, return only: {"result": "blocked", "category": "missing_input", '
                '"description": "...", "needs_from": "w_pm"}')


S = {"type": "string"}
LIST = {"type": "array", "items": S}
OBJECTIVE_KEYS = ["product", "target_customer", "primary_outcome", "business_outcome", "success_criteria",
                  "constraints", "priorities"]
SCHEMAS = {
    "objective": {"type": "object", "properties": {**{k: S for k in OBJECTIVE_KEYS}, "inferred_fields": LIST,
                                                   "missing_fields": LIST},
                  "required": OBJECTIVE_KEYS + ["inferred_fields", "missing_fields"]},
    "plan": {"type": "object", "required": ["workstreams", "tasks"], "properties": {
        "workstreams": {"type": "array", "items": {"type": "object", "properties": {"id": S, "name": S},
                                                   "required": ["id", "name"]}},
        "tasks": {"type": "array", "items": {"type": "object", "properties": {
            "id": S, "workstream_id": S, "kind": {"type": "string", "enum": list(KIND_TIER)},
            "owner_worker_id": {"type": "string", "enum": ["w_cto", "w_pm", "w_eng_a", "w_eng_b"]}, "title": S,
            "inputs": S, "expected_output": S, "dependencies": LIST, "tools": LIST, "budget": {"type": "integer"},
            "deadline_day": {"type": "integer"}, "verification_method": S},
            "required": ["id", "workstream_id", "kind", "owner_worker_id", "title", "inputs", "expected_output",
                         "dependencies", "tools", "budget", "deadline_day", "verification_method"]}}}},
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


def _int(value, default: int) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return default


def validate_plan(plan: dict) -> dict:
    """The platform owns the rubric: a kind's risk tier and owner are not the model's call.

    Task ids are renumbered t_01, t_02 in plan order and dependencies follow them, because
    ids end up in URLs and decision ids; model text never becomes an identifier.
    """
    if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list) or not plan["tasks"]:
        raise IntelligenceError("plan has no tasks")
    if not all(isinstance(t, dict) for t in plan["tasks"]):
        raise IntelligenceError("every task must be an object")
    rename = {}
    for i, t in enumerate(plan["tasks"], start=1):
        old = str(t.get("id") or "").strip()
        new = f"t_{i:02d}"
        if old:
            rename[old] = new
        t["id"] = new
    ids = set()
    kinds = []
    for t in plan["tasks"]:
        for key in ("workstream_id", "kind", "owner_worker_id", "title"):
            if not str(t.get(key) or "").strip():
                raise IntelligenceError(f"{t['id']} is missing {key}")
            t[key] = str(t[key]).strip()
        if t["kind"] not in KIND_TIER:
            raise IntelligenceError(f"unknown task kind {t['kind']}")
        if t["owner_worker_id"] not in KIND_OWNERS[t["kind"]]:
            raise IntelligenceError(f"{t['id']}: {t['kind']} cannot be owned by {t['owner_worker_id']}")
        t["risk_tier"] = KIND_TIER[t["kind"]]
        deps = t.get("dependencies") or []
        if isinstance(deps, str):
            deps = [d for d in re.split(r"[,\s]+", deps) if d]
        if not isinstance(deps, list):
            raise IntelligenceError(f"{t['id']}: dependencies must be a list")
        t["dependencies"] = []
        for dep in deps:
            dep = rename.get(str(dep).strip(), str(dep).strip())
            if dep not in ids:
                raise IntelligenceError(f"{t['id']} depends on {dep}, which is not an earlier task")
            if dep not in t["dependencies"]:
                t["dependencies"].append(dep)
        ids.add(t["id"])
        kinds.append(t["kind"])
        for key in ("inputs", "expected_output", "verification_method"):
            t[key] = str(t.get(key) or "")
        t["tools"] = [str(x) for x in t.get("tools") or []] if isinstance(t.get("tools"), list) else []
        t["budget"] = _int(t.get("budget"), 10)
        t["deadline_day"] = _int(t.get("deadline_day"), 1)
    for kind, n in (("review_merge", 1), ("deploy", 1)):
        if kinds.count(kind) != n:
            raise IntelligenceError(f"plan needs exactly {n} {kind} task")
    if kinds[-1] != "deploy":
        raise IntelligenceError("deploy must be the last task")
    if "code" not in kinds:
        raise IntelligenceError("plan has no code task")
    ws = [w for w in (plan.get("workstreams") or []) if isinstance(w, dict) and w.get("id")]
    known = {w["id"] for w in ws}
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

    def plan(self, objective: dict, note: str = "") -> tuple[dict, dict]:
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

DELIVERY_CONTRACT = ("Delivery contract. The product is a Python 3.10 standard library web app. No third party "
                     "packages. app.py sits at the repository root and starts its HTTP server only under "
                     "`if __name__ == \"__main__\":`, on 127.0.0.1 and the port in the PORT environment variable. "
                     "It answers GET /health with 200 and GET / with 200 and the product's web page. It keeps its "
                     "data in the JSON file named by the DATA_FILE environment variable. Tests are unittest files "
                     "named test_*.py at the repository root; they must not need the network, and a test that "
                     "starts a server uses port 0. Every test in the repository is rerun with "
                     "`python -m unittest discover` on each change. File names are paths relative to the "
                     "repository root; Markdown documents are filed under docs/.")


class ModelSource:
    kind = "model"

    def __init__(self):
        resolved = model_adapter.resolve()
        if resolved is None:
            raise IntelligenceError("Live mode needs a model: in the desktop app, start one in the Model screen; "
                                    "otherwise a local model server (CYNQRA_LOCAL_BASE_URL or CYNQRA_OLLAMA_MODEL), "
                                    "or ANTHROPIC_API_KEY or OPENAI_API_KEY.")
        self.label = resolved["label"]
        self.last_text = ""  # the last raw reply, kept to show what a model wrote when it could not be read
        self.prompt_v2 = (HERE / "objective_prompt.txt").read_text(encoding="utf-8")

    def _call(self, prompt: str, max_tokens: int = 4000, files: bool = False, schema: dict | None = None) -> tuple[dict, dict]:
        """One model call. files=True: a JSON header followed by file blocks, so no constrained JSON mode."""

        def parse(text: str):
            data = _parse_json(text)
            if files:
                blocks = _file_blocks(text)
                if blocks and not (isinstance(data, dict) and isinstance(data.get("files"), dict) and data["files"]):
                    data = dict(data) if isinstance(data, dict) else {"result": "done"}
                    data["files"] = blocks
            return data

        out = model_adapter.complete(prompt, max_tokens=max_tokens, want_json=not files, schema=schema)
        if out.get("error"):
            raise IntelligenceError(out["error"])
        self.last_text = out["text"]
        data = parse(out["text"])
        no_files = files and isinstance(data, dict) and data.get("result") != "blocked" and not data.get("files")
        if not isinstance(data, dict) or no_files:
            again = ("\n\nYour reply had no files in the required layout. " + FILES_LAYOUT) if files else \
                "\n\nReply with only one JSON object."
            out2 = model_adapter.complete(prompt + again, max_tokens=max_tokens, want_json=not files, schema=schema,
                                          temperature=0.4)
            if out2.get("error"):
                raise IntelligenceError(out2["error"])
            self.last_text = out2["text"]
            data = parse(out2["text"])
            out["tokens_in"] += out2["tokens_in"]
            out["tokens_out"] += out2["tokens_out"]
        if not isinstance(data, dict):
            raise IntelligenceError("model did not return a JSON object")
        units = max(1, -(-(out["tokens_in"] + out["tokens_out"]) // 1000))
        usage = {"tokens_in": out["tokens_in"], "tokens_out": out["tokens_out"], "estimated": out["estimated"],
                 "label": out.get("model", self.label), "latency_s": out.get("latency_s", 0), "units": units}
        if out.get("speed"):
            usage.update(out["speed"])
        return data, usage

    @staticmethod
    def _ctx(objective: dict, rules: list[str]) -> str:
        fields = {k: objective.get(k, "") for k in ("product", "target_customer", "primary_outcome", "business_outcome",
                                                     "success_criteria", "constraints", "priorities")}
        r = "\n".join(f"* {x}" for x in rules) or "* none yet"
        return f"Confirmed objective:\n{json.dumps(fields, indent=1)}\nDecided rules:\n{r}\n"

    def structure_objective(self, messy: str) -> tuple[dict, dict]:
        data, usage = self._call(self.prompt_v2 + messy + "\n", max_tokens=1500, schema=SCHEMAS["objective"])
        empty = [k for k in OBJECTIVE_KEYS if not str(data.get(k) or "").strip()]
        if empty:
            # Small models (and strongly compressed ones) leave implied fields blank instead of inferring them. One
            # short follow-up for just those fields gives the founder a reading to check instead of a blank to fill.
            fields = {k: str(data.get(k) or "") for k in OBJECTIVE_KEYS}
            prompt = ("A founder described what they want built:\n" + messy.strip() + "\n\nThe structured objective so "
                      "far:\n" + json.dumps(fields, indent=1) + "\n\nThese fields are still empty: " + ", ".join(empty) +
                      ". For each one, write the most reasonable reading of the founder's words, one or two sentences, "
                      "without adding features, users or constraints they did not state or clearly imply. The founder "
                      "will check each one. Return JSON with exactly these keys.")
            schema = _closed({"type": "object", "properties": {k: S for k in empty}, "required": empty})
            try:
                more, usage2 = self._call(prompt, max_tokens=600, schema=schema)
            except IntelligenceError:
                return data, usage  # the founder fills the blanks on the confirm screen, as before
            filled = [k for k in empty if str(more.get(k) or "").strip()]
            data = dict(data)
            for k in filled:
                data[k] = str(more[k]).strip()
            data["inferred_fields"] = list(dict.fromkeys(list(data.get("inferred_fields") or []) + filled))
            data["missing_fields"] = [k for k in (data.get("missing_fields") or []) if k not in filled]
            for k in ("tokens_in", "tokens_out", "units"):
                usage[k] += usage2[k]
        return data, usage

    def plan(self, objective: dict, note: str = "") -> tuple[dict, dict]:
        prompt = (ROLE_TEXT["w_pm"] + "\n" + self._ctx(objective, []) + "\n" + DELIVERY_CONTRACT + "\n\n"
                  "Plan the work for the fixed organization: w_cto, w_pm, w_eng_a, w_eng_b. Use only these task kinds:\n"
                  "spec (owner w_pm): spec.md and acceptance.md.\n"
                  "decision (owner w_pm): exactly the one product rule the objective leaves open, for the founder.\n"
                  "code (owner w_eng_a or w_eng_b): 2 or 3 tasks, each producing Python files and test_*.py. "
                  "Exactly one code task owns app.py and the web page.\n"
                  "review_merge (owner w_cto): exactly one, after all code tasks.\n"
                  "deploy (owner w_cto): exactly one, the last task.\n"
                  "Ids t_01, t_02 and so on. dependencies may only name earlier tasks.\n"
                  + (f"The founder rejected the previous plan: {note}\n" if note else "") +
                  'Return JSON: {"workstreams": [{"id", "name"}], "tasks": [{"id", "workstream_id", "kind", '
                  '"owner_worker_id", "title", "inputs", "expected_output", "dependencies", "tools", "budget", '
                  '"deadline_day", "verification_method"}]}')
        data, usage = self._call(prompt, max_tokens=3000, schema=SCHEMAS["plan"])
        try:
            return validate_plan(data), usage
        except IntelligenceError as exc:
            data2, usage2 = self._call(prompt + f"\n\nYour previous plan was refused: {exc}. Return a corrected plan.",
                                       max_tokens=3000, schema=SCHEMAS["plan"])
            for k in ("tokens_in", "tokens_out", "units"):
                usage[k] += usage2[k]
            return validate_plan(data2), usage

    def assign(self, task: dict, objective: dict, rules: list[str], artifact_index: list[str], **_) -> tuple[dict, dict]:
        prompt = (ROLE_TEXT["w_pm"] + "\n" + self._ctx(objective, rules) + "\n" + DELIVERY_CONTRACT + "\n\n"
                  f"Assign task {task['id']} ({task['title']}) to {task['owner_worker_id']}. Expected output: "
                  f"{task['expected_output']}.\nArtifacts that exist: {json.dumps(artifact_index)}\n"
                  "List only the artifacts the engineer needs. Put every closed list or rule they must not invent "
                  "into acceptance_check.\n"
                  'Return JSON: {"artifacts": [ids], "context_ref": "...", "acceptance_check": "..."}')
        return self._call(prompt, max_tokens=1500, schema=SCHEMAS["handoff"])

    def work(self, task: dict, worker: str, objective: dict, rules: list[str], handoff: dict,
             inbox: dict[str, str], feedback: str = "", answers: list[dict] | None = None,
             previous: dict[str, str] | None = None, repo_files: list[str] | None = None, **_) -> tuple[dict, dict]:
        files = "".join(f"=== FILE: {k} ===\n{v.rstrip()}\n=== END FILE ===\n" for k, v in inbox.items()) or "none"
        extra = ""
        if answers:
            extra += "\nAnswers to your Blockers:\n" + "\n".join(a.get("acceptance_check", "") for a in answers)
        if feedback:
            extra += "\nYour last attempt failed a check. Fix it:\n" + feedback
            if previous:
                extra += ("\nYour previous files, to fix rather than rewrite from nothing:\n"
                          + "".join(f"=== FILE: {k} ===\n{v.rstrip()}\n=== END FILE ===\n" for k, v in previous.items()))
        kind = task["kind"]
        if kind in ("spec", "code"):
            shape = None
        else:
            shape = ('{"result": "proposal", "problem": "...", "recommendation": "...", "evidence_refs": [], '
                     '"cost": "...", "confidence": "low, medium or high", "what_would_change_this": "..."}')
        repo = f"Files already in the repository: {json.dumps(repo_files or [])}\n" if kind == "code" else ""
        prompt = (ROLE_TEXT.get(worker, "") + "\n" + self._ctx(objective, rules) + "\n" + DELIVERY_CONTRACT + "\n\n"
                  f"Task {task['id']}: {task['title']}. Expected output: {task['expected_output']}.\n"
                  f"Handoff: {json.dumps({k: handoff.get(k) for k in ('acceptance_check', 'context_ref', 'artifacts')})}\n"
                  f"{repo}Files handed to you:\n{files}\n{extra}\n"
                  "If a fact you need is missing and you would have to guess it, raise a Blocker instead.\n"
                  + (FILES_LAYOUT if shape is None else f"Return one JSON object: {shape}"))
        return self._call(prompt, max_tokens=8000 if kind == "code" else 3000, files=shape is None,
                          schema=None if shape is None else SCHEMAS["proposal"])

    def answer_blocker(self, task: dict, worker: str, objective: dict, rules: list[str], blocker: dict,
                       artifact_index: list[str], **_) -> tuple[dict, dict]:
        prompt = (ROLE_TEXT.get(worker, "") + "\n" + self._ctx(objective, rules) + "\n"
                  f"{blocker.get('raised_by')} raised a Blocker on {task['id']} ({task['title']}): "
                  f"{blocker.get('description')}\nArtifacts that exist: {json.dumps(artifact_index)}\n"
                  "Clear it using only the objective, the decided rules and the artifacts. If it needs a new product "
                  "decision, say so plainly and give the safest reading for now.\n"
                  'Return JSON: {"artifacts": [ids], "context_ref": "...", "acceptance_check": "the missing facts"}')
        return self._call(prompt, max_tokens=1500, schema=SCHEMAS["handoff"])


def make(mode: str, scenario_id: str = "candidate_tracker"):
    if mode == "live":
        return ModelSource()
    return ScriptedSource(scenario_id)
