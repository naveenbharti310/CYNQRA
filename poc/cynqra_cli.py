#!/usr/bin/env python3
"""Cynqra from the terminal: real agents, a local open model, your laptop.

  python poc/cynqra_cli.py doctor            is this laptop ready? (add --full for a coding check)
  python poc/cynqra_cli.py run               build something: you answer the founder's decisions here
  python poc/cynqra_cli.py run "objective"   same, with the objective given
  python poc/cynqra_cli.py run --yes "..."   unattended: every decision approved and listed in the report
  python poc/cynqra_cli.py bench             compare installed models on Cynqra's own tasks
  python poc/cynqra_cli.py ui                the same engine in the browser

Settings come from poc/local_config.json (written by the installer), and any environment
variable of the same meaning overrides it. Standard library only.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
CONFIG = HERE / "local_config.json"

# config key -> environment variable read by cynqra/model_adapter.py and the engine
ENV_KEYS = {"model": "CYNQRA_OLLAMA_MODEL", "host": "OLLAMA_HOST", "num_ctx": "CYNQRA_NUM_CTX",
            "num_predict": "CYNQRA_NUM_PREDICT", "seed": "CYNQRA_SEED",
            "think": "CYNQRA_THINK", "temperature": "CYNQRA_TEMPERATURE", "timeout": "CYNQRA_TIMEOUT",
            "self_checks": "CYNQRA_SELF_CHECKS", "local_base_url": "CYNQRA_LOCAL_BASE_URL",
            "local_model": "CYNQRA_MODEL"}

# From the research in poc/research/local_open_models_2026-09.md, summarised in LAPTOP_SETUP.md.
# Memory is what the machine has in total; the model, its context, the operating system and a
# browser all have to fit. Dense models above ~10B are only offered on Macs: on a laptop CPU
# they take 15 to 25 minutes a call. The 3B-active mixture-of-experts models are the fast ones.
TIERS = [
    {"min_gb": 28, "model": "qwen3.6:35b", "num_ctx": 32768, "num_predict": 8192, "think": False,
     "why": "the default: a strong coder with 3B active parameters, so it stays fast without a GPU"},
    {"min_gb": 0, "model": "qwen3.5:9b", "num_ctx": 24576, "num_predict": 6144, "think": False,
     "why": "leaves room in 16 to 24 GB; slow without a GPU, so consider sharing a bigger machine (LAPTOP_SETUP.md)"},
]
# Chosen on purpose with setup --model: the upgrade for 32 GB and more, and the smaller fallbacks.
KNOWN = {"qwen3.6:27b": {"num_ctx": 32768, "num_predict": 8192, "think": False,
                         "why": "stronger dense model, three to four times slower; best on a Mac with 32 GB or more"},
         "gpt-oss:20b": {"num_ctx": 32768, "num_predict": 8192, "think": "low",
                         "why": "fast fallback; its reasoning cannot be turned off, only kept low"},
         "qwen3.5:4b": {"num_ctx": 24576, "num_predict": 6144, "think": False,
                        "why": "smallest fallback when even 9B is too slow"}}
ALTERNATIVES = ["qwen3.6:27b", "gpt-oss:20b", "glm-4.7-flash", "devstral-small-2:24b", "gemma4:26b"]
MIN_OLLAMA = (0, 34, 4)  # thinking combined with JSON schema output was fixed here (2026-09-23)


def load_config() -> dict:
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    except (OSError, ValueError):
        cfg = {}
    for key, env in ENV_KEYS.items():
        if cfg.get(key) not in (None, "") and not os.environ.get(env):
            os.environ[env] = str(cfg[key]).lower() if isinstance(cfg[key], bool) else str(cfg[key])
    return cfg


def total_ram_gb() -> float | None:
    try:
        if sys.platform.startswith("linux"):
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 1024 / 1024
        if sys.platform == "darwin":
            return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout) / 1024 ** 3
        if sys.platform == "win32":
            class MEM(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MEM()
            m.dwLength = ctypes.sizeof(MEM)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullTotalPhys / 1024 ** 3
    except (OSError, ValueError, AttributeError):
        return None
    return None


def pick_tier(ram_gb: float | None, is_mac: bool | None = None) -> dict:
    is_mac = sys.platform == "darwin" if is_mac is None else is_mac
    for tier in TIERS:
        if (ram_gb or 0) >= tier["min_gb"]:
            return tier
    return TIERS[-1]


def _version(text: str) -> tuple:
    try:
        return tuple(int(x) for x in text.split("-")[0].split(".")[:3])
    except ValueError:
        return (0,)


def _get(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read() or b"null")


def _post(url: str, body: dict, timeout: float = 30.0):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"null")


# ----------------------------------------------------------------- setup ----
def setup(args) -> int:
    """Choose the model for this machine (or the one given) and write poc/local_config.json."""
    ram = total_ram_gb()
    tier = dict(pick_tier(ram))
    if args.model:
        known = {t["model"]: t for t in TIERS}
        known.update({k: dict(v, model=k) for k, v in KNOWN.items()})
        tier = dict(known.get(args.model, {"model": args.model, "num_ctx": 32768, "num_predict": 8192, "think": False,
                                          "why": "chosen by you"}))
    cfg = {"provider": "ollama", "model": tier["model"], "num_ctx": args.num_ctx or tier["num_ctx"],
           "num_predict": tier["num_predict"], "think": tier["think"], "temperature": 0, "seed": 42, "self_checks": 2,
           "chosen_for": f"{ram:.0f} GB, {platform.system()}" if ram else platform.system(), "why": tier["why"]}
    if args.host:
        cfg["host"] = args.host
    CONFIG.write_text(json.dumps(cfg, indent=1) + "\n", encoding="utf-8")
    if args.print_model:
        print(cfg["model"])
    else:
        print(f"Wrote {CONFIG}: {cfg['model']} ({cfg['why']})")
    return 0


# ---------------------------------------------------------------- doctor ----
def doctor(args) -> int:
    from cynqra import model_adapter
    cfg = load_config()
    results = []

    def check(name: str, ok: bool | None, detail: str, fix: str = "") -> bool:
        mark = {True: "PASS", False: "FAIL", None: "WARN"}[ok]
        results.append(ok)
        print(f"  [{mark}] {name}: {detail}")
        if fix and ok is not True:
            print(f"         fix: {fix}")
        return bool(ok)

    print("Cynqra doctor\n")
    check("Python", sys.version_info >= (3, 10), platform.python_version(),
          "install Python 3.10 or newer from python.org")
    ram = total_ram_gb()
    tier = pick_tier(ram)
    check("Memory", True if ram else None, f"{ram:.0f} GB, suggested model {tier['model']} ({tier['why']})" if ram else "unknown")
    resolved = model_adapter.resolve()
    if not check("Model configured", resolved is not None,
                 f"{resolved['kind']}: {resolved['label']}" if resolved else "none",
                 "run the installer, or set CYNQRA_OLLAMA_MODEL, for example: " + tier["model"]):
        return 1
    if resolved["kind"] == "ollama":
        host, model = model_adapter.ollama_host(), resolved["label"]
        try:
            version = _get(host + "/api/version").get("version", "?")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            check("Ollama", False, f"not reachable at {host} ({exc})", "start the Ollama app, or run: ollama serve")
            return 1
        check("Ollama", True if _version(version) >= MIN_OLLAMA else None, f"version {version} at {host}",
              "update Ollama to 0.34.4 or newer (thinking with JSON output was fixed there)")
        if model.endswith("-mlx") or ":mlx" in model:
            check("Model build", None, f"{model} uses the MLX engine", "use the plain tag; MLX JSON output can run away")
        tags = {m["name"]: m for m in (_get(host + "/api/tags").get("models") or [])}
        name = model if model in tags else (model + ":latest" if model + ":latest" in tags else None)
        if not check("Model installed", name is not None, model, f"ollama pull {model}"):
            return 1
        size_gb = tags[name].get("size", 0) / 1024 ** 3
        try:
            show = _post(host + "/api/show", {"model": model})
        except (urllib.error.URLError, OSError, ValueError):
            show = {}
        info = show.get("model_info") or {}
        ctx_max = next((v for k, v in info.items() if k.endswith(".context_length")), None)
        caps = show.get("capabilities") or []
        num_ctx = int(os.environ.get("CYNQRA_NUM_CTX") or 32768)
        check("Model size", None if ram and size_gb > 0.7 * ram else True,
              f"{size_gb:.1f} GB on disk" + (f", {size_gb / ram:.0%} of memory" if ram else ""),
              "close other apps, or choose a smaller model: " + TIERS[-1]["model"])
        check("Context window", None if ctx_max and num_ctx > ctx_max else True,
              f"num_ctx {num_ctx}" + (f" of the model's {ctx_max}" if ctx_max else ""),
              "lower num_ctx in poc/local_config.json")
        if caps:
            check("Capabilities", True, ", ".join(caps))
    print("\n  Asking the model for a small JSON answer (the first call also loads it into memory)...")
    t0 = time.time()
    out = model_adapter.complete('Return only this JSON object with the sum filled in: {"ok": true, "sum": 2 + 3}',
                                 max_tokens=200, want_json=True)
    if not check("JSON answer", not out.get("error"), out.get("error") or out["text"].strip()[:80]):
        return 1
    try:
        parsed = json.loads(out["text"])
    except ValueError:
        parsed = None
    check("JSON is valid", isinstance(parsed, dict) and parsed.get("sum") == 5, str(parsed)[:80])
    rate = out["tokens_out"] / max(0.001, out["latency_s"])
    check("Speed", True if rate >= 5 else None, f"{out['latency_s']:.1f} s, {out['tokens_out']} tokens out "
          f"({rate:.1f} tokens/s including load)", "a full run may take an hour or more at this speed")
    if args.full:
        code_check(check, model_adapter)
    bad = results.count(False)
    print(f"\n{'Ready.' if not bad else 'Not ready.'} {bad} failed, {results.count(None)} warnings. "
          + ("Next: python poc/cynqra_cli.py run" if not bad else ""))
    return 0 if not bad else 1


def code_check(check, model_adapter) -> None:
    """A small version of an engineer's task: write a module and its tests, then the tests must pass."""
    print("\n  Coding check: the model writes a module and its unittest tests (a few minutes on a CPU)...")
    prompt = ("You are an engineer. Write a Python standard library module slug.py with a function slugify(text) that "
              "lowercases, turns runs of non letters and digits into one hyphen and strips hyphens from both ends, and "
              "a file test_slug.py with at least four unittest tests. Return one JSON object: "
              '{"files": {"slug.py": "full file content", "test_slug.py": "full file content"}}')
    out = model_adapter.complete(prompt, max_tokens=3000, want_json=True)
    if not check("Code answer", not out.get("error"), out.get("error") or f"{out['latency_s']:.0f} s"):
        return
    try:
        files = json.loads(out["text"]).get("files") or {}
    except (ValueError, AttributeError):
        files = {}
    work = Path(tempfile.mkdtemp(prefix="cynqra_doctor_"))
    try:
        for name, text in files.items():
            if isinstance(text, str) and "/" not in name and name.endswith(".py"):
                (work / name).write_text(text, encoding="utf-8")
        from cynqra.verification import run_unittests
        rep = run_unittests(work)
        check("Code works", rep["passed"], f"{rep['ran']} tests, {len(rep['failed'])} failed" if rep["ran"]
              else "no tests ran", "the model may be too small; see LAPTOP_SETUP.md")
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ------------------------------------------------------------------- run ----
def ask(prompt: str, choices: str, default: str) -> str:
    while True:
        try:
            a = input(prompt).strip().lower() or default
        except EOFError:
            return default
        if a[:1] in choices:
            return a[:1]
        print(f"  Type one of: {', '.join(choices)}")


def text_input(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def show_objective(obj: dict) -> None:
    print("\nStructured objective (version %s):" % obj["version"])
    for k, v in obj["structured"].items():
        tag = "  inferred, check it" if k in obj["inferred_fields"] else ""
        print(f"  {k.replace('_', ' '):17} {v}{tag}")


def show_plan(e) -> None:
    print("\nOrganization: CTO, PM, Engineer A, Engineer B, plus the Verification Service (not a worker).")
    print("Plan:")
    for t in e.tasks():
        deps = ", ".join(t["dependencies"]) or "none"
        print(f"  {t['id']}  {t['risk_tier']:6} {t['owner_worker_id']:8} {t['title']}  (after: {deps})")


def show_decision(d: dict) -> None:
    title = {"decision": "Product rule", "review_merge": "Merge the release to main", "deploy": "Production deploy",
             "accept_delivery": "Accept delivery", "escalation": "Escalation", "budget_breaker": "Budget cap reached",
             "objective_change": "Objective change"}.get(d["kind"], d["kind"])
    print(f"\n=== Needs you: {title}{' for ' + d['task_id'] if d.get('task_id') else ''}  [{d['risk']} risk] ===")
    print(f"  Problem:        {d['problem']}")
    print(f"  Recommendation: {d['recommendation']}")
    if d.get("evidence_refs"):
        print(f"  Evidence:       {'; '.join(map(str, d['evidence_refs']))}")
    print(f"  Confidence:     {d.get('confidence', '')}.  Would change if: {d.get('what_would_change_this', '')}")
    side = (d.get("extra") or {}).get("side_action")
    if side:
        print(f"  Stopped by policy: {side.get('summary', '')} ({side.get('reason', '')})")


def decide_interactive(e, d: dict) -> None:
    show_decision(d)
    if d["kind"] == "budget_breaker":
        cap = text_input(f"  New cap in work units, or press Enter to stop [{e.budget()['cap'] + 200}]: ")
        if cap.lower() in ("n", "no", "stop", "q"):
            e.decide(d["id"], "reject", "stopped at the cap")
        else:
            e.decide(d["id"], "approve", edited={"cap": int(cap) if cap.isdigit() else e.budget()["cap"] + 200})
        return
    options = "a/r/q" + ("/e" if d["kind"] == "decision" else "")
    a = ask(f"  [a]pprove, [r]eject with a reason{', [e]dit the rule' if d['kind'] == 'decision' else ''}, [q]uit ({options}) [a]: ",
            "areq" if d["kind"] == "decision" else "arq", "a")
    if a == "q":
        raise KeyboardInterrupt
    if a == "e":
        rule = text_input("  Your version of the rule: ")
        e.decide(d["id"], "approve", edited={"recommendation": rule} if rule else None)
    elif a == "r":
        e.decide(d["id"], "reject", text_input("  Reason: "))
    else:
        e.decide(d["id"], "approve")


def step_line(r: dict, e, t0: float) -> str:
    did, task = r.get("did", ""), r.get("task", "")
    t = e.store.get("task", task) if task else None
    words = {"assigned": "handed to " + (r.get("to") or ""), "completed": "done by the worker, waiting for verification",
             "verified": "VERIFIED", "rework": "sent back: verification caught a defect",
             "self_check_failed": "the engineer's own tests failed; it is fixing them",
             "blocked": "Blocker raised instead of guessing", "blocker_cleared": "Blocker cleared by " + str(r.get("by", "")),
             "proposed": "needs the founder", "escalated": "escalated to the founder", "delivered": "every task verified, live",
             "retry": "reply refused, trying the step again", "write_refused": "a write was refused",
             "error": "the model failed: " + str(r.get("why", ""))[:160], "paused": "paused"}.get(did, did)
    title = f" {t['title']}" if t else ""
    calls = e.store.all("call")
    speed = ""
    if calls and did in ("completed", "proposed", "blocked", "blocker_cleared", "assigned", "self_check_failed"):
        c = calls[-1]
        if c.get("latency_s"):
            speed = f"  [{c.get('tokens_in', 0)} in, {c.get('tokens_out', 0)} out, {c['latency_s']:.0f} s]"
    return f"  {time.time() - t0:7.0f}s  {task or '':5} {words}{'  -' + title if title and did in ('assigned', 'verified') else ''}{speed}"


def run(args) -> int:
    load_config()
    from cynqra import model_adapter
    from cynqra.engine import Engine
    import live_check

    resolved = model_adapter.resolve()
    if resolved is None:
        print("No model is configured. Run the installer, or: python poc/cynqra_cli.py doctor")
        return 2
    objective = args.objective or text_input("What do you want Cynqra to build? One or two sentences:\n> ")
    if not objective:
        print("No objective given.")
        return 2
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    data = Path(os.environ.get("CYNQRA_DATA_DIR") or HERE / "data" / "cli_runs") / stamp
    e = Engine(data)
    t0 = time.time()
    report = {"started_at": datetime.now().astimezone().isoformat(timespec="seconds"), "objective": objective,
              "max_usd": 0.0, "model": resolved, "effort": os.environ.get("CYNQRA_THINK") or "model default",
              "counts_as_measured_result": resolved["kind"] != "cmd", "decisions": []}
    try:
        e.create_company(args.company, "live")
        print(f"\nModel: {resolved['label']} ({resolved['kind']}). Run folder: {data}")
        print("Structuring your objective...")
        obj = e.draft_objective(objective)
        while True:
            show_objective(obj)
            if obj["missing_fields"]:
                for k in obj["missing_fields"]:
                    obj = e.edit_objective({k: text_input(f"  {k.replace('_', ' ')} is empty. Your answer: ") or "none stated"})
                continue
            if args.yes:
                break
            a = ask("\n[c]onfirm, [e]dit a field, [q]uit (c/e/q) [c]: ", "ceq", "c")
            if a == "q":
                return 0
            if a == "c":
                break
            field = text_input("  Field name (for example priorities): ").replace(" ", "_")
            if field in obj["structured"]:
                obj = e.edit_objective({field: text_input(f"  New {field.replace('_', ' ')}: ")})
        cap = e.budget()["cap"] if not args.cap_units else args.cap_units
        e.set_guardrails(budget_cap=cap)
        print(f"\nBudget cap: {cap} work units (one unit is 1000 tokens). Planning...")
        e.confirm_objective()
        report["decisions"].append({"kind": "confirm_objective", "action": "approve"})
        while True:
            show_plan(e)
            plan = [d for d in e.pending_decisions() if d["kind"] == "approve_plan"][0]
            a = "a" if args.yes else ask("\n[a]pprove the organization and plan, [r]eject and ask for another, [q]uit (a/r/q) [a]: ", "arq", "a")
            if a == "q":
                return 0
            if a == "a":
                e.decide(plan["id"], "approve")
                report["decisions"].append({"kind": "approve_plan", "action": "approve"})
                break
            e.decide(plan["id"], "reject", text_input("  What should change? "))
        print("\nThe organization is working. Steps:")
        while e.meta["phase"] not in ("accepted", "stopped"):
            r = e.step()
            if r["did"] != "idle":
                print(step_line(r, e, t0), flush=True)
            if e.meta["phase"] == "stopped_error":
                print("\n  " + e.meta.get("notice", ""))
                if args.yes or ask("  [r]etry the same step, [q]uit (r/q) [r]: ", "rq", "r") == "q":
                    break
                e.resume()
                continue
            if r["did"] == "idle":
                pend = [d for d in e.pending_decisions() if not d.get("in_digest")] or e.pending_decisions()
                if not pend:
                    if e.meta["phase"] == "delivered":
                        continue
                    print("  The run went idle with nothing to decide: " + r.get("why", ""))
                    break
                d = pend[0]
                report["decisions"].append({"id": d["id"], "kind": d["kind"], "risk": d.get("risk"),
                                            "task_id": d.get("task_id"), "problem": d.get("problem", "")[:300],
                                            "action": "approve" if args.yes else "asked"})
                if args.yes:
                    show_decision(d)
                    print("  (approved automatically: --yes)")
                    e.decide(d["id"], "approve")
                else:
                    decide_interactive(e, d)
    except KeyboardInterrupt:
        print("\nStopped by you.")
    finally:
        phase = e.meta["phase"]
        m = e.metrics() if e.store.get("company", e.cid) else {}
        calls = e.store.all("call")
        tin, tout = sum(c.get("tokens_in", 0) for c in calls), sum(c.get("tokens_out", 0) for c in calls)
        print(f"\nPhase: {phase}. {m.get('tasks_verified', 0)} of {m.get('tasks_total', 0)} tasks verified. "
              f"{m.get('founder_interventions', 0)} founder decisions. {len(calls)} model calls, {tin} tokens in, {tout} out. "
              f"{time.time() - t0:.0f} s.")
        if phase == "accepted":
            health = live_check.health(e.live_url())
            tests = live_check.rerun_product_tests(e.paths["main"])
            report.update(health=health, product_tests=tests)
            outcome = "PASS" if health.get("status") == 200 and tests["passed"] else "FAIL"
            reason = "accepted, live, healthy, and the product's tests pass on rerun" if outcome == "PASS" else \
                "accepted, but the independent checks failed"
        else:
            outcome, reason = ("UNRUN" if phase == "stopped_error" else "FAIL"), e.meta.get("notice") or f"ended in phase {phase}"
        report.update(outcome=outcome, reason=reason, seconds=round(time.time() - t0, 1), phase=phase, usd=0.0,
                      tokens_in=tin, tokens_out=tout, metrics=m,
                      calls=[{k: c.get(k) for k in ("id", "task_id", "worker", "purpose", "label", "tokens_in",
                                                    "tokens_out", "estimated", "latency_s")} for c in calls],
                      plan=[{k: t.get(k) for k in ("id", "kind", "owner_worker_id", "title", "status", "attempts")}
                            for t in e.tasks()] if e.store.get("plan", "plan_1") else [])
        path = live_check.write(report)
        print(f"{outcome}: {reason}\nReport: {path}\nEverything the organization produced: {data}")
        if phase == "accepted" and e.live_url():
            print(f"\nThe product is live at {e.live_url()}  (its code is in {e.paths['main']})")
            if not args.yes:
                text_input("Open it in your browser. Press Enter here to stop it and exit. ")
        e.close()
    return {"PASS": 0, "FAIL": 1}.get(report.get("outcome"), 3)


# ----------------------------------------------------------------- bench ----
BENCH_OBJECTIVES = [
    "I run a small bakery and my staff keep losing track of custom cake orders. I want a simple internal web page "
    "where they can log an order with the pickup date, see what is due in the next few days, and mark orders as "
    "paid and picked up. Nothing public, no card payments, and it has to run on the shop laptop.",
    "We are a six person dog walking company. I want a small internal tool where the owner assigns each day's walks "
    "to walkers, walkers see their walks for today, and a walker marks a walk done with a short note.",
    "Build me an internal tracker so my two recruiters can add candidates, set a stage, and I can see who is stuck.",
]
BENCH_CODE_TASK = {"id": "t_03", "title": "Order store", "kind": "code", "owner_worker_id": "w_eng_a",
                   "expected_output": "store.py and test_store.py"}
BENCH_HANDOFF = {"acceptance_check": (
    "Write store.py and test_store.py, standard library only. OrderStore(path) keeps orders in one JSON file, "
    "loading it if it exists and saving after every change. add(customer, cake, pickup_date) returns the order dict "
    "(keys id, customer, cake, pickup_date, paid, picked_up; paid and picked_up start False) and raises ValueError "
    "when customer or cake is blank or pickup_date is not a real YYYY-MM-DD date. set_paid(order_id, paid) and "
    "set_picked_up(order_id, picked_up) raise KeyError for an unknown id. due_soon(today) returns orders not picked "
    "up whose pickup date is before today or within today plus 3 days, soonest first. Tests must cover every rule."),
    "context_ref": "bench", "artifacts": []}


def bench(args) -> int:
    """Cynqra's own kinds of work, on each model: structure objectives, plan, write tested code and fix it."""
    cfg = load_config()
    from cynqra import model_adapter
    from cynqra.engine import OBJECTIVE_FIELDS
    from cynqra.intelligence import IntelligenceError, ModelSource
    from cynqra.verification import run_unittests
    models = args.models or [cfg.get("model") or os.environ.get("CYNQRA_OLLAMA_MODEL") or pick_tier(total_ram_gb())["model"]]
    rows = []
    for model in models:
        os.environ["CYNQRA_OLLAMA_MODEL"] = model
        src = ModelSource()
        row = {"model": model, "objectives": 0, "plan": False, "code": "fail", "rounds": 0, "seconds": 0.0,
               "tokens_out": 0, "errors": []}
        t0 = time.time()
        print(f"\n== {model}")
        objective = None
        for text in BENCH_OBJECTIVES[: args.objectives]:
            try:
                data, u = src.structure_objective(text)
                row["tokens_out"] += u["tokens_out"]
                ok = all(str(data.get(k) or "").strip() for k in OBJECTIVE_FIELDS)
                row["objectives"] += ok
                objective = objective or {k: str(data.get(k) or "") for k in OBJECTIVE_FIELDS}
                print(f"  objective: {'complete' if ok else 'fields missing'} ({u['latency_s']:.0f} s)")
            except IntelligenceError as exc:
                row["errors"].append(str(exc)[:200])
                print(f"  objective: error {str(exc)[:120]}")
        try:
            plan, u = src.plan(objective or {k: "" for k in OBJECTIVE_FIELDS})
            row["plan"], row["tokens_out"] = True, row["tokens_out"] + u["tokens_out"]
            print(f"  plan: valid, {len(plan['tasks'])} tasks ({u['latency_s']:.0f} s)")
        except IntelligenceError as exc:
            row["errors"].append(str(exc)[:200])
            print(f"  plan: refused, {str(exc)[:120]}")
        work = Path(tempfile.mkdtemp(prefix="cynqra_bench_"))
        feedback, previous = "", {}
        try:
            for rnd in range(3):
                try:
                    data, u = src.work(BENCH_CODE_TASK, worker="w_eng_a", objective=objective or {}, rules=[],
                                       handoff=BENCH_HANDOFF, inbox={}, feedback=feedback, previous=previous, repo_files=[])
                except IntelligenceError as exc:
                    row["errors"].append(str(exc)[:200])
                    print(f"  code round {rnd + 1}: error {str(exc)[:120]}")
                    break
                row["tokens_out"] += u["tokens_out"]
                files = {k: v for k, v in (data.get("files") or {}).items() if isinstance(v, str) and k.endswith(".py")
                         and "/" not in k}
                for p in work.glob("*.py"):
                    p.unlink()
                for name, text in files.items():
                    (work / name).write_text(text, encoding="utf-8")
                rep = run_unittests(work)
                row["rounds"] = rnd + 1
                print(f"  code round {rnd + 1}: {rep['ran']} tests, {len(rep['failed'])} failed ({u['latency_s']:.0f} s)")
                if rep["passed"]:
                    row["code"] = "pass"
                    break
                previous = files
                feedback = "Failing tests: " + (", ".join(rep["failed"]) or "none ran") + "\n" + rep["output"][-1500:]
        finally:
            shutil.rmtree(work, ignore_errors=True)
        row["seconds"] = round(time.time() - t0, 1)
        rows.append(row)
    print("\nmodel                     objectives  plan   code (rounds)   minutes  tokens out")
    for r in rows:
        print(f"{r['model']:25} {r['objectives']}/{args.objectives:<9} {'valid' if r['plan'] else 'no':6} "
              f"{r['code']:4} ({r['rounds']})       {r['seconds'] / 60:6.1f}   {r['tokens_out']}")
    import live_check
    live_check.REPORTS.mkdir(parents=True, exist_ok=True)
    out = live_check.REPORTS / f"bench_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps({"ram_gb": total_ram_gb(), "platform": platform.platform(), "rows": rows}, indent=1),
                   encoding="utf-8")
    print(f"\nSaved {out}. The full test of a model is a whole run: python poc/cynqra_cli.py run --yes \"...\"")
    return 0 if all(r["code"] == "pass" and r["plan"] for r in rows) else 1


def ui(args) -> int:
    load_config()
    import run_poc
    sys.argv = ["run_poc.py"] + (["--port", str(args.port)] if args.port else [])
    return run_poc.main()


def main() -> int:
    ap = argparse.ArgumentParser(description="Cynqra on this laptop.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("doctor", help="check that this laptop is ready")
    d.add_argument("--full", action="store_true", help="also ask the model to write and pass a small tested module")
    r = sub.add_parser("run", help="build something, answering the founder's decisions here")
    r.add_argument("objective", nargs="?", default="")
    r.add_argument("--yes", action="store_true", help="approve every decision automatically")
    r.add_argument("--company", default="My company")
    r.add_argument("--cap-units", type=int, default=0, help="budget cap in work units (default: live default)")
    st = sub.add_parser("setup", help="choose the model for this machine and write poc/local_config.json")
    st.add_argument("--model", default="", help="an Ollama tag instead of the automatic choice")
    st.add_argument("--num-ctx", type=int, default=0)
    st.add_argument("--host", default="", help="use Ollama on another machine, for example http://192.168.1.20:11434")
    st.add_argument("--print-model", action="store_true", help="print only the model tag (for the installers)")
    b = sub.add_parser("bench", help="compare installed models on Cynqra's own tasks")
    b.add_argument("models", nargs="*", help="Ollama tags; default: the configured model")
    b.add_argument("--objectives", type=int, default=3, choices=(1, 2, 3))
    u = sub.add_parser("ui", help="open the web app")
    u.add_argument("--port", type=int, default=0)
    args = ap.parse_args()
    try:
        return {"setup": setup, "doctor": doctor, "run": run, "bench": bench, "ui": ui}[args.cmd](args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
