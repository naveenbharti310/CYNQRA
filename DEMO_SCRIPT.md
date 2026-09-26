# Giving the Cynqra demo

How to show someone how Cynqra works, end to end, in about five minutes. Nothing to install
for the first two ways.

## Three ways to run it

| Way | When | How |
| --- | --- | --- |
| The link | Sending it, or presenting from any browser | https://claude.ai/artifact/MDLWXXQu2sFDfLK7SUQdiD. It is private: open it, press Share, and give access to the people you send it to. |
| The file | No internet, or a projector laptop | Double click `03_pages/how-cynqra-works.html`. Same page, works offline in any browser. |
| The app itself | Someone asks to see it run for real | Double click `RUN_POC.bat` (needs Python). Demo mode runs the same journey live; the guide bar at the bottom explains each step as it happens. With an Anthropic key set, Live mode builds the audience's own idea. |

The link and the file are a recorded run of the real engine, replayed through the real
screens. Next and Back step through it (or the arrow keys); Play runs it on its own. The
buttons on the screens work too: Structure, Confirm and Approve move the story forward, and
you can click any tab at any step.

## The talk track

The bottom bar says what is happening at every step, so you can read it or say it in your
own words. These are the moments to slow down on.

| Steps | What to say | What to point at |
| --- | --- | --- |
| 1 to 3 | "I write one sentence. Cynqra turns it into an objective, then proposes a team and a plan. I approve twice, that is all the setup." | The two amber inferred fields. The Verification Service sitting outside the team. |
| 4 to 8 | "From here the workers run. They never chat: every message is a structured object." | The protocol tape on the right of Work. |
| 9 | "The objective never said what stuck means. The PM will not guess, so this comes to me." | The rule card: problem, recommendation, evidence, what would change it. |
| 13 to 16 | "Engineer A says done. Verification disagrees: a test fails. It goes back, gets fixed, passes. I was never asked." | The red rework note on the card, then Verified after rework. |
| 18 and 19 | "Engineer B hits a question and raises a Blocker instead of inventing a login. The PM answers it. Still not me." | The Blocker and the Handoff that answers it on the tape. |
| 27 | "The CTO asks me to approve the production deploy, and also tried to email the recruiters. Workers may never send external messages, so policy stopped it before it went out." | The red DENIED box on the deploy card. |
| 29 to 31 | "It is live. Ten stages, every one checked. I accept, and I can take everything with me." | The ten stage stepper on Delivery. |
| 32 to 36 | "This is the product they built. Every step can be replayed. Authority is written down. Six decisions from me in total." | The product picture, the 8 of 8 replay, the Company tiles. |

Step 36 opens the two runs with a real model; "See it with a real model" at the bottom of
the page opens them at any time.

## Questions you will get

**Is this real, or a mock-up?** The engine is real. In this recording the workers' words
come from a prepared script, which the Demo label says on every screen. Everything else
really happened: the code was written to disk, its tests ran, it was merged, deployed and
used, and every record was produced by the engine. The same engine then ran twice with a
real Claude model writing every word, on a bakery order tracker and a dog walking tracker
it had never seen, and both went live (`poc/live_reports/`).

**What does it cost to run?** Not measured yet. Those real model runs could not count
tokens exactly. Spike S2 measures cost per task and needs an API key on about ten dollars of
credit. Say it is unmeasured; do not quote a number.

**What can it build today?** Small internal web apps: a store, a page, tests, a deploy to
one machine, with a fixed team of four. That is the first product category the plan commits
to. Larger organizations, other kinds of work and real cloud hosting come later.

**What stops it from doing something dangerous?** Every action goes through one gateway
with a written policy. Anything not listed is refused. Some actions (external messages,
money, legal commitments) are prohibited for every worker. Medium and high risk actions wait
for the founder. There is a budget cap and a kill switch that freezes everything at once.

**How is this different from a coding assistant?** A coding assistant is one worker. Cynqra
is the organization around the workers: roles with authority, work handed over as
structured objects, verification kept separate from the people doing the work, decisions
routed to the founder only when they need a founder, and a record of all of it.

**What happens next?** M1 closes on two measurements, S1 (can a model structure a messy
objective) and S2 (what the organization costs per task). Both need an API key. Then M2
builds the real runtime: isolated workers, a proper event store, the policy engine.

## Rebuilding the demo

After changing the app or the narration:

    python poc/demo/record_replay.py    records a fresh run of the real engine
    python poc/demo/build_demo.py       rebuilds 03_pages/how-cynqra-works.html

Then republish `poc/demo/out/how-cynqra-works.artifact.html` to the same link.
