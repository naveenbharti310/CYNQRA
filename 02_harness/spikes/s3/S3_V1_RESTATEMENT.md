# S3 v1 restatement

Recorded 26 September 2026 by the acting CTO, who owns spike results under Book 4.
Rule three of this project: we void our own results when they are contaminated. This is
that rule applied to our best number.

## What was claimed

S3 at the mechanical tier: 9 of 10 seeded defects caught, bar 0.8 met. STATE_OF_PLAY
listed it first under "what is actually proven".

## What the record shows

1. Same author, same seven minutes. File times inside
   04_prior_builds/Cynqra_M1_Full_25Aug.zip (stored in UTC, shown here in India time):
   seeds.json 22:00, contract_checks.py 22:03, the five tainted fixtures 22:03,
   run_s3.py 22:04, s3_report.json 22:04, all on 25 August. The checks do not open the
   seed file, which is true, but the person writing them had just written it.
2. The non code tier matches the planted sentences, not the defects. The four lint rules
   look for "public careers", "applicant" with "log in", "dashboard" with "success" or
   "pretty", and "stuck" near "7 day". Tested on 26 September with the same four defects
   in other words ("a jobs page on our website where people can apply", "candidates get
   a portal account to track their application", "done when the founder has good
   looking charts for the board meeting", "stuck after one week without movement"):
   0 of 4 caught. A correct spec ("The dashboard lists candidates. Success criteria: a
   recruiter can create, stage, list and filter stuck candidates") was flagged as a
   defect. False rejection was never measured in v1.
3. Ten seeds, nine defects. s3_05 (unknown id does not error) and s3_06 (failing write
   reported as success) are the same line in tainted/store.py: one except clause that
   swallows every error. The probe credited to s3_05 caught it. So the "miss" that
   STATE_OF_PLAY calls the most dangerous gap was partly a mapping artifact, while the
   real gap, no read back and no injected failure, was never tested.
4. The seed mix is not the one S3_BRIEF.md asked for: no broken auth check, no off by
   one, no bad query.

## Ruling

S3 v1 does not count as evidence that verification catches bad work. The file
s3_report.json stays as it was recorded, like run 001. G2 (verification trusted) is open.

What survives: the five generic store probes (empty name, list completeness, starts at
applied, unknown stage, unknown id) are sound contract checks and stay in the kit as
regression checks.

## What changed in the kit

1. Two new probes for "errors must surface": write_persists (a valid write must read
   back) and failure_surfaces (an injected storage failure must raise). On the v1
   fixture failure_surfaces fires and a correct store passes. That is a unit test of the
   probe, not a score. run_s3.py still maps s3_06 to the old probe, and it no longer
   overwrites s3_report.json on a rerun.
2. The spec lint is not extended with more keywords. That would fit the next test the
   same way. Spec defects go to the MEDIUM tier: an independent model review in
   kit/model_review.py, which Book 2 always required and which did not exist.

## What S3 v2 needs before any claim

See spikes/s3v2/SEED_GUIDE.md. Seeds and clean controls written and sealed by someone
who has not read kit/contract_checks.py, kit/verify.py or kit/model_review.py. One
defect per fixture. Clean controls so false rejection is measured. Both tiers run. Same
bar: 80 percent caught before anything is marked verified.
