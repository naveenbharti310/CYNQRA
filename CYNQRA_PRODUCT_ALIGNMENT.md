# Cynqra's code against the product definition

27 September 2026. The founder made **Cynqra Product Flows and Architecture v1** the core document: everything
in the Cynqra build follows it. This file records what the code omitted (the document requires it, the code
did not have it) and what it committed (the code did something the document rules out), what was changed for
each, and where. Everything below is in `poc/` and covered by tests (`poc/tests/test_product_flow.py`,
`test_journey.py`, `test_workforce.py`, and the rest of the suite: 213 tests).

A second pass the same day rebuilt the core instead of patching it: the orchestrator was split into engines behind
an explicit run contract, every run is staffed through the registry (the demo too), US dollars became the only
budget, task types and their verifiers moved into the role catalog, and a second demo scenario runs a nine-worker
organization. The section "The rebuild" below says what changed and why.

The canon still says otherwise in places (D-2: "no dynamic org synthesis"; D-28: three roles; Book 4: M3 is the
fixed org). The product definition supersedes them for the build by the founder's instruction; that should be
written into the canon as a decision (a D-37), which is the founder's to record.

## Commissions: what the code did that the document rules out

| # | The code did | The document says | Now |
| --- | --- | --- | --- |
| C1 | A fixed four-worker organization (`TEMPLATE`, `REPORTS_TO` in `engine.py`) was the product | Section 2: the fixed organization is a test fixture, not the product; the organization is synthesized from the objective | Removed from the product code. The catalog (`cynqra/roles.py`) holds eleven roles; the fixed four exist only as a test fixture (`tests/helpers.M1_ROLES`) |
| C2 | The founder had to confirm a structured objective, and every field had to be filled | Stages 0 and 1: the human gives the outcome, budget and constraints; Cynqra decomposes it. The gates are the workforce and the roadmap | `submit_objective` hands it over; a field the brief leaves out is recorded as "not stated in the brief" and does not block. No `confirm_objective` decision exists any more |
| C3 | One decision approved "the organization and the plan" together | Stage 3 and Stage 6 are separate gates: the workforce first, then the roadmap and budget | Two decisions: `approve_workforce`, then `approve_roadmap` |
| C4 | Worker ids were literals in the engine and the prompts (`w_pm` assigns, `w_cto` reviews, Blockers go to `w_pm`) | Roles and reporting lines are generated per project | Resolved from the organization: `roles.assigner`, `roles.answerers`, `roles.owners_of`; prompts get the worker's persona from the catalog |
| C5 | The authority matrix had three hand-written rows | Authority belongs to the role | `policy.MATRIX = roles.matrix()`: one row per catalog role; the M1 rows are unchanged |
| C6 | Budget was work units; the dollar budget was a side ledger | Stage 7: a monetary budget in layers, reconciled against actuals; the budget breaker ends the budget flow | US dollars are the only budget. The Budget Engine (`cynqra/budget.py`) builds the forecast in layers, charges every dollar to a worker, a task and a layer, and opens the breaker on dollars. Work units are gone |
| C7 | A worker's model was replaced only after three failed verifications, with no check of the successor | Stage 10: replacement follows evidence against thresholds, and the new intelligence passes a regression check before it continues | The Performance Engine's thresholds trigger an evaluation early; the Replacement Engine decides keep, reroute or replace and runs a regression check first |
| C8 | Planning, synthesis, routing, budget, performance and replacement were one engine | Section 5: six separate engines | One module per engine (see "The rebuild"); `engine.py` only orchestrates and implements the run contract |

## Omissions: what the document requires that the code did not have

| # | Document | Now in the code |
| --- | --- | --- |
| O1 | Stage 0: project name, objective, budget and constraints (deadline, geography, technology, compliance, risk tolerance) | `set_guardrails(constraints=...)`; the UI's objective card; constraints go into every worker's prompt |
| O2 | Stage 1: requirements by area (product, functional, non-functional, AI/ML, data, design, security, QA, DevOps, deployment), workstreams, dependencies and critical path, verification requirements | `intelligence.decompose` → `validate_requirements` (platform ids, areas, workstreams, cycle check, critical path computed) → `requirements` record |
| O3 | Stage 2: dynamic workforce synthesis with the reason for every role | `intelligence.synthesize` → `validate_workforce`: roles from the catalog within their limits, every requirement covered by a role whose areas include it, the roles the pipeline cannot run without; reporting lines generated from who is present (section 3's twelve-worker restaurant organization reproduces the org chart exactly, test) |
| O4 | Stage 3: approve, reject (Cynqra revises against the feedback), edit only if governance allows; every choice audited | `approve_workforce`; reject → a new proposal version with the note; edit → `synthesis.override` only when `allow_workforce_override` is set, validated like a proposal, labelled `approved_edited` and a `workforce.overridden` event |
| O5 | Stage 4: intelligence per worker, many-to-many, workload-specific | Staffing after the workforce gate over the role's kinds of work, refined after planning to the kinds of the tasks each worker owns; capability fit from the model's facts; "models in use" shows one model powering several workers |
| O6 | Stage 5: milestones, tasks with acceptance criteria, the best-positioned owner, dependencies, reporting and accountability, handoffs and coordination, escalation conditions, verification gates, workload estimates | Plan schema with milestones, acceptance criteria and requirement ids; `planner.enrich` adds accountability, the Handoff route, Blocker routes, verification gates, escalation conditions and the critical path; the Budget Engine adds per-task tokens, minutes and money |
| O7 | Stage 7: layers (workforce allocation, model inference, tools, infrastructure, verification, reserve, total) against the hard cap; forecast versus actual | `budget.construct` and `budget.actual`; views by worker, workstream and milestone; warnings when over the cap or under the minimum reserve |
| O8 | Stage 8: output sanitized | The gateway refuses a write that holds a credential (private keys and common API key formats) |
| O9 | Stage 9: first-pass success, rework, defect escape, false acceptance and rejection, verification latency and cost | Verification records the worker, model, seconds and a hash of the work; a later pass on identical work marks the earlier failure a false rejection; a failure in the release candidate, on main or live is recorded as a defect escape against the verified task and model it came from; metrics report all of them |
| O10 | Stage 10: signals (quality, reliability, efficiency, economics, capability fit, stability, human friction), thresholds, keep / reroute / replace, regression check | `performance.scorecard` per worker and per (worker, model); `performance.below`; `replacement.evaluate` with task rerouting to a peer of the same role as well as model replacement; `probe.regression_check` |
| O11 | Section 4: registry facts (modalities, tool calling and MCP, context, benchmark results, verified history, latency, cost, hardware, licence and commercial use, fallback and regression status) | Registry fields added; `profile` reports the role/workload benchmark (probe and regression work) and the record per model version |
| O12 | Section 7: model regression gate | A new model or a new version is "unverified" until its calibration work passes; a failed check makes it unavailable to the router |
| O13 | Section 8, step 14: the final screen | `engine.final_report()`: delivered artifacts, budget forecast against actual by layer and by worker, every worker's scorecard on every model, every intelligence change; shown in the Delivery view |

## What is still short of the document, said plainly

- **The demonstration of section 8 on real models** has not produced a result yet. The first `[workforce]` run
  (27 September) stopped before it started: `workforce_demo.py` was not packaged into the app. Fixed, with a test
  that every module `desktop.py` imports is packaged, and the whole demonstration now runs in the suite against
  the llama-server test double. A real run needs the next `[workforce]` push.
- **Design work is verified as a document** (its sections and the requirements it cites), not by looking at
  screens; there is no visual review.
- **Independent review** is still the founder for MEDIUM and HIGH work; there is no second-model reviewer.
- **Workers answer in structured text**, not native tool calls; the gateway is the same either way.
- **Evidence is shared across projects** in the registry; tenant scoping (D-7) is not built.

## The rebuild

The first pass added what the document asked for around the old engine. The founder asked for the core to be
rebuilt rather than patched, and audited from scratch. What changed:

**The orchestrator and the engines.** `engine.py` holds the run's state, the founder's gates and the step loop,
and nothing else. Every stage is an engine module that sees the run only through the run contract
(`cynqra/run.py`, a Protocol: the audit trail, the inbox, the objective, the organization, the tasks, the
gateway, money and intelligence):

| Engine | Module | Stage |
| --- | --- | --- |
| Objective Intelligence | `objective.py` | 0, 1 |
| Workforce Synthesizer | `synthesis.py` | 2, 3 |
| Intelligence Router | `router.py` | 4 |
| Execution Planner | `planner.py` | 5 |
| Budget Engine | `budget.py`, `settings.py` | 6, 7 |
| Gateway | `gateway.py` | 8 |
| Execution | `execution.py` | 8 |
| Verification Service | `verifier.py` (and `testrunner.py`, the clean test process) | 9 |
| Performance Engine | `performance.py` | 10 |
| Replacement Engine | `replacement.py` | 10 |
| Delivery | `delivery.py` | final report, replay, graph, export |

Engines never import the orchestrator. The model proposes and the engine checks: every answer passes a
validator in the engine that owns it (`validate_requirements`, `validate_workforce`, `validate_plan`, the
protocol builder), and `intelligence.ask` gives the model one retry with the reason before the step stops.

**One intelligence path.** WORKER is not MODEL in every run. A live run is staffed from the app's registry, or
from the model the environment names, which is registered as the `environment` model and priced at its list
price. A demo run stands its scripted source in a registry of its own as the `scripted` model, so the demo is
staffed, routed, metered and scored exactly as a live run is. `intelligence.py` holds only prompts and transport.

**Dollars only.** The project's settings (`settings.py`) hold the budget in US dollars, the value of an hour,
the price of this machine's time and the governance switches. Inference is priced per token, or per second on
this machine; the workers' own test runs and the Verification Service are priced as machine time; the forecast
prices every layer the same way. `live_check.py`'s spend cap is the Budget Engine's breaker.

**Task types and verifiers in the catalog.** `roles.TASK_TYPES` names what a task can be, its risk and its
verifier: document, decision, code, forecast, review_merge, deploy. `roles.DOC_TYPES` names the documents
(business brief, product specification, acceptance checks, design, architecture, method, test plan, runbook)
and the rules their verifier checks. Each role says which task types it owns and which documents it writes. A
forecast is verified by its tests and then by the platform's own backtest against a seasonal baseline.

**Two demos.** The candidate tracker (CTO, PM, two engineers: six tasks, one rework, one Blocker) and the
restaurant covers forecast (CEO, CTO, PM, Data Scientist, Backend, Frontend, Designer, DevOps, QA: fourteen
tasks, seven documents, a forecast whose first method fails the backtest and is reworked, a deploy proposed by
DevOps). Both pass the same validators a model's answers do.

**Audit findings fixed in the pass.** `ModelSource.structure_objective` had been generated with the scripted
source's body (live mode could not structure an objective); a refused cap raise consumed the breaker's
decision and left the founder nothing to answer; a reopened live run whose model was gone stopped the app from
starting; the desktop app's model check duplicated the registry's probe (now one probe, whose results also
become the model's first measured record); `live_check.py` kept its own price table and spend counter beside
the engine's ledger.

