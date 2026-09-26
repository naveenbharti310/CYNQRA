# Cynqra POC test report

Run on 26 September 2026 by the acting CTO. Linux, Python 3.11.15, Node 22 with
Playwright and Chromium. The full suite was also run on Python 3.10 with the same result,
which is the floor RUN_POC.bat checks for.

## Result

95 tests, 95 passed, 0 failed, 0 skipped. Run time about 80 seconds.

| Module | Tests | What it proves |
| --- | --- | --- |
| test_core | 21 | Append only events (the database refuses UPDATE and DELETE), the D-18 envelope, personal data keys refused (D-22), content addressed objects, policy for every tier and role (D-17, D-21, D-27, D-28), kill switch and breaker in policy, protocol objects that content cannot reroute, the test runner, the document lint, workers never see keys |
| test_journey | 17 | The whole demo run end to end through the engine: accepted, live product answering /health, six tasks verified, founder sees exactly four proposals and six interventions in total, twelve fields per task, Blocker cleared without the founder, defect caught before verified, prohibited email denied, every task replays complete, no names in events, ten deployment stages, six category export, transition record |
| test_controls | 21 | Gateway keeps writes in the workspace and audits every call, decision cards carry every field, edit, reject with reason, request evidence, D-29 escalation budget with SEV-1 bypass, budget warnings at 50, 80, 95 and the breaker at 100, kill switch mid run, objective change pauses the run (D-30), a run survives a restart |
| test_failure_paths | 13 | Three invalid worker replies escalate; the founder retries or stops; code that fails verification three times escalates with the failing test named and never integrates; a fixed retry recovers; a write outside the workspace is refused and reworked; a failing release candidate is not merged; a failed live smoke test rolls back and a retry goes live; rejected delivery is recorded; a refused budget raise stops the run |
| test_adapter | 8 | Live mode over the real Anthropic Messages and OpenAI Chat Completions wire formats against a local fake provider: headers, body, measured tokens, the whole journey to accepted, the retired claude-sonnet-4-20250514 fails loudly, provider outage stops the run, one JSON retry, prose twice is refused |
| test_live_and_deploy | 10 | Live mode needs a model and writes nothing without one, the command path end to end, a model error invents nothing, the platform owns the plan rules and risk tiers, the POC adapter is byte for byte the spike adapter, the deployment service with rollback, the demo product's own 16 tests |
| test_server | 5 | HTTP API: UI served, path traversal blocked, full journey over HTTP, bad requests are 400 not crashes, auto run and archive on reset; and the browser test, the whole journey clicked through the real UI in Chromium |

The 02_harness spike tests (15) also pass unchanged.

## Coverage

Statement coverage of the platform code, measured with coverage.py over the full suite:

| File | Statements | Missed | Cover |
| --- | --- | --- | --- |
| cynqra/db.py | 89 | 1 | 99% |
| cynqra/deploy.py | 118 | 7 | 94% |
| cynqra/engine.py | 804 | 22 | 97% |
| cynqra/intelligence.py | 166 | 8 | 95% |
| cynqra/model_adapter.py | 65 | 3 | 95% |
| cynqra/policy.py | 43 | 2 | 95% |
| cynqra/protocol.py | 24 | 0 | 100% |
| cynqra/server.py | 136 | 7 | 95% |
| cynqra/verification.py | 55 | 3 | 95% |
| Total | 1500 | 53 | 96% |

The product the demo organization builds (store.py and app.py) is covered 93% by its own
16 tests. The lines left uncovered are defensive branches: a smoke check that times out,
an unreadable smoke.json, a gateway call for an action with no tool implementation.

## Unrun, stated plainly

Unrun is not pass and not fail.

1. A run against a real Claude or OpenAI model. There is no API key in this environment.
   The same code path is proven against the exact wire formats. To run it: set
   ANTHROPIC_API_KEY, start the POC, choose Live.
2. A double click of RUN_POC.bat on Windows. The launcher was written and checked by
   reading; the Python it starts is the same code tested here.

## Bugs found and fixed while testing

1. RUN_M1.bat redirected to /dev/null, which does not exist on Windows, so it always
   reported that Python was missing. Now it redirects to nul. RUN_POC.bat uses the same
   fix and also checks for Python 3.10 or newer.
2. An intelligence source passed to the engine was dropped when the company was created.
   It now survives, which is what let the failure path tests inject faulty workers.
3. Rejecting delivery left no trace in the audit trail. It now records
   transition.rejected and keeps the product live.
4. The audit table cut the time column short. Widened.

## 26 September, second pass: before the first real model call

Checked the adapter against the current Messages API reference rather than the fake
provider, which had accepted anything. Three defects would have stopped or corrupted the
first live run:

1. claude-sonnet-5, the default, rejects temperature with HTTP 400. The adapter sent
   temperature 0 on every call, so every live POC, S1 and S2 call would have failed. A test
   asserted temperature 0, which pinned the bug in place. temperature is no longer sent to
   Anthropic, and the fake provider now returns 400 if it is, as the real API does.
2. Sonnet 5 thinks by default and thinking counts against max_tokens. S1's 1500 token
   limit could be spent on thinking. Anthropic calls now get at least 16000 tokens of room.
3. stop_reason was never read. A truncated reply or a refusal now raises and is an unrun
   call, never a short answer. OpenAI finish_reason length is treated the same way.

Also: transient 429, 5xx and 529 overloads are retried twice with backoff instead of
stopping the run; live mode starts at a 600 unit budget because one unit is 1000 real
tokens; and poc/live_check.py is the real model test, reachable from RUN_M1.bat item 7.

102 POC tests pass (7 new), 15 spike tests and 3 kit tests pass. The real model run itself
is still unrun here: this environment has no API key. Its report lands in poc/live_reports.

## 26 September, third pass: end to end audit and a real model run

Read every POC module against what a real model sends, not what the scripted demo sends.
Fourteen defects, all fixed with tests in tests/test_real_model_paths.py (16 tests):

1. The planner was shown an empty objective: the whole record was passed where the
   structured fields belong. Found by the real model run below; the demo ignores its inputs.
2. Task ids from the model became URL and decision ids; an id like T1 or task-1 made its
   decisions impossible to approve. Plans are renumbered t_01 onward, dependencies remapped,
   budgets coerced, and a refused plan is retried once with the reason.
3. A reply with no files stopped the whole run as if the provider had failed. It is now a
   protocol error: rework, then escalation.
4. Refused writes looped without end. They escalate after three attempts.
5. A bad assignment or Blocker answer sent the task to rework with no handoff. It now
   retries the same step, and an approved escalation returns to the step that failed.
6. Files in subfolders were written but never verified or integrated.
7. An app that broke the delivery contract passed its own tests and failed only at deploy,
   where no worker could fix it. Code tasks that write app.py are now started during
   verification: /health and / must answer, and the app's own output goes into the feedback.
8. The delivery contract never told the model about GET /, starting the server only under
   __main__, DATA_FILE, or where tests live.
9. Rework showed the worker only the failure, not its own previous files; code tasks now
   also see the repository file list.
10. A model or network error left the run dead. Try the same step again resumes it.
11. A planning failure left a confirmed objective with no plan and no way back.
12. The budget breaker tripping mid write was counted against the worker.
13. Unexpected errors dropped the HTTP connection instead of returning a message.
14. Tests with docstrings were missing from the recorded test ids.

Results: 118 POC tests pass (16 new in this pass), 15 spike tests and 3 kit tests pass.

Real model run: PASS on a new objective, a bakery order tracker, with Claude answering every
worker prompt through tests/model_bridge.py. Six of six tasks verified first pass, live,
product tests pass on rerun, and the delivered page works in Chromium. Tokens are estimated,
so it is not a measured API result. Details in live_reports/README.md.
