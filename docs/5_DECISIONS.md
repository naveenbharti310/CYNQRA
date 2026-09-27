# 5. Decisions

These are settled. Change one only with the founder's explicit agreement, and record the change here.

## Product

| # | Decision |
| --- | --- |
| P1 | **The founder is the CEO.** Cynqra's AI roles report to them; no AI role is the CEO. |
| P2 | **The team always follows the idea.** No role is there by default. Expertise particular to the idea is a Specialist named from it. |
| P3 | **The CEO decides only what a CEO should:** the team, the plan and budget, and real choices (scope, money, risk, merges, deploys). |
| P4 | **Nothing counts as done on a worker's word.** Every piece of work passes an independent check. |
| P5 | **Trust is the product.** Foundation documents separate sourced facts, assumptions, and what a professional must confirm. |
| P6 | **Cynqra prepares real-world actions; the CEO does them** (registering, banking, signing, hiring). |
| P7 | **The measure of success** is how few times the CEO is needed, for a result that is verified. |

## How the team works

| # | Decision |
| --- | --- |
| T1 | **Everyone works at the same time.** Each round, every member with ready work takes one piece; a member does one thing at a time. |
| T2 | **Members coordinate by Handoff (done) and Blocker (doubt)**, to the right colleague, not through the CEO. |
| T3 | **AI thinking runs in parallel; recording results runs one at a time**, so the records stay consistent. |
| T4 | **A failing AI is replaced; the worker keeps its identity, role and history.** A new model version runs only after it passes a check. |
| T5 | **US dollars are the only budget.** A breaker stops all work at the cap until the CEO decides. |

## Intelligence

| # | Decision |
| --- | --- |
| I1 | **Worker, intelligence, provider connection and credential are four separate things.** A worker never holds a model or a key. |
| I2 | **Keys live only in the secrets layer** (an environment variable's name, or Cynqra's secrets file readable only by its owner). The gateway reads a key for one call at a time. |
| I3 | **The Intelligence Layer is part of Cynqra**, with its own records in Cynqra's database; not a separate service. |
| I4 | **Providers:** OpenAI-compatible, Anthropic and local/self-hosted are built. AWS Bedrock is planned, not built. |
| I5 | **Cynqra chooses the AI for each worker from measured results**, not from hand-made scores. |
| I6 | **Hugging Face is one connection leading to many serving companies.** Cynqra records which company serves each model and always asks for that one. A change of company counts as a new version and is re-checked. |
| I7 | **A Hugging Face subscription is a monthly credit, not unlimited use.** Cynqra's dollar budget governs spending. |

## Engineering

| # | Decision |
| --- | --- |
| E1 | **Standard-library Python only**, so it runs anywhere with nothing to install. |
| E2 | **The repository is private.** Heavy GitHub runs start only when asked, to stay within the free minutes. |
| E3 | **Every change keeps all tests passing** before it is pushed. |
| E4 | **Documentation is these five documents and the README.** Anything historical goes to `archive/`, unchanged. |
