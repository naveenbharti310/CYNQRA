# CYNQRA phased architecture contract

Last updated: 1 October 2026.

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
