"use strict";
/* Plain words for what is on screen, from the same state the UI renders (GET /api/state).
   Used by the guide panel in the app and by the guided demo page (poc/demo), so a presenter
   and a first time viewer read the same explanation of each step. */
const CynqraTour = (() => {
  let WORKERS = [];
  const who = (id) => { if (id === "orchestrator") return "Cynqra"; const w = WORKERS.find((x) => x.id === id); return w ? `the ${w.title}` : id || "a worker"; };
  const Who = (id) => { const w = who(id); return w.charAt(0).toUpperCase() + w.slice(1); };
  const CH = { objective: "Objective", workforce: "Workforce", plan: "Roadmap and budget", work: "The organization works",
    decide: "Founder decision", live: "Live and handed over" };

  function task(st, id) { return (st.tasks || []).find((t) => t.id === id) || {}; }
  function lastVerification(st, id) { return (st.verifications || []).filter((v) => v.task_id === id).slice(-1)[0] || {}; }
  function pending(st) { return (st.decisions && st.decisions.pending) || []; }
  function decisionsSoFar(st) { return (st.metrics && st.metrics.founder_interventions) || 0; }

  function forDecision(st, d) {
    const n = decisionsSoFar(st) + 1;
    if (d.kind === "approve_workforce" || d.kind === "approve_roadmap") return null;
    if (d.kind === "decision") return { chapter: CH.decide, view: "decisions", title: "A product rule needs the founder",
      body: `The objective never says this, so the PM will not guess: "${d.problem}" The PM proposes a rule with its evidence, confidence and what would change it. Product rules are MEDIUM risk, so the founder decides. This is founder decision ${n}. The founder can approve, edit the rule first, reject with a reason, or ask for more evidence.` };
    if (d.kind === "review_merge") {
      const tests = (d.evidence_refs || []).find((e) => /tests on the release candidate/.test(e)) || "every test ran on the release candidate";
      return { chapter: CH.decide, view: "decisions", title: "The CTO proposes merging the release",
        body: `Before asking, the CTO ran the release candidate's tests: ${tests}. Merging to main is MEDIUM risk, so it comes to the founder. This is founder decision ${n}.` };
    }
    if (d.kind === "deploy") {
      const side = d.extra && d.extra.side_action;
      return { chapter: CH.decide, view: "decisions", title: side ? "A production deploy, and policy stops an email" : "The CTO proposes the production deploy",
        body: "The deployment service already built, tested, packaged and previewed the release. Production deploys are HIGH risk, so the founder approves every one. " +
          (side ? `The CTO also tried to send an email: "${side.summary}" External messages are prohibited for every worker, so policy denied it before anything was sent. The founder only sees that it was stopped. ` : "") +
          `This is founder decision ${n}.` };
    }
    if (d.kind === "accept_delivery") return { chapter: CH.live, view: "delivery", title: "Every task verified, the product is live",
      body: `Cynqra writes a transition record: the problem, what changed, the evidence, the cost and the founder's interventions. The export bundle holds the repository, the decisions, the event log and the configuration, so nothing is locked in. Accepting is founder decision ${n}.` };
    if (d.kind === "escalation") return { chapter: CH.decide, view: "decisions", title: "A worker escalated to the founder",
      body: `${d.problem} Workers escalate only what they cannot resolve, and each day has an escalation budget. The founder can retry the task or stop the run.` };
    if (d.kind === "budget_breaker") return { chapter: CH.decide, view: "decisions", title: "The budget cap stopped the work",
      body: "Spending reached the cap the founder set, so every worker is paused. Only the founder can raise the cap or stop the run." };
    if (d.kind === "objective_change") return { chapter: CH.decide, view: "decisions", title: "The objective changed mid run",
      body: "Changing the objective pauses the run and shows what it affects. Verified work stays; open tasks continue against the new version once the founder confirms." };
    return { chapter: CH.decide, view: "decisions", title: "A decision needs the founder", body: d.problem || "" };
  }

  function narrate(st) {
    if (!st || !st.meta) return null;
    WORKERS = st.workers && st.workers.length ? st.workers : ((st.proposal || {}).workers || []);
    const m = st.meta, last = st.last_step || {}, t = task(st, last.task);
    const obj = st.objective, pend = pending(st).filter((d) => !d.in_digest);
    if (m.frozen) return { chapter: CH.work, view: "work", title: "Kill switch on: every worker is frozen",
      body: "Every action is refused by policy until the founder releases the kill switch. An answer that arrives from a model while it is on is discarded." };
    if (m.phase === "new") return { chapter: CH.objective, title: "A founder says what they want",
      body: "Cynqra starts from the outcome in the founder's own words, a budget and any constraints. The founder does not name a team. From this Cynqra determines the organization, the intelligence for each worker, the roadmap and the budget." };
    if (m.phase === "objective") return { chapter: CH.objective, title: "One sentence becomes a structured objective",
      body: `The Objective System turns the sentence into seven fields: product, customer, outcomes, success criteria, constraints and priorities. ${obj && obj.inferred_fields.length ? `${obj.inferred_fields.length} of them were inferred and are marked, so the founder can check exactly those.` : ""} The founder sets the dollar budget and any constraints, then submits. Cynqra decomposes it into requirements and synthesizes the workforce.` };
    if (m.phase === "workforce") {
      const p = st.proposal || {}, req = st.requirements || { requirements: [] };
      return { chapter: CH.workforce, title: "Cynqra proposes the workforce the objective needs",
        body: `The objective became ${req.requirements.length} requirements. From its role catalog the Workforce Synthesizer proposes ${(p.workers || []).length} workers: ${(p.roles || []).map((r) => `${r.role} x${r.quantity}`).join(", ")}, each with the reason it is needed and the requirements it covers. The founder approves the organization, or rejects it with feedback and Cynqra revises it. This is the first approval gate.` };
    }
    if (m.phase === "planning") return { chapter: CH.plan, title: "The roadmap and the budget",
      body: `Every worker now has an intelligence chosen for its work, and one model can power several workers. The Execution Planner broke the objective into ${((st.plan || {}).milestones || []).length} milestones and ${(st.tasks || []).length} tasks, each with an owner, the worker accountable for it, acceptance criteria and a verification gate the platform sets. The Budget Engine priced it in layers against the hard cap. This is the second approval gate.` };
    if (m.phase === "stopped_error") return { chapter: CH.work, view: "work", title: "The model failed, and nothing was invented",
      body: "A model or network error stops the step. Cynqra does not fill the gap with made up output. The founder presses Try the same step again once the model is reachable." };
    if (m.phase === "stopped") return { chapter: CH.work, view: "work", title: "The founder stopped the run", body: m.notice || "" };
    if (m.phase === "accepted") return { chapter: CH.live, view: "company", title: "Delivered and accepted",
      body: `${decisionsSoFar(st)} founder decisions in total. Everything else, including ${st.metrics.defects_caught_before_verified} defect caught, ${st.metrics.blockers_cleared_without_founder} Blocker cleared and ${st.metrics.actions_stopped_by_policy} action stopped by policy, was handled by the organization and recorded as it happened.` };
    if (pend.length) { const n = forDecision(st, pend[0]); if (n) return n; }
    if (last.did === "roadmap approved") return { chapter: CH.work, view: "work", title: "The organization starts work",
      body: "From here the founder does nothing unless a decision needs them. Workers pass work to each other as protocol objects, shown on the protocol tape. Every action goes through the Tool Gateway: identity, policy, budget, the action itself, then the audit record." };
    if (last.did === "approved") {
      const title = { decision: "The founder decided the rule", review_merge: "The founder approved the merge", deploy: "The founder approved the production deploy" }[last.kind] || "The founder approved";
      const body = { decision: "The rule becomes company memory: it is written to DECISIONS.md and every later task receives it, so no worker has to guess it again.",
        review_merge: "The CTO merges the release candidate to main, and every test runs again on main after the merge.",
        deploy: "Only now does the release go to production: deploy, health check, smoke test, then live. A failed check rolls back automatically." }[last.kind] || "";
      return { chapter: CH.decide, view: "work", title, body };
    }
    if (last.did === "assigned") return { chapter: CH.work, view: "work",
      title: `${Who(t.handoff_from || "orchestrator")} hands ${t.id} to ${who(t.owner_worker_id)}`,
      body: `${t.title}. The Handoff carries the inputs, the artifacts and the acceptance check. Workers never chat: a message that is not a valid protocol object is refused.` };
    if (last.did === "completed" && t.attempts) return { chapter: CH.work, view: "work", title: `${Who(t.owner_worker_id)} fixes ${t.id} and resubmits`,
      body: "The engineer saw the failing test and its output, and sent a corrected version. It still counts for nothing until verification runs every test again." };
    if (last.did === "completed") return { chapter: CH.work, view: "work", title: `${Who(t.owner_worker_id)} says ${t.id} is done`,
      body: `Completed is a claim, not a result. ${(t.outputs || []).map((o) => o.file).join(", ")} sit in the worker's own workspace until the Verification Service checks them.` };
    if (last.did === "rework") {
      const v = lastVerification(st, t.id), failed = (v.checks && v.checks.failed) || [];
      return { chapter: CH.work, view: "work", title: "Verification caught a defect",
        body: `${Who(t.owner_worker_id)}'s work on ${t.id} failed ${failed.length ? failed.join(", ") : "its checks"}. It goes back to the engineer with the failure named, and it is not marked verified. The founder is never asked; catching this is verification's job.` };
    }
    if (last.did === "blocked") return { chapter: CH.work, view: "work", title: `${Who(t.owner_worker_id)} raised a Blocker instead of guessing`,
      body: `"${(t.blocker || {}).description || ""}" Guessing here would build the wrong product. The Blocker goes to ${who((t.blocker || {}).needs_from)}, not to the founder.` };
    if (last.did === "blocker_cleared") {
      const a = (t.answers || []).slice(-1)[0] || {};
      return { chapter: CH.work, view: "work", title: `${Who(last.by)} cleared the Blocker without the founder`,
        body: `Answered from the objective and the rules already decided: "${a.acceptance_check || ""}" The founder was not interrupted.` };
    }
    if (last.did === "verified") {
      if (t.kind === "spec") return { chapter: CH.work, view: "work", title: "Verification checks the spec against the objective",
        body: "A coverage check derived from the confirmed objective: every constraint must be addressed and the success criteria covered. It passed, so the documents join the repository." };
      if (t.kind === "code") return { chapter: CH.work, view: "work", title: t.attempts ? `The fix passes: ${t.id} verified` : `${t.id} verified`,
        body: `Verification ran every test in the repository, including the earlier tasks' tests${(lastVerification(st, t.id).method || "").includes("delivery contract") ? ", and started the app to check it serves its page" : ""}. Only now is the code integrated.` };
      if (t.kind === "decision") return { chapter: CH.decide, view: "work", title: "The rule is part of the company's memory",
        body: "Written to docs/DECISIONS.md and passed to every later task." };
      if (t.kind === "review_merge") return { chapter: CH.decide, view: "work", title: "Merged, and main passes every test",
        body: "Main now holds the release candidate, and its full test suite ran again after the merge." };
      if (t.kind === "deploy") return { chapter: CH.live, view: "delivery", title: "Live: ten stages, each one checked",
        body: "Build, test, package, preview, verify, founder approval, deploy, health check, smoke test, live. The product is running and answering on its own address." };
    }
    if (last.did === "delivered") return forDecision(st, { kind: "accept_delivery" });
    if (last.did === "paused") return { chapter: CH.work, view: "work", title: "Paused", body: "The answer arrived after work was paused, so it was set aside. Nothing was lost." };
    if (last.did === "replaced" || last.did === "rerouted") return { chapter: CH.work, view: "workforce", title: last.did === "replaced" ? "A worker's intelligence was replaced" : "A task was rerouted to a peer",
      body: "The Performance Engine's evidence crossed a threshold, so the Replacement Engine weighed the alternatives, ran a regression check on the one it chose, and moved the work. The worker's identity, authority and history stay; only the intelligence changed." };
    if (last.did === "retry" || last.did === "write_refused") return { chapter: CH.work, view: "work", title: "A reply was refused and retried",
      body: "The worker's reply broke a rule, so it was refused and the step runs again. Three refusals escalate to the founder." };
    return { chapter: CH.work, view: "work", title: "The organization is working", body: "Workers are passing work through the Tool Gateway. Nothing needs the founder right now." };
  }

  return { narrate };
})();
if (typeof module !== "undefined") module.exports = CynqraTour;
