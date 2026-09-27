S3 MEMO: Verification quality
Date: 25 August 2026
Spike: S3
Result: BAR MISSED. 0.4 caught. Bar 0.8.

Question
Do the tiers catch bad output, including non code?

Bar
80 percent of seeded defects caught before verified.
Brief asks for at least 10 seeds. Run 002 Day 6 seeded 5. Report that limit.

Method
Seeds sealed in day6/sealed/seeds.json. Verifier process could not read them.
Verifier ran held t_002 tests only. Not a second model. Not founder review.

Seeds
def_001 code. create accepts empty name. Missed. t_001 test was not rerun.
def_002 code. set_stage accepts an unknown stage. Caught. test_unknown_stage FAIL.
def_003 code. create does not start at applied. Caught. test_create_starts_applied ERROR.
def_004 code. list returns only the last candidate. Missed. t_001 test was not rerun.
def_005 non_code. spec_stuck.md defines stuck as a 7 day clock. Missed. No spec lint.

Score
caught_before_verified / seeded = 2 / 5 = 0.4
met_bar = no

Escaped defects
def_001, def_004, def_005

False acceptance: the tainted store would have been VERIFIED if someone looked only at a subset of t_002 tests that still passed (set_stage happy path, closed list constant).
False rejection: none on this seed set.
Rework count: not measured.
Verification latency: under a second. Not informative.

Why the bar was missed
Verification scoped to the current task's tests. Prior acceptance and decided
rules were not in the path. Non code had no checker.

Requirement
Rerun prior task tests. Lint specs against decided rules. Use a verifier that
is not the worker. Seed 10, mark them before scoring. If the bar is missed,
M2 does not start. It is missed. M2 does not start.
