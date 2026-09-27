S2 RUN SHEET
Estimate locked: 25 August 2026 in spikes/S2_ESTIMATE.md
Runner written: 26 September 2026, spikes/s2/run_s2.py. Rulings in RULINGS.md.
Do not edit the estimate, tasks.json, company_context.json or RULINGS.md after
scoring begins.

Template: CTO, PM, Engineer A, Engineer B.
Project category: CRUD (D-6 ratified).
Tasks: 12 across 3 workstreams, from tasks.json.
Every coordination message is a protocol object.

How to run
Windows: double click RUN_M1.bat in the handover root and choose S2.
Any machine: python spikes/s2/run_s2.py with ANTHROPIC_API_KEY or OPENAI_API_KEY set.

Recorded per task
task_id, owner, risk, status, protocol_count, model_calls, tokens_in, tokens_out,
wall_minutes, retries, blocker_rounds, founder_touched, structured

Pass
Every estimate line within 0.5x to 2x of its measured median, all 12 tasks
finished, every message structured. See RULINGS.md R1.

Honesty rule
A token count estimated from characters is not a measured result. Those runs
write s2_wiring_test.json only.

This sheet is empty of results until a scored run exists.
