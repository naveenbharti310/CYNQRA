# Cynqra POC specification

Written 26 September 2026 by the acting CEO, CTO, CPO and COO. Owner: CTO.
Authority: D-36, the founder's instruction of 26 September to build an end to end POC
with screen mockups, tested code and a product demo video.

Since 27 September the founder's product definition (Cynqra Product Flows and Architecture
v1) governs the build and supersedes this spec where they differ: the organization is
synthesized from the objective behind a workforce gate (A3's fixed template is now a test
fixture), the roadmap is a second gate, and the budget is in US dollars.
../CYNQRA_PRODUCT_ALIGNMENT.md records every change. The acceptance table below maps each
criterion to the tests that hold it today.

## What the POC is, and what it is not

It is the Book 1 demo sentence made runnable on one machine: "I typed an objective,
approved an org and a plan, answered a handful of decisions, and had a deployed product
I could export and walk away with." Every piece of the organization layer is real code:
the objective record, the fixed organization, protocol objects, the policy check before
every action, the Tool Gateway, the budget breaker, append only events, tiered
verification, the approval inbox, the deployment lifecycle, export and replay.

It is not evidence for any gate. S1, S2 and S3 v2 still decide M2. In demo mode the
workers' words come from a prepared script and every screen says so. In live mode a real
model does the thinking, through the same adapter the spikes use. Code the workers write
is written to disk, tested for real and deployed for real in both modes.

## Readiness cross check, 26 September

| Needed to build | Source | State | Action taken |
| --- | --- | --- | --- |
| What to build | Book 1 P0 1 to 12, acceptance contract in the v0.4 addendum | Complete | Traced to tests below |
| How to build | Book 2 addendum contracts, IMPLEMENTATION_DECISIONS_LIVE.md | Complete for M2; POC uses local substitutes | Substitutes listed below |
| Who may do what | D-28 authority matrix | Ratified, text lost with v0.5 | Working text below, to re-ratify under D-34 |
| How risky is it | D-27 risk rubric | Ratified, text lost with v0.5 | Working text below, to re-ratify under D-34 |
| MEDIUM review | D-17: founder reviews every MEDIUM action | Decided | Enforced by policy |
| Production deploy | D-21: founder approves every production deploy | Decided | Enforced by policy |
| Escalation budget | D-29: five per company per day, SEV-1 always interrupts | Decided | Enforced by the inbox |
| Objective change | D-30: pause, impact summary, reconfirm or end | Decided | Enforced by the orchestrator |
| Personal data | D-22: events carry references only | Decided, counsel pending | Event payloads carry ids and hashes, never names |
| Event contract | D-18 plus D-32 proposal | Decided plus proposal | Envelope includes protocol_hash and test_ids |
| Screens | Book 0 section 21 and 22 | Defined in words only | Mockups on the design canvas |
| Model access | spikes/model_adapter.py | Ready, no key | Two modes: demo and live |

## D-27 working text: risk rubric

Classify every action by its worst plausible outcome. When unsure, go one tier higher.

| Tier | Test | Examples |
| --- | --- | --- |
| LOW | Reversible, inside the worker's own workspace, inside the task budget, nobody outside sees it | write a file in the workspace, read a handed artifact, run tests, raise a Blocker, send a Handoff |
| MEDIUM | Reversible, but changes shared product state or what the product means | merge to the main repository, a product rule decision, install a package, a preview deploy |
| HIGH | Hard to reverse, or visible outside the company | production deploy, deleting data, spend above the task budget |
| Prohibited | No worker may do it at any autonomy level (Book 1 addendum boundary) | external messages, money movement, legal commitments, changing the objective, the budget or anyone's authority |

## D-28 working text: authority matrix for the fixed template

E = executes. P = proposes; the proposal goes to the founder (D-17, D-21). N = not allowed.

| Action | Engineer A, B | PM | CTO | Tier |
| --- | --- | --- | --- | --- |
| write_file (own workspace) | E | E | E | LOW |
| read_artifact (handed to it) | E | E | E | LOW |
| run_tests (own workspace) | E | E | E | LOW |
| raise_blocker, send_handoff | E | E | E | LOW |
| assign_task, answer_blocker | N | E | E | LOW |
| product_rule_decision | N | P | P | MEDIUM |
| review_work | N | E | E | LOW |
| merge_to_main | P | N | P | MEDIUM |
| install_package | P | N | P | MEDIUM |
| deploy_production | N | N | P | HIGH |
| external_message | N | N | N | Prohibited |
| change_budget, change_objective, change_authority | N | N | N | Prohibited |

Founder only: confirm the objective, approve the organization and plan, answer proposals,
raise the budget cap, pull the kill switch, accept delivery.

## The journey the POC runs

1. Objective. The founder types one messy sentence. The Objective System returns the seven
   fields and marks which it inferred (D-31). The founder edits, sets a budget cap and risk
   tolerance, confirms. Intervention 1.
2. Organization and plan. The fixed template is instantiated: CTO, PM, Engineer A,
   Engineer B, plus the Verification Service, which is not a worker. The PM plans
   workstreams and tasks with every Book 0 section 13 field. The founder approves.
   Intervention 2.
3. Work. Workers act only through the Tool Gateway, only inside their own workspace, only
   on artifacts a Handoff listed. Every message between them is a stamped protocol object.
   The demo run contains, on purpose:
   * a Blocker that the PM clears without the founder (Book 1 P0 7);
   * a failing first attempt that verification catches before anything is marked verified;
   * a MEDIUM product rule that goes to the founder (intervention 3) and a MEDIUM merge
     that goes to the founder (intervention 4);
   * a Prohibited action (an external email) that policy denies with no founder involved.
4. Delivery. Production deploy is HIGH and waits for the founder (D-21, intervention 5).
   The deployment runs BUILD, TEST, PACKAGE, PREVIEW, VERIFY, APPROVAL, DEPLOY, HEALTH
   CHECK, SMOKE TEST, LIVE. The app is served at a local URL. The export bundle and the
   transition record are written. The founder accepts delivery. Intervention 6.

## Delivery contract for the product being built

Any product the organization builds in the POC is a Python standard library web app:
`app.py` serving on the port in the PORT environment variable, a `/health` route, and
unittest files named `test_*.py`. This is the CRUD category of D-6 made concrete, and it
is what the deploy step checks.

## Acceptance tests

Each line is automated in poc/tests. Book 1 P0 numbers in brackets. Module and class
names are the real ones; run `python -m unittest -v` inside poc/tests to see each by name.

| ID | Acceptance | Where it is tested |
| --- | --- | --- |
| A1 | A company and objective are created and submitted, with version and submission recorded [1, 2] | test_journey: test_objective_submitted_and_decomposed |
| A2 | Inferred fields are flagged and editable before confirmation (D-31); a change during a run pauses it (D-30) | test_controls: ObjectiveTests |
| A3 | The organization is the approved proposal, from the catalog, with nobody hired before the founder approves [3] | test_journey: test_workforce_synthesized_then_approved; test_product_flow: GateTests |
| A4 | Every task, worker and decision answers who owns, depends, approves [4] | test_journey: test_graph_answers_owner_dependency_approver; test_core: PolicyTests.test_graph_query |
| A5 | Every task carries the twelve fields and a risk tier set by the platform, not the model [5] | test_journey: test_every_task_has_the_twelve_fields; test_live_and_deploy: test_plan_rules_are_the_platforms |
| A6 | Workers write only inside their workspace, only through the Gateway, only allowlisted tools [6] | test_controls: GatewayTests; test_failure_paths: WriteRefusedTests |
| A7 | Handoff, Blocker, Escalation and Approval are stamped protocol objects; one dependency resolves without the founder [7] | test_core: ProtocolTests; test_journey: test_blocker_resolved_without_the_founder; test_failure_paths: InvalidProtocolTests |
| A8 | Completed and verified are separate states; a defect is caught before verified; prior tests rerun; three failures escalate [8] | test_journey: test_defect_caught_before_verified, test_completed_is_separate_from_verified; test_failure_paths: VerificationFailsThreeTimesTests |
| A9 | The inbox shows problem, evidence, recommendation, cost, risk, confidence, what would change it; approve, edit, reject, request evidence [9] | test_controls: DecisionTests |
| A10 | Budget warnings at 50, 80, 95; hard stop and founder alert at the cap, in US dollars [10] | test_controls: BudgetTests; test_product_flow: BudgetEngineTests; test_failure_paths: test_budget_breaker_refused_stops_the_run |
| A11 | Events are append only; every task replays actor, authority, policy decision, context, intelligence, tool, result, verification [11] | test_core: EventStoreTests; test_journey: test_replay_is_complete_for_every_task |
| A12 | Deploy record, health and smoke check, live URL, rollback, export manifest [12] | test_journey: test_deployment_record_and_export; test_live_and_deploy: DeployServiceTests; test_failure_paths: LiveSmokeFailsTests |
| A13 | MEDIUM goes to the founder (D-17), production deploy goes to the founder (D-21), Prohibited is denied (D-27) | test_core: PolicyTests; test_journey: test_prohibited_action_denied_without_the_founder, test_founder_only_sees_what_needs_them |
| A14 | The kill switch freezes all workers mid run | test_controls: KillSwitchTests |
| A15 | Live mode reaches the model only through the adapter, over the real provider wire formats; a model error invents nothing and goes to the Replacement Engine, then the founder | test_live_and_deploy: LiveModeTests; test_adapter |
| A16 | The whole journey runs through the web UI in a real browser | test_server: BrowserEndToEnd (runs when Node and Playwright are present) |

Not automated, stated plainly: a run against a real Claude model (no key in this
environment, so it is unrun, not passed) and a double click of RUN_POC.bat on Windows.

## Local substitutes for the M2 build

| M2 choice | POC substitute | Gap that remains |
| --- | --- | --- |
| Postgres, insert only events table | SQLite with triggers that reject UPDATE and DELETE on events | Multi user, backups |
| gVisor container per worker session | A separate workspace folder per worker, subprocess with a cleaned environment and a timeout | No kernel isolation, no egress control. Not safe for untrusted code |
| Durable workflows | A step machine persisted in SQLite, resumable after restart | No distributed workers |
| Secret manager | No secrets in demo mode; the live key stays in the process environment only | Rotation, scoping |
| Deployment target | A local process on 127.0.0.1 | Real hosting, rollback of infrastructure |

## Running it

Windows: double click RUN_POC.bat. Any machine: `python poc/run_poc.py`, then open
http://127.0.0.1:8750. Live mode: set ANTHROPIC_API_KEY before starting, and choose Live
in the wizard.
