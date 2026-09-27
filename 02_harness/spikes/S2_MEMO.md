S2 MEMO: Coordination cost (measured)
Date: 27 September 2026
Spike: S2
Result: BAR MISSED, on the low side. 1 of 5 estimate lines within 2x on both models.
Every task finished on Qwen; gpt-oss left one blocked and one message unstructured.

Question
What does a 4 worker org cost per task, against the estimate locked on 25 August?

Bar (S2_ESTIMATE.md and s2/RULINGS.md R1, both written before this run)
Each of five lines between 0.5x and 2x of the estimate, all 12 tasks finished, every
message between workers a structured protocol object.

How it was run
GitHub Actions run 36299849447, commit 34500e3, 27 September 2026.
s2/run_s2.py through spikes/run_local.py on the desktop app's llama-server (b11201).
Machine: GitHub-hosted Linux runner, 4 CPU threads (AMD EPYC), 15.6 GB RAM, no GPU.
Token counts are llama-server's own counts (token_source: measured).

Medians against the estimate
line                      estimate   Qwen3.6 35B-A3B Q2       gpt-oss 20B
tokens per LOW task        12,000     2,001  (0.17x) miss     3,122  (0.26x) miss
tokens per MEDIUM task     20,000     5,636  (0.28x) miss     4,641  (0.23x) miss
tokens per protocol msg       800     1,158  (1.45x) pass     1,012  (1.27x) pass
wall min per LOW task           8     2.3    (0.29x) miss     3.5    (0.44x) miss
wall min per MEDIUM task       15     6.7    (0.45x) miss     5.7    (0.38x) miss
All five lines are under 2x on both models (context_only_upper_bound: all true).

Totals
                           Qwen3.6 35B-A3B Q2       gpt-oss 20B
tasks finished             12 of 12                 11 of 12 (t2_05 blocked)
model calls                23                       27
tokens, all tasks          46,915                   58,370
protocol messages          30                       32
all structured             yes                      no (t2_10)
founder touched            4 (the MEDIUM tasks)     5 (MEDIUM tasks + the blocked one)
retries / blocker rounds   1 / 1                    4 / 2
wall, all tasks            61 min                   75 min

What it proves
- The estimate is about four times too pessimistic on tokens per task and two to three
  times on time. Under the two-sided bar (RULINGS R1) that is a miss, and a real finding:
  the cost model would overprice work. The one line that passes, tokens per coordination
  message, is the one the protocol controls directly.
- Coordination held on the local Qwen model: 12 tasks, Handoffs, a Blocker answered by
  the PM, reviews by a worker who did not do the work, all as protocol objects.
- gpt-oss 20B broke format twice in work replies (t2_06, t2_09; both parsed on retry),
  and t2_10 ended with one protocol message that was not structured. Structure is a model property, not only a protocol one.

What it does not prove
- The estimate assumed tool-looping workers on an API model; RULINGS R1 said in advance
  that plain calls could land under half on wall time. The numbers are from a 4-thread
  CPU writing about 6 tokens a second; a hosted model would be faster and differently sized.
- It is one run per model. The medians of 6 LOW and 6 MEDIUM tasks move with one task.
- It does not re-seed the estimate. That needs a hosted run ([hf], waiting on HF_TOKEN)
  and a founder decision to write a new locked estimate before the next scored run.

Decision owner
Whether a low-side miss blocks M2 is the founder's call. Recommendation: record S2 as
missed, keep the protocol finding, and write estimate v2 from these medians before the
hosted run, not after it.

----------------------------------------------------------------------------------------
Earlier memo, kept as written:

S2 MEMO: Coordination cost
Date: 25 August 2026
Spike: S2
Result: NOT SCORED against the bar. Protocols held.

Question
What does a 4 worker org cost per task?

Bar
Median within 2x of the pre-run estimate. Protocols stay structured.

Estimate
None was written before run 002. The brief requires the estimate first.
Without it the 2x bar cannot be passed or failed. That is a miss of process,
not a measured cost.

What run 002 did measure
- Protocol objects sent: 8
- Verified tasks: 2 (t_001, t_002)
- Objects per verified task: 4.0
- Every coordination message was a protocol object (Handoff, Blocker, Approval).
- No free chat between workers.
- Wall seconds per scripted turn: about 0.02s. That is not model latency.
- Tokens in / tokens out: not measured. No model command.

Table (protocol counts, not tokens)

task     worker    protocol_count  tokens  wall_seconds  retries  founder_touched
t_001    w_eng_a   1 Handoff       n/a     0.023         0        no
t_002    w_eng_b   1 Handoff + 1 Blocker + 1 Handoff     n/a  0.025+0.024  0  no
t_003    w_pm      1 Approval      n/a     0.023         0        yes (int_002)

Did protocols hold?
Yes. Engineer B blocked instead of guessing. PM answered with an object.

Why this is not a pass
The bar is cost within 2x of estimate. There was no estimate, and no token
meter. Structured protocols are necessary and not sufficient.

Requirement before a real S2
Write the estimate. Attach a model. Run at least 12 tasks. Record tokens.
A miss is still a result. Do not start M2 on this memo.
