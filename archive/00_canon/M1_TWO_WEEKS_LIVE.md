# M1 two weeks: 25 August to 8 September 2026

Live export, 25 August 2026. Owner: CEO.
This is Book 4 M1 de-risk. It is not a runtime build.

M2 does not start. No dashboards. No design.

## Locked today

- S3 seed set of ten, sealed 25 August at 21:57. Do not edit after scoring starts.
- S3 mechanical score: 9 of 10. Bar 0.8 met. Not a second model. Memo written.
- S2 estimate dated 25 August. Do not edit after scoring starts.
- The verifier kit reruns prior tests and lints specifications against decision_001.
- D-22 Hybrid is decided. Counsel still confirms erasure duties.

## The 25 August scare, and what it was worth

For part of the evening the working environment showed only four files, and the loss was
reported as real. That report was wrong, and the correction matters more than the scare.
The environment was showing an incomplete view of itself. The full tree came back: 146
files, run 002 in full, the G0 results, the kit, the sealed S3 seeds, and the original S1
corpus with its original wording. Nothing was lost and nothing had to be rewritten.

Two things came out of it that are worth keeping.

First, a real bug, found only because the scare forced a line by line read of the S1
runner. It was not using the shared model adapter. It looked for a shell command and
nothing else. An API key on its own would have produced filler output, and the report
would have called it a model result. That is the same failure that voided run 001, sitting
inside the harness. Now fixed: S1 goes through the adapter, and with no model it refuses
to score rather than print a number.

Second, a way to run S1 with a chat subscription and no API key. S1 measures accuracy, not
cost, so a person can carry the text by hand without weakening the result. Ten items, ten
fresh chats, replies saved as files, scored by the same scorer against the same bar of 8
of 10. Rules are in the paste pack: new chat each time, paste exactly, never tidy a reply.
S2 cannot be done this way, because S2 is the cost measurement.

Standing rule either way: every scored run exports a zip the same day, and from the first
engineer hire the harness, seeds, estimates and event logs live in a git repository.

## Calendar

| When | Work | Blocked on |
| --- | --- | --- |
| Deferred | Send D-22 Hybrid to counsel | No lawyer retained. Moved to a gate before the first paying company |
| Days 1 to 3 | S1 model pass. Bar 8 of 10 | A model, by key or by hand |
| Days 1 to 4 | S2 scored against the locked estimate | A metered API key |
| Days 1 to 4 | S3 on the sealed ten seeds | Done at the mechanical tier. Second model tier needs building |
| Days 10 to 14 | Three memos. Keep or lift the M2 no-go | The three spike results |

## Do not do

Runtime. Dashboards. Designer. Pricing. Brand. Cross-tenant learning.

## Needed from the founder

1. S1 by hand using the paste pack, since there is no API key. Ten chats, about an hour.
2. For S2, an API key with a token meter. There is no hand carried version of a cost test.
3. The founding engineer or CTO search. Everything after M1 assumes a second person with
   a machine.

D-22 no longer sits here. There is no lawyer yet, and hiring one to review event log
design before a single paying company exists is early. The draft is written and waits at
the gate.

## Note added at handover

Items 1 and 2 above both become simple once a CTO exists, because both need a machine
that persists and a key that can be held safely. That is the real reason this two week
plan has been waiting.
