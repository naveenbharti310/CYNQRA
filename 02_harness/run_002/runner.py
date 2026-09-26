#!/usr/bin/env python3
"""Run 002 orchestrator.

Each worker turn mounts only that worker's home. Protocol objects are the
only thing copied between homes. The test project is a chew toy. It is not
the product.
"""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os

# Guard added 26 Sep 2026 by the acting CTO. Run 002 is closed and audited.
# main() below wipes workers/, shared/, golden_sets/ and verification/, which
# kit/test_kit.py reads, rewrites measures.json without the audit corrections,
# and then copies to /data, which only existed in the old sandbox. A rerun
# destroys the record and then crashes. days_6_9.py and day10_close.py import
# this module, so the guard covers them too. The code stays as a record.
if os.environ.get("CYNQRA_RERUN_CLOSED_RUN_002") != "destroy the audited record":
    raise SystemExit(
        "run_002 is closed. Read RUN.md and audit/AUDIT.md. These scripts are a record, not a tool."
    )

IST = timezone(timedelta(hours=5, minutes=30))
ROOT = Path(__file__).resolve().parent
WORKERS = ("cto", "pm", "eng_a", "eng_b")
EVENT_FIELDS = [
    "event_id",
    "event_type",
    "event_version",
    "company_id",
    "aggregate_type",
    "aggregate_id",
    "aggregate_version",
    "actor_type",
    "actor_id",
    "authority_snapshot",
    "policy_decision",
    "correlation_id",
    "causation_id",
    "command_id",
    "idempotency_key",
    "context_refs",
    "payload",
    "payload_schema_version",
    "source_service",
    "created_at",
]
BREAK_FIELDS = [
    "break_id",
    "day",
    "step",
    "what_broke",
    "canon_rule_that_failed",
    "who_had_to_step_in",
    "engineering_requirement",
    "severity",
]
INT_FIELDS = [
    "intervention_id",
    "created_at",
    "action",
    "counts",
    "reason",
    "related_decision_id",
    "related_event_id",
    "notes",
]

clock = datetime(2026, 8, 25, 20, 5, 0, tzinfo=IST)
event_n = 0
break_n = 0
cmd_n = 0
last_event = ""
protocol_tape = []
measures = {
    "run_id": "run_002",
    "started_at": None,
    "worker_turns": [],
    "protocol_objects_sent": 0,
    "founder_interventions": 0,
    "orchestrator_steps_in": 0,
    "tasks_verified": 0,
    "tasks_blocked": 0,
    "verification_catch_rate": None,
    "coordination_cost_objects_per_verified_task": None,
    "note": "Catch rate waits for Day 6. S1 waits for a model command.",
}


def now():
    global clock
    clock = clock + timedelta(seconds=37)
    return clock.isoformat()


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def home(worker: str) -> Path:
    return ROOT / "workers" / worker


def wipe():
    for name in ("workers", "shared", "golden_sets", "verification"):
        p = ROOT / name
        if p.exists():
            shutil.rmtree(p)
    for w in WORKERS:
        for sub in ("inbox", "workspace", "outbox", "log"):
            (home(w) / sub).mkdir(parents=True, exist_ok=True)
    (ROOT / "shared").mkdir(parents=True, exist_ok=True)
    (ROOT / "golden_sets").mkdir(parents=True, exist_ok=True)
    (ROOT / "verification").mkdir(parents=True, exist_ok=True)
    with (ROOT / "shared" / "event_log.csv").open("w", encoding="utf-8", newline="") as f:
        csv.DictWriter(f, fieldnames=EVENT_FIELDS).writeheader()
    with (ROOT / "shared" / "breaks.csv").open("w", encoding="utf-8", newline="") as f:
        csv.DictWriter(f, fieldnames=BREAK_FIELDS).writeheader()
    with (ROOT / "shared" / "founder_interventions.csv").open("w", encoding="utf-8", newline="") as f:
        csv.DictWriter(f, fieldnames=INT_FIELDS).writeheader()


def log_event(**row):
    global event_n, last_event, cmd_n
    event_n += 1
    cmd_n += 1
    eid = f"evt_{event_n:03d}"
    rec = {k: "" for k in EVENT_FIELDS}
    rec.update(row)
    rec["event_id"] = eid
    rec["event_version"] = rec.get("event_version") or "1"
    rec["company_id"] = "company_woz_001"
    rec["correlation_id"] = "run_002"
    rec["causation_id"] = rec.get("causation_id") or last_event
    rec["command_id"] = f"cmd_{cmd_n:03d}"
    rec["idempotency_key"] = f"idemp_{cmd_n:03d}"
    rec["payload_schema_version"] = rec.get("payload_schema_version") or "1"
    rec["source_service"] = rec.get("source_service") or "woz_run_002"
    rec["created_at"] = rec.get("created_at") or now()
    if not isinstance(rec["payload"], str):
        rec["payload"] = json.dumps(rec["payload"], separators=(",", ":"))
    if not isinstance(rec.get("context_refs"), str):
        rec["context_refs"] = json.dumps(rec.get("context_refs") or [])
    with (ROOT / "shared" / "event_log.csv").open("a", encoding="utf-8", newline="") as f:
        csv.DictWriter(f, fieldnames=EVENT_FIELDS).writerow(rec)
    last_event = eid
    return eid


def log_break(**row):
    global break_n
    break_n += 1
    rec = {k: "" for k in BREAK_FIELDS}
    rec.update(row)
    rec["break_id"] = f"b_{break_n:03d}"
    with (ROOT / "shared" / "breaks.csv").open("a", encoding="utf-8", newline="") as f:
        csv.DictWriter(f, fieldnames=BREAK_FIELDS).writerow(rec)
    measures["orchestrator_steps_in"] += 1 if rec.get("who_had_to_step_in") == "orchestrator" else 0
    return rec["break_id"]


def log_intervention(**row):
    rec = {k: "" for k in INT_FIELDS}
    rec.update(row)
    rec["counts"] = "yes"
    with (ROOT / "shared" / "founder_interventions.csv").open("a", encoding="utf-8", newline="") as f:
        csv.DictWriter(f, fieldnames=INT_FIELDS).writerow(rec)
    measures["founder_interventions"] += 1


def deliver(from_worker: str, to_worker: str, filename: str, obj=None, src: Path | None = None):
    """Copy one protocol object into the receiver inbox. Nothing else."""
    dest_dir = home(to_worker) / "inbox"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    if obj is not None:
        write_json(dest, obj)
    elif src is not None:
        shutil.copy2(src, dest)
    else:
        raise SystemExit("deliver needs obj or src")
    # orchestrator keeps a tape copy
    tape_path = ROOT / "shared" / "tape" / f"{from_worker}_to_{to_worker}_{filename}"
    shutil.copy2(dest, tape_path) if False else write_json(tape_path, read_json(dest))
    protocol_tape.append(
        {
            "from": from_worker,
            "to": to_worker,
            "file": filename,
            "protocol": read_json(dest).get("protocol", "object"),
            "at": now(),
        }
    )
    measures["protocol_objects_sent"] += 1
    log_event(
        event_type="protocol.sent",
        aggregate_type="protocol",
        aggregate_id=filename.replace(".json", ""),
        aggregate_version="1",
        actor_type="worker" if from_worker in WORKERS else "service",
        actor_id=f"w_{from_worker}" if from_worker in WORKERS else from_worker,
        authority_snapshot="low",
        policy_decision="ALLOW",
        payload={"from": from_worker, "to": to_worker, "file": filename},
    )
    return dest


def deliver_artifacts(to_worker: str, listed: list[str], from_dir: Path):
    copied = []
    missing = []
    inbox_art = home(to_worker) / "inbox" / "artifacts"
    inbox_art.mkdir(parents=True, exist_ok=True)
    for rel in listed:
        src = from_dir / Path(rel).name
        if not src.exists():
            missing.append(rel)
            continue
        shutil.copy2(src, inbox_art / src.name)
        copied.append(src.name)
    return copied, missing


def run_worker(worker: str, script: str) -> dict:
    """Run a worker script with cwd = that worker home. Refuse other homes."""
    start = datetime.now(IST)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "worker_scripts" / script)],
        cwd=str(home(worker)),
        capture_output=True,
        text=True,
        check=False,
        env={
            "PYTHONPATH": str(ROOT / "worker_scripts"),
            "CYNQRA_WORKER": worker,
            "CYNQRA_HOME": str(home(worker)),
            "CYNQRA_ROOT": str(ROOT),
        },
    )
    elapsed = (datetime.now(IST) - start).total_seconds()
    result = {
        "worker": worker,
        "script": script,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-2000:],
        "seconds": round(elapsed, 3),
    }
    write_json(home(worker) / "log" / f"{script}.json", result)
    measures["worker_turns"].append(
        {"worker": worker, "script": script, "seconds": result["seconds"], "ok": proc.returncode == 0}
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(f"worker {worker} failed on {script}")
    return result


def verify_tests(label: str, test_file: Path, cwd: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(test_file)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    out = {
        "label": label,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-2000:],
        "stderr": proc.stderr[-1000:],
        "passed": proc.returncode == 0,
    }
    write_json(ROOT / "verification" / f"{label}.json", out)
    return out


def html_esc(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_board(state: dict):
    breaks = list(csv.DictReader((ROOT / "shared" / "breaks.csv").open(encoding="utf-8")))
    events = list(csv.DictReader((ROOT / "shared" / "event_log.csv").open(encoding="utf-8")))
    ints = list(csv.DictReader((ROOT / "shared" / "founder_interventions.csv").open(encoding="utf-8")))
    days = state["days"]
    tape_html = ""
    for i, item in enumerate(protocol_tape):
        tape_html += (
            f'<div class="pearl"><div class="pearl-id">{html_esc(item["protocol"])}</div>'
            f'<div class="pearl-path">{html_esc(item["from"])} to {html_esc(item["to"])}</div>'
            f'<div class="pearl-file">{html_esc(item["file"])}</div></div>'
        )
        if i < len(protocol_tape) - 1:
            tape_html += '<div class="dot"></div>'
    break_rows = ""
    for b in breaks:
        break_rows += (
            "<tr>"
            f'<td>{html_esc(b["break_id"])}</td>'
            f'<td>{html_esc(b["day"])}</td>'
            f'<td>{html_esc(b["what_broke"])}</td>'
            f'<td>{html_esc(b["engineering_requirement"])}</td>'
            f'<td>{html_esc(b["severity"])}</td>'
            "</tr>"
        )
    day_rows = ""
    for d in days:
        mark = "done" if d["status"] == "done" else ("live" if d["status"] == "live" else "wait")
        day_rows += (
            f'<div class="day {mark}"><div class="day-n">Day {d["n"]}</div>'
            f'<div class="day-t">{html_esc(d["title"])}</div>'
            f'<div class="day-s">{html_esc(d["detail"])}</div></div>'
        )
    worker_cards = ""
    for w in WORKERS:
        inbox = sorted(p.name for p in (home(w) / "inbox").glob("*") if p.is_file() or p.is_dir())
        outbox = sorted(p.name for p in (home(w) / "outbox").glob("*") if p.is_file())
        st = state["worker_status"].get(w, "idle")
        worker_cards += (
            f'<div class="wcard"><div class="wrole">{html_esc(w)}</div>'
            f'<div class="wst {st}">{html_esc(st)}</div>'
            f'<div class="wmeta">inbox: {html_esc(", ".join(inbox) or "empty")}</div>'
            f'<div class="wmeta">outbox: {html_esc(", ".join(outbox) or "empty")}</div></div>'
        )
    cc = measures["coordination_cost_objects_per_verified_task"]
    cc_s = "not yet" if cc is None else f"{cc}"
    catch = measures["verification_catch_rate"]
    catch_s = "Day 6 not run" if catch is None else f"{catch}"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Cynqra Run 002</title>
<style>
  :root {{
    --ink: #2C2C2B;
    --muted: #7D7A75;
    --border: #E6E5E3;
    --surface: #F0EFED;
    --soft: #F9F8F7;
    --blue: #2783DE;
    --orange: #D5803B;
    --green: #46A171;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; background: var(--soft); color: var(--ink);
    font: 16px/1.45 "Liberation Sans", "Segoe UI", sans-serif; }}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 28px 22px 64px; }}
  h1 {{ font-size: 22px; font-weight: 650; margin: 0 0 6px; letter-spacing: -0.02em; }}
  .kicker {{ color: var(--muted); font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em; }}
  .lede {{ font-size: 18px; max-width: 40em; margin: 18px 0 8px; }}
  .note {{ color: var(--muted); max-width: 42em; margin: 0 0 28px; }}
  h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted);
    margin: 32px 0 12px; font-weight: 650; }}
  .nums {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
  .num {{ background: #fff; border: 1px solid var(--border); padding: 16px 18px; }}
  .num b {{ display: block; font-size: 28px; font-weight: 650; }}
  .num span {{ color: var(--muted); font-size: 13px; }}
  .workers {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }}
  .wcard {{ background: #fff; border: 1px solid var(--border); padding: 14px; min-height: 120px; }}
  .wrole {{ font-weight: 650; text-transform: uppercase; font-size: 12px; letter-spacing: 0.06em; }}
  .wst {{ font-size: 12px; margin: 6px 0; }}
  .wst.idle {{ color: var(--muted); }}
  .wst.done {{ color: var(--green); }}
  .wst.blocked {{ color: var(--orange); }}
  .wmeta {{ color: var(--muted); font-size: 12px; word-break: break-word; }}
  .tape {{ display: flex; flex-wrap: wrap; align-items: center; gap: 0; background: #fff;
    border: 1px solid var(--border); padding: 16px; }}
  .pearl {{ border: 1px solid var(--border); padding: 10px 12px; background: var(--soft); min-width: 140px; }}
  .pearl-id {{ font-weight: 650; font-size: 13px; }}
  .pearl-path, .pearl-file {{ color: var(--muted); font-size: 12px; }}
  .dot {{ width: 18px; height: 1px; background: var(--ink); margin: 0 4px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; font-size: 14px; }}
  th, td {{ text-align: left; vertical-align: top; padding: 10px 12px; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--muted); font-size: 12px; font-weight: 650; text-transform: uppercase; letter-spacing: 0.04em; }}
  .days {{ display: grid; gap: 8px; }}
  .day {{ display: grid; grid-template-columns: 64px 1fr; gap: 4px 12px; background: #fff;
    border: 1px solid var(--border); padding: 12px 14px; }}
  .day-n {{ font-weight: 650; font-size: 13px; }}
  .day-t {{ font-weight: 650; }}
  .day-s {{ color: var(--muted); font-size: 13px; grid-column: 2; }}
  .day.done .day-n {{ color: var(--green); }}
  .day.live .day-n {{ color: var(--blue); }}
  .day.wait .day-n {{ color: var(--muted); }}
  .call {{ background: #fff; border-left: 3px solid var(--orange); padding: 14px 16px; margin: 18px 0; }}
  .call b {{ display: block; margin-bottom: 4px; }}
  .tiny {{ font-size: 13px; color: var(--muted); max-width: 42em; }}
  button.tab {{ background: transparent; border: 1px solid var(--border); padding: 6px 10px; margin-right: 6px; cursor: pointer; }}
  button.tab.on {{ background: var(--ink); color: #fff; }}
  pre {{ background: #fff; border: 1px solid var(--border); padding: 12px; overflow: auto; font-size: 12px;
    font-family: "Liberation Mono", ui-monospace, monospace; }}
  @media (max-width: 800px) {{
    .nums, .workers {{ grid-template-columns: 1fr 1fr; }}
  }}
  @media (max-width: 520px) {{
    .nums, .workers {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="kicker">Cynqra · Wizard of Oz · company_woz_001</div>
  <h1>Run 002 is the first real run</h1>
  <p class="lede">Cynqra takes a human objective, builds the organization that will pursue it, runs that organization, and changes it when reality demands. The product is the organization layer: workers, authority, verification, and the objects that cross a boundary.</p>
  <p class="note">The candidate tracker is the chew toy for this run. It is not what we ship. If a screen shows candidates as the thing being built, that screen is wrong.</p>

  <div class="call">
    <b>Run 001 is void.</b>
    One process wrote the worker output, the tests, and the verdict. Nothing crossed a boundary. Two founder actions still count: confirming the objective, and rejecting elapsed time as the meaning of stuck.
  </div>

  <h2>Three numbers</h2>
  <div class="nums">
    <div class="num"><b>{measures["founder_interventions"]}</b><span>Founder interventions (reading does not count)</span></div>
    <div class="num"><b>{html_esc(cc_s)}</b><span>Protocol objects per verified task</span></div>
    <div class="num"><b>{html_esc(catch_s)}</b><span>Verification catch rate</span></div>
  </div>
  <p class="tiny">Verified tasks this run: {measures["tasks_verified"]}. Protocol objects sent: {measures["protocol_objects_sent"]}. Worker turns: {len(measures["worker_turns"])}.</p>

  <h2>Four workers</h2>
  <div class="workers">{worker_cards}</div>
  <p class="tiny">Each worker sees only its inbox. The next worker does not inherit memory. If the object is missing a fact, the receiver must raise a Blocker, not guess.</p>

  <h2>Protocol tape</h2>
  <div class="tape">{tape_html or "<div class='tiny'>No objects sent.</div>"}</div>

  <h2>Breaks (these become engineering requirements)</h2>
  <table>
    <thead><tr><th>ID</th><th>Day</th><th>What broke</th><th>Requirement</th><th>Sev</th></tr></thead>
    <tbody>{break_rows}</tbody>
  </table>

  <h2>Ten day script</h2>
  <div class="days">{day_rows}</div>

  <h2>Founder interventions that still count</h2>
  <table>
    <thead><tr><th>ID</th><th>Action</th><th>Reason</th></tr></thead>
    <tbody>
      {''.join(f"<tr><td>{html_esc(i['intervention_id'])}</td><td>{html_esc(i['action'])}</td><td>{html_esc(i['reason'])}</td></tr>" for i in ints)}
    </tbody>
  </table>

  <h2>What the chew toy was asked to do</h2>
  <p class="tiny">Product: internal candidate tracker. Success: create, set a stage, list, filter stuck. Constraint: no public site, no applicant login. Stuck is not a clock. Stuck is a named reason.</p>

  <p class="tiny">Event rows: {len(events)}. Generated {html_esc(state['generated_at'])}. Nothing to install. This file is the run surface.</p>
</div>
</body>
</html>"""
    (ROOT / "board.html").write_text(html, encoding="utf-8")
    shutil.copy2(ROOT / "board.html", Path("/data/cynqra-run-002.html"))


def main():
    global clock
    wipe()
    measures["started_at"] = now()
    (ROOT / "shared" / "tape").mkdir(parents=True, exist_ok=True)

    # Inherited founder facts. Not re-asked.
    objective = {
        "id": "obj_001",
        "company_id": "company_woz_001",
        "version": 1,
        "status": "confirmed",
        "messy": "I need a simple internal tracker so two recruiters can log candidates, move them through stages, and I can see who is stuck. No public careers site.",
        "structured": {
            "product": "internal candidate tracker",
            "target_customer": "founder and two recruiters",
            "primary_outcome": "every candidate has a visible stage and stuck candidates are obvious",
            "business_outcome": "founder can see who is stuck without asking",
            "success_criteria": "a recruiter can create a candidate, set a stage, list all candidates, and filter stuck ones",
            "constraints": "no public careers site, one company, no applicant login",
            "priorities": "stage visibility first, then stuck filter",
        },
        "confirmed_by": "founder",
        "confirmed_at": "2026-08-24T16:33:00+05:30",
        "inherited_from": "run_001",
    }
    write_json(ROOT / "shared" / "objective.json", objective)

    log_event(
        event_type="run.started",
        aggregate_type="run",
        aggregate_id="run_002",
        aggregate_version="1",
        actor_type="service",
        actor_id="orchestrator",
        authority_snapshot="platform",
        policy_decision="ALLOW",
        payload={"voids": "run_001", "keeps": ["obj_001", "decision_001"]},
    )
    log_event(
        event_type="company.created",
        aggregate_type="company",
        aggregate_id="company_woz_001",
        aggregate_version="1",
        actor_type="human",
        actor_id="founder",
        authority_snapshot="founder",
        policy_decision="ALLOW",
        payload={"name": "woz-company-001", "inherited": True},
    )
    log_event(
        event_type="objective.created",
        aggregate_type="objective",
        aggregate_id="obj_001",
        aggregate_version="1",
        actor_type="human",
        actor_id="founder",
        authority_snapshot="founder",
        policy_decision="ALLOW",
        payload={
            "product": "internal candidate tracker",
            "constraint_flags": "no_public_site,no_applicant_login",
            "inherited": True,
        },
    )
    log_intervention(
        intervention_id="int_001",
        created_at="2026-08-24T16:33:30+05:30",
        action="confirm_objective",
        reason="Day 1 founder confirmation of structured objective",
        related_decision_id="",
        related_event_id="evt_003",
        notes="Inherited from run 001. Still counts.",
    )

    log_break(
        day="0",
        step="run_001 close",
        what_broke="Worker output, tests, and verification were written by one process. The founder was shown the chew toy as the product.",
        canon_rule_that_failed="Book 4 WoZ: off the shelf tools play the four workers. Protocol objects must cross a boundary. The run surface is the organization, not the test project.",
        who_had_to_step_in="founder",
        engineering_requirement="Seal each worker filesystem. Move only protocol objects and listed artifacts. The run surface shows workers, tape, breaks, and the three numbers.",
        severity="SEV-1",
    )
    log_break(
        day="0",
        step="measurement setup",
        what_broke="No second verifier process exists in this environment. Catch rate cannot be independent while the operator is also the worker.",
        canon_rule_that_failed="Book 4: verification is the founder plus a second model. QA is not a fifth worker, and it is also not the same process as the engineer.",
        who_had_to_step_in="orchestrator",
        engineering_requirement="S3 and Day 6 need a separate verifier. Until then catch rate stays unreported.",
        severity="SEV-2",
    )
    log_break(
        day="0",
        step="worker runtime",
        what_broke="No off the shelf worker APIs are connected. Turns run as sealed scripts under the orchestrator.",
        canon_rule_that_failed="Book 4: off the shelf AI tools play the four workers.",
        who_had_to_step_in="orchestrator",
        engineering_requirement="M2 worker runtime must be separate processes. This run still enforces the file boundary, which run 001 did not.",
        severity="SEV-2",
    )

    # Day 1 already inherited. Day 2: CTO then PM.
    deliver("orchestrator", "cto", "objective.json", obj=objective)
    run_worker("cto", "cto_org.py")
    org = read_json(home("cto") / "outbox" / "organization.json")
    shutil.copy2(home("cto") / "outbox" / "organization.json", ROOT / "shared" / "organization.json")
    log_event(
        event_type="organization.changed",
        aggregate_type="organization",
        aggregate_id="org_001",
        aggregate_version="1",
        actor_type="worker",
        actor_id="w_cto",
        authority_snapshot="cto",
        policy_decision="ALLOW",
        payload={"template": org["template"], "worker_count": len(org["workers"])},
    )

    deliver("cto", "pm", "organization.json", src=home("cto") / "outbox" / "organization.json")
    deliver("orchestrator", "pm", "objective.json", obj=objective)
    run_worker("pm", "pm_plan.py")
    tasks = read_json(home("pm") / "outbox" / "tasks.json")
    shutil.copy2(home("pm") / "outbox" / "tasks.json", ROOT / "shared" / "tasks.json")
    for t in tasks["tasks"]:
        log_event(
            event_type="task.created",
            aggregate_type="task",
            aggregate_id=t["id"],
            aggregate_version="1",
            actor_type="worker",
            actor_id="w_pm",
            authority_snapshot="pm_low",
            policy_decision="ALLOW",
            payload={"risk_tier": t["risk_tier"], "owner_worker_id": t["owner_worker_id"]},
        )

    # Day 3: Engineer A, LOW, from PM handoff only.
    handoff_t001 = read_json(home("pm") / "outbox" / "handoff_t001.json")
    deliver("pm", "eng_a", "handoff.json", src=home("pm") / "outbox" / "handoff_t001.json")
    log_event(
        event_type="task.started",
        aggregate_type="task",
        aggregate_id="t_001",
        aggregate_version="1",
        actor_type="worker",
        actor_id="w_eng_a",
        authority_snapshot="eng_low",
        policy_decision="ALLOW",
        payload={"risk_tier": "LOW"},
    )
    run_worker("eng_a", "eng_a_t001.py")
    v1 = verify_tests(
        "t_001",
        home("eng_a") / "outbox" / "test_store.py",
        home("eng_a") / "outbox",
    )
    log_event(
        event_type="action.executed",
        aggregate_type="action",
        aggregate_id="a_001",
        aggregate_version="1",
        actor_type="worker",
        actor_id="w_eng_a",
        authority_snapshot="eng_low",
        policy_decision="ALLOW",
        payload={"action_type": "write_files", "task_id": "t_001"},
    )
    log_event(
        event_type="verification.completed",
        aggregate_type="verification",
        aggregate_id="v_001",
        aggregate_version="1",
        actor_type="service",
        actor_id="verification",
        authority_snapshot="platform",
        policy_decision="ALLOW",
        payload={"verdict": "VERIFIED" if v1["passed"] else "FAILED", "method": "automated_tests", "task_id": "t_001"},
    )
    if v1["passed"]:
        log_event(
            event_type="task.verified",
            aggregate_type="task",
            aggregate_id="t_001",
            aggregate_version="1",
            actor_type="service",
            actor_id="verification",
            authority_snapshot="platform",
            policy_decision="ALLOW",
            payload={"status": "VERIFIED"},
        )
        measures["tasks_verified"] += 1
        tasks["tasks"][0]["status"] = "VERIFIED"
    else:
        measures["tasks_blocked"] += 1
        log_break(
            day="3",
            step="t_001 verification",
            what_broke="Engineer A tests did not pass.",
            canon_rule_that_failed="LOW work verifies with automated checks.",
            who_had_to_step_in="orchestrator",
            engineering_requirement="Do not mark VERIFIED on a red test.",
            severity="SEV-1",
        )

    # Day 4: PM proposes stuck rule. Founder already decided. Do not re-ask.
    run_worker("pm", "pm_stuck_draft.py")
    draft = read_json(home("pm") / "outbox" / "approval_decision_001_draft.json")
    # First draft used elapsed time. That is the known failure mode.
    log_event(
        event_type="decision.created",
        aggregate_type="decision",
        aggregate_id="decision_001",
        aggregate_version="1",
        actor_type="worker",
        actor_id="w_pm",
        authority_snapshot="pm_medium",
        policy_decision="REQUIRE_APPROVAL",
        payload={"risk": "MEDIUM", "task_id": "t_003", "draft": "elapsed_time_as_stuck"},
    )
    # Founder intervention inherited.
    log_intervention(
        intervention_id="int_002",
        created_at="2026-08-24T16:56:00+05:30",
        action="reject_and_amend",
        reason="Rejected clock as stuck. Required a named reason.",
        related_decision_id="decision_001",
        related_event_id="",
        notes="Inherited from run 001. Still counts. Not re-asked.",
    )
    amended = read_json(home("pm") / "outbox" / "approval_decision_001.json")
    # Simulate PM receiving the founder label and writing the amended object.
    deliver("pm", "orchestrator", "approval_decision_001.json", src=home("pm") / "outbox" / "approval_decision_001.json")
    log_event(
        event_type="decision.approved",
        aggregate_type="decision",
        aggregate_id="decision_001",
        aggregate_version="2",
        actor_type="human",
        actor_id="founder",
        authority_snapshot="founder",
        policy_decision="ALLOW",
        payload={"outcome_label": "approved_edited", "risk": "MEDIUM"},
    )
    log_break(
        day="4",
        step="decision_001 first draft",
        what_broke="PM proposed elapsed time as the meaning of stuck. That describes a clock, not a cause.",
        canon_rule_that_failed="Book 1: a worker will confidently propose a metric that is not the thing anyone cares about. Only the founder caught it.",
        who_had_to_step_in="founder",
        engineering_requirement="MEDIUM product meaning rules require founder review. Seed this case in the eval corpus. Never treat a timer as a diagnosis.",
        severity="SEV-2",
    )
    write_json(
        ROOT / "golden_sets" / "gold_001.json",
        {
            "id": "gold_001",
            "source": "decision_001",
            "type": "decision_labeling",
            "messy": "A candidate in applied with no stage change for 8 days is stuck.",
            "gold": "Flagged only. Stuck requires a named reason from the closed list. If the stage already moved, both marks clear.",
            "label": "approved_edited",
            "what_would_change_this": "Evidence that recruiters need the clock itself to mean stuck.",
        },
    )

    # Day 5: Engineer A hands listed artifacts to Engineer B. Founder stays out.
    run_worker("eng_a", "eng_a_handoff_t002.py")
    handoff_t002 = read_json(home("eng_a") / "outbox" / "handoff_t002.json")
    deliver("eng_a", "eng_b", "handoff.json", src=home("eng_a") / "outbox" / "handoff_t002.json")
    copied, missing = deliver_artifacts(
        "eng_b",
        handoff_t002.get("artifacts", []),
        home("eng_a") / "outbox",
    )
    if missing:
        log_break(
            day="5",
            step="handoff_t002 artifacts",
            what_broke="Handoff listed files that were not in Engineer A outbox: " + ", ".join(missing),
            canon_rule_that_failed="Handoff artifacts must exist and must be the only files the receiver gets.",
            who_had_to_step_in="none",
            engineering_requirement="Reject a Handoff whose artifacts cannot be copied. Do not let the receiver hunt.",
            severity="SEV-2",
        )
        blocker = {
            "protocol": "Blocker",
            "raised_by": "w_eng_b",
            "task_id": "t_002",
            "category": "missing_input",
            "severity": "SEV-2",
            "description": "Listed artifacts were not delivered: " + ", ".join(missing),
            "needs_from": "w_eng_a",
        }
        write_json(home("eng_b") / "outbox" / "blocker_t002.json", blocker)
        deliver("eng_b", "eng_a", "blocker_t002.json", obj=blocker)
        measures["tasks_blocked"] += 1
    else:
        log_event(
            event_type="task.started",
            aggregate_type="task",
            aggregate_id="t_002",
            aggregate_version="1",
            actor_type="worker",
            actor_id="w_eng_b",
            authority_snapshot="eng_low",
            policy_decision="ALLOW",
            payload={"risk_tier": "LOW", "copied_artifacts": copied},
        )
        run_worker("eng_b", "eng_b_t002.py")
        blocker_path = home("eng_b") / "outbox" / "blocker.json"
        if blocker_path.exists():
            blocker = read_json(blocker_path)
            deliver("eng_b", "pm", "blocker.json", obj=blocker)
            log_break(
                day="5",
                step="t_002 first handoff",
                what_broke=blocker.get("description", "Engineer B raised a Blocker"),
                canon_rule_that_failed="Cross worker work proceeds by protocol object, not by guessing.",
                who_had_to_step_in="none",
                engineering_requirement="A Handoff must carry the closed list the receiver is not allowed to invent. Missing facts become Blockers, not guesses.",
                severity=blocker.get("severity", "SEV-2"),
            )
            run_worker("pm", "pm_stages.py")
            deliver(
                "pm",
                "eng_b",
                "handoff_stages.json",
                src=home("pm") / "outbox" / "handoff_t002_stages.json",
            )
            run_worker("eng_b", "eng_b_t002.py")
        blocker_path = home("eng_b") / "outbox" / "blocker.json"
        if blocker_path.exists():
            measures["tasks_blocked"] += 1
            v2 = {"passed": False, "stdout": "still blocked"}
        else:
            v2 = verify_tests(
                "t_002",
                home("eng_b") / "outbox" / "test_store.py",
                home("eng_b") / "outbox",
            )
            log_event(
                event_type="action.executed",
                aggregate_type="action",
                aggregate_id="a_002",
                aggregate_version="1",
                actor_type="worker",
                actor_id="w_eng_b",
                authority_snapshot="eng_low",
                policy_decision="ALLOW",
                payload={"action_type": "write_files", "task_id": "t_002"},
            )
            log_event(
                event_type="verification.completed",
                aggregate_type="verification",
                aggregate_id="v_002",
                aggregate_version="1",
                actor_type="service",
                actor_id="verification",
                authority_snapshot="platform",
                policy_decision="ALLOW",
                payload={"verdict": "VERIFIED" if v2["passed"] else "FAILED", "method": "automated_tests", "task_id": "t_002"},
            )
            if v2["passed"]:
                log_event(
                    event_type="task.verified",
                    aggregate_type="task",
                    aggregate_id="t_002",
                    aggregate_version="1",
                    actor_type="service",
                    actor_id="verification",
                    authority_snapshot="platform",
                    policy_decision="ALLOW",
                    payload={"status": "VERIFIED"},
                )
                measures["tasks_verified"] += 1
                tasks["tasks"][1]["status"] = "VERIFIED"
            else:
                measures["tasks_blocked"] += 1
                log_break(
                    day="5",
                    step="t_002 verification",
                    what_broke="Engineer B tests did not pass from the handed artifacts.",
                    canon_rule_that_failed="The receiver must be able to finish from the Handoff alone.",
                    who_had_to_step_in="none",
                    engineering_requirement="Acceptance checks on a Handoff must be executable by the receiver without extra context.",
                    severity="SEV-2",
                )

    # Protocol templates lack envelope fields. Record once, from inspection.
    log_break(
        day="5",
        step="protocol templates",
        what_broke="Handoff, Blocker, Escalation, and Approval templates have no created_at, protocol_version, or correlation_id.",
        canon_rule_that_failed="Book 2 event envelope: protocol messages are objects that must be attributable and replayable.",
        who_had_to_step_in="orchestrator",
        engineering_requirement="Add protocol_version, created_at, correlation_id, and from/to worker ids to every protocol object.",
        severity="SEV-3",
    )

    write_json(ROOT / "shared" / "tasks.json", tasks)
    if measures["tasks_verified"]:
        measures["coordination_cost_objects_per_verified_task"] = round(
            measures["protocol_objects_sent"] / measures["tasks_verified"], 2
        )
    write_json(ROOT / "shared" / "measures.json", measures)

    days = [
        {"n": 1, "title": "Objective", "status": "done", "detail": "Inherited. Founder confirmed the seven fields. int_001 counts."},
        {"n": 2, "title": "Organization and plan", "status": "done", "detail": "CTO instantiated fixed_mvp_4. PM opened t_001, t_002, t_003."},
        {"n": 3, "title": "First LOW risk work", "status": "done" if v1["passed"] else "live", "detail": "Engineer A built create and list from the PM Handoff only."},
        {"n": 4, "title": "First MEDIUM risk work", "status": "done", "detail": "PM draft used a clock. Founder rejected it. Amended rule adopted. int_002 counts."},
        {"n": 5, "title": "First cross worker dependency", "status": "done", "detail": "Engineer A handed artifacts to Engineer B. Founder was not in this path."},
        {"n": 6, "title": "Verification catch", "status": "wait", "detail": "Seed five defects, including one non code defect. Blocked until a second verifier exists."},
        {"n": 7, "title": "Budget breaker", "status": "wait", "detail": "Hit 50, 80, 95, then the cap. Work must enter PAUSED."},
        {"n": 8, "title": "HIGH risk gate", "status": "wait", "detail": "Attempt a HIGH action. It must stop. Reject one on purpose."},
        {"n": 9, "title": "Export and replay", "status": "wait", "detail": "Export repo, event log, decisions, breaks. Replay one task from the log."},
        {"n": 10, "title": "Close", "status": "wait", "detail": "Run report, golden sets, go or no go on M2."},
    ]
    worker_status = {"cto": "done", "pm": "done", "eng_a": "done", "eng_b": "done"}
    if (home("eng_b") / "outbox" / "blocker.json").exists() or missing:
        worker_status["eng_b"] = "blocked"
        days[4]["status"] = "live"
        days[4]["detail"] = "Engineer B could not finish from the Handoff. Blocker raised. Founder still not in the path."
    build_board(
        {
            "days": days,
            "worker_status": worker_status,
            "generated_at": now(),
        }
    )
    print(json.dumps({"measures": measures, "breaks": break_n, "events": event_n, "tape": protocol_tape}, indent=2))


if __name__ == "__main__":
    main()
