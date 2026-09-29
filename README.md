# Cynqra

**Describe the company you want to build. Cynqra assembles the expert team it needs, checks every piece of their
work, and asks you only what a CEO should decide.**

## The story

Say you want to start a company. In real life you would first find cofounders: someone to lead the technology,
someone to lead the product, maybe someone to look after the money. Each cofounder would then hire their own
people. As CEO you would not write the code or check every spreadsheet. You would make the big calls.

Cynqra works the same way, with AI experts in place of people.

1. **You describe your idea** in your own words.
2. **Cynqra suggests your cofounders** and tells you why each one is needed.
3. **Each cofounder picks a team** for their area. A CTO might pick engineers and a tester; a CFO might pick a legal
   advisor.
4. **You see the whole organization chart and approve it once.** Then you approve the plan and the budget.
5. **The team gets to work.** Cofounders hand out the tasks, answer their team's questions and review every piece of
   work. Cynqra also checks each piece on its own, for example by running the code's tests.
6. **You are asked only what a CEO should decide:** spending money, taking a risk, going live.
7. **At the end you get the Company Pack:** the founding documents, the working product, every decision you made and
   what it all cost.

## Why it matters

Building software with AI has become cheap. The hard part is knowing which experts a real company needs, and trusting
work you cannot check yourself. With a single AI chat you have to know what to ask and check every answer yourself.
With Cynqra the team asks the right questions, and every piece of work is checked before it counts.

## See it: the Bluedip demo

Here is the story above with a real example. A founder describes **Bluedip**: an app that tells a restaurant owner
how many customers and how much money to expect each hour, and what a discount would really do before trying it.

Cynqra suggests three cofounders, and each picks a team:

| Cofounder | Their team |
| --- | --- |
| CTO | a Data Scientist, a Backend Engineer, a Frontend Engineer, a DevOps Engineer and a QA Engineer |
| Chief Product Officer | a Project Manager, a Designer, a Market Analyst and a Restaurant Revenue Management Specialist |
| CFO | a Legal and Compliance Advisor |

Together they write the company's founding documents, build and check the app, and put it live.

Then the owner tries their own idea in the live app: 50% off for up to 15 customers between 1 pm and 4 pm. Bluedip
shows that this brings in more sales but **loses money once food cost is counted**, because customers who would have
come anyway also pay half. It suggests 20% off instead, which **makes money**. A single AI chat would not have told
the founder this. It took the right experts and numbers anyone can check.

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
