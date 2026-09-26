# S2 rulings

Recorded 26 September 2026 by the acting CTO, before any S2 run and before any S2
token was measured. S2_ESTIMATE.md and tasks.json are unchanged and stay locked.

## Why this file exists

The handover said S2 was one command. The command did not exist: spikes/s2 held only
the run sheet and the task list. A runner was found inside
04_prior_builds/cynqra_m1_harness.zip, written during the false alarm of 25 August and
never carried into the handover. It made one model call per task, with no Handoff
between workers, no Blocker, no review and a fixed count of two messages per task. It
measured the cost of a single completion, not the cost of coordination, which is the
whole question S2 asks. Its self test also showed its bar check passing a result fifty
times below the estimate. It is not used. run_s2.py was written fresh.

## R1. What "within 2x of the estimate" means

The estimate has five lines. Each line passes when the measured median is between half
and double the estimate: 0.5 <= measured / estimate <= 2. S2 passes only when all five
lines pass, all twelve tasks finish, and every message between workers is a structured
protocol object.

Why two sided: Book 2 says "cost model lands within 2x of estimate" and Book 3 section 6
says S2 seeds the cost model. A cost model that is ten times too pessimistic misprices
the product as badly as one that is ten times too optimistic. The report also shows the
upper bound alone under context_only_upper_bound. That field never decides anything.

Risk stated in advance: the wall time lines (8 and 15 minutes) assume workers that loop
through tools. This runner makes plain model calls, so wall time may land below half the
estimate and fail. That would be a real finding about the estimate, and the bar does not
move to avoid it.

## R2. What each measured number is

1. Tokens per task: input plus output tokens of every model call made for that task:
   the assignment, the work, any Blocker answer and retry, any format retry, and the
   MEDIUM review.
2. Tokens per protocol message: tokens of each call whose only output is a coordination
   object, meaning PM assignments, Blocker answers and reviews. Work calls are left out
   because their tokens are the work product, not coordination.
3. Wall minutes per task: elapsed time from assignment to the last message of the task.
4. The median of each is taken over the LOW tasks, the MEDIUM tasks, or all
   coordination calls, as the estimate line says.

## R3. How the simulated organization works

Fixed template: CTO, PM, Engineer A, Engineer B. No fifth worker.
1. The PM assigns engineering tasks with a Handoff that it writes. The orchestrator
   assigns PM and CTO tasks with a fixed Handoff listing the artifacts of the same
   workstream.
2. A worker sees its role, the company context in company_context.json, its Handoff and
   only the artifacts the Handoff lists (Book 0 section 19, context layering).
3. A worker that would have to guess raises a Blocker. The worker it names answers with a
   Handoff. One more try, then the task ends blocked and counts as a founder touch.
4. MEDIUM work gets an Approval from a worker who did not do it. The founder reviews every
   MEDIUM action under D-17, so those tasks count as founder touched.
5. Routing fields (from, to, task, decision id) are set by the runner. Workers never
   route themselves (Book 2: authority is never inferred from model text).
6. Every message is stamped with protocol_version, created_at, correlation_id and an
   object hash, closing break b_006.

## R4. Refusals

1. No model: exit 2.
2. Any model error: stop, write s2_unrun.json, exit 3. Unrun, not failed.
3. Token counts estimated from a shell command: the run is a wiring test. It writes
   s2_wiring_test.json and exits 4. It never writes s2_report.json.
4. Token cap of 600,000 for the whole run, about three dollars on Claude Sonnet 5. If it
   is hit the run stops and the report says so, with met_bar false.

## R5. Model

Default is claude-sonnet-5 with an Anthropic key, or gpt-4o-mini with an OpenAI key.
CYNQRA_MODEL overrides. The report names the exact model. Whoever runs S2 writes the
model into the memo, because a cost result belongs to the model that produced it.
