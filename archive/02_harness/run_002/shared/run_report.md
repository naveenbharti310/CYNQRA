CYNQRA RUN 002 REPORT
Closed: 25 August 2026
Owner: CEO
Verdict: NO-GO on M2

What we tested
Can four workers pursue a human objective through protocol objects,
with the founder only on real decisions, and with verification that
catches bad output before anyone says verified?

The chew toy was an internal candidate tracker. It is not the product.

What still counts from run 001
int_001 confirm objective
int_002 reject and amend stuck (decision_001, approved_edited)
gold_001 elapsed time is not stuck

Run 001 itself is void.

Three numbers
Founder interventions: 3 (confirm, amend stuck, reject HIGH send)
Protocol objects per verified task: 4.0 (8 objects, 2 verified tasks)
Verification catch rate: 0.4 (2 of 5 seeded). Bar 0.8. Not met.

What worked
- Sealed inboxes. Engineer B refused to invent the stage list and raised a Blocker.
- PM cleared the Blocker without the founder.
- MEDIUM meaning of stuck came to the founder. Clock as stuck died.
- HIGH external message stopped. Rejected. Nothing was sent.
- Budget cap paused OPEN work at 100.

What did not work
- Held tests for the current task missed empty name, list completeness, and a spec that redefined stuck as a clock.
- The event log cannot replay a task. It names files, not closed lists, Blocker text, tests, or source.
- No second verifier process. Catch rate is mechanical.
- No off the shelf worker APIs. Turns were sealed scripts.
- S1 has no model command. 0 of 10 baseline is not a spike result.
- S2 has no pre-run estimate and no token meter. The 2x bar cannot be scored.
- S3 bar is 80 percent of at least 10 seeds. This run seeded 5. Catch 0.4.

Golden set
gold_001. Messy: a candidate in applied with no stage change for 8 days is stuck.
Gold: flagged only. Stuck needs a named reason. If the stage already moved, both marks clear.

Breaks that are now engineering requirements
b_001 Seal worker filesystems. Run surface is workers, tape, breaks, numbers.
b_002 Second verifier process. Do not score catch rate from the same operator as the worker.
b_003 M2 worker runtime must be separate processes.
b_004 Never treat a timer as a diagnosis.
b_005 Handoff must carry closed lists. Missing facts become Blockers.
b_006 Protocol objects need protocol_version, created_at, correlation_id.
b_007 Verification must rerun prior tests and lint specs against decided rules.
b_009 Event payloads must carry protocol hashes, closed lists, and test ids.

Go or no go on M2
NO-GO.

Book 4 gates M2 on the run report, golden sets, the break list, founder
interventions, cost, and verification catch rate. Catch rate missed the bar.
S1 is not scored. S2 is not scored. Workers were not off the shelf tools.
G0 has not been held. D-6 and D-17 remain open.

What to do instead of M2
1. Hold G0. Vote the open decisions. Send D-22 to counsel.
2. Attach a model command and run S1. Bar 8 of 10.
3. Write the S2 estimate first, then measure tokens. Do not invent the estimate after.
4. Reseed S3 to 10 defects with a verifier that cannot see the seed file and is not the worker.
5. Fix b_006, b_007, and b_009 in the protocol and event envelope before any runtime build.

Do not start dashboards, design, or M2 on this report.
