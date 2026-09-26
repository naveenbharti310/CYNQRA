# Live reports

`live_check.py` writes one JSON and one Markdown report per run here. Run folders
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
