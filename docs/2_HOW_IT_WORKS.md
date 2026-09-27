# 2. How it works

All code paths below are inside `poc/cynqra/` unless stated.

## A project, step by step

| Step | What happens | Who decides | Code |
| --- | --- | --- | --- |
| 1. The idea | The CEO describes the company in their own words. Cynqra turns it into a clear brief: outcome, users, constraints, success criteria. It asks only about what it cannot safely assume. | CEO confirms the brief, sets the budget | `objective.py` |
| 2. Requirements | The brief is broken into requirements, each tagged with an area (product, finance, legal, domain, ...) | Cynqra | `objective.py` |
| 3. The team | Cynqra proposes the smallest team that covers every requirement. General roles come from the catalog; expertise particular to the idea becomes a **Specialist** named from it. Anything left uncovered is added by the platform and labelled. | **CEO approves** (gate 1) | `synthesis.py`, `roles.py` |
| 4. The right AI per member | Each team member is bound to the AI that measured best for its kind of work | Cynqra | `intelligence_layer/router.py`, `binding.py` |
| 5. Plan and budget | Milestones, tasks, owners, dependencies, acceptance criteria, and a dollar budget per task | **CEO approves** (gate 2) | `planner.py`, `budget.py` |
| 6. The work | Everyone works at the same time (see below) | The team | `engine.py` (`step`), `execution.py` |
| 7. Checks | Every piece of work is checked before it counts as done | Cynqra | `verifier.py` |
| 8. When a member stops | Cynqra first finds out why. Only an AI that cannot do the role's work is replaced, and the CEO is told what the better one costs (see below) | Cynqra; the CEO only for money or accounts | `replacement.py`, `performance.py` |
| 9. Delivery | The product is merged and deployed; the CEO receives the Company Pack | **CEO accepts** | `delivery.py`, `deploy.py` |

## How the team works together

The run moves in **rounds**. In each round:

- **Every team member with work it can do now takes one piece of it**, and they all work at the same time. A
  member does one thing at a time.
- **When a member finishes**, it hands its work over with a **Handoff**. Whoever needed it can start in the next
  round.
- **When a member has a doubt**, it raises a **Blocker** to the colleague whose field it is. That colleague answers
  in the next round; the others keep working.
- **Only real decisions go to the CEO:** scope, money, risk, merges, deploys.

The slow part, the AI thinking, happens in parallel. Saving results, spending money and logging happen one at a
time, so the records always stay consistent. Models running on one laptop take turns (a laptop runs one model at a
time); online models run truly in parallel. Up to `parallel_workers` members (default 6) think at once.

Messages between members are structured, hashed objects (Handoff, Blocker, Escalation, Approval), never free
chat: `protocol.py`.

## When a team member stops

Cynqra never swaps a member's AI on the first sign of trouble. It first finds out **why** the member stopped.

| Why | Example | What Cynqra does | Is the AI replaced? |
| --- | --- | --- | --- |
| **The provider's side** | Outage, timeout, too many calls | The member waits and tries again. The rest of the team keeps working. If the CEO named a fallback for that AI, it stands in; otherwise Cynqra asks the CEO once whether a stand-in may cover the wait, with its price. The member returns to its own AI as soon as that AI answers again. | **No** |
| **The account** | No credit left, key refused | The members on that account wait. The CEO is asked to top up or fix the key; the work then continues where it stopped. | **No** |
| **The AI itself** | Work fails its checks three times; replies keep running out of room or breaking the rules; its measured record falls too low; a new version fails its check | The AI cannot do this role's work. Cynqra picks a better one that passes a check on this kind of work first, and **tells the CEO**: why, which AI now does the work, and its price against the old one. If no better AI fits the budget, the CEO decides. | **Yes** |

The member keeps its identity, role, history and files in every case; only the AI behind it changes. Notices to the
CEO ("What Cynqra told you") are not decisions: nothing waits on them. They are listed on the Workforce screen and in
the Company Pack. `replacement.py` (`diagnose`, `model_failed`, `evaluate`, `inform`).

## The team

The team always follows the idea. Nothing is there by default.

| Kind | Roles | Code |
| --- | --- | --- |
| Leadership | Business Lead (runs the business side for the CEO), CTO, CPO, Project Manager | `roles.py` |
| Foundation | CFO, Market Analyst, Legal and Compliance Advisor, Security Expert | `roles.py` |
| Build | Software Engineer, Backend and Frontend Engineers, Data Scientist, Designer, QA, DevOps | `roles.py` |
| Field experts | **Specialist**, named from the idea: one per field the idea needs ("Food Safety Specialist") | `roles.py`, `synthesis.py` |

Each role has: the work it may own, the documents it writes, the areas it covers, and its authority (what it may
do, propose or never do). Authority is enforced on every action: `policy.py`, `gateway.py`.

## The intelligence

Four separate things, never mixed:

| Thing | What it is | Holds a key? | Code |
| --- | --- | --- | --- |
| **Worker** | A team member: identity, role, authority, history | Never | the run's store |
| **Intelligence** | An AI model, with its facts and its measured record | Never | `intelligence_layer/registry.py` |
| **Provider connection** | How Cynqra reaches a provider (OpenAI-compatible, Anthropic, local; Bedrock planned) | A reference only | `intelligence_layer/connections.py` |
| **Credential** | The key itself, kept in the secrets file or named in the environment | It is the key | `intelligence_layer/credentials.py` |

A worker's call goes: worker → its **binding** (which AI, which version) → the **gateway** (reads the key for this
one call) → the provider's **adapter** → the provider → the model. `binding.py`, `intelligence_layer/gateway.py`,
`intelligence_layer/adapters.py`.

**Hugging Face** is one connection that leads to many serving companies. Cynqra records which company serves each
model and always asks for that same one, so costs and results are never mixed between companies.

## The checks

| Work | How it is checked | Code |
| --- | --- | --- |
| Code | All tests re-run in a clean copy, plus the delivery contract (health and smoke checks) | `verifier.py`, `testrunner.py` |
| Forecasts | Back-tested by the platform against a simple baseline | `verifier.py` |
| Documents | The sections their type needs; foundation documents must separate sourced facts, assumptions, and what a professional must confirm | `verifier.py`, `roles.DOC_TYPES` |
| Merges and deploys | Tests on the release candidate; the CEO approves; health and smoke checks after deploy, with rollback | `deploy.py` |

## Money

Everything is priced in US dollars: AI calls from their real token counts, machine time, infrastructure and
verification. Every task has a budget. At the project's cap, a breaker stops all work until the CEO decides.
`budget.py`, `settings.py`.

## The record

Every action, decision and handoff is an event in an append-only log, so any task can be replayed and audited:
`db.py`, `delivery.py` (`replay`).

## The screens and the apps

| Part | Code |
| --- | --- |
| Web screens | `poc/ui/app.js`, `poc/ui/app.css` |
| HTTP API behind them | `server.py` |
| Desktop app (window, local models via llama.cpp) | `poc/desktop.py`, `runtime.py`, `desktop/` |
| Demo scenarios (scripted, free) | `poc/scenarios/` |
