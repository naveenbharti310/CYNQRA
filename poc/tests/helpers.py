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
# A connected model's automatic evaluation makes real calls in the background; a test that wants it turns it on.
os.environ.setdefault("CYNQRA_AUTO_EVALUATE", "0")
# Release dates come from a public catalogue on the internet; a test that needs them serves its own.
os.environ.setdefault("CYNQRA_MODEL_DATES_URL", "0")

from cynqra.engine import Engine  # noqa: E402
from cynqra.intelligence import ModelSource  # noqa: E402

SCENARIO = json.loads((POC / "scenarios" / "candidate_tracker" / "scenario.json").read_text(encoding="utf-8"))
RESTAURANT = json.loads((POC / "scenarios" / "restaurant_forecast" / "scenario.json").read_text(encoding="utf-8"))
# The M1 build's fixed organization: one instantiation of the role catalog, used where a test needs a small one.
M1_ROLES = [{"role": "CTO", "quantity": 1}, {"role": "PM", "quantity": 1}, {"role": "Engineer", "quantity": 2}]
FAKE_MODEL = POC / "tests" / "fake_model.py"
MODEL_ENV = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CYNQRA_S1_MODEL_CMD", "CYNQRA_MODEL", "CYNQRA_EFFORT",
             "CYNQRA_OLLAMA_MODEL", "OLLAMA_HOST", "CYNQRA_LOCAL_BASE_URL", "CYNQRA_NUM_CTX", "CYNQRA_THINK",
             "CYNQRA_TEMPERATURE", "CYNQRA_TIMEOUT", "CYNQRA_REPORTS_DIR", "CYNQRA_DATA_DIR",
             "CYNQRA_NUM_PREDICT", "CYNQRA_SEED", "CYNQRA_KEEP_ALIVE", "CYNQRA_LLAMA_SERVER", "CYNQRA_HF_BASE",
             "HF_TOKEN", "CYNQRA_HF_MODEL", "HF_ROUTER_URL", "CYNQRA_PRICE_PER_M",
             "CYNQRA_ANTHROPIC_URL", "CYNQRA_OPENAI_URL")


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


class EnvAccess:
    """What the environment names, connected through a real Intelligence Layer (connection, credential reference,
    adapter, gateway), as a live run with nothing else connected is. Each test gets its own control plane."""

    def __init__(self):
        from cynqra.intelligence_layer import IntelligenceSupply
        self.dir = tempfile.mkdtemp(prefix="cynqra_env_")
        self.supply = IntelligenceSupply(Path(self.dir))
        self.entries = self.supply.connect_environment()
        if not self.entries:
            raise AssertionError("the environment names no intelligence")
        self.model_id = self.entries[0]["id"]

    def intelligence_for(self, worker: str) -> str:
        return self.model_id

    def invoke(self, worker: str, request: dict) -> dict:
        return self.supply.gateway.invoke(self.model_id, request)


def env_source() -> ModelSource:
    """A model source bound to the intelligence the environment names, through the Intelligence Gateway."""
    src = ModelSource()
    src.bind(EnvAccess())
    return src


def fake_model_cmd(fail: bool = False) -> str:
    return f'"{sys.executable}" "{FAKE_MODEL}"' + (" --fail" if fail else "")


def approve(e: Engine, kind: str, action: str = "approve", **kw) -> dict:
    d = [x for x in e.pending_decisions() if x["kind"] == kind][0]
    return e.decide(d["id"], action, **kw)


def engine_to_gates(e: Engine) -> Engine:
    """The founder's steps 2 to 4: approve the plan, define themselves (keeping the profile they have), then approve
    the team and the budget."""
    approve(e, "approve_workforce")
    e.define_founder()
    approve(e, "approve_roadmap")
    return e


def engine_to_running(folder: Path, mode: str = "demo", scenario: str = "candidate_tracker", budget_usd=None,
                      governance: dict | None = None, **engine_kw) -> Engine:
    e = Engine(folder, **engine_kw)
    e.create_company("Harbor Recruiting", mode, scenario)
    messy = json.loads((POC / "scenarios" / scenario / "scenario.json").read_text(encoding="utf-8"))["messy"] \
        if mode == "demo" else SCENARIO["messy"]
    e.draft_objective(messy)
    if budget_usd is not None or governance:
        e.set_guardrails(budget_usd=budget_usd, governance=governance)
    e.submit_objective()
    return engine_to_gates(e)


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
        if e.meta["phase"] == "founder":  # step 3: the founder defines themselves, then the team and budget follow
            e.define_founder()
        if e.meta["phase"] == "accepted":
            break
    return answered
