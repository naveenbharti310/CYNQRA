# Cynqra POC test report

Run on 27 September 2026, after the core was rebuilt into engines behind the run contract. Linux, Python
3.11.15, Node 22 with Playwright and Chromium.

## Result

213 tests, 213 passed, 0 failed, 0 skipped. Run time about 220 seconds.

| Module | Tests | What it proves |
| --- | --- | --- |
| test_core | 30 | Append only events, the D-18 envelope, personal data keys refused (D-22), content addressed objects, policy for every tier and role, protocol objects that content cannot reroute, the test runner, workers never see keys, and the verifiers: document types' sections, numbered checks and cited requirement ids, the objective lint for briefs and specifications, the forecast backtest rejecting a flat mean and accepting a weekday mean |
| test_journey | 25 | Both demos end to end. Candidate tracker: accepted and live, the workforce synthesized then approved, the roadmap and budget as a second gate, twelve fields per task including its dollar budget, a Blocker cleared without the founder, a defect caught before verified, a prohibited email denied, every task replays, the scripted source staffed and metered through the registry, the orchestrator implementing the run contract. Restaurant forecast: nine workers, fourteen tasks, the backtest rejecting the first forecast, eight documents and the decided rule in the repository, a deploy proposed by DevOps |
| test_controls | 23 | Gateway: workspace rules, audit, a credential never written. Decisions: every field, edit, reject, request evidence, the D-29 escalation budget. Budget in dollars: machine time priced, warnings at 50, 80 and 95, the breaker, a refused cap raise leaving the decision open, raising the cap resuming the run, bad budgets refused. Kill switch, objective change (D-30), a run surviving a restart |
| test_failure_paths | 13 | Three invalid replies go to the Replacement Engine and then the founder; three failed verifications likewise, with the failing test named and nothing integrated; retries recover; refused writes; a failing release candidate is not merged; a failed live smoke test rolls back; rejected delivery; a refused breaker stops the run |
| test_product_flow | 15 | Requirements, workforce and plan validators; section 3's twelve-worker organization; authority from the catalog; the workforce gate (reject revises, edits only under governance and checked first); the roadmap gate; the Budget Engine's layers and charges; performance thresholds; both scenarios passing the validators a model's answers do |
| test_workforce | 10 | Three models behind llama-server test doubles: registry facts, selection from measured outcomes, staffing and metering, an offline model detected and replaced, a task rerouted to a peer, the dollar breaker, keep or replace on evidence, the regression gate, a successor inheriting the work |
| test_real_model_paths | 19 | Model ids renumbered, money never taken from the model, a refused plan retried once with the reason, replies without files, nested files, a broken delivery contract, bad assignments, escalations returning to the failed stage, a slow model not blocking the screen or the kill switch, outages resuming, the HTTP API's decision trail |
| test_live_and_deploy | 12 | Live mode needs a model and writes nothing without one; the environment's model registered and staffed; a failing model with no alternative goes to the founder and recovers; a reopened run whose model is gone still opens; the deployment service with rollback; both demo products' own tests |
| test_adapter | 15 | The Anthropic and OpenAI wire formats against a local fake provider, retired models, a provider outage going to the Replacement Engine, JSON retries, and live_check.py with the Budget Engine's breaker as its spend cap |
| test_local_models | 21 | Local servers (Ollama, llama.cpp), Hugging Face providers, file blocks, cut-off replies, blank objective fields inferred in one follow-up, the environment model priced at its list price |
| test_desktop | 25 | The desktop app: model download and runtime, the app's API, the self-test, --e2e and --check-model (the registry's probe) against the test double, the workforce demonstration |
| test_server | 5 | HTTP API: the UI served, path traversal blocked, the full journey over HTTP, bad requests are 400, auto run and archive; and the browser test, the whole journey clicked through the real UI in Chromium |

## Coverage

Statement coverage of the platform code, measured with coverage.py over the full suite:

| File | Statements | Missed | Cover |
| --- | --- | --- | --- |
| cynqra/budget.py | 140 | 4 | 97% |
| cynqra/db.py | 89 | 1 | 99% |
| cynqra/delivery.py | 98 | 0 | 100% |
| cynqra/deploy.py | 149 | 9 | 94% |
| cynqra/engine.py | 531 | 27 | 95% |
| cynqra/execution.py | 310 | 19 | 94% |
| cynqra/gateway.py | 75 | 2 | 97% |
| cynqra/intelligence.py | 283 | 9 | 97% |
| cynqra/model_adapter.py | 259 | 27 | 90% |
| cynqra/objective.py | 112 | 4 | 96% |
| cynqra/performance.py | 58 | 4 | 93% |
| cynqra/planner.py | 120 | 10 | 92% |
| cynqra/policy.py | 44 | 2 | 95% |
| cynqra/probe.py | 110 | 16 | 85% |
| cynqra/protocol.py | 24 | 0 | 100% |
| cynqra/registry.py | 232 | 31 | 87% |
| cynqra/replacement.py | 140 | 5 | 96% |
| cynqra/roles.py | 71 | 2 | 97% |
| cynqra/router.py | 60 | 2 | 97% |
| cynqra/run.py | 10 | 0 | 100% |
| cynqra/runtime.py | 398 | 82 | 79% |
| cynqra/server.py | 229 | 33 | 86% |
| cynqra/settings.py | 27 | 0 | 100% |
| cynqra/synthesis.py | 117 | 5 | 96% |
| cynqra/testrunner.py | 72 | 4 | 94% |
| cynqra/verifier.py | 189 | 8 | 96% |
| Total | 3947 | 306 | 92% |

`runtime.py` (79%) is the desktop app's model download and llama-server manager; its GPU and platform branches
run on the build machines of `.github/workflows/cynqra-desktop.yml`, not here.

## Also checked

- The demo video's recording script (`demo/record_demo.js`) runs the whole current flow in headless Chromium:
  232 seconds, no errors. Encoding the MP4 needs ffmpeg, which this machine does not have.
- pyflakes reports nothing on `cynqra/`, the tests and the entry points.
