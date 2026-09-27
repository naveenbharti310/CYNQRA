#!/usr/bin/env python3
"""Day 10 close. Does not wipe. Does not start M2."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import runner
from days_6_9 import hydrate

ROOT = runner.ROOT


def write_close_html():
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Cynqra Run 002 close</title>
<style>
  :root { --ink:#2C2C2B; --muted:#7D7A75; --border:#E6E5E3; --soft:#F9F8F7; --blue:#2783DE; --orange:#D5803B; --green:#46A171; }
  * { box-sizing: border-box; }
  html, body { margin:0; padding:0; background:var(--soft); color:var(--ink); font:16px/1.45 "Liberation Sans","Segoe UI",sans-serif; }
  .wrap { max-width: 820px; margin: 0 auto; padding: 28px 22px 72px; }
  .kicker { color:var(--muted); font-size:13px; text-transform:uppercase; letter-spacing:0.08em; }
  h1 { font-size:22px; font-weight:650; margin:6px 0 14px; }
  h2 { font-size:13px; text-transform:uppercase; letter-spacing:0.08em; color:var(--muted); margin:28px 0 10px; }
  p { max-width: 42em; }
  .verdict { background:#fff; border-left:3px solid var(--orange); padding:16px 18px; margin:18px 0; }
  .verdict b { display:block; font-size:20px; margin-bottom:6px; }
  .nums { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
  .num { background:#fff; border:1px solid var(--border); padding:16px 18px; }
  .num b { display:block; font-size:28px; font-weight:650; }
  .num span { color:var(--muted); font-size:13px; }
  ul { padding-left: 1.2em; max-width: 42em; }
  li { margin: 6px 0; }
  .tiny { color:var(--muted); font-size:13px; }
  @media (max-width: 640px) { .nums { grid-template-columns:1fr; } }
</style>
</head>
<body>
<div class="wrap">
  <div class="kicker">Cynqra · Run 002 · Day 10</div>
  <h1>M2 does not start</h1>
  <div class="verdict">
    <b>NO-GO</b>
    The loop was tested. Catch rate missed the bar. S1 and S2 were not scored. Workers were sealed scripts, not off the shelf tools. G0 has not been held. Building the runtime now would freeze those gaps into the product.
  </div>
  <p>Cynqra is the organization layer: an objective, workers, authority, verification, and the objects that cross a boundary. The candidate tracker was the chew toy. It is not what we ship.</p>

  <h2>Three numbers</h2>
  <div class="nums">
    <div class="num"><b>3</b><span>Founder interventions</span></div>
    <div class="num"><b>4.0</b><span>Protocol objects per verified task</span></div>
    <div class="num"><b>0.4</b><span>Catch rate. Bar 0.8. Not met.</span></div>
  </div>

  <h2>What worked</h2>
  <ul>
    <li>Engineer B refused to invent the stage list and raised a Blocker. PM cleared it. The founder was not in that path.</li>
    <li>A 7 day clock was rejected as the meaning of stuck. gold_001 exists.</li>
    <li>A HIGH external message stopped and was rejected. Nothing was sent.</li>
    <li>At budget cap 100, OPEN work entered PAUSED.</li>
  </ul>

  <h2>What missed</h2>
  <ul>
    <li>Held t_002 tests caught 2 of 5 seeded defects. Empty name, list completeness, and a spec that redefined stuck as a clock all slipped.</li>
    <li>The event log cannot replay a task. It names files, not closed lists, Blocker text, tests, or source.</li>
    <li>S1 has no model command. S2 had no pre-run estimate and no token meter.</li>
  </ul>

  <h2>Instead of M2</h2>
  <ul>
    <li>Hold G0. Vote the open decisions. Send D-22 to counsel.</li>
    <li>Attach a model command and run S1. Bar 8 of 10.</li>
    <li>Write the S2 estimate first, then measure tokens.</li>
    <li>Reseed S3 to 10 defects with a verifier that cannot see the seeds and is not the worker.</li>
    <li>Fix protocol envelope, prior-test rerun, and event payloads before any runtime build.</li>
  </ul>

  <p class="tiny">Do not start dashboards, design, or M2 on this report. Run 001 is void. Run 002 is closed.</p>
</div>
</body>
</html>
"""
    path = ROOT / "day10" / "close.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    shutil.copy2(path, Path("/data/cynqra-run-002-close.html"))
    return path


def main():
    hydrate()
    runner.measures["verdict"] = "NO-GO"
    runner.measures["m2"] = "does_not_start"
    runner.measures["closed_at"] = runner.now()
    runner.measures["note"] = (
        "Run 002 closed. M2 NO-GO. Catch rate 0.4 missed bar 0.8. "
        "S1 not scored. S2 not scored. G0 not held."
    )
    runner.log_event(
        event_type="run.closed",
        aggregate_type="run",
        aggregate_id="run_002",
        aggregate_version="1",
        actor_type="service",
        actor_id="orchestrator",
        authority_snapshot="platform",
        policy_decision="DENY",
        payload={"verdict": "NO-GO", "m2": "does_not_start", "catch_rate": 0.4},
    )
    runner.write_json(ROOT / "shared" / "measures.json", runner.measures)
    shutil.copy2(ROOT / "day10" / "run_report.md", ROOT / "shared" / "run_report.md")
    shutil.copy2(Path("/data/cynqra_m1/spikes/S2_MEMO.md"), ROOT / "day10" / "S2_MEMO.md")
    shutil.copy2(Path("/data/cynqra_m1/spikes/S3_MEMO.md"), ROOT / "day10" / "S3_MEMO.md")
    write_close_html()
    days = [
        {"n": 1, "title": "Objective", "status": "done", "detail": "Inherited. Founder confirmed the seven fields. int_001 counts."},
        {"n": 2, "title": "Organization and plan", "status": "done", "detail": "CTO instantiated fixed_mvp_4. PM opened t_001, t_002, t_003."},
        {"n": 3, "title": "First LOW risk work", "status": "done", "detail": "Engineer A built create and list from the PM Handoff only."},
        {"n": 4, "title": "First MEDIUM risk work", "status": "done", "detail": "PM draft used a clock. Founder rejected it. Amended rule adopted. int_002 counts."},
        {"n": 5, "title": "First cross worker dependency", "status": "done", "detail": "Engineer B raised a Blocker. PM sent the closed list. Founder was not in this path."},
        {"n": 6, "title": "Verification catch", "status": "done", "detail": "5 defects seeded including one spec. Held t_002 tests caught 2 of 5. Bar 80% not met."},
        {"n": 7, "title": "Budget breaker", "status": "done", "detail": "Hit 50, 80, 95, then 100. OPEN work entered PAUSED."},
        {"n": 8, "title": "HIGH risk gate", "status": "done", "detail": "External message stopped. decision_002 rejected. int_003 counts. No send."},
        {"n": 9, "title": "Export and replay", "status": "done", "detail": "Export written. t_002 replayed from the log. Stage list was not in the payload."},
        {"n": 10, "title": "Close", "status": "done", "detail": "Run report written. M2 is NO-GO. S1 not scored. G0 not held."},
    ]
    runner.build_board(
        {
            "days": days,
            "worker_status": {"cto": "done", "pm": "done", "eng_a": "done", "eng_b": "done"},
            "generated_at": runner.now(),
        }
    )
    print(json.dumps({"verdict": "NO-GO", "m2": "does_not_start"}, indent=2))


if __name__ == "__main__":
    main()
