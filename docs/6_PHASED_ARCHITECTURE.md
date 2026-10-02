# CYNQRA phased architecture contract

Last updated: 1 October 2026 (objective intelligence control implemented).

This document is the authoritative implementation contract for the current CYNQRA product architecture. Files under
archive/ are historical records and must not silently override this contract.

## Product architecture

The architecture is outcome-first and objective-specific. CYNQRA does not select a universally "best" model and
then build around it. It receives the founder's objective, turns that objective into measurable requirements and
acceptance criteria, creates the work graph and workforce, evaluates available intelligence against the actual work,
binds the strongest evidenced intelligence to each worker/task, and continuously re-evaluates that choice from
verified execution results.

Founder objective
-> objective system
-> requirements, constraints, risks and acceptance criteria
-> work graph
-> workforce synthesis
-> cofounders
-> specialist workforce
-> intelligence supply and registry
-> objective-specific intelligence selection
-> worker binding
-> planner and scheduler
-> budget
-> governed execution
-> continuous review and verification
-> rework / replacement / rerouting
-> production verification
-> delivery
-> audit, learning and refinement

The organization is dynamic. Roles are generated from the confirmed objective and founder profile. There is no
fixed universal organization.

### Outcome and intelligence-selection contract

The unit CYNQRA optimizes is the verified objective outcome, not model prestige, benchmark rank, or a generic model
score.

For every material work item, CYNQRA maintains two evidence layers:

1. Global intelligence evidence: provider/version identity, capabilities, context, cost, latency, reliability and
   measured history across prior work.
2. Objective evidence: performance of that intelligence on the current objective, its role, task kind, acceptance
   criteria, tool environment, failures, rework, verification results, cost and time.

Global evidence is a prior. Objective evidence becomes more authoritative as the current run produces verified
results. A model is never considered "best" for an objective merely because it is popular, expensive, newer, or
strong on a generic benchmark.

Selection is therefore a closed loop:

discover -> qualify -> propose candidates -> objective-specific calibration -> bind -> execute -> verify -> measure
-> retain, reroute or replace -> re-verify.

The bounded hosted calibration runner is an intake mechanism for discovering and qualifying intelligence; it is not
the product's final model-ranking mechanism. Models not selected for a bounded calibration remain explicitly
untested, not failed. Provider outages remain provider failures, not intelligence failures.

### Objective work graph

The objective system produces an inspectable work graph. Each work item has, at minimum:

* objective and requirement references
* role/worker ownership
* task kind and dependencies
* acceptance criteria and verification method
* risk and budget constraints
* required capabilities/tools/context
* current intelligence binding
* execution state
* verification evidence
* rework history
* intelligence-selection evidence

The graph may branch, execute independent work in parallel, merge through governed integration points, and reopen
completed work when verification finds a defect. This makes the user's objective the stable control plane while
workers and intelligence remain replaceable.

### Quality control loop

A worker's output is never sufficient evidence of completion.

For material work:
* the worker produces an artifact;
* an independent verifier checks it against objective-specific acceptance criteria;
* failures become structured rework;
* repeated or diagnostic failures update intelligence evidence;
* CYNQRA decides whether to keep the binding, reroute the task, or replace the intelligence;
* replacement candidates must pass the applicable qualification/regression check before binding;
* the resulting artifact is re-verified;
* the objective is complete only when its acceptance criteria and production verification gates pass.

The user-facing system should expose this loop as progress: workforce formation, intelligence selection, task
assignment, execution, review, findings, rework, replacement/rerouting, verification and final production readiness.
The visibility is an explanation of the control plane, not a second manual workflow for the founder.

## Objective intelligence control: what is implemented

Status, 1 October 2026: **implemented and tested with deterministic test doubles; not yet proven on real models.**
The executable loop exists in code:

```
objective (objective_id, version, lifecycle) -> requirements + machine-readable acceptance criteria -> work graph
-> workforce -> candidate intelligence -> global qualification gate -> bounded objective calibration
-> SelectionDecision (persisted, immutable snapshot) -> worker / work binding (versioned) -> budget reservation
-> execution -> independent verification -> causal attribution -> objective evidence -> performance dimensions
-> exploration / exploitation -> reselection / reroute / replacement -> production verification -> delivery
-> immutable audit and replay
```

What the unit, contract and integration tests prove is the mechanics and the state transitions. They use test
doubles, so they prove nothing about any real model's quality; that needs real provider runs (see "Evidence rule").

### Boundary: the Objective Intelligence Controller

`poc/cynqra/controller.py` is the control plane's one boundary for choosing, binding, measuring and re-choosing
intelligence. Its inputs are the objective and its version, the requirements and acceptance criteria, the work
graph, the candidate intelligence (registry), global evidence, objective evidence, the policies and the run state
(bindings, budget, reservations). Its outputs are candidate sets, calibration plans, SelectionDecisions, bindings,
evidence updates, reselection decisions and the ranking the Replacement Engine works from. The other engines call
it; none of them decides on its own which intelligence does a piece of work.

| Module | Role in the loop |
| --- | --- |
| `cynqra/policies.py` | Every rule the control plane decides by, versioned and discoverable in one place: system, authority (`policy.py`), objective, inheritance, selection, evidence, risk, budget, verification, calibration, replacement, isolation, retention. A decision stores the full bodies of the policies it used. |
| `cynqra/objective.py` | `objective_id` and `objective_version`; the lifecycle state machine (`TRANSITIONS`, `transition`, refused moves recorded); version records with statement, field, requirement and acceptance hashes; `classify_change` and `inheritance_map` (full, prior only, none); `acceptance_criteria` and `task_acceptance` (machine-readable criteria); `acceptance_hash` (the frozen bar); `constraint_model` (hard constraints, mandatory requirements, optimization dimensions, preferences, risk thresholds and acceptance criteria kept apart, stored with the requirements); a cancelled objective records its work in flight as cancelled (`controller.cancel_open_attempts`), never failed. |
| `cynqra/planner.py` | Work items carry objective identity and version, acceptance criteria with verification methods, the frozen acceptance hash and their work class; the work graph is content-addressed and announced (`workgraph.created`). |
| `cynqra/objective_evidence.py` | Persisted objective evidence: immutable content-addressed bodies, an index with lifecycle (active, archived, invalidated, redacted), idempotent recording, an evidence version advanced atomically, tenant/workspace/objective-scoped queries, redaction and archival that keep hashes and causal links, and a refusal of any record that carries content or credentials. |
| `cynqra/attribution.py` | Failure attribution: provider, account, network, tool, environment, specification, verification, execution, cancelled, human, intelligence. Only intelligence failures update quality; the rest is recorded as contaminated. `diagnose` moved here from `replacement.py` (still re-exported there). |
| `cynqra/intelligence_layer/evidence.py` | The evidence model, pure: levels (objective verified, objective partial, historical, global; capability metadata and reputation never measure quality), per-item weight from relevance (the same work item, class, requirement or acceptance criteria, kind for another role, closest kind), verification quality, recency, environment and author conflict; tenant and workspace isolation by the isolation policy (objective evidence never crosses a workspace; other work only where the policy shares it; qualification is global); caps on the lower levels; a Beta posterior with mean, an 80% band and effective sample size; maturity (none, thin, developing, mature); evidence strength components; exclusions with reasons; `superior` (verified superiority). |
| `cynqra/intelligence_layer/router.py` | `hard_constraints` and `select`: a pure function of a decision snapshot. Hard constraints first (qualified for this family of work, available, context, output limit, modality, the capabilities the work item needs, where only a provider's stated inability excludes and unknown is never unable, protocol fit from evidence, the founder's local-only constraint); the budget cap and evidence scope are enforced elsewhere (reservations and the breaker; the isolation policy), and the policy says so; then evidence per kind of work; then the risk tier's trade-off (quality first for HIGH, the lowest expected cost of a verified result among candidates that clear a quality floor for MEDIUM and LOW); then exploitation, bounded exploration, or keeping the incumbent. The legacy `estimate/rank/choose/staff` remain as the economics and forecast model. |
| `cynqra/intelligence_layer/candidates.py` | Bounded candidate sets for qualification and calibration: provider-fair, family-diverse, newest of each family, metadata priority only, never quality. Used by `run_hosted_examination.py` and calibration. |
| `cynqra/calibration.py` | Cold-start objective calibration on representative work items taken from the objective's own plan (code, forecasts, documents: what the platform can verify before the work is real), bounded candidates, upper-bound budget, stopping policy (never settling on a best candidate whose verified work has not covered the item's acceptance criteria), task coverage on the plan (every class of open work: calibrated, skipped with its reason, not verifiable before it is real, or beyond the class limit), frozen content-addressed items checked before each verdict, platform-owned verdicts, author-conflict marking. |
| `cynqra/binding.py` | Worker bindings and work (task) bindings, both versioned with compare-and-set and a global sequence; the newest decision wins (`effective`). Every binding names its decision; a binding made by another engine's rule (a stand-in, a version pin, a return after an outage) still gets a persisted decision (`controller.record_direct`). |
| `cynqra/budget.py` | Reservations: every model call during governed execution reserves its upper-bound cost before it starts; a call that would take spent plus reserved past the cap does not start. Ledger writes are transactional. |
| `cynqra/db.py` | `Store.atomic()` (one transaction, `BEGIN IMMEDIATE`), `compare_and_put` (optimistic concurrency), `next_seq` / `next_id` (ids never handed out twice), per-aggregate event versions. |
| `cynqra/verifier.py`, `execution.py`, `replacement.py`, `engine.py`, `delivery.py` | Integration: verification records name the producing intelligence and carry a record hash; acceptance integrity is checked first; verification, reviews, founder verdicts, protocol violations, refused tool requests, cancellations, Blockers, provider failures and defect escapes become objective evidence; reviews of HIGH-tier work go to an intelligence other than the producer's; replacement and rerouting rank through the controller and replace a working incumbent only on verified superiority; production verification gates completion. |

### SelectionDecision

A persisted record (`selection_decision`) with: `decision_id`, `objective_id`, `objective_version`,
`work_item_id`, `worker_id`, `candidate_set`, `eligible_candidates`, `excluded_candidates` (each with its violated
constraint), `hard_constraints`, `selection_policy_version` and every policy version, `evidence_snapshot` (the
content hash of the immutable snapshot of every input: work item, candidate facts, evidence records, budget state,
exploration state, policy bodies, the time), `evidence_version`, `evidence_ids`, `selected_intelligence` (id, name,
served version), `selection_mode` (exploit, explore, keep_incumbent, reselect, single_candidate, replacement,
directed, no_feasible_candidate), `selection_reason`, `ranking` (per candidate: mean, band, maturity, decisive
level, expected cost and minutes), `expected_cost`, `expected_latency_minutes`, `risk_state`, `budget_state`,
`decision_timestamp`, `binding_version`, `status` (proposed, committed, superseded_before_commit,
lost_binding_race, kept, no_selection) and `result_hash`. `controller.replay` reproduces a decision from its
snapshot alone; `controller.explain` builds a task's causal audit from persisted records.

### Events

From real persisted state transitions only: `objective.created`, `objective.state_changed`,
`objective.version_created`, `objective.transition_refused`, `requirements.created`, `workgraph.created`,
`workforce.created`, `intelligence.discovered`, `intelligence.candidate_set.created`,
`intelligence.calibration.started`, `intelligence.calibration.completed`, `intelligence.selection.proposed`,
`intelligence.selection.committed`, `worker.bound`, `task.started`, `review.started`, `verification.completed`,
`rework.created`, `intelligence.evidence.updated`, `intelligence.reselection.triggered`, `intelligence.rerouted`,
`acceptance.integrity_violation`, `budget.reservation_refused`, `production.verification.started`,
`production.verification.completed`, `objective.completed`. Events carry `event_id`, `correlation_id`,
`causation_id` (the triggering event where known), `aggregate_version` (the aggregate's own sequence for the
intelligence aggregates), an idempotency key (evidence events are keyed by their evidence record) and a hash chain.

### Implemented, target and future

| | What |
| --- | --- |
| Implemented | Everything in the tables above, exercised by `poc/tests/test_objective_intelligence.py` (pure evidence and selection rules, store-level isolation, idempotency, immutability, concurrency and reservations, the demo lifecycle and causal audit, adversarial guards, and a closed-loop live run on differentiated test doubles: calibration separates a model that writes broken code, a model that breaks after calibration is replaced on evidence and the next task of that kind is reselected while the worker keeps its seat, every decision replays). |
| Target (needs real runs) | That the evidence and calibration choose better intelligence than the global prior on real objectives; the thresholds, weights, caps and floors in `policies.py` are first settings, to be tuned only from real evidence. |
| Future | Calibration of work the platform cannot verify before it is real (proposals, merges, releases) beyond the global prior; a privacy-preserving cross-tenant aggregation policy (cross-tenant evidence is denied in this build); a hosted multi-tenant control plane (tenants are enforced per record today, on one machine's store); OS/container isolation for generated code (unchanged, see P3). |

### Answers the mandate asks for, from the code

* **"Build a location tracking application", five qualified models, no evidence: who does the first important
  tasks?** The planner's work items are classified by kind and owning role; `calibration.plan` takes the first
  machine-verifiable item of each important class, picks at most three feasible candidates per class
  (qualified for that family of work, available, inside the hard constraints; provider-fair and family-diverse,
  the strongest prior first) within 10% of the cap, freezes each item, runs it on each candidate and has the
  platform's verifier judge it. The results are objective calibration evidence; `controller.bind_tasks` then
  decides every work item from them (`router.select`), keeping the worker's incumbent unless a candidate is
  verifiably superior.
* **Model A fails two backend acceptance tests, Model B succeeds: where is that stored?** In the run's
  `intel_evidence` records (immutable bodies in `objects`), keyed to the objective, version, work item, attempt,
  intelligence and served version, with the verification record's id and hash; clean outcomes are also written to
  the registry's tenant-scoped `outcome` history for other objectives.
* **How does the router consume it?** `controller.snapshot` gathers the candidates' objective evidence and the
  tenant's registry history; `evidence.assess` weights them by level, relevance and verification quality;
  `router.select` orders feasible candidates by the tier's policy. New evidence triggers `controller.after_evidence`
  for future work of that kind, and `revalidate` when a task starts.
* **Objective A excellent, Objective B poor: no contamination?** Objective evidence is queried by objective id,
  tenant and workspace; another objective's evidence is never objective evidence, only capped historical evidence from the
  registry of the same tenant, ranked below everything B produces about itself.
* **HTTP 503 (or 408, 409, 425, 429, a timeout, a dropped connection)?** The adapter waits and retries it;
  `attribution.call_failure` says provider (or network); the evidence record is contaminated (`clean: false`), no
  registry outcome is written, the quality posterior is unchanged (`test_a_provider_outage_is_not_an_intelligence_failure`).
* **A model version changes?** Evidence carries the served version (version and serving company); another
  version's evidence is excluded (`version_mismatch`); the gateway's version pin forces a regression check before a
  bound worker continues; registry stats keep serving companies apart.
* **Ten workers concurrently?** Each call reserves its upper-bound cost atomically; spent plus reserved never
  passes the cap; a refused reservation waits for in-flight work or opens the breaker for the founder.
* **Intelligence changes under a worker?** Worker identity is separate; bindings keep their history; a
  replacement brings a new person into the seat (P18) and the task binding's history keeps the old intelligence.
* **Why was this intelligence selected, and why did it change?** `engine.explain(task)` and the persisted
  SelectionDecisions (selection, reselection, replacement), each with its snapshot, policy versions and reason.
* **Lifecycle and versions?** `objective.TRANSITIONS`; a material change (`classify_change`) creates a new version,
  the previous one is superseded, and `inheritance_map` decides what its evidence is worth (none, prior only, full).
* **Tiny samples, staleness, exploration, calibration stopping and integrity, hard constraints versus preferences,
  trade-offs, tool use, retries, cancellations, duplicates, races, tenants, replay, policy versions, the boundary,
  adversarial tests:** `policies.EVIDENCE` (caps, maturity, half-life, environment factor),
  `policies.SELECTION` (tiers, exploration bounds, superiority), `calibration._stop`, `calibration._trial`
  (spec hash), `router.hard_constraints`, `execution.work` (tool-use counts, `attribution.tool_failure`),
  `controller.attempt_kind` and `autonomy_of`, `objective_evidence.record` (idempotency), `controller.commit`
  (evidence-version check, binding compare-and-set), `objective_evidence.query` (tenant scope), `controller.replay`,
  `selection_policy_version` on every decision, `controller.py`, and `test_objective_intelligence.GuardTests`.

### Audit against the mandate, 2 Oct

A section-by-section audit of the mandate against the code found these gaps, now closed, each with a test in
`poc/tests/test_mandate_audit.py`: HTTP 425 and dropped connections were not retried (16); verification and call
records named their objective version only through their task, which a new version relabels (5); a work item's
declared capability needs were not a hard constraint (46); calibration's acceptance coverage and task coverage were
described but not computed (41); a cancelled objective left its work in flight unclassified (49); a founder-directed
stand-in was not recorded as a human-directed reroute (50); workspace isolation of historical evidence did not follow
the isolation policy (53); the rework and cut-off limits were module constants beside their policies (57); relevance
ignored shared requirements and acceptance criteria (13); hard constraints, requirements, dimensions, preferences and
thresholds had no explicit model (44). The policy's hard-constraint list also named two rules the router does not
enforce as exclusions (the budget cap, evidence scope); it now lists them as enforced elsewhere.

Unchanged and stated plainly: a task has no wall-clock time limit; it ends by its rework limit, the Replacement
Engine, its budget, the breaker or the kill switch, and every model call has a timeout. No product action lets a
person override a verdict, so `human_override` is defined (and excluded as evidence) but never produced.

## Identity contract

A worker is an organizational seat plus a persistent worker identity. Intelligence is a separate binding.

Worker != intelligence != provider connection != credential.

Changing intelligence does not change the worker's historical record. A replacement event may create a new
human-facing person identity for the same seat when product policy requires visible replacement. The previous
person remains in history. A provider outage alone does not trigger replacement.

## Eight implementation phases

### P0: architecture and canon reconciliation
Exit gate:
* one authoritative current architecture
* historical fixed-organization language is explicitly marked historical
* worker/intelligence/provider/credential separation is explicit
* replacement identity semantics are explicit

### P1: intelligence qualification
Exit gate:
* real provider adapters can register intelligence
* version and serving-provider are pinned
* unverified intelligence cannot be assigned
* qualification, calls, outcomes, cost and regression evidence are persisted

### P2: dynamic workforce proof
Exit gate:
* multiple unrelated objectives synthesize different organizations
* founder capabilities remove corresponding cofounder seats
* requirements have owners
* uncovered capabilities are closed from the role catalog
* workforce validation is deterministic after model proposal

### P3: isolated worker runtime
Exit gate:
* workers can inspect/search/read/write/delete files in a scoped workspace
* workers can execute approved commands with timeout and output limits
* dependency installation, build and test are represented as governed tools
* credentials are never inherited broadly
* network, filesystem, process, budget and kill-switch controls are enforced

### P4: blank-repository build
Exit gate:
* an empty repository can be handed to CYNQRA
* no prepared application is required
* the workforce can plan, implement, test and deliver a working application

### P5: autonomous multi-worker coordination
Exit gate:
* workers coordinate through structured protocol objects
* humans do not assign individual implementation tasks
* parallel work is supported
* integration conflicts are detected and resolved through governed workflows

### P6: verification and recovery
Exit gate:
* verification is independent of the worker claiming completion
* failed work is returned for repair
* intelligence failures are diagnosed
* replacement/rerouting preserves work and history
* provider outages do not cause unnecessary replacement

### P7: economics and observability
Exit gate:
* model, provider, tool, compute, verification and rework cost are measured
* latency and throughput are measured
* human interventions are measured separately
* every delivered result has an evidence trail

### P8: examination set
Exit gate:
* one full vertical slice passes
* three unrelated objectives pass
* ten-objective examination run is reproducible
* twenty-objective examination run can be executed without changing product logic
* results are stored as evidence, not represented as claims

## Evidence rule

A unit test using a fake provider proves deterministic platform behaviour only.
A prepared demo proves the scripted/demo path only.
A real-model run proves only the objective, provider, model, environment and run that actually executed.
A phase is not marked empirically proven merely because its unit tests pass.
