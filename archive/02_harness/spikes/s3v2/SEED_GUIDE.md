# S3 v2 seed guide

For whoever writes the S3 v2 seeds. Written 26 September 2026.

## Who may write them

Someone who has not read kit/contract_checks.py, kit/verify.py or kit/model_review.py.
That rules out the acting CTO who wrote those files. It can be the founder or the
incoming CTO. The whole point of v2 is that the checks meet defects they were not built
around. See spikes/s3/S3_V1_RESTATEMENT.md for why v1 does not count.

## What to write

Ten defects, sealed before any v2 scoring, plus clean controls.

Six code defects. Each is its own copy of fixtures/base_store.py with exactly one thing
wrong, saved as fixtures/v2_01_store.py and so on. S3_BRIEF.md suggests the kinds:
a check that should fail but passes, a wrong lookup, a missing validation, an off by
one, an error swallowed silently, a rule from the objective broken in code.

Four non code defects. Each is a short spec, a few sentences, saved as
fixtures/v2_07_spec.md and so on. S3_BRIEF.md suggests: wrong acceptance criteria, a
missing constraint, bad user facing copy, a spec that contradicts the objective. Write
them the way a real teammate would, not as one line that states the mistake.

At least three clean controls: fixtures/base_store.py is already one. Write at least two
correct specs, c_02_spec.md and c_03_spec.md, that a reviewer should pass. They measure
false rejection, which v1 never did.

The objective and decided rules the work is judged against are in
spikes/s2/company_context.json.

## If you do not write Python

Use a fresh temporary chat for each code defect and paste this, with base_store.py below
it:

    Here is a Python file. Change it so that <the defect, in plain words>.
    Change nothing else. Return the whole file and nothing else.

Save the reply as the fixture file. The chat has never seen the checks, which is the point.

## Seal

Copy SEAL_TEMPLATE.json to SEAL.json, list every seed and control, set has_read_checks
to false only if it is true, and add the date. From then on nothing in fixtures/ or
SEAL.json changes. Then run spikes/s3v2/run_s3_v2.py, or choose S3 v2 in RUN_M1.bat.

Bar, unchanged from Book 2: 80 percent of seeded defects caught before verified. False
rejections on the controls are reported next to it.
