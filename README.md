# Cynqra

**Describe the company you want to build. Cynqra assembles the expert team it needs, checks every piece of their
work, and asks you only what a CEO should decide.**

| | |
| --- | --- |
| **What** | An expert team on demand, for any idea, built the way a founder builds a real company. You are the CEO. Cynqra proposes the cofounders your company needs, each cofounder chooses the team for its area, and each member gets the best AI for its job. You receive the Company Pack: the foundation documents, the product, your decisions and what it cost. |
| **Why** | Building a product has become cheap. Knowing what a real company needs, and trusting AI work you cannot judge yourself, has not. With a single AI chat you must know what to ask and check every answer; with Cynqra, the team does, and the work is checked before it counts. |
| **How** | You describe the company. Cynqra proposes your cofounders, each cofounder chooses its team, and you approve the whole organization once, then the plan and budget. Cofounders run their areas: they hand out their team's work, answer its doubts and review it after an independent check. You decide only the real choices: money, risk, going live. |

## See it: the Bluedip demo

A founder describes **Bluedip**, an app that predicts a restaurant's footfall and revenue hour by hour and estimates
what an offer will do before the owner runs it. Cynqra proposes three cofounders: a CTO, a Chief Product Officer and
a CFO. The CTO builds a team of a Data Scientist, Backend and Frontend Engineers, DevOps and QA; the Chief Product
Officer a Project Manager, a Designer, a Market Analyst and a Restaurant Revenue Management Specialist; the CFO a
Legal and Compliance Advisor. They lay the company's foundation, build and check the models and the app, and put it
live.

In the live app, the owner's own idea, 50% off for at most 15 customers from 1 pm to 4 pm, turns out to raise revenue
and **lose money after food cost**, because customers who would have come anyway pay half too. Bluedip recommends 20%
off, which **earns money**. That is the depth a single AI chat does not give a founder: the right experts, and
numbers you can check.

## Read these, in order

| # | Document | What it answers | Time |
| --- | --- | --- | --- |
| 1 | [docs/1_VISION.md](docs/1_VISION.md) | What Cynqra is, why it exists, how it works, for whom | 5 min |
| 2 | [docs/2_HOW_IT_WORKS.md](docs/2_HOW_IT_WORKS.md) | How a project runs, step by step, why it is built that way, and where each step is in the code | 10 min |
| 3 | [docs/3_STATUS_AND_ROADMAP.md](docs/3_STATUS_AND_ROADMAP.md) | What works today, what is proven, what comes next and why in that order | 5 min |
| 4 | [docs/4_RUN_AND_TEST.md](docs/4_RUN_AND_TEST.md) | How to run it, test it and build it, and what each run proves | 5 min |
| 5 | [docs/5_DECISIONS.md](docs/5_DECISIONS.md) | What is settled, and why | 5 min |

## The repository

| Folder | What is in it |
| --- | --- |
| `poc/` | The product: the engine (`poc/cynqra/`), the screens (`poc/ui/`), the demos (`poc/scenarios/`), the tests (`poc/tests/`) |
| `desktop/` | Builds the installable app for Windows, macOS and Linux |
| `.github/workflows/` | The automatic checks and the real-AI test runs on GitHub |
| `archive/` | History only: earlier plans, notes and experiments. Not needed to work on Cynqra |

## Start in one minute

```
python3 poc/run_poc.py
```

A browser opens. Choose **Demo** and press **Make it a brief**: the Bluedip project runs from the founder's words to a
live app, with nothing to install or pay for. The guide at the bottom of the screen says what is happening at each
step, and why.
