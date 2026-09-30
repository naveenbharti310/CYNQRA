"use strict";
/* Plain words for what is on screen, from the same state the UI renders (GET /api/state).
   Used by the guide panel in the app and by the guided demo page (poc/demo), so a presenter
   and a first time viewer read the same explanation of each step. Written for the CEO:
   what is happening and why it matters to them, in their words. */
const CynqraTour = (() => {
  let WORKERS = [];
  const seat = (w) => (w.title || w.role || "").replace(" (you lead this area)", "").replace(/ [A-Z]$/, "");
  // a person by name, and always as the AI in a seat; no pronouns are assumed from a name
  const who = (id) => { if (id === "orchestrator") return "Cynqra"; const w = WORKERS.find((x) => x.id === id); return w ? (w.name ? `${w.name}, the AI ${seat(w)}` : `the ${w.title}`) : id || "a team member"; };
  const Who = (id) => { const w = who(id); return w.charAt(0).toUpperCase() + w.slice(1); };
  const CH = { objective: "Step 1: Describe the idea", workforce: "Step 2: Approve the plan", you: "Step 3: Define yourself",
    plan: "Step 4: Approve the team and budget", work: "Step 5: Watch it being built", decide: "Step 5: A decision only you can make",
    live: "Step 6: Receive the product", refine: "Step 7: Audit and refine" };

  function task(st, id) { return (st.tasks || []).find((t) => t.id === id) || {}; }
  function lastVerification(st, id) { return (st.verifications || []).filter((v) => v.task_id === id).slice(-1)[0] || {}; }
  function pending(st) { return (st.decisions && st.decisions.pending) || []; }
  function decisionsSoFar(st) { return (st.metrics && st.metrics.founder_interventions) || 0; }
  const plural = (k, word) => `${k} ${word}${k === 1 ? "" : "s"}`;
  const files = (t) => (t.outputs || []).map((o) => o.file).join(", ");

  function forDecision(st, d) {
    const n = decisionsSoFar(st) + 1;
    const via = d.extra && d.extra.endorsed_by ? `It reaches you through ${who(d.extra.endorsed_by)}, who leads this area and reviewed it first. ` : "";
    if (d.kind === "approve_workforce" || d.kind === "approve_roadmap") return null;
    if (d.kind === "decision") return { chapter: CH.decide, view: "decisions", title: "A business rule for you to decide",
      body: `Nobody has said this yet, and ${who(d.source)} does not guess: "${d.problem}" A rule is proposed, with the evidence, how sure the proposal is, and what would change it. ${via}Rules like this are yours to decide. This is your decision ${n}: approve it, edit it, reject it with a reason, or ask for more evidence.` };
    if (d.kind === "review_merge") {
      const tests = (d.evidence_refs || []).find((e) => /tests on the release candidate/.test(e)) || "every test ran on the finished version";
      return { chapter: CH.decide, view: "decisions", title: `${Who(d.source)} asks to merge the finished product`,
        body: `Before asking, ${who(d.source)} ran every test on the finished version: ${tests}. Merging it into the main copy is your call. This is your decision ${n}.` };
    }
    if (d.kind === "deploy") {
      const side = d.extra && d.extra.side_action;
      return { chapter: CH.decide, view: "decisions", title: side ? "Going live, and a message was stopped" : `${Who(d.source)} asks to put it live`,
        body: "The release was already built, tested and tried out in a preview. Going live always needs you. " +
          (side ? `${Who(d.source)} also tried to send a message: "${side.summary}" Team members may not message anyone outside the company, so Cynqra stopped it before anything was sent. ` : "") +
          `${via}This is your decision ${n}.` };
    }
    if (d.kind === "accept_delivery") return { chapter: CH.live, view: "delivery", title: "Your product is live",
      body: "Open it and use it. The audit shows every requirement of your original objective and whether it is met. If something is not right, say what should change and Cynqra reworks it; when it is right, accept it. Everything can be downloaded, so nothing is locked in." };
    if (d.kind === "escalation") return { chapter: CH.decide, view: "decisions", title: "A team member needs you",
      body: `${d.problem} The team brings you only what it cannot settle itself. Try the task again, or stop the project.` };
    if (d.kind === "budget_breaker") return { chapter: CH.decide, view: "decisions", title: "The budget limit was reached",
      body: "Spending reached the dollar limit you set, so all work is paused. Only you can raise the limit or stop the project." };
    if (d.kind === "objective_change") return { chapter: CH.decide, view: "decisions", title: "The idea changed mid-project",
      body: "Changing the idea pauses the work and shows what it affects. Checked work stays; open work continues on the new version once you confirm." };
    if (d.kind === "provider_outage") return { chapter: CH.decide, view: "decisions", title: "An AI provider stopped answering",
      body: `${d.problem} Approve to let another AI stand in until it is back, at the price shown; reject to wait.` };
    if (d.kind === "provider_account") return { chapter: CH.decide, view: "decisions", title: "A provider account needs you", body: d.problem };
    return { chapter: CH.decide, view: "decisions", title: "A decision needs you", body: d.problem || "" };
  }

  function narrate(st) {
    if (!st || !st.meta) return null;
    WORKERS = st.workers && st.workers.length ? st.workers : ((st.proposal || {}).workers || []);
    const m = st.meta, last = st.last_step || {}, t = task(st, last.task);
    const obj = st.objective, pend = pending(st).filter((d) => !d.in_digest);
    if (m.frozen) return { chapter: CH.work, view: "work", title: "Emergency stop: all work is frozen",
      body: "Nothing happens until you release the stop. An answer that arrives from an AI while it is on is thrown away." };
    if (m.phase === "new") return { chapter: CH.objective, title: "You bring the vision",
      body: "Describe what you want to build and the outcome you want, in your own words, with a budget. Cynqra creates the organisation that can build it around you, runs it, and hands you the working product. You do not have to find people or manage AI models." };
    if (m.phase === "objective") return { chapter: CH.objective, title: "Your words become a clear brief",
      body: `Cynqra turns your description into a brief: the product, the customers, the outcomes, what success looks like, the limits and the priorities. ${obj && obj.inferred_fields.length ? `${obj.inferred_fields.length} of them were filled in by Cynqra and are marked, so you can check exactly those.` : ""} Set the budget in dollars, then see the plan.` };
    if (m.phase === "workforce") {
      const p = st.proposal || {}, req = st.requirements || { requirements: [] }, ws = p.workers || [];
      const cofs = ws.filter((w) => w.tier === "cofounder");
      const teams = cofs.map((c) => { const team = ws.filter((w) => w.reports_to === c.id).map((w) => w.name ? `${w.name} (${seat(w)})` : w.title);
        return `${c.name || "the " + c.title}, the AI ${seat(c)}, chose ${team.length ? team.join(", ") : "no one, and does the work alone"}`; });
      const ch = p.challenge || {}, ln = p.lean || {};
      return { chapter: CH.workforce, title: "The plan: what it takes, and who builds it",
        body: `Your idea became ${(req.outcomes || []).length} outcomes and ${req.requirements.length} requirements. Cynqra proposes ${cofs.length} AI cofounders (${cofs.map((c) => c.name ? `${c.name}, ${seat(c)}` : c.title).join("; ")}), and each chose a team: ${teams.join("; ")}. An independent check tried to make it smaller${(ch.removed || []).length ? ` and cut ${ch.removed.map((r) => r.title).join(", ")}` : ""}. A lean team of ${ln.seats || 0} is beside it. Approve the plan; next you define your own role.` };
    }
    if (m.phase === "founder") return { chapter: CH.you, title: "Define yourself",
      body: m.mode === "demo" ? "Say what you bring: your experience, your skills, the areas you lead yourself. An area you lead gets no AI cofounder; that seat becomes a lead who reports to you. In a demo your part and the team are scripted." :
        "Say what you bring: your experience, your skills, the areas you lead yourself. Cynqra then builds the organisation again around you: no seat for what you bring, and the capabilities you lack. An area you lead gets no AI cofounder; that seat reports to you. If you are technical yourself, you do not need a CTO." };
    if (m.phase === "planning" && (m.cycle || 1) > 1) return { chapter: CH.plan, title: `Cycle ${m.cycle}: the next piece of work`,
      body: `The product is live, and the same team planned only what you asked for next, with what users said. ${(st.tasks || []).filter((t) => t.cycle === m.cycle).length} tasks, priced against your budget. Approve once; the team builds, checks and releases it, and the release before it stays as the way back.` };
    if (m.phase === "planning") return { chapter: CH.plan, title: "Your team and budget",
      body: `The organisation is fitted around you, and each member has the AI best suited to their work. The work is ${((st.plan || {}).milestones || []).length} milestones and ${(st.tasks || []).length} tasks, each with an owner and a check it must pass, priced against your budget. Nothing starts until you approve.` };
    if (m.phase === "stopped_error") return { chapter: CH.work, view: "work", title: "The AI failed, and nothing was invented",
      body: "An AI or network error stopped this step. Cynqra never fills a gap with made-up work. Press Try the same step again once the AI is reachable." };
    if (m.phase === "stopped") return { chapter: CH.work, view: "work", title: "The project was stopped", body: m.notice || "" };
    if (m.phase === "accepted") return { chapter: CH.refine, view: "delivery", title: "Accepted",
      body: `Your product is live and accepted. Whenever something should change, say it on the Product screen and Cynqra reworks it. You were needed ${decisionsSoFar(st)} times. Everything else, including ${plural(st.metrics.defects_caught_before_verified, "mistake")} caught by the checks, ${plural(st.metrics.sent_back_by_cofounders || 0, "piece")} of work sent back by a cofounder, ${plural(st.metrics.blockers_cleared_without_founder, "question")} settled within the team and ${plural(st.metrics.actions_stopped_by_policy, "action")} stopped by the rules, the team handled itself, and every step is on record.` };
    if (pend.length) { const n = forDecision(st, pend[0]); if (n) return n; }
    if (last.did === "approved" && last.kind === "approve_workforce") return { chapter: CH.you, title: "The plan is approved",
      body: "Next, define yourself. Cynqra then fits the team around you, gives each member the AI that suits their work, and draws up the budget for your approval." };
    if (last.did === "approved" && last.kind === "approve_roadmap") return { chapter: CH.work, view: "work", title: "The team starts work",
      body: "From here you do nothing unless a decision needs you. Cofounders run their areas: they hand out their team's work, answer its doubts and review it before it counts. Everyone works at the same time, and every action is checked against the rules and recorded." };
    if (last.did === "approved") {
      const title = { decision: "You decided the rule", review_merge: "You approved the merge", deploy: "You approved going live" }[last.kind] || "You approved";
      const body = { decision: "It is written into the company's memory, and every later task receives it, so nobody has to guess it again.",
        review_merge: "The finished version is merged, and every test runs again afterwards.",
        deploy: "Only now does it go live: deployed, checked for health, tried out, then live. A failed check rolls it back automatically." }[last.kind] || "";
      return { chapter: CH.decide, view: "work", title, body };
    }
    if (last.did === "assigned") return { chapter: CH.work, view: "work",
      title: `${Who(t.handoff_from || "orchestrator")} hands "${t.title}" to ${who(t.owner_worker_id)}`,
      body: `${t.handoff_from && t.handoff_from !== "orchestrator" ? `${Who(t.handoff_from)} leads this area and hands out its work. ` : "A cofounder's own work comes straight from the plan you approved. "}The handover carries what is needed and how the work will be checked. Every handover and question is a structured message on record.` };
    if (last.did === "completed" && t.attempts) return { chapter: CH.work, view: "work", title: `${Who(t.owner_worker_id)} fixes the work and sends it again`,
      body: "The failed check and its details went back to them, and they sent a corrected version. It still counts for nothing until every check runs again." };
    if (last.did === "completed") return { chapter: CH.work, view: "work", title: `${Who(t.owner_worker_id)} says "${t.title}" is done`,
      body: `Saying it is done proves nothing yet. ${files(t)} wait in their own workspace until Cynqra checks them.` };
    if (last.did === "rework") {
      const v = lastVerification(st, t.id), failed = (v.checks && v.checks.failed) || [], bt = (v.checks || {}).backtest;
      if (bt && !bt.passed) return { chapter: CH.work, view: "work", title: "The forecast failed its test on real days",
        body: `${Who(t.owner_worker_id)}'s forecast passed its own tests, but on days it had not seen it was off by ${bt.model_mae} covers a day, worse than simply repeating last week (${bt.baseline_mae}). It goes back with the numbers; you are never asked.` };
      const docs = (v.checks || {}).documents;
      if (docs && docs.length) return { chapter: CH.work, view: "work", title: "A document was sent back",
        body: `${Who(t.owner_worker_id)}'s document is missing what it needs: ${docs.map((x) => x.why).join("; ")}.` };
      return { chapter: CH.work, view: "work", title: "A check caught a mistake",
        body: `${Who(t.owner_worker_id)}'s work failed ${failed.length ? failed.join(", ") : "its checks"}. It goes back with the failure named and does not count as done. You are never asked: catching this is the checks' job.` };
    }
    if (last.did === "blocked") {
      const to = (t.blocker || {}).needs_from, lead = to === t.reviewed_by;
      return { chapter: CH.work, view: "work", title: `${Who(t.owner_worker_id)} asks ${lead ? "their cofounder" : "a colleague"} instead of guessing`,
        body: `"${(t.blocker || {}).description || ""}" Guessing here could build the wrong thing. The question goes to ${who(to)}${lead ? ", who leads this area" : ", who knows the answer"}. You are not interrupted.` };
    }
    if (last.did === "blocker_cleared") {
      const a = (t.answers || []).slice(-1)[0] || {};
      return { chapter: CH.work, view: "work", title: `${Who(last.by)} answered, without you`,
        body: `"${a.acceptance_check || ""}" You were not interrupted.` };
    }
    if (last.did === "checked") return { chapter: CH.work, view: "work", title: `"${t.title}" passed its checks; now its cofounder reviews it`,
      body: `The checks prove it does what the tests and rules say. ${Who(t.reviewed_by)}, who leads this area, now reviews it as an owner would, before it counts.` };
    if (last.did === "to_cofounder") return { chapter: CH.work, view: "work", title: `${Who(t.owner_worker_id)}'s proposal goes to its cofounder first`,
      body: `A team member's proposal reaches you through the cofounder who leads its area. ${Who(t.reviewed_by)} reviews it before it is brought to you.` };
    if (last.did === "sent_back") { const r = (t.reviews || []).slice(-1)[0] || {};
      return { chapter: CH.work, view: "work", title: `${Who(last.by)} sent the work back`,
        body: `It passed the automatic checks, but its cofounder saw a problem: "${r.note || ""}" It goes back to ${who(t.owner_worker_id)} with what to change. You are never asked.` }; }
    if (last.did === "verified" && t.reviews && t.reviews.length && (t.reviews.slice(-1)[0] || {}).verdict === "approve" && t.kind !== "deploy") {
      const r = t.reviews.slice(-1)[0];
      return { chapter: CH.work, view: "work", title: `${Who(r.by)} approved "${t.title}"`,
        body: `"${r.note}" It passed its checks and its cofounder's review, and now counts as done.` };
    }
    if (last.did === "verified") {
      if (t.kind === "document") return { chapter: CH.work, view: "work", title: `"${t.title}" passed its check`,
        body: `Each kind of document has its own check: the sections it needs and the requirements it covers; for the company's foundation documents, separate sections for sources, assumptions and what a professional must confirm. ${files(t)} now belong to the company.` };
      if (t.kind === "forecast") { const bt = (lastVerification(st, t.id).checks || {}).backtest || {};
        return { chapter: CH.work, view: "work", title: "The forecast beats last week's numbers",
          body: `Its tests passed, then Cynqra tried it on ${bt.holdout_days || 14} days it had not seen: off by ${bt.model_mae} covers a day, against ${bt.baseline_mae} for repeating last week. Only now does it count as done.` }; }
      if (t.kind === "code") return { chapter: CH.work, view: "work", title: t.attempts ? "The fix passes every check" : `"${t.title}" passes every check`,
        body: `Cynqra ran every test, including the tests of earlier work${(lastVerification(st, t.id).method || "").includes("delivery contract") ? ", and started the product to check it answers" : ""}. Only now does it count as done.` };
      if (t.kind === "decision") return { chapter: CH.decide, view: "work", title: "The rule is in the company's memory",
        body: "Every later task receives it." };
      if (t.kind === "review_merge") return { chapter: CH.decide, view: "work", title: "Merged, and every test passes again",
        body: "The main copy now holds the finished version, and all its tests ran again after the merge." };
      if (t.kind === "deploy") return { chapter: CH.live, view: "delivery", title: "Live, and checked at every stage",
        body: "Built, tested, packaged, previewed, checked, approved by you, deployed, health-checked, tried out, live. It is running at its own address." };
    }
    if (last.did === "delivered") return forDecision(st, { kind: "accept_delivery" });
    if (last.did === "paused") return { chapter: CH.work, view: "work", title: "Paused", body: "An answer arrived after work was paused, so it was set aside. Nothing was lost." };
    if (last.did === "replaced" || last.did === "rerouted") return { chapter: CH.work, view: "workforce", title: last.did === "replaced" ? "A new person takes a seat" : "Work moved to a colleague",
      body: last.did === "replaced" ? "The AI in this seat could not do the work: it kept failing the checks. Cynqra replaced them with a new person, an AI that passed a trial on this kind of work first, and told you who left, who joined, why, and what the newcomer costs. The seat keeps its work and files; the one who left stays in the history with their record, and the newcomer's record starts now."
        : "The work moved to a colleague in the same role whose AI is expected to do better. Both stay in their seats." };
    if (["model_error_retry", "waiting", "waiting_on_ceo", "stand_in"].includes(last.did)) return { chapter: CH.work, view: "work", title: "An AI provider is not answering",
      body: "Cynqra checked why: the fault is on the provider's side and the AI is fine, so no one is replaced. That work waits and tries again; the rest of the team keeps going." };
    if (last.did === "retry" || last.did === "write_refused") return { chapter: CH.work, view: "work", title: "A reply was refused and tried again",
      body: "The reply broke a rule, so it was refused and the step runs again. After three refusals, Cynqra looks for a better AI or brings it to you." };
    return { chapter: CH.work, view: "work", title: "The team is at work", body: "Team members are handing work over and checking it. Nothing needs you right now." };
  }

  return { narrate };
})();
if (typeof module !== "undefined") module.exports = CynqraTour;
