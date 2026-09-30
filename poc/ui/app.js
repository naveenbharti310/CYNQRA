"use strict";
/* Cynqra POC web UI. Plain JavaScript, no build step. Polls /api/state and renders.
   Screens follow the mockups in archive/04_design_mockups/mockups (Book 0 sections 21 and 22). */

const S = {
  teamOption: "recommended",
  st: null, view: "company", worker: null, replayTask: null, replay: null, replayKey: "",
  seen: -1, sig: "", err: "", busy: false, graph: null, browse: {}, answers: {}, budgetGiven: false, mode: "live", shown: new Set(), guide: true, modelOpen: false,
  regOpen: false, probes: {}, sup: null, scenario: "bluedip",
};
/* Cards animate in only the first time they appear; a repaint must not replay it for every card. */
const fresh = (key) => { if (S.shown.has(key)) return ""; S.shown.add(key); return "fresh"; };
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const FIELD_LABELS = {
  product: "Product", target_customer: "Target customer", primary_outcome: "Primary outcome",
  business_outcome: "Business outcome", success_criteria: "Success criteria", constraints: "Constraints", priorities: "Priorities",
};
const KIND_TITLE = {
  decision: "Product rule", review_merge: "Merge release to main", deploy: "Production deploy",
  accept_delivery: "Accept delivery", budget_breaker: "Budget cap reached", escalation: "Escalation",
  objective_change: "Objective change", approve_workforce: "Proposed workforce", approve_roadmap: "Roadmap and budget",
  provider_outage: "An AI provider stopped answering", provider_account: "A provider account needs you",
};
// Decisions the proposer can revise with the CEO's note (cynqra/engine.py EVIDENCE_KINDS); the others take approve or reject.
const EVIDENCE_KINDS = ["decision", "review_merge", "deploy", "approve_workforce", "approve_roadmap"];
const AREA_TITLE = { business: "Business", market: "Market", finance: "Finance", legal: "Legal", domain: "Domain knowledge", product: "Product", functional: "Functional", non_functional: "Non-functional", ai_ml: "AI and ML", data: "Data",
  design: "Design", security: "Security", qa: "QA", devops: "DevOps", deployment: "Deployment" };
const ACT_TITLE = { write_file: "Write files", run_tests: "Run tests", assign_task: "Hand out work", product_rule_decision: "Decide a product rule",
  merge_to_main: "Merge code", deploy_production: "Put the product live", external_message: "Message anyone outside the company" };
const CONSTRAINTS = [["deadline", "Deadline"], ["geography", "Geography"], ["technology", "Technology"], ["compliance", "Compliance"], ["risk_tolerance", "Risk tolerance"]];
const SERVICE_TITLE = { orchestrator: "Orchestrator", verification: "Verification", founder: "Founder", budget_engine: "Budget Engine",
  workforce_synthesizer: "Workforce Synthesizer", execution_planner: "Execution Planner", replacement_engine: "Replacement Engine",
  objective_intelligence: "Objective Intelligence", intelligence_router: "Intelligence Router" };
// the founder's views first; the machinery behind them after "More"
const VIEWS = [["company", "Overview"], ["work", "Work"], ["decisions", "Decisions"], ["organization", "Team"], ["delivery", "Product"],
  ["workforce", "Workforce"], ["intelligence", "Intelligence"], ["performance", "Performance"], ["audit", "Audit trail"]];
const MAIN_VIEWS = 5;
// what an action is, in the founder's words (cynqra/policy.py RISK)
const ACTION_TITLE = { write_file: "writing a file", read_artifact: "reading a document", run_tests: "running tests",
  send_protocol: "a message to a colleague", assign_task: "handing out work", answer_blocker: "answering a question",
  review_work: "reviewing work", product_rule_decision: "a product rule", merge_to_main: "merging code", install_package: "installing a package",
  deploy_production: "going live", delete_data: "deleting data", external_message: "a message outside the company", move_money: "moving money",
  legal_commitment: "a legal commitment", change_objective: "changing the goal", change_budget: "changing the budget",
  change_authority: "changing who may do what" };
const actionTitle = (a) => ACTION_TITLE[a] || a;
const taskTitle = (id) => (((S.st && S.st.tasks) || []).find((t) => t.id === id) || {}).title || id;
// A seat is a title; the person in it has a name, and is always shown as an AI.
const seatOf = (w) => (w.title || w.role || "").replace(" (you lead this area)", "").replace(/ [A-Z]$/, "");
const label = (w) => (w.name ? `${w.name}, AI ${seatOf(w)}` : seatOf(w));
const wt = (id) => { const w = ((S.st && S.st.workers) || []).find((x) => x.id === id); return w ? label(w) : SERVICE_TITLE[id] || id; };

async function api(path, body) {
  const opts = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `request failed (${r.status})`);
  return data;
}

/* act() repaints before fn runs, so handlers read every input they need first, then call act(). */
// A refusal is shown next to the button that caused it, so it is seen wherever the page is scrolled.
document.addEventListener("click", (e) => { const b = e.target.closest && e.target.closest("button[id]"); S.lastClick = b ? b.id : ""; }, true);
// A technical failure is said plainly: what happened, that nothing was made up, and what to do.
const plainError = (m) => { const k = /^[A-Z]\w*(Error|Exception): /; return k.test(m || "") ? `The AI could not answer (${m.replace(k, "")}). Nothing was invented. Check the AI on the Intelligence screen, then try again.` : m; };
async function act(fn) {
  if (S.busy) return;
  const from = S.lastClick || "";
  S.busy = true; S.err = ""; S.errAt = ""; paint(true);
  try { await fn(); } catch (e) { S.err = plainError(e.message); S.errAt = from; }
  S.busy = false;
  await refresh(true);
}

async function refresh(force) {
  try {
    const st = await api("/api/state?window=1");  // ?window=1: the desktop app knows its window is open
    S.st = st;
    if (S.view === "intelligence" || S.regOpen || !S.sup) { try { S.sup = await api("/api/intelligence"); S.probes = S.sup.probes || {}; } catch (e) { /* keep */ } }
    toasts(st.events || []);
    if (S.view === "audit") await loadReplay();
    paint(force);
  } catch (e) { /* server restarting: keep the last screen */ }
}

function signature() {
  const st = S.st; if (!st) return "";
  const ev = st.events || [];
  return [ev.length ? ev[ev.length - 1].seq : 0, st.meta.phase, st.meta.frozen, st.auto.on, S.view, S.worker,
    S.replayTask, S.replayKey, S.err, S.busy, S.guide, JSON.stringify(S.graph), (st.decisions.pending || []).map((d) => d.id).join(),
    S.modelOpen, rtSignature(), S.regOpen, JSON.stringify(st.workforce || {}).length, JSON.stringify(S.probes).length, JSON.stringify(S.sup || {}).length].join("|");
}

function paint(force) {
  const sig = signature();
  if (!force && sig === S.sig) return;
  S.sig = sig;
  const keep = {};
  $$("#app input, #app textarea, #app select").forEach((el) => { if (el.id) keep[el.id] = el.value; });
  const focus = document.activeElement && document.activeElement.id;
  // a section the founder opened or closed stays that way through a repaint, known by its summary line
  const said = (el) => { const x = el.querySelector("summary"); return x ? x.textContent : ""; };
  const opened = new Map($$("#app details").map((el) => [said(el), el.open]));
  const phase = S.st.meta.phase;
  const model = showModelScreen();
  const g = model ? "" : guideBar();
  $("#app").innerHTML = (model ? modelScreen() : S.regOpen ? regScreen() : ["new", "objective", "workforce", "founder", "planning"].includes(phase) ? wizard() : shell()) + g;
  $("#app").classList.toggle("with-guide", !!g);
  const bar = $(".guide-bar");
  if (bar) document.documentElement.style.setProperty("--guide-h", bar.offsetHeight + "px");
  Object.entries(keep).forEach(([id, v]) => { const el = document.getElementById(id); if (el && el.dataset.keep !== "no") el.value = v; });
  $$("#app details").forEach((el) => { if (opened.has(said(el))) el.open = opened.get(said(el)); });
  if (focus) { const el = document.getElementById(focus); if (el) el.focus(); }
  if (S.err && S.errAt) {
    const b = document.getElementById(S.errAt);
    if (b) (b.closest(".row") || b).insertAdjacentHTML("afterend", `<div class="err err-inline" role="alert">${esc(S.err)}</div>`);
    else { S.errAt = ""; paint(true); return; }  // the screen changed: the message goes back to the top
  }
  bind();
}

/* ---------- guide: what is happening, in plain words (ui/tour.js) ---------- */
function guideBar() {
  if (!S.guide || typeof CynqraTour === "undefined") return "";
  const n = CynqraTour.narrate(S.st);
  if (!n) return "";
  return `<aside class="guide-bar" aria-label="Guide" aria-live="polite"><div class="guide-text"><span class="guide-chapter">${esc(n.chapter)}</span>
    <b class="guide-title">${esc(n.title)}</b><p class="guide-body">${esc(n.body)}</p></div>
    <button class="btn sm" id="guide-off" type="button">Hide guide</button></aside>`;
}
function guideToggle() {
  if (S.guide) return "";  // while it shows, the bar has its own Hide button
  return `<button class="btn sm" id="guide-toggle" type="button">Show guide</button>`;
}

/* ---------- toasts from new events ---------- */
function toasts(events) {
  if (S.seen < 0) { S.seen = events.length ? events[events.length - 1].seq : 0; return; }
  for (const e of events) {
    if (e.seq <= S.seen) continue;
    S.seen = e.seq;
    const p = e.payload || {};
    let msg = null, kind = "info";
    if (e.event_type === "task.verified") { msg = `${e.aggregate_id} verified`; kind = "good"; }
    else if (e.event_type === "verification.completed" && p.verdict === "REQUIRES_REWORK") { msg = `${p.task_id} sent back for rework: verification caught a defect`; kind = "warn"; }
    else if (e.event_type === "task.blocked") { msg = `${e.aggregate_id}: ${wt(e.actor_id)} raised a Blocker instead of guessing`; kind = "warn"; }
    else if (e.event_type === "action.denied") { msg = `The rules stopped ${actionTitle(p.action_type)} by the ${wt(e.actor_id)}`; kind = "bad"; }
    else if (e.event_type === "decision.created" && !p.settled_by && !["approve_workforce", "approve_roadmap"].includes(p.kind)) { msg = `Needs you: ${KIND_TITLE[p.kind] || p.kind}`; kind = "warn"; }
    else if (e.event_type === "decision.approved" && p.outcome_label === "settled_by_cofounder") { msg = `Settled by the ${wt(p.by)}: ${KIND_TITLE[p.kind] || p.kind}. You are told, not asked.`; kind = "info"; }
    else if (e.event_type === "worker.model_replaced") { msg = `${wt(e.aggregate_id)} moved to another model: ${p.reason || ""}`.slice(0, 160); kind = "warn"; }
    else if (e.event_type === "task.rerouted") { msg = `${e.aggregate_id} rerouted from ${wt(p.from_worker)} to ${wt(p.to_worker)}`; kind = "warn"; }
    else if (e.event_type === "deployment.verified") { msg = "Live and verified"; kind = "good"; }
    else if (e.event_type === "budget.threshold_reached") { msg = `Budget passed ${p.threshold} percent`; kind = p.threshold >= 100 ? "bad" : "warn"; }
    if (msg) toast(msg, kind);
  }
}
function toast(msg, kind) {
  const el = document.createElement("div");
  el.className = `toast ${kind}`; el.textContent = msg;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), 4200);
}

/* ---------- wizard: the canonical flow up to the start of work ----------
   1 Objective (Stage 0, 1)  2 Workforce (Stages 2, 3)  3 Roadmap and budget (Stages 4 to 7)  4 Run */
/* The founder's journey, the same everywhere (docs/0_USER_JOURNEY.md). */
const STEPS = ["Describe the idea", "Approve the plan", "Define yourself", "Approve the team and budget", "Watch it being built",
  "Receive the product", "Audit and refine"];
function steps(on) {
  return `<div class="steps" aria-label="Step ${on + 1} of 7">${STEPS.map((x, i) => `<span class="${i === on ? "on" : i < on ? "done" : ""}" title="${esc(x)}">${i + 1}${i === on ? " " + esc(x) : ""}</span>`).join("")}</div>`;
}
function journeyStep() {
  const st = S.st, ph = st.meta.phase;
  if (["new", "objective"].includes(ph)) return 0;
  if (ph === "workforce") return 1;
  if (ph === "founder") return 2;
  if (ph === "planning") return 3;
  if (ph === "delivered" || ph === "accepted") return 6;  // received the moment it is delivered; now you audit it
  return 4;
}

function wizard() {
  const st = S.st, phase = st.meta.phase, obj = st.objective;
  const top = `<div class="wiz-top"><div class="row"><span class="wordmark">Cynqra</span><span class="muted small">${esc(st.company ? st.company.name : "New project")}</span></div>
    <div class="row"><button class="btn sm" data-reg-open="1">Intelligence${(() => { const n = regModels().filter((m) => m.available && m.provider !== "demo").length || ((S.sup && S.sup.environment) || []).length; return n ? ` (${n})` : ""; })()}</button>${guideToggle()}${modePill()}</div></div>`;
  if (phase === "workforce") return `<div class="wiz">${top}${workforceStep()}</div>`;
  if (phase === "founder") return `<div class="wiz">${top}${founderStep()}</div>`;
  if (phase === "planning") return `<div class="wiz">${top}${planStep()}</div>`;
  const scen = scenario();
  const modeChoice = phase === "new" ? `
      <label class="lbl" for="coname">Project name</label>
      <input type="text" id="coname" placeholder="For example: Fitslot" value="${esc(scen && S.mode === "demo" ? scen.title : (S.answers.name || ""))}">
      ${`<div class="modes" role="radiogroup" aria-label="Intelligence">
        <label class="mode ${S.mode === "live" ? "on" : ""}" id="m-live"><input type="radio" name="mode" value="live" ${S.mode === "live" ? "checked" : ""}>Your idea, real AI models</label>
        <label class="mode ${S.mode === "demo" ? "on" : ""}" id="m-demo"><input type="radio" name="mode" value="demo" ${S.mode === "demo" ? "checked" : ""}>Watch a demo instead</label>
      </div>
      ${S.mode === "demo" ? `<label class="lbl" for="scenario">Demo scenario</label>
        <select id="scenario" data-keep="no">${(st.scenarios || []).map((x) => `<option value="${esc(x.id)}" ${x.id === S.scenario ? "selected" : ""}>${esc(x.title)}</option>`).join("")}</select>` : intelSources()}`}` : "";
  // before the brief exists, the right side says what this demo will show, so the page reads left to right
  const about = phase === "new" && S.mode === "demo" && scen ? `<div class="stack" style="max-width:640px"><span class="caps">In this demo</span><p style="margin:0;color:var(--ink2)">${esc(scen.about)}</p></div>` : "";
  const journey = `<div class="stack" style="gap:10px"><span class="caps">What happens next</span><ol class="journey">${STEPS.map((x, i) => `<li><span class="jn">${i + 1}</span>${esc(x)}</li>`).join("")}</ol></div>`;
  const right = obj ? objectiveCard(obj) : `<div class="card stack start-panel">${about}${journey}<p class="muted small" style="margin:0">Your brief appears here once Cynqra has read your words.</p></div>`;
  return `<div class="wiz">${top}<div class="wiz-body">
    <div class="wiz-left">
      ${steps(0)}
      <h1 class="hero">Describe what you want to build.</h1>
      <p class="lede">Not a prompt: a vision. Say what you want to build and the outcome you want. Cynqra works out what it takes, and the organisation that can build it around you.</p>
      ${modeChoice}
      ${ideaInputs(obj, scen, phase)}
      <div class="row"><button class="btn primary" id="structure" ${S.busy ? "disabled" : ""}>${obj ? "Make the brief again" : "Make it a brief"}</button></div>
      <div class="err" role="alert">${S.errAt ? "" : esc(S.err)}</div>
      <p class="small muted" style="margin:0">${(phase === "new" ? S.mode === "demo" : st.meta.mode === "demo")
        ? "Demo mode: the words the workers write come from a prepared script, and every screen says so. Code is still written, tested, backtested and deployed for real. Nothing to download or connect."
        : `Live mode: every worker is bound to an intelligence from the ones available, chosen from measured evidence.${isDesktop() ? " A model on this computer takes minutes per step; the Work view shows what it is doing." : ""}`}</p>
    </div>
    <div class="wiz-right">${right}</div></div></div>`;
}

// A live project starts from nothing: Cynqra asks what it needs, then writes the brief from the answers.
const QUESTIONS = [
  ["what", "What do you want to build?", "For example: an app that helps independent gyms fill their empty classes.", true],
  ["who", "Who is it for?", "For example: owners of small gyms with 50 to 300 members.", true],
  ["result", "What result do you want? How will you know it worked?", "For example: classes at least 70% full within three months.", true],
  ["rules", "Anything it must or must not do? (optional)", "For example: no card payments; it has to run on a phone.", false]];
const Q_LABEL = { what: "What I want to build", who: "Who it is for", result: "The result I want", rules: "What it must or must not do" };
const composeIdea = (a) => QUESTIONS.filter(([k]) => (a[k] || "").trim()).map(([k]) => `${Q_LABEL[k]}: ${a[k].trim()}`).join("\n");
function parseIdea(text) {
  const out = {}, keys = Object.keys(Q_LABEL);
  for (const line of String(text || "").split("\n")) { const k = keys.find((x) => line.startsWith(Q_LABEL[x] + ": ")); if (k) out[k] = line.slice(Q_LABEL[k].length + 2); }
  if (!Object.keys(out).length && text) out.what = text;
  return out;
}
function ideaInputs(obj, scen, phase) {
  const demo = phase === "new" ? S.mode === "demo" : S.st.meta.mode === "demo";
  if (demo) return `<label class="lbl" for="messy">What the founder in this demo wants, in their own words</label>
      <textarea class="big" id="messy">${esc(obj ? obj.statement : scen ? scen.messy : "")}</textarea>`;
  const a = Object.keys(S.answers).length > 1 ? S.answers : { ...parseIdea(obj ? obj.statement : ""), ...S.answers };
  return QUESTIONS.map(([k, q, ph, req]) => `<label class="lbl" for="q_${k}">${esc(q)}</label>
      <textarea class="${k === "what" ? "big" : ""}" rows="${k === "what" ? 3 : 2}" id="q_${k}" data-answer="${k}" ${req ? 'aria-required="true"' : ""} placeholder="${esc(ph)}">${esc(a[k] || "")}</textarea>`).join("");
}

const scenario = () => ((S.st && S.st.scenarios) || []).find((x) => x.id === ((S.st.meta || {}).scenario || S.scenario));

function objectiveCard(obj) {
  const st = S.st, s = st.budget.settings;
  const fields = Object.keys(FIELD_LABELS).map((k) => {
    const inf = obj.inferred_fields.includes(k);
    return `<div class="field ${inf ? "inf" : ""}"><div class="between caps"><span>${FIELD_LABELS[k]}</span>
      <span class="tag ${inf ? "inferred" : "stated"}">${inf ? "Inferred, check it" : "Stated"}</span></div>
      <textarea rows="2" id="f_${k}" data-field="${k}" data-keep="no" aria-label="${FIELD_LABELS[k]}">${esc(obj.structured[k])}</textarea></div>`;
  }).join("");
  const given = obj.founder_constraints || {};
  const cons = CONSTRAINTS.map(([k, l]) => `<div class="cons-row"><label for="c_${k}">${l}</label><input type="text" id="c_${k}" data-constraint="${k}" data-keep="no" value="${esc(given[k] || "")}" placeholder="optional"></div>`).join("");
  return `<div class="card stack" style="flex:1">
    <div class="between"><h2 style="font-size:20px">Your brief</h2><span class="small muted">Version ${obj.version} · ${esc(obj.intelligence)}</span></div>
    ${obj.notice ? `<div class="notice">${esc(obj.notice)}</div>` : ""}
    <div class="fields">${fields}
      <div class="field" style="border-style:dashed"><div class="caps">Budget</div>
        ${st.meta.mode === "live" ? `<div class="between"><label for="usd">Budget, US dollars (hard cap), required</label><input type="number" id="usd" min="0" step="0.5" placeholder="e.g. 5" value="${esc(S.budgetGiven ? s.budget_usd : "")}" style="width:110px"></div>
        <div class="between"><label for="tv">Value of an hour of your time, US dollars (optional)</label><input type="number" id="tv" min="0" step="1" placeholder="e.g. 50" value="${esc(S.budgetGiven ? s.time_value_per_hour : "")}" style="width:110px"></div>`
        : `<div class="between"><label for="usd">Budget, US dollars (hard cap)</label><input type="number" id="usd" data-keep="no" min="0" step="0.5" value="${esc(s.budget_usd)}" style="width:110px"></div>
        <div class="between"><label for="tv">Value of an hour, US dollars</label><input type="number" id="tv" data-keep="no" min="0" step="1" value="${esc(s.time_value_per_hour)}" style="width:110px"></div>`}</div>
      <details class="field" style="border-style:dashed"><summary class="caps">Constraints, optional</summary>${cons}</details>
    </div>
    <div class="between" style="margin-top:auto;padding-top:14px;border-top:1px solid var(--line)">
      <span class="small muted">Next, Cynqra shows you the plan: what it will build, the capabilities it needs, the team and the cost.</span>
      <button class="btn dark" id="submit" ${S.busy ? "disabled" : ""}>See the plan</button></div></div>`;
}

const LEADS = [["CTO", "I lead the technology", "no CTO cofounder"], ["CPO", "I lead the product", "no Chief Product Officer"],
  ["CFO", "I handle the money", "no CFO"], ["CCO", "I handle compliance", "no Chief Compliance Officer"]];
function founderStep() {
  const st = S.st, f = (st.company || {}).founder || {}, leads = f.leads || [], demo = st.meta.mode === "demo", off = demo ? "disabled" : "";
  const cofs = (st.workers || []).filter((w) => w.tier === "cofounder");
  return `<div class="wiz-body">
    <div class="wiz-left">
      ${steps(2)}
      <h1 class="hero">Define yourself.</h1>
      <p class="lede">Your experience, your skills, what you can contribute. ${demo ? "Cynqra fits the team around you" : "Cynqra builds the organisation again around what you write"}: no seat for what you bring yourself, and an area you lead gets no AI cofounder; that seat reports to you.</p>
      <label class="lbl" for="f_background">Your background</label>
      <textarea class="big" id="f_background" data-keep="yes" placeholder="For example: ten years as a backend engineer; I know the customers because I was one.">${esc(f.background || "")}</textarea>
      <div class="stack" style="gap:8px"><span class="lbl">What you lead yourself</span>
        ${LEADS.map(([k, l, n]) => `<label class="lead-opt ${off ? "off" : ""}"><input type="checkbox" data-founder-lead="${k}" data-keep="no" ${off} ${leads.includes(k) ? "checked" : ""}><span>${l} <span class="muted">(${n})</span></span></label>`).join("")}
        ${demo ? `<p class="small muted" style="margin:0">In a demo the founder is part of the script, so these are fixed. In live mode the team is fitted to what you choose.</p>` : ""}</div>
      <div class="between"><label for="f_hours">Your hours a week</label><input type="number" id="f_hours" data-keep="no" min="0" max="100" value="${esc(f.hours_per_week ?? 10)}" style="width:110px"></div>
      <div class="row"><button class="btn primary" id="define-founder" ${S.busy ? "disabled" : ""}>See the team and budget</button></div>
      <div class="err" role="alert">${S.errAt ? "" : esc(S.err)}</div>
    </div>
    <div class="wiz-right"><div class="card stack">
      <h2 style="font-size:20px">The cofounders the plan proposes</h2>
      <p class="small muted" style="margin:0">Tick an area you lead and its cofounder becomes a lead who reports to you.</p>
      ${cofs.map((w) => `<div class="kv"><span><b>${esc(w.name || "")}</b> <span class="muted">AI ${esc(seatOf(w))}</span><br><span class="small muted">${esc(w.why || "")}</span></span><span class="small nowrap">${(st.workers || []).filter((x) => x.reports_to === w.id).length} in the team</span></div>`).join("") || `<p class="muted small">None.</p>`}
      ${orgChart(st.workers || [])}
    </div></div></div>`;
}

function orgChart(workers) {
  const kids = (id) => workers.filter((w) => (w.reports_to || "founder") === id);
  const node = (w) => `<li><div class="onode${w.tier === "cofounder" ? " cofounder" : ""}"><b>${esc(w.name || seatOf(w))}</b><small>${esc([w.name ? `AI ${seatOf(w)}` : "", w.tier === "cofounder" ? "cofounder" : w.led_by_founder ? "reports to you: you lead this area" : "", w.model || ""].filter(Boolean).join(" · "))}</small></div>${kids(w.id).length ? `<ul>${kids(w.id).map(node).join("")}</ul>` : ""}</li>`;
  return `<div class="ochart"><div class="onode founder"><b>You, the founder</b><small>the vision and the calls that cannot be undone</small></div><ul class="otop">${kids("founder").map(node).join("")}</ul></div>`;
}

function reqList(req) {
  if (!req) return "";
  const byArea = {};
  req.requirements.forEach((r) => (byArea[r.area] = byArea[r.area] || []).push(r));
  return Object.entries(byArea).map(([a, rs]) => `<div class="stack" style="gap:2px"><span class="caps">${esc(AREA_TITLE[a] || a)}</span>
    ${rs.map((r) => `<div class="small"><span class="mono">${esc(r.id)}</span> ${esc(r.text)} <span class="muted">Verified by: ${esc(r.verification || "n/a")}</span></div>`).join("")}</div>`).join("");
}

function seatName(prop, key) {
  const r = (prop.roles || []).concat((prop.lean || {}).roles || []).find((x) => (x.field ? "Specialist:" + x.field.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") : x.role) === key);
  const c = (S.st.catalog || []).find((x) => x.role === key);
  return r ? (r.title || (c || {}).title || r.role) : key === "founder" ? "you" : c ? c.title : key;
}

function workforceStep() {
  const st = S.st, prop = st.proposal || {}, req = st.requirements, d = (st.decisions.pending || []).find((x) => x.kind === "approve_workforce");
  const lean = S.teamOption === "lean", ln = prop.lean || {}, demo = st.meta.mode === "demo";
  const rows = lean ? (ln.roles || []) : (prop.roles || []);
  const cost = (lean ? ln.cost_by_role : prop.cost_by_role) || {};
  const cards = {}; ((lean ? ln.cards : prop.cards) || []).forEach((c) => cards[c.seat] = c);
  const keyOf = (r) => r.field ? "Specialist:" + r.field.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") : r.role;
  const row = (r) => {
    const cat = (st.catalog || []).find((c) => c.role === r.role) || {}, c = cards[keyOf(r)] || {};
    const name = r.title || cat.title || r.role, key = r.title || r.role, fid = r.field ? "spec_" + r.field.replace(/[^a-z0-9]+/gi, "_") : r.role;
    const cof = r.tier === "cofounder";
    return `<tr class="${cof ? "cof-row" : "team-row"}"><td>${cof ? `<span class="pill blue">Cofounder</span> <b>${esc(name)}</b>` : `<span class="indent">${esc(name)}</span>`}${r.quantity > 1 ? ` <span class="muted">x${esc(r.quantity)}</span>` : ""}${r.mode ? ` <span class="pill grey" title="${esc(r.mode_why || "")}">${r.mode === "advisor" ? "advisor" : "joins later"}</span>` : ""}
        <div class="small muted">${esc(r.why)}</div>${(c.without || []).length ? `<div class="small muted">Without it: ${esc(c.without.join("; "))}</div>` : ""}</td>
      <td class="mono small">${cost[key] === undefined ? "n/a" : usd(cost[key])}</td>
      ${allowOverride() && !lean ? `<td><input type="number" min="0" max="${esc(r.field ? 1 : cat.max || 1)}" id="q_${esc(fid)}" data-role="${esc(r.role)}" data-field="${esc(r.field || "")}" data-title="${esc(r.title || "")}" data-lead="${esc(r.lead || "")}" data-keep="no" value="${esc(r.quantity)}" style="width:60px" aria-label="Quantity"></td>` : ""}</tr>`;
  };
  const cofs = rows.filter((r) => r.tier === "cofounder");
  const table = cofs.map((c) => row(c) + rows.filter((r) => r.lead === c.role).map(row).join("")).join("") + rows.filter((r) => r.tier !== "cofounder" && !cofs.some((c) => c.role === r.lead)).map(row).join("");
  const ch = prop.challenge || {};
  const cut = (ch.removed || []).map((r) => `<li><b>${esc(r.title)}</b> was cut: ${esc(r.why)}</li>`).join("");
  const kept = (ch.overruled || []).map((o) => `<li><b>${esc(o.title)}</b> was kept because ${esc(o.kept_because)}</li>`).join("");
  const leanNote = lean ? `<div class="small"><b>What the recommended team adds:</b><ul style="margin:4px 0 0;padding-left:18px">${(ln.left_out || []).map((x) => `<li>${esc(x.title)}: ${esc(x.adds)}</li>`).join("")}${(ln.fewer || []).map((x) => `<li>${x.from} ${esc(x.title)}s instead of one: the work goes faster</li>`).join("")}</ul></div>` : "";
  const nSeats = (rs) => rs.reduce((n, r) => n + Number(r.quantity || 0), 0);
  const total = Object.values(cost).reduce((a, b) => a + Number(b || 0), 0);
  const outcomes = ((req || {}).outcomes || []).map((o) => `<li>${esc(o)}</li>`).join("");
  const areas = [...new Set(((req || {}).requirements || []).map((r) => r.area))].map((a) => `<span class="pill grey">${esc(AREA_TITLE[a] || a)}</span>`).join(" ");
  const w = prop.why_team || {};
  return `<div class="wiz-body">
    <div class="wiz-left">
      ${steps(1)}
      <h1 class="hero">The plan.</h1>
      <p class="lede">What Cynqra will build, the capabilities it takes, and the organisation it proposes to build it. Next you define your own role, and the team is fitted around you.</p>
      <div class="card stack"><div class="caps">What you'll get</div><ul style="margin:0;padding-left:18px">${outcomes}</ul>
        ${areas ? `<div class="caps" style="margin-top:8px">Capabilities it takes</div><div class="row" style="flex-wrap:wrap;gap:6px">${areas}</div>` : ""}
        <details><summary class="small">The ${req ? req.requirements.length : 0} requirements it is built from</summary>${reqList(req)}</details></div>
      <div class="card stack"><div class="between"><div class="caps">Estimated budget</div><b class="mono">${usd(((st.budget || {}).settings || {}).budget_usd)}</b></div>
        <span class="small muted">${demo ? "In a demo the team's words come from a script, so its AI costs nothing." : `The team's AI work is estimated at ${usd(total)} of it.`} The final budget comes with the team, after you define yourself.</span></div>
      <details class="card"><summary><b>How this team was checked</b> <span class="pill ${w.confidence === "high" ? "green" : w.confidence === "low" ? "red" : "amber"}">Confidence: ${esc(w.confidence || "medium")}</span></summary>
        <ul class="small" style="margin:8px 0 0;padding-left:18px">${(w.lines || []).map((l) => `<li>${esc(l)}</li>`).join("")}${cut}${kept}</ul></details>
      <div class="err" role="alert">${S.errAt ? "" : esc(S.err)}</div>
    </div>
    <div class="wiz-right"><div class="card stack">
      <div class="between"><h2 style="font-size:20px">The proposed organisation: ${nSeats(rows)} seats</h2>
        <div class="row" role="radiogroup" aria-label="Team"><button class="btn sm ${lean ? "" : "primary"}" data-team-option="recommended">Recommended, ${nSeats(prop.roles || [])}</button>
        <button class="btn sm ${lean ? "primary" : ""}" data-team-option="lean">Lean, ${esc(ln.seats || 0)}</button></div></div>
      ${lean ? leanNote : `<p class="small" style="margin:0">${esc(prop.summary || "")}</p>`}
      ${orgChart((lean ? ln.workers : prop.workers) || [])}
      <details><summary class="small">Every seat, why it is there and what it costs</summary>
        <div class="tscroll"><table class="tbl"><thead><tr><th>Seat and why</th><th>Expected cost</th>${allowOverride() && !lean ? "<th>Edit</th>" : ""}</tr></thead><tbody>${table}</tbody></table></div></details>
      ${lean && demo ? `<p class="small muted" style="margin:0">The demo's script plans the recommended team only; in live mode Cynqra plans for whichever team you choose.</p>` : ""}
      <label class="lbl" for="wf_note">Anything to change in the plan?</label><textarea class="note" id="wf_note" data-keep="yes"></textarea>
      <div class="row"><button class="btn primary" id="approve-workforce" data-id="${esc(d ? d.id : "")}" data-option="${lean ? "lean" : "recommended"}" ${S.busy || !d || (lean && demo) ? "disabled" : ""}>Approve the plan</button>
        <button class="btn" id="revise-workforce" data-id="${esc(d ? d.id : "")}" ${S.busy || !d ? "disabled" : ""}>Ask for a different plan</button></div>
    </div></div></div>`;
}
const allowOverride = () => !!(wfv().settings || {}).allow_workforce_override;

function budgetTable(f) {
  if (!f) return "";
  const rows = Object.entries(f.layers).map(([k, v]) => `<tr><td>${esc(k.charAt(0).toUpperCase() + k.slice(1))}</td><td class="mono">${usd(v.usd)}</td><td class="small">${esc(v.basis)}</td></tr>`).join("");
  const byw = Object.entries(f.by_worker || {}).map(([w, v]) => `<span class="pill grey">${esc(wt(w))} ${usd(v.usd)}</span>`).join(" ");
  return `<div class="tscroll"><table class="tbl"><thead><tr><th>Layer</th><th>USD</th><th>Basis</th></tr></thead><tbody>${rows}
    <tr><td><b>Project total</b></td><td class="mono"><b>${usd(f.total_usd)}</b></td><td class="small">against the hard cap of ${usd(f.cap_usd)}${f.spent_before_usd ? `, ${usd(f.spent_before_usd)} of it already spent` : ""}</td></tr></tbody></table></div>
    <div class="small">By worker: ${byw}</div>${(f.warnings || []).map((w) => `<div class="notice small">${esc(w)}</div>`).join("")}
    ${S.st && S.st.meta.mode === "demo" ? `<div class="small muted">In a demo the team's words come from a script, so its AI costs nothing. With real AI, every task is priced here in dollars before it starts.</div>` : ""}`;
}

/* Step 4: what changed in the organisation once the founder defined themselves. */
function fitCard(mine) {
  const fit = (S.st.proposal || {}).fitted, lines = [];
  if (fit && fit.added.length) lines.push(`<li>Added for what you do not bring: ${esc(fit.added.join(", "))}</li>`);
  if (fit && fit.removed.length) lines.push(`<li>Not needed, because you bring it: ${esc(fit.removed.join(", "))}</li>`);
  if (fit && !lines.length) lines.push(`<li>Rebuilt around your background: the same seats still fit.</li>`);
  mine.forEach((w) => lines.push(`<li>${esc(label(w))} reports to you: you lead this area</li>`));
  return lines.length ? `<div class="card stack" data-fit="1"><div class="caps">Fitted to you</div><ul class="small" style="margin:0;padding-left:18px">${lines.join("")}</ul></div>` : "";
}

function planStep() {
  const st = S.st, plan = st.plan || {}, f = st.forecast || {};
  const d = (st.decisions.pending || []).find((x) => x.kind === "approve_roadmap");
  const tasks = st.tasks || [];
  const ms = (plan.milestones || []).map((m) => `<tr class="ms"><td colspan="4"><b>${esc(m.name)}</b> <span class="muted small">by day ${esc(m.due_day)}</span></td></tr>
    ${tasks.filter((t) => t.milestone_id === m.id).map((t) => `<tr><td>${esc(t.title)}<div class="small muted">${esc((t.acceptance_criteria || []).join("; "))}</div></td>
      <td>${esc(wt(t.owner_worker_id))}</td><td>${riskPill(t.risk_tier)}</td><td class="small">${esc(t.verification_gate)}</td></tr>`).join("")}`).join("");
  const days = Math.max(0, ...(plan.milestones || []).map((m) => Number(m.due_day) || 0));
  const timeline = (plan.milestones || []).map((m) => `<div class="kv"><span>${esc(m.name)}</span><span class="small">day ${esc(m.due_day)}</span></div>`).join("");
  const mine = (st.workers || []).filter((w) => w.led_by_founder);
  return `<div class="wiz-body">
    <div class="wiz-left">
      ${steps(3)}
      ${(st.meta.cycle || 1) > 1 ? `<h1 class="hero">Your rework: plan and budget.</h1>
      <p class="lede">What you asked to change: “${esc((st.meta.cycle_note || "").split("\n")[0])}” The same team plans only this work, priced against your budget. Nothing starts until you approve, and the release you have stays as the way back.</p>` : `<h1 class="hero">Your team and budget.</h1>
      <p class="lede">The organisation fitted around you, what it will deliver and when, and what it costs. Nothing starts until you approve. After that, you are asked only what cannot be undone.</p>`}
      <div class="card stack"><div class="between"><div class="caps">Budget</div><b class="mono">${usd(f.total_usd)} of ${usd(f.cap_usd)}</b></div>
        <details><summary class="small">How it adds up</summary>${budgetTable(f)}</details></div>
      <div class="card stack"><div class="between"><div class="caps">Timeline</div><span class="small">about ${days} days</span></div>${timeline}</div>
      ${fitCard(mine)}
      <div class="err" role="alert">${S.errAt ? "" : esc(S.err)}</div>
    </div>
    <div class="wiz-right"><div class="card stack">
      <h2 style="font-size:20px">Your organisation: ${(st.workers || []).length} members</h2>
      ${orgChart(st.workers || [])}
      <details><summary class="small">Every task, in order (${tasks.length})</summary>
        <div class="tscroll"><table class="plan-table"><thead><tr><th>Task and how it is accepted</th><th>Who</th><th>Risk</th><th>How it is checked</th></tr></thead><tbody>${ms}</tbody></table></div></details>
      <div class="row"><button class="btn primary" id="approve-plan" data-id="${esc(d ? d.id : "")}" ${S.busy || !d ? "disabled" : ""}>${(st.meta.cycle || 1) > 1 ? "Approve the rework plan" : "Approve the team and budget"}</button>
        <button class="btn" id="replan" data-id="${esc(d ? d.id : "")}" ${S.busy || !d ? "disabled" : ""}>Ask for a different plan</button></div>
    </div></div></div>`;
}

/* ---------- desktop app: the open model on this computer ---------- */
const isDesktop = () => !!(S.st && S.st.desktop && S.st.runtime);
const rt = () => (S.st && S.st.runtime) || {};
const gb = (b) => (b >= 1073741824 ? (b / 1073741824).toFixed(1) : (b / 1073741824).toFixed(2));
const RT_WORKING = ["downloading", "checking", "starting", "checking-gpu"];

function rtSignature() {
  if (!isDesktop()) return "";
  const r = rt();
  return [r.state, r.model, Math.floor((r.done || 0) / 52428800), Math.round((r.rate || 0) / 1048576), r.error, r.gpu,
    r.busy ? Math.floor(r.busy.tokens / 25) : -1, (r.catalog || []).map((m) => `${m.installed}:${m.partial_gb}`).join()].join(",");
}

/* The models this computer can run are one source of intelligence among others, opened on request: a new user can
   try the demo or connect a provider without downloading anything. */
function showModelScreen() {
  return isDesktop() && S.modelOpen;
}

function modelActivity() {
  if (!isDesktop()) return "";
  const b = rt().busy;
  if (!b) return "";
  const what = b.tokens ? `Model writing: ${b.tokens.toLocaleString()} tokens` : `Model reading a ${(b.prompt || 0).toLocaleString()}-token prompt`;
  return `<span class="pill blue" title="What the model on this computer is doing right now"><i class="dot pulse"></i>${what}</span>`;
}

function modelBanner() {
  if (!S.st || S.st.meta.mode !== "live" || regModels().some((m) => m.available)) return "";
  const r = rt(), working = isDesktop() && RT_WORKING.includes(r.state);
  return `<div class="notice">${working ? `A model is ${r.state === "downloading" ? "downloading" : "starting"} on this computer; the run continues when it is ready.`
    : "No intelligence is available, so the organisation cannot work."} ${isDesktop() ? `<button class="btn sm" data-model-open="1">Models on this computer</button>` : ""}<button class="btn sm primary" data-reg-open="1">Connect a provider</button></div>`;
}

/* Where a live run's intelligence comes from, on the first screen. */
function intelSources() {
  const avail = regModels().filter((m) => m.available), conns = supConns().filter((c) => c.origin !== "demo");
  const env = ((S.sup && S.sup.environment) || []).filter((n) => !conns.some((c) => c.name === n));
  const n = avail.length || env.length;
  return `<div class="card stack" style="padding:14px 16px"><div class="between"><b>Intelligence available</b><span class="pill ${n ? "teal" : "amber"}">${avail.length ? `${avail.length} model${avail.length === 1 ? "" : "s"}` : env.length ? `${env.length} source${env.length === 1 ? "" : "s"}` : "None yet"}</span></div>
    <span class="small muted">${avail.length ? `From ${esc(conns.filter((c) => avail.some((m) => m.connection_id === c.id)).map((c) => c.name).join(", "))}. Cynqra evaluates each one on its own work, then chooses which one powers each team member.`
      : env.length ? `From this computer's settings: ${esc(env.join(", "))}. Connected when you start; Cynqra picks which model powers each worker from measured evidence.`
      : "Download an open model to this computer, or connect a provider such as Hugging Face, OpenAI or Anthropic."}</span>
    <div class="row wrap" style="gap:8px">${isDesktop() ? `<button class="btn sm" data-model-open="1">Models on this computer</button>` : ""}<button class="btn sm" data-reg-open="1">Connect a provider</button></div></div>`;
}

function modelStatus() {
  const r = rt();
  const name = esc(r.model_name || r.model || "");
  if (r.state === "downloading") {
    const pct = r.total ? Math.floor((100 * r.done) / r.total) : 0;
    const left = r.rate > 0 && r.total ? Math.max(1, Math.round((r.total - r.done) / r.rate / 60)) : null;
    return `<div class="card stack"><div class="between"><b>Downloading ${name}</b><span class="mono small">${pct}%</span></div>
      <div class="meter wide" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><i style="width:${pct}%"></i></div>
      <span class="small mono">${gb(r.done)} of ${r.total ? gb(r.total) : "?"} GB · ${(r.rate / 1e6).toFixed(0)} MB/s${left ? ` · about ${left} min left` : ""}</span>
      <span class="small muted">From Hugging Face, checked against its published SHA-256 when it finishes. If you pause or quit, the download resumes where it stopped.</span>
      <div class="row"><button class="btn" id="rt-cancel">Pause download</button></div></div>`;
  }
  if (r.state === "checking") return `<div class="card stack"><b>Checking the download</b><span class="small muted">Comparing ${name} with its published SHA-256. Under a minute.</span></div>`;
  if (r.state === "checking-gpu") return `<div class="card stack"><div class="row"><i class="dot pulse" style="color:var(--accent)"></i><b>Testing the graphics card</b></div>
    <span class="small muted">${name} is loaded on the GPU; Cynqra asks it for one short answer before using it. If the card cannot answer, the processor is used instead.</span></div>`;
  if (r.state === "starting") return `<div class="card stack"><div class="row"><i class="dot pulse" style="color:var(--accent)"></i><b>Starting ${name}</b></div>
    <span class="small muted">llama.cpp is loading the model into memory${r.accel ? ` (${esc(r.accel === "cpu" ? "processor" : r.accel)})` : ""}. From a few seconds to two minutes.</span>
    <div class="row"><button class="btn" id="rt-cancel">Stop</button></div></div>`;
  if (r.state === "ready") return `<div class="card stack ok-card"><b>${name} is running on this computer</b>
    <span class="small">Served by llama.cpp on 127.0.0.1 using the ${esc(r.accel === "cpu" ? "processor" : r.accel === "metal" ? "Apple GPU (Metal)" : "GPU (Vulkan)")}. Prompts and answers stay on this computer.</span>
    <div class="row"><button class="btn primary" data-model-close="1">Continue</button><button class="btn" id="rt-stop">Stop the model</button></div></div>`;
  if (r.state === "error") return `<div class="card stack warn"><b>The model did not start</b><span class="small" style="color:var(--red)">${esc(r.error)}</span>
    ${r.log ? `<details><summary class="small">Details from llama-server</summary><pre class="log">${esc(r.log)}</pre></details>` : ""}
    <span class="small muted">Try again below. If it keeps failing, try a smaller model, or send the details to the Cynqra team.</span></div>`;
  return "";
}

function modelScreen() {
  const r = rt(), working = RT_WORKING.includes(r.state);
  const cards = (r.catalog || []).map((m) => {
    const running = m.id === r.model && r.state === "ready";
    const label = m.installed ? "Start" : m.partial_gb ? `Resume download (${m.partial_gb} of ${m.size_gb} GB)` : `Download ${m.size_gb} GB and start`;
    const action = running ? `<span class="pill green">Running</span>`
      : `<button class="btn" data-rt-start="${esc(m.id)}" ${working || S.busy ? "disabled" : ""}>${label}</button>`;
    return `<div class="mcard ${running ? "on" : ""}">
      <div class="between"><b>${esc(m.name)}</b><span class="row" style="gap:6px">${m.fits ? `<span class="pill">Fits this computer's memory</span>` : ""}
        ${m.fits ? "" : `<span class="pill amber">Needs ${m.min_gb} GB of memory</span>`}</span></div>
      <p class="small" style="margin:6px 0 10px">${esc(m.about)}</p>
      <div class="between"><span class="small muted mono">${m.size_gb} GB · ${Math.round(m.ctx / 1024)}K context${m.installed ? " · downloaded" : ""}</span>${action}</div></div>`;
  }).join("");
  const gpus = (r.gpus || []).map((g) => `${esc(g.name)} (${Math.round(g.mib / 1024)} GB)`).join(", ");
  const accel = (r.servers || []).includes("vulkan") ? `<label class="lbl" for="rt-gpu">Graphics card</label>
      <select id="rt-gpu" data-keep="no" ${working ? "disabled" : ""}>
        <option value="auto" ${r.gpu === "auto" || !r.gpu ? "selected" : ""}>Automatic: ${r.gpu_pick ? `use ${esc(r.gpu_pick)}` : "no suitable card found, use the processor"}</option>
        <option value="on" ${r.gpu === "on" ? "selected" : ""}>On: use the graphics card even if it is small or integrated</option>
        <option value="off" ${r.gpu === "off" ? "selected" : ""}>Off: use the processor only</option></select>
      <span class="small muted">${gpus ? `Found: ${gpus}. ` : "No graphics card found through Vulkan. "}If the card cannot run the model, Cynqra falls back to the processor by itself. Applies the next time a model starts.</span>`
    : (r.servers || []).includes("metal") ? `<span class="small muted">This Mac's GPU is used through Metal.</span>` : "";
  return `<div class="wiz"><div class="wiz-top"><div class="row"><span class="wordmark">Cynqra</span><span class="muted small">Model</span></div>
      <div class="row"><button class="btn sm" data-model-close="1">Back</button><button class="btn sm" data-app-quit="1">Quit</button></div></div>
    <div class="wiz-body"><div class="wiz-left">
      <h1 class="hero">Models on this computer.</h1>
      <p class="lede">An open-weight model can run here, through llama.cpp: downloaded once, after which no prompt, answer or code leaves this computer. It is one source of intelligence among those you connect; Cynqra picks which one powers each worker. Nothing here is required to try the demo.</p>
      <div class="card stack"><div class="kv"><span>This computer</span><span>${esc(r.platform)}</span></div>
        <div class="kv"><span>Memory</span><span>${r.ram_gb ? `${r.ram_gb} GB` : "unknown"}</span></div>
        <div class="kv"><span>Model server</span><span>llama.cpp, ${esc((r.servers || []).join(", ") || "missing")}</span></div>${accel}</div>
      ${modelStatus()}
      <div class="err" role="alert">${S.errAt ? "" : esc(S.err)}</div>
    </div><div class="wiz-right"><div class="stack">${cards}</div>
      <p class="small muted">Models come from their publishers on Hugging Face (Unsloth quantizations of Alibaba's Qwen models, Apache 2.0). Which model suits which computer comes from Cynqra's September 2026 research.</p></div></div></div>`;
}

/* ---------- shell ---------- */
function modePill() {
  const st = S.st;
  if (st.meta.mode === "live" || (st.meta.phase === "new" && S.mode === "live")) {
    const n = regModels().filter((m) => m.available).length || ((S.sup && S.sup.environment) || []).length;
    return `<span class="pill blue">Live mode: ${n ? `${n} intelligence source${n === 1 ? "" : "s"} available` : "no AI connected yet"}</span>`;
  }
  return `<span class="pill amber">Demo mode: scripted workers</span>`;
}
function riskPill(r) {
  const c = { LOW: "green", MEDIUM: "amber", HIGH: "red", PROHIBITED: "red" }[r] || "grey";
  return `<span class="pill ${c}">${esc(r)}</span>`;
}
function statusPill() {
  const st = S.st, m = st.meta, pend = (st.decisions.pending || []).filter((d) => !d.in_digest);
  if (m.frozen) return `<span class="pill red">Frozen by kill switch</span>`;
  if (m.phase === "accepted") return `<span class="pill green">Delivered and accepted</span>`;
  if (m.phase.startsWith("stopped")) return `<span class="pill red">Stopped</span>`;
  if (pend.length) return `<span class="pill amber">Waiting on you</span>`;
  if (st.auto.on && m.phase === "running") return `<span class="pill teal"><i class="dot pulse"></i>Working</span>`;
  return `<span class="pill grey">Paused</span>`;
}

function shell() {
  const st = S.st, cap = st.budget.settings.budget_usd, spent = st.budget.ledger.spent_total;
  const pct = cap ? Math.min(100, Math.round((100 * spent) / cap)) : 100;
  const pend = (st.decisions.pending || []).filter((d) => !d.in_digest).length;
  const nav = VIEWS.map(([k, label], i) => `${i === MAIN_VIEWS ? `<span class="caps nav-more">More</span>` : ""}<button class="nav ${i >= MAIN_VIEWS ? "minor" : ""} ${S.view === k ? "on" : ""}" data-view="${k}"${S.view === k ? ' aria-current="page"' : ""}>
    <span>${label}</span>${k === "decisions" && pend ? `<span class="badge">${pend}</span>` : ""}</button>`).join("");
  const running = st.meta.phase === "running";
  const views = { company: vCompany, organization: vOrg, workforce: vWorkforce, work: vWork, decisions: vDecisions, intelligence: vIntelligence,
    performance: vPerformance, audit: vAudit, delivery: vDelivery };
  return `<div class="shell">
    <nav class="side" aria-label="Main"><div class="brand"><span class="wordmark">Cynqra</span><span class="small muted">${esc(st.company ? st.company.name : "")}</span></div>
      ${nav}
      <div class="foot">${modePill()}
        <button class="btn danger ${st.meta.frozen ? "on" : ""}" id="kill">${st.meta.frozen ? "Release kill switch" : "Kill switch"}</button>
        <button class="btn sm" id="reset" title="Archive this run and start again">New run</button>${guideToggle()}
        ${isDesktop() ? `<div class="row" style="gap:8px"><button class="btn sm" data-model-open="1">This computer</button><button class="btn sm" data-app-quit="1">Quit</button></div>` : ""}</div></nav>
    <main class="main">
      <header class="top"><div class="row" style="gap:14px"><h1>${VIEWS.find((v) => v[0] === S.view)[1]}</h1><span class="small muted">Step ${journeyStep() + 1} of 7: ${esc(STEPS[journeyStep()])}</span></div>
        <div class="row small" style="gap:20px">
          <div class="row" style="gap:8px"><span>Budget</span><div class="meter ${pct >= 95 ? "bad" : pct >= 80 ? "warn" : ""}" role="img" aria-label="Budget ${pct} percent used"><i style="width:${pct}%"></i></div>
            <span class="mono">${usd(spent)} / ${usd(cap)}</span></div>
          ${modelActivity()}${statusPill()}
          <button class="btn sm" id="step" ${!running || st.auto.on || S.busy ? "disabled" : ""}>Step</button>
          <button class="btn sm ${st.auto.on ? "" : "primary"}" id="auto" ${!running ? "disabled" : ""}>${st.auto.on ? "Pause" : "Run"}</button>
        </div></header>
      <div class="view">${modelBanner()}${S.err && !S.errAt && !(st.meta.notice || "").includes(S.err) ? `<div class="err" role="alert">${esc(S.err)}</div>` : ""}${st.meta.notice ? `<div class="notice ${st.meta.phase === "stopped_error" || st.meta.frozen ? "warn" : ""}">${esc(st.meta.notice)}${st.meta.phase === "stopped_error" ? ` <button class="btn sm primary" id="resume" ${S.busy ? "disabled" : ""}>Try the same step again</button>` : ""}</div>` : ""}${views[S.view]()}</div>
    </main></div>`;
}

function vCompany() {
  const st = S.st, o = st.objective, m = st.metrics, ts = st.tasks || [];
  const pend = (st.decisions.pending || []).filter((d) => !d.in_digest);
  const needs = pend.length ? pend.slice(0, 3).map((d) => `<div class="needs"><div class="stack" style="gap:2px"><b>${esc(KIND_TITLE[d.kind] || d.kind)}${d.task_id ? `: ${esc(taskTitle(d.task_id))}` : ""}</b>
      <span class="small muted">${esc(d.problem)}</span></div><button class="btn dark sm" data-view="decisions">Review</button></div>`).join("")
    : `<p class="muted" style="margin:0">${["delivered", "accepted"].includes(st.meta.phase) ? "Nothing needs you. Your product is ready on the Product screen." : "Nothing needs you right now. The team is working."}</p>`;
  const rows = ts.map((t) => `<div class="list-row"><span>${esc(t.title)}</span><span class="st ${t.status}">${esc(statusText(t))}</span></div>`).join("");
  const tile = (v, l) => `<div class="tile"><b>${esc(v ?? "0")}</b><span>${l}</span></div>`;
  const done = ["delivered", "accepted"].includes(st.meta.phase);
  return `<div class="card stack">
      <span class="caps">What you are building</span>
      <span class="serif" style="font-size:28px;font-weight:600;line-height:1.2">${esc(o.structured.product)}</span>
      <span style="color:var(--ink2)">${esc(o.structured.success_criteria)}</span>
      ${steps(journeyStep())}
      ${done ? `<div class="row"><button class="btn primary" data-view="delivery">See your product</button></div>` : ""}</div>
    <div class="tiles">${tile(`${m.tasks_verified} of ${m.tasks_total}`, "Pieces of work done and checked")}${tile(m.founder_interventions, "Times you were needed")}
      ${tile(m.defects_caught_before_verified, "Mistakes caught before they counted")}${tile(m.blockers_cleared_without_founder, "Questions the team settled itself")}</div>
    <div class="two"><div class="card stack"><h2 style="font-size:17px">Needs you</h2>${needs}</div>
      <div class="card"><h2 style="font-size:17px;margin-bottom:6px">The work</h2>${rows}</div></div>`;
}

function statusText(t) {
  return {
    PLANNED: "Planned", ASSIGNED: "In progress", IN_PROGRESS: "In progress", BLOCKED: "Blocked", REVIEW: "Done by worker, verifying",
    LEAD_REVIEW: t.pending_proposal ? "With its cofounder, before it reaches you" : "Checked, with its cofounder for review",
    REWORK: "Rework", AWAITING_FOUNDER: "Waiting on you", APPROVED: "Approved, executing",
    VERIFIED: t.attempts ? "Verified after rework" : "Verified", FAILED: "Escalated",
    WAITING: t.waiting ? `Waiting: ${t.waiting.why}` : "Waiting",
  }[t.status] || t.status;
}

/* Who held a seat before, why they left, and the record they left. */
function formerList(w) {
  const f = w.former || [];
  if (!f.length) return "";
  return `<div class="stack" style="gap:6px"><span class="caps">Before in this seat</span>${f.map((x) => `<div class="small"><b>${esc(x.name)}</b> <span class="muted">on ${esc(modelName(x.model) || x.model || "an AI")}</span>: replaced because ${esc(x.why)}. Record: ${esc((x.record || {}).verified || 0)} verified, ${esc((x.record || {}).reworks || 0)} reworks.</div>`).join("")}</div>`;
}

function vOrg() {
  const st = S.st, ws = Object.fromEntries((st.workers || []).map((w) => [w.id, w]));
  const busyTask = (id) => (st.tasks || []).find((t) => t.owner_worker_id === id && !["PLANNED", "VERIFIED"].includes(t.status));
  const node = (id, note) => {
    const b = busyTask(id);
    return `<button class="node ${S.worker === id ? "sel" : ""}" data-worker="${id}"><b>${esc(ws[id] ? ws[id].name || seatOf(ws[id]) : id)}</b><small>${ws[id] ? `AI ${esc(seatOf(ws[id]))}` : ""}${note ? ` · ${esc(note)}` : ""}</small>
      ${b ? `<span class="busy">${esc(b.id)}: ${esc(statusText(b))}</span>` : ""}</button>`;
  };
  if (!ws[S.worker] && (st.workers || []).length) S.worker = st.workers[st.workers.length - 1].id;
  const w = ws[S.worker] || {};
  const p = w.performance_profile || {};
  const cur = (st.tasks || []).filter((t) => t.owner_worker_id === S.worker && t.status !== "VERIFIED").map((t) => `${t.id} ${statusText(t)}`).join(", ") || "none";
  const matrix = (st.policy.matrix[w.role] || {});
  const acts = ["write_file", "run_tests", "assign_task", "product_rule_decision", "merge_to_main", "deploy_production", "external_message"];
  const auth = acts.map((a) => {
    const g = matrix[a], risk = st.policy.risk[a];
    const [cls, txt] = risk === "PROHIBITED" ? ["N", "Prohibited"] : g === "execute" ? ["E", "Executes"] : g === "propose" ? ["P", "Proposes"] : ["N", "Not allowed"];
    return `<div class="kv"><span>${esc(ACT_TITLE[a] || a)}</span><span class="auth-${cls}">${txt}</span></div>`;
  }).join("");
  const ans = S.graph ? `<div class="small" id="graph-answer">${graphAnswer(S.graph)}</div>` : "";
  const kids = (id) => (st.workers || []).filter((x) => (x.reports_to || "founder") === id);
  // each cofounder a column with the team it leads, as on the plan: who reports to whom reads at a glance
  const col = (c) => `<div class="tcol">${node(c.id, c.tier === "cofounder" ? "cofounder" : c.led_by_founder ? "you lead this area" : "")}<div class="tmembers">${kids(c.id).map((x) => node(x.id, "")).join("")}</div></div>`;
  return `<div class="org"><div class="card tree">
      <div class="node founder"><b>You, the founder</b><small>The vision, the budget, and the calls that cannot be undone</small></div>
      <div class="tcols">${kids("founder").map(col).join("")}</div>
      <div class="node svc"><b>Verification Service</b><small style="color:var(--accent-ink)">Not a person. Checks every piece of work: tests, lint, review</small></div>
      <div class="card stack" style="margin-top:28px;width:100%;background:var(--paper);border:0">
        <label class="lbl" for="gq">Ask the organisation graph</label>
        <div class="row"><select id="gq"><option value="approves">Who approves</option><option value="owns">Who owns</option><option value="depends">What depends on</option></select>
          <input type="text" id="gs" value="merge_to_main" aria-label="Action type or task id" style="flex:1"><button class="btn sm" id="ask">Ask</button></div>${ans}</div></div>
    <div class="card side-panel stack"><div><span class="caps">AI ${esc(seatOf(w))}</span><h2 style="font-size:20px">${esc(w.name || seatOf(w))}</h2></div>
      ${w.name ? `<div class="row" style="gap:8px"><input type="text" id="rn_name" data-keep="yes" value="${esc(w.name)}" style="flex:1;min-width:0" aria-label="Name"><button class="btn sm" id="rename" data-id="${esc(w.id)}" ${S.busy ? "disabled" : ""}>Rename</button></div>` : ""}
      <div class="kv"><span>The AI it works on</span><span>${esc(w.model || ((wfv().workers || []).find((x) => x.id === w.id) || {}).model || "not yet")}${w.binding && w.binding.version ? " · version " + esc(w.binding.version) : ""}</span></div>
      <div class="kv"><span>Capabilities</span><span>${esc((w.capabilities || []).join(", "))}</span></div>
      <div class="kv"><span>Reports to</span><span>${esc(wt(w.reports_to))}</span></div>
      <div class="kv"><span>Current work</span><span>${esc(cur)}</span></div>
      <div class="kv"><span>Verified, first pass</span><span class="mono">${p.verified || 0}, ${p.first_pass || 0}</span></div>
      <div class="kv"><span>Reworks, questions raised</span><span class="mono">${p.reworks || 0}, ${p.blockers || 0}</span></div>
      <h3 style="font-size:15px;margin-top:6px">What this seat may do</h3>${auth}
      ${formerList(w)}
      <p class="small muted" style="margin:6px 0 0">The seat keeps its work, authority and history. When an AI in it cannot do the work, a new person takes the seat, with a record of their own; an outage replaces no one.</p></div></div>`;
}
/* ---------------------------------------------------------------- the AI workforce and the model registry -- */
const wfv = () => (S.st && S.st.workforce) || {};
const regModels = () => (S.sup && S.sup.intelligence) || wfv().registry || [];
const supConns = () => (S.sup && S.sup.connections) || [];
const connName = (id) => (supConns().find((c) => c.id === id) || {}).name || "a removed connection";
// cents as usual; a fraction of a cent (one AI call can cost that) keeps four places, and nothing is $0.00
const usd = (v) => { if (v === null || v === undefined) return "n/a"; const n = Number(v), a = Math.abs(n); return `$${n.toFixed(a > 0 && a < 0.01 ? 4 : 2)}`; };
const pctx = (v) => (v === null || v === undefined ? "n/a" : `${Math.round(v * 100)}%`);
const PTYPE = { openai_compatible: "OpenAI-compatible API", anthropic: "Anthropic API", local: "Local / self-hosted",
  demo_script: "Demo script (not a provider)", bedrock: "AWS Bedrock" };

function candTable(rows, chosen, compact) {
  if (!rows || !rows.length) return "";
  return `<div class="tscroll"><table class="tbl"><thead><tr><th>Model</th><th>P(verified)</th><th>Expected cost</th><th>Expected time</th><th>Score</th><th>${compact ? "Samples" : "Evidence"}</th></tr></thead><tbody>
    ${rows.map((r) => `<tr class="${r.model_id === chosen ? "chosen" : ""}${r.fits_budget === false ? " over" : ""}"><td>${esc(r.model)}${r.model_id === chosen ? " ✓" : ""}</td>
      <td class="mono">${pctx(r.p_task)}</td><td class="mono">${usd(r.expected_usd)}</td><td class="mono">${esc(r.expected_minutes)} min</td>
      <td class="mono">${esc(r.score)}</td><td class="small">${compact ? esc((r.by_kind || []).reduce((a, k) => a + (k.samples || 0), 0))
        : esc((r.by_kind || []).map((k) => `${k.kind}: ${k.basis}`).join("; "))}</td></tr>`).join("")}</tbody></table></div>`;
}

function vWorkforce() {
  const wf = wfv();
  if (!wf.active) return `<div class="card"><p class="muted" style="margin:0">No workers yet.</p></div>`;
  const L = wf.ledger || {}, s = wf.settings || {};
  const alloc = Object.values(L.allocated || {}).reduce((a, b) => a + b, 0);
  const tile = (v, l) => `<div class="tile"><b>${v}</b><span>${l}</span></div>`;
  const workers = (wf.workers || []).map((w) => `<div class="card stack">
      <div class="between"><div style="min-width:0;overflow-wrap:anywhere"><span class="caps">AI ${esc(w.seat || w.title)}</span><h2 style="font-size:20px">${esc(w.name || w.title)}</h2></div>
        <span class="pill teal">${esc(w.model)}</span></div>
      <div class="kv"><span>Budget allocated, spent</span><span class="mono">${usd(w.budget.allocated)}, ${usd(w.budget.spent)}</span></div>
      <div class="kv"><span>Verified, first pass, reworks</span><span class="mono">${w.performance.verified || 0}, ${w.performance.first_pass || 0}, ${w.performance.reworks || 0}</span></div>
      <div class="small muted">${esc(w.why)}</div>
      ${formerList(w)}${w.binding && (w.binding.history || []).length && !(w.former || []).length ? `<div class="small muted">Earlier AIs for ${esc(w.name || "this seat")}: ${esc(w.binding.history.map((h) => `${h.intelligence} (${h.reason})`).join("; "))}.</div>` : ""}
      <details><summary class="small">The staffing choice: every available intelligence, scored for this worker's work</summary>${candTable(w.candidates, w.model_id, true)}</details></div>`).join("");
  const reps = (wf.replacements || []).map((r) => `<div class="card stack rep">
      <div class="between"><b>${esc(r.task_id)}: ${esc(r.role)} ${esc(r.worker_id)} moved from ${esc(modelName(r.from))} to ${esc(modelName(r.to))}</b><span class="small muted">${esc(r.at)}</span></div>
      <span class="small">Why: ${esc(r.reason)}</span>
      <span class="small">Before the change: ${esc(r.attempts)} attempt${r.attempts === 1 ? "" : "s"} on this task reached verification, and ${usd(r.usd_spent_by_previous)} was spent on it.</span>
      <span class="small">Inherited: ${esc(r.inherited.join(", "))}.</span>
      <details><summary class="small">The choice: every other available model</summary>${candTable(r.candidates, r.to)}</details></div>`).join("")
    || `<p class="muted small">No worker has been replaced in this run.</p>`;
  const notes = (wf.ceo_notices || []).slice().reverse().map((n) => `<div class="card stack"><b>${esc(n.headline)}</b><span class="small">${esc(n.detail)}</span>
      ${n.usd_difference !== null && n.usd_difference !== undefined ? `<span class="small mono">${n.usd_difference > 0 ? "+" : ""}${usd(n.usd_difference)} a task</span>` : ""}</div>`).join("")
    || `<p class="muted small">Nothing to tell you yet.</p>`;
  const ledger = (L.events || []).slice(-8).reverse().map((e) => `<div class="list-row small"><span>${e.what === "allocated" ? `Allocated ${e.tasks} tasks` : `${esc(e.task)}: released ${usd(e.released)} from ${esc(modelName(e.from))}, drew ${usd(e.drawn)} for ${esc(modelName(e.to))}`}</span><span class="mono">reserve ${usd(e.reserve)}</span></div>`).join("");
  const reuse = Object.entries(wf.models_in_use || {}).map(([m, ws]) => `<div class="kv"><span>${esc(modelName(m))}</span><span>${esc(ws.map(wt).join(", "))}</span></div>`).join("");
  return `<div class="tiles">${tile(usd(s.budget_usd), "Budget")}${tile(usd(alloc), "Allocated to tasks")}${tile(usd(L.spent_total), "Spent")}
      ${tile(usd(L.reserve), "Reserve for retries and replacements")}${tile(`$${esc(s.time_value_per_hour)}/h`, "Value of an hour")}${tile((wf.replacements || []).length, "Replacements")}</div>
    <div class="card stack"><h2 style="font-size:17px">Models in use</h2><span class="small muted">Worker is not model: one model can power many workers, and workers with the same title can run on different models.</span>${reuse}</div>
    <div class="grid2">${workers}</div>
    <h2 style="font-size:17px;margin:10px 0 4px">What Cynqra told you</h2><p class="small muted" style="margin:0 0 6px">A worker's AI is replaced only when it cannot do the role's work. A provider's outage or an account problem is waited out or brought to you. You are told each time, with the cost.</p>${notes}
    <h2 style="font-size:17px;margin:10px 0 4px">Replacements</h2>${reps}
    <div class="card"><h2 style="font-size:17px;margin-bottom:6px">Budget ledger</h2>${ledger || '<p class="muted small">Nothing allocated yet.</p>'}</div>`;
}

function scorecards() {
  const cards = S.st.performance || [];
  if (!cards.length) return "";
  const n = (v) => (v === null || v === undefined ? "n/a" : v);
  const rows = cards.map((c) => c.by_model.map((m) => `<tr><td>${esc(wt(c.worker_id))}</td><td>${esc(modelName(m.model_id) || "")}${m.model_id === c.model_id ? " (now)" : ""}</td>
    <td class="mono">${pctx(m.quality.acceptance_rate)}</td><td class="mono">${n(m.quality.defect_escapes)}</td>
    <td class="mono">${pctx(m.reliability.failure_rate)} / ${n(m.reliability.protocol_violations)} / ${n(m.reliability.tool_errors)}</td>
    <td class="mono">${n(m.efficiency.latency_s)} s / ${n(m.efficiency.retries)}</td><td class="mono">${usd(m.economics.usd_per_verified)}</td>
    <td class="mono">${m.capability_fit ? pctx(m.capability_fit.benchmark_pass_rate) : "n/a"}</td><td class="small">${m.stability ? esc(m.stability.regression) : "n/a"}</td>
    <td class="mono">${n(m.human_friction.escalations)} / ${n(m.human_friction.rejections)}</td></tr>`).join("")).join("");
  return `<div class="card"><h2 style="font-size:17px;margin-bottom:6px">Performance Engine: every worker on every model it ran on</h2>
    <div class="tscroll"><table class="tbl"><thead><tr><th>Worker</th><th>Model</th><th>Acceptance</th><th>Escapes</th><th>Fail rate / violations / tool errors</th>
    <th>Latency / retries</th><th>Cost per verified</th><th>Benchmark</th><th>Regression</th><th>Escalations / rejections</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
}

function companyPack(f) {
  const p = f.company_pack;
  if (!p) return "";
  const docs = (p.documents || []).map((d) => `<div class="kv"><span>${esc(d.title)}<br><span class="small muted">${esc(d.author)}${d.types.length ? " · " + esc(d.types.join(", ")) : ""}</span></span><span style="color:${d.verified ? "var(--green)" : "var(--muted)"};font-weight:600">${d.verified ? "checked" : "not checked"}</span></div>`).join("") || `<p class="small muted">No documents in this project.</p>`;
  const said = (d) => (d.status === "approved" ? "approved" : "turned down");
  const dec = (p.ceo_decisions || []).map((d) => `<div class="kv"><span>${esc(KIND_TITLE[d.kind] || d.kind)}${d.task ? `: ${esc(d.task)}` : ""}</span><span style="color:${d.status === "approved" ? "var(--green)" : "var(--red)"};font-weight:600">${said(d)}</span></div>`).join("") || `<p class="small muted">None.</p>`;
  const settled = (p.settled_for_you || []).map((d) => `<div class="kv"><span>${esc(KIND_TITLE[d.kind] || d.kind)}${d.task ? `: ${esc(d.task)}` : ""}</span><span style="color:var(--green);font-weight:600">${said(d)} by ${esc(d.by)}</span></div>`).join("");
  return `<div class="stack">
    <div class="pack-sec" data-pack="documents"><h3>Documents</h3>${docs}</div>
    <div class="pack-sec" data-pack="decisions"><h3>Your decisions</h3>${dec}</div>
    ${settled ? `<div class="pack-sec"><h3>Settled for you by a cofounder</h3>${settled}</div>` : ""}</div>`;
}

function finalReport() {
  const f = S.st.final;
  if (!f) return "";
  const ec = f.economics || {};
  const layers = Object.entries(ec.layers || {}).map(([k, v]) => `<tr><td>${esc(k)}</td><td class="mono">${usd(v.forecast)}</td><td class="mono">${usd(v.actual)}</td><td class="mono">${usd(v.variance)}</td></tr>`).join("");
  const byw = Object.entries(ec.by_worker || {}).map(([w, v]) => `<tr><td>${esc(wt(w))}</td><td class="mono">${usd(v.forecast)}</td><td class="mono">${usd(v.actual)}</td></tr>`).join("");
  const changes = (f.intelligence_changes || []).map((r) => `<div class="small">${esc(r.task_id)}: ${esc(wt(r.worker_id))} ${r.rerouted ? `rerouted to ${esc(wt(r.to_worker))}` : `moved from ${esc(modelName(r.from))} to ${esc(modelName(r.to))}`}. ${esc(r.reason)}</div>`).join("") || `<p class="small muted">No intelligence changed in this run.</p>`;
  return `<div class="card stack"><h2 style="font-size:17px">Final report</h2>
    <div class="small">Delivered: ${esc(f.artifacts.length)} files (${esc(f.artifacts.slice(0, 12).join(", "))}${f.artifacts.length > 12 ? ", ..." : ""})${f.live_url ? `, live at ${esc(f.live_url)}` : ""}.</div>
    <div class="two"><div><span class="caps">Budget, forecast against actual</span><div class="tscroll"><table class="tbl"><thead><tr><th>Layer</th><th>Forecast</th><th>Actual</th><th>Variance</th></tr></thead><tbody>${layers}
      <tr><td><b>Total</b></td><td class="mono">${usd(ec.total_forecast)}</td><td class="mono">${usd(ec.total_actual)}</td><td class="mono">cap ${usd(ec.cap_usd)}</td></tr></tbody></table></div></div>
      <div><span class="caps">By worker</span><div class="tscroll"><table class="tbl"><thead><tr><th>Worker</th><th>Forecast</th><th>Actual</th></tr></thead><tbody>${byw}</tbody></table></div></div></div>
    <span class="caps">Intelligence changes</span>${changes}
    <div class="small">First pass ${pctx(f.metrics.first_pass_rate)}, reworks ${esc(f.metrics.reworks)}, defect escapes ${esc(f.metrics.defect_escapes)}, false rejections ${esc(f.metrics.false_rejections)}, verification ${esc(f.metrics.verification_seconds)} s.
      Every worker's scorecard is in <button class="btn sm" data-view="performance">Performance</button>.</div></div>`;
}

function modelName(id) { const m = regModels().find((x) => x.id === id); return m ? m.name : id; }

function perfRows(perf) {
  const row = (label, s) => `<tr><td>${esc(label)}</td><td class="mono">${s.attempts}</td><td class="mono">${pctx(s.success_rate)}</td><td class="mono">${pctx(s.first_pass_rate)}</td>
    <td class="mono">${usd(s.usd_per_attempt)}</td><td class="mono">${s.seconds_per_attempt === null ? "n/a" : (s.seconds_per_attempt / 60).toFixed(1) + " min"}</td></tr>`;
  const kinds = Object.entries(perf.by_task_kind || {});
  if (!perf.overall.attempts) return `<p class="small muted">No measured work yet. Probe it, or let it work: every verification it gets is recorded here.</p>`;
  return `<div class="tscroll"><table class="tbl"><thead><tr><th>Work</th><th>Attempts</th><th>Verified</th><th>First pass</th><th>Cost/attempt</th><th>Time/attempt</th></tr></thead><tbody>
    ${row("All", perf.overall)}${kinds.map(([k, s]) => row(k, s)).join("")}</tbody></table></div>`;
}

function connCard(c) {
  const cr = c.credential || {}, offered = regModels().filter((m) => m.connection_id === c.id && m.status !== "retired");
  const auth = cr.method === "env" ? `key in the environment variable ${cr.env_var}` : cr.method === "secret" ? "key kept in Cynqra's secrets file" : "no key";
  return `<div class="card stack mcard">
    <div class="between"><div><span class="caps">${esc(PTYPE[c.type] || c.type)}${c.server ? " · " + esc(c.server) : ""}</span><h2 style="font-size:17px">${esc(c.name)}</h2></div>
      <span class="pill ${c.status === "connected" ? "teal" : "warn"}">${esc(c.status)}</span></div>
    ${c.endpoint ? `<div class="kv"><span>Endpoint</span><span class="mono small">${esc(c.endpoint)}</span></div>` : ""}
    <div class="kv"><span>Credential</span><span>${cr.method === "none" ? "none needed" : `${esc(auth)}: ${cr.present ? "present" : esc(cr.status || "missing")}`}</span></div>
    <div class="kv"><span>Offers</span><span>${offered.length ? esc(offered.slice(0, 6).map((m) => m.name).join(", ")) + (offered.length > 6 ? ` and ${offered.length - 6} more` : "") : "nothing yet"}</span></div>
    ${c.rate_limits && c.rate_limits.calls_per_minute ? `<div class="kv"><span>Rate limit</span><span>${esc(c.rate_limits.calls_per_minute)} calls per minute</span></div>` : ""}
    <div class="kv"><span>Added</span><span>${esc(c.permission)}</span></div>
    ${c.status_note ? `<p class="small muted" style="margin:0">${esc(c.status_note)}</p>` : ""}
    ${(() => { const ids = offered.map((m) => m.id), q = ids.filter((i) => ["queued", "running"].includes((S.probes[i] || {}).state)).length;
      return q ? `<div class="notice small">Evaluating ${q} of ${ids.length} model${ids.length === 1 ? "" : "s"} on Cynqra's own work. Nothing is assigned on a name or a default.</div>` : ""; })()}
    ${browser(c)}
    <div class="row wrap" style="gap:8px">${c.origin === "demo" || c.type === "local" ? "" : `<button class="btn sm" data-browse="${esc(c.id)}">${S.browse[c.id] ? "Close the model list" : "Search and choose models"}</button>`}<button class="btn sm" data-discover="${esc(c.id)}">Discover again</button>
      ${c.origin === "demo" ? "" : `<button class="btn sm" data-disconnect="${esc(c.id)}">Remove</button>`}</div></div>`;
}

function intelCard(m) {
  const pr = S.probes[m.id] || {}, o = m.performance.overall, f = m.fault || {};
  const others = regModels().filter((x) => x.id !== m.id && x.status !== "retired");
  return `<div class="card stack mcard">
    <div class="between"><div><span class="caps">${esc(connName(m.connection_id))}</span><h2 style="font-size:20px">${esc(m.name)}</h2></div>
      <span class="pill ${m.available ? "teal" : "warn"}">${m.available ? "Available" : esc(m.availability)}</span></div>
    <div class="kv"><span>Serves</span><span class="mono small">${esc(m.ref)}${m.version ? " · version " + esc(m.version) : ""}</span></div>
    <div class="kv"><span>Provider, licence</span><span>${esc(m.provider || "n/a")}, ${esc(m.license || "n/a")}</span></div>
    <div class="kv"><span>Context, hardware</span><span>${esc(m.context || "n/a")} tokens, ${esc(m.hardware || "n/a")}</span></div>
    <div class="kv"><span>Price</span><span class="mono">${m.local ? `$${m.compute_usd_per_hour}/h of this computer` : `$${m.price_in} in, $${m.price_out} out per M tokens`}</span></div>
    <div class="kv"><span>Regression check</span><span>${esc((m.regression || {}).status || "n/a")}</span></div>
    <div class="kv"><span>Calls, errors, speed</span><span class="mono">${o.calls}, ${o.call_errors}, ${o.write_tps ? o.write_tps + " tokens/s" : "n/a"}</span></div>
    ${evalLine(m, pr)}
    <h3 style="font-size:14px;margin-top:4px">Measured on Cynqra's work</h3>${perfRows(m.performance)}
    ${Object.keys(f).length ? `<div class="notice small">Fault set: ${f.offline ? "offline" : ""}${f.offline && f.max_reply ? ", " : ""}${f.max_reply ? `replies capped at ${f.max_reply} tokens` : ""}</div>` : ""}
    <div class="row wrap" style="gap:8px">
      <button class="btn sm" data-probe="${esc(m.id)}" ${["running", "queued"].includes(pr.state) ? "disabled" : ""}>${pr.state === "running" ? "Evaluating..." : pr.state === "queued" ? "Waiting to be evaluated" : o.calls ? "Evaluate again" : "Evaluate it"}</button>
      <button class="btn sm" data-fault-off="${esc(m.id)}" data-on="${f.offline ? "0" : "1"}">${f.offline ? "Bring back online" : "Take offline"}</button>
      <input type="number" id="cap_${esc(m.id)}" min="0" step="10" placeholder="reply cap" value="${esc(f.max_reply || "")}" style="width:100px" aria-label="Reply cap in tokens">
      <button class="btn sm" data-fault-cap="${esc(m.id)}">Set reply cap</button>
      <select id="fb_${esc(m.id)}" aria-label="Fallback"><option value="">No fallback</option>${others.map((x) => `<option value="${esc(x.id)}" ${x.id === m.fallback_id ? "selected" : ""}>Fallback: ${esc(x.name)}</option>`).join("")}</select>
      <button class="btn sm" data-fallback="${esc(m.id)}">Set fallback</button>
      <button class="btn sm" data-retire="${esc(m.id)}">Retire</button></div>
    ${pr.log && pr.log.length ? `<pre class="log">${esc(pr.log.join("\n"))}${pr.error ? "\n" + esc(pr.error) : ""}</pre>` : ""}</div>`;
}

// Cynqra evaluates every connected model on its own work before relying on it: planning a founder's words into a
// brief (what a cofounder does) and writing code that passes its tests (what an engineer does).
function evalLine(m, pr) {
  const st = pr.state;
  if (st === "queued") return `<div class="notice small">Waiting for its evaluation: Cynqra will have it plan a brief and write code that must pass tests.</div>`;
  if (st === "running") return `<div class="notice small">Being evaluated now: planning a brief, then writing code that must pass its tests. This can take a few minutes on a free endpoint.</div>`;
  if (st === "error") return `<div class="notice warn small">The evaluation could not finish: ${esc(pr.error || "")}</div>`;
  if (st === "done") return `<div class="notice small">Evaluated. Cynqra uses these measurements to choose which team members this model powers.</div>`;
  return m.performance.overall.calls ? "" : `<div class="notice small">Not evaluated yet. Press "Evaluate it" so Cynqra can measure it before choosing it for anyone.</div>`;
}

// The models a connection's provider lists: search them and choose which ones Cynqra may use.
function browser(c) {
  const b = S.browse[c.id];
  if (!b) return "";
  if (b.loading) return `<div class="notice small">Reading the list of models from ${esc(c.name)}...</div>`;
  if (b.err) return `<div class="notice warn small">${esc(b.err)}</div>`;
  const month = (t) => t ? new Date(t * 1000).toLocaleDateString(undefined, { month: "short", year: "numeric" }) : "";
  const all = b.models || [], shown = all.filter((x) => b.all || x.current || b.sel.has(x.ref)), hidden = all.length - shown.length;
  const list = shown.map((x) => `<label class="mb-row" data-mb-name="${esc((x.ref + " " + x.name).toLowerCase())}">
      <input type="checkbox" data-mb="${esc(c.id)}" value="${esc(x.ref)}" ${b.sel.has(x.ref) ? "checked" : ""}>
      <span class="mono small">${esc(x.ref)}</span>
      <span class="small muted">${x.released ? `Released ${esc(month(x.released))}` : "Release date unknown"}${x.current ? "" : " · older"}</span></label>`).join("");
  return `<div class="stack mbrowser" style="gap:8px">
    <p class="small muted" style="margin:0">${b.dates ? `Newest first. Shown: models released in the last 12 months, the newest version of each.` : "Release dates could not be read, so every model is listed."}${hidden ? ` <button class="linkbtn" data-mb-all="${esc(c.id)}">Show ${hidden} older or undated model${hidden === 1 ? "" : "s"}</button>` : b.all && b.dates ? ` <button class="linkbtn" data-mb-all="${esc(c.id)}">Show only the latest</button>` : ""}</p>
    <input type="search" id="mb_q_${esc(c.id)}" data-mb-search="${esc(c.id)}" placeholder="Search ${esc(shown.length)} models, e.g. kimi, gemini, glm" aria-label="Search models">
    <div class="mb-list">${list || '<p class="small muted">The provider lists no chat models.</p>'}</div>
    <div class="between"><span class="small muted" id="mb_n_${esc(c.id)}">${b.sel.size} chosen. Cynqra evaluates each new one, then decides who it powers.</span>
      <button class="btn sm primary" data-mb-save="${esc(c.id)}" ${S.busy ? "disabled" : ""}>Use the chosen models</button></div></div>`;
}

function vIntelligence() {
  const types = (S.sup && S.sup.provider_types) || [];
  const models = regModels().filter((m) => m.status !== "retired");
  const opts = types.map((t) => `<option value="${esc(t.type)}" ${t.implemented ? "" : "disabled"}>${esc(t.title)}${t.implemented ? "" : " (planned)"}</option>`).join("");
  return `<div class="card stack"><h2 style="font-size:17px">Connect a provider</h2>
      <p class="small muted" style="margin:0">Connect a source of intelligence once. Cynqra discovers the models it offers, measures them on its own work, and the Intelligence Router picks which one powers each worker. A worker never holds a key: the connection keeps a reference to its credential, and only the Intelligence Gateway reads it, for one call at a time. Name an environment variable, or keep the key in Cynqra's secrets file on this computer.</p>
      <div class="form-grid">
        <label class="fld"><span>Provider</span><select id="c_type">${opts}</select></label>
        <label class="fld"><span>Name</span><input type="text" id="c_name" placeholder="e.g. My OpenAI account"></label>
        <label class="fld wide"><span>Endpoint URL</span><input type="text" id="c_endpoint" placeholder="blank: the provider's own"></label>
        <label class="fld"><span>Local server</span><select id="c_server"><option value="">Not a local server</option><option value="ollama">Ollama</option><option value="endpoint">A server at the endpoint</option><option value="llama">This computer</option></select></label>
        <label class="fld"><span>Key</span><select id="c_auth"><option value="secret">In Cynqra's secrets file</option><option value="env">In an environment variable</option><option value="none">No key</option></select></label>
        <label class="fld"><span>Environment variable</span><input type="text" id="c_env" placeholder="e.g. OPENAI_API_KEY"></label>
        <label class="fld"><span>Key (secrets file only)</span><input type="password" id="c_secret" autocomplete="off"></label>
        <label class="fld wide"><span>Models to offer</span><input type="text" id="c_models" placeholder="blank: the newest models it lists (last 12 months)"></label>
        <label class="fld"><span>Price in, $ per million tokens</span><input type="number" id="c_in" step="0.01"></label>
        <label class="fld"><span>Price out, $ per million tokens</span><input type="number" id="c_out" step="0.01"></label>
        <label class="fld"><span>Calls per minute</span><input type="number" id="c_rpm"></label>
        <label class="fld"><span>Thinking effort</span><select id="c_effort"><option value="">The model's own default</option><option value="low">Low (fastest)</option><option value="medium">Medium</option><option value="high">High</option></select></label>
      </div>
      <div class="row"><button class="btn primary" id="connect">Connect</button></div></div>
    <h2 style="font-size:17px;margin:6px 0 0">Provider connections</h2>
    <div class="grid2">${supConns().map(connCard).join("") || '<p class="muted">No provider connected yet.</p>'}</div>
    <h2 style="font-size:17px;margin:6px 0 0">Intelligence Registry</h2>
    <p class="small muted" style="margin:0">What each connection offers, with the facts its provider gives and what Cynqra has measured. Nothing here is a hand-made score.</p>
    <div class="grid2">${models.map(intelCard).join("") || '<p class="muted">No intelligence registered yet.</p>'}</div>`;
}

function regScreen() {
  return `<div class="wiz"><div class="wiz-top"><div class="row"><span class="wordmark">Cynqra</span><span class="muted small">Intelligence</span></div>
    <div class="row"><button class="btn sm primary" data-reg-close="1">Done</button></div></div>
    <div class="view">${S.err && !S.errAt ? `<div class="err" role="alert">${esc(S.err)}</div>` : ""}${vIntelligence()}</div></div>`;
}

function graphAnswer(g) {
  if (g.error) return `<span style="color:var(--red)">${esc(g.error)}</span>`;
  if (g.approves) return `<b>${esc(g.action_type)}</b> (${esc(g.risk_tier)}): executes ${esc(g.executes.join(", ") || "nobody")}; proposes ${esc(g.proposes.join(", ") || "nobody")}; approves: ${esc(g.approves)}.`;
  if (g.owner) return `<b>${esc(g.task)}</b> is owned by ${esc(wt(g.owner))}, who reports to ${esc(wt(g.reports_to))}.`;
  return `<b>${esc(g.task)}</b> depends on ${esc(g.depends_on.join(", ") || "nothing")}; needed by ${esc(g.needed_by.join(", ") || "nothing")}.`;
}

function vWork() {
  const st = S.st, ts = st.tasks || [], active = st.last_step && st.last_step.task;
  const cols = [["Planned", ["PLANNED"]], ["In progress", ["ASSIGNED", "IN_PROGRESS", "BLOCKED", "REWORK"]],
    ["Review", ["REVIEW", "LEAD_REVIEW", "AWAITING_FOUNDER", "APPROVED", "FAILED"]], ["Verified", ["VERIFIED"]]];
  const note = (t) => {
    if (t.status === "BLOCKED") return `<span class="small" style="color:var(--amber-ink)">Blocked: ${esc((t.blocker || {}).description)}</span>`;
    if (t.status === "REWORK") return `<span class="small" style="color:var(--red)">Rework: ${esc((t.feedback || "").split("\n")[0])}</span>`;
    if (t.status === "AWAITING_FOUNDER") return `<span class="small" style="color:var(--amber-ink)">Needs you: ${esc(t.risk_tier)} risk</span>`;
    if (t.status === "PLANNED") return `<span class="small muted">${t.dependencies.length ? "Depends on " + esc(t.dependencies.join(", ")) : "Ready"}</span>`;
    if (t.status === "REVIEW") return `<span class="small" style="color:var(--blue)">Completed by the worker. Not yet verified.</span>`;
    if (t.status === "LEAD_REVIEW") return `<span class="small" style="color:var(--blue)">${t.pending_proposal ? "Proposal" : "Passed the checks"}. ${esc(wt(t.reviewed_by))} reviews it.</span>`;
    if (t.status === "VERIFIED") return `<span class="small" style="color:var(--green)">${esc(statusText(t))}</span>`;
    if (t.status === "ASSIGNED") return `<span class="small" style="color:var(--accent-ink)">Handoff received${(t.answers || []).length ? ", Blocker answered" : ""}</span>`;
    return `<span class="small muted">${esc(statusText(t))}</span>`;
  };
  const colHtml = cols.map(([name, sts]) => `<div class="col"><span class="caps" style="font-weight:600">${name}</span>
    ${ts.filter((t) => sts.includes(t.status)).map((t) => `<div class="tcard ${active === t.id ? "active" : ""} ${fresh("t:" + t.id + ":" + t.status)}" data-task="${esc(t.id)}"><span class="meta">${esc(t.id)} · ${esc(t.risk_tier)}</span><span class="who">${esc(((S.st.workers || []).find((x) => x.id === t.owner_worker_id) || {}).name || t.owner_worker_id)}</span>
      <span class="ttl">${esc(t.title)}</span>${note(t)}</div>`).join("")}</div>`).join("");
  const tape = (st.protocols || []).slice().reverse().map((p) => `<div class="pobj ${esc(p.kind)} ${fresh("p:" + p.id)}" data-task="${esc(p.task_id)}"><span class="h">${esc(p.kind)} · ${esc(wt(p.sender))} to ${esc(wt(p.to))} · ${esc(p.task_id)}</span>
    <span class="small">${esc(p.summary)}</span>${p.artifacts && p.artifacts.length ? `<span class="small muted mono">${esc(p.artifacts.join(", "))}</span>` : ""}</div>`).join("");
  return `<p class="small muted" style="margin:0">Completed means a worker says it is done. Verified means the Verification Service agrees and, for a team member's work, its cofounder approved it.</p>
    <div class="work"><div class="cols">${colHtml}</div>
    <div class="tape card"><h2 style="font-size:17px">Protocol tape</h2><span class="small muted">Every message between workers is a structured object. No free chat.</span>${tape || `<span class="muted small">No messages yet.</span>`}</div></div>`;
}

function vDecisions() {
  const st = S.st, pend = st.decisions.pending || [], main = pend.filter((d) => !d.in_digest), dig = pend.filter((d) => d.in_digest);
  const card = (d, big) => {
    const extra = d.kind === "decision" ? `<label class="lbl" for="edit_${d.id}">Edit the rule before approving (optional)</label>
        <textarea class="note" id="edit_${d.id}">${esc(d.recommendation)}</textarea>` : d.kind === "budget_breaker" ?
      `<label class="lbl" for="usd_${d.id}">New budget, US dollars</label><input type="number" id="usd_${d.id}" step="0.5" value="${esc((Math.max(st.budget.settings.budget_usd, st.budget.ledger.spent_total) * 1.5).toFixed(2))}">` : "";
    const side = d.extra && d.extra.side_action ? `<div class="deny"><span class="h">${d.extra.side_action.status === "denied" ? "Stopped" : esc(d.extra.side_action.status)}: ${actionTitle("external_message")}</span><span class="small">${esc(d.extra.side_action.summary)} ${esc(d.extra.side_action.reason)}</span></div>` : "";
    return `<div class="dcard ${fresh("d:" + d.id)}"><div class="between"><span class="mono small muted">${esc(d.id)} · from ${esc(wt(d.source))}${d.extra && d.extra.endorsed_by ? `, endorsed by ${esc(wt(d.extra.endorsed_by))}` : ""}</span>${riskPill(d.risk)}</div>
      <h2>${esc(KIND_TITLE[d.kind] || d.kind)}${d.task_id ? `: ${esc(taskTitle(d.task_id))}` : ""}</h2>
      <div class="dgrid"><div><span class="caps">Problem</span><p>${esc(d.problem)}</p></div><div><span class="caps">Recommendation</span><p>${esc(d.recommendation)}</p></div>
        <div><span class="caps">Evidence</span><p>${esc((d.evidence_refs || []).join("; ") || "none")}</p></div><div><span class="caps">What would change this</span><p>${esc(d.what_would_change_this)}</p></div></div>
      <div class="dline"><span><b>Cost</b>${esc(d.cost)}</span><span><b>Risk</b>${esc(d.risk)}</span><span><b>Confidence</b>${esc(d.confidence)}</span>${["escalation", "budget_breaker"].includes(d.kind) ? `<span><b>Severity</b>${esc(d.severity)}</span>` : ""}</div>
      ${side}${extra}
      <label class="lbl" for="note_${d.id}">Reason, if you reject or ask for more</label><textarea class="note" id="note_${d.id}" data-keep="yes"></textarea>
      <div class="row"><button class="btn primary" data-decide="approve" data-id="${d.id}" ${S.busy ? "disabled" : ""}>Approve</button>
        <button class="btn" data-decide="reject" data-id="${d.id}" ${S.busy ? "disabled" : ""}>Reject</button>
        ${EVIDENCE_KINDS.includes(d.kind) ? `<button class="btn" data-decide="request_evidence" data-id="${d.id}" ${S.busy ? "disabled" : ""}>Request more evidence</button>` : ""}</div></div>`;
  };
  const label = (d) => (d.outcome_label === "settled_by_cofounder" ? `settled by the ${wt(d.resolved_by)}` : String(d.outcome_label || d.status).replace(/_/g, " "));
  const answered = (st.decisions.answered || []).map((d) => `<div class="kv"><span>${esc(KIND_TITLE[d.kind] || d.kind)}${d.task_id ? ": " + esc(taskTitle(d.task_id)) : ""}</span>
    <span style="color:${d.status === "approved" ? "var(--green)" : "var(--red)"}">${esc(label(d))}</span></div>`).join("") || `<span class="muted small">Nothing yet.</span>`;
  const denied = (st.denied || []).map((a) => `<div class="deny"><span class="h">Stopped: ${esc(actionTitle(a.action_type))} by the ${esc(wt(a.worker_id))}, on ${esc(taskTitle(a.task_id))}</span><span class="small">${esc(a.policy_reason)}</span></div>`).join("") || `<span class="muted small">Nothing stopped yet.</span>`;
  return `<p class="small muted" style="margin:0">Every answer you give is kept on the record. Brought to you today: ${st.metrics.escalations_today} of at most ${st.metrics.escalation_budget}; anything past that waits in a daily digest.</p>
    <div class="dec"><div class="dec-main">${main.map((d, i) => card(d, i === 0)).join("") || `<div class="card"><p class="muted" style="margin:0">Nothing waits on you. The organisation is working.</p></div>`}
      ${dig.length ? `<div class="card"><h3 style="font-size:15px">Daily digest, over the escalation budget</h3>${dig.map((d) => card(d, false)).join("")}</div>` : ""}</div>
      <div class="dec-side"><div class="card stack"><h3 style="font-size:15px">Answered</h3>${answered}</div>
        <div class="card stack"><h3 style="font-size:15px">Stopped by policy, nothing for you to do</h3>${denied}</div></div></div>`;
}

function vPerformance() {
  const st = S.st;
  if (!(st.performance || []).length) return `<div class="card"><p class="muted">No organisation yet.</p></div>`;
  const evals = (st.evaluations || []).slice().reverse().map((e) => `<div class="list-row small"><span><b>${esc(e.decision)}</b> ${esc(e.task_id)}, ${esc(wt(e.worker_id))} on ${esc(modelName(e.model_id))}: ${esc(e.why)}${e.regression_check ? ` · regression check: ${esc(e.regression_check)}` : ""}${e.why_kept ? ` · ${esc(e.why_kept)}` : ""}</span><span class="mono">${esc(e.at.slice(11, 19))}</span></div>`).join("");
  return `<p class="small muted" style="margin:0">Intelligence is measured on the work itself, per worker and per model it ran on: quality, reliability, efficiency, cost, fit and stability. The Replacement Engine reads these signals.</p>
    ${scorecards()}
    <div class="card stack"><h2 style="font-size:17px">Replacement Engine</h2><span class="small muted">Every evaluation, and whether it kept the model, rerouted the task to a peer or replaced the model, with the reason.</span>${evals || '<p class="muted small">No evaluation yet: no worker has crossed a threshold.</p>'}</div>`;
}

async function loadReplay() {
  const ts = (S.st && S.st.tasks) || [];
  if (!ts.length) return;
  if (!S.replayTask) S.replayTask = (ts.find((t) => t.kind === "code" && t.status === "VERIFIED") || ts[0]).id;
  const key = S.replayTask + ":" + ((S.st.events || []).slice(-1)[0] || {}).seq;
  if (key === S.replayKey) return;
  try { S.replay = await api(`/api/replay/${S.replayTask}`); S.replayKey = key; } catch (e) { S.replay = { error: e.message }; }
}

function vAudit() {
  const st = S.st, evs = (st.events || []).slice().reverse();
  const last = evs.length ? evs[0].seq : 0;
  const rows = evs.map((e) => `<tr class="${e.seq > last - 3 ? "new" : ""}"><td>${e.seq}</td><td>${esc(e.created_at.slice(11, 19))}</td><td>${esc(e.event_type)}</td>
    <td title="${esc(e.aggregate_id)}">${esc(e.correlation_id)}</td><td>${esc(((S.st.workers || []).find((x) => x.id === e.actor_id) || {}).name || e.actor_id)}</td><td class="pd-${esc(e.policy_decision)}">${esc(e.policy_decision)}</td>
    <td>${e.protocol_hash ? esc(e.protocol_hash.slice(0, 8)) : ""}${e.test_ids && e.test_ids.length ? ` ${e.test_ids.length} tests` : ""}</td></tr>`).join("");
  const r = S.replay;
  const opts = (st.tasks || []).map((t) => `<option value="${t.id}" ${t.id === S.replayTask ? "selected" : ""}>${esc(t.id)} ${esc(t.title)}</option>`).join("");
  const labels = { actor: "Who acted", authority: "Authority", policy_decisions: "Policy decisions", context: "Context (Handoff)", intelligence: "Intelligence", tools: "Tools", result: "Result", verification: "Verification" };
  const facts = r && r.facts ? Object.entries(labels).map(([k, l]) => {
    const v = r.facts[k]; const txt = Array.isArray(v) ? v.join("; ") : v;
    return `<div class="kv"><span>${l}</span><span style="text-align:right">${txt ? esc(txt) : `<span style="color:var(--red)">missing</span>`}</span></div>`;
  }).join("") : "";
  const banner = r && r.facts ? (r.complete ? `<div class="ok-banner">Replay complete: 8 of 8 facts present, ${r.events} events, ${r.test_ids.length} test ids</div>`
    : `<div class="bad-banner">Replay incomplete: missing ${esc(r.missing.join(", "))}</div>`) : "";
  return `<p class="small muted" style="margin:0">Events are append only; the database refuses updates and deletes. A correction is a new event. Payloads carry ids and hashes and no personal data (D-22).</p>
    <div class="audit"><div class="card evt"><div class="tscroll"><table><colgroup><col style="width:52px"><col style="width:86px"><col style="width:210px"><col style="width:190px"><col style="width:160px"><col style="width:150px"><col style="width:110px"></colgroup><thead><tr><th>Seq</th><th>Time</th><th>Event</th><th title="Correlation id">Correlation</th><th>Actor</th><th>Policy</th><th>Refs</th></tr></thead><tbody>${rows}</tbody></table></div></div>
    <div class="card replay stack"><h2 style="font-size:17px">Replay a task</h2><select id="replay-task" aria-label="Task to replay">${opts}</select>
      <span class="small muted">Rebuilt from events and stored protocol objects only.</span>${facts}${banner}</div></div>`;
}

function vDelivery() {
  const st = S.st, deps = st.deployments || [], dep = deps[deps.length - 1];
  const stages = ["BUILD", "TEST", "PACKAGE", "PREVIEW", "VERIFY", "APPROVAL", "DEPLOY", "HEALTH_CHECK", "SMOKE_TEST", "LIVE"];
  const names = { HEALTH_CHECK: "Health", SMOKE_TEST: "Smoke" };
  const log = dep ? Object.fromEntries(dep.log.map((x) => [x.stage, x])) : {};
  const stepper = stages.map((s) => {
    let c = "";
    if (log[s]) c = log[s].ok ? (s === "LIVE" ? "live" : "ok") : "fail";
    else if (s === "APPROVAL" && dep && dep.status === "awaiting_approval") c = "wait";
    return `<div class="${c}">${esc(names[s] || s.charAt(0) + s.slice(1).toLowerCase())}</div>`;
  }).join("");
  const acc = (st.decisions.pending || []).find((d) => d.kind === "accept_delivery");
  const ready = ["delivered", "accepted"].includes(st.meta.phase), a = st.audit, lc = (st.live_checks || []).slice(-1)[0];
  const product = `<div class="card stack" data-step="product"><div class="between"><h2 style="font-size:20px">Your working product</h2>
      ${dep ? `<span class="pill ${dep.status === "live" ? "green" : dep.status === "awaiting_approval" ? "amber" : "red"}">${esc(dep.status.replace("_", " "))}</span>` : `<span class="pill grey">Being built</span>`}</div>
    ${st.live_url ? `<div class="row" style="flex-wrap:wrap;gap:12px"><a class="btn primary" href="${esc(st.live_url)}" target="_blank" rel="noopener" id="live-link">Open it</a>
      <a class="btn" href="/api/export" id="export">Download everything</a>
      <button class="btn" id="live-check" ${S.busy ? "disabled" : ""}>Check it is up</button>
      <span class="small mono muted">${esc(st.live_url.replace("http://", ""))}</span>${lc ? `<span class="small ${lc.ok ? "" : "err"}">${lc.ok ? "Up" : "No answer"}</span>` : ""}</div>`
      : `<p class="muted" style="margin:0">Your product appears here when the team has built it and you have approved going live.</p>`}
    <div class="stepper">${stepper}</div></div>`;
  const audit = a ? `<div class="card stack" data-step="refine"><div class="between"><h2 style="font-size:20px">Audit and refine</h2>
      <span class="pill ${a.met === a.total ? "green" : "amber"}">${a.met} of ${a.total} requirements met</span></div>
    <p class="small muted" style="margin:0">The product against your original objective: every requirement, the work that answers it, and whether that work passed its checks. ${a.tests} tests pass in the live release.</p>
    <details ${a.met === a.total ? "" : "open"}><summary class="small">Every requirement</summary>${a.requirements.map((r) => `<div class="kv"><span>${esc(r.text)}</span><span style="color:${r.met ? "var(--green)" : "var(--amber-ink)"};font-weight:600">${r.met ? "met" : "open"}</span></div>`).join("")}</details>
    <label class="lbl" for="rw_note">What needs to change?</label><textarea class="note" id="rw_note" data-keep="yes" placeholder="Say what is not right, or what the product should do differently."></textarea>
    <div class="between"><label for="rw_usd">Add to the budget for the rework, US dollars</label><input type="number" id="rw_usd" data-keep="yes" min="0" step="0.5" value="1" style="width:110px"></div>
    ${st.rework_available === false ? `<p class="small muted" style="margin:0">This demo's script covers the first release only, so it cannot build a rework. In live mode the same team plans, builds and releases what you ask for.</p>` : ""}
    <div class="row"><button class="btn" id="rework" ${S.busy || st.rework_available === false ? "disabled" : ""}>Rework it</button>
      ${acc ? `<button class="btn primary" data-decide="approve" data-id="${acc.id}" ${S.busy ? "disabled" : ""}>Accept the product</button>` : st.meta.phase === "accepted" ? `<span class="pill green">Accepted</span>` : ""}</div></div>` : "";
  const handed = ready && st.final ? `<details class="card"><summary><b>Everything handed over</b> <span class="small muted">documents, decisions, costs</span></summary>
    <div class="stack" style="margin-top:10px">${companyPack(st.final)}${finalReport()}</div></details>` : "";
  return product + audit + handed;
}

/* ---------- events ---------- */
function bind() {
  // the brief's answers are shown whole: each box grows to its text instead of cutting it off
  const fit = (t) => { t.style.height = "auto"; t.style.height = t.scrollHeight + 2 + "px"; };
  $$(".field textarea").forEach((t) => { fit(t); t.addEventListener("input", () => fit(t)); });
  $$("[data-view]").forEach((b) => b.onclick = () => { S.view = b.dataset.view; S.err = ""; if (S.view === "audit") loadReplay().then(() => paint(true)); paint(true); });
  $$(".mode input").forEach((r) => r.onchange = () => {
    if (!r.checked) return;
    S.mode = r.value;
    paint(true);  // live starts from your own answers; a demo shows its founder's words
  });
  const sc = $("#scenario");
  if (sc) sc.onchange = () => { S.scenario = sc.value; const x = scenario(); if (x) { $("#messy").value = x.messy; $("#coname").value = x.title; } paint(true); };
  const on = (id, fn) => { const el = document.getElementById(id); if (el) el.onclick = fn; };
  on("structure", () => {
    const isNew = S.st.meta.phase === "new", name = isNew ? ($("#coname") || {}).value || "" : "";
    const mode = isNew ? ((($("input[name=mode]:checked") || {}).value) || S.mode) : S.st.meta.mode;
    let messy = ($("#messy") || {}).value || "";
    if (mode === "live") {
      const ans = {}; $$("[data-answer]").forEach((t) => ans[t.dataset.answer] = t.value);
      S.answers = { ...ans, name };
      const missing = QUESTIONS.filter(([k, , , req]) => req && !(ans[k] || "").trim()).map(([, q]) => q.replace(/\?.*$/, "?"));
      if (isNew && !name.trim()) missing.unshift("A project name");
      if (missing.length) { act(async () => { throw new Error("Cynqra needs a little more before it can write your brief. Please answer: " + missing.join(" ")); }); return; }
      messy = composeIdea(ans);
    }
    act(async () => {
      if (isNew) await api("/api/company", { name, mode, scenario: S.scenario });
      await api("/api/objective/draft", { messy });
    });
  });
  on("submit", () => {
    const fields = {}; $$("[data-field]").forEach((i) => fields[i.dataset.field] = i.value);
    const constraints = {}; $$("[data-constraint]").forEach((i) => constraints[i.dataset.constraint] = i.value);
    const usdRaw = $("#usd").value.trim(), tvRaw = $("#tv").value.trim();
    if (S.st.meta.mode === "live" && !(Number(usdRaw) > 0)) { act(async () => { throw new Error("Set a budget in US dollars first: it is the most Cynqra may spend on AI for this project, and it never goes over it."); }); return; }
    const usd = usdRaw === "" ? null : Number(usdRaw), tv = tvRaw === "" ? null : Number(tvRaw);
    S.budgetGiven = true;
    act(async () => {
      await api("/api/objective/fields", { fields });
      await api("/api/objective/guardrails", { budget_usd: usd, time_value_per_hour: tv, constraints });
      await api("/api/objective/submit", {});
    });
  });
  on("define-founder", () => {
    const f = (S.st.company || {}).founder || {};
    const founder = { leads: $$("[data-founder-lead]").filter((i) => i.checked).map((i) => i.dataset.founderLead), stage: f.stage,
      hours_per_week: Number(($("#f_hours") || {}).value || 0), background: ($("#f_background") || {}).value || "" };
    act(() => api("/api/founder/define", { founder }));
  });
  $$("[data-team-option]").forEach((b) => b.onclick = () => { S.teamOption = b.dataset.teamOption; paint(true); });
  on("approve-workforce", (ev) => {
    const id = ev.currentTarget.dataset.id, roles = [];
    if (ev.currentTarget.dataset.option === "lean") { act(() => api(`/api/decisions/${id}`, { action: "approve", edited: { option: "lean" } })); return; }
    $$("[data-role]").forEach((i) => { if (Number(i.value) > 0) roles.push({ role: i.dataset.role, quantity: Number(i.value), why: "founder override", ...(i.dataset.lead ? { lead: i.dataset.lead } : {}), ...(i.dataset.field ? { field: i.dataset.field, title: i.dataset.title } : {}) }); });
    const prop = S.st.proposal || {}, same = roles.length === (prop.roles || []).length && roles.every((r) => (prop.roles.find((p) => p.role === r.role && (p.field || "") === (r.field || "")) || {}).quantity === r.quantity);
    act(() => api(`/api/decisions/${id}`, { action: "approve", edited: roles.length && !same ? { roles } : null }));
  });
  on("revise-workforce", (ev) => { const id = ev.currentTarget.dataset.id, note = ($("#wf_note") || {}).value || "Revise the workforce";
    act(() => api(`/api/decisions/${id}`, { action: "reject", note })); });
  on("approve-plan", (ev) => act(async () => {
    await api(`/api/decisions/${ev.currentTarget.dataset.id}`, { action: "approve" });
    await api("/api/run/auto", { on: true });
    S.view = "work";
  }));
  on("replan", (ev) => act(() => api(`/api/decisions/${ev.currentTarget.dataset.id}`, { action: "reject", note: "Ask for a different roadmap" })));
  on("step", () => act(() => api("/api/run/step", {})));
  on("live-check", () => act(() => api("/api/live/check", {})));
  on("rename", (ev) => { const id = ev.currentTarget.dataset.id, name = ($("#rn_name") || {}).value || "";
    act(() => api("/api/worker/rename", { worker_id: id, name })); });
  on("rework", () => { const note = ($("#rw_note") || {}).value || "", usd = Number(($("#rw_usd") || {}).value || 0);
    act(async () => { await api("/api/rework", { note, budget_usd: usd || null }); const el = $("#rw_note"); if (el) el.value = ""; }); });
  on("guide-toggle", () => { S.guide = !S.guide; paint(true); });
  on("guide-off", () => { S.guide = false; paint(true); });
  on("resume", () => act(() => api("/api/run/resume", {})));
  on("auto", () => act(() => api("/api/run/auto", { on: !S.st.auto.on })));
  on("kill", () => act(() => api("/api/killswitch", { on: !S.st.meta.frozen })));
  on("reset", () => { if (window.confirm("Archive this run and start a new one? Nothing is deleted.")) act(async () => { await api("/api/reset", {}); S.view = "company"; S.seen = -1; S.mode = "live"; S.answers = {}; S.budgetGiven = false; }); });
  on("ask", () => {
    const q = $("#gq").value, subject = $("#gs").value.trim();
    act(async () => {
      try { S.graph = await api(`/api/graph?q=${encodeURIComponent(q)}&subject=${encodeURIComponent(subject)}`); }
      catch (e) { S.graph = { error: e.message }; }
    });
  });
  $$("[data-worker]").forEach((b) => b.onclick = () => { S.worker = b.dataset.worker; paint(true); });
  $$("[data-reg-open]").forEach((b) => b.onclick = () => { S.regOpen = true; S.err = ""; paint(true); });
  $$("[data-reg-close]").forEach((b) => b.onclick = () => { S.regOpen = false; S.err = ""; paint(true); });
  on("connect", () => {
    const v = (id) => (($("#" + id) || {}).value || "").trim();
    const method = v("c_auth");
    // a key typed where the name of an environment variable belongs would be read as that name and never found
    const looksLikeKey = (x) => /^(AQ\.|AIza|nvapi-|sk-|hf_|gsk_)/.test(x) || (x.length > 30 && !/^[A-Z][A-Z0-9_]*$/.test(x));
    if (method === "env" && looksLikeKey(v("c_env"))) { const e = $("#c_env"); if (e) e.value = "";
      act(async () => { throw new Error("That looks like the key itself, not the name of an environment variable. Choose \"In Cynqra's secrets file\" under Key and paste the key into the Key (secrets file only) box."); }); return; }
    if (method === "secret" && !v("c_secret") && looksLikeKey(v("c_env"))) { const e = $("#c_env"); if (e) e.value = "";
      act(async () => { throw new Error("The key was typed into the Environment variable box. Paste it into the Key (secrets file only) box instead."); }); return; }
    const spec = { type: v("c_type"), name: v("c_name"), endpoint: v("c_endpoint"), models: v("c_models"),
      auth: method === "env" ? { method, env_var: v("c_env") } : method === "secret" ? { method, secret: v("c_secret") } : { method } };
    if (v("c_server")) spec.server = v("c_server");
    if (v("c_in") !== "" || v("c_out") !== "") spec.price_per_m = [Number(v("c_in") || 0), Number(v("c_out") || 0)];
    if (v("c_rpm") !== "") spec.rate_limits = { calls_per_minute: Number(v("c_rpm")) };
    if (v("c_effort")) spec.settings = { CYNQRA_EFFORT: v("c_effort") };
    const sec = $("#c_secret"); if (sec) sec.value = "";  // the key leaves the page with this request only
    act(() => api("/api/connections", spec));
  });
  // show only the box the chosen way of keeping the key uses
  const auth = $("#c_auth");
  if (auth) { const sync = () => { const m = auth.value, show = (id, on) => { const el = $("#" + id); if (el && el.closest("label")) el.closest("label").style.display = on ? "" : "none"; };
    show("c_env", m === "env"); show("c_secret", m === "secret"); }; auth.onchange = sync; sync(); }
  $$("[data-browse]").forEach((b) => b.onclick = async () => {
    const id = b.dataset.browse;
    if (S.browse[id]) { delete S.browse[id]; paint(true); return; }
    S.browse[id] = { loading: true, sel: new Set() }; paint(true);
    try {
      const r = await api(`/api/connections/${id}/catalog`, {});
      S.browse[id] = { models: r.models, dates: r.dates, all: !r.dates, sel: new Set(r.models.filter((x) => x.offered).map((x) => x.ref)) };
    } catch (e) { S.browse[id] = { err: e.message, sel: new Set() }; }
    paint(true);
  });
  $$("[data-mb-all]").forEach((x) => x.onclick = () => { const b = S.browse[x.dataset.mbAll]; if (b) { b.all = !b.all; paint(true); } });
  $$("[data-mb-search]").forEach((q) => q.oninput = () => {
    const t = q.value.trim().toLowerCase(), box = q.closest(".mbrowser");
    box.querySelectorAll(".mb-row").forEach((r) => r.style.display = !t || r.dataset.mbName.includes(t) ? "" : "none");
  });
  $$("[data-mb]").forEach((x) => x.onchange = () => { const b = S.browse[x.dataset.mb]; if (!b) return;
    if (x.checked) b.sel.add(x.value); else b.sel.delete(x.value);
    const n = $("#mb_n_" + x.dataset.mb); if (n) n.textContent = `${b.sel.size} chosen. Cynqra evaluates each new one, then decides who it powers.`; });
  $$("[data-mb-save]").forEach((b) => b.onclick = () => {
    const id = b.dataset.mbSave, sel = [...((S.browse[id] || {}).sel || [])];
    if (!sel.length) { act(async () => { throw new Error("Choose at least one model, or remove the connection."); }); return; }
    act(async () => { await api(`/api/connections/${id}/update`, { models: sel }); delete S.browse[id]; });
  });
  $$("[data-discover]").forEach((b) => b.onclick = () => { const id = b.dataset.discover; act(() => api(`/api/connections/${id}/discover`, {})); });
  $$("[data-disconnect]").forEach((b) => b.onclick = () => { const id = b.dataset.disconnect; if (window.confirm("Remove this connection? Its credential is deleted and the intelligence it offered is retired; their measured record is kept.")) act(() => api(`/api/connections/${id}/remove`, {})); });
  $$("[data-probe]").forEach((b) => b.onclick = () => { const id = b.dataset.probe; act(async () => { S.probes[id] = await api(`/api/intelligence/${id}/probe`, {}); }); });
  $$("[data-fault-off]").forEach((b) => b.onclick = () => { const id = b.dataset.faultOff, on = b.dataset.on === "1"; act(() => api(`/api/intelligence/${id}/fault`, { offline: on })); });
  $$("[data-fault-cap]").forEach((b) => b.onclick = () => { const id = b.dataset.faultCap, n = Number(($("#cap_" + id) || {}).value || 0); act(() => api(`/api/intelligence/${id}/fault`, { max_reply: n })); });
  $$("[data-fallback]").forEach((b) => b.onclick = () => { const id = b.dataset.fallback, fb = ($("#fb_" + id) || {}).value || ""; act(() => api(`/api/intelligence/${id}/fallback`, { fallback_id: fb })); });
  $$("[data-retire]").forEach((b) => b.onclick = () => { const id = b.dataset.retire; if (window.confirm("Retire this intelligence? Workers bound to it are moved by the Replacement Engine; its measured record is kept.")) act(() => api(`/api/intelligence/${id}/retire`, {})); });
  $$("[data-rt-start]").forEach((b) => b.onclick = () => { const model = b.dataset.rtStart; act(() => api("/api/runtime/start", { model })); });
  on("rt-cancel", () => act(() => api("/api/runtime/cancel", {})));
  on("rt-stop", () => act(() => api("/api/runtime/stop", {})));
  $$("[data-model-open]").forEach((b) => b.onclick = () => { S.modelOpen = true; S.err = ""; paint(true); });
  $$("[data-model-close]").forEach((b) => b.onclick = () => { S.modelOpen = false; S.err = ""; paint(true); });
  const gpu = $("#rt-gpu");
  if (gpu) gpu.onchange = () => { const v = gpu.value; act(() => api("/api/runtime/gpu", { gpu: v })); };
  $$("[data-app-quit]").forEach((b) => b.onclick = () => {
    if (!window.confirm("Quit Cynqra? The model and any product Cynqra deployed on this computer stop. Your runs are kept.")) return;
    api("/api/app/quit", {}).catch(() => {});
    document.body.innerHTML = `<div class="closed"><span class="wordmark">Cynqra</span><p>Cynqra has quit. You can close this window.</p></div>`;
  });
  const rt = $("#replay-task");
  if (rt) rt.onchange = () => { S.replayTask = rt.value; S.replayKey = ""; loadReplay().then(() => paint(true)); };
  $$("[data-decide]").forEach((b) => b.onclick = () => {
    const id = b.dataset.id, action = b.dataset.decide, d = (S.st.decisions.pending || []).find((x) => x.id === id) || {};
    const noteEl = document.getElementById(`note_${id}`), editEl = document.getElementById(`edit_${id}`), usdEl = document.getElementById(`usd_${id}`);
    const edited = {}, note = noteEl ? noteEl.value : "";
    if (editEl && editEl.value.trim() && editEl.value.trim() !== (d.recommendation || "").trim()) edited.recommendation = editEl.value.trim();
    if (usdEl) edited.budget_usd = Number(usdEl.value);
    act(() => api(`/api/decisions/${id}`, { action, note, edited }));
  });
}

refresh(true);
setInterval(() => refresh(false), 700);
