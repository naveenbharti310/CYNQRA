# Cynqra POC test report

**What:** every automated test, and what each module proves. **Why:** a change is safe only if the whole flow still
works after it. **How:** `cd poc && python3 -m unittest discover -s tests -t tests`. **What the tests do not prove:**
the quality of real AI output; the tests use stand-in AIs and the demos' prepared scripts, and real-model runs are
reported in docs/3_STATUS_AND_ROADMAP.md.

Run on 28 September 2026. Linux, Python 3.11.15, Node 22 with Playwright and Chromium.

## Result

248 tests, 248 passed, 0 failed, 0 skipped. Run time about 280 seconds.

| Module | Tests | What it proves |
| --- | --- | --- |
| test_core | 30 | Append only events, the D-18 envelope, personal data keys refused (D-22), content addressed objects, policy for every tier and role, protocol objects that content cannot reroute, the test runner, workers never see keys, and the verifiers: document types' sections, numbered checks and cited requirement ids, the objective lint for briefs and specifications, the forecast backtest rejecting a flat mean and accepting a weekday mean |
| test_journey | 32 | All three demos end to end. Bluedip (the demo that opens first): the team the idea needs, a Data Scientist and a Restaurant Revenue Management Specialist among them; the Company Pack with every foundation document checked and its sourced, assumed and confirm-with-a-professional sections, and the brief answering what, why and how; the platform's backtest rejecting the first forecast and a test catching the ignored cap; the engineer's doubt answered by the Specialist without the CEO; the CEO deciding only the CFO's rule on offers, the merge, going live and acceptance; the live app showing the owner's 50% offer losing margin and a better one earning it; every task replays. Candidate tracker: accepted and live, the workforce synthesized then approved, the roadmap and budget as a second gate, twelve fields per task including its dollar budget, a Blocker cleared without the founder, a defect caught before verified, a prohibited email denied, every task replays, the scripted source staffed and metered through the registry, the orchestrator implementing the run contract. Restaurant forecast: nine workers, fourteen tasks, the backtest rejecting the first forecast, eight documents and the decided rule in the repository, a deploy proposed by DevOps |
| test_controls | 23 | Gateway: workspace rules, audit, a credential never written. Decisions: every field, edit, reject, request evidence, the D-29 escalation budget. Budget in dollars: machine time priced, warnings at 50, 80 and 95, the breaker, a refused cap raise leaving the decision open, raising the cap resuming the run, bad budgets refused. Kill switch, objective change (D-30), a run surviving a restart |
| test_failure_paths | 13 | Three invalid replies go to the Replacement Engine and then the founder; three failed verifications likewise, with the failing test named and nothing integrated; retries recover; refused writes; a failing release candidate is not merged; a failed live smoke test rolls back; rejected delivery; a refused breaker stops the run |
| test_product_flow | 17 | Requirements, workforce and plan validators; the platform closing what the catalog requires (a role for an uncovered area, added and labelled; a founder's edit refused instead); section 3's twelve-worker organization; authority from the catalog; the workforce gate (reject revises, edits only under governance and checked first); the roadmap gate; the Budget Engine's layers and charges; performance thresholds; all three scenarios passing the validators a model's answers do |
| test_workforce | 13 | Three OpenAI-compatible provider connections to llama-server test doubles: registry facts, removing a connection retires its models, selection from measured outcomes, staffing and metering, why a call failed (outage, timeout, rate limit, no credit, refused key, withdrawn); an offline model diagnosed, not replaced, with one CEO question, a stand-in and the return to its own AI; the CEO choosing to wait; no credit going to the CEO with nothing replaced; a task rerouted to a peer, the dollar breaker, keep or replace on evidence, the regression gate, a successor inheriting the work and the CEO told its price |
| test_real_model_paths | 19 | Model ids renumbered, money never taken from the model, a refused plan retried once with the reason, replies without files, nested files, a broken delivery contract, bad assignments, escalations returning to the failed stage, a slow model not blocking the screen or the kill switch, outages resuming, the HTTP API's decision trail |
| test_live_and_deploy | 12 | Live mode needs a model and writes nothing without one; the environment's model registered and staffed; a failing model with no alternative is waited for, invents nothing, and recovers; a reopened run whose model is gone still opens; the deployment service with rollback; the demo products' own tests |
| test_adapter | 15 | The Anthropic and OpenAI wire formats against a local fake provider, retired models, a provider outage waited out with the CEO told, JSON retries, and live_check.py with the Budget Engine's breaker as its spend cap |
| test_local_models | 21 | Local servers (Ollama, llama.cpp), Hugging Face providers, file blocks, cut-off replies, blank objective fields inferred in one follow-up, the environment model priced at its list price |
| test_desktop | 25 | The desktop app: model download and runtime, the app's API, the self-test, --e2e and --check-model (the registry's probe) against the test double, the workforce demonstration |
| test_intelligence_supply | 17 | The locked V1 decisions and their ten demonstrations: OpenAI-compatible, Anthropic and local connections discovered and registered; the key only in the secrets layer and resolved per call; Bedrock planned, not connectable; a new adapter plugged in with nothing else changed; workers holding no intelligence, several sharing one, different workers on different intelligence by evidence; a run through the gateway, metered; a better intelligence detected and the worker rebound with its identity kept; a new version regression-checked; the fallback preferred; every decision an audit event; a catalogue model no provider serves skipped, not fatal; a hosted call giving up after ten minutes; the demonstration picking the newest served model of each family; the company serving a Hugging Face model pinned on every call, kept while live, and a change of it treated as a new version |
| test_parallel_team | 2 | The team works at the same time: in the restaurant demo several experts act in one round after the brief, each worker one piece at a time; four workers' model calls overlap while the run stays consistent, and the project is accepted |
| test_server | 6 | HTTP API: provider connections (connect, update, fault, remove, a key never shown, Bedrock refused); the UI served, path traversal blocked, the full journey over HTTP, bad requests are 400, auto run and archive; and the browser test, the whole journey clicked through the real UI in Chromium |

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
