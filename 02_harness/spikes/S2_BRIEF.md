# S2: Coordination cost

Question: What does a simulated 4 worker org cost per task in tokens and latency?
Success: cost model lands within 2x of estimate, protocols stay structured.
Timebox: 4 days.
Owner: CTO, with CEO acting until hired.

## What to simulate

Fixed template only: CTO, PM, Engineer A, Engineer B.
Use the protocol templates in /protocols. No free chat between workers.
Run at least 12 tasks across 3 workstreams of the WoZ project.

## What to record per task

task_id, worker, protocol_count, tokens_in, tokens_out, wall_seconds, retries, founder_touched

## Estimate to beat

Write the estimate before the run, not after:
- tokens per LOW risk task
- tokens per MEDIUM risk task
- tokens per protocol message
- wall minutes per task

Pass if the measured median is within 2x of that estimate and every coordination
message used a protocol object.

## Memo

One page. Append to Book 2. Include the estimate, the table, and whether
protocols held. A miss is still a result.
