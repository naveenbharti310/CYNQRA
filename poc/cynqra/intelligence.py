"""Intelligence sources. Book 0 section 10: a worker's identity stays when its intelligence changes.

ScriptedSource  demo mode. Every word comes from scenarios/<id>/scenario.json, and the
                product labels it. Code it hands over is real and gets tested for real.
ModelSource     live mode. Every call goes through model_adapter (ADR-4), the same
                adapter the spikes use. A model error stops the step; nothing is invented.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from . import model_adapter, roles

HERE = Path(__file__).resolve().parent
SCENARIOS = HERE.parent / "scenarios"

KIND_TIER = {"spec": "LOW", "decision": "MEDIUM", "code": "LOW", "review_merge": "MEDIUM", "deploy": "HIGH"}
SCRIPTED_UNITS_PER_CALL = 3


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


FILE_HEAD = re.compile(r"^[ \t>*#`]*={2,}[ \t]*FILE[ \t]*:?[ \t]*`?(?P<name>[\w./ -]+?)`?[ \t]*={2,}[ \t*`]*$", re.M | re.I)
FILE_END = re.compile(r"^[ \t>*#`]*={2,}[ \t]*END\b[^\n]*$", re.M | re.I)
FENCED = re.compile(r"^```[\w+-]*[ \t]*\n(?P<body>.*?)\n```[ \t]*$", re.S | re.M)
NAME = re.compile(r"(?<![\w/.-])(?P<name>[\w-]+(?:/[\w-]+)*\.(?:py|md|html|css|js|json|txt|toml|cfg|ini|yaml|yml))\b")


def files_layout(needs_from: str = "w_pm") -> str:
    return ("Return your answer in exactly this layout and nothing else. First one JSON object on its own:\n"
            '{"result": "done", "summary": "...", "acceptance_check": "..."}\n'
            "Then each file you write, exactly like this:\n"
            "=== FILE: name.ext ===\n"
            "the complete file content, exactly as it should be saved\n"
            "=== END FILE ===\n"
            "Write file contents as plain text, not escaped and not inside code fences. "
            'If a fact you need is missing, return only: {"result": "blocked", "category": "missing_input", '
            f'"description": "...", "needs_from": "{needs_from}"}}')


FILES_LAYOUT = files_layout()


S = {"type": "string"}
LIST = {"type": "array", "items": S}
OBJECTIVE_KEYS = ["product", "target_customer", "primary_outcome", "business_outcome", "success_criteria",
                  "constraints", "priorities"]
SCHEMAS = {
    "objective": {"type": "object", "properties": {**{k: S for k in OBJECTIVE_KEYS}, "inferred_fields": LIST,
                                                   "missing_fields": LIST},
                  "required": OBJECTIVE_KEYS + ["inferred_fields", "missing_fields"]},
    "requirements": {"type": "object", "required": ["outcomes", "requirements", "workstreams"], "properties": {
        "outcomes": LIST,
        "requirements": {"type": "array", "items": {"type": "object", "properties": {
            "id": S, "area": {"type": "string", "enum": roles.AREAS}, "text": S, "verification": S},
            "required": ["id", "area", "text", "verification"]}},
        "workstreams": {"type": "array", "items": {"type": "object", "properties": {
            "id": S, "name": S, "requirement_ids": LIST, "depends_on": LIST},
            "required": ["id", "name", "requirement_ids", "depends_on"]}}}},
    "workforce": {"type": "object", "required": ["summary", "roles"], "properties": {
        "summary": S,
        "roles": {"type": "array", "items": {"type": "object", "properties": {
            "role": {"type": "string", "enum": list(roles.ROLES)}, "quantity": {"type": "integer"}, "why": S,
            "requirement_ids": LIST}, "required": ["role", "quantity", "why", "requirement_ids"]}}}},
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
    """The roadmap's shape, with the owners this organization actually has."""
    return _closed({"type": "object", "required": ["workstreams", "milestones", "tasks"], "properties": {
        "workstreams": {"type": "array", "items": {"type": "object", "properties": {"id": S, "name": S},
                                                   "required": ["id", "name"]}},
        "milestones": {"type": "array", "items": {"type": "object", "properties": {
            "id": S, "name": S, "due_day": {"type": "integer"}}, "required": ["id", "name", "due_day"]}},
        "tasks": {"type": "array", "items": {"type": "object", "properties": {
            "id": S, "workstream_id": S, "milestone_id": S, "kind": {"type": "string", "enum": list(KIND_TIER)},
            "owner_worker_id": {"type": "string", "enum": list(worker_ids)}, "title": S,
            "inputs": S, "expected_output": S, "acceptance_criteria": LIST, "requirement_ids": LIST,
            "dependencies": LIST, "tools": LIST, "budget": {"type": "integer"},
            "deadline_day": {"type": "integer"}, "verification_method": S},
            "required": ["id", "workstream_id", "milestone_id", "kind", "owner_worker_id", "title", "inputs",
                         "expected_output", "acceptance_criteria", "requirement_ids", "dependencies", "tools",
                         "budget", "deadline_day", "verification_method"]}}}})


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


def _int(value, default: int) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return default


AREA_ALIASES = {"ai": "ai_ml", "ml": "ai_ml", "ai/ml": "ai_ml", "machine_learning": "ai_ml", "nonfunctional": "non_functional",
                "non-functional": "non_functional", "ux": "design", "ui": "design", "testing": "qa", "quality": "qa",
                "infrastructure": "devops", "ops": "devops", "deploy": "deployment", "business": "product"}


def _slug_list(value) -> list[str]:
    if isinstance(value, str):
        value = [v for v in re.split(r"[,\s]+", value) if v]
    return [str(v).strip() for v in value or [] if str(v).strip()] if isinstance(value, list) else []


def validate_requirements(pkg: dict) -> dict:
    """Stage 1's objective package, checked by the platform: known areas, ids it owns (r_01, ws_01), workstreams that
    hold every requirement, dependencies without cycles, and the critical path computed from them."""
    if not isinstance(pkg, dict) or not isinstance(pkg.get("requirements"), list) or not pkg["requirements"]:
        raise IntelligenceError("the objective package has no requirements")
    rename, reqs = {}, []
    for i, r in enumerate(pkg["requirements"], start=1):
        if not isinstance(r, dict) or not str(r.get("text") or "").strip():
            raise IntelligenceError(f"requirement {i} has no text")
        area = str(r.get("area") or "").strip().lower().replace(" ", "_")
        area = AREA_ALIASES.get(area, area)
        if area not in roles.AREAS:
            raise IntelligenceError(f"requirement {i}: unknown area {r.get('area')!r}; use one of {', '.join(roles.AREAS)}")
        rid = f"r_{i:02d}"
        if str(r.get("id") or "").strip():
            rename[str(r["id"]).strip()] = rid
        reqs.append({"id": rid, "area": area, "text": str(r["text"]).strip(),
                     "verification": str(r.get("verification") or "").strip()})
    known = {r["id"] for r in reqs}
    ws_in = [w for w in pkg.get("workstreams") or [] if isinstance(w, dict) and str(w.get("name") or w.get("id") or "").strip()]
    ws_rename = {str(w.get("id") or "").strip(): f"ws_{i:02d}" for i, w in enumerate(ws_in, start=1)}
    workstreams, placed = [], set()
    for i, w in enumerate(ws_in, start=1):
        ids = [rename.get(x, x) for x in _slug_list(w.get("requirement_ids"))]
        ids = [x for x in dict.fromkeys(ids) if x in known and x not in placed]
        placed.update(ids)
        deps = [ws_rename.get(x) for x in _slug_list(w.get("depends_on"))]
        workstreams.append({"id": f"ws_{i:02d}", "name": str(w.get("name") or w.get("id")).strip(),
                            "requirement_ids": ids, "depends_on": [d for d in dict.fromkeys(deps) if d]})
    loose = [r["id"] for r in reqs if r["id"] not in placed]
    if loose:  # every requirement belongs to some workstream; the platform says when it had to place one
        workstreams.append({"id": f"ws_{len(workstreams) + 1:02d}", "name": "Other requirements",
                            "requirement_ids": loose, "depends_on": [], "placed_by": "platform"})
    ids = [w["id"] for w in workstreams]
    for w in workstreams:  # a dependency on itself or on a later workstream that loops back is dropped
        w["depends_on"] = [d for d in w["depends_on"] if d in ids and d != w["id"]]
    order, seen = [], set()

    def visit(wid, stack=()):
        if wid in stack:
            raise IntelligenceError(f"workstream dependencies loop through {wid}")
        if wid in seen:
            return
        for d in next(x for x in workstreams if x["id"] == wid)["depends_on"]:
            visit(d, stack + (wid,))
        seen.add(wid)
        order.append(wid)
    for wid in ids:
        visit(wid)
    longest: dict[str, list[str]] = {}
    for wid in order:
        w = next(x for x in workstreams if x["id"] == wid)
        best = max((longest[d] for d in w["depends_on"]), key=len, default=[])
        longest[wid] = best + [wid]
    critical = max(longest.values(), key=len, default=[])
    outs = pkg.get("outcomes")
    outs = [outs] if isinstance(outs, str) else outs if isinstance(outs, list) else []
    return {"outcomes": [str(x).strip() for x in outs if str(x).strip()],
            "requirements": reqs, "workstreams": workstreams, "critical_path": critical,
            "verification": [f"{r['id']}: {r['verification']}" for r in reqs if r["verification"]]}


def validate_workforce(prop: dict, pkg: dict) -> dict:
    """Stage 2's proposal, checked by the platform against the role catalog and the requirements:
    known roles within their limits; every requirement covered by a proposed role whose areas include it; and the
    roles the delivery pipeline cannot run without (someone to write code, a CTO to review and merge, someone to
    assign work and to deploy)."""
    if not isinstance(prop, dict) or not isinstance(prop.get("roles"), list) or not prop["roles"]:
        raise IntelligenceError("the workforce proposal has no roles")
    merged: dict[str, dict] = {}
    for r in prop["roles"]:
        if not isinstance(r, dict):
            raise IntelligenceError("every role must be an object")
        name = str(r.get("role") or "").strip()
        if name not in roles.ROLES:
            raise IntelligenceError(f"{name!r} is not in the role catalog")
        q = _int(r.get("quantity"), 1) or 1
        m = merged.setdefault(name, {"role": name, "quantity": 0, "why": "", "requirement_ids": []})
        m["quantity"] += q
        m["why"] = (m["why"] + " " + str(r.get("why") or "").strip()).strip()
        m["requirement_ids"] += [x for x in _slug_list(r.get("requirement_ids")) if x not in m["requirement_ids"]]
    for m in merged.values():
        cap = roles.role(m["role"])["max"]
        if m["quantity"] > cap:
            raise IntelligenceError(f"{m['role']}: {m['quantity']} proposed, the catalog allows at most {cap}")
        if not m["why"]:
            raise IntelligenceError(f"{m['role']}: say why the role is needed")
    total = sum(m["quantity"] for m in merged.values())
    if total > roles.MAX_WORKERS:
        raise IntelligenceError(f"{total} workers proposed; at most {roles.MAX_WORKERS}")
    reqs = {r["id"]: r for r in pkg["requirements"]}
    coverage: dict[str, list[str]] = {rid: [] for rid in reqs}
    for m in merged.values():
        areas = roles.role(m["role"])["areas"]
        m["requirement_ids"] = [x for x in m["requirement_ids"] if x in reqs and reqs[x]["area"] in areas]
        for rid in m["requirement_ids"]:
            coverage[rid].append(m["role"])
    for rid, r in reqs.items():  # a requirement no proposed role claimed goes to a proposed role that covers its area
        if not coverage[rid]:
            fit = [m for m in merged.values() if r["area"] in roles.role(m["role"])["areas"]]
            if not fit:
                raise IntelligenceError(f"{rid} ({r['area']}: {r['text'][:80]}) is covered by no proposed role")
            fit[0]["requirement_ids"].append(rid)
            coverage[rid].append(fit[0]["role"])
    workers = roles.instantiate(list(merged.values()))
    needs = [("code", "write the product's code"), ("review_merge", "review and merge the release"),
             ("deploy", "propose the production deploy")]
    for kind, what in needs:
        if not roles.owners_of(kind, workers):
            raise IntelligenceError(f"no proposed role can {what} ({kind}); the catalog says who can")
    if roles.assigner(workers) is None:
        raise IntelligenceError("no proposed role can assign work (a Project Manager, CTO or CEO)")
    return {"summary": str(prop.get("summary") or "").strip(), "roles": list(merged.values()), "coverage": coverage,
            "workers": workers}


def validate_plan(plan: dict, workers: list[dict], requirement_ids: list[str] | None = None) -> dict:
    """The platform owns the rubric: a kind's risk tier, and which roles may own it, are not the model's call.

    Task ids are renumbered t_01, t_02 in plan order and dependencies follow them, because ids end up in URLs and
    decision ids; model text never becomes an identifier. Milestones and acceptance criteria a model left out are
    derived from the workstreams and the expected output, and marked as derived.
    """
    if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list) or not plan["tasks"]:
        raise IntelligenceError("plan has no tasks")
    if not all(isinstance(t, dict) for t in plan["tasks"]):
        raise IntelligenceError("every task must be an object")
    by_id = {w["id"]: w for w in workers}
    rename = {}
    for i, t in enumerate(plan["tasks"], start=1):
        old = str(t.get("id") or "").strip()
        new = f"t_{i:02d}"
        if old:
            rename[old] = new
        t["id"] = new
    ids = set()
    kinds = []
    known_req = set(requirement_ids or [])
    for t in plan["tasks"]:
        for key in ("workstream_id", "kind", "owner_worker_id", "title"):
            if not str(t.get(key) or "").strip():
                raise IntelligenceError(f"{t['id']} is missing {key}")
            t[key] = str(t[key]).strip()
        if t["kind"] not in KIND_TIER:
            raise IntelligenceError(f"unknown task kind {t['kind']}")
        owner = by_id.get(t["owner_worker_id"])
        if owner is None:
            raise IntelligenceError(f"{t['id']}: {t['owner_worker_id']} is not a worker in this organization")
        if t["kind"] not in roles.role(owner["role"])["owns"]:
            may = ", ".join(roles.owners_of(t["kind"], workers))
            raise IntelligenceError(f"{t['id']}: {t['kind']} cannot be owned by {t['owner_worker_id']} "
                                    f"({owner['role']}); it can be owned by {may}")
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
        t["deadline_day"] = _int(t.get("deadline_day"), 1) or 1
        crit = t.get("acceptance_criteria")
        crit = [crit] if isinstance(crit, str) else crit
        t["acceptance_criteria"] = [str(x).strip() for x in crit or [] if str(x).strip()]
        if not t["acceptance_criteria"]:
            t["acceptance_criteria"] = [t["expected_output"] or t["title"]]
            t["acceptance_derived"] = True
        t["requirement_ids"] = [x for x in _slug_list(t.get("requirement_ids")) if not known_req or x in known_req]
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
    ms = [{"id": str(m.get("id")).strip(), "name": str(m.get("name") or m.get("id")).strip(),
           "due_day": _int(m.get("due_day"), 0)} for m in plan.get("milestones") or []
          if isinstance(m, dict) and str(m.get("id") or "").strip()]
    if not ms:  # one milestone per workstream, in plan order, said to be derived
        for w in ws:
            ms.append({"id": "m_" + w["id"], "name": w["name"], "due_day": 0, "derived": True})
        for t in plan["tasks"]:
            t["milestone_id"] = "m_" + t["workstream_id"]
    mids = {m["id"] for m in ms}
    for t in plan["tasks"]:
        if str(t.get("milestone_id") or "").strip() not in mids:
            t["milestone_id"] = ms[-1]["id"] if t["kind"] in ("review_merge", "deploy") else ms[0]["id"]
    for m in ms:
        own = [t for t in plan["tasks"] if t["milestone_id"] == m["id"]]
        m["task_ids"] = [t["id"] for t in own]
        m["due_day"] = max([m["due_day"]] + [t["deadline_day"] for t in own])
    plan["milestones"] = [m for m in ms if m["task_ids"]]
    uncovered = [r for r in (requirement_ids or []) if not any(r in t["requirement_ids"] for t in plan["tasks"])]
    plan["uncovered_requirements"] = uncovered
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

    def decompose(self, objective: dict, **_) -> tuple[dict, dict]:
        return validate_requirements(json.loads(json.dumps(self.data["requirements"]))), self._usage()

    def synthesize(self, objective: dict, requirements: dict, note: str = "", **_) -> tuple[dict, dict]:
        return validate_workforce(json.loads(json.dumps(self.data["workforce"])), requirements), self._usage()

    def plan(self, objective: dict, note: str = "", workers: list[dict] | None = None,
             requirements: dict | None = None, **_) -> tuple[dict, dict]:
        workers = workers or roles.instantiate(roles.FIXTURE_M1)
        rids = [r["id"] for r in (requirements or {}).get("requirements", [])]
        return validate_plan(json.loads(json.dumps(self.data["plan"])), workers, rids), self._usage()

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


class ModelSource:
    kind = "model"

    def __init__(self, router=None):
        # router(worker) -> (model_id, route): each worker's calls go to the model it is assigned now. Without
        # one, every call goes to the single model the environment names.
        self.router = router
        resolved = {"label": "workforce"} if router else model_adapter.resolve()
        if resolved is None:
            raise IntelligenceError("Live mode needs a model: in the desktop app, start one in the Model screen; "
                                    "otherwise a local model server (CYNQRA_LOCAL_BASE_URL or CYNQRA_OLLAMA_MODEL), "
                                    "or ANTHROPIC_API_KEY or OPENAI_API_KEY.")
        self.label = resolved["label"]
        self.last_text = ""  # the last raw reply, kept to show what a model wrote when it could not be read
        self.answered: dict[str, int] = {}  # prompt digest -> replies already received for exactly that prompt
        self.prompt_v2 = (HERE / "objective_prompt.txt").read_text(encoding="utf-8")

    def _call(self, prompt: str, max_tokens: int = 4000, files: bool = False, schema: dict | None = None,
              worker: str = "system") -> tuple[dict, dict]:
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
        model_id, route = self.router(worker) if self.router else (None, None)
        key = hashlib.sha256(f"{model_id}|{prompt}".encode("utf-8")).hexdigest()
        repeats = self.answered.get(key, 0)
        out = model_adapter.complete(prompt, max_tokens=max_tokens, want_json=not files, schema=schema,
                                     temperature=round(min(0.3 * repeats, 0.9), 1) if repeats else None, partial=files,
                                     route=route)
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
            again = ("\n\nYour reply had no files in the required layout. " + files_layout(
                re.search(r'"needs_from": "(\w+)"', prompt).group(1) if '"needs_from": "' in prompt else "w_pm")) if files else \
                "\n\nReply with only one JSON object."
            out2 = model_adapter.complete(prompt + again, max_tokens=max_tokens, want_json=not files, schema=schema,
                                          temperature=0.4, route=route)
            if out2.get("error"):
                raise IntelligenceError(out2["error"], model_id=model_id, usage=out2)
            self.last_text = out2["text"]
            data = parse(out2["text"])
            out["tokens_in"] += out2["tokens_in"]
            out["tokens_out"] += out2["tokens_out"]
        if not isinstance(data, dict):
            raise IntelligenceError("model did not return a JSON object")
        units = max(1, -(-(out["tokens_in"] + out["tokens_out"]) // 1000))
        usage = {"tokens_in": out["tokens_in"], "tokens_out": out["tokens_out"], "estimated": out["estimated"],
                 "label": out.get("model", self.label), "latency_s": out.get("latency_s", 0), "units": units,
                 "model_id": model_id}
        if out.get("speed"):
            usage.update(out["speed"])
        return data, usage

    @staticmethod
    def _head(persona: str, objective: dict, rules: list[str]) -> str:
        """The start of every role's prompt. What stays the same through a run comes first (the contract, the
        objective, then the rules, which only grow), the role after it: a local server reuses its cache for the
        part a prompt shares with the one before, so a change of speaker no longer means reading it all again."""
        return DELIVERY_CONTRACT + "\n\n" + ModelSource._ctx(objective, rules) + "\n" + (persona or "") + "\n\n"

    @staticmethod
    def _ctx(objective: dict, rules: list[str]) -> str:
        fields = {k: objective.get(k, "") for k in ("product", "target_customer", "primary_outcome", "business_outcome",
                                                     "success_criteria", "constraints", "priorities")}
        stated = {k: v for k, v in (objective.get("_constraints") or {}).items() if v}
        r = "\n".join(f"* {x}" for x in rules) or "* none yet"
        return (f"Objective:\n{json.dumps(fields, indent=1)}\n"
                + (f"Constraints the founder set: {json.dumps(stated)}\n" if stated else "")
                + f"Decided rules:\n{r}\n")

    def _checked(self, prompt: str, schema: dict, check, max_tokens: int, worker: str = "system"):
        """A call whose answer the platform validates; one retry with the reason when it is refused."""
        data, usage = self._call(prompt, max_tokens=max_tokens, schema=schema, worker=worker)
        try:
            return check(data), usage
        except IntelligenceError as exc:
            data2, usage2 = self._call(prompt + f"\n\nYour previous answer was refused: {exc}. Return a corrected one.",
                                       max_tokens=max_tokens, schema=schema, worker=worker)
            for k in ("tokens_in", "tokens_out", "units"):
                usage[k] += usage2[k]
            return check(data2), usage

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

    def decompose(self, objective: dict, **_) -> tuple[dict, dict]:
        """Stage 1: the objective as requirements, workstreams and their dependencies."""
        prompt = (self._head("You are Cynqra's Objective Intelligence.", objective, []) +
                  "Decompose the objective into requirements. Cover, where the objective calls for them: product "
                  "outcomes and success criteria, functional and non-functional requirements, AI/ML and data "
                  "requirements, design, security, QA, DevOps and deployment. Each requirement has an area, one of "
                  f"{', '.join(roles.AREAS)}, a sentence, and how it will be verified. Group the requirements into "
                  "engineering workstreams and say which workstreams depend on which. Add nothing the founder did "
                  "not state or clearly imply.\n"
                  'Return JSON: {"outcomes": ["..."], "requirements": [{"id": "r_01", "area", "text", '
                  '"verification"}], "workstreams": [{"id", "name", "requirement_ids", "depends_on"}]}')
        return self._checked(prompt, SCHEMAS["requirements"], validate_requirements, 3000)

    def synthesize(self, objective: dict, requirements: dict, note: str = "", **_) -> tuple[dict, dict]:
        """Stage 2: the organization this objective needs, from the role catalog."""
        cat = "\n".join(f"* {r['role']}: {r['title']}. {r['charter']} Covers: {', '.join(r['areas'])}. "
                        f"Owns: {', '.join(r['owns'])}. At most {r['max']}." for r in roles.catalog())
        reqs = "\n".join(f"* {r['id']} ({r['area']}): {r['text']}" for r in requirements["requirements"])
        prompt = (self._head("You are Cynqra's Workforce Synthesizer.", objective, []) +
                  "Synthesize the workforce for this objective from the role catalog: which roles, how many of each, "
                  "and why each is required. Propose the smallest organization that covers every requirement; do not "
                  "add a role the requirements do not need. Merges into main need a CTO, and someone must assign "
                  "work and propose the deploy.\n"
                  f"Role catalog:\n{cat}\nRequirements:\n{reqs}\n"
                  + (f"The founder rejected the previous proposal: {note}\n" if note else "") +
                  'Return JSON: {"summary": "...", "roles": [{"role", "quantity", "why", "requirement_ids"}]}')
        return self._checked(prompt, SCHEMAS["workforce"], lambda d: validate_workforce(d, requirements), 2000)

    def plan(self, objective: dict, note: str = "", workers: list[dict] | None = None,
             requirements: dict | None = None, planner: str = "system", persona: str = "") -> tuple[dict, dict]:
        """Stage 5: the roadmap for this organization."""
        workers = workers or roles.instantiate(roles.FIXTURE_M1)
        org = "\n".join(f"* {w['id']}: {w['title']} ({w['role']}), may own {', '.join(roles.role(w['role'])['owns'])}"
                        for w in workers)
        reqs = requirements["requirements"] if requirements else []
        rlist = "\n".join(f"* {r['id']} ({r['area']}): {r['text']}" for r in reqs) or "* none"
        prompt = (self._head(persona, objective, []) +
                  f"Plan the work for this organization:\n{org}\nRequirements:\n{rlist}\n"
                  "Break the objective into milestones and workstreams, and the workstreams into tasks. Give each task "
                  "to the worker best positioned to do it, with acceptance criteria that can be checked and the "
                  "requirement ids it satisfies. Use only these task kinds:\n"
                  "spec: documents (specs, acceptance checks, designs, test plans, runbooks) as Markdown.\n"
                  "decision: exactly the one product rule the objective leaves open, for the founder.\n"
                  "code: Python files and test_*.py. Exactly one code task owns app.py and the web page.\n"
                  "review_merge: exactly one, after all code tasks.\n"
                  "deploy: exactly one, the last task.\n"
                  "A task's owner must be a worker who may own its kind. Ids t_01, t_02 and so on; dependencies may "
                  "only name earlier tasks.\n"
                  + (f"The founder rejected the previous roadmap: {note}\n" if note else "") +
                  'Return JSON: {"workstreams": [{"id", "name"}], "milestones": [{"id", "name", "due_day"}], '
                  '"tasks": [{"id", "workstream_id", "milestone_id", "kind", "owner_worker_id", "title", "inputs", '
                  '"expected_output", "acceptance_criteria", "requirement_ids", "dependencies", "tools", "budget", '
                  '"deadline_day", "verification_method"}]}')
        rids = [r["id"] for r in reqs]
        return self._checked(prompt, plan_schema([w["id"] for w in workers]),
                             lambda d: validate_plan(d, workers, rids), 4000, worker=planner)

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
        if kind in ("spec", "code"):
            shape = None
        else:
            shape = ('{"result": "proposal", "problem": "...", "recommendation": "...", "evidence_refs": [], '
                     '"cost": "...", "confidence": "low, medium or high", "what_would_change_this": "..."}')
        repo = f"Files already in the repository: {json.dumps(repo_files or [])}\n" if kind == "code" else ""
        limit = _int(os.environ.get("CYNQRA_NUM_PREDICT"), 0) if shape is None else 0
        if limit:  # a local model's reply is capped; a longer one is cut off, and the files it finished are kept
            extra += (f"\nA reply holds at most about {limit} tokens. If the work needs more, send the most important "
                      "files first and keep each file short; you will be asked for the rest.")
        crit = "; ".join(task.get("acceptance_criteria") or [])
        who = answerers or ["w_pm"]
        prompt = (self._head(persona, objective, rules) +
                  f"Task {task['id']}: {task['title']}. Expected output: {task['expected_output']}.\n"
                  + (f"Acceptance criteria: {crit}\n" if crit else "") +
                  f"Handoff: {json.dumps({k: handoff.get(k) for k in ('acceptance_check', 'context_ref', 'artifacts')})}\n"
                  f"{repo}Files handed to you:\n{files}\n{extra}\n"
                  "If a fact you need is missing and you would have to guess it, raise a Blocker instead; "
                  f"needs_from names who can answer it: {', '.join(who)}.\n"
                  + (files_layout(who[0]) if shape is None else f"Return one JSON object: {shape}"))
        return self._call(prompt, max_tokens=8000 if kind == "code" else 3000, files=shape is None,
                          schema=None if shape is None else SCHEMAS["proposal"], worker=worker)

    def answer_blocker(self, task: dict, worker: str, objective: dict, rules: list[str], blocker: dict,
                       artifact_index: list[str], persona: str = "", **_) -> tuple[dict, dict]:
        prompt = (self._head(persona, objective, rules) +
                  f"{blocker.get('raised_by')} raised a Blocker on {task['id']} ({task['title']}): "
                  f"{blocker.get('description')}\nArtifacts that exist: {json.dumps(artifact_index)}\n"
                  "Clear it using only the objective, the decided rules and the artifacts. If it needs a new product "
                  "decision, say so plainly and give the safest reading for now.\n"
                  'Return JSON: {"artifacts": [ids], "context_ref": "...", "acceptance_check": "the missing facts"}')
        return self._call(prompt, max_tokens=1500, schema=SCHEMAS["handoff"], worker=worker)


def make(mode: str, scenario_id: str = "candidate_tracker"):
    if mode == "live":
        return ModelSource()
    return ScriptedSource(scenario_id)
