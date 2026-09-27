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

## 26 September, fourth pass: live mode through the real UI

Driving the live mode UI in Chromium with a real model found four defects the demo browser
test could not, because it never chose Live, never edited a field and its model answers
instantly:

1. Choosing Live never worked. Every button handler repainted before reading its inputs,
   and the repaint rebuilt the mode radios with Demo checked.
2. For the same reason, founder edits to the objective fields and the budget cap were reset
   before Confirm sent them.
3. A step holds the engine lock through its model call, and the state read and kill switch
   waited on it: the screen froze and the kill switch was dead while a model answered. Both
   now run without the lock; an answer that lands after the kill switch is discarded without
   counting against the worker.
4. Every repaint replayed every card's fade in, so the screen flickered through a run.

The browser test now edits a field and the budget cap and checks the server kept them, and
checks a repaint does not replay the animation; both fail on the old UI.
test_real_model_paths.SlowModelTests covers 3 and fails on the old engine.
tests/e2e/live_walk.js drives live mode through the UI with any model.

Results: 119 POC tests pass, 15 spike tests and 3 kit tests pass. Live UI run: PASS, see
live_reports/README.md.

## 26 September, fifth pass: laptops, open models, real agents

The POC now runs on a laptop with an open-weight model through Ollama, chosen by the research
in research/local_open_models_2026-09.md: qwen3.6:35b on 32 GB and more, qwen3.5:9b below.

- model_adapter: an Ollama provider on the native /api/chat with num_ctx, num_predict, a JSON
  schema per call, think, temperature 0 and seed, shift and truncate false, keep_alive; real
  token counts; clear errors for a stopped server, a missing model, an overlong prompt and a
  cut-off reply. An OpenAI-compatible path for LM Studio and llama-server with json_schema.
- Engineers are agents: in live mode they run their own tests and start their app through the
  gateway, read the failures and syntax errors, and fix them (up to two rounds) before
  independent verification.
- Code comes back as plain file blocks after a small JSON header, because long code escaped
  inside JSON is where local models fail (Ollama #18094).
- cynqra_cli.py: setup, doctor (with --full), run (founder decisions in the terminal, or --yes),
  bench (a head-to-head on Cynqra's own tasks) and ui. install.sh, install.ps1, INSTALL.bat,
  CYNQRA.bat and ./cynqra.

Results: 140 POC tests pass (20 new, against a fake Ollama server that speaks the native API),
15 spike and 3 kit tests pass. install.sh ran end to end here against that fake server with a
stub ollama command; install.ps1 could not be run here (no PowerShell).

Unrun: a real open model. This cloud environment's network policy blocks ollama.com,
registry.ollama.ai and huggingface.co, so no model weights could be downloaded. The first real
runs happen on the team's laptops; LAPTOP_SETUP.md says what to send back.

## 26 September, sixth pass: the desktop app, tested on real Windows, macOS and Linux machines

The fifth pass is superseded: its Ollama installers and cynqra_cli.py were replaced by an
installable desktop app (CYNQRA_DESKTOP.md). It bundles Python 3.12.14 and llama.cpp's
llama-server b11201, downloads the model once from Hugging Face (checked against the published
SHA-256), and runs it on 127.0.0.1. The installers are built by .github/workflows/cynqra-desktop.yml
on GitHub's machines, then installed there the way a user would and tested with real models.

Measured on those machines (Windows Server 2025, macOS 26 on Apple M1, Ubuntu 24.04):

| Check | Windows | macOS | Linux |
| --- | --- | --- | --- |
| Installer builds (size) | 40 MB .exe | 82 MB .dmg | 82 MB .tar.gz |
| Installs like a user (silent installer, dmg copy, install.sh) | pass | pass | pass |
| Self-test: bundled Python and llama-server run, app server, engine journey with real tests and deploy, model files on Hugging Face | 7 of 7 | 7 of 7 | 7 of 7 |
| App window loads Cynqra (Edge app mode, pywebview, Chrome) | pass | pass | pass |
| Launch like a user (Start menu, open Cynqra.app, menu entry), Quit stops app and llama-server | pass | pass | pass |
| Real model: download, llama-server, objective, code that passes its own tests | pass (Qwen3.6 35B-A3B 2-bit: 23 tests right first time) | pass (Qwen3.5 4B on Metal, 7 GB machine: 14 tests passing after two fixes; reads 49, writes 12.9 tokens/s) | pass (Qwen3.6 35B-A3B 2-bit: 15 tests right first time) |
| Uninstall keeps the models; reinstall and self-test in `Program Files Tést\Cynqra Ü` with data in `Données de l'équipe` | pass | | |

The first real runs found three defects, each fixed and covered by a test:
- Qwen3.5 9B wrote code in a layout the strict file parser read as no files at all. The parser
  now reads the common drifts, and a reply without files is asked for once more.
- On macOS the window test passed but the process never exited (pywebview leaves a thread
  behind). The app now ends its process once everything is stopped.
- The Windows reinstall test passed a folder with spaces to the installer unquoted (a test bug).
- On GitHub's virtual Mac, llama-server loaded the model on the emulated GPU (Metal) in 105 s and
  then gave no answer to a 150-token request within the hour. A GPU that loads a model but cannot
  compute would freeze a founder's first run, so every GPU start is now followed by a 4-token test
  answer; a start that cannot answer within 2 minutes, or answers slower than 1.5 tokens/s, falls
  back to the processor by itself. On the next run the same Mac passed that test and did the whole
  check on Metal.
- Qwen3.6 35B-A3B 2-bit on Linux left two of the seven objective fields empty (success criteria,
  priorities) on one run and one on another. When fields come back empty, Cynqra now asks the
  model once more, briefly, to infer just those from the founder's words; they are marked
  Inferred for the founder to check.

Model race on the 16 GB Linux machine, CPU only, Cynqra's own work (tokens per second are
llama-server's own timings): Qwen3.5 9B passed after one fix, reading 12 and writing 5.1;
Qwen3.6 35B-A3B 2-bit wrote passing code first time, reading 22 and writing 7.7, and still passed
with 5 GB of the 16 held by another process; the 3-bit file passed after one fix at the same
speed; gpt-oss 20B passed first time, reading 17 and writing 9.1; the smallest 2-bit file failed.
The recommended model now follows memory: Qwen3.6 35B-A3B at 4, 3 and 2 bits for 32, 24 and 16 GB.

A whole journey on Windows (`desktop.py --e2e`, through the installed app's own API, every founder
decision approved automatically), Qwen3.6 35B-A3B 2-bit on the processor of GitHub's 16 GB, 4-thread
Windows machine, for the bakery objective: **passed**. Accepted, deployed, healthy, and the product's
17 tests pass on rerun; 6 of 6 tasks verified; 24 model calls, 89,668 tokens in and 58,586 out, reading
10 to 22 and writing 5 to 7 tokens/s; 248 minutes. Report: `live_20260927_010657` in the run's artifact.

That run also showed where the time went: 14 of the 24 calls, about three hours, were one task (the
HTTP server and its tests), and two verifier defects kept that engineer going round in circles:
- http.server logs every request to stderr, in the middle of unittest's `name (id) ... ok` line. The
  parser then found no results at all, so a plainly named failure (`FAIL: test_orders`, with its
  traceback) reached the engineer as "the test run did not complete". Results are now read through
  interleaved output, and failing tests are also taken from unittest's own FAIL and ERROR summary.
  A run that hangs now names the test that was running and what usually causes it (a server not in a
  daemon thread, a request with no timeout); a process that dies names the test it died in. Before,
  a hang reached the engineer as "timed out after 120s" and, with no results, as "no test_*.py".
- The local model runs at temperature 0 with a fixed seed, so a rework whose feedback and previous
  files matched an earlier attempt got the same failing reply: eight calls had identical token counts.
  A prompt sent again now gets temperature 0.3, then 0.6, then 0.9.
- The delivery contract now tells engineers how a test starts a server: port 0, serve_forever() in a
  daemon thread, a timeout on every request, and shut down when done.

Unrun here: a GPU (GitHub's standard machines have none), so the Vulkan path is exercised only
up to device detection and the fallback to the processor; Gatekeeper and SmartScreen prompts, which
appear only for a file downloaded by a browser.
