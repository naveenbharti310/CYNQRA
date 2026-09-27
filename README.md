# Cynqra

**Your expert team, on demand.** You describe the company you want to build. Cynqra assembles the team it needs,
gives each member the best AI for its job, and the team works together, like a real company, to deliver it. You are
the CEO: you make only the decisions a CEO should.

## Read these, in order

| # | Document | What it answers | Time |
| --- | --- | --- | --- |
| 1 | [docs/1_VISION.md](docs/1_VISION.md) | What Cynqra is, for whom, and why it matters | 5 min |
| 2 | [docs/2_HOW_IT_WORKS.md](docs/2_HOW_IT_WORKS.md) | How a project runs, step by step, and where each step is in the code | 10 min |
| 3 | [docs/3_STATUS_AND_ROADMAP.md](docs/3_STATUS_AND_ROADMAP.md) | What works today, what is proven, and what to build next | 5 min |
| 4 | [docs/4_RUN_AND_TEST.md](docs/4_RUN_AND_TEST.md) | How to run it, test it and build it | 5 min |
| 5 | [docs/5_DECISIONS.md](docs/5_DECISIONS.md) | The decisions that are settled and must not be reopened without the founder | 5 min |

## The repository

| Folder | What is in it |
| --- | --- |
| `poc/` | The product: the engine (`poc/cynqra/`), the web screens (`poc/ui/`), the tests (`poc/tests/`) |
| `desktop/` | Builds the installable app for Windows, macOS and Linux |
| `.github/workflows/` | The automatic checks and the real-model test runs on GitHub |
| `archive/` | History only: earlier plans, notes and experiments. Not needed to work on Cynqra |

## Start in one minute

```
python3 poc/run_poc.py
```

A browser opens on the first screen. Choose **Demo** to watch a full project with nothing to install or pay for.
