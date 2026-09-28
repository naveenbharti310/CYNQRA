# M1 restart

26 September 2026. Written at the founder's instruction. Naveen Bharti remains the founder and the only person who ratifies Book 4.
This file supersedes STATE_OF_PLAY.md, which stays as the 25 August record.

## Where Cynqra stands

Still inside M1. M2 is NO-GO, and that verdict stands. M1 was planned to close on
8 September and is 18 days late. The cause has not changed since the handover: S1 and S2
need a model and a machine, and the plan waited for a CTO hire that has not happened.

A full read of the handover, all 191 files, plus a run of every script, found that the
harness was not ready in the way the handover said. Four defects would have produced
wrong numbers on the first real run. They are fixed, tested and committed. One result the
handover called proven does not hold up and has been restated.

## Scorecard today

| Item | State | Next |
| --- | --- | --- |
| S1 objective structuring, bar 8 of 10 | Unrun. Harness fixed and tested. | A key, or ten chats by hand. |
| S2 coordination cost, bar in s2/RULINGS.md | Unrun. Runner built, it was missing. | A spend capped API key. |
| S3 verification, bar 0.8 | v1 restated, does not count. Both tiers now built. | Ten blind seeds, then one run. |
| Run 002 | Closed NO-GO, audited. Scripts now refuse to rerun. | Nothing. It is a record. |
| G0 decisions | 30 closed, with one record conflict on D-22, D-7, D-8, D-9. | One line from the founder. |
| Canon | Books 1 to 4 in the handover are v0.4. Ratified rows cite v0.5 sections. | Recover the v1.2 build. |
| M2 | NO-GO. | Opens only on real S1 and S2 scores and a written go. |
| POC (D-36) | Audited end to end, 14 defects fixed. 118 tests pass, browser test included. A real Claude model took a new objective to a live, accepted product (command model, tokens estimated; poc/live_reports). Not gate evidence. | A measured API run: RUN_M1.bat item 7 with the S1 key. |

## What was wrong, found by running it

1. **S1 could report a failure it never earned.** Any model error, including a bad key,
   became empty text, which was scored and written as "0 of 10, this is the S1 result".
   Reproduced with an invalid Anthropic key. Fixed: the run stops and is marked unrun.
2. **The first real S1 run would have hit that bug.** The adapter's Anthropic default,
   claude-sonnet-4-20250514, was retired on 15 June 2026. Fixed: default is
   claude-sonnet-5.
3. **S1's prompt and scorer contradicted each other.** The prompt said to leave unstated
   fields empty. The scorer fails any empty field. No objective in the corpus states a
   priority, so a model that obeyed scored 0 of 10, reproduced. Fixed with prompt v2. The
   corpus, expected answers, scorer and bar are unchanged. Recorded in s1/RULINGS.md
   before any run.
4. **The S2 runner did not exist.** The runbook's "one command" pointed at a missing file.
   The only runner found, inside 04_prior_builds, made one model call per task and never
   passed work between workers, so it could not measure coordination. run_s2.py was
   written fresh: PM handoffs, Blockers and answers, independent MEDIUM review, every
   message a stamped protocol object.
5. **S3 v1 does not count.** The seeds, the checks and the fixtures were written by one
   operator within seven minutes. The four spec checks match the four planted sentences:
   the same defects reworded were caught 0 of 4 times, and a correct spec was flagged. Two
   of the ten seeds are the same line of code. Restated in s3/S3_V1_RESTATEMENT.md,
   record kept, G2 open. This is rule three applied to our best number.
6. **Rerunning run 002 would have destroyed it.** runner.py wipes the worker folders the
   kit tests read, rewrites the audited numbers, then crashes on a /data path from the old
   sandbox. The three run 002 scripts now refuse to run.
7. **The canon cites text that is not in the handover.** Ten Canon CI findings are listed
   in 00_canon/BOOK_4_PROPOSED_26SEP.md. The biggest: D-19 and D-23 to D-28 point at v0.5
   sections that the v0.4 PDFs do not have, so the claim that v0.5 was wording only is
   wrong.

All fixes are covered by 15 new tests in 02_harness/spikes/test_spikes.py. The three
original kit tests still pass. Nothing calls a real model.

## Decisions by seat

### CEO

1. Taken: M1 is unblocked by the founder, not by the hire. Proposed as D-33 for the log.
   Cost of running S1 and S2 once: under ten dollars.
2. Taken: the CTO search stays hire number one. The spikes can run without an engineer.
   M2 cannot be built without one, whatever S1 and S2 show.
3. Needs the founder: ratify D-31 to D-34, confirm the D-22 record, recover the v1.2 build.

### CTO

1. Taken: the four harness fixes above, the S2 runner, the model review tier
   (kit/model_review.py) and the S3 v2 runner.
2. Taken: S3 v1 restated (D-35 in the proposals file).
3. Taken: implementation choices for the M2 set, recorded in
   00_canon/IMPLEMENTATION_DECISIONS_LIVE.md. Postgres with an insert only events table,
   durable workflows as a library on that Postgres, one gVisor container per worker session
   with an egress allowlist, a Tool Gateway in the addendum's exact order, policy rows with
   default DENY, secrets only in the Gateway. The hired CTO can replace any of them in week
   one with a written reason.
4. Taken: the meaning of the S2 bar, fixed before any data. Every estimate line must land
   between half and double. Stated risk: the wall time lines assume tool loops and may fail
   low. The bar does not move if they do.

### CPO

1. Needs the founder: D-31, the Objective System proposes a complete objective and flags
   what it inferred. That is what Book 1 already describes, and it is the product basis for
   S1 prompt v2. Ratify before S1 runs.
2. Unchanged: CRUD web apps as the first category (D-6). The candidate tracker is a test
   fixture. Planning interaction mode (Book 1 open question 3) is not needed until M3.

### COO

1. Spend: one Anthropic API key on ten dollars of prepaid credit, which is a hard cap by
   itself. The S2 runner also stops at 600,000 tokens, about three dollars.
2. Key hygiene: the launcher takes the key in a hidden prompt and never writes it down. If
   the key is ever pasted into a chat, revoke it after the run.
3. Durability: the project is now a git repository, first commit exactly as handed over.
   Every scored run exports a zip the same day; the launcher does it automatically.
4. Counsel: unchanged. D-22 waits at the gate before the first paying company. It blocks
   nothing in M1 or M2.
5. Cost model v0: spikes/s2/cost_model_v0.py turns a measured S2 report into dollars per
   task and per run for the model inference line of Book 3. The other three lines stay
   tracked, not measured, until M2 has a runtime.

## Plan, 26 September to 10 October

| When | Who | What | Done when |
| --- | --- | --- | --- |
| Sat 26 Sep | Acting officers | Harness fixed, S2 built, tests, git, this memo | Done |
| By Tue 29 Sep | Founder | Ratify D-31 to D-34, confirm the D-22 line | Rows marked in Book 4 |
| By Tue 29 Sep | Founder | Get an Anthropic key on ten dollars of prepaid credit. Run S1 and S2, either by double clicking RUN_M1.bat or by giving the key to the acting CTO for one session | s1_report.json and s2_report.json exist |
| Within a day of results | Acting CTO | S1 memo, S2 memo, cost model v0, go or no go recommendation for M2 | Three files, one recommendation |
| Same day | Founder | Write the go or no go in Book 4 | One dated row |
| By Sat 3 Oct | Founder or hired CTO | Write and seal ten S3 v2 seeds and three clean controls, per s3v2/SEED_GUIDE.md | SEAL.json exists |
| After the seal | Acting CTO | Run S3 v2, write the memo | s3v2_report.json |
| By Sat 3 Oct | Founder | Put Cynqra_Production_Build_Edition_v1.2.zip and G0_Ratification_Packet_v1.2.pdf into the Cynqra latest_10 folder, or connect Notion | Canon at v0.5 again |
| Ongoing | Founder | CTO search | An offer out |

## What happens after the scores

1. S1 at 8 or more and S2 inside the bar: recommend GO on M2, to start when an engineer
   exists. First build step is G1, runtime safe, on the implementation choices above.
   G2 must pass through S3 v2 before M2's exit demo, because that demo claims a verified
   output.
2. S1 below 8: a real finding. A model cannot reliably structure a messy objective in one
   pass, so the objective wizard has to ask the founder more. That is a CPO redesign of the
   entry point, not a lower bar.
3. S2 outside the bar: cost model v0 is wrong by more than double. Write a new estimate,
   lock it, run S2 again. The old estimate is not edited.
4. Any unrun result, meaning an error, no key or a wiring test, decides nothing.

## The POC, added 26 September evening (D-36)

The founder asked for an end to end working POC with screen mockups, tested code and an
animated demo video. It is in poc/ and it is a demonstration only. S1, S2 and S3 v2 still
decide M2, and nothing in poc/ is quoted as evidence for them.

What it does: one founder sentence becomes a seven field objective, the fixed four worker
organization plans six tasks, workers act only through the Tool Gateway, verification
catches a seeded defect, the PM clears a Blocker, policy denies a prohibited email, and a
real candidate tracker is built, tested, deployed to a local URL and exported. The
founder makes six decisions in total.

Where to look: poc/README.md to run it, poc/POC_SPEC.md for what it enforces and the
acceptance tests A1 to A16, poc/TEST_REPORT.md for results, poc/design/mockups for the
screens (also on the design canvas), Cynqra_POC_demo.mp4 next to this folder for the video, poc/demo for how it is made.

Unrun, not passed: a live run against a real model, and a double click of RUN_POC.bat on
Windows. RUN_M1.bat had a Windows bug that made it report Python missing every time; it
is fixed in this build.

## What the founder needs to do, all of it

1. Ratify or amend D-31, D-32, D-33 and D-34, and add the D-22 line
   (00_canon/BOOK_4_PROPOSED_26SEP.md). Ten minutes.
2. Create one Anthropic API key on ten dollars of prepaid credit. Then either double click
   RUN_M1.bat (it needs Python, and opens the Python download page if Python is
   missing), or give the key to the acting CTO and revoke it afterwards. Thirty minutes.
3. Drop the v1.2 zip and the G0 packet into the Cynqra latest_10 folder, or connect Notion.
   Five minutes.
4. Decide who writes the S3 v2 seeds: yourself this week, or the CTO hire later. It cannot
   be whoever wrote the checks.

## Where things are

| File | What it is |
| --- | --- |
| RUN_M1.bat | Double click. Runs everything above on Windows. |
| RUN_POC.bat | Double click. Starts the POC and opens it in the browser. |
| poc/README.md | What the POC is, how to run and test it, its limits |
| Cynqra_POC_demo.mp4, next to this folder | The product demo video, 3 minutes 36 seconds |
| 00_canon/BOOK_4_PROPOSED_26SEP.md | Rows to vote, the D-22 conflict, Canon CI findings |
| 00_canon/IMPLEMENTATION_DECISIONS_LIVE.md | CTO technology choices for M2 |
| 02_harness/spikes/s1/RULINGS.md | Why S1 changed before its first run |
| 02_harness/spikes/s2/RULINGS.md | What the S2 bar and numbers mean |
| 02_harness/spikes/s3/S3_V1_RESTATEMENT.md | Why S3 v1 does not count |
| 02_harness/spikes/s3v2/SEED_GUIDE.md | How to write the blind S3 seeds |
| 03_pages/cynqra-s1-paste-pack.html | S1 by hand, with reply boxes and a save button |
| cynqra.bundle, next to this folder | The full git history. `git clone cynqra.bundle` restores it anywhere. |
