# 2. How it works

**What** this covers: how a project runs, from the founder's words to the Company Pack. **Why** it is built this
way: three promises decide every part of the design; the team follows the idea, nothing counts until it is checked,
and the CEO is asked only CEO questions. **How** to read it: each section says what happens, why, and where it is in
the code. All code paths are inside `poc/cynqra/` unless stated. The example throughout is the Bluedip demo.

## A project, step by step

| Step | What happens | Why | Who decides | Code |
| --- | --- | --- | --- | --- |
| 1. The idea | The CEO describes the company in their own words. Cynqra turns it into a brief: product, customers, outcomes, success criteria, limits, priorities. What Cynqra filled in itself is marked for the CEO to check. | Everything after it is judged against this brief | CEO confirms it, sets the budget | `objective.py` |
| 2. Requirements | The brief is split into requirements, each with an area (business, market, finance, legal, domain, AI and data, product, ...) | Every requirement must end up owned by someone and checked | Cynqra | `objective.py` |
| 3. The team | As a founder would, Cynqra first proposes the **cofounders** the company needs, each with its reason (Bluedip: a CTO, a Chief Product Officer and a CFO). Then **each cofounder chooses the team for its own area**, with the reason for every hire (Bluedip's CTO: a Data Scientist, Backend and Frontend Engineers, DevOps and QA). Expertise particular to the idea becomes a **Specialist** named from it. Anything still uncovered is added by the platform and labelled. The CEO sees it all as one org chart. | A real company starts with its cofounders, and each builds its own team; there is no fixed template | **CEO approves** the whole organization once (gate 1) | `synthesis.py`, `roles.py` |
| 4. The right AI per member | Each member is bound to the AI that measured best for its kind of work | Different work needs different strengths, and measured results beat opinions | Cynqra | `intelligence_layer/router.py`, `binding.py` |
| 5. Plan and budget | Milestones, tasks, owners, dependencies, acceptance criteria, how each task will be checked, and a dollar budget per task | Nothing starts until the CEO sees who does what and what it costs | **CEO approves** (gate 2) | `planner.py`, `budget.py` |
| 6. The work | Everyone works at the same time, and cofounders run their areas (below) | A real company works in parallel, and each leader runs its own team | The team | `engine.py` (`step`), `execution.py` |
| 7. Checks | Every piece of work is checked by Cynqra, then a team member's work is reviewed by its cofounder, before it counts as done | AI output reads the same whether it is right or wrong; a check proves the rules are met, a cofounder judges whether it is right for the company | Cynqra, then the cofounder | `verifier.py`, `execution.py` (`lead_review`) |
| 8. When a member stops | Cynqra first finds out why. Only an AI that cannot do the role's work is replaced, and the CEO is told what the better one costs (below) | A provider's outage is not the AI's fault; a better AI costs more | Cynqra; the CEO only for money or accounts | `replacement.py`, `performance.py` |
| 9. Delivery | The product is merged and put live; the CEO receives the Company Pack | The founder gets a working result to use | **CEO accepts** | `delivery.py`, `deploy.py` |

## How the team works together

**What.** The run moves in **rounds**. In each round:

- **every team member with work it can do now takes one piece of it**, and they all work at the same time; a member
  does one thing at a time;
- **cofounders run their areas.** Each one hands out its team's work with a **Handoff**, answers its team's doubts,
  reviews its team's work after Cynqra's checks and before it counts (approve, or send it back with what to change),
  and brings the CEO only the decisions a CEO should make. A cofounder's own work comes straight from the approved plan;
- **when a member has a doubt**, it raises a **Blocker** to its cofounder, or to the colleague whose field it is
  (Bluedip: the Backend Engineer asks the Revenue Management Specialist which food cost to use; the Frontend Engineer
  asks the CTO what a new restaurant sees before it has history), who answers in the next round while the others
  keep working;
- **a team member's proposal reaches the CEO through its cofounder** (Bluedip: DevOps proposes going live, the CTO
  endorses it);
- **only real decisions go to the CEO:** money, risk, merges, going live.

**Why.** Working one at a time made real runs take hours; a real company does not wait for one person to finish
before the next starts. Each cofounder knows its area best, so it hands out, answers and reviews there, and the CEO
is left with CEO questions. A cofounder may send the same work back twice; after that Cynqra's checks decide and the
cofounder's concern stays on record in the Company Pack, so a disagreement never stalls the company.

**How.** The slow part, the AI thinking, runs in parallel. Saving results, spending money and logging run one at a
time, so the records always stay consistent. Models on one laptop take turns (a laptop runs one model at a time);
online models run truly in parallel. Up to `parallel_workers` members (default 6) think at once. Messages between
members are structured, hashed objects (Handoff, Blocker, Review, Escalation, Approval) with fixed fields:
`protocol.py`.

## The team

**What.** The team always follows the idea. Nothing is there by default. The founder is the CEO; Cynqra has no AI
CEO.

| Kind | Roles | Who leads them | Code |
| --- | --- | --- | --- |
| Cofounders | CTO, Chief Product Officer, CFO, and a Chief Compliance Officer for a regulated business (payments, lending, insurance, health, children's data). A simple tool may need two; Bluedip has three. | They report to the CEO | `roles.py` |
| Product | Project Manager, Product Designer, Market Analyst | Usually the Chief Product Officer | `roles.py` |
| Engineering | Software, Backend and Frontend Engineers, Data Scientist, QA, DevOps, Security Expert | The CTO | `roles.py` |
| Finance and legal | Legal and Compliance Advisor | The Chief Compliance Officer, else the CFO | `roles.py` |
| Field experts | **Specialist**, named from the idea: one per field the idea needs ("Restaurant Revenue Management Specialist") | The cofounder whose area the field serves | `roles.py`, `synthesis.py` |

**Why.** A fixed team wastes money on roles an idea does not need and misses the expertise it does. Starting from
the cofounders, as a real founder does, gives every part of the company a leader who is accountable for it.

**How.** Each role has the work it may own, the documents it writes, the areas it covers, and its authority: what it
may do, only propose, or never do. Authority is enforced on every action: `policy.py`, `gateway.py`.

## The intelligence

**What.** Four separate things, never mixed:

| Thing | What it is | Holds a key? | Code |
| --- | --- | --- | --- |
| **Worker** | A team member: identity, role, authority, history | Never | the run's store |
| **Intelligence** | An AI model, with its facts and its measured record | Never | `intelligence_layer/registry.py` |
| **Provider connection** | How Cynqra reaches a provider (OpenAI-compatible, Anthropic, local; Bedrock planned) | A reference only | `intelligence_layer/connections.py` |
| **Credential** | The key itself, kept in the secrets file or named in the environment | It is the key | `intelligence_layer/credentials.py` |

**Why.** An AI can be swapped without touching the worker, and a key never travels with the work.

**How.** A worker's call goes: worker → its **binding** (which AI, which version) → the **gateway** (reads the key
for this one call) → the provider's **adapter** → the provider → the model. `binding.py`,
`intelligence_layer/gateway.py`, `intelligence_layer/adapters.py`. **Hugging Face** is one connection that leads to
many serving companies; Cynqra records which company serves each model and always asks for that same one, so costs
and results are never mixed between companies.

## When a team member stops

**What.** Cynqra never swaps a member's AI on the first sign of trouble. It first finds out **why** the member stopped.

| Why | Example | What Cynqra does | Is the AI replaced? |
| --- | --- | --- | --- |
| **The provider's side** | Outage, timeout, too many calls | The member waits and tries again; the rest of the team keeps working. If the CEO named a fallback for that AI, it stands in; otherwise Cynqra asks the CEO once whether a stand-in may cover the wait, with its price. The member returns to its own AI as soon as that AI answers again. | **No** |
| **The account** | No credit left, key refused | The members on that account wait. The CEO is asked to top up or fix the key; the work then continues where it stopped. | **No** |
| **The AI itself** | Work fails its checks three times; replies keep running out of room or breaking the rules; its measured record falls too low; a new version fails its check | The AI cannot do this role's work. Cynqra picks a better one that passes a check on this kind of work first, and **tells the CEO** why, which AI now does the work, and its price against the old one. If no better AI fits the budget, the CEO decides. | **Yes** |

**Why.** Replacing a capable AI for a provider's outage throws away its record; a better AI usually costs more, so
the CEO must know.

**How.** The member keeps its identity, role, history and files in every case; only the AI behind it changes.
Notices to the CEO ("What Cynqra told you") are not decisions: nothing waits on them. They are on the Workforce
screen and in the Company Pack. `replacement.py` (`diagnose`, `model_failed`, `evaluate`, `inform`).

## The checks

**What.**

| Work | How it is checked | Code |
| --- | --- | --- |
| Code | All tests re-run in a clean copy, plus the delivery contract (the app starts, answers its health and smoke checks) | `verifier.py`, `testrunner.py` |
| Prediction models | Their tests, then the platform's own backtest on days the model has not seen, against a simple baseline (last week's numbers) | `verifier.py` |
| Documents | The sections their type needs; foundation documents must separate sourced facts, assumptions, and what a professional must confirm | `verifier.py`, `roles.DOC_TYPES` |
| Merges and going live | Tests on the release candidate; the CEO approves; health and smoke checks after going live, with automatic rollback | `deploy.py` |

**Why.** Nothing counts as done on a worker's word. In the Bluedip demo the checks catch two mistakes before they
count: a forecast worse than last week's numbers, and an estimate that ignored the owner's cap.

**How.** A failed check goes back to the worker with the failure named. Three failures, and Cynqra looks for a
better AI or brings it to the CEO.

## Money

**What.** Everything is priced in US dollars: AI calls from their real token counts, machine time, infrastructure and
checks. Every task has a budget. **Why:** one currency the CEO understands, and a hard stop. **How:** at the
project's cap, a breaker stops all work until the CEO decides. `budget.py`, `settings.py`.

## The record

**What.** Every action, decision and handoff is an event in an append-only log. **Why:** any task can be replayed and
audited, so the CEO can see how any result came about. **How:** `db.py`, `delivery.py` (`replay`).

## The screens and the apps

| Part | Code |
| --- | --- |
| Web screens, and the guide that explains each step | `poc/ui/app.js`, `poc/ui/tour.js`, `poc/ui/app.css` |
| HTTP API behind them | `server.py` |
| Desktop app (window, local models via llama.cpp) | `poc/desktop.py`, `runtime.py`, `desktop/` |
| Demos (scripted, free): Bluedip (opens first), a candidate tracker, a restaurant covers forecast | `poc/scenarios/` |
