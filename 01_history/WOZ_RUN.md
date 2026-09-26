# Wizard of Oz run

Owner: CEO
Window: weeks 0 to 2, parallel with M1
Timebox: ten working days
Category: one real CRUD style project (D-6 remains Proposed)

Project name: ________________________________
Start date: ________________________________
End date: ________________________________

## What this run is

You play orchestrator. Off the shelf AI tools play the four workers:
CTO, PM, Engineer A, Engineer B. The platform Verification Service is you
plus a second model. Follow the canon. Do not invent a fifth worker.

## What done means

- A run report exists.
- The first golden sets exist for Book 2, section 11.
- Every broken step is written in breaks.csv as an engineering requirement.
- Founder interventions, token and time cost, and verification catch rate
  are measured.

## Ten day script

Day 1. Objective.
Write the messy founder sentence. Convert it into the structured objective
fields: product, target customer, primary outcome, business outcome,
success criteria, constraints, priorities. Confirm it yourself. Log
objective.created. Do not add fields.

Day 2. Organization and plan.
Instantiate the fixed template only. Write the first workstreams and tasks.
Each task needs owner, inputs, expected output, dependencies, tools, budget,
deadline, verification method, risk tier, status. Log organization.changed
and task.created.

Day 3. First LOW risk work.
Engineer A does sandbox work only: files, tests, branch. No production.
Verify LOW with automated checks. Log action.executed and verification.completed.

Day 4. First MEDIUM risk work.
Until D-17 is decided, every MEDIUM risk action comes to you. Merge,
preview deploy, package install, spend inside the task budget. Log the
Approval. Count the intervention.

Day 5. First cross worker dependency.
PM hands a spec to Engineer B, or Engineer A raises a Blocker that Engineer B
must clear. Use the protocol templates. The founder should not be in this
path. If you had to step in, write the break.

Day 6. Verification catch.
Seed at least five defects, including one non code defect (wrong spec,
missing constraint, bad copy). Record how many were caught before anyone
said verified.

Day 7. Budget and breaker drill.
Set a small company cap. Hit 50, 80, 95, then the hard cap. Confirm work
enters PAUSED. Log budget.threshold_reached.

Day 8. HIGH risk gate.
Attempt a production deploy or an external message. It must stop for your
approval. Reject one on purpose. Log decision.rejected.

Day 9. Export and replay.
Export the repo, the event log, the decision history, and the break list.
Replay one completed task from the log on paper. Write what you could not
reconstruct.

Day 10. Close.
Write the run report. Copy golden sets out of the best labeled decisions.
List every break as a requirement. Decide go or no go on starting M2.

## Measures

Use founder_interventions.csv. One row per action you take, excluding
reading. Approvals, rejections, requests for more evidence, and replies to
escalations all count.

Gaming check: if interventions fall while rework or escaped defects rise,
the week is unproven.

## What you must not do

- Do not add a fifth worker.
- Do not auto execute MEDIUM or HIGH risk work.
- Do not put personal data in event payloads.
- Do not treat D-6, D-17, or D-18 through D-30 as decided.
- Do not start dashboard design during this run unless a break says the
  paper protocol cannot be followed without a screen. If that happens,
  write the break. Do not open a design workstream.
