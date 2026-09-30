# 2. How it works

**What** this covers: how a project runs through the seven steps of the journey ([0_USER_JOURNEY.md](0_USER_JOURNEY.md)),
from the founder's words to the working product. **Why** it is built this way: the organisation follows the idea and
the founder, nothing counts until it is checked, and the founder is asked only what cannot be undone. **How** to read
it: each section says what happens, why, and where it is in the code. All code paths are inside `poc/cynqra/` unless
stated. The example throughout is the Bluedip demo.

## The seven steps

| Step | What happens | Who decides | Code |
| --- | --- | --- | --- |
| 1. Describe the idea | The founder describes what they want in their own words. Cynqra turns it into a brief: product, customers, outcomes, success criteria, limits, priorities. What Cynqra filled in itself is marked for the founder to check. The brief becomes the requirements the team is built from, each in an area (product, AI and data, design, deployment, business, ...), and the risks that must not happen. | The founder confirms it and sets the budget | `objective.py` |
| 2. Approve the plan | Cynqra shows what it will build, the capabilities it takes and the organisation it proposes: the **AI cofounders** the idea needs (Bluedip: a CTO, a Chief Product Officer and a CFO), and the team **each cofounder chooses** for its own area. Every seat has to earn its place (below). A lean team is shown beside the recommended one, with an estimated budget. | **The founder approves** the plan, or asks for a different one | `synthesis.py`, `seats.py`, `roles.py` |
| 3. Define yourself | The founder says what they bring: background, the areas they lead, their hours. In live mode Cynqra then constructs the organisation again around them: the cofounders and every team are drafted anew with the founder's background, checked and challenged as before, and replace the step 2 organisation before anyone is staffed; what changed is shown at step 4. A cofounder seat the founder leads is not filled by an AI cofounder: that area becomes a lead who reports to the founder, and what that cofounder would have settled comes to the founder. A technical founder gets no CTO. A team the founder edited by hand at step 2 is kept, and a demo's organisation is part of its script. | The founder | `engine.py` (`define_founder`, `_fit_founder`), `synthesis.py` (`refit`) |
| 4. Approve the team and budget | Each member is bound to the AI that measured best for its kind of work. The plan sets milestones, tasks, owners, dependencies, how each task is checked and a dollar budget per task. A member with no work leaves before anything starts. | **The founder approves** the team and budget | `intelligence_layer/router.py`, `binding.py`, `planner.py`, `budget.py` |
| 5. Watch it being built | Everyone works at the same time and cofounders run their areas (below). Every piece of work is checked by Cynqra, then reviewed by its cofounder, before it counts. A member that stops is diagnosed first, and its AI is replaced only if it cannot do the work. | The team; **the founder** only for what cannot be undone, such as a rule about money and putting the product live | `engine.py` (`step`), `execution.py`, `verifier.py`, `replacement.py` |
| 6. Receive the working product | The product is merged, put live and checked after it goes live. The founder opens it, uses it, or downloads everything. | The founder | `delivery.py`, `deploy.py` |
| 7. Audit, rework and refine | Cynqra audits the product against the original objective: every requirement, the work that answers it, and whether that work passed its checks. The founder accepts it, or says what should change; the same team plans only that work, which is priced, approved once, built, checked and released. The release before it stays as the way back. | **The founder** accepts, or asks for a rework | `engine.py` (`audit`, `rework`, `start_cycle`), `planner.py` |

## Every seat earns its place

**What.** Before the founder sees the team, Cynqra checks every seat, and the founder is asked nothing more for it:

- **One owner per requirement, someone on every risk.** When several seats work on a requirement, the one doing the
  work owns it; the others help.
- **A card for every seat:** who asked for it (Cynqra for a cofounder, the cofounder for a hire, "added by Cynqra" for
  a gap), what it owns, helps with and watches, and what would be left undone without it (the removal test).
- **The independent challenge.** A reviewer outside the team, whose only job is to make it smaller, says which
  seats to cut, merge, keep only as an advisor or bring in later, and the likeliest reasons the company would fail.
  The platform decides: a seat the removal test finds nothing behind is cut; a seat the challenger wanted gone but
  that is the only one on something stays, with the reason. "Advisor" and "later" are shown as labels on the seat;
  every member joins with its first task in any case. If the challenger's answer cannot be read, the removal test
  still runs and the confidence drops.
- **The lean team,** the smallest team that still covers every requirement, risk and delivery step, is shown next to
  the recommended one with what each extra seat adds. A seat's work goes to another only if that seat covers the
  same area and can do every kind of work it did.
- **Why this team,** with a confidence that comes from the checks: high when everything has one owner and the
  proposers needed no help; medium when Cynqra had to fill a gap or could not read the challenge; low when anything
  is left without an owner.
- **A headcount limit by stage:** a cofounder hires at most 2 seats at the idea stage, 4 for a first version and 6
  for going live, the default. In a demo the founder's areas and stage are part of the script and cannot be changed;
  the hours can.
- **After planning,** every member joins with its first task, and a member with no work leaves before anything starts.

**Why.** A founder should be able to ask "why are you confident this is the team?" and get an answer backed by
checks, and pay for no seat that does nothing. AI models, like managers, tend to hire too many; the challenge and
the limits push back. The founder's time is the promise, so the checks run by themselves.

**How.** `seats.py` (`owners`, `cards`, `apply_challenge`, `lean`, `why`, `work_check`); the challenger's prompt is
`ModelSource.challenge` in `intelligence.py`. In the demos the lean team is shown but not run, because each script
plans the recommended team; in live mode Cynqra plans whichever team the founder chooses.

## How the team works together

**What.** The run moves in **rounds**. In each round:

- **every team member with work it can do now takes one piece of it**, and they all work at the same time; a member
  does one thing at a time;
- **cofounders run their areas.** Each one hands out its team's work with a **Handoff**, answers its team's doubts,
  reviews its team's work after Cynqra's checks and before it counts (approve, or send it back with what to change),
  and brings the founder only the decisions a founder should make. A cofounder's own work comes straight from the approved plan;
- **when a member has a doubt**, it raises a **Blocker** to its cofounder, or to the colleague whose field it is
  (Bluedip: the Backend Engineer asks the Revenue Management Specialist which food cost to use; the Frontend Engineer
  asks the CTO what a new restaurant sees before it has history), who answers in the next round while the others
  keep working;
- **a team member's proposal reaches the founder through its cofounder** (Bluedip: DevOps proposes going live, the CTO
  endorses it);
- **only real decisions go to the founder:** the ones that cannot be undone, such as money, law and going live. A
  decision that can be undone (a merge, a product rule outside money and law) is settled by the cofounder accountable
  for it, recorded like the founder's, and the founder is told. A cofounder settles only what it approved in its review or
  proposed itself; a rule whose subject is unclear, or proposed by the CFO or the Chief Compliance Officer, goes to
  the founder. A governance setting (`cofounders_settle_reversible`) sends
  every decision to the founder instead.

**Why.** Working one at a time made real runs take hours; a real company does not wait for one person to finish
before the next starts. Each cofounder knows its area best, so it hands out, answers and reviews there, and the founder
is left with only the founder's questions. A cofounder may send the same work back twice; after that Cynqra's checks decide and the
cofounder's concern stays on record in the handover, so a disagreement never stalls the company.

**How.** The slow part, the AI thinking, runs in parallel. Saving results, spending money and logging run one at a
time, so the records always stay consistent. Models on one laptop take turns (a laptop runs one model at a time);
online models run truly in parallel. Up to `parallel_workers` members (default 6) think at once. Messages between
members are structured, hashed objects (Handoff, Blocker, Review, Escalation, Approval) with fixed fields:
`protocol.py`.

## The team

**What.** The team always follows the idea. Nothing is there by default. The founder leads the company; Cynqra has no AI
founder.

| Kind | Roles | Who leads them | Code |
| --- | --- | --- | --- |
| Cofounders | CTO, Chief Product Officer, CFO, and a Chief Compliance Officer for a regulated business (payments, lending, insurance, health, children's data). A simple tool may need two; Bluedip has three. | They report to the founder | `roles.py` |
| Product | Project Manager, Product Designer, Market Analyst, Growth Marketer | Usually the Chief Product Officer | `roles.py` |
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
| **The provider's side** | Outage, timeout, too many calls | The member waits and tries again; the rest of the team keeps working. If the founder named a fallback for that AI, it stands in; otherwise Cynqra asks the founder once whether a stand-in may cover the wait, with its price. The member returns to its own AI as soon as that AI answers again. | **No** |
| **The account** | No credit left, key refused | The members on that account wait. The founder is asked to top up or fix the key; the work then continues where it stopped. | **No** |
| **The AI itself** | Work fails its checks three times; replies keep running out of room or breaking the rules; its measured record falls too low; a new version fails its check | The AI cannot do this role's work. Cynqra picks a better one that passes a check on this kind of work first, and **tells the founder** why, which AI now does the work, and its price against the old one. If no better AI fits the budget, the founder decides. | **Yes** |

**Why.** Replacing a capable AI for a provider's outage throws away its record; a better AI usually costs more, so
the founder must know.

**How.** The member keeps its identity, role, history and files in every case; only the AI behind it changes.
Notices to the founder ("What Cynqra told you") are not decisions: nothing waits on them. They are on the Workforce
screen and in the handover. `replacement.py` (`diagnose`, `model_failed`, `evaluate`, `inform`).

## The checks

**What.**

| Work | How it is checked | Code |
| --- | --- | --- |
| Code | All tests re-run in a clean copy, plus the delivery contract (the app starts, answers its health and smoke checks) | `verifier.py`, `testrunner.py` |
| Prediction models | Their tests, then the platform's own backtest on days the model has not seen, against a simple baseline (last week's numbers) | `verifier.py` |
| Documents | The sections their type needs; foundation documents must mark their assumptions and list at least one source where they have a Sources section | `verifier.py`, `roles.DOC_TYPES` |
| The financial model | Its numbers block is read, every input must say whether it is an assumption, measured or sourced, and every figure that follows from the inputs is recomputed; a figure more than 2% off is sent back with the right one | `numbers.py` |
| Merges and going live | Tests on the release candidate; the CTO settles the merge (it can be undone) and every test reruns on main; the founder approves going live; health and smoke checks after going live, with automatic rollback | `deploy.py`, `execution.py` |

**Why.** Nothing counts as done on a worker's word. In the Bluedip demo the checks catch three mistakes before they
count: a forecast worse than last week's numbers, a financial model whose value of a restaurant did not follow from
its own inputs, and an estimate that ignored the owner's cap.

**How.** A failed check goes back to the worker with the failure named. Three failures, and Cynqra looks for a
better AI or brings it to the founder.

## The guesses behind the idea

These are kept in the record and in the downloaded handover; the screens leave them out, because Cynqra is
responsible for the product and the business stays with the founder.

**What.** Every idea rests on guesses: that people want it, that it makes money, that it can be built. Cynqra lists
them riskiest first, each with the requirements whose work tests it. At the roadmap gate it says when each is first
tested, and says plainly when a high-risk guess is tested only at the end. A guess only a person can test (showing
the app to customers) becomes a prepared next step for the founder, and desk work never counts as proof of it. Two
or three measures of success, each with a target and a line below which to rethink, go into the handover.

**Why.** Most new companies fail because they built something too few people wanted, or could not make money from
it. Testing the riskiest guess first, before money goes into what depends on it, is the cheapest protection there
is.

**How.** `objective.py` (`assumptions`, `measures`), `planner.py` (`assumption_tests`), `delivery.py`
(`company_pack`).

## Money

**What.** Everything is priced in US dollars: AI calls from their real token counts, machine time, infrastructure and
checks. Every task has a budget. **Why:** one currency the founder understands, and a hard stop. **How:** at the
project's cap, a breaker stops all work until the founder decides. `budget.py`, `settings.py`.

## Audit, rework and refine

**What.** When the product is delivered, the Product screen shows the audit: each requirement of the original
objective, the work linked to it, and whether that work was verified, with the number of tests that pass in the live
release. The founder can **accept** the product, or write what should change and **rework** it, with more budget if
needed. A rework turns down the delivery with that note and starts a new cycle: the same team plans only the new
work, the founder approves its plan and budget once, and it is built, checked and released like the first. Cynqra can
also check that the live product is up.

**Why.** The founder came for a product that meets their objective. The audit shows exactly how the product answers
it, and a rework keeps going until it does, without starting over.

**How.** `engine.py` (`audit`, `rework`, `start_cycle`, `check_live`), `lessons.py` (after every accepted delivery
Cynqra keeps a short lesson, and the next team proposal for similar work shows that track record). In the demos, only
the candidate tracker has a scripted second cycle; in live mode the team plans any rework.

## The record

**What.** Every action, decision and handoff is an event in an append-only log. **Why:** any task can be replayed and
audited, so the founder can see how any result came about. **How:** `db.py`, `delivery.py` (`replay`).

## The screens and the apps

| Part | Code |
| --- | --- |
| Web screens, and the guide that explains each step | `poc/ui/app.js`, `poc/ui/tour.js`, `poc/ui/app.css` |
| HTTP API behind them | `server.py` |
| Desktop app (window, local models via llama.cpp) | `poc/desktop.py`, `runtime.py`, `desktop/` |
| Demos (scripted, free): Bluedip (opens first), a candidate tracker, a restaurant covers forecast | `poc/scenarios/` |
