# Cynqra POC test report

**What:** every automated test, and what each module proves. **Why:** a change is safe only if the whole flow still
works after it. **How:** `cd poc && python3 -m unittest discover -s tests -t tests`. **What the tests do not prove:**
the quality of real AI output; the tests use stand-in AIs and the demos' prepared scripts, and real-model runs are
reported in docs/3_STATUS_AND_ROADMAP.md.

Run on 30 September 2026. Linux, Python 3.11.15, Node 22 with Playwright and Chromium.

## Result

308 tests, 308 passed, 0 failed, 0 skipped. About 8 minutes in all.

| Module | Tests | What it proves |
| --- | --- | --- |
| test_core | 30 | Append only events, the D-18 envelope, personal data keys refused (D-22), content addressed objects, policy for every tier and role, protocol objects that content cannot reroute, the test runner, workers never see keys, and the verifiers: document types' sections, numbered checks and cited requirement ids, the objective lint for briefs and specifications, the forecast backtest rejecting a flat mean and accepting a weekday mean |
| test_journey | 33 | All three demos end to end. Bluedip (the demo that opens first): three cofounders (CTO, Chief Product Officer, CFO) each with the team it chose, a Data Scientist and a Restaurant Revenue Management Specialist among them, and no AI CEO; every team member's task handed out, answered and reviewed by its cofounder, the Designer's screen sent back once by the CPO; the Company Pack with every foundation document checked and its sourced, assumed and confirm-with-a-professional sections, and the brief answering what, why and how; the platform's backtest rejecting the first forecast and a test catching the ignored cap; the Backend Engineer's doubt answered by the Specialist and the Frontend Engineer's by the CTO, without the CEO; the CEO deciding only the CFO's rule on offers, the merge, going live (proposed by DevOps, endorsed by the CTO) and acceptance; the live app showing the owner's 50% offer losing margin and a better one earning it; every task replays. Candidate tracker: accepted and live, two cofounders and their teams synthesized then approved, the roadmap and budget as a second gate, twelve fields per task including its dollar budget, a Blocker cleared without the founder, a defect caught before verified, a prohibited email denied, every task replays, the scripted source staffed and metered through the registry, the orchestrator implementing the run contract. Restaurant forecast: two cofounders and seven team members, fourteen tasks, the backtest rejecting the first forecast, eight documents and the decided rule in the repository, a deploy proposed by DevOps |
| test_controls | 25 | Gateway: workspace rules, audit, a credential never written. Decisions: every field, edit, reject, request evidence, "more evidence" never stopping the run, the D-29 escalation budget. Budget in dollars: machine time priced, warnings at 50, 80 and 95, the breaker, a refused cap raise leaving the decision open, raising the cap resuming the run, bad budgets refused. Kill switch, objective change (D-30), a second change waiting for the first, a run surviving a restart |
| test_failure_paths | 13 | Three invalid replies go to the Replacement Engine and then the founder; three failed verifications likewise, with the failing test named and nothing integrated; retries recover; refused writes; a failing release candidate is not merged; a failed live smoke test rolls back; rejected delivery; a refused breaker stops the run |
| test_product_flow | 21 | Requirements, cofounders, teams and plan validators: only cofounder roles in the first step, each cofounder hiring only roles it may lead, nobody hired twice, one of each cofounder, an empty team allowed; the platform closing what the catalog requires (a role for an uncovered area, added and labelled, reporting to the cofounder whose area it serves; a founder's edit refused instead); section 3's organization as two cofounders and nine team members; authority from the catalog; the workforce gate (reject revises, edits only under governance and checked first); the roadmap gate; the Budget Engine's layers and charges; performance thresholds; all three scenarios passing the validators a model's answers do |
| test_workforce | 14 | Three OpenAI-compatible provider connections to llama-server test doubles: registry facts, removing a connection retires its models, selection from measured outcomes, staffing and metering, why a call failed (outage, timeout, rate limit, no credit, refused key, withdrawn, and a reply cut off or unreadable, which is the AI's fault and never the provider's); an offline model kept after its outage is diagnosed, with one CEO question, a stand-in and the return to its own AI; an AI withdrawn mid-run moving every worker on it, the CEO told; the CEO choosing to wait; no credit going to the CEO with nothing replaced; a task rerouted to a peer, the dollar breaker, keep or replace on evidence, the regression gate, a successor inheriting the work and the CEO told its price |
| test_real_model_paths | 19 | Model ids renumbered, money never taken from the model, a refused plan retried once with the reason, replies without files, nested files, a broken delivery contract, bad assignments, escalations returning to the failed stage, a slow model not blocking the screen or the kill switch, outages resuming, the HTTP API's decision trail |
| test_live_and_deploy | 13 | Live mode needs a model and writes nothing without one; the environment's model registered and staffed; a failing model with no alternative is waited for, invents nothing, and recovers; a reopened run whose model is gone still opens; the deployment service with rollback; a product that listens on every network address refused before preview; the demo products' own tests |
| test_adapter | 15 | The Anthropic and OpenAI wire formats against a local fake provider, retired models, a provider outage waited out with the CEO told, JSON retries, and live_check.py with the Budget Engine's breaker as its spend cap |
| test_local_models | 21 | Local servers (Ollama, llama.cpp), Hugging Face providers, file blocks, cut-off replies, blank objective fields inferred in one follow-up, the environment model priced at its list price |
| test_desktop | 25 | The desktop app: model download and runtime, the app's API, the self-test, --e2e and --check-model (the registry's probe) against the test double, the workforce demonstration |
| test_intelligence_supply | 17 | The locked V1 decisions and their ten demonstrations: OpenAI-compatible, Anthropic and local connections discovered and registered; the key only in the secrets layer and resolved per call; Bedrock listed as planned and refused if connected; a new adapter plugged in with nothing else changed; workers holding no intelligence, several sharing one, different workers on different intelligence by evidence; a run through the gateway, metered; a better intelligence detected and the worker rebound with its identity kept; a new version regression-checked; the fallback preferred; every decision an audit event; a catalogue model no provider serves skipped and the run carries on; a hosted call giving up after ten minutes; the demonstration picking the newest served model of each family; the company serving a Hugging Face model pinned on every call, kept while live, and a change of it treated as a new version |
| test_parallel_team | 2 | The team works at the same time: in the restaurant demo several experts act in one round after the brief, each worker one piece at a time; four workers' model calls overlap while the run stays consistent, and the project is accepted |
| test_robustness | 5 | The demos' answers garbled at random, the cofounders' and teams' proposals and the cofounders' reviews included (fields dropped, text arriving as numbers, lists as objects) end every run cleanly, on the seeds that reached each of the five crashes the second audit found; protocol objects take the template's shape; only a prepared demo can be opened; the screen reads only the newest events |
| test_cofounders | 6 | A cofounder sends the same work back at most twice, then the platform's checks decide and the concern stays on the record, and an unendorsed proposal is not marked endorsed; an unreadable review is asked again once, then the work goes on and it is said; a team member always reports to a cofounder who may lead it; a project saved with roles that no longer exist stops with a plain reason and can still be read; a doubt no colleague can answer goes to the CEO as an escalation |
| test_team_trust | 9 | Every seat earns its place, asking the founder nothing more: in Bluedip the CTO's Security Expert owned nothing and is cut, the Designer the challenger wanted merged away is kept because it is the only seat on the screen design; one owner per requirement, every risk watched, who asked for each seat, confidence "high" from the checks; the lean team of 10 covering everything with its own seat cards, and refused in a demo with the reason; a challenger that wants every seat gone overruled on all but the empty one; an unreadable challenge still running the removal test and lowering the confidence; an area the founder leads getting no cofounder, its requirements and risks theirs; the founder's profile checked (leading technology refused with the reason; a demo's founder fixed by its script; the background kept); the stage limiting a cofounder's headcount; every member joining with its first task and one with none listed |
| test_right_thing | 14 | The business numbers recomputed like code: every claim from its inputs, a wrong lifetime value caught with the right figure, figures that are not numbers (NaN, infinity) or make no sense (negative churn, a zero price) refused, every input marked assumption, measured or sourced, months to profit and whether the money lasts, Bluedip's model holding up; foundation documents marking assumptions and listing sources; the guesses an idea rests on ranked riskiest first, measures of success kept, a company that must earn money getting a way to reach customers, a high-risk guess tested late said plainly; a guess keeping its link when the model numbers requirements its own way; an internal tool never given someone to sell it; Bluedip end to end with the CFO's wrong figure caught and fixed, and a guess only the founder can test never called proven by desk work |
| test_keeps_running | 13 | Decisions that can be undone (a merge, a product rule) settled by the accountable cofounder and the founder told; a rule on money, one whose subject is unclear, one the CFO proposes, one its cofounder did not approve, and going live kept for the founder; a member who left never asked for help; governance sending everything to the founder; the next cycle on the live product from what users said, with its own budget, the CTO merging and the founder only putting it live and accepting it, release 1.1 live; a demo with no script for a cycle stopping plainly; a cycle whose plan failed retried with the same ask; the cycle's work replaying; a rejected delivery fixed in a cycle; the founder's update; the Company Pack separating the founder's decisions from what was settled for them; the foundations checklist with what prepared each item; the next similar project getting a track record |
| test_security | 5 | What the security audit found, kept fixed: a key never follows a redirect (all five kinds) to another server; a key only over https to another computer, and a provider's address only a web address (a file is refused); a key quoted in an error never written to the database; a hung test, and a passing one, leave nothing they started running |
| test_server | 8 | HTTP API: other websites refused (DNS rebinding, another site's page, a non-JSON command, a link or image from another site); Cynqra's pages refuse to be framed or embedded and run only Cynqra's scripts; commands over 2 MB refused; provider connections (connect, update, fault, remove, a key never shown, Bedrock refused); the UI served, path traversal blocked, the full journey over HTTP, bad requests are 400, auto run and archive; and the browser test, the seven steps clicked through the real UI in Chromium: the founder defining themselves, the audit on the Product screen and acceptance there |

## Coverage

Statement coverage of the platform code, measured with coverage.py over the full suite on 28 September 2026, before `seats.py`, `numbers.py` and `lessons.py` were added (their tests are listed above):

| File | Statements | Missed | Cover |
| --- | --- | --- | --- |
| cynqra/binding.py | 22 | 1 | 95% |
| cynqra/budget.py | 142 | 4 | 97% |
| cynqra/db.py | 101 | 1 | 99% |
| cynqra/delivery.py | 111 | 0 | 100% |
| cynqra/deploy.py | 159 | 9 | 94% |
| cynqra/engine.py | 592 | 32 | 95% |
| cynqra/execution.py | 386 | 20 | 95% |
| cynqra/gateway.py | 73 | 2 | 97% |
| cynqra/intelligence.py | 318 | 13 | 96% |
| cynqra/intelligence_layer/__init__.py | 70 | 4 | 94% |
| cynqra/intelligence_layer/adapters.py | 294 | 25 | 91% |
| cynqra/intelligence_layer/connections.py | 96 | 5 | 95% |
| cynqra/intelligence_layer/contracts.py | 7 | 0 | 100% |
| cynqra/intelligence_layer/credentials.py | 82 | 10 | 88% |
| cynqra/intelligence_layer/gateway.py | 60 | 14 | 77% |
| cynqra/intelligence_layer/registry.py | 177 | 5 | 97% |
| cynqra/intelligence_layer/router.py | 60 | 2 | 97% |
| cynqra/model_adapter.py | 263 | 26 | 90% |
| cynqra/objective.py | 112 | 2 | 98% |
| cynqra/performance.py | 61 | 3 | 95% |
| cynqra/planner.py | 123 | 9 | 93% |
| cynqra/policy.py | 44 | 2 | 95% |
| cynqra/probe.py | 117 | 16 | 86% |
| cynqra/protocol.py | 34 | 1 | 97% |
| cynqra/replacement.py | 413 | 38 | 91% |
| cynqra/roles.py | 104 | 2 | 98% |
| cynqra/run.py | 10 | 0 | 100% |
| cynqra/runtime.py | 391 | 82 | 79% |
| cynqra/server.py | 284 | 45 | 84% |
| cynqra/settings.py | 29 | 1 | 97% |
| cynqra/synthesis.py | 261 | 8 | 97% |
| cynqra/testrunner.py | 93 | 7 | 92% |
| cynqra/verifier.py | 188 | 6 | 97% |
| TOTAL | 5277 | 395 | 93% |

`runtime.py` (79%) is the desktop app's model download and llama-server manager; its GPU and platform branches
run on the build machines of `.github/workflows/cynqra-desktop.yml`.

## Also checked

- The browser walk-through (`tests/e2e/walk.js`) of the Bluedip demo, in Chromium with Playwright: the whole
  journey through the real screens, the four CEO decisions, the live Bluedip app used, no errors (28 September).
  Walked again at phone width (`WALK_WIDTH=390`): every screen fits a 390-pixel screen with no sideways scrolling.
- Security: a hostile demo team whose every answer carries markup that would run code if the screen inserted it
  as HTML, walked through every screen in Chromium: shown as text, run nowhere. Another site's page framing
  Cynqra: refused by the browser. A provider that redirects: nothing reaches the other server.
- Fuzzing: 360 runs (120 per demo) of the three demos with their answers garbled at random (the harness the robustness test is
  drawn from); no run crashes after the fixes. Before them, five kinds of answer crashed the run.
- After the cofounder change, 75 more runs (25 per demo) with the cofounders', teams' and reviews' answers garbled too: no run crashes. A hostile team whose every answer carries markup that would run code, walked through every screen including the org chart: shown as text, run nowhere.
- pyflakes reports nothing on `cynqra/`, the tests, the entry points and the demos' code.
- The demo video was recorded again on Bluedip with `demo/record_demo.js`. The recording checks that every highlight
  sits fully above the captions (none was cut) and logs each caption, screen change and caught moment; the frame at
  every caption and around every screen change was reviewed. A walk of every screen at the video's size
  (1600 x 900) with a layout check (anything past the screen's edge, wider than its box, or out of its card) found
  nothing after the fixes.
