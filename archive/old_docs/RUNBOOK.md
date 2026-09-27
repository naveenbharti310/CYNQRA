# RUNBOOK

Updated 26 September 2026. Windows users: double click RUN_M1.bat and skip the
commands below. Changes since 25 August are listed in M1_RESTART_26SEP2026.md.

Everything here runs on a plain machine with Python 3 and nothing else. No pip install,
no packages, no database, no server, no Docker. Standard library only. That was a
deliberate choice so a handover could never fail on a broken environment.

Built and tested against Python 3.13. Anything 3.9 or newer should work.

## Setup

```
cd 02_harness
python3 --version
python3 spikes/preflight.py
```

Preflight prints one line per spike: READY, BLOCKED, IN PROG or DONE, and what is
missing. Run it whenever you are unsure where the project stands. It reads the report
files on disk, so it cannot flatter you.

## Give the harness a model

S1 and S2 need to reach a real model. Pick one:

```
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export CYNQRA_S1_MODEL_CMD='your-cli --quiet'
```

Optional model choice. Defaults: claude-sonnet-5 with an Anthropic key,
gpt-4o-mini with an OpenAI key. The old Anthropic default,
claude-sonnet-4-20250514, was retired on 15 June 2026.

```
export CYNQRA_MODEL=claude-sonnet-5
```

Resolution order is command, then OpenAI, then Anthropic. All model access goes through
`spikes/model_adapter.py`. Nothing else in the harness talks to a provider directly, and
nothing should. That mirrors the model registry rule in Book 2, ADR-4.

Token counts from an API are real. Token counts from a shell command are estimated from
character length and are flagged `estimated`. An estimated count is not a valid S2 result.
The runner enforces this with `counts_as_measured_result`.

## S1: can a model structure a messy objective

Bar: 8 of 10, one retry per item.

```
python3 spikes/s1/run_s1.py
```

Ten messy founder sentences in `spikes/s1/corpus.json`, each with a hand written expected
answer. The expected answers were written on 24 August, before anything ran, and the
prompt does not contain them. Scoring requires all seven fields filled and at least four
of them overlapping the expected answer by half its words. Writes `s1_report.json`.

With no model it refuses and exits 2. It does not fall back to filler. If a
model call fails it stops, writes s1_unrun.json and exits 3. Prompt v2 of
26 September replaced v1; the reasons are in spikes/s1/RULINGS.md.

### The no key route

If you have a chat subscription but no API key, S1 can be carried by hand. S1 measures
accuracy, not cost, so a human moving text does not weaken it.

```
python3 spikes/s1/make_paste_pack.py     # writes PASTE_PACK.md
python3 spikes/s1/make_paste_html.py     # writes 03_pages/cynqra-s1-paste-pack.html
```

Ten blocks. New temporary chat per block, paste exactly, save each reply as
`spikes/s1/answers/T01.txt` through `T10.txt`, retries as `T01_retry.txt`. Or
use the browser page, which saves one `s1_answers.json` for the same folder.

```
python3 spikes/s1/score_manual.py
```

Same scorer, same bar, marked `source: manual_paste` with tokens declared unmeasured.
It refuses to score a partial run.

## S2: what a four worker organization costs per task

Bar: measured median within 2x of the estimate locked on 25 August.

```
python3 spikes/s2/run_s2.py
```

Twelve tasks across three workstreams in `spikes/s2/tasks.json`, four workers, risk tiers
per D-27. Coordination happens as protocol objects, never free chat, because free chat is
what makes coordination cost explode. Writes `s2_report.json` and `s2_messages.json`.
The runner was missing from the handover and was written on 26 September. What the bar
means, and what each number measures, is fixed in `spikes/s2/RULINGS.md`.

The estimate is in `spikes/S2_ESTIMATE.md`. Do not edit it after scoring starts. It is
the whole point that it was written first.

S2 cannot be done by hand. It is the cost measurement, so it needs a metered key.

## S3: does verification catch bad work

Bar: 80 percent of seeded defects caught before anything is marked verified.

```
python3 spikes/s3/run_s3.py
```

Ten defects sealed in `spikes/s3/seeds.json` on 25 August at 21:57. Six are code defects,
four are specification defects, because a system that only catches broken code will happily
build the wrong product correctly.

The important design point: the checks in `kit/contract_checks.py` were derived from the
confirmed objective and decision_001, not from reading the seed file. An earlier version
read the seed labels and scored itself, which is cheating, and that is one reason run 001
is void.

Recorded v1 result: 9 of 10, missing `s3_06`. Restated on 26 September: it does not
count as evidence, because the spec checks match the planted sentences rather than the
defects. See `spikes/s3/S3_V1_RESTATEMENT.md`. The next claim comes from S3 v2 with blind
seeds, `spikes/s3v2/SEED_GUIDE.md`.

## Verifier kit

```
python3 kit/test_kit.py
```

Reruns the earlier tests and lints specifications against the adopted definition of stuck.

It reads the real submissions from `run_002/workers/` sitting beside it in this folder, so
it is checking work that actually happened rather than a fixture written for the test. That
also means the folder layout matters: keep `run_002` where it is, next to `kit` and
`spikes`. Move it and the tests fail with a missing file, which is how the dependency was
found in the first place.

## What each result file means

`met_bar` is the only field that decides anything. Everything else is context.
`counts_as_measured_result` false means the numbers are indicative and must not be quoted
as the spike result. `source: manual_paste` means a human was the transport.

## The gate you must not walk through casually

M2 does not start until S1 and S2 have real scores and someone writes the go or no go
in Book 4. S3 passing on its own is not enough, and S3 has only passed at the mechanical
tier. Book 2 wants a second model for MEDIUM risk and a human for HIGH risk, and neither
of those tiers has been built or tested.
