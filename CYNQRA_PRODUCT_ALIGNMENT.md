# Cynqra's code against the product definition

27 September 2026. The founder made **Cynqra Product Flows and Architecture v1** the core document: everything
in the Cynqra build follows it. This file records what the code omitted (the document requires it, the code
did not have it) and what it committed (the code did something the document rules out), what was changed for
each, and where. Everything below is in `poc/` and covered by tests (`poc/tests/test_product_flow.py`,
`test_journey.py`, `test_workforce.py`, and the rest of the suite: 195 tests).

The canon still says otherwise in places (D-2: "no dynamic org synthesis"; D-28: three roles; Book 4: M3 is the
fixed org). The product definition supersedes them for the build by the founder's instruction; that should be
written into the canon as a decision (a D-37), which is the founder's to record.

## Commissions: what the code did that the document rules out

| # | The code did | The document says | Now |
| --- | --- | --- | --- |
| C1 | A fixed four-worker organization (`TEMPLATE`, `REPORTS_TO` in `engine.py`) was the product | Section 2: the fixed organization is a test fixture, not the product; the organization is synthesized from the objective | Removed from the engine. The catalog (`cynqra/roles.py`) holds eleven roles; the fixed four are `roles.FIXTURE_M1`, a fixture |
| C2 | The founder had to confirm a structured objective, and every field had to be filled | Stages 0 and 1: the human gives the outcome, budget and constraints; Cynqra decomposes it. The gates are the workforce and the roadmap | `submit_objective` hands it over; a field the brief leaves out is recorded as "not stated in the brief" and does not block. No `confirm_objective` decision exists any more |
| C3 | One decision approved "the organization and the plan" together | Stage 3 and Stage 6 are separate gates: the workforce first, then the roadmap and budget | Two decisions: `approve_workforce`, then `approve_roadmap` |
| C4 | Worker ids were literals in the engine and the prompts (`w_pm` assigns, `w_cto` reviews, Blockers go to `w_pm`) | Roles and reporting lines are generated per project | Resolved from the organization: `roles.assigner`, `roles.answerers`, `roles.owners_of`; prompts get the worker's persona from the catalog |
| C5 | The authority matrix had three hand-written rows | Authority belongs to the role | `policy.MATRIX = roles.matrix()`: one row per catalog role; the M1 rows are unchanged |
| C6 | Budget was work units; the dollar budget was a side ledger | Stage 7: a monetary budget in layers, reconciled against actuals; the budget breaker ends the budget flow | The Budget Engine (`cynqra/budget.py`) builds the forecast in layers; in a run staffed from the registry the dollar cap is the hard stop (the breaker opens on dollars); work units remain a safety cap |
| C7 | A worker's model was replaced only after three failed verifications, with no check of the successor | Stage 10: replacement follows evidence against thresholds, and the new intelligence passes a regression check before it continues | The Performance Engine's thresholds trigger an evaluation early; the Replacement Engine decides keep, reroute or replace and runs a regression check first |
| C8 | Planning, synthesis, routing, budget, performance and replacement were one engine | Section 5: six separate engines | Six modules: `synthesis.py`, `workforce.py` (router), `planner.py`, `budget.py`, `performance.py`, `replacement.py`; `engine.py` orchestrates |

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
- **The scripted demo** still builds the candidate tracker with CTO, Project Manager and two engineers. That is
  now what the synthesizer proposes for that objective, validated like any proposal; a restaurant forecasting
  run needs a live model.
- **Roles other than engineering deliver documents or code.** A Data Scientist's forecast is verified by its
  tests; there is no platform-owned backtest yet, and design work is verified by the document lint.
- **Independent review** is still the founder for MEDIUM and HIGH work; there is no second-model reviewer.
- **Workers answer in structured text**, not native tool calls; the gateway is the same either way.
- **Evidence is shared across projects** in the registry; tenant scoping (D-7) is not built.
