# Cynqra POC

One founder sentence in, a live product out, with the founder deciding only what needs a
founder. It follows Cynqra Product Flows and Architecture v1 (see ../CYNQRA_PRODUCT_ALIGNMENT.md).
Everything in the organization layer is real code: objective and requirements, a workforce
synthesized from the role catalog, intelligence per worker, roadmap and budget, protocol objects, policy before every action, Tool Gateway, budget breaker,
append only events, tiered verification, approval inbox, deployment lifecycle, export and
replay. The spec, the decisions it enforces and the acceptance tests are in POC_SPEC.md.

This POC is not gate evidence. S1, S2 and S3 v2 still decide Milestone 2.

## The desktop app

`CYNQRA_DESKTOP.md` at the project root: download the installer for Windows, macOS or Linux,
install it, open it. It runs this engine with an open-weight model on the laptop itself
(Qwen3.6 35B-A3B or Qwen3.5 9B, by memory) through llama.cpp's llama-server, which the app
bundles. `desktop.py` is its entry point; `cynqra/runtime.py` downloads, checks and serves the
model; `../desktop/` builds the installers. The guide bar at the bottom of the app explains each
step as it happens; Hide guide turns it off.

## Run it

Windows: double click RUN_POC.bat in the project folder.

Any machine with Python 3.10 or newer:

    python poc/run_poc.py

Then open http://127.0.0.1:8750 if the browser does not open by itself. No packages to
install. Data lives in poc/data. New run archives the old one; nothing is deleted.

## Two modes

Demo. The workers' words come from a prepared scenario; the first screen offers two. The
candidate tracker: an internal recruiting tool built by a CTO, a PM and two engineers. The
restaurant covers forecast: a 14-day forecast and prep plan built by nine workers (CEO, CTO,
PM, Data Scientist, backend and frontend engineers, designer, DevOps, QA). Every screen says
it is demo mode. The script stands in the run's model registry as its only model, so the
demo is staffed, routed and metered like a live run. The documents and code the workers hand
over are still written to disk, verified for real (tests, document rules, the forecast's
backtest), merged for real and deployed for real on your machine.

Live. Real models do the thinking. The run is staffed from the model registry (Models, on
the first screen); when the registry offers none, the model the environment names is
registered and used: set ANTHROPIC_API_KEY (default model claude-sonnet-5) or OPENAI_API_KEY
(default gpt-4o-mini) before starting, or CYNQRA_MODEL to pick another. A model that stops
answering is replaced by another that passes its regression check, or the founder decides.
Nothing is invented to fill the gap.

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
Every run's budget is in US dollars (5 by default; set it on the objective screen). A hosted
model is priced at its list price, a model on this machine at the machine time you state.

## What you will see, about five minutes in demo mode (candidate tracker)

1. Objective. Structure the sentence into seven fields. Two are marked inferred. Edit,
   set the dollar budget and any constraints, submit. Cynqra decomposes it into seven
   requirements and synthesizes the workforce: a CTO, a Project Manager and two engineers,
   each with the reason it is needed.
2. Workforce gate. Approve the organization, or reject it with feedback and Cynqra revises it.
3. Roadmap and budget gate. Three milestones, six tasks with owners, accountability,
   acceptance criteria and verification gates, and the budget in layers. Approve.
3. Work. Press Run. Engineer A's first attempt fails a test and goes back for rework.
   Engineer B raises a Blocker; the PM clears it without you. The CTO tries to email the
   recruiters; policy denies it without you.
4. Your inbox gets four cards: a product rule (MEDIUM), the merge (MEDIUM), the production
   deploy (HIGH) and delivery. Approve each.
5. Delivery. The product is live on a local URL, with the final report: artifacts, budget
   forecast against actual, every worker's scorecard and every intelligence change. Open it,
   add a candidate. Download the export bundle. Replay any task in Audit.

The restaurant forecast runs the same flow with nine workers and fourteen tasks: seven
documents checked against their types, a product rule on the prep margin, the Data
Scientist's first forecast rejected by the platform's backtest and reworked, and a deploy
proposed by DevOps.

Try also: the kill switch, a low budget cap (the breaker stops work at 100 percent),
editing the objective mid run (the run pauses for your reconfirmation), and rejecting a
card (the work goes back with your note).

## Test it

    cd poc/tests
    python -m unittest -v

The browser test runs when Node and Playwright are installed and is skipped otherwise.
For live mode through the UI with a real model, start `run_poc.py` with a key set, then
`node tests/e2e/live_walk.js http://127.0.0.1:8750 <screenshot dir> "<objective>"`.
TEST_REPORT.md holds the last full run and its coverage.

## Folder map

| Path | What it is |
| --- | --- |
| desktop.py | The desktop app: window, model runtime, server; --selftest, --check-model, --e2e |
| run_poc.py | Starts the server and opens the browser (demo mode, or live with an API key) |
| research/ | Which open model and runtime to use, and why (September 2026) |
| live_check.py | The real model test of the whole journey, with a spend cap and a written report |
| live_reports/ | Reports of real model runs, with what each one proves |
| cynqra/engine.py | The orchestrator: the run's state, the founder's gates, the step loop; implements the run contract |
| cynqra/run.py | The run contract: what every engine may ask of the run, and nothing more |
| cynqra/objective.py | Objective Intelligence: the objective structured and decomposed into requirements |
| cynqra/synthesis.py | Workforce Synthesizer: the organization the objective needs, and its gate |
| cynqra/roles.py | The catalog: roles, task types and their verifiers, document types |
| cynqra/router.py | Intelligence Router: a model for every worker, from measured evidence |
| cynqra/planner.py | Execution Planner: milestones, tasks, owners, accountability, verification gates |
| cynqra/budget.py, settings.py | Budget Engine: the dollar forecast in layers, the ledger, the breaker; the project's settings |
| cynqra/gateway.py | Every worker action: identity, policy, budget, target check, execute, sanitize, audit |
| cynqra/execution.py | Each task's lifecycle, Handoff to verified |
| cynqra/verifier.py | Verification Service: documents, tests, the forecast backtest, defect escapes |
| cynqra/testrunner.py | Test runner in a clean process, with a cleaned environment |
| cynqra/performance.py, replacement.py | Performance Engine and Replacement Engine: keep, reroute or replace |
| cynqra/delivery.py | Delivery, final report, replay, the organization graph, export |
| cynqra/registry.py, probe.py | The model registry, and the calibration work every model does |
| cynqra/policy.py | D-27 risk rubric and D-28 authority matrix as code |
| cynqra/protocol.py | Handoff, Blocker, Escalation, Approval as stamped, hashed objects |
| cynqra/db.py | SQLite store; events are append only, enforced by triggers |
| cynqra/deploy.py | BUILD to LIVE with health, smoke and rollback |
| cynqra/intelligence.py | Prompts and transport: the scripted source and the model source |
| cynqra/model_adapter.py | Byte for byte copy of 02_harness/spikes/model_adapter.py |
| cynqra/server.py | HTTP API and static UI |
| cynqra/runtime.py | The desktop app's model: catalog, verified download, llama-server start and GPU fallback |
| ui/ | The web app, vanilla HTML, CSS and JS, fonts bundled |
| scenarios/ | The demo scenarios and the real documents and code the workers hand over |
| design/ | High level screen mockups, copied from the design canvas |
| tests/ | Unit, journey, failure path, provider wire, API and browser tests |
| demo/ | The guided demo (record_replay.py, build_demo.py, guided/) and how the demo video is recorded |
| ui/tour.js | The plain words for each step, shared by the guide bar and the guided demo |

## Limits, stated plainly

No kernel isolation for worker code (a folder and a cleaned subprocess, not a container).
Single user. The deployment target is a local process. Rejecting delivery keeps the
product live and records the note; iterating on a delivered product is outside this POC.
