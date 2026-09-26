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
