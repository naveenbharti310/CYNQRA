# Cynqra: the product against the code

> **Update, 27 September 2026.** The founder made the product definition the core document for the build. Its
> changes (section 9) are now implemented; what was built, stage by stage, is in CYNQRA_PRODUCT_ALIGNMENT.md.
> This review stays as the record of the analysis and the risks it names.

27 September 2026. A review of the Cynqra POC (branch `cynqra`) against the product definition of the same day:
an AI workforce operating system that turns an objective into requirements, synthesizes the workforce, assigns
intelligence to each worker, budgets it, governs its execution, measures it and replaces its intelligence while
the worker's identity, accountability and history persist.

The code is the source of truth for what exists. The canon (`00_canon/`) is the source of truth for what was
decided. Where they and the product definition disagree, this document says so.

---

## 0. The first contradiction: the canon decided against this, on purpose

The fixed four-worker organization is not an accident of the POC. It is decided:

- **D-2** (16 Aug, CPO): "The MVP is a fixed org template delivering a deployed web app. **No dynamic org
  synthesis.**"
- **D-28**: the authority matrix exists for exactly three roles (Engineer, PM, CTO).
- **Book 4 milestones**: M2 is *one* worker fully trusted; M3 is *the fixed org*. Dynamic synthesis is not on
  the 90-day ladder at all.
- **D-6**: the first product category is CRUD web apps, *because they have the richest automated verification*.
- **D-36**: the POC is a demonstration and "is never quoted as evidence for S1, S2, S3 or any gate".

The product definition in front of me supersedes D-2 and moves dynamic synthesis from "later" to "the next
POC". That may well be right, but it is a founder decision that must be written (a D-37 superseding D-2 for
the POC, or for the product), not something to drift into through code. The reasons D-2 existed are still
real and are the main risks below: coordination cost grows with the organization (S2 is unscored), and
verification is the make-or-break system (D-4) and is only strong for software.

**Recommendation:** keep D-2's *discipline* while dropping its *restriction*: dynamic synthesis from a
governed role catalog, with every role required to have an automated verification contract before it can be
synthesized. That keeps the thesis honest.

---

## 1. What already aligns

| Product principle | In the code | Where |
| --- | --- | --- |
| Worker identity is separate from intelligence | Worker record has id, role, reporting line, authority policy, performance profile; `model_id` is an assignment that can change | `engine.worker`, `_staff`, `_replace_or_escalate` |
| Model proposes, Cynqra executes | Every file write, test run, merge and deploy goes through `gateway()`: identity, policy, budget, target validation, execute, sanitize, audit | `engine.gateway`, `policy.evaluate` |
| Default deny; prohibited actions | Unknown action types and roles are denied; external messages, money, legal, objective/budget/authority changes are prohibited for every worker | `policy.py` |
| Human approval of high-risk actions | MEDIUM goes to the founder (D-17), every deploy (D-21), plan approval, delivery acceptance | `_decision`, `decide` |
| "The AI says it is done" ≠ "it is done" | Worker claims go to REVIEW; the Verification Service reruns every test in a clean copy, checks the delivery contract; deploy has health and smoke checks and rollback | `_verify`, `deploy.py` |
| Structured coordination, no free chat | Handoff, Blocker, Approval, Escalation protocol objects, hashed, in an append-only event log | `protocol.py`, `db.py` |
| Intelligence Registry | Models as facts (runtime, provider, price, context, licence, hardware), availability, faults | `registry.py` |
| Intelligence assignment by evidence | Expected money and time per verified task, from measured outcomes per task kind, within budget; full table kept | `workforce.py` |
| Performance measurement feeding decisions | Every call metered; every verification an outcome per model and kind; outcomes change the next selection | `registry.record_*`, `workforce.estimate` |
| Intelligence replacement preserving identity | After 3 failed verifications, 4 overflowing replies, or a model that stops answering: another model takes the worker, inherits task, files, failures; budget moves | `engine._replace_or_escalate` |
| Budget in money | USD budget, per-task allocation, reserve, per-worker ledger, reallocation on replacement | `workforce.Workforce` |
| Multiple models, many workers on one model | Routes per call; several workers can share a model; local, Hugging Face, OpenAI-compatible | `model_adapter` routes |
| Accountability and replay | Event log, decisions with labels, export bundle, task replay | `engine.replay/export` |

---

## 2. Partially implemented

| Capability | What exists | What is missing |
| --- | --- | --- |
| Objective understanding (Step 1) | Messy sentence → seven fields (product, customer, outcomes, success criteria, constraints, priorities), inferred fields flagged, founder confirms | No requirement decomposition: no product/technical/data/ML/UX/infra/security/QA/deploy requirements, no workstreams, complexity or effort. The plan call jumps from seven fields straight to tasks |
| Roadmap (Step 6) | Plan: workstreams, 5–7 tasks, dependencies, owners, risk tiers set by the platform | No milestones, no sequencing beyond dependencies, no durations, no review/verification ownership per workstream, no escalation paths beyond "the founder" |
| Human approval gates (Steps 5, 7) | One gate: "organization and plan" together | The product needs two: workforce (with economics) and then organization + roadmap |
| Economics (Step 8) | Per-task allocation from expected cost; reserve; ledger | No breakdown by worker × model × tokens × tools × infrastructure × verification × deployment; no forecast vs actual over time; work units still the hard stop |
| Execution (Step 9) | Write files, run tests, merge, deploy, raise Blockers, answer them, propose decisions | No research, no web, no browsing, no package install, no real tool-calling loop (workers reply in structured text that the engine turns into actions); code runs in a folder with a cleaned environment, **not a sandbox** (the M2 exit criterion) |
| Evaluation before replacement (Step 11) | Candidates scored on measured outcomes | No regression run of the candidate before the swap (ADR-4 requires one for a model change); no shadow evaluation |
| Performance measurement (Step 10) | First pass, verified, attempts, cost, time, errors per model and kind | No defect escape measure (a bug found after "verified"), no quality measure beyond tests, no human-intervention attribution per worker, no task difficulty normalization |
| Autonomy ladder (D-5, D-23) | Company at L1; policy takes autonomy level | No promotion or demotion is ever computed; the evidence exists in outcomes but nothing reads it |

---

## 3. Fundamentally missing

1. **Requirement decomposition.** No artifact between "seven fields" and "tasks". Everything downstream
   (synthesis, capability requirements, verification contracts, budget) needs it.
2. **Workforce synthesis.** Roles, counts and hierarchy are constants (`TEMPLATE`, `REPORTS_TO`,
   `KIND_OWNERS`, `ROLE_TEXT`, three rows of `policy.MATRIX`, a hand-drawn org chart in the UI, 13 hard-coded
   worker ids in `engine.py`).
3. **A role catalog.** There is nowhere to say what a "Data Scientist" is: its responsibilities, the capabilities
   its work needs, its tools, its authority row, the artifacts it produces and **how those artifacts are
   verified**.
4. **Verification beyond software.** The Verification Service knows unit tests, a document lint and an HTTP
   delivery contract. A Data Scientist's forecast, a Designer's flows, a Security Engineer's review have no
   verifier. Without one, those workers can only be judged by other models, which is the weakest evidence.
5. **Capability requirements per worker.** Selection today is by task kind (`code`, `spec`...). The product
   needs "this worker's workload needs coding 70%, data analysis 30%, context ≥ 64k, tool use", matched to
   evidence per capability.
6. **Tenant scoping of learning.** The registry learns across runs in one installation. D-7 forbids
   cross-tenant learning without explicit founder opt-in. A multi-tenant product must keep evidence per company
   and aggregate only with consent.
7. **A native tool-calling execution loop** with a provider-neutral action schema (models from different
   vendors emit tool calls differently; the Gateway must be the one format).
8. **Task-level reassignment** (moving a task to another worker, as opposed to changing a worker's model), and
   **workforce adaptation** (adding or removing workers mid-project).

---

## 4. Retain

- **The Gateway and policy model**: identity → policy → budget → target → execute → audit, default deny,
  prohibited list. This is the product's control plane. Generalize its inputs (role catalog rows), do not
  replace it.
- **Protocol objects and the event log**: every coordination message structured, hashed, replayable.
- **The Verification Service as a platform service, not a worker** (D-4). Its independence is the reason
  measurements mean anything.
- **"Nothing invented"**: an unrun step is unrun, not failed; model errors stop the step visibly.
- **Evidence-based intelligence assignment** as built (`workforce.estimate`): priors neutral by name,
  evidence from Cynqra's own verified work, whole table kept.
- **Identity-preserving replacement** as built, with the inheritance list.
- **The founder's decision surface cap** (D-11) and the decision labels (D-10).

## 5. Redesign

| Now | Why it must change | To |
| --- | --- | --- |
| Five task kinds with fixed owners (`KIND_OWNERS`) | Owners are role ids of a fixed org | Task kinds belong to **artifact types** in the role catalog; a task's owner is any worker whose role produces that artifact type |
| `policy.MATRIX` keyed by three role names | Cannot express a synthesized role | Authority rows per **catalog role**, generated from the role's declared action classes, capped by the risk rubric, versioned (ADR-6 already plans rows in Postgres) |
| `ROLE_TEXT` constants | Four prompts | Role charter from the catalog + the worker's own responsibilities from the approved workforce |
| One approval for "organization and plan" | The product has two distinct approvals | Gate 1: workforce + economics. Gate 2: organization + roadmap |
| Model selection per role's task kinds | Too coarse; roles are now arbitrary | Selection per **worker workload profile** (capability mix from its assigned requirements) |
| Replacement triggered by 3 failed verifications | Right trigger, too blunt | A **degradation test** (below), then a candidate **evaluation**, then the swap |
| Work units as the hard stop | Not money | USD ledger is the hard stop; work units kept only as an internal meter |
| D-17 founder reviews every MEDIUM action | With 12 workers, MEDIUM actions exceed the D-11 cap of ~3 decisions/day | Independent-worker review for MEDIUM (a reviewer on a *different* model family), founder sees a digest; needs a decision revising D-17 |

---

## 6. Challenges to the product definition

**6.1 An AI "CEO" under a human founder is a contradiction.** The founder holds the objective, the budget and
all HIGH-risk authority (D-21, prohibited list). An AI CEO has nothing to decide that is not the founder's or
the CTO/CPO's. Every extra layer costs tokens and latency on every coordination hop, which is exactly what S2
measures and has not yet scored. Recommendation: synthesis must justify each role by **workload it owns**, not by
title; management layers only when span of control demands them (e.g. more than ~6 direct reports). For the
restaurant example that removes the CEO, and probably the CPO.

**6.2 The illustrative budget is off by orders of magnitude, and that matters for the model.** S2's locked
estimate is 12,000–20,000 tokens per task. At hosted open-model prices ($0.2–$3 per million tokens), a
60-task project costs roughly **$1–$30 in tokens**, not $3,000 per worker. The real costs are elsewhere:
infrastructure, data, third-party APIs, human review time, and wall-clock time. An economic model that allocates
$50,000 across "CEO $3,000, CTO $5,000" would be fiction. The Budget Engine must be built bottom-up from measured
cost per verified task, plus infrastructure and tools as separate lines, and report the time dimension (which is
where local models are expensive).

**6.3 "Capability scores" in a registry contradict "evidence-based".** Reasoning 9.4, coding 8.7: somebody
invents those. Registry fields should split into **facts** (context, tool use, multimodal, licence, price,
hardware: eligibility filters) and **evidence** (verified outcomes per capability, per tenant). Cold start comes
from a **standardized evaluation suite** per capability run on registration (the probe, extended), not from
benchmark numbers. Published benchmarks may be shown, never used as scores.

**6.4 Within one project, the evidence is too thin for confident replacement.** A worker may do 5–10 tasks. Three
failures on one task are as easily the task's fault (a bad spec, an ambiguous handoff, an impossible constraint)
as the model's. Replacement needs: (a) outcomes normalized by task difficulty (the same task's other attempts,
the same kind across models), (b) a check that the failure is not upstream (was the spec verified? did the PM's
handoff change?), (c) an **evaluation of the candidate on the failed task's context** before the swap, and
(d) evidence accumulated across the tenant's projects. Otherwise Cynqra will churn models on noise.

**6.5 Correlated judgment.** If the author and its reviewer run on the same model, review catches little. The
assignment engine should prefer a **different model family** for reviewers and verification-by-model than for
the author. This is a real use of many-to-many assignment, and a better argument for it than cost.

**6.6 Verification decides which roles are real.** A synthesized Data Scientist whose forecast is judged only by
another model is theater. The next POC should only synthesize roles whose outputs have an automated verifier:
code (tests), data pipelines (schema + row checks), forecasts (backtest error against a holdout, computed by the
platform, not reported by the worker), APIs (contract checks), UI (render + accessibility checks), deployment
(health + smoke). Roles without one (brand, marketing strategy) stay out until they have one.

**6.7 Autonomy.** "Progressively more autonomy as trust is established" is D-5/D-23. Today nothing promotes.
Evidence now exists (verified outcomes, defect escapes, human overrides); the promotion rule should read it.

**6.8 The founder surface.** Two approvals per project plus replacements plus MEDIUM reviews plus deploys will
exceed D-11's ~3 decisions a day. Replacements that stay within budget and policy should not ask; they should
appear in a daily digest with the evidence and a one-click reversal.

---

## 7. Minimum architecture for the next POC

Eight components. Five exist in some form.

```
                 ┌──────────────────────────── founder ────────────────────────────┐
                 │  objective, constraints, budget     approve workforce  approve roadmap   decisions (≤3/day)
                 ▼                                         ▲                   ▲                ▲
 [1 Objective & Requirements]──►[2 Workforce Synthesizer]──┤                   │                │
          │ requirement graph        │ workers (roles, counts,│                   │                │
          │                          │ workload profiles)     │                   │                │
          │                          ▼                        │                   │                │
          │               [3 Intelligence Assignment]◄──[Intelligence Registry + Evidence]◄──────┐ │
          │                          │ worker→model           ▲                                  │ │
          │                          ▼                        │                                  │ │
          │                   [4 Budget Engine]───────────────┘ (forecast)                       │ │
          │                          │                                                           │ │
          └──────────────►[5 Roadmap Engine]──── org, workstreams, milestones, tasks ────────────►│ │
                                     │                                                           │ │
                                     ▼                                                           │ │
                    [6 Execution Gateway]  model proposes → identity → policy → budget → target  │ │
                                     │      → execute (sandbox) → result → model                  │ │
                                     ▼                                                           │ │
                    [7 Verification + Evaluation Engine]  verdicts, outcomes, degradation ────────┤ │
                                     │                                                           │ │
                                     ▼                                                           │ │
                    [8 Replacement / Optimization Engine]  evaluate candidates, swap, reassign ──┘─┘
```

**Contracts between them** (all data, all in the event log):

| From → To | Artifact |
| --- | --- |
| 1 → 2 | `RequirementGraph`: requirements typed by area (product, data, ML, backend, frontend, UX, infra, security, QA, deploy), each with acceptance criteria, **verifier type**, estimated effort (S/M/L), dependencies |
| 2 → 3, 4, 5 | `WorkforceProposal`: workers `{id, catalog_role, count index, owned requirement ids, workload profile (capability mix, context need, tool needs), reports_to}` plus a justification per worker (the workload it owns) |
| Catalog → 2, 6, 7 | `RoleCatalog`: role → charter, capabilities needed, artifact types produced, tools, authority row, verifier types |
| 3 → 4, 5 | `Assignment`: worker → model, with the scoring table and the evidence behind it; reviewer-diversity constraint applied |
| 4 → founder | `Economics`: per worker × model: expected tasks, tokens, $, hours; infrastructure, tools, verification, deployment lines; reserve; confidence band |
| 5 → 6 | `Roadmap`: workstreams, milestones, tasks with owner worker, reviewer worker, verifier, dependencies, sequencing |
| 6 → 7 | Action results and claims (REVIEW) |
| 7 → Registry, 8 | Verdicts and outcomes (model, worker, role, capability, task, difficulty, attempt, cost, time, verdict, failure) |
| 8 → 3, 5, 4 | Replacement or reassignment decision with evidence; budget move |

---

## 8. How the engines interact, and who decides what

| Engine | Deterministic (code, rules, math) | LLM-driven (proposes, never decides authority) |
| --- | --- | --- |
| Objective & Requirements | Schema validation; every requirement has a verifier type from the catalog or is flagged; dependency graph acyclic | Reading the objective; drafting requirements, acceptance criteria, effort |
| Workforce Synthesizer | Roles only from the catalog; every requirement owned; span of control; no role without a verifier; minimum-workforce check (merge roles whose workload is small); budget feasibility | Proposing roles, counts and ownership from the requirement graph, with a justification per worker |
| Intelligence Assignment | Eligibility filters (context, tools, availability, licence); scoring formula; budget constraint; reviewer-diversity constraint; tie-breaks | None. Assignment is arithmetic over evidence |
| Budget Engine | All of it: forecast from measured cost per verified task per model and kind, fixed lines for infra/tools, reserve policy, ledger, breakers | None |
| Roadmap Engine | Topological order, milestone gates, owner validity, reviewer ≠ author, sequencing | Proposing workstreams, milestones and task wording |
| Execution Gateway | All of it: identity, policy row, budget, target validation, sandbox, audit | The worker's *request* only |
| Verification | All automated verifiers; model-based review only where the catalog allows it, always by a different model family, and weighted as weak evidence | Reviewer's opinion, recorded as such |
| Evaluation | Outcome recording, difficulty normalization, degradation test (e.g. first-pass rate on this worker's last N tasks below the model's tenant baseline by a margin, with N ≥ 3) | None |
| Replacement / Optimization | Trigger rules, candidate evaluation run on the failed task's frozen context, swap, reallocation, reversal | Diagnosing an upstream cause (bad spec?), as a proposal the rules check |

The rule: **an LLM may propose any structure; only deterministic code may grant authority, spend money, choose a
model, or declare work verified.**

---

## 9. The exact changes from this POC

In order. Each step keeps the suite green and the product runnable.

**Decisions first (founder):** D-37 superseding D-2 for the next POC (dynamic synthesis from a governed role
catalog); a revision of D-17 (independent-worker review for MEDIUM, founder digest) or an explicit acceptance
that the founder surface will exceed D-11 in the POC; D-7 applied to the registry (evidence per tenant).

1. **Role catalog** (`cynqra/roles.py` + `roles/*.json`): PM, Tech Lead, Backend Engineer, Frontend Engineer,
   Data Engineer, Data Scientist, QA Engineer, DevOps Engineer, Product Designer. Each: charter, artifact types,
   tools, action classes, verifier types, capability mix. Replace `TEMPLATE`, `REPORTS_TO`, `ROLE_TEXT`,
   `KIND_OWNERS`, and the three `policy.MATRIX` rows with catalog lookups. The old four become one catalog
   instantiation, kept as the regression fixture.
2. **Workers by id, not by constant.** Replace the 13 literal worker ids in `engine.py` (`w_pm` as the default
   assigner, `w_cto` for review/deploy) with roles resolved from the organization (`the worker whose role
   reviews`, `the worker who assigns`). The UI draws the org chart from `organization.reports_to`.
3. **Requirement decomposition** (`intelligence.decompose`, schema-validated): the `RequirementGraph` between
   the objective and the plan.
4. **Workforce Synthesizer** (`cynqra/synthesis.py`): LLM proposal constrained to the catalog, then the
   deterministic checks of section 8. Produces `WorkforceProposal`. New decision kind `approve_workforce`.
5. **Assignment per workload profile** (`workforce.py`): score each worker against the capability mix of its
   owned requirements; add reviewer-diversity; keep the table. Evidence keyed by capability as well as task kind.
6. **Economics** (`workforce.forecast`): per worker × model tokens, $ and hours from measured cost per verified
   task; infra and tools lines; reserve; shown at the workforce gate. USD becomes the hard stop.
7. **Roadmap Engine** (split `_plan`): workstreams, milestones, tasks with owner, reviewer and verifier from the
   catalog. Decision kind `approve_roadmap` after `approve_workforce`.
8. **Verifiers for the new artifact types** (`verification.py`): data schema and row checks; **forecast backtest**
   (the platform computes error on a held-out window of a platform-owned dataset); API contract checks.
9. **Evaluation before replacement**: freeze the failed task's inputs; run the top two candidates on it in the
   sandbox; swap to the one that passes (or the cheaper if both pass); record the evaluation as outcomes.
   Degradation test in addition to the three-failure trigger. Upstream-cause check: if the task's spec or handoff
   was itself unverified or changed, reassign upstream first.
10. **Task reassignment** (move a task to another worker of the same role) as a separate action from model
    replacement.
11. **Tenant scoping** in the registry: evidence rows carry `company_id`; cross-company aggregation behind an
    opt-in flag (D-7).
12. **Sandbox** for code and tests (the M2 criterion): a container or at least a separate OS user with no network,
    before any role with tools beyond the current set.
13. **Native tool calling** through the gateway, with one provider-neutral action schema; the structured-text
    path stays as the fallback for models without tool calls.

What stays out of the next POC: an AI CEO, research on the open web, workforce adaptation mid-project (adding or
removing workers), autonomy promotion. Each is real, none is needed to prove the thesis.

---

## 10. The demonstration: an AI-powered restaurant demand forecasting platform

**Founder input.** Project "Tablecast". Objective: "Forecast daily covers and ingredient demand for a
three-site restaurant group from their sales history, so managers order the right stock." Constraints: runs on
one laptop, no customer personal data, standard library Python, a web dashboard. Budget: **$25**, value of an
hour $10. (Tokens are cheap; the budget is honest about that.)

**1. Requirements** (LLM drafts, schema checks it, founder sees it):

| Area | Requirement | Verifier |
| --- | --- | --- |
| Data | Ingest daily sales CSVs per site; validate schema; fill gaps | schema + row checks on the platform's sample data |
| ML | Forecast covers 14 days ahead per site; weekly seasonality, holidays | **backtest**: MAPE on the held-out last 28 days ≤ a threshold set from a seasonal-naive baseline the platform computes |
| ML | Ingredient demand from covers × recipe mix | unit tests |
| Backend | API: forecasts, accuracy, ingredient orders | contract tests |
| Frontend | Dashboard: per-site forecast, confidence, order list | render + accessibility checks |
| QA | Test plan across the above; regression suite | tests pass; coverage of acceptance criteria |
| Deploy | Runs on the laptop with health checks | health + smoke |

**2. Workforce proposal** (LLM proposes from the catalog; code checks it):

| Worker | Catalog role | Owns | Why it exists |
| --- | --- | --- | --- |
| lead-1 | Tech Lead | architecture, review, merge, deploy proposal | reviews all code; reports to the founder |
| pm-1 | Product Manager | spec, acceptance criteria, product rules | sequences work; answers Blockers |
| data-1 | Data Engineer | ingestion, validation | data work is separable and verifiable |
| ds-1 | Data Scientist | forecasting, backtests | the ML requirement |
| be-1 | Backend Engineer | API, ingredient demand | |
| fe-1 | Frontend Engineer | dashboard | |
| qa-1 | QA Engineer | test plan, regression suite | independent of the authors |

Seven workers. No CEO (6.1), no CPO (the PM owns product), no DevOps (deploying to one laptop is the Tech Lead's
proposal and the platform's execution), one backend engineer (the workload is small). If the synthesizer proposed
twelve, the minimum-workforce check would merge roles whose owned effort is under a threshold, and the founder
would see why.

**3. Assignment** (three registered models; numbers are what the tables would show, from evidence):

| Worker | Model | Why (from the table) |
| --- | --- | --- |
| lead-1 | Kimi K2.5 | best verified rate on review and planning; cost small because review is short |
| pm-1 | Qwen3.5-35B-A3B | spec work passes lint first time at a fraction of the cost |
| data-1, fe-1, qa-1 | Qwen3.5-35B-A3B | cheapest per verified task on their kinds (one model, three workers) |
| ds-1, be-1 | GLM-4.7 | higher first-pass rate on code; worth its price per verified task |
| reviewer of GLM's code | Kimi K2.5 | reviewer-diversity: not the author's model |

**4. Economics** (founder sees before approving): per worker × model: expected tasks, tokens, $, hours; plus
infrastructure $0 (laptop), tools $0, verification compute (hours), reserve 30%. Example total: about $4 of
tokens and about 6 hours on the laptop models, with a $25 budget: the founder learns time, not money, is the
constraint on local models.

**5. Approve workforce → 6. Roadmap** (milestones: data validated → baseline forecast beats seasonal-naive →
API + dashboard → QA regression → deploy) **→ 7. Approve roadmap.**

**8. Execution through the Gateway.** ds-1 (GLM-4.7) writes the forecaster; the platform runs the backtest
itself on the held-out window; the worker never reports its own accuracy.

**9. Failure and replacement.** The founder caps ds-1's model's replies (or GLM-4.7 simply fails the backtest:
MAPE above the threshold three times). Cynqra:
1. records three failed outcomes for GLM-4.7 on `ml.forecast` in this company;
2. checks upstream: the data validation task was verified, the spec unchanged, so the failure is ds-1's;
3. freezes the task context and evaluates Kimi K2.5 and Qwen3.5-35B-A3B on it in the sandbox;
4. Kimi passes the backtest; Qwen does not;
5. ds-1's model becomes Kimi K2.5. ds-1 keeps its id, its owned requirements, its history (three failures under
   GLM, now a pass under Kimi), its reporting line and its authority. The ledger releases GLM's unspent allocation,
   charges the evaluation, draws Kimi's expected cost from the reserve;
6. the founder's digest: "ds-1's intelligence changed GLM-4.7 → Kimi K2.5 after 3 failed backtests; evaluation
   evidence attached; $0.21 moved from reserve; reverse?"

**10. Delivery.** QA's regression suite passes, the Tech Lead proposes the deploy, the founder approves (D-21),
the platform deploys with health and smoke checks, and the export carries the event log, the decisions, every
assignment table, the replacement with its evaluation, and the ledger.

What this demonstrates, against the six things the POC must show: different workers on different models (ds-1
vs pm-1); several workers on one model (data-1, fe-1, qa-1); selection from capability, cost and evidence (the
tables); measurement (outcomes per worker and model); replacement (ds-1); the same worker continuing (ds-1's
identity, ownership and history across the change).

---

## 11. The risks, plainly

1. **Coordination cost grows with the workforce and is unmeasured** (S2 unscored). A seven-worker org may cost
   more per verified task than four. Measure it before claiming synthesis is better.
2. **Verification coverage limits the product.** Every role without an automated verifier is a role Cynqra cannot
   honestly measure, and so cannot honestly optimize.
3. **Small-sample replacement** will churn models on noise unless evaluation-before-swap and tenant-level evidence
   exist.
4. **Local hardware** makes time, not money, the binding constraint; the economics must show hours.
5. **The canon.** D-2, D-17, D-11 and D-7 each conflict with part of this. The decisions must be written before the
   code, or the code will quietly contradict the governance it exists to enforce.
