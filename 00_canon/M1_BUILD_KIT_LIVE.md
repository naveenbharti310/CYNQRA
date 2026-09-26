# M1 Build Kit: Wizard of Oz and Spikes

Live export, 25 August 2026. Working kit, not canon. Nothing here ratifies any decision.
Owner: CEO. Window: weeks 0 to 2.

The code this page refers to is in `02_harness/`. The run records are in `01_history/`.

## Position

Run 002 is closed and audited. Verdict: NO-GO on M2 still holds. Founder interventions
that count: 2. Worker protocol objects per verified task: 3.0. Catch rate 0.4 is
mechanical, sample of five, and is not S3. Run 001 is void.

Project name: internal candidate tracker, test project only.
Start 25 August 2026, end 4 September 2026.
Company company_woz_001. Objective obj_001. Run run_002.

## The confirmed objective

This is the structured form the whole run was pointed at. It is also the shape S1 has to
produce from a messy sentence.

- product: internal candidate tracker
- target customer: founder and two recruiters
- primary outcome: every candidate has a visible stage and stuck candidates are obvious
- business outcome: founder can see who is stuck without asking
- success criteria: a recruiter can create a candidate, set a stage, list all candidates,
  and filter stuck ones
- constraints: no public careers site, one company, no applicant login
- priorities: stage visibility first, then stuck filter

## Wizard of Oz method

The founder plays orchestrator. Off the shelf tools play CTO, PM, Engineer A and
Engineer B. Verification is the founder plus a second model. No fifth worker.

Done when the run report exists, the first golden sets exist, every broken step is in
`breaks.csv`, and founder interventions, cost and verification catch rate are measured.

## The ten day tape, run 002

- Day 1. Objective confirmed. Inherited. Intervention int_001 counts.
- Day 2. Fixed four worker template. Three tasks opened.
- Day 3. First LOW risk work. Engineer A built create and list from the PM handoff. 3 of
  3 tests passed. Task t_001 verified.
- Day 4. First MEDIUM risk work. decision_001 first draft rejected. Amended rule adopted.
  Intervention int_002 counts. Does not ratify D-17.
- Day 5. First cross worker dependency. Engineer B raised a blocker instead of inventing
  the stage list. PM cleared it. The founder was not in this path. Task t_002 verified.
- Day 6. Five defects seeded, including one specification defect. The held t_002 tests
  caught 2 of 5. Catch rate 0.4. Bar 0.8 not met. Mechanical verifier, not a second model.
- Day 7. Budget hit 50, 80, 95, then 100 percent. Open work entered paused.
- Day 8. A HIGH risk external message was stopped. The gate worked. Intervention int_003
  does not count, because the founder never saw the approval.
- Day 9. Export written. Task t_002 replayed from the log. The stage list was not in the
  payload. That is a real defect in the export contract.
- Day 10. Run report written. M2 is NO-GO. S1 not scored. G0 not yet held.

## Spikes

| Spike | Question | Bar | Timebox | Status |
| --- | --- | --- | --- | --- |
| S1 Objective structuring | Can a model fill the Book 1 fields from a messy sentence? | 8 of 10, one retry | 3 days | Harness ready and refuses to score without a model. Never run against a real model |
| S2 Coordination cost | What does a four worker org cost per task? | Median within 2x of the pre-run estimate, protocols stay structured | 4 days | Estimate locked 25 August. Not scored. No token meter available |
| S3 Verification quality | Do the tiers catch bad output, including non code? | 80 percent of seeded defects caught before verified | 4 days | Scored 9 of 10 on the sealed seeds. Mechanical tier only. Second model tier not built |

A failed spike is a successful spike. Write the memo anyway.

## Decision 001: adopted as edited

The first draft was rejected. A seven day clock is not the meaning of stuck.

Adopted rule:

- Flagged means applied or screen, and no movement for seven days. Alarm only.
- Stuck means flagged plus a named reason: waiting_on_recruiter, waiting_on_candidate,
  waiting_on_founder, missing_document, no_owner.
- If the stage already moved, the card leaves both lists at once. If it does not, that is
  a freshness bug, not a new product decision.
- If real life moved and nobody recorded it, that is a missing write, not a refresh bug.

Label: approved_edited. This does not ratify D-17.

This rule is what `kit/contract_checks.py` lints specifications against, which is why the
verifier can catch specification defects and not only code defects.

## Hard rules

- Protocol messages are objects, not free chat.
- Event payloads carry no personal data.
- HIGH risk actions need named founder approval.
- One founder intervention is one action taken, excluding reading.
- Do not start dashboard design unless a break proves the paper protocol cannot be
  followed without a screen. If that happens, write the break.

## G0 results

The founder authorized the packet recommendations on 25 August 2026. Binding text lives in
Book 4. D-6 and D-17 through D-21, and D-23 through D-30, ratified as recommended. D-22
decided as Hybrid. D-7, D-8 and D-9 closed on the recommended options.

M2 does not start. S1 still needs a model.
