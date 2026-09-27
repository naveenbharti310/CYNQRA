# Cynqra's AI workforce: choosing, measuring and replacing the intelligence

Cynqra is an operating system for AI-run organizations. Intelligence is replaceable; identity, authority,
policy, execution, verification, memory, budget and accountability stay with the platform. This document
records how the proof of concept now separates **the worker** from **the model**, how Cynqra chooses a model
for each worker, measures it on real work, replaces it when it fails, and keeps the project inside a budget.
Everything described as implemented is in `poc/` and covered by tests; what is not yet built is said plainly.

> Since 27 September the model registry, the router and model access are the **Intelligence Layer**
> (`poc/cynqra/intelligence_layer/`): provider connections, credentials in a secrets layer, the Intelligence
> Registry, the Router and the Intelligence Gateway, with a worker's intelligence held in a binding, never on the
> worker. CYNQRA_INTELLIGENCE_SUPPLY.md maps the locked V1 decisions to the code. Sections 2 to 9 below record how
> the workforce first came about; where they name `registry.py`, `router.py` or a worker's `model_id`, read the
> Intelligence Layer and the worker's binding.

## 1. The architecture as it was, and what was only conceptual

Read from the code, not the README.

| Part | Where | State before this change |
| --- | --- | --- |
| Event log, append-only, hash-chained | `cynqra/db.py` | Implemented |
| Objective System: sentence to seven fields, founder confirms | `engine.draft_objective`, `intelligence.structure_objective` | Implemented, with a real model |
| Organization: CTO, PM, two engineers, reporting lines | `engine.TEMPLATE`, `_instantiate_org` | Implemented, **fixed template** of four |
| Workers: identity, role, capabilities, authority policy, performance profile | `worker` records | Implemented; `intelligence_source_id` was **one label shared by all four** |
| Planning, assignment by the PM, Handoff/Blocker/Approval protocol objects | `engine._plan/_assign/_answer`, `protocol.py` | Implemented |
| Gateway: identity, policy, budget, target validation, execute, audit | `engine.gateway`, `policy.py` | Implemented; default deny; D-17 and D-21 enforced |
| Verification: tests rerun in a clean folder, lint for documents, delivery contract, self-checks | `engine._verify`, `verification.py`, `deploy.py` | Implemented |
| Build, test, merge, release candidate, health and smoke checks, deploy, rollback | `deploy.py`, `_execute_approved` | Implemented, on this machine |
| Budget | `engine.charge` | Work units (1 unit = 1,000 tokens), one company cap and a breaker |
| Model access | `model_adapter.py` | **One model per process**, named by environment variables |
| What happens when a worker keeps failing | `_escalate` | The founder is asked; **no other model is ever considered** |

So the seams existed (a worker was already separate from the prompt that drives it, and authority came from the
role, not the model) but the product behaved as one model playing four roles.

## 2. The minimum change

Five changes, no rewrite. The task engine, the protocol, the gateway, policy, verification and deployment are
unchanged; they still see the same four workers.

1. **A call carries its model.** `model_adapter.complete(route=...)`: the route holds one model's settings and
   overlays the environment for that call, on that thread. Without a route, nothing changed.
2. **A model registry** (`cynqra/registry.py`): models as facts, calls metered, verifications recorded as
   outcomes. It sits beside the runs, so learning carries across projects.
3. **A workforce engine**: scoring, staffing, allocation, the ledger. Since the rebuild these are the
   Intelligence Router (`cynqra/router.py`) and the Budget Engine (`cynqra/budget.py`).
4. **Engine hooks**: staff at organization time, allocate after the plan, meter each call, record each
   verification, replace instead of escalating when another model fits. Since the rebuild: the orchestrator
   (`engine.py`), the Verification Service (`verifier.py`) and the Replacement Engine (`replacement.py`).
5. **Routing in `ModelSource`** (`cynqra/intelligence.py`): each call is sent through the calling worker's
   current model. The prompts are the same.

## 3. The model registry

### Data

`model` (one per registered model): `id`, `name`, `version`, `provider`, `runtime` (`llama` on this machine,
`hf` for Hugging Face Inference Providers, `openai_compatible` for any compatible server, `environment` for
the model the environment names, priced at its list price, and `scripted` for a demo's prepared script, which
stands in a demo run's own registry so the demo is staffed and metered like any run), `ref` (catalog id,
Hugging Face id with its provider, or served name), `local`, `hardware`, `context`, `license`, `params`,
`price_in`/`price_out` (USD per million tokens), `compute_usd_per_hour` (for a model on this machine),
`base_url`, `api_key_env` (the variable's name; a key is never stored), `effort`, `json_schema`, `tools`,
`status`, `fault`, `health`, `registered_at`.

There is no capability score. For a Hugging Face model the provider, price and context come from the router's
live listing at registration.

`call` (every model call): `model_id`, `role`, `purpose`, `task_kind`, `run_id`, tokens in and out, seconds,
`usd`, write speed, `error`.

`outcome` (every verification of one attempt): `model_id`, `role`, `task_kind`, `task_id`, `run_id`, `attempt`,
`verified`, `first_pass`, `usd`, `seconds`, `tokens`, `failure` (the failing tests or the reason), `source`
(`project` or `probe`).

### Derived

`stats(model, kind)`: attempts, verified, success rate, first-pass rate, cost, time and tokens per attempt,
calls, call errors, total spend, speed. `profile(model)`: overall and per kind of work.
`availability(model)`: registered, runnable here (downloaded, token set, key variable set), and not down (two
failed calls in a row mark it down for ten minutes).

### API

| Method | Path | Does |
| --- | --- | --- |
| GET | `/api/models` | Every model with facts, availability, measured profile; running probes |
| POST | `/api/models` | Register: `{runtime, ref, name, ...facts}` |
| POST | `/api/models/<id>/probe` | Run the calibration work on it (below) |
| POST | `/api/models/<id>/fault` | `{offline: bool}` or `{max_reply: tokens}`, for proving replacement |
| POST | `/api/models/<id>/remove` | Retire it; its record stays |
| POST | `/api/objective/guardrails` | Also `budget_usd` and `time_value_per_hour` |
| GET | `/api/state` | `workforce`: workers and their models, tables, ledger, replacements, registry |

### Probe

`cynqra/probe.py`. A newly registered model does two pieces of Cynqra's real work: structure a founder's
sentence into the seven fields (verified when at most one is left for the founder to fill), and write a small module and its tests from a
precise handoff, fixing it from the failing tests for up to three rounds (each round verified by running the
tests). Every round is an outcome with its real tokens, time and cost. It is how selection starts from evidence
instead of a name. The desktop app's `--check-model` runs the same probe on a registered model, so a machine
check is also that model's first measured record.

## 4. The AI worker

A worker is **role + identity + authority + tools + budget + history**, with a **model assignment**:

```
worker w_eng_a
  role        Engineer                      (authority from policy.MATRIX["Engineer"])
  reports to  w_pm
  tools       write_file, run_tests, send_protocol; merge_to_main and install_package only as proposals
  budget      allocated and spent, USD      (the workforce ledger)
  history     verified, first pass, reworks, Blockers
  model_id    qwen3-5-9b                    (the only thing a replacement changes)
```

Changing `model_id` changes nothing else: the gateway checks the same role, the task keeps its id, handoff and
files, the protocol objects keep flowing between the same workers.

## 5. The workforce selection engine

For a model *m* and a kind of work *k* (a task type from the catalog: document, decision, code, forecast,
review_merge, deploy; or coordination work: objective, plan, assign):

- **p**, the chance one attempt passes verification: *m*'s verified over attempts on *k*, pulled toward *m*'s
  record on all kinds with the weight of two samples: `p = (verified_k + 2 * p_m) / (attempts_k + 2)`,
  `p_m = (verified + 1) / (attempts + 2)`. With no history, 1/2 for every model: nothing favours a name.
- **c** and **t**, cost and seconds of one attempt: *m*'s measured means on *k*; else on all kinds; else the
  mean size every model has measured on *k*, priced at *m*'s rate and speed; else S2's pre-registered estimate
  (12,000 tokens for LOW work, 20,000 for MEDIUM).
- Within the engine's three attempts: `P = 1 - (1-p)^3`, expected attempts `E = P / p`.
- **Score** = `(E*c + value_of_time * E*t) / P`: the expected money and time spent per verified task. Lower is
  better. This is "expected successful outcome per unit of cost and time"; the founder sets the value of an hour.

Staffing gives each worker the model with the lowest summed score over its role's kinds of work, among available
models whose expected cost fits the budget. Every choice stores the whole table (each model's P, expected cost,
expected minutes, score and the evidence behind them), shown in the Workforce view and in the event log.

What makes this learn: every verification adds an outcome. A model that keeps failing code sees its `p` for code
fall and its score rise; a cheaper model that passes sees the opposite. On the next staffing or replacement, the
table is different.

## 6. Worker replacement

Triggers:
1. a task fails verification three times;
2. four replies in a row run past the model's output limit;
3. the model stops answering (two failed calls in a row).

What happens, in the Replacement Engine (`replacement.evaluate`; the steps below are the forced path, and since
the product definition's flow the Performance Engine's thresholds can trigger it earlier, where keeping the
model is a valid answer, a task can be rerouted to a peer of the same role, and every successor passes a
regression check first):
1. The failure is recorded as outcomes against the model, with the failing tests.
2. Every other available model is scored for this task's kind, with the updated evidence, against the budget
   left: the reserve plus what the failing model left unspent of this task's allocation.
3. If one fits: the worker's `model_id` changes; the ledger releases the failing model's unspent allocation and
   draws the new model's expected cost; a `replacement` record and a `worker.model_replaced` event keep the
   reason, what the previous model spent, how many attempts reached verification, and the whole table.
4. The task goes back to work with its attempts reset. The successor inherits the objective, the task and its
   handoff, the decided rules, **the workspace files** (kept, since a reply now carries only the files it
   changes), the previous attempts and the test failures, and a handover note naming the previous model.
5. The founder decides only when no model is available, none fits the budget, or the task has already had two
   replacements. High-risk actions still need the founder (D-21), whatever the model.

## 7. Performance measurement

Primary evidence is Cynqra's own work. Each outcome records who (model, role), what (task kind, task, run),
whether it passed, on which attempt, and at what cost and time. From these:

| Measure | From |
| --- | --- |
| Success rate per model and kind | verified / attempts |
| First-pass rate | tasks verified on attempt one / tasks started |
| Cost and time per attempt | the metered calls of that attempt |
| Speed | llama-server's or the provider's own token timings |
| Reliability | failed calls; time down |

Probes add outcomes of the same kinds before a project. Benchmarks and model cards are not used as scores.

## 8. Budget allocation

The founder sets a USD budget and the value of an hour. After the plan is approved, each task is allocated its
expected cost on its owner's model; the rest is the **reserve** for retries and replacements. Every call is
charged in dollars to its worker and task (hosted: tokens at the provider's price; on this machine: seconds at
the stated rate per hour). A task past its allocation draws on the reserve. A replacement releases the failing
model's unspent allocation and draws the successor's expected cost. The workers' own test runs and the Verification Service are
charged as this machine's time. The Workforce view shows the budget, allocations, spend, reserve and each move
in the ledger. The dollar cap is the hard stop: when spending reaches it the breaker opens and all work pauses
until the founder raises the cap or stops the run.

## 9. The proof of concept: run it

**In the app** (`poc/desktop.py`, or the installed Cynqra): open **Models** from the first screen, register three
models, probe them, then give the objective and a USD budget. The **Workforce** view shows each worker's model and
why; on any model card, **Take offline** or **Set reply cap** makes it fail for real; the Workforce view then
shows the detection, the replacement, the inherited context and the budget moving, and the project continues.

**Unattended** (`poc/workforce_demo.py`):

```
python poc/desktop.py --workforce local "objective"   # Qwen3.5 4B, Qwen3.5 9B, gpt-oss 20B on this machine
python poc/desktop.py --workforce hf "objective"      # Qwen3.5-35B-A3B, GLM-4.7, Kimi K2.5 (HF_TOKEN)
```

It registers, probes, staffs, caps the replies of the model staffed as Engineer A, runs to delivery, and writes
`reports/workforce_<time>.json` with the staffing tables, every replacement, the ledger and every outcome.
On GitHub, a commit message with `[workforce]` runs both (`.github/workflows/cynqra-workforce.yml`).

No response is mocked in the product or the demonstration. The unit tests (`poc/tests/test_workforce.py`) use a
llama-server test double so they run in seconds; they are tests of the mechanism, not results.

## 10. Since then (27 September): the product definition's flow

The roles are no longer the fixed four: a role catalog (`roles.py`) and the Workforce Synthesizer choose the roles
and quantities an objective needs, behind a founder gate; staffing is refined to each worker's actual workload;
the Performance Engine and the Replacement Engine decide keep, reroute (the task moves to a peer of the same role)
or replace, and a regression check comes before any new intelligence continues. CYNQRA_PRODUCT_ALIGNMENT.md has
the whole account.

**Measured.** The first `[workforce]` run on real models (27 September, commit 44a2327) stopped before it began:
the app build did not package `workforce_demo.py` (`ModuleNotFoundError`). No model was run and there is no
result. Fixed, and the demonstration now runs in the test suite against the llama-server test double.

The second (27 September, commit 7bcd244, run 36310111670, a 4-thread CPU runner, bakery objective) ran the
probes: Qwen3.5 9B and gpt-oss 20B each filled 7 of 7 objective fields and passed the code work in one round
(14 and 16 tests, 295 s and 180 s); Qwen3.5 4B filled the objective but failed the code work in all three
rounds (one test failing each time). It then stopped at Stage 2: the synthesized workforce was refused twice
with "r_01 (product: …) is covered by no proposed role". The check was right; the refusal did not say how to
fix it. Refusals now name the roles that close the gap ("add a role that covers product: CEO, CPO, PM"), with a
test, and the demonstration was pushed again.

The third (27 September, commit c1952ad, run 36315283277, same runner and objective) probed all three models:
Qwen3.5 4B passed the code work in one round (15 tests, 264 s), Qwen3.5 9B in three (17 tests; 1 failing in
rounds one and two), gpt-oss 20B in two (16 tests, all 16 failing in round one). All three filled 7 of 7 objective
fields. It stopped at Stage 2 again, after about eight minutes of synthesis: "r_13 (devops: every change must
re-run all tests) is covered by no proposed role; add a role that covers devops: CTO, DevOps". So even with the
refusal naming the roles, the model did not add one. Which roles cover an area is the catalog's rule, not a
judgment, so the platform now closes such a gap itself: it adds the catalog role that closes the most open gaps,
labelled "Added by Cynqra" with what it closes, for the founder to see at the workforce gate. A founder's own
edit is still refused, not completed behind them. Tests in `test_product_flow.py`. The Hugging Face job did not
run: the repository has no `HF_TOKEN` secret.

The same commit's desktop build on Windows (run 36315283319) passed install, self-test, window, Start-menu
launch, uninstall and reinstall into a folder with spaces and accents. Its real-model check did not pass:
Qwen3.6 35B-A3B at 2 bits filled the objective (7 of 7), but left the same 2 of 14 tests failing in all three
code rounds (15.5 tokens/s read, 5.5 written). Every call worked; this is the model's work, and the same model
passed on 0.1.2 earlier that day. Linux and macOS passed the same check.

The desktop app's 0.1.2 end-to-end run on Windows (run 36296951000, the earlier fixed-organization flow, a CPU
runner) passed with Qwen3.6 35B-A3B at 2 bits: accepted, live, healthy, the product's tests passing on rerun;
20 model calls, 73,262 tokens in and 41,322 out, 195.5 minutes, the web app task reworked twice before it
verified. The same run's two Linux end-to-end jobs did not finish within their 340 minutes: gpt-oss 20B
(27 calls, 203,477 tokens in, 53,450 out) and Qwen3.6 35B-A3B at 2 bits (32 calls, 240,609 in, 89,315 out) were
both still reworking the web app task (t_04) when time ran out; gpt-oss once returned an answer the server could
not parse against the schema, and the run stopped on it rather than inventing one. Nothing in the app failed;
these runners write 5 to 7 tokens a second, and the web app is the largest task.

## 11. What is not built yet

- **Replacement changes the worker's model for all its tasks.** Choosing a different model per task for the same
  worker is a small change in `_route` once wanted.
- **Workers answer in text, not native tool calls.** Their files and protocol objects come back as structured
  replies that the engine turns into gateway actions. Native tool calling through the same gateway is the planned
  next form of execution; the gateway does not change.
- **One model runs on this machine at a time.** Local models are swapped in when their worker needs them (seconds
  to load). Hosted models have no such limit.
- **The prior is uniform.** Probes give each model real evidence before its first project; with more runs the
  record, not the prior, decides.

## 12. Direction: Cynqra supplies the intelligence

Decided with the founder on 27 September, to build next. Intelligence will be abundant; what is scarce is
knowing which intelligence to use for which work. If each founder had to bring keys, Cynqra could only route
among the few models that founder happened to hold, and the router would have little to choose from. So Cynqra
supplies the intelligence, and the founder sets the outcome and a budget in dollars:

```
                       CYNQRA
                         │
   Budget Engine ──▶ Intelligence Router ◀── Intelligence Registry
   (dollars left)   (per worker, per task    (models, prices, measured
                     type: lowest cost per    scorecards per task type,
                     verified task)           pooled across runs)
                         │                          ▲
            ┌────────────┴────────────┐             │ outcomes: passed or failed,
         Worker A                 Worker B          │ cost, time, retries
           CTO                 Data Scientist       │
            └────────────┬────────────┘             │
                         │            Verification Service
                         │                          ▲
                Intelligence Gateway ───────────────┘
        (holds credentials in a vault, meters $ per worker and task)
       ┌──────────┬──────────┬───────────┬─────────────┐
     OpenAI   Anthropic   Bedrock   Open-weight    Founder's own
   connection connection connection (hosted/local) key (optional)

   Performance Engine ──▶ Replacement Engine: keep / reroute / replace the model
   (the worker's identity, role, authority and history stay)
```

- **The Gateway holds the connections.** Cynqra's own provider accounts, hosted open-weight models and, as an
  option, a founder's key for a company that must use a particular provider. Credentials live in a vault and are
  added only as a call leaves; no worker, prompt, log or export ever holds one. Every call is metered in dollars
  to the company, the worker, the task and the layer.
- **The Registry becomes a service.** Models, prices and scorecards pooled across every run, so each project
  starts from everything Cynqra has measured. What is pooled is the task type, the outcome, the cost and the
  time, never the work itself.
- **The loop closes on verification.** Every verified or rejected attempt updates its model's record for that
  task type; the Router reads only that record.
- **New models join on evidence.** A new model or version runs the calibration work (the probe) and the
  regression gate, then earns work as its record justifies.

What exists now: the Router, the Registry (per installation), the probe and regression gate, the Budget Engine,
the Performance and Replacement Engines, and per-call routing and metering. What this direction adds: the
Gateway as a service with its vault and connections, and the Registry as a shared service. Business questions
for the founder: reselling terms with each provider, prepaid credit or billing after use, and the data-handling
commitments for calls that pass through Cynqra.

