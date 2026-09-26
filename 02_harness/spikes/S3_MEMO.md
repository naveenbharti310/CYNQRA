S3 MEMO: Verification quality
Date: 25 August 2026
Spike: S3
Result: BAR MET on the mechanical contract. 9 of 10. Not a second model.

Question
Do the tiers catch bad output, including non code?

Bar
80 percent of 10 seeded defects caught before verified.

Method
Seeds sealed in spikes/s3/seeds.json on 25 August before scoring.
Checks came from the confirmed objective and decision_001, not from reading the seed file at check time.
Store probes: empty name, list completeness, starts applied, unknown stage, unknown id, valid write.
Spec lint: stuck-as-clock, public careers site, dashboard as success, applicant login.
Not a second model. Not founder review.

Score
caught 9 / 10 = 0.9
met_bar = yes (mechanical only)

Caught
s3_01 empty name
s3_02 unknown stage
s3_03 create not applied
s3_04 list only last
s3_05 unknown id
s3_07 stuck as clock
s3_08 public careers site
s3_09 dashboard as success
s3_10 applicant login

Missed
s3_06 failing write swallowed as success. The unknown-id path was already caught as s3_05. A valid write still returned, so the silent-success probe did not fire a second time.

What this is not
This is not S3 as Book 2 wrote it. Book 2 wants LOW automated, MEDIUM second model, HIGH founder. This memo is the automated plus spec lint tier only.

M2
Do not start. S1 is not scored. S2 is not scored. A mechanical 0.9 does not replace those.
