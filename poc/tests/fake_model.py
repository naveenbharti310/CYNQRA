#!/usr/bin/env python3
"""Test double for live mode. NOT a model and never a result.

Two ways in, both exactly the way a real model is reached:
  1. as a shell command through CYNQRA_S1_MODEL_CMD (prompt on stdin, text on stdout)
  2. through FakeProvider in test_adapter.py, which speaks the Anthropic and OpenAI
     HTTP wire formats on localhost and calls answer() below

Either way the live path (ModelSource, model_adapter, parse, engine) runs end to end.
It answers each prompt with the prepared scenario, choosing by the prompt's own words.

--fail makes the command exit 1, to prove a model error stops the run instead of being papered over.
"""
import json
import sys
from pathlib import Path

SCEN_DIR = Path(__file__).resolve().parent.parent / "scenarios" / "candidate_tracker"
S = json.loads((SCEN_DIR / "scenario.json").read_text(encoding="utf-8"))


def _resolve(obj):
    if isinstance(obj, str) and obj.startswith("@files/"):
        return (SCEN_DIR / obj[1:]).read_text(encoding="utf-8")
    if isinstance(obj, dict):
        return {k: _resolve(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve(v) for v in obj]
    return obj


def _task_in(prompt: str, prefix: str):
    for i in range(1, 10):
        tid = f"t_0{i}"
        if f"{prefix}{tid}" in prompt:
            return tid
    return None


def answer(prompt: str) -> str:
    if "Convert the founder objective" in prompt:
        out = S["objective"]
    elif "Decompose the objective into requirements" in prompt:
        out = S["requirements"]
    elif "choose the cofounders this company needs" in prompt:
        out = {"summary": S["workforce"]["summary"], "cofounders": S["workforce"]["cofounders"]}
    elif "Propose the team you need for your own area" in prompt:
        lead = next((c for c in S["workforce"]["teams"] if f"(w_{c.lower()})" in prompt), None)
        out = S["workforce"]["teams"].get(lead) or {"summary": "", "roles": []}
    elif "You are the independent challenger of a proposed team" in prompt:
        out = S.get("challenge") or {"seats": [], "failure_stories": []}
    elif "Review it as the cofounder accountable for this area" in prompt:
        out = S.get("review_default") or {"verdict": "approve", "note": "Checked against the handoff. Approved."}
    elif "Plan the work for this organization" in prompt:
        out = S["plan"]
    elif _task_in(prompt, "Assign task "):
        out = S["assign"][_task_in(prompt, "Assign task ")]
    elif "raised a Blocker on" in prompt:
        out = S["answer_blocker"][_task_in(prompt, "raised a Blocker on ")]
    elif _task_in(prompt, "Task "):
        tid = _task_in(prompt, "Task ")
        items = S["work"][tid]
        if tid == "t_03":
            out = items[1] if "failed a check" in prompt else items[0]
        elif tid == "t_04":
            out = items[1] if "Answers to your Blockers" in prompt else items[0]
        else:
            out = items[-1]
    else:
        out = {"note": "fake model has no answer for this prompt"}
    return "```json\n" + json.dumps(_resolve(out)) + "\n```"


if __name__ == "__main__":
    if "--fail" in sys.argv:
        sys.stderr.write("fake model asked to fail\n")
        sys.exit(1)
    print(answer(sys.stdin.read()))
