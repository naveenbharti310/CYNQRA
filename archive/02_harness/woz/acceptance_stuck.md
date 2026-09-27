# Acceptance check: flagged versus stuck

Task: t_003
Owner: PM
Risk: MEDIUM
Status: adopted as amended by founder direction on 24 August 2026

Supersedes the first draft of decision_001, which treated the 7 day clock
as the meaning of stuck. That draft is rejected.

## Split the problem

1. Flagged. Stage is applied or screen, and last_moved_at is 7 days old or
   older. This is only an alarm. It does not say what went wrong.
2. Stuck. The card is flagged AND a named reason exists. Allowed reasons:
   waiting_on_recruiter, waiting_on_candidate, waiting_on_founder,
   missing_document, no_owner.
3. Freshness. If the stage has already moved past applied or screen, the
   card cannot appear on flagged or stuck. That is a display and store
   invariant. It is not a new product decision.
4. Missing write. If real life has moved on but nobody recorded the new
   stage, the tracker will still flag the old card. That is not a refresh
   bug. That is an unrecorded handoff.

## What the product must show

- A recruiter can list all candidates.
- A recruiter can list flagged cards. Flagged is not the same as stuck.
- A recruiter can list stuck cards, each with a reason.
- Setting a reason on a flagged card makes it stuck.
- Moving a card to interview or later clears the reason and removes it
  from both lists immediately.
- The 7 day window only starts the alarm. Changing the window later is a
  new decision.

## What this does not do

- It does not send mail.
- It does not auto reject.
- It does not invent a reason from the clock.
