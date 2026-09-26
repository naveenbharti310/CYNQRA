# S3: Verification quality

Question: Does tiered verification catch bad output, including non code?
Success: at least 80 percent of seeded defects caught before verified.
Timebox: 4 days.
Owner: CTO, with CEO acting until hired.

## Tiers

LOW: automated checks (build and tests).
MEDIUM: independent second model review. Until D-17 is decided, also founder review.
HIGH: founder approval. Always.

## Seed set

Seed at least 10 defects before anyone verifies:
- 6 code defects (failing test, bad query, broken auth check, off by one, missing validation, silent exception)
- 4 non code defects (wrong acceptance criteria, missing constraint, bad user facing copy, spec that contradicts the objective)

Mark each seed before the run. Do not add seeds after scoring starts.

## Scoring

caught_before_verified / seeded >= 0.80

Also record: false acceptance, false rejection, rework count, verification latency.
These supporting measures do not replace the 80 percent bar.

## Memo

One page. Append to Book 2. List every escaped defect. If the bar is missed,
M2 does not start.
