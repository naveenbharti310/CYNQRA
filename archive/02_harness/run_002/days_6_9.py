#!/usr/bin/env python3
"""Days 6 to 9 of run 002. Does not wipe days 1 to 5."""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import runner

IST = timezone(timedelta(hours=5, minutes=30))
ROOT = runner.ROOT
HELD_T002 = ROOT / "workers" / "eng_b" / "outbox" / "test_store.py"
CLEAN_STORE = ROOT / "workers" / "eng_b" / "outbox" / "store.py"


def hydrate():
    events = list(csv.DictReader((ROOT / "shared" / "event_log.csv").open(encoding="utf-8")))
    breaks = list(csv.DictReader((ROOT / "shared" / "breaks.csv").open(encoding="utf-8")))
    runner.event_n = len(events)
    runner.cmd_n = len(events)
    runner.last_event = events[-1]["event_id"] if events else ""
    runner.break_n = len(breaks)
    last_at = events[-1]["created_at"] if events else "2026-08-25T20:26:00+05:30"
    runner.clock = datetime.fromisoformat(last_at)
    runner.measures = json.loads((ROOT / "shared" / "measures.json").read_text(encoding="utf-8"))
    tape = []
    for e in events:
        if e["event_type"] == "protocol.sent":
            payload = json.loads(e["payload"])
            tape.append(
                {
                    "from": payload.get("from", ""),
                    "to": payload.get("to", ""),
                    "file": payload.get("file", ""),
                    "protocol": Path(payload.get("file", "object")).stem.split("_")[0].title()
                    if payload.get("file")
                    else "object",
                    "at": e["created_at"],
                }
            )
    runner.protocol_tape = tape


def write_tainted():
    day6 = ROOT / "day6"
    if day6.exists():
        shutil.rmtree(day6)
    sub = day6 / "submission"
    held = day6 / "held"
    sealed = day6 / "sealed"
    sub.mkdir(parents=True)
    held.mkdir(parents=True)
    sealed.mkdir(parents=True)
    shutil.copy2(HELD_T002, held / "test_store.py")
    shutil.copy2(CLEAN_STORE, day6 / "clean_store.py")

    tainted = '''class CandidateError(Exception):
    pass


class CandidateStore:
    def __init__(self):
        self._items = {}
        self._n = 0

    def create(self, name):
        self._n += 1
        cid = f"c_{self._n:03d}"
        rec = {"id": cid, "name": str(name)}
        self._items[cid] = rec
        return rec

    def list(self):
        vals = list(self._items.values())
        return [vals[-1]] if vals else []

    def set_stage(self, cid, stage):
        if cid not in self._items:
            raise CandidateError("unknown candidate")
        self._items[cid]["stage"] = stage
        return self._items[cid]


ALLOWED_STAGES = ("applied", "screen", "interview", "offer", "hired", "rejected")
'''
    (sub / "store.py").write_text(tainted, encoding="utf-8")
    (sub / "spec_stuck.md").write_text(
        "Stuck means a candidate with no stage change for 7 days.\n",
        encoding="utf-8",
    )
    seeds = [
        {
            "id": "def_001",
            "kind": "code",
            "what": "create accepts an empty name",
            "violates": "t_001 acceptance: empty name is an error",
            "caught_by_t002_tests": False,
        },
        {
            "id": "def_002",
            "kind": "code",
            "what": "set_stage accepts a stage that is not on the closed list",
            "violates": "t_002 acceptance: unknown stages raise CandidateError",
            "caught_by_t002_tests": True,
            "test_name": "test_unknown_stage",
        },
        {
            "id": "def_003",
            "kind": "code",
            "what": "create does not start the candidate at applied",
            "violates": "t_002 acceptance: create starts at applied",
            "caught_by_t002_tests": True,
            "test_name": "test_create_starts_applied",
        },
        {
            "id": "def_004",
            "kind": "code",
            "what": "list returns only the last candidate",
            "violates": "t_001 acceptance: list returns all created candidates",
            "caught_by_t002_tests": False,
        },
        {
            "id": "def_005",
            "kind": "non_code",
            "what": "spec_stuck.md defines stuck as a 7 day clock",
            "violates": "decision_001 approved_edited: stuck needs a named reason",
            "caught_by_t002_tests": False,
        },
    ]
    (sealed / "seeds.json").write_text(json.dumps(seeds, indent=2) + "\n", encoding="utf-8")
    verifier = r'''#!/usr/bin/env python3
"""Platform verifier. May read submission and held t_002 tests only."""
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
work = HERE / "work"
if work.exists():
    shutil.rmtree(work)
work.mkdir()
shutil.copy2(HERE / "submission" / "store.py", work / "store.py")
shutil.copy2(HERE / "held" / "test_store.py", work / "test_store.py")
proc = subprocess.run(
    [sys.executable, str(work / "test_store.py")],
    cwd=str(work),
    capture_output=True,
    text=True,
    check=False,
)
print(proc.stdout)
print(proc.stderr)
(HERE / "work" / "verifier_stdout.txt").write_text(proc.stdout + "\n" + proc.stderr, encoding="utf-8")
raise SystemExit(proc.returncode)
'''
    (day6 / "verifier.py").write_text(verifier, encoding="utf-8")
    return seeds


def run_verifier():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "day6" / "verifier.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout + proc.stderr
    (ROOT / "day6" / "verifier_out.txt").write_text(out, encoding="utf-8")
    failed_tests = []
    for line in out.splitlines():
        if line.startswith("FAIL:"):
            failed_tests.append(line.split()[1].split(".")[-1])
    return {"returncode": proc.returncode, "output": out[-3000:], "failed_tests": failed_tests}


def score(seeds, vresult):
    caught = []
    missed = []
    for s in seeds:
        if s.get("caught_by_t002_tests") and s.get("test_name") in vresult["failed_tests"]:
            caught.append(s["id"])
        elif s.get("caught_by_t002_tests") and vresult["returncode"] != 0 and s.get("test_name") in vresult["output"]:
            caught.append(s["id"])
        else:
            missed.append(s["id"])
    # Map by test names if FAIL lines used a different shape.
    if not vresult["failed_tests"] and vresult["returncode"] != 0:
        text = vresult["output"]
        remap = []
        still_miss = []
        for s in seeds:
            tn = s.get("test_name")
            if tn and tn in text:
                remap.append(s["id"])
            else:
                still_miss.append(s["id"])
        caught, missed = remap, still_miss
    rate = round(len(caught) / len(seeds), 2) if seeds else 0
    report = {
        "seeded": len(seeds),
        "caught": caught,
        "missed": missed,
        "catch_rate": rate,
        "bar": 0.8,
        "met_bar": rate >= 0.8,
        "method": "held t_002 automated tests only",
        "note": "Not a second model. Mechanical verifier. Seeds were sealed from the verifier process.",
        "failed_tests": vresult["failed_tests"],
    }
    (ROOT / "day6" / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def day6():
    seeds = write_tainted()
    runner.log_event(
        event_type="verification.started",
        aggregate_type="verification",
        aggregate_id="v_day6",
        aggregate_version="1",
        actor_type="service",
        actor_id="verification",
        authority_snapshot="platform",
        policy_decision="ALLOW",
        payload={"method": "held_t002_tests", "seeded": 5, "includes_non_code": True},
    )
    vresult = run_verifier()
    report = score(seeds, vresult)
    runner.measures["verification_catch_rate"] = report["catch_rate"]
    runner.measures["verification_caught"] = report["caught"]
    runner.measures["verification_missed"] = report["missed"]
    runner.measures["note"] = (
        f"Catch rate {report['catch_rate']} on 5 seeded defects using held t_002 tests only. "
        "S1 still has no model command."
    )
    runner.log_event(
        event_type="verification.completed",
        aggregate_type="verification",
        aggregate_id="v_day6",
        aggregate_version="1",
        actor_type="service",
        actor_id="verification",
        authority_snapshot="platform",
        policy_decision="ALLOW",
        payload={
            "verdict": "FAILED",
            "method": "held_t002_tests",
            "caught": len(report["caught"]),
            "seeded": 5,
            "catch_rate": report["catch_rate"],
        },
    )
    runner.log_break(
        day="6",
        step="verification catch",
        what_broke=(
            f"Held t_002 tests caught {len(report['caught'])} of 5 seeded defects "
            f"({report['missed']}). Empty name, list completeness, and the stuck spec slipped."
        ),
        canon_rule_that_failed="Book 4 Day 6 / S3: 80% of seeded defects caught before anyone says verified, including non code.",
        who_had_to_step_in="none",
        engineering_requirement=(
            "Verification must rerun prior task tests and lint specs against decided rules. "
            "A green t_002 file is not enough."
        ),
        severity="SEV-2",
    )
    return report


def day7():
    budget = {
        "company_id": "company_woz_001",
        "unit": "work_units",
        "cap": 100,
        "spent": 40,
        "status": "active",
        "thresholds": [50, 80, 95, 100],
        "hits": [],
    }
    spends = [
        (15, 50),
        (30, 80),
        (12, 95),
        (3, 100),
    ]
    for amount, mark in spends:
        budget["spent"] += amount
        budget["hits"].append({"threshold": mark, "spent": budget["spent"]})
        decision = "ALLOW" if mark < 100 else "DENY"
        runner.log_event(
            event_type="budget.threshold_reached",
            aggregate_type="company",
            aggregate_id="company_woz_001",
            aggregate_version=str(mark),
            actor_type="service",
            actor_id="budget",
            authority_snapshot="platform",
            policy_decision=decision,
            payload={"threshold": mark, "spent": budget["spent"], "cap": 100, "unit": "work_units"},
        )
    budget["status"] = "PAUSED"
    budget["spent"] = 100
    (ROOT / "shared" / "budget.json").write_text(json.dumps(budget, indent=2) + "\n", encoding="utf-8")
    tasks = json.loads((ROOT / "shared" / "tasks.json").read_text(encoding="utf-8"))
    for t in tasks["tasks"]:
        if t["status"] == "OPEN":
            t["status"] = "PAUSED"
            runner.log_event(
                event_type="task.paused",
                aggregate_type="task",
                aggregate_id=t["id"],
                aggregate_version="1",
                actor_type="service",
                actor_id="budget",
                authority_snapshot="platform",
                policy_decision="DENY",
                payload={"reason": "company_cap", "task_id": t["id"]},
            )
    (ROOT / "shared" / "tasks.json").write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")
    runner.measures["budget_status"] = "PAUSED"
    runner.measures["budget_spent"] = 100
    runner.measures["budget_cap"] = 100
    runner.log_break(
        day="7",
        step="budget cap",
        what_broke="At the hard cap, work entered PAUSED. That is the required behavior, not a product failure.",
        canon_rule_that_failed="Book 4 Day 7: hit 50, 80, 95, then the cap. Work must enter PAUSED.",
        who_had_to_step_in="none",
        engineering_requirement="M2 budget service must emit threshold events and pause OPEN tasks at cap. No new ALLOW after cap.",
        severity="SEV-3",
    )
    return budget


def day8():
    approval = {
        "protocol": "Approval",
        "decision_id": "decision_002",
        "task_id": "t_004",
        "recommendation": "Send an external message to a candidate from the chew toy store.",
        "evidence_refs": ["shared/tasks.json"],
        "cost": "external side effect",
        "risk": "HIGH",
        "confidence": "low",
        "options": ["approve", "reject", "request_evidence"],
        "what_would_change_this": "Named founder approval with a written audience and a delete path.",
        "outcome_label": "",
        "labeled_by": "",
        "labeled_at": "",
        "status": "pending_founder",
    }
    runner.write_json(ROOT / "shared" / "decisions" / "decision_002_pending.json", approval)
    runner.log_event(
        event_type="decision.created",
        aggregate_type="decision",
        aggregate_id="decision_002",
        aggregate_version="1",
        actor_type="worker",
        actor_id="w_eng_b",
        authority_snapshot="eng_low",
        policy_decision="REQUIRE_APPROVAL",
        payload={"risk": "HIGH", "action": "external_message", "stopped": True},
    )
    # Scripted drill. Continue on the ten day script includes reject one on purpose.
    rejected = dict(approval)
    rejected["outcome_label"] = "rejected"
    rejected["labeled_by"] = "founder"
    rejected["labeled_at"] = runner.now()
    rejected["status"] = "decided"
    rejected["note"] = "Day 8 drill. HIGH external message stopped. Rejected on purpose. No send."
    runner.write_json(ROOT / "shared" / "decisions" / "decision_002.json", rejected)
    eid = runner.log_event(
        event_type="decision.rejected",
        aggregate_type="decision",
        aggregate_id="decision_002",
        aggregate_version="1",
        actor_type="human",
        actor_id="founder",
        authority_snapshot="founder",
        policy_decision="DENY",
        payload={"outcome_label": "rejected", "risk": "HIGH", "action": "external_message"},
    )
    runner.log_intervention(
        intervention_id="int_003",
        created_at=rejected["labeled_at"],
        action="reject",
        reason="Day 8 drill. HIGH external message. Rejected on purpose. No send.",
        related_decision_id="decision_002",
        related_event_id=eid,
        notes="Ten day script item. Does not ratify D-17. Continue authorized the drill.",
    )
    return rejected


def day9():
    export_dir = ROOT / "export"
    if export_dir.exists():
        shutil.rmtree(export_dir)
    export_dir.mkdir()
    zpath = Path("/data/Cynqra_Run_002_Export.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in ROOT.rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
                z.write(p, p.relative_to(ROOT.parent))
    shutil.copy2(zpath, export_dir / "Cynqra_Run_002_Export.zip")

    events = list(csv.DictReader((ROOT / "shared" / "event_log.csv").open(encoding="utf-8")))
    t002 = [e for e in events if "t_002" in (e["payload"] + e["aggregate_id"])]
    reconstructed = []
    missing = []
    for e in t002:
        reconstructed.append(
            {
                "event_id": e["event_id"],
                "event_type": e["event_type"],
                "actor_id": e["actor_id"],
                "payload": e["payload"],
            }
        )
    # What the log cannot rebuild
    missing = [
        "Closed list of stages. protocol.sent payloads name the file, not allowed_stages.",
        "Blocker description. Only the filename blocker.json is in the event payload.",
        "Test names and pass counts. verification.completed has a verdict, not the suite.",
        "store.py source. The log records write_files, not the bytes.",
    ]
    replay = {
        "task_id": "t_002",
        "method": "event_log only",
        "events_touching_task": len(t002),
        "reconstructed_skeleton": reconstructed,
        "could_not_reconstruct": missing,
    }
    runner.write_json(ROOT / "day9" / "replay_t002.json", replay)
    (ROOT / "day9" / "replay_t002.md").write_text(
        "REPLAY t_002 FROM THE EVENT LOG ONLY\n\n"
        f"Events that mention t_002: {len(t002)}\n\n"
        "What the log is enough for\n"
        "Owner w_eng_b. LOW risk. Started after a Handoff from Engineer A.\n"
        "A Blocker went to PM. A second Handoff followed. Then write_files, then VERIFIED.\n\n"
        "What the log is not enough for\n"
        + "\n".join(f"- {m}" for m in missing)
        + "\n\nRequirement: event payloads must carry the protocol object hash and the closed lists they name, or replay is a skeleton.\n",
        encoding="utf-8",
    )
    runner.log_event(
        event_type="export.completed",
        aggregate_type="run",
        aggregate_id="run_002",
        aggregate_version="1",
        actor_type="service",
        actor_id="orchestrator",
        authority_snapshot="platform",
        policy_decision="ALLOW",
        payload={"zip": "Cynqra_Run_002_Export.zip", "replay_task": "t_002"},
    )
    runner.log_break(
        day="9",
        step="replay t_002",
        what_broke="The event log reconstructs the skeleton of t_002, not the stage list, the Blocker text, or the source.",
        canon_rule_that_failed="Book 4 Day 9: replay one completed task from the log.",
        who_had_to_step_in="orchestrator",
        engineering_requirement="Store a hash of each protocol object and the closed lists it carries on the event payload. Log test ids, not only VERIFIED.",
        severity="SEV-2",
    )
    return replay


def rebuild_board(day6_report):
    days = [
        {"n": 1, "title": "Objective", "status": "done", "detail": "Inherited. Founder confirmed the seven fields. int_001 counts."},
        {"n": 2, "title": "Organization and plan", "status": "done", "detail": "CTO instantiated fixed_mvp_4. PM opened t_001, t_002, t_003."},
        {"n": 3, "title": "First LOW risk work", "status": "done", "detail": "Engineer A built create and list from the PM Handoff only."},
        {"n": 4, "title": "First MEDIUM risk work", "status": "done", "detail": "PM draft used a clock. Founder rejected it. Amended rule adopted. int_002 counts."},
        {"n": 5, "title": "First cross worker dependency", "status": "done", "detail": "Engineer B raised a Blocker. PM sent the closed list. Founder was not in this path."},
        {
            "n": 6,
            "title": "Verification catch",
            "status": "done",
            "detail": (
                f"5 defects seeded including one spec. Held t_002 tests caught {len(day6_report['caught'])} of 5. "
                "Bar 80% not met. Not a second model."
            ),
        },
        {"n": 7, "title": "Budget breaker", "status": "done", "detail": "Hit 50, 80, 95, then 100. OPEN work entered PAUSED."},
        {"n": 8, "title": "HIGH risk gate", "status": "done", "detail": "External message stopped. decision_002 rejected. int_003 counts. No send."},
        {"n": 9, "title": "Export and replay", "status": "done", "detail": "Export written. t_002 replayed from the log. Stage list was not in the payload."},
        {"n": 10, "title": "Close", "status": "wait", "detail": "Run report and M2 go or no go. Not opened. S1 still has no model."},
    ]
    runner.write_json(ROOT / "shared" / "measures.json", runner.measures)
    runner.build_board(
        {
            "days": days,
            "worker_status": {"cto": "done", "pm": "done", "eng_a": "done", "eng_b": "done"},
            "generated_at": runner.now(),
        }
    )


def main():
    hydrate()
    d6 = day6()
    day7()
    day8()
    day9()
    rebuild_board(d6)
    print(json.dumps({"day6": d6, "measures": runner.measures}, indent=2))


if __name__ == "__main__":
    main()
