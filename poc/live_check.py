#!/usr/bin/env python3
"""Real model test of the whole POC journey. Spends real money; nothing here is simulated.

  export ANTHROPIC_API_KEY=...          (or OPENAI_API_KEY)
  python poc/live_check.py              default objective, $3.00 hard spend cap
  python poc/live_check.py --max-usd 5 --objective "one founder sentence"

Every model call goes through cynqra/model_adapter.py against the provider's real API.
The run is staffed from a registry holding the model the environment names, priced at its list
price (registry.LIST_PRICES, or CYNQRA_PRICE_PER_M), and --max-usd is the run's budget: the
Budget Engine's breaker is the spend cap. A shell command model (CYNQRA_S1_MODEL_CMD) is refused
unless --allow-cmd is given; then the report says so, tokens are estimated, no dollars are
counted and counts_as_measured_result is false. tests/model_bridge.py is such a command.

The founder's decisions are approved automatically, the same way tests/helpers.run_journey
does it, and every one is listed in the report. The run passes only when the product the
workers wrote is accepted, answers GET /health with 200 on its live URL, and its own tests
pass again when rerun here from the merged repository.

Outcomes, written to poc/live_reports/live_<timestamp>.json and .md:
  PASS    the journey reached accepted and the independent checks passed
  FAIL    the model answered but the organization did not deliver working software
  UNRUN   no model, a provider or network error, or the spend cap stopped the run.
          Unrun is not pass and not fail (rule two).
Exit codes: 0 PASS, 1 FAIL, 2 no model, 3 UNRUN.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cynqra import budget, model_adapter  # noqa: E402
from cynqra.engine import Engine  # noqa: E402
from cynqra.testrunner import NO_WINDOW, python_exe  # noqa: E402


def reports_dir() -> Path:
    """Where reports go: CYNQRA_REPORTS_DIR (the desktop app sets its data folder), else poc/live_reports."""
    return Path(os.environ.get("CYNQRA_REPORTS_DIR") or HERE / "live_reports")
SCENARIO = json.loads((HERE / "scenarios" / "candidate_tracker" / "scenario.json").read_text(encoding="utf-8"))

UNRUN_MARKERS = ("HTTP 4", "HTTP 5", "network error", "No model", "refused (category", "URLError", "timed out",
                 "model command exited")


def rerun_product_tests(repo: Path) -> dict:
    """The product's own tests, run again from the merged repository in a scratch copy."""
    if not repo.exists() or not any(repo.rglob("test_*.py")):
        return {"ran": False, "passed": False, "output": "no test_*.py in the merged repository"}
    scratch = repo.parent / "_live_check_rerun"
    shutil.rmtree(scratch, ignore_errors=True)
    shutil.copytree(repo, scratch, ignore=shutil.ignore_patterns("__pycache__", "*.json.lock"))
    env = {k: v for k, v in os.environ.items() if "KEY" not in k and "TOKEN" not in k}
    try:
        proc = subprocess.run([python_exe(), "-m", "unittest", "discover", "-v"], cwd=scratch, env=env,
                              capture_output=True, encoding="utf-8", errors="replace", timeout=300,
                              creationflags=NO_WINDOW)
        out = (proc.stdout + proc.stderr)[-4000:]
        return {"ran": True, "passed": proc.returncode == 0, "output": out}
    except subprocess.TimeoutExpired:
        return {"ran": True, "passed": False, "output": "timed out after 300 s"}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def health(url: str | None) -> dict:
    if not url:
        return {"url": None, "status": None}
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=10) as r:
            return {"url": url, "status": r.status}
    except Exception as exc:  # noqa: BLE001 - any failure is a failed health check
        return {"url": url, "status": None, "error": str(exc)[:200]}


def run(objective: str, max_usd: float, data_dir: Path, log=print, allow_cmd: bool = False) -> dict:
    resolved = model_adapter.resolve()
    measured = bool(resolved) and resolved["kind"] != "cmd"
    report = {"started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "objective": objective,
              "max_usd": max_usd, "model": resolved, "effort": os.environ.get("CYNQRA_EFFORT") or "model default",
              "counts_as_measured_result": measured}
    if resolved is None or (resolved["kind"] == "cmd" and not allow_cmd):
        report.update(outcome="UNRUN", reason="No real model API key. Set ANTHROPIC_API_KEY or OPENAI_API_KEY.")
        return report

    e = Engine(data_dir)
    t0 = time.time()
    decisions, steps = [], []

    def cost() -> float:
        return budget.ledger(e.store)["spent_total"]

    def finish(outcome: str, reason: str) -> dict:
        calls = e.store.all("call")
        report.update(
            outcome=outcome, reason=reason, seconds=round(time.time() - t0, 1), phase=e.meta["phase"],
            notice=e.meta.get("notice", ""), usd=round(cost(), 4),
            tokens_in=sum(c.get("tokens_in", 0) for c in calls), tokens_out=sum(c.get("tokens_out", 0) for c in calls),
            calls=[{k: c.get(k) for k in ("id", "task_id", "worker", "purpose", "label", "model_id", "tokens_in",
                                          "tokens_out", "usd", "estimated", "latency_s")} for c in calls],
            decisions=decisions, steps=steps[-200:],
            objective_structured=(e.objective() or {}).get("structured"),
            inferred_fields=(e.objective() or {}).get("inferred_fields"),
            plan=[{k: t.get(k) for k in ("id", "kind", "owner_worker_id", "title", "status", "attempts")} for t in e.tasks()],
            verifications=[{k: v.get(k) for k in ("id", "task_id", "verdict", "method")} for v in e.store.all("verification")],
            metrics=e.metrics() if e.store.get("company", e.cid) else {},
            budget=budget.ledger(e.store),
        )
        return report

    try:
        e.create_company("Live check", "live")
        e.set_guardrails(budget_usd=max_usd)
        model = e.registry.get("environment")
        log(f"model: {resolved['label']} ({resolved['kind']}), "
            + (f"${model['price_in']}/${model['price_out']} per M tokens, budget ${max_usd:.2f}" if measured
               else "command model: tokens estimated, no dollars counted"))
        obj = e.draft_objective(objective)
        log(f"objective structured: {len(obj['structured'])} fields, inferred {obj['inferred_fields']}, "
            f"missing {obj['missing_fields']}  ${cost():.3f}")
        if obj["missing_fields"]:
            return finish("FAIL", f"the model left objective fields empty: {obj['missing_fields']}")
        e.submit_objective()
        decisions.append({"kind": "submit_objective", "action": "submit"})
        for _ in range(400):
            phase = e.meta["phase"]
            if phase in ("accepted", "stopped", "stopped_error"):
                break
            r = e.step()
            if r["did"] not in ("idle",):
                steps.append(r)
                log(f"  {r.get('did'):<22} {r.get('task', ''):<6} ${cost():.3f}")
            if r["did"] == "error":
                break
            if r["did"] == "idle":
                pend = e.pending_decisions()
                if any(d["kind"] == "budget_breaker" for d in pend):
                    return finish("UNRUN", f"spend cap reached: ${cost():.3f} of ${max_usd:.2f}. The budget breaker "
                                           "stopped the run.")
                if any(d["kind"] == "escalation" and "stopped answering" in d["problem"] for d in pend):
                    return finish("UNRUN", next(d["problem"] for d in pend if d["kind"] == "escalation"))
                if not pend:
                    if e.meta["phase"] in ("accepted", "delivered"):
                        continue
                    return finish("FAIL", f"the run went idle with nothing to decide: {r.get('why')}")
                d = pend[0]
                decisions.append({"id": d["id"], "kind": d["kind"], "risk": d.get("risk"), "task_id": d.get("task_id"),
                                  "problem": d.get("problem", "")[:300], "action": "approve"})
                log(f"  founder approves {d['kind']} {d.get('task_id') or ''}")
                e.decide(d["id"], "approve")
        phase = e.meta["phase"]
        if phase == "stopped_error":
            notice = e.meta.get("notice", "")
            unrun = any(m in notice for m in UNRUN_MARKERS)
            return finish("UNRUN" if unrun else "FAIL", notice)
        if phase != "accepted":
            return finish("FAIL", f"the run ended in phase {phase}, not accepted")
        h = health(e.live_url())
        tests = rerun_product_tests(e.paths["main"])
        report["health"], report["product_tests"] = h, tests
        if h.get("status") != 200:
            return finish("FAIL", f"the live product did not answer /health with 200: {h}")
        if not tests["passed"]:
            return finish("FAIL", "the product's own tests fail when rerun from the merged repository")
        return finish("PASS", "accepted, live, healthy, and the product's tests pass on rerun")
    except Exception as exc:  # noqa: BLE001 - recorded, never swallowed silently
        msg = f"{type(exc).__name__}: {exc}"
        unrun = any(m in msg for m in UNRUN_MARKERS)
        return finish("UNRUN" if unrun else "FAIL", msg)
    finally:
        e.close()


def write(report: dict) -> Path:
    reports = reports_dir()
    reports.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    j = reports / f"live_{ts}.json"
    j.write_text(json.dumps(report, indent=1), encoding="utf-8")
    lines = [f"# Live check {ts}", "", f"**Outcome: {report['outcome']}**. {report.get('reason', '')}", "",
             f"Model: {(report.get('model') or {}).get('label')}, effort {report.get('effort')}. "
             + ("Local model on this machine: token counts are real, there is no API spend. "
                if (report.get("model") or {}).get("local") else
                f"Spend ${report.get('usd', 0):.3f} of ${report['max_usd']:.2f} cap. " if report["counts_as_measured_result"]
                else "Command model: tokens are estimated, spend is not measured, not a cost result. ") +
             f"Tokens {report.get('tokens_in', 0)} in, {report.get('tokens_out', 0)} out. "
             f"{report.get('seconds', 0)} s.", "", f"Objective: {report['objective']}", ""]
    if report.get("plan"):
        lines += ["| Task | Kind | Owner | Status | Attempts |", "| --- | --- | --- | --- | --- |"]
        lines += [f"| {t['id']} {t['title']} | {t['kind']} | {t['owner_worker_id']} | {t['status']} | {t['attempts']} |"
                  for t in report["plan"]]
        lines.append("")
    if report.get("decisions"):
        lines.append(f"Founder decisions, all approved automatically: {len(report['decisions'])}")
        lines += [f"* {d['kind']} {d.get('task_id') or ''} {d.get('risk') or ''}" for d in report["decisions"]]
        lines.append("")
    if report.get("metrics"):
        lines += ["Metrics:", "```", json.dumps(report["metrics"], indent=1), "```", ""]
    if report.get("product_tests"):
        lines += ["Product tests rerun:", "```", report["product_tests"]["output"][-1500:], "```"]
    j.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return j


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the whole Cynqra POC against a real model.")
    ap.add_argument("--objective", default=SCENARIO["messy"], help="the founder sentence")
    ap.add_argument("--max-usd", type=float, default=3.00, help="hard spend cap; the run is killed above it")
    ap.add_argument("--keep", action="store_true", help="keep the run folder under poc/live_reports/")
    ap.add_argument("--allow-cmd", action="store_true", help="accept a command model (CYNQRA_S1_MODEL_CMD); not measured")
    args = ap.parse_args()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    data = reports_dir() / f"run_{ts}"
    report = run(args.objective, args.max_usd, data, allow_cmd=args.allow_cmd)
    path = write(report)
    if not args.keep:
        shutil.rmtree(data, ignore_errors=True)
    print(f"\n{report['outcome']}: {report.get('reason', '')}\nreport: {path}")
    if report.get("model") is None or ((report.get("model") or {}).get("kind") == "cmd" and not args.allow_cmd):
        return 2
    return {"PASS": 0, "FAIL": 1}.get(report["outcome"], 3)


if __name__ == "__main__":
    sys.exit(main())
