# 5. Decisions

**What** this covers: the decisions that are settled. **Why** it matters: they keep Cynqra consistent as it grows,
and each one says why it was made, so nobody has to guess. **How** to use it: change a decision only with the
founder's explicit agreement, and record the change here.

## Product

| # | Decision | Why |
| --- | --- | --- |
| P1 | **The founder is the CEO.** Cynqra's AI roles report to them; no AI role is the CEO. | The founder owns the vision and the risk; AI roles advise and do the work, they do not own the company. |
| P2 | **The team always follows the idea.** No role is there by default. Expertise particular to the idea is a Specialist named from it. | A fixed team wastes money on roles an idea does not need and misses the expertise it does. |
| P3 | **The CEO decides only what a CEO should:** the team, the plan and budget, and real choices (scope, money, risk, merges, going live). | The founder's attention is the scarcest resource. |
| P4 | **Nothing counts as done on a worker's word.** Every piece of work passes an independent check. | AI output reads the same whether it is right or wrong; only a check tells them apart. |
| P5 | **Trust is the product.** Foundation documents separate sourced facts, assumptions, and what a professional must confirm. | A non-expert cannot judge a polished document; they can judge what is marked. |
| P6 | **Cynqra prepares real-world actions; the CEO does them** (registering, banking, signing, hiring). | Legal and financial acts need an accountable person. |
| P7 | **The measure of success** is how few times the CEO is needed, for a result that is checked. | It holds both halves of the promise: the CEO's time, and a result that holds up. |
| P8 | **One sentence, everywhere:** "Describe the company you want to build. Cynqra assembles the expert team it needs, checks every piece of their work, and asks you only what a CEO should decide." | A story told differently in each place sells nothing. |
| P9 | **The demo that opens first is Bluedip**: an app that predicts a restaurant's footfall and revenue and estimates what an offer will really do. The same idea is the objective of the real-model run. | It shows the depth of the idea (prediction models checked on unseen data, a field Specialist, a real money decision), and the real-model run then tests the same thing without a script. |

## How the team works

| # | Decision | Why |
| --- | --- | --- |
| T1 | **Everyone works at the same time.** Each round, every member with ready work takes one piece; a member does one thing at a time. | A real company works in parallel; one at a time made runs take hours. |
| T2 | **Members coordinate by Handoff (done) and Blocker (doubt)**, to the right colleague, not through the CEO. | The colleague who knows answers faster and better, and every exchange stays on record. |
| T3 | **AI thinking runs in parallel; recording results runs one at a time.** | Speed from parallel AI calls, without the records ever conflicting. |
| T4 | **Cynqra first finds out why a member stopped.** A provider outage or an account problem is not the AI's fault: the member waits (or a stand-in the CEO allowed covers the wait) and nothing is replaced. **Only an AI that cannot do the role's work is replaced**, by a better one that passes a check first, and **the CEO is told, with the price** of the better AI against the old one. The member keeps its identity, role and history. A new model version runs only after it passes a check. | Replacing a capable AI for a provider's outage throws away its record; a better AI usually costs more, so the CEO must know. |
| T5 | **US dollars are the only budget.** A breaker stops all work at the cap until the CEO decides. | One currency the CEO understands, and no surprise bills. |

## Intelligence

| # | Decision | Why |
| --- | --- | --- |
| I1 | **Worker, intelligence, provider connection and credential are four separate things.** A worker never holds a model or a key. | An AI can be swapped without touching the worker, and a key never travels with the work. |
| I2 | **Keys live only in the secrets layer** (an environment variable's name, or Cynqra's secrets file readable only by its owner). The gateway reads a key for one call at a time. | A log, a document or a report can never leak a key. |
| I3 | **The Intelligence Layer is part of Cynqra**, with its own records in Cynqra's database; not a separate service. | One product to install and to trust. |
| I4 | **Providers:** OpenAI-compatible, Anthropic and local/self-hosted are built. AWS Bedrock is planned, not built. | No dependence on one provider. |
| I5 | **Cynqra chooses the AI for each worker from measured results**, not from hand-made scores. | A model's own record on this kind of work predicts better than benchmarks or opinions. |
| I6 | **Hugging Face is one connection leading to many serving companies.** Cynqra records which company serves each model and always asks for that one. A change of company counts as a new version and is re-checked. | The same model from two companies can differ in price and behaviour; mixing them would corrupt the record. |
| I7 | **A Hugging Face subscription is a monthly credit, not unlimited use.** Cynqra's dollar budget governs spending. | The dollar budget stays the only control. |

## Engineering

| # | Decision | Why |
| --- | --- | --- |
| E1 | **Standard-library Python only.** | It runs anywhere, with nothing to install and nothing to break. |
| E2 | **The repository is private.** Heavy GitHub runs start only when asked. | The free minutes stay for when they matter. |
| E3 | **Every change keeps all tests passing** before it is pushed. | The whole flow keeps working after every change. |
| E4 | **Documentation is these five documents and the README**, each answering what, why and how. Anything historical goes to `archive/`, unchanged. | One place to read, and nothing stale to mislead. |
