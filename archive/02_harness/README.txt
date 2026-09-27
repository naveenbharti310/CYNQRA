CYNQRA M1 BUILD KIT
Weeks 0 to 2 of M1, still open. Owner: CEO until a CPO exists.
Status: working kit. Not canon. Does not ratify any decision.
Updated 26 September 2026. The 25 August text said S1 needs no API key and
listed the spikes under Book 2 section 10. Both were wrong. See
../M1_RESTART_26SEP2026.md for what changed and why.

WHAT THIS IS
Measurement scaffolding for M1, not product. It runs:
1. The Wizard of Oz record (run 002, closed NO-GO, audited)
2. Spikes S1, S2, S3 (Book 2 section 9)

CONTENTS
m1.py                      Menu behind RUN_M1.bat in the handover root
spikes/preflight.py        What is ready and what is blocked
spikes/model_adapter.py    The only way any spike reaches a model (ADR-4)
spikes/s1/                 Objective structuring. RULINGS.md first
spikes/s2/                 Coordination cost. RULINGS.md first
spikes/s3/                 S3 v1, restated. S3_V1_RESTATEMENT.md
spikes/s3v2/               S3 v2, waiting on blind seeds. SEED_GUIDE.md
spikes/test_spikes.py      Harness tests, no key needed
kit/                       Protocol stamping, event log, verifier, contract
                           checks, model review tier, entity floor
protocols/                 Blocker, Handoff, Escalation, Approval templates
run_002/                   Closed run record. Scripts refuse to rerun
woz/                       Run 001 fixture, void as evidence
g0/                        G0 session material

HARD RULES
1. Protocol messages are structured objects, not free chat.
2. Event payloads carry no personal data.
3. HIGH risk actions need named founder approval.
4. One founder intervention is one action the founder takes, excluding reading.
5. A failed spike is a successful spike. An unrun spike is neither.
6. Keep run_002 next to kit and spikes. kit/test_kit.py reads it.
