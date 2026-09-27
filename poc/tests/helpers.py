"""Shared test helpers. Every test works in its own temporary folder."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

POC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(POC))

from cynqra.engine import Engine  # noqa: E402

SCENARIO = json.loads((POC / "scenarios" / "candidate_tracker" / "scenario.json").read_text(encoding="utf-8"))
FAKE_MODEL = POC / "tests" / "fake_model.py"
MODEL_ENV = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CYNQRA_S1_MODEL_CMD", "CYNQRA_MODEL", "CYNQRA_EFFORT",
             "CYNQRA_OLLAMA_MODEL", "OLLAMA_HOST", "CYNQRA_LOCAL_BASE_URL", "CYNQRA_NUM_CTX", "CYNQRA_THINK",
             "CYNQRA_TEMPERATURE", "CYNQRA_TIMEOUT", "CYNQRA_SELF_CHECKS", "CYNQRA_REPORTS_DIR", "CYNQRA_DATA_DIR",
             "CYNQRA_NUM_PREDICT", "CYNQRA_SEED", "CYNQRA_KEEP_ALIVE", "CYNQRA_LLAMA_SERVER", "CYNQRA_HF_BASE",
             "HF_TOKEN", "CYNQRA_HF_MODEL", "HF_ROUTER_URL", "CYNQRA_PRICE_PER_M")


class TempDir:
    def __init__(self):
        self.path = Path(tempfile.mkdtemp(prefix="cynqra_poc_"))

    def cleanup(self):
        shutil.rmtree(self.path, ignore_errors=True)


def no_model_env():
    saved = {k: os.environ.pop(k) for k in MODEL_ENV if k in os.environ}
    return saved


def restore_env(saved: dict):
    for k in MODEL_ENV:
        os.environ.pop(k, None)
    os.environ.update(saved)


def fake_model_cmd(fail: bool = False) -> str:
    return f'"{sys.executable}" "{FAKE_MODEL}"' + (" --fail" if fail else "")


def engine_to_running(folder: Path, cap: int = 120, mode: str = "demo") -> Engine:
    e = Engine(folder)
    e.create_company("Harbor Recruiting", mode)
    e.draft_objective(SCENARIO["messy"])
    e.set_guardrails(budget_cap=cap)
    e.confirm_objective()
    plan = [d for d in e.pending_decisions() if d["kind"] == "approve_plan"][0]
    e.decide(plan["id"], "approve")
    return e


def run_journey(e: Engine, answer: str = "approve", max_rounds: int = 20) -> list[dict]:
    """Step until idle, answer the first pending decision, repeat until accepted."""
    answered = []
    for _ in range(max_rounds):
        e.run_until_idle()
        pend = e.pending_decisions()
        if not pend:
            break
        d = pend[0]
        answered.append(d)
        e.decide(d["id"], answer)
        if e.meta["phase"] == "accepted":
            break
    return answered
