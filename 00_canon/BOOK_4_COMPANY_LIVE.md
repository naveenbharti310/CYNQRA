# Book 4: Company and Execution Plan

Live export, 25 August 2026. This is newer than the PDF in this folder.
Book 4 answers: who do we hire, what are the next 90 days, and what have we decided.
Owner: CEO. It holds the team plan, the execution plan, and the Decision Log that
governs the whole canon.

## 1. Operating model and canon ownership

| Role | Owns | Accountable for |
| --- | --- | --- |
| CEO (founder) | Book 0, Book 4 | Doctrine, objectives, budget, risk tolerance, final decisions |
| CPO | Book 1 | MVP scope, journeys, metrics, acceptance criteria |
| CTO | Book 2 | Architecture decisions, schemas, security, spike results |
| COO | Book 3 | Incidents, liability posture, unit economics, compliance |

Cadence: a weekly canon review, 30 minutes. One page per book: what changed, what we
learned, what decisions we need. The Decision Log is updated live.

## 2. Day one team and hiring order

| # | Role | Why this order | Trigger to hire |
| --- | --- | --- | --- |
| 1 | Founding engineer / CTO | Owns runtime, event core, architecture | Day 1 |
| 2 | Agent and LLM engineer | Worker runtime, model registry, evaluation, protocols | Day 1 |
| 3 | Product engineer (full stack) | Dashboards, approval inbox, objective wizard | Week 3 to 4, once the spikes land |
| 4 | Designer (fractional) | Decision dashboard, org graph UX | Week 6, before the first demo |
| 5 | COO / ops (fractional) | Cost model, legal posture, support | First paying company |

The CEO is the product owner until a CPO exists. Nobody is hired to do what the canon
has not defined.

## 3. The first 90 days

| Phase | Weeks | Goal | Exit criteria |
| --- | --- | --- | --- |
| M1: De-risk | 1 to 2 | Run spikes S1 to S3 (Book 2 section 9) | Three spike memos, cost model v0, go or no go on the architecture |
| M2: One worker, fully trusted | 3 to 6 | A single worker executes real tasks end to end: sandbox, tools, audit trail, verification, budget breaker | Live demo: assign task, worker executes, verified output, complete audit replay |
| M3: The fixed org | 7 to 12 | The fixed 4 worker template (CTO, PM, 2 engineers) runs protocols, escalations and approvals, and ships one real constrained product | Live demo: objective in, deployed web app out, founder approving only HIGH risk decisions, export bundle delivered |

The 90 day definition of done: the Book 1 demo sentence is true, on video, with the
event log to prove it.

Current position: still inside M1. M2 is NO-GO. See STATE_OF_PLAY.md at the root of
this handover.

## 4. Validation before the team: the Wizard of Oz run

Before any hire, we run one real project through a manual Cynqra. The CEO plays
orchestrator, off the shelf AI tools play the workers, and the run follows the canon's
own rules.

- Follow the protocol contracts (Book 2 section 7), the escalation rules (Book 0
  section 11) and the verification tiers (Book 0 section 13).
- Log events per the catalog (Book 2 section 6). A spreadsheet is fine.
- Measure founder interventions, token and time cost, and verification catch rate.
- Output: a run report appended to this book. Every place the loop breaks becomes an
  engineering requirement. This is the cheapest validation we will ever get.

Two runs exist. Run 001 is void. Run 002 closed NO-GO. Both are in `01_history/`.

## 5. Decision Log

The single record of consequential decisions. Newest last. Never delete, only supersede.
All thirty are closed.

| ID | Date | Decision | Status | Owner |
| --- | --- | --- | --- | --- |
| D-1 | 2026-08-16 | The PRD becomes a canon: Book 0 (doctrine) plus Books 1 to 4 (execution). Final PRD v1.0 is archived as the historical draft | Decided | CEO |
| D-2 | 2026-08-16 | The MVP is a fixed org template delivering a deployed web app. No dynamic org synthesis | Decided | CPO |
| D-3 | 2026-08-16 | Human workers deferred past Phase 2 (Book 3 section 5) | Decided | CEO |
| D-4 | 2026-08-16 | Verification is the make or break system. It gets a dedicated spike (S3) and a tiered design | Decided | CTO |
| D-5 | 2026-08-16 | Progressive autonomy ladder L0 to L3. New companies start at L1 | Decided | CPO |
| D-6 | 2026-08-25 | First product category for runs: CRUD style web apps, because they have the richest automated verification. G0 ratified the packet recommendation | Decided | CPO |
| D-7 | 2026-08-25 | No cross-tenant learning without explicit founder opt in. No learning feature ships without that opt in | Decided | CEO |
| D-8 | 2026-08-25 | No price now. When real run data exists, use the Book 3 three-quote median. Choose per run versus subscription then | Decided | COO |
| D-9 | 2026-08-25 | No brand spend until a 10 person gut check at the start of brand work | Decided | CEO |
| D-10 | 2026-08-16 | Every founder inbox action is captured as a decision label. The Decision entity gains what_would_change_this and label fields | Decided | CTO |
| D-11 | 2026-08-16 | The entry point is doctrine: we own the moment an objective is born, wizard first, and the founder surface is capped at roughly 3 decisions a day at any org size | Decided | CPO |
| D-12 | 2026-08-16 | Regulatory-first strategy adopted: Books 2 and 3 go to standards bodies this year as a reference architecture for auditable AI organizations | Decided | COO |
| D-13 | 2026-08-16 | Eval corpus cold start: golden sets hand built from Wizard of Oz runs, conservative thresholds, L1 default until labels accumulate | Decided | CTO |
| D-14 | 2026-08-16 | Labels are weighed against outcomes, never treated as truth. The falsification field on every recommendation is written by an independent reviewer model, not the recommending pipeline | Decided | CTO |
| D-15 | 2026-08-16 | Public accountability standard: 72 hour disclosure for public-harm incidents, insurance sized to the worst plausible run | Decided | COO |
| D-16 | 2026-08-16 | The founder relationship is a standing appointment, not a management console: daily three decisions plus a weekly evolution review | Decided | CPO |
| D-17 | 2026-08-25 | MEDIUM risk review in the MVP: founder reviews every MEDIUM action, option A. Revisit at L2. G0 ratified | Decided | CEO |
| D-18 | 2026-08-25 | Event envelope and catalog in Book 2 section 6 are the binding event contract. G0 ratified | Decided | CTO |
| D-19 | 2026-08-25 | MVP schema floor in Book 2 section 5, including Workstream and Run. G0 ratified | Decided | CTO |
| D-20 | 2026-08-25 | Action and Verification are first class MVP records. G0 ratified | Decided | CTO |
| D-21 | 2026-08-25 | Every production deployment needs founder approval in the MVP, at every autonomy level. G0 ratified | Decided | CEO |
| D-22 | 2026-08-25 | Immutable history versus deletion: Hybrid. Events carry references only. Personal data lives in erasable stores. Company key destruction is the fallback if cost dominates. Counsel still confirms erasure duties. Founder chose Hybrid | Decided | CEO |
| D-23 | 2026-08-25 | Autonomy promotion and safety demotion rules. L2 delegation list starts empty. G0 ratified | Decided | CEO |
| D-24 | 2026-08-25 | Deployment lifecycle and record. G0 ratified | Decided | CTO |
| D-25 | 2026-08-25 | Export manifest and portability contract. G0 ratified | Decided | COO |
| D-26 | 2026-08-25 | Weekly canon consistency review as a standing control. G0 ratified | Decided | CEO |
| D-27 | 2026-08-25 | LOW, MEDIUM, HIGH, Prohibited risk rubric. Classify by worst plausible outcome. G0 ratified | Decided | CEO |
| D-28 | 2026-08-25 | Fixed template authority matrix for Engineer, PM, CTO. G0 ratified | Decided | CEO |
| D-29 | 2026-08-25 | Escalation budget starts at five per company per day. SEV-1 always interrupts. G0 ratified | Decided | CPO |
| D-30 | 2026-08-25 | Objective change during an MVP run pauses for a short impact summary, then reconfirm or end. G0 ratified | Decided | CPO |

G0 session 25 August 2026. Founder authorized the packet recommendations, chose Hybrid
for D-22, and closed D-7, D-8 and D-9 on the recommended options. Counsel still confirms
erasure duties. M2 does not start on this log.

Open item carried into the handover: D-22 needs legal confirmation. There is no lawyer
retained. The letter is drafted and waits at a gate before the first paying company. It
blocks nothing in M1 or M2.

## 6. Canon governance

1. Book 0 changes only by founder decision logged here.
2. Books 1 to 4 change freely within their owner's authority. Every change is versioned
   and dated in the book's footer.
3. Contradictions between books are bugs. Fix the book, or log the decision that changes it.
4. The canon test: if a team member asks a question the canon cannot answer, that is a
   canon gap. Log it, answer it, write it down.

Version history: live export. Decision Log now complete through D-30 following the G0
session of 25 August 2026. Earlier: v0.3 extended D-13 to D-16 from bench round 3, v0.2
added D-10 to D-12, v0.1 seeded the log from the doctrine review.
