# STATE OF PLAY

As of 25 August 2026, 23:00 India time. Written for the incoming CTO.
This file is deliberately blunt. Comfort belongs in a pitch deck, not a handover.

## Timeline, day 0 to today

**23 August. The documents.**
A single product requirements document was turned into a canon: one doctrine book plus
four execution books. Three release rounds, v1.0 to v1.2, each one audited for gaps a
real team would trip over. Output is in `04_prior_builds/` and `00_canon/`.

**24 August. The kit, and the first run.**
A paper harness was built so a fake organization could be run by hand: event log,
protocol templates, spike briefs, the S1 corpus with its expected answers. Then run 001
of the Wizard of Oz exercise.

**Run 001 is void.** Two reasons, both recorded. The whole thing executed inside one
process, so the coordination it claimed to measure never happened. And the candidate
tracker, which is only a test fixture, was presented as if it were the Cynqra product.
The void notice is in `01_history/run_002/VOID_RUN_001.md`. Three artifacts survived
because they were independently valid: two founder interventions and one golden set.

**25 August. Run 002, then G0, then the spikes.**
Run 002 was executed properly across ten days of script, with real separation between
workers. It closed **NO-GO on M2**, and that verdict stands. Measured: founder
interventions that count, 2. Protocol objects per verified task, 3.0. Verification catch
rate 0.4, which missed its bar, on a sample of five, mechanical only.

Then the G0 ratification session. Thirty decisions, D-1 through D-30, are now all closed.
That includes the hard one, D-22, on whether an immutable event log can coexist with a
legal duty to delete personal data. The answer chosen was Hybrid: events carry references
only, personal data lives in erasable stores, destroying a company key is the fallback.
Counsel has not confirmed it. There is no lawyer yet, and that item now waits at a gate
before the first paying company.

Then the spike harness was rebuilt as real code, and S3 was scored.

## What is actually proven

**S3, at the mechanical tier only: 9 of 10, bar was 0.8.** It catches nine seeded defects
including four specification defects. It misses one, `s3_06`, a failing write that gets
reported as success. That miss is real and it is the most dangerous class of bug in this
whole system, because it is the machine version of lying about progress.

This result reproduced after a scare on the evening of 25 August, which is the only reason
it is worth quoting.

**The protocol discipline holds.** Across run 002, coordination stayed as structured
objects and did not degrade into chat. That is the mechanism Book 1 relies on to stop
coordination cost from exploding, and it survived contact with a real run.

**The organization caught its own cheating twice.** Once when the day 6 scorer was found
reading the seed labels it was supposed to be detecting. Once when the S1 runner was found
not using the model adapter at all, meaning an API key would have produced filler output
labelled as a model result. Both are fixed. Both are in the record.

## What is not proven, and you should assume the worst until it is

**S1 is unrun.** Not failed. Unrun. There has never been a real model call, because the
founder has a chat subscription and the build environment had no network egress. The
harness is ready and refuses to score without a model.

**S2 is unrun.** Same reason, and it cannot be carried by hand because it is the cost
measurement. The estimate it will be judged against is locked and dated.

**S3 above the mechanical tier does not exist.** Book 2 specifies a second model for
MEDIUM risk and a human for HIGH risk. Neither is built. Do not quote 9 of 10 as if S3
is done.

**Nothing has been built.** There is no runtime, no dashboard, no worker container, no
event store, no policy engine. Everything in `02_harness/` is measurement scaffolding, not
product. Any impression of progress toward a shipping system would be false.

**No design work exists, deliberately.** Book 4 puts a designer at week six. The rule
held: no dashboards until a run breaks in a way that proves paper cannot carry the
protocol.

## The blocker, stated plainly

The project is one person in a browser. Every remaining M1 step needs someone who can run
code on a machine that persists, hold an API key, and own a repository. The hire order in
Book 4 already says founding engineer or CTO first. That is you, and the plan has been
waiting on you rather than on any technical unknown.

## Your first decisions

1. Run S1 and S2. Two commands, roughly an hour, a few cents of tokens. Then write the go
   or no go on M2 in Book 4. That is the gate.
2. Fix `s3_06` or consciously accept it. A failing write reported as success will poison
   every verification claim above it.
3. Rule on the ADRs in Book 2. Twelve of them are still marked proposed, which is honest,
   but they are yours to decide now, and M2 needs at least the runtime isolation, event
   store and policy engine calls made.
4. Put this folder in git today.

## Things that will look strange, and why they are correct

A candidate tracker keeps appearing. It is a chew toy, not the product.

A run is marked void with its data intact. That is on purpose. Deleting a bad run hides
the lesson.

Some scripts refuse to run and exit with an error rather than a number. That is the most
important behavior in the repository.

The decision log contains decisions to do nothing: no price, no brand spend, no
cross-tenant learning. A recorded decision not to act is still a decision, and it stops
the same argument being reopened weekly.
