"""Cynqra chooses, measures and replaces AI workers on real models: the whole demonstration, unattended.

    desktop.py --workforce local "objective"     three open models on this machine, swapped in as needed
    desktop.py --workforce hf "objective"        Qwen3.5-35B-A3B, GLM-4.7 and Kimi K2.5 on Hugging Face (HF_TOKEN)

Through the app's own HTTP API, as the window drives it:
 1. Register three real models (facts only: runtime, price, context; no scores).
 2. Probe each one on Cynqra's calibration work, so selection starts from measured outcomes.
 3. Give Cynqra the objective and a dollar budget. Cynqra decomposes it into requirements and synthesizes the
    organization; the founder approves the workforce, then the roadmap and the budget built on it.
 4. Show the workforce it staffed: every worker, its model, and the table behind each choice.
 5. Fault: cap the replies of the model staffed as Engineer A, so its real output cannot fit its code.
 6. Run. Cynqra detects the failure, replaces the model, the successor inherits the work, the budget moves,
    and the project continues to delivery. Every founder decision is approved and listed.
 7. Report: staffing, replacements, the ledger, every outcome learned, each model's measured record.

Nothing is simulated: the words come from the models, the code runs, the product is deployed and tested.
Exit 0 only when the project is accepted, the product passes its checks, and a worker was moved off the
faulted model.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

# The three open models the demonstration can run on one 16 GB machine without a key (one at a time).
LOCAL = [("qwen3.5-4b", "Qwen3.5 4B"), ("qwen3.5-9b", "Qwen3.5 9B"), ("gpt-oss-20b", "gpt-oss 20B")]
# The three the product brief names, hosted by Hugging Face Inference Providers.
HOSTED = [("Qwen/Qwen3.5-35B-A3B", "Qwen3.5-35B-A3B"), ("zai-org/GLM-4.7", "GLM-4.7"), ("moonshotai/Kimi-K2.5", "Kimi K2.5")]
LOCAL_USD_PER_HOUR = 0.10  # the value put on an hour of this machine, so local work has a price; stated in the report
FAULT_REPLY_TOKENS = 300   # a reply cap no real module and its tests fit into


def run(args) -> int:
    from desktop import Desktop, data_dir, http  # the app itself, in this process
    import live_check
    d = Path(args.data) if args.data else data_dir()
    desk = Desktop(d)
    api = lambda path, body=None: http(desk.url + path, body, timeout=4000)  # noqa: E731
    t0 = time.time()
    rep = {"started_at": datetime.now().astimezone().isoformat(timespec="seconds"), "route": args.workforce,
           "objective": args.objective, "outcome": "FAIL", "reason": "did not finish", "models": [], "probes": [],
           "decisions": [], "local_usd_per_hour": LOCAL_USD_PER_HOUR if args.workforce == "local" else None}
    say = lambda *a: print(f"{time.time() - t0:7.0f}s ", *a, flush=True)  # noqa: E731
    try:
        # 1. register
        if args.workforce == "local":
            for ref, name in LOCAL:
                say(f"downloading {name} if needed")
                desk.runtime.download(ref)
                rep["models"].append(api("/api/models", {"runtime": "llama", "ref": ref, "name": name,
                                                         "compute_usd_per_hour": LOCAL_USD_PER_HOUR}))
        else:
            for ref, name in HOSTED:
                rep["models"].append(api("/api/models", {"runtime": "hf", "ref": ref, "name": name}))
        for m in rep["models"]:
            say(f"registered {m['name']}: {m['runtime']} {m['ref']}, context {m['context']}, "
                + (f"${m['compute_usd_per_hour']}/h of this machine" if m["local"] else f"${m['price_in']} in / ${m['price_out']} out per M"))
        # 2. probe
        if not args.no_probe:
            from cynqra.probe import probe
            for m in rep["models"]:
                say(f"probing {m['name']} on Cynqra's calibration work")
                r = probe(desk.app.registry, m["id"], log=lambda s: say(s.strip()))
                rep["probes"].append(r)
        # 3. project
        api("/api/company", {"name": args.company, "mode": "live"})
        say("structuring the objective")
        obj = api("/api/objective/draft", {"messy": args.objective})
        missing = [k for k, v in obj["structured"].items() if not str(v).strip()]
        if missing:
            api("/api/objective/fields", {"fields": {k: "none stated" for k in missing}})
        api("/api/objective/guardrails", {"budget_usd": args.budget_usd, "time_value_per_hour": 10})
        api("/api/objective/submit", {})
        st = api("/api/state")
        prop = st["proposal"]
        rep["workforce_proposal"] = {"roles": prop["roles"], "summary": prop["summary"]}
        say("proposed workforce: " + ", ".join(f"{r['role']} x{r['quantity']}" for r in prop["roles"]))
        gate = [x for x in st["decisions"]["pending"] if x["kind"] == "approve_workforce"][0]
        api(f"/api/decisions/{gate['id']}", {"action": "approve"})
        rep["decisions"].append({"kind": "approve_workforce"})
        # 4. staffing
        st = api("/api/state")
        wf = st["workforce"]
        rep["staffing"] = [{"worker": w["id"], "role": w["role"], "model": w["model"],
                            "candidates": [{k: c[k] for k in ("model", "p_task", "expected_usd", "expected_minutes", "score")}
                                           for c in w["candidates"]]} for w in wf["workers"]]
        for w in rep["staffing"]:
            say(f"staffed {w['worker']:<8} ({w['role']}) -> {w['model']}   "
                + "  ".join(f"{c['model']}: P {c['p_task']}, ${c['expected_usd']}, {c['expected_minutes']} min"
                            for c in w["candidates"]))
        rep["forecast"] = {k: st["forecast"][k] for k in ("cap_usd", "subtotal_usd", "reserve_usd", "layers", "warnings")}
        plan = [x for x in st["decisions"]["pending"] if x["kind"] == "approve_roadmap"][0]
        api(f"/api/decisions/{plan['id']}", {"action": "approve"})
        rep["decisions"].append({"kind": "approve_roadmap"})
        L = api("/api/state")["workforce"]["ledger"]
        say(f"budget ${args.budget_usd}: allocated {sum(L['allocated'].values()):.4f} to {len(L['allocated'])} tasks, "
            f"reserve {L['reserve']:.4f}")
        # 5. fault
        eng = next(w for w in wf["workers"] if w["id"] == "w_eng_a")
        faulted = eng["model_id"]
        api(f"/api/models/{faulted}/fault", {"max_reply": FAULT_REPLY_TOKENS})
        rep["fault"] = {"model_id": faulted, "model": eng["model"], "max_reply": FAULT_REPLY_TOKENS,
                        "why": "the model staffed as Engineer A; its replies are capped so its real code cannot fit"}
        say(f"FAULT: {eng['model']} (Engineer A's model) now has its replies capped at {FAULT_REPLY_TOKENS} tokens")
        # 6. run
        api("/api/run/auto", {"on": True, "delay": 0})
        seen, deadline = 0, t0 + args.max_minutes * 60
        shown = ("worker.model_assigned", "worker.model_replaced", "task.verified", "verification.completed",
                 "task.reply_cut_off", "task.failed", "deployment.verified", "worker.self_checked")
        while time.time() < deadline:
            st = api("/api/state")
            for ev in st.get("events") or []:
                if ev["seq"] > seen:
                    seen = ev["seq"]
                    if ev["event_type"] in shown:
                        p = ev.get("payload") or {}
                        extra = (f"{p.get('from')} -> {p.get('to')}: {p.get('reason', '')[:120]}" if ev["event_type"] ==
                                 "worker.model_replaced" else p.get("verdict") or p.get("passed") or p.get("reason") or "")
                        say(f"{ev['event_type']:<24} {ev['aggregate_id']:<10} {str(extra)[:160]}")
            phase = st["meta"]["phase"]
            if phase in ("accepted", "stopped", "stopped_error"):
                break
            pend = st["decisions"]["pending"]
            if pend:
                dd = pend[0]
                rep["decisions"].append({"kind": dd["kind"], "task_id": dd.get("task_id"), "problem": dd.get("problem", "")[:300]})
                say(f"founder approves {dd['kind']} {dd.get('task_id') or ''}")
                api(f"/api/decisions/{dd['id']}", {"action": "approve"})
                continue
            if phase == "running" and not st["auto"]["on"]:
                api("/api/run/auto", {"on": True, "delay": 0})
            time.sleep(3)
        api("/api/run/auto", {"on": False})
        # 7. report
        e = desk.app.engine
        with e.lock:
            view = e.workforce_view()
            phase = e.meta["phase"]
            rep.update(phase=phase, notice=e.meta.get("notice", ""), seconds=round(time.time() - t0),
                       replacements=[{k: r[k] for k in ("task_id", "worker_id", "role", "from", "to", "reason", "attempts",
                                                        "usd_spent_by_previous", "inherited")} for r in view.get("replacements", [])],
                       ledger=view.get("ledger"), workers_final=[{k: w[k] for k in ("id", "role", "model", "budget")}
                                                                 for w in view.get("workers", [])],
                       outcomes=[o for o in desk.app.registry.outcomes() if o["run_id"] == e.cid],
                       registry=[{"name": m["name"], "runtime": m["runtime"], "ref": m["ref"], "fault": m.get("fault"),
                                  "available": m["available"], "performance": m["performance"]} for m in view["registry"]],
                       tasks=[{k: t.get(k) for k in ("id", "kind", "owner_worker_id", "title", "status", "attempts",
                                                     "replacements")} for t in e.tasks()])
            fin = e.final_report()
            rep.update(economics=fin["economics"], performance=fin["performance"], evaluations=fin["evaluations"],
                       metrics=fin["metrics"])
            moved = [r for r in rep["replacements"] if r["from"] == faulted]
            if phase == "accepted":
                health = live_check.health(e.live_url())
                tests = live_check.rerun_product_tests(e.paths["main"])
                rep.update(health=health, product_tests={"passed": tests["passed"], "ran": tests.get("ran")})
                ok = health.get("status") == 200 and tests["passed"]
            else:
                ok = False
            if ok and moved:
                rep.update(outcome="PASS", reason=f"delivered and accepted; {len(moved)} worker(s) moved off the faulted "
                                                  f"model {rep['fault']['model']}, and the work continued")
            elif ok:
                rep.update(outcome="FAIL", reason="delivered, but no worker was moved off the faulted model")
            else:
                rep.update(outcome="FAIL", reason=rep["notice"] or f"ended in phase {phase}")
    except Exception as exc:  # noqa: BLE001 - every failure goes into the report
        rep.update(outcome="FAIL", reason=f"{type(exc).__name__}: {exc}"[:1000], seconds=round(time.time() - t0))
    finally:
        out = Path(os.environ["CYNQRA_REPORTS_DIR"]) / f"workforce_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
        desk.close()
    print(f"\n{rep['outcome']}: {rep['reason']}\nReport: {out}", flush=True)
    for r in rep.get("replacements") or []:
        print(f"  replaced: {r['task_id']} {r['role']} {r['from']} -> {r['to']} ({r['reason'][:140]})")
    L = rep.get("ledger") or {}
    if L:
        print(f"  budget: spent ${L.get('spent_total', 0):.4f}, reserve ${L.get('reserve', 0):.4f}")
    return 0 if rep["outcome"] == "PASS" else 1
