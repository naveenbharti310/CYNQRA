# Live reports

**What:** reports of earlier runs on real AI models. **Why** they are kept: they are the evidence behind the
real-model results in docs/3_STATUS_AND_ROADMAP.md. **How:** `live_check.py` writes one JSON and one Markdown report
per run here. Run folders
(`run_*`) are scratch and ignored by git.

## 26 September 2026, 17:05: PASS, command model (not a measured API result)

Objective, new and never scripted: a bakery's internal page to log custom cake orders with
a pickup date, see what is due in the next few days, and mark orders paid and picked up.

Who answered: Claude, the model running the acting CTO session, reached through
`tests/model_bridge.py` as `CYNQRA_S1_MODEL_CMD`. Every prompt the engine built was
answered from that prompt alone, as the worker it addressed, without running the code
first. All 10 prompts and replies are in `live_20260926_170520_bridge/`.

What it proves: the live path works end to end with real model output on an objective the
demo never saw. Objective structuring, planning, assignment, a product rule decided by the
founder, two code tasks, verification with the delivery contract, merge, deploy and
acceptance. All six tasks verified first pass, the product went live, its 14 tests passed
again when rerun from main, and a Chromium check of the delivered page logged orders,
showed an overdue order, ticked Paid and showed the validation error
(`live_20260926_170520_product.png`).

What it found: the planner was shown an empty objective. The engine passed the whole
objective record where the structured fields belong, so every field but constraints was
blank. The scripted demo ignores its inputs and never noticed. Fixed, with a regression test
(`test_real_model_paths.PromptContentTests`).

What it does not prove: anything about the HTTPS API path, token counts or cost. Tokens are
estimated from characters and `counts_as_measured_result` is false. The API wire format is
covered by `tests/test_adapter.py` against a local server speaking the Anthropic and OpenAI
formats. A measured run needs `ANTHROPIC_API_KEY`: `python poc/live_check.py`, or
RUN_M1.bat item 7. It is not gate evidence for S1, S2 or S3.

## 26 September 2026, 17:50: PASS through the live mode UI, command model

The same kind of run, driven through the real screens instead of the engine:
`run_poc.py` in live mode, Chromium clicking what a founder clicks (`tests/e2e/live_walk.js`),
and Claude answering every worker prompt through the bridge. New objective: a six person
dog walking company that assigns daily walks to walkers, who mark them done with a note.

What it exercised, in order: Live chosen in the wizard; the objective structured; the plan
rejected once from the UI and the founder's note reaching the planner, which answered with a
different plan; a product rule approved from the Decisions screen; a rehearsed provider
outage on t_03's assignment, shown as Stopped with "Try the same step again", clicked, and
the same step asked again; two code tasks, merge, deploy and acceptance approved from the
UI; the live product opened; the audit replay complete, 8 of 8 facts. Every task verified
first pass. `ui_20260926_dogwalks/ui_walk_result.json` has the driver's own record, and all
13 prompts and replies are in `ui_20260926_dogwalks/bridge/` (prompt 6 is the rehearsed
outage and has no reply).

Then the delivered product was used in Chromium: two walkers added, three walks assigned,
Maya saw only her two walks earliest first, marked one done with a note, an empty note was
refused with the spec's message, and her name was remembered after a reload
(`12_product_owner.png`, `13_product_walker.png`).

What the attempt found before it could pass, all fixed with checks that fail on the old code:

1. Choosing Live in the UI never worked: the company was always created in demo mode.
   The first attempt ran entirely on the scripted demo and was thrown away.
2. Founder edits to objective fields and the budget cap were discarded on Confirm.
3. The screen froze and the kill switch could not be pressed while a model was answering.
4. Every repaint replayed the fade in of every card, so the screen flickered throughout a
   run; `05_stopped.png` was taken before this fix and shows it.

Same limits as the first run: tokens estimated, no cost, not a measured API result.
