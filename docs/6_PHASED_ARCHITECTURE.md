# CYNQRA phased architecture contract

Last updated: 1 October 2026.

This document is the authoritative implementation contract for the current CYNQRA product architecture. Files under
archive/ are historical records and must not silently override this contract.

## Product architecture

Founder objective
-> objective system
-> requirements and risks
-> workforce synthesis
-> cofounders
-> specialist workforce
-> intelligence registry
-> measured intelligence selection
-> worker binding
-> planner
-> budget
-> governed execution
-> verification
-> performance
-> replacement or rerouting
-> delivery
-> audit and refinement

The organization is dynamic. Roles are generated from the confirmed objective and founder profile. There is no
fixed universal organization.

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
