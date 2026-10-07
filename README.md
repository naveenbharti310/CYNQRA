# Cynqra

**You bring the vision. Cynqra creates the organisation that can build it.**

## The story

The world has made intelligence cheap. Building a company is still expensive.

Anyone can ask one AI to design a product, another to write the code and another to test it. But someone still has
to work out what needs to be done, who should do it, which intelligence should do it and how they should work
together. Today that person is the founder, and that is where company building breaks down.

Cynqra starts from the founder's vision, not a prompt. It understands the product and what it takes to build it.
Then it understands the founder: their experience, their skills, what they can contribute. It asks one question:
**what organisation does this founder need around them to make this company possible?** A technical founder may not
need a CTO. A product founder may need engineering leadership. A domain expert may need product and technical
capabilities around them.

Cynqra builds that organisation, gives each role the right intelligence and runs the work. **Cynqra manages the
organisation. The founder manages the vision.** What the founder gets at the end is not an AI workforce. It is the
working product they came to build.

| Today | With Cynqra |
| --- | --- |
| Idea → find people → convince them → form team → coordinate team → choose technology → manage execution → build product | Idea → understand founder → construct organisation → orchestrate intelligence → build product |

**Anyone with a strong enough idea should be able to build a real company without first having to build the company
that builds it.**

## The journey, in seven steps

1. **Describe the idea.** What you want to build and the outcome you want.
2. **Approve the plan.** Cynqra shows what it will build, the capabilities it takes, the organisation it proposes,
   the timeline and an estimated budget.
3. **Define yourself.** Your background and what you lead yourself. Cynqra builds the organisation again around
   you: no seat for what you bring, and an area you lead gets no AI cofounder.
4. **Approve the team and budget.** The organisation fitted around you, and what it costs.
5. **Watch it being built.** The team works in the background. You are asked only what cannot be undone, such as
   putting the product live.
6. **Receive the working product.** Open it and use it, or download everything.
7. **Audit and refine.** Every requirement is checked against your original objective. Say what should change and
   Cynqra reworks it, until it meets the objective.

The founder should not have to become an AI workforce manager. Cynqra handles the complexity. The founder gets the
outcome. Cynqra is responsible for delivering that outcome within the budget; whether the business succeeds stays
with the founder. The full journey is in [docs/0_USER_JOURNEY.md](docs/0_USER_JOURNEY.md).

## See it: the Bluedip demo

A founder describes **Bluedip**: an app that tells a restaurant owner how many customers and how much money to expect
each hour, and what an offer would really do before trying it.

Cynqra proposes three AI cofounders: Imani Lindqvist, AI CTO; Wen Torres, AI Chief Product Officer; and Joaquín
Khalil, AI CFO. Each picks the team for their own area, every member with a name: engineers, a data scientist and a
tester; a project manager, a designer and a restaurant revenue specialist; a legal and compliance advisor. If an AI
in a seat cannot do the work, a new person takes the seat and you are told who left, who joined and why. A Security Expert the CTO asked for is cut before the founder sees the team, because
release 1 takes no payments and keeps no diner data. The team builds and checks the app and puts it live. The founder
is asked twice while it is built: one rule about money, and going live.

Then the owner tries their own idea in the live app: 50% off for up to 15 customers between 1 pm and 4 pm. Bluedip
shows that this brings in more sales but **loses money once food cost is counted**, because customers who would have
come anyway also pay half. It suggests 20% off instead, which **makes money**.

## Read these, in order

| # | Document | What it answers | Time |
| --- | --- | --- | --- |
| 0 | [docs/0_USER_JOURNEY.md](docs/0_USER_JOURNEY.md) | The seven steps every screen follows | 2 min |
| 1 | [docs/1_VISION.md](docs/1_VISION.md) | What Cynqra is, why it exists, the thesis, for whom | 5 min |
| 2 | [docs/2_HOW_IT_WORKS.md](docs/2_HOW_IT_WORKS.md) | How a project runs, step by step, why it is built that way, and where each step is in the code | 10 min |
| 3 | [docs/3_STATUS_AND_ROADMAP.md](docs/3_STATUS_AND_ROADMAP.md) | What works today, what is proven, what comes next and why in that order | 5 min |
| 4 | [docs/4_RUN_AND_TEST.md](docs/4_RUN_AND_TEST.md) | How to run it, test it and build it, and what each run proves | 5 min |
| 5 | [docs/5_DECISIONS.md](docs/5_DECISIONS.md) | What is settled, and why | 5 min |
| 6 | [docs/6_PHASED_ARCHITECTURE.md](docs/6_PHASED_ARCHITECTURE.md) | The authoritative architecture contract, phase by phase | 10 min |

## The repository

| Folder | What is in it |
| --- | --- |
| `poc/` | The product: the engine (`poc/cynqra/`), the screens (`poc/ui/`), the demos (`poc/scenarios/`), the tests (`poc/tests/`) |
| `desktop/` | Builds the installable app for Windows, macOS and Linux |
| `.github/workflows/` | The automatic checks and the real-AI test runs on GitHub |
| `archive/` | History only: earlier plans, notes and experiments. Not needed to work on Cynqra |

## Where it stands

The engine, the screens and the objective intelligence control loop are built and covered by 481 automated tests (`cd poc && python3 -m unittest discover -s tests -t tests`). On real hosted models (the free tiers of Google, NVIDIA, Groq and Mistral so far), the loop chooses an intelligence for each piece of work from evidence it gathers on that objective, and objectives have been delivered and accepted end to end; free-tier limits still stop many runs before delivery. Every real run, what it showed and what was fixed because of it is in [docs/3_STATUS_AND_ROADMAP.md](docs/3_STATUS_AND_ROADMAP.md); how to start one is in [docs/4_RUN_AND_TEST.md](docs/4_RUN_AND_TEST.md).

## Start in one minute

```
python3 poc/run_poc.py
```

A browser opens. Choose **Demo** and press **Make it a brief**: the Bluedip project runs through all seven steps, from
the founder's words to a live app, with nothing to install or pay for. The guide at the bottom of the screen says
what is happening at each step, and why.
