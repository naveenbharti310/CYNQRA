# Cynqra POC

One founder sentence in, a live product out, with the founder deciding only what needs a
founder. Everything in the organization layer is real code: objective record, fixed
organization, protocol objects, policy before every action, Tool Gateway, budget breaker,
append only events, tiered verification, approval inbox, deployment lifecycle, export and
replay. The spec, the decisions it enforces and the acceptance tests are in POC_SPEC.md.

This POC is not gate evidence. S1, S2 and S3 v2 still decide Milestone 2.

## Run it

Windows: double click RUN_POC.bat in the project folder.

Any machine with Python 3.10 or newer:

    python poc/run_poc.py

Then open http://127.0.0.1:8750 if the browser does not open by itself. No packages to
install. Data lives in poc/data. New run archives the old one; nothing is deleted.

## Two modes

Demo. The workers' words come from a prepared scenario (an internal candidate tracker for
a recruiting firm). Every screen says it is demo mode. The code the workers hand over is
still written to disk, tested for real, merged for real and deployed for real on your
machine.

Live. A real model does the thinking through the same adapter the spikes use. Set
ANTHROPIC_API_KEY (default model claude-sonnet-5) or OPENAI_API_KEY (default gpt-4o-mini)
before starting, then choose Live in the first screen. Set CYNQRA_MODEL to pick another
model. A model error stops the run and says so. Nothing is invented to fill the gap.

## Real model test

    export ANTHROPIC_API_KEY=...        # or OPENAI_API_KEY
    python poc/live_check.py            # hard cap 3 dollars, --max-usd to change

Or double click RUN_M1.bat and choose 7; the key goes into a hidden prompt and is never
written down. It runs the whole journey against the real API, approves the founder's
decisions automatically (each one is listed), then checks the product independently: the
live URL must answer /health with 200 and the product's own tests must pass when rerun from
the merged repository. It writes poc/live_reports/live_<time>.json and .md with the
outcome, every call's measured tokens, the dollar spend, the plan and the metrics.

PASS, FAIL or UNRUN. A provider error, a missing key or the spend cap is UNRUN, never a
score. A model or network error in the UI shows Try the same step again; nothing the
failed call touched was written.

Without a key, `--allow-cmd` accepts a command model, such as tests/model_bridge.py, which
hands each prompt to a person or another model through files. Such a run is labelled
unmeasured. The 26 September run in live_reports/ was done this way; its README says what it
proves and what it does not. Optional: CYNQRA_MODEL to pick the model, CYNQRA_EFFORT (low to max) to set effort.
Live mode starts with a 600 work unit budget (one unit is 1000 real tokens); demo mode
starts with 120.

## What you will see, about five minutes in demo mode

1. Objective. Structure the sentence into seven fields. Two are marked inferred. Edit,
   set the budget cap, confirm. Founder decision 1.
2. Plan. The fixed organization (CTO, PM, Engineer A, Engineer B, plus the Verification
   Service) and six tasks. Approve. Founder decision 2.
3. Work. Press Run. Engineer A's first attempt fails a test and goes back for rework.
   Engineer B raises a Blocker; the PM clears it without you. The CTO tries to email the
   recruiters; policy denies it without you.
4. Your inbox gets four cards: a product rule (MEDIUM), the merge (MEDIUM), the production
   deploy (HIGH) and delivery. Approve each. Founder decisions 3 to 6.
5. Delivery. The product is live on a local URL. Open it, add a candidate. Download the
   export bundle. Replay any task in Audit.

Try also: the kill switch, a low budget cap (the breaker stops work at 100 percent),
editing the objective mid run (the run pauses for your reconfirmation), and rejecting a
card (the work goes back with your note).

## Test it

    cd poc/tests
    python -m unittest -v

The browser test runs when Node and Playwright are installed and is skipped otherwise.
TEST_REPORT.md holds the last full run and its coverage.

## Folder map

| Path | What it is |
| --- | --- |
| run_poc.py | Starts the server and opens the browser |
| live_check.py | The real model test of the whole journey, with a spend cap and a written report |
| live_reports/ | Reports of real model runs, with what each one proves |
| cynqra/engine.py | The orchestrator: journey, gateway, decisions, verification, delivery, replay, export |
| cynqra/policy.py | D-27 risk rubric and D-28 authority matrix as code |
| cynqra/protocol.py | Handoff, Blocker, Escalation, Approval as stamped, hashed objects |
| cynqra/db.py | SQLite store; events are append only, enforced by triggers |
| cynqra/deploy.py | BUILD to LIVE with health, smoke and rollback |
| cynqra/verification.py | Test runner and document lint, with a cleaned environment |
| cynqra/intelligence.py | Demo source and live model source; the platform validates every plan |
| cynqra/model_adapter.py | Byte for byte copy of 02_harness/spikes/model_adapter.py |
| cynqra/server.py | HTTP API and static UI |
| ui/ | The web app, vanilla HTML, CSS and JS, fonts bundled |
| scenarios/candidate_tracker | The demo scenario and the real product code the workers hand over |
| design/ | High level screen mockups, copied from the design canvas |
| tests/ | Unit, journey, failure path, provider wire, API and browser tests |
| demo/ | How the demo video is recorded; the video sits next to the project folder |

## Limits, stated plainly

No kernel isolation for worker code (a folder and a cleaned subprocess, not a container).
Single user. The deployment target is a local process. Rejecting delivery keeps the
product live and records the note; iterating on a delivered product is outside this POC.
