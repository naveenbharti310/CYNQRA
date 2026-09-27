# CYNQRA HANDOVER

> To run Cynqra for real: install the desktop app for Windows, macOS or Linux from
> https://github.com/naveenbharti310/Passway/releases and follow CYNQRA_DESKTOP.md. It runs an
> open-source model on the laptop itself; no API key, nothing else to install.

> 26 September 2026: read M1_RESTART_26SEP2026.md first. It supersedes
> STATE_OF_PLAY.md, which is kept as the 25 August record.
>
> The working POC (D-36) is in poc/. Double click RUN_POC.bat to see it, or watch
> Cynqra_POC_demo.mp4. Start with poc/README.md. It is a demonstration, not gate evidence.

Prepared 25 August 2026 for the incoming CTO or founding engineer.
Prepared by the founder, Naveen Bharti, with an AI assistant doing the writing and the harness code.

Read this file, then RUNBOOK.md, then STATE_OF_PLAY.md. That is about thirty minutes
and it is enough to start work. The canon itself is longer and you read it in order.

## What Cynqra is, in one paragraph

Cynqra is a system that takes a human objective and builds, runs and changes the
organization needed to reach it. A founder says what they want. Cynqra assembles the
workers, gives them authority, coordinates them, verifies their output, and reports
what happened. The first product proves one narrow slice of that: a founder describes
a small web application, Cynqra synthesizes the organization it needs (in the two demos: a
CTO, a Project Manager and two engineers for a candidate tracker; nine workers, from a CEO
and a Data Scientist to DevOps and QA, for a restaurant covers forecast), and the founder
approves the workforce, the roadmap and only the other decisions that genuinely need a human. Since 27 September the build
follows Cynqra Product Flows and Architecture v1: see CYNQRA_PRODUCT_ALIGNMENT.md.

The candidate tracker you will see throughout this package is NOT the product. It is
the practice project the fake organization was pointed at, so we could watch the
organization fail. Read it as a test fixture.

## What is in this folder

```
START_HERE.md          this file
RUNBOOK.md             how to run everything on your machine
M1_RESTART_26SEP2026.md  where things stand now; supersedes STATE_OF_PLAY.md
STATE_OF_PLAY.md       the 25 August record: what was proven, what was not

00_canon/              the company documents, five books plus live status pages
02_harness/            the working tree exactly as it ran: spike runners, verifier kit,
                       protocol templates, the G0 material and the run 002 records
03_pages/              browser readable reports, open any of them by double click
poc/                   the working proof of concept: engine, UI, desktop app, mockups, tests
desktop/               builds the desktop app installers; CYNQRA_DESKTOP.md is the user guide
RUN_M1.bat             double click to run the M1 spikes, or the POC against a real model
RUN_POC.bat            double click to start the POC on Windows
```

The run records live under `02_harness/`. The verifier kit reruns its tests against the
files in `02_harness/run_002/`, so do not move that folder.

Removed on 26 September to keep the repository clean, all recoverable from the first
commit (`git show 29f8ca2:<path>`): `01_history/`, a reading copy whose 19 files were byte
for byte copies of originals in `02_harness/`; `04_prior_builds/`, three earlier release
zips, one identical to the PDFs in `00_canon/`, now kept by git history; `MANIFEST.txt`,
a 25 August file list that git now replaces; five HTML pages in `02_harness/` identical to
their copies in `03_pages/`; the run 002 export zip; and a server log.

## How to read the canon

In `00_canon/` you get both forms of the documents, and they are not duplicates.

The PDFs are the production build from 23 August. Book 0 is the doctrine and it is
the longest. Books 1 to 4 are the execution books. Read Book 0 first, all of it, then
Book 2 because you own it.

The files ending `_LIVE.md` are exports of the working pages as they stand today.
They are newer than the PDFs. Where they disagree, the LIVE file wins, because two
things happened after the PDFs were built: the G0 ratification session on 25 August,
which closed thirty decisions, and two real runs of the fake organization.

So: PDFs for the thinking, LIVE files for the current state of the decision log.

## Three rules this project runs on

These are not slogans. They have already cost us a full run, and keeping them is the
reason the remaining results are worth anything.

**One. A bar is set before the test, and it never moves afterward.**
S1 is 8 of 10. S3 is 80 percent of seeded defects. Those were written down before any
scoring happened. If a result misses, the result is wrong, not the bar.

**Two. An unrun test is not a passed test and not a failed test.**
The harness refuses to print a score when it has no model. Earlier it did print one,
using filler text, and that is exactly the bug described in STATE_OF_PLAY. If you find
any code path that invents a number, treat it as a defect of the highest order.

**Three. We void our own results when they are contaminated.**
Run 001 is void. It is still in this package, with the reason written on it. You are
inheriting a project that throws away its own good news, and you are expected to keep
doing that.

## What the founder can and cannot do

The founder is not an engineer, works from a browser, and has nothing installed. Every
deliverable so far has been either a document or a single HTML file that opens by double
clicking. That constraint is why `03_pages/` exists.

This matters for you: from your first day, you are the only person who can run code,
hold an API key, or operate a repository. Plan accordingly, and do not hand the founder
a terminal command.

## First hour, concretely

1. Read this file and RUNBOOK.md.
2. Run the preflight command in RUNBOOK.md. It tells you what is ready and what is blocked.
3. Read STATE_OF_PLAY.md and the two spike memos in `02_harness/spikes/`.
4. Put this whole folder in a private git repository, first commit, no edits. That is the
   durability rule we learned the hard way on 25 August.
5. Then run S1 and S2. Those two results decide whether M2 opens.
