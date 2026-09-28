"use strict";
/* Cynqra POC web UI. Plain JavaScript, no build step. Polls /api/state and renders.
   Screens follow the mockups in archive/04_design_mockups/mockups (Book 0 sections 21 and 22). */

const S = {
  st: null, view: "company", worker: null, replayTask: null, replay: null, replayKey: "",
  seen: -1, sig: "", err: "", busy: false, graph: null, mode: "demo", shown: new Set(), guide: true, modelOpen: false,
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
const AREA_TITLE = { product: "Product", functional: "Functional", non_functional: "Non-functional", ai_ml: "AI and ML", data: "Data",
  design: "Design", security: "Security", qa: "QA", devops: "DevOps", deployment: "Deployment" };
const CONSTRAINTS = [["deadline", "Deadline"], ["geography", "Geography"], ["technology", "Technology"], ["compliance", "Compliance"], ["risk_tolerance", "Risk tolerance"]];
const SERVICE_TITLE = { orchestrator: "Orchestrator", verification: "Verification", founder: "Founder", budget_engine: "Budget Engine",
  workforce_synthesizer: "Workforce Synthesizer", execution_planner: "Execution Planner", replacement_engine: "Replacement Engine",
  objective_intelligence: "Objective Intelligence", intelligence_router: "Intelligence Router" };
const VIEWS = [["company", "Company"], ["organization", "Organization"], ["workforce", "Workforce"], ["work", "Work"],
  ["decisions", "Decisions"], ["intelligence", "Intelligence"], ["performance", "Performance"], ["audit", "Audit"], ["delivery", "Delivery"]];
const wt = (id) => { const w = ((S.st && S.st.workers) || []).find((x) => x.id === id); return w ? w.title : SERVICE_TITLE[id] || id; };

async function api(path, body) {
  const opts = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `request failed (${r.status})`);
  return data;
}

/* act() repaints before fn runs, so handlers read every input they need first, then call act(). */
async function act(fn) {
  if (S.busy) return;
  S.busy = true; S.err = ""; paint(true);
  try { await fn(); } catch (e) { S.err = e.message; }
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
  const phase = S.st.meta.phase;
  const model = showModelScreen();
  const g = model ? "" : guideBar();
  $("#app").innerHTML = (model ? modelScreen() : S.regOpen ? regScreen() : ["new", "objective", "workforce", "planning"].includes(phase) ? wizard() : shell()) + g;
  $("#app").classList.toggle("with-guide", !!g);
  const bar = $(".guide-bar");
  if (bar) document.documentElement.style.setProperty("--guide-h", bar.offsetHeight + "px");
  Object.entries(keep).forEach(([id, v]) => { const el = document.getElementById(id); if (el && el.dataset.keep !== "no") el.value = v; });
  if (focus) { const el = document.getElementById(focus); if (el) el.focus(); }
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
    else if (e.event_type === "action.denied") { msg = `Policy stopped ${p.action_type} by ${wt(e.actor_id)}`; kind = "bad"; }
    else if (e.event_type === "decision.created" && !["approve_workforce", "approve_roadmap"].includes(p.kind)) { msg = `Needs you: ${KIND_TITLE[p.kind] || p.kind}`; kind = "warn"; }
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
function steps(on) {
  return `<div class="steps">${["1 Objective", "2 Workforce", "3 Roadmap and budget", "4 Run"].map((x, i) => `<span class="${i === on ? "on" : ""}">${x}</span>`).join("")}</div>`;
}

function wizard() {
  const st = S.st, phase = st.meta.phase, obj = st.objective;
  const top = `<div class="wiz-top"><div class="row"><span class="wordmark">Cynqra</span><span class="muted small">${esc(st.company ? st.company.name : "New project")}</span></div>
    <div class="row"><button class="btn sm" data-reg-open="1">Intelligence (${regModels().filter((m) => m.available).length})</button>${guideToggle()}${modePill()}</div></div>`;
  if (phase === "workforce") return `<div class="wiz">${top}${workforceStep()}</div>`;
  if (phase === "planning") return `<div class="wiz">${top}${planStep()}</div>`;
  const scen = scenario();
  const modeChoice = phase === "new" ? `
      <label class="lbl" for="coname">Project name</label>
      <input type="text" id="coname" value="${esc(scen ? scen.title : "My project")}">
      ${`<div class="modes" role="radiogroup" aria-label="Intelligence">
        <label class="mode ${S.mode === "demo" ? "on" : ""}" id="m-demo"><input type="radio" name="mode" value="demo" ${S.mode === "demo" ? "checked" : ""}>Demo: scripted workers</label>
        <label class="mode ${S.mode === "live" ? "on" : ""}" id="m-live"><input type="radio" name="mode" value="live" ${S.mode === "live" ? "checked" : ""}>Live: real models</label>
      </div>
      ${S.mode === "demo" ? `<label class="lbl" for="scenario">Demo scenario</label>
        <select id="scenario" data-keep="no">${(st.scenarios || []).map((x) => `<option value="${esc(x.id)}" ${x.id === S.scenario ? "selected" : ""}>${esc(x.title)}</option>`).join("")}</select>
        <p class="small muted" style="margin:0">${esc(scen ? scen.about : "")}</p>` : intelSources()}`}` : "";
  const right = obj ? objectiveCard(obj) : `<div class="card" style="flex:1;display:flex;align-items:center;justify-content:center"><p class="muted">Your brief appears here.</p></div>`;
  return `<div class="wiz">${top}<div class="wiz-body">
    <div class="wiz-left">
      ${steps(0)}
      <h1 class="hero">Describe the company you want to build.</h1>
      <p class="lede">Cynqra assembles the expert team it needs, checks every piece of their work, and asks you only what a CEO should decide. You don't name the team: you approve it, then the plan and budget.</p>
      ${modeChoice}
      <label class="lbl" for="messy">Your company, in your own words</label>
      <textarea class="big" id="messy">${esc(obj ? obj.statement : scen ? scen.messy : "")}</textarea>
      <div class="row"><button class="btn primary" id="structure" ${S.busy ? "disabled" : ""}>${obj ? "Make the brief again" : "Make it a brief"}</button></div>
      <div class="err" role="alert">${esc(S.err)}</div>
      <p class="small muted" style="margin:0">${S.mode === "demo" && phase === "new" || st.meta.mode === "demo"
        ? "Demo mode: the words the workers write come from a prepared script, and every screen says so. Code is still written, tested, backtested and deployed for real. Nothing to download or connect."
        : `Live mode: every worker is bound to an intelligence from the ones available, chosen from measured evidence.${isDesktop() ? " A model on this computer takes minutes per step; the Work view shows what it is doing." : ""}`}</p>
    </div>
    <div class="wiz-right">${right}</div></div></div>`;
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
  const cons = CONSTRAINTS.map(([k, l]) => `<div class="between"><label for="c_${k}">${l}</label><input type="text" id="c_${k}" data-constraint="${k}" data-keep="no" value="${esc(given[k] || "")}" placeholder="optional" style="width:220px"></div>`).join("");
  return `<div class="card stack" style="flex:1">
    <div class="between"><h2 style="font-size:20px">Structured objective</h2><span class="small muted">Version ${obj.version} · ${esc(obj.intelligence)}</span></div>
    ${obj.notice ? `<div class="notice">${esc(obj.notice)}</div>` : ""}
    <div class="fields">${fields}
      <div class="field" style="border-style:dashed"><div class="caps">Budget</div>
        <div class="between"><label for="usd">Budget, US dollars (hard cap)</label><input type="number" id="usd" data-keep="no" min="0" step="0.5" value="${esc(s.budget_usd)}" style="width:110px"></div>
        <div class="between"><label for="tv">Value of an hour, US dollars</label><input type="number" id="tv" data-keep="no" min="0" step="1" value="${esc(s.time_value_per_hour)}" style="width:110px"></div></div>
      <div class="field" style="border-style:dashed"><div class="caps">Constraints, optional</div>${cons}</div>
    </div>
    <div class="between" style="margin-top:auto;padding-top:14px;border-top:1px solid var(--line)">
      <span class="small muted">Cynqra decomposes it into requirements and proposes the workforce. Submitting counts as one founder intervention.</span>
      <button class="btn dark" id="submit" ${S.busy ? "disabled" : ""}>Submit to Cynqra</button></div></div>`;
}

function orgChart(workers) {
  const kids = (id) => workers.filter((w) => (w.reports_to || "founder") === id);
  const node = (w) => `<li><div class="onode"><b>${esc(w.title)}</b><small>${esc(w.role)}${w.model ? " · " + esc(w.model) : ""}</small></div>${kids(w.id).length ? `<ul>${kids(w.id).map(node).join("")}</ul>` : ""}</li>`;
  return `<div class="ochart"><ul><li><div class="onode founder"><b>Founder</b><small>approval gates</small></div><ul>${kids("founder").map(node).join("")}</ul></li></ul></div>`;
}

function reqList(req) {
  if (!req) return "";
  const byArea = {};
  req.requirements.forEach((r) => (byArea[r.area] = byArea[r.area] || []).push(r));
  return Object.entries(byArea).map(([a, rs]) => `<div class="stack" style="gap:2px"><span class="caps">${esc(AREA_TITLE[a] || a)}</span>
    ${rs.map((r) => `<div class="small"><span class="mono">${esc(r.id)}</span> ${esc(r.text)} <span class="muted">Verified by: ${esc(r.verification || "n/a")}</span></div>`).join("")}</div>`).join("");
}

function workforceStep() {
  const st = S.st, prop = st.proposal || {}, req = st.requirements, d = (st.decisions.pending || []).find((x) => x.kind === "approve_workforce");
  const cost = prop.cost_by_role || {};
  const roles = (prop.roles || []).map((r) => {
    const cat = (st.catalog || []).find((c) => c.role === r.role) || {};
    const name = r.title || cat.title || r.role, key = r.title || r.role, fid = r.field ? "spec_" + r.field.replace(/[^a-z0-9]+/gi, "_") : r.role;
    return `<tr><td><b>${esc(name)}</b>${r.added_by === "platform" ? ` <span class="pill teal">added by Cynqra</span>` : ""}</td><td class="mono">${esc(r.quantity)}</td><td class="small">${esc(r.why)}</td>
      <td class="mono small">${esc((r.requirement_ids || []).join(", "))}</td><td class="mono small">${cost[key] === undefined ? "n/a" : usd(cost[key])}</td>
      ${allowOverride() ? `<td><input type="number" min="0" max="${esc(r.field ? 1 : cat.max || 1)}" id="q_${esc(fid)}" data-role="${esc(r.role)}" data-field="${esc(r.field || "")}" data-title="${esc(r.title || "")}" data-keep="no" value="${esc(r.quantity)}" style="width:60px" aria-label="Quantity"></td>` : ""}</tr>`;
  }).join("");
  const ws = req ? req.workstreams.map((w) => `<span class="pill grey">${esc(w.id)} ${esc(w.name)}</span>`).join(" ") : "";
  return `<div class="wiz-body">
    <div class="wiz-left">
      ${steps(1)}
      <h1 class="hero">The team your company needs.</h1>
      <p class="lede">Cynqra broke your idea into ${req ? req.requirements.length : 0} requirements and chose the team that covers every one. You approve the team; you don't have to build it.</p>
      <div class="card stack"><div class="caps">Requirements</div>${reqList(req)}
        <div class="small">Workstreams: ${ws}</div><div class="small">Critical path: <span class="mono">${esc(((req || {}).critical_path || []).join(" > "))}</span></div></div>
      <div class="err" role="alert">${esc(S.err)}</div>
    </div>
    <div class="wiz-right"><div class="card stack">
      <div class="between"><h2 style="font-size:20px">Proposed organization: ${(prop.workers || []).length} workers</h2><span class="small muted">proposal ${esc(prop.id || "")} · ${esc(prop.intelligence || "")}</span></div>
      <p class="small" style="margin:0">${esc(prop.summary || "")}</p>
      <div class="tscroll"><table class="tbl"><thead><tr><th>Role</th><th>Qty</th><th>Why required</th><th>Covers</th><th>Expected cost</th>${allowOverride() ? "<th>Edit</th>" : ""}</tr></thead><tbody>${roles}</tbody></table></div>
      ${orgChart(prop.workers || [])}
      <p class="small muted" style="margin:0">Reporting lines are generated from the roles present. The Verification Service checks everyone's work and is not a worker. ${allowOverride() ? "Your governance policy allows editing the proposal: an edit is checked like any proposal and recorded as an override." : "Your governance policy does not allow editing it: reject with your feedback and Cynqra revises it."}</p>
      <label class="lbl" for="wf_note">Feedback, if you reject</label><textarea class="note" id="wf_note" data-keep="yes"></textarea>
      <div class="row"><button class="btn primary" id="approve-workforce" data-id="${esc(d ? d.id : "")}" ${S.busy || !d ? "disabled" : ""}>Approve the workforce</button>
        <button class="btn" id="revise-workforce" data-id="${esc(d ? d.id : "")}" ${S.busy || !d ? "disabled" : ""}>Reject and revise</button></div>
    </div></div></div>`;
}
const allowOverride = () => !!(wfv().settings || {}).allow_workforce_override;

function budgetTable(f) {
  if (!f) return "";
  const rows = Object.entries(f.layers).map(([k, v]) => `<tr><td>${esc(k.charAt(0).toUpperCase() + k.slice(1))}</td><td class="mono">${usd(v.usd)}</td><td class="small">${esc(v.basis)}</td></tr>`).join("");
  const byw = Object.entries(f.by_worker || {}).map(([w, v]) => `<span class="pill grey">${esc(wt(w))} ${usd(v.usd)}</span>`).join(" ");
  return `<div class="tscroll"><table class="tbl"><thead><tr><th>Layer</th><th>USD</th><th>Basis</th></tr></thead><tbody>${rows}
    <tr><td><b>Project total</b></td><td class="mono"><b>${usd(f.total_usd)}</b></td><td class="small">against the hard cap of ${usd(f.cap_usd)}${f.spent_before_usd ? `, ${usd(f.spent_before_usd)} of it already spent on planning` : ""}</td></tr></tbody></table></div>
    <div class="small">By worker: ${byw}</div>${(f.warnings || []).map((w) => `<div class="notice small">${esc(w)}</div>`).join("")}`;
}

function planStep() {
  const st = S.st, plan = st.plan || {};
  const d = (st.decisions.pending || []).find((x) => x.kind === "approve_roadmap");
  const tasks = st.tasks || [];
  const ms = (plan.milestones || []).map((m) => `<tr class="ms"><td colspan="6"><b>${esc(m.name)}</b> <span class="muted small">day ${esc(m.due_day)}</span></td></tr>
    ${tasks.filter((t) => t.milestone_id === m.id).map((t) => `<tr><td class="mono">${esc(t.id)}</td><td>${esc(t.title)}<div class="small muted">${esc((t.acceptance_criteria || []).join("; "))}</div></td>
      <td>${esc(wt(t.owner_worker_id))}<div class="small muted">accountable: ${esc(wt(t.accountable))}</div></td><td>${riskPill(t.risk_tier)}</td>
      <td class="mono small">${esc((t.dependencies || []).join(", ") || "none")}</td><td class="small">${esc(t.verification_gate)}${t.documents ? `<div class="muted">${esc(t.documents.join(", "))}</div>` : ""}</td></tr>`).join("")}`).join("");
  const staffed = (wfv().workers || []).map((w) => { const c = (w.candidates || []).find((x) => x.model_id === w.model_id) || {};
    return `<div class="kv"><span>${esc(w.title)}</span><span>${esc(w.model)} · ${pctx(c.p_task)} · ${usd(c.expected_usd)}</span></div>`; }).join("");
  return `<div class="wiz-body">
    <div class="wiz-left">
      ${steps(2)}
      <h1 class="hero">The plan and the budget.</h1>
      <p class="lede">Who does what, in what order, how each piece of work is checked, which AI each team member uses, and what it all costs. Nothing starts until you approve.</p>
      <div class="card stack"><div class="caps">Intelligence for each worker</div>${staffed}
        <span class="small muted">Chosen by the Intelligence Router from the registry's measured evidence: the chance of passing verification, expected cost and time.${regModels().length === 1 ? " The registry holds one model, so every worker runs on it." : ""}</span></div>
      <div class="card stack"><div class="caps">Budget</div>${budgetTable(st.forecast)}</div>
      <div class="err" role="alert">${esc(S.err)}</div>
    </div>
    <div class="wiz-right"><div class="card stack">
      <div class="between"><h2 style="font-size:20px">Roadmap: ${(plan.milestones || []).length} milestones, ${tasks.length} tasks</h2><span class="small muted">${esc(d ? d.cost : "")}</span></div>
      <table class="plan-table"><thead><tr><th>Task</th><th>Title and acceptance</th><th>Owner</th><th>Risk</th><th>Depends on</th><th>Verification gate</th></tr></thead><tbody>${ms}</tbody></table>
      <div class="small">Critical path: <span class="mono">${esc((plan.critical_path || []).join(" > "))}</span></div>
      <details><summary class="small">Escalation conditions</summary><ul class="small">${(plan.escalation_conditions || []).map((c) => `<li>${esc(c)}</li>`).join("")}</ul></details>
      <p class="small muted" style="margin:0">MEDIUM and HIGH work still comes back to you before it happens. Approving counts as one founder intervention.</p>
      <div class="row"><button class="btn primary" id="approve-plan" data-id="${esc(d ? d.id : "")}" ${S.busy || !d ? "disabled" : ""}>Approve roadmap and budget</button>
        <button class="btn" id="replan" data-id="${esc(d ? d.id : "")}" ${S.busy || !d ? "disabled" : ""}>Ask for a different roadmap</button></div>
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
    : "No intelligence is available, so the organization cannot work."} ${isDesktop() ? `<button class="btn sm" data-model-open="1">Models on this computer</button>` : ""}<button class="btn sm primary" data-reg-open="1">Connect a provider</button></div>`;
}

/* Where a live run's intelligence comes from, on the first screen. */
function intelSources() {
  const avail = regModels().filter((m) => m.available), conns = supConns().filter((c) => c.origin !== "demo");
  return `<div class="card stack" style="padding:14px 16px"><div class="between"><b>Intelligence available</b><span class="pill ${avail.length ? "teal" : "warn"}">${avail.length} model${avail.length === 1 ? "" : "s"}</span></div>
    <span class="small muted">${avail.length ? `From ${esc(conns.filter((c) => avail.some((m) => m.connection_id === c.id)).map((c) => c.name).join(", "))}. Cynqra picks which one powers each worker from measured evidence.`
      : "None yet. Download an open model to this computer, or connect a provider such as Hugging Face, OpenAI or Anthropic."}</span>
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
      : `<button class="btn ${m.recommended ? "primary" : ""}" data-rt-start="${esc(m.id)}" ${working || S.busy ? "disabled" : ""}>${label}</button>`;
    return `<div class="mcard ${m.recommended ? "rec" : ""} ${running ? "on" : ""}">
      <div class="between"><b>${esc(m.name)}</b><span class="row" style="gap:6px">${m.recommended ? `<span class="pill teal">Recommended for this computer</span>` : ""}
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
      <div class="err" role="alert">${esc(S.err)}</div>
    </div><div class="wiz-right"><div class="stack">${cards}</div>
      <p class="small muted">Models come from their publishers on Hugging Face (Unsloth quantizations of Alibaba's Qwen models, Apache 2.0). Which model suits which computer comes from Cynqra's September 2026 research.</p></div></div></div>`;
}

/* ---------- shell ---------- */
function modePill() {
  const st = S.st;
  if (st.meta.mode === "live" || (st.meta.phase === "new" && S.mode === "live")) {
    const n = regModels().filter((m) => m.available).length;
    return `<span class="pill blue">Live mode: ${n} intelligence source${n === 1 ? "" : "s"} available</span>`;
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
  const nav = VIEWS.map(([k, label]) => `<button class="nav ${S.view === k ? "on" : ""}" data-view="${k}"${S.view === k ? ' aria-current="page"' : ""}>
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
      <header class="top"><h1>${VIEWS.find((v) => v[0] === S.view)[1]}</h1>
        <div class="row small" style="gap:20px">
          <div class="row" style="gap:8px"><span>Budget</span><div class="meter ${pct >= 95 ? "bad" : pct >= 80 ? "warn" : ""}" role="img" aria-label="Budget ${pct} percent used"><i style="width:${pct}%"></i></div>
            <span class="mono">${usd(spent)} / ${usd(cap)}</span></div>
          <span>Founder interventions <b class="mono">${st.metrics.founder_interventions ?? 0}</b></span>
          ${modelActivity()}${statusPill()}
          <button class="btn sm" id="step" ${!running || st.auto.on || S.busy ? "disabled" : ""}>Step</button>
          <button class="btn sm ${st.auto.on ? "" : "primary"}" id="auto" ${!running ? "disabled" : ""}>${st.auto.on ? "Pause" : "Run"}</button>
        </div></header>
      <div class="view">${modelBanner()}${S.err ? `<div class="err" role="alert">${esc(S.err)}</div>` : ""}${st.meta.notice ? `<div class="notice">${esc(st.meta.notice)}${st.meta.phase === "stopped_error" ? ` <button class="btn sm primary" id="resume" ${S.busy ? "disabled" : ""}>Try the same step again</button>` : ""}</div>` : ""}${views[S.view]()}</div>
    </main></div>`;
}

function stage() {
  const st = S.st, ts = st.tasks || [], by = (k) => ts.filter((t) => t.kind === k), m = st.meta;
  const ver = (arr) => arr.length && arr.every((t) => t.status === "VERIFIED");
  const waiting = (arr) => arr.some((t) => t.status === "AWAITING_FOUNDER");
  const obj = st.objective && st.objective.status === "submitted";
  const wf = !!st.organization;
  const org = st.organization && st.organization.status === "active";
  const cls = (done, now, work) => done ? "done" : now ? "now" : work ? "work" : "";
  const build = by("document").concat(by("decision"), by("code"), by("forecast"));
  return [
    ["Objective", cls(obj)], ["Workforce", cls(wf, !wf && obj)], ["Roadmap and budget", cls(org, !org && wf)],
    ["Build", cls(ver(build), waiting(build), org)], ["Verify", cls(ver(by("review_merge")), waiting(by("review_merge")), ver(build))],
    ["Deploy", cls(ver(by("deploy")), waiting(by("deploy")), ver(by("review_merge")))],
    ["Export", cls(["delivered", "accepted"].includes(m.phase) && m.phase === "accepted", m.phase === "delivered")],
  ];
}

function vCompany() {
  const st = S.st, o = st.objective, m = st.metrics, ts = st.tasks || [];
  const ribbonLabel = (name, c) => c === "now" ? `${name}, waiting on you` : name;
  const ribbon = stage().map(([n, c]) => `<div class="${c}">${ribbonLabel(n, c)}</div>`).join("");
  const pend = (st.decisions.pending || []).filter((d) => !d.in_digest);
  const needs = pend.length ? pend.slice(0, 3).map((d) => `<div class="needs"><div class="stack" style="gap:2px"><b>${esc(KIND_TITLE[d.kind] || d.kind)}${d.task_id ? ` · ${esc(d.task_id)}` : ""}</b>
      <span class="small muted">${esc(d.risk)} risk. ${esc(d.problem)}</span></div><button class="btn dark sm" data-view="decisions">Review</button></div>`).join("")
    : `<p class="muted" style="margin:0">Nothing needs you right now.</p>`;
  const rows = ts.map((t) => `<div class="list-row"><span>${esc(t.id)} ${esc(t.title)}</span><span class="st ${t.status}">${esc(statusText(t))}</span></div>`).join("");
  const tile = (v, l) => `<div class="tile"><b>${esc(v ?? "0")}</b><span>${l}</span></div>`;
  return `<div class="card stack">
      <div class="between" style="align-items:flex-start"><div class="stack" style="gap:6px">
        <span class="caps">Objective, version ${esc(o.version)}, submitted by the founder</span>
        <span class="serif" style="font-size:28px;font-weight:600;line-height:1.2">${esc(o.structured.product)} for ${esc(o.structured.target_customer.toLowerCase())}</span>
        <span style="color:var(--ink2)">Success: ${esc(o.structured.success_criteria)}. ${esc(o.structured.constraints)}.</span></div>
        <span class="pill teal">Stage: ${esc(st.company.stage)}</span></div>
      <div class="ribbon">${ribbon}</div></div>
    <div class="tiles">${tile(m.founder_interventions, "Founder interventions")}${tile(`${m.tasks_verified} of ${m.tasks_total}`, "Tasks verified")}
      ${tile(m.defects_caught_before_verified, "Defects caught before verified")}${tile(m.blockers_cleared_without_founder, "Blockers cleared without you")}
      ${tile(m.actions_stopped_by_policy, "Actions stopped by policy")}${tile(m.protocol_objects_per_verified_task ?? "n/a", "Protocol objects per verified task")}</div>
    <div class="two"><div class="card stack"><h2 style="font-size:17px">Needs you today</h2>${needs}
        <span class="small muted" style="margin-top:auto">At most three decisions a day should reach you at any organization size (D-11). Escalations today: ${m.escalations_today} of ${m.escalation_budget} (D-29).</span></div>
      <div class="card"><h2 style="font-size:17px;margin-bottom:6px">Work</h2>${rows}</div></div>`;
}

function statusText(t) {
  return {
    PLANNED: "Planned", ASSIGNED: "In progress", IN_PROGRESS: "In progress", BLOCKED: "Blocked", REVIEW: "Done by worker, verifying",
    REWORK: "Rework", AWAITING_FOUNDER: "Waiting on you", APPROVED: "Approved, executing",
    VERIFIED: t.attempts ? "Verified after rework" : "Verified", FAILED: "Escalated",
    WAITING: t.waiting ? `Waiting: ${t.waiting.why}` : "Waiting",
  }[t.status] || t.status;
}

function vOrg() {
  const st = S.st, ws = Object.fromEntries((st.workers || []).map((w) => [w.id, w]));
  const busyTask = (id) => (st.tasks || []).find((t) => t.owner_worker_id === id && !["PLANNED", "VERIFIED"].includes(t.status));
  const node = (id, note) => {
    const b = busyTask(id);
    return `<button class="node ${S.worker === id ? "sel" : ""}" data-worker="${id}"><b>${esc(ws[id] ? ws[id].title : id)}</b><small>${esc(note)}</small>
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
    return `<div class="kv"><span class="mono">${a}</span><span class="auth-${cls}">${txt}</span></div>`;
  }).join("");
  const ans = S.graph ? `<div class="small" id="graph-answer">${graphAnswer(S.graph)}</div>` : "";
  const kids = (id) => (st.workers || []).filter((x) => (x.reports_to || "founder") === id);
  const branch = (id) => kids(id).length ? `<div class="vline"></div><div class="nodes">${kids(id).map((x) => `<div class="branch">${node(x.id, x.role)}${branch(x.id)}</div>`).join("")}</div>` : "";
  return `<div class="org"><div class="card tree">
      <div class="node founder"><b>Founder</b><small>Outcome, budget, the two approval gates, MEDIUM and HIGH risk</small></div>${branch("founder")}
      <div class="nodes" style="margin-top:18px"><div class="node svc"><b>Verification Service</b><small style="color:var(--accent-ink)">Not a worker. Tests, lint, review</small></div></div>
      <div class="card stack" style="margin-top:28px;width:100%;background:var(--paper);border:0">
        <label class="lbl" for="gq">Ask the organization graph</label>
        <div class="row"><select id="gq"><option value="approves">Who approves</option><option value="owns">Who owns</option><option value="depends">What depends on</option></select>
          <input type="text" id="gs" value="merge_to_main" aria-label="Action type or task id" style="flex:1"><button class="btn sm" id="ask">Ask</button></div>${ans}</div></div>
    <div class="card side-panel stack"><div><span class="caps">Worker ${esc(w.id)}</span><h2 style="font-size:22px">${esc(w.title)}</h2></div>
      <div class="kv"><span>Intelligence bound by the Intelligence Router</span><span>${esc(w.model || "not yet")}${w.binding && w.binding.version ? " · version " + esc(w.binding.version) : ""}</span></div>
      <div class="kv"><span>Capabilities</span><span>${esc((w.capabilities || []).join(", "))}</span></div>
      <div class="kv"><span>Reports to</span><span>${esc(wt(w.reports_to))}</span></div>
      <div class="kv"><span>Current work</span><span>${esc(cur)}</span></div>
      <div class="kv"><span>Verified, first pass</span><span class="mono">${p.verified || 0}, ${p.first_pass || 0}</span></div>
      <div class="kv"><span>Reworks, Blockers raised</span><span class="mono">${p.reworks || 0}, ${p.blockers || 0}</span></div>
      <h3 style="font-size:15px;margin-top:6px">Authority (${esc(st.policy.version)})</h3>${auth}
      <p class="small muted" style="margin:6px 0 0">Worker is not model: the identity, role, authority and history stay when the intelligence under it changes.</p></div></div>`;
}
/* ---------------------------------------------------------------- the AI workforce and the model registry -- */
const wfv = () => (S.st && S.st.workforce) || {};
const regModels = () => (S.sup && S.sup.intelligence) || wfv().registry || [];
const supConns = () => (S.sup && S.sup.connections) || [];
const connName = (id) => (supConns().find((c) => c.id === id) || {}).name || "a removed connection";
const usd = (v) => (v === null || v === undefined ? "n/a" : `$${Number(v).toFixed(Number(v) < 1 ? 4 : 2)}`);
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
      <div class="between"><div><span class="caps">${esc(w.role)} · ${esc(w.id)}</span><h2 style="font-size:19px">${esc(w.title)}</h2></div>
        <span class="pill teal">${esc(w.model)}</span></div>
      <div class="kv"><span>Budget allocated, spent</span><span class="mono">${usd(w.budget.allocated)}, ${usd(w.budget.spent)}</span></div>
      <div class="kv"><span>Verified, first pass, reworks</span><span class="mono">${w.performance.verified || 0}, ${w.performance.first_pass || 0}, ${w.performance.reworks || 0}</span></div>
      <div class="small muted">${esc(w.why)}</div>
      ${w.binding && (w.binding.history || []).length ? `<div class="small muted">Before: ${esc(w.binding.history.map((h) => `${h.intelligence} (${h.reason})`).join("; "))}. The worker is the same; only its intelligence changed.</div>` : ""}
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
    <h2 style="font-size:18px;margin:10px 0 4px">What Cynqra told you</h2><p class="small muted" style="margin:0 0 6px">A worker's AI is replaced only when it cannot do the role's work, never for a provider's outage or an account problem; you are told each time, with the cost.</p>${notes}
    <h2 style="font-size:18px;margin:10px 0 4px">Replacements</h2>${reps}
    <div class="card"><h2 style="font-size:17px;margin-bottom:6px">Budget ledger</h2>${ledger || '<p class="muted small">Nothing allocated yet.</p>'}</div>`;
}

function scorecards() {
  const cards = S.st.performance || [];
  if (!cards.length) return "";
  const n = (v) => (v === null || v === undefined ? "n/a" : v);
  const rows = cards.map((c) => c.by_model.map((m) => `<tr><td>${esc(c.title)}</td><td>${esc(modelName(m.model_id) || "")}${m.model_id === c.model_id ? " (now)" : ""}</td>
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
  const docs = (p.documents || []).map((d) => `<div class="kv"><span>${esc(d.title)}<br><span class="small muted">${esc(d.author)}${d.types.length ? " · " + esc(d.types.join(", ")) : ""}</span></span><span style="color:${d.verified ? "var(--green)" : "var(--muted)"};font-weight:600">${d.verified ? "verified" : "not verified"}</span></div>`).join("") || `<p class="small muted">No documents in this project.</p>`;
  const dec = (p.ceo_decisions || []).map((d) => `<div class="small">${esc(d.kind.replace(/_/g, " "))}: ${esc(d.problem)}${d.outcome ? ` <b>${esc(d.outcome)}</b>` : ""}</div>`).join("") || `<p class="small muted">None.</p>`;
  return `<div class="card stack"><div class="between"><h2 style="font-size:17px">Company Pack</h2><span class="pill teal">${p.ceo_interventions} CEO decision${p.ceo_interventions === 1 ? "" : "s"}</span></div>
    <p class="small muted" style="margin:0">What your founding team hands you: every document, who wrote it and whether it passed its check; the decisions you made; and how many questions the team settled among itself (${p.settled_by_the_team}).</p>
    ${docs}<h3 style="font-size:14px;margin:6px 0 0">Your decisions</h3>${dec}
    ${(p.ceo_informed || []).length ? `<h3 style="font-size:14px;margin:6px 0 0">What Cynqra changed and told you</h3>${p.ceo_informed.map((n) => `<div class="small">${esc(n.headline)}</div>`).join("")}` : ""}</div>`;
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
    <div class="between"><div><span class="caps">${esc(PTYPE[c.type] || c.type)}${c.server ? " · " + esc(c.server) : ""}</span><h2 style="font-size:18px">${esc(c.name)}</h2></div>
      <span class="pill ${c.status === "connected" ? "teal" : "warn"}">${esc(c.status)}</span></div>
    ${c.endpoint ? `<div class="kv"><span>Endpoint</span><span class="mono small">${esc(c.endpoint)}</span></div>` : ""}
    <div class="kv"><span>Credential</span><span>${cr.method === "none" ? "none needed" : `${esc(auth)}: ${cr.present ? "present" : esc(cr.status || "missing")}`}</span></div>
    <div class="kv"><span>Offers</span><span>${offered.length ? esc(offered.map((m) => m.name).join(", ")) : "nothing yet"}</span></div>
    ${c.rate_limits && c.rate_limits.calls_per_minute ? `<div class="kv"><span>Rate limit</span><span>${esc(c.rate_limits.calls_per_minute)} calls per minute</span></div>` : ""}
    <div class="kv"><span>Added</span><span>${esc(c.permission)}</span></div>
    ${c.status_note ? `<p class="small muted" style="margin:0">${esc(c.status_note)}</p>` : ""}
    <div class="row wrap" style="gap:8px"><button class="btn sm" data-discover="${esc(c.id)}">Discover again</button>
      ${c.origin === "demo" ? "" : `<button class="btn sm" data-disconnect="${esc(c.id)}">Remove</button>`}</div></div>`;
}

function intelCard(m) {
  const pr = S.probes[m.id] || {}, o = m.performance.overall, f = m.fault || {};
  const others = regModels().filter((x) => x.id !== m.id && x.status !== "retired");
  return `<div class="card stack mcard">
    <div class="between"><div><span class="caps">${esc(connName(m.connection_id))}</span><h2 style="font-size:19px">${esc(m.name)}</h2></div>
      <span class="pill ${m.available ? "teal" : "warn"}">${m.available ? "Available" : esc(m.availability)}</span></div>
    <div class="kv"><span>Serves</span><span class="mono small">${esc(m.ref)}${m.version ? " · version " + esc(m.version) : ""}</span></div>
    <div class="kv"><span>Provider, licence</span><span>${esc(m.provider || "n/a")}, ${esc(m.license || "n/a")}</span></div>
    <div class="kv"><span>Context, hardware</span><span>${esc(m.context || "n/a")} tokens, ${esc(m.hardware || "n/a")}</span></div>
    <div class="kv"><span>Price</span><span class="mono">${m.local ? `$${m.compute_usd_per_hour}/h of this computer` : `$${m.price_in} in, $${m.price_out} out per M tokens`}</span></div>
    <div class="kv"><span>Regression check</span><span>${esc((m.regression || {}).status || "n/a")}</span></div>
    <div class="kv"><span>Calls, errors, speed</span><span class="mono">${o.calls}, ${o.call_errors}, ${o.write_tps ? o.write_tps + " tokens/s" : "n/a"}</span></div>
    <h3 style="font-size:14px;margin-top:4px">Measured on Cynqra's work</h3>${perfRows(m.performance)}
    ${Object.keys(f).length ? `<div class="notice small">Fault set: ${f.offline ? "offline" : ""}${f.offline && f.max_reply ? ", " : ""}${f.max_reply ? `replies capped at ${f.max_reply} tokens` : ""}</div>` : ""}
    <div class="row wrap" style="gap:8px">
      <button class="btn sm" data-probe="${esc(m.id)}" ${pr.state === "running" ? "disabled" : ""}>${pr.state === "running" ? "Probing..." : "Probe it"}</button>
      <button class="btn sm" data-fault-off="${esc(m.id)}" data-on="${f.offline ? "0" : "1"}">${f.offline ? "Bring back online" : "Take offline"}</button>
      <input type="number" id="cap_${esc(m.id)}" min="0" step="10" placeholder="reply cap" value="${esc(f.max_reply || "")}" style="width:100px" aria-label="Reply cap in tokens">
      <button class="btn sm" data-fault-cap="${esc(m.id)}">Set reply cap</button>
      <select id="fb_${esc(m.id)}" aria-label="Fallback"><option value="">No fallback</option>${others.map((x) => `<option value="${esc(x.id)}" ${x.id === m.fallback_id ? "selected" : ""}>Fallback: ${esc(x.name)}</option>`).join("")}</select>
      <button class="btn sm" data-fallback="${esc(m.id)}">Set fallback</button>
      <button class="btn sm" data-retire="${esc(m.id)}">Retire</button></div>
    ${pr.log && pr.log.length ? `<pre class="log">${esc(pr.log.join("\n"))}${pr.error ? "\n" + esc(pr.error) : ""}</pre>` : ""}</div>`;
}

function vIntelligence() {
  const types = (S.sup && S.sup.provider_types) || [];
  const models = regModels().filter((m) => m.status !== "retired");
  const opts = types.map((t) => `<option value="${esc(t.type)}" ${t.implemented ? "" : "disabled"}>${esc(t.title)}${t.implemented ? "" : " (planned)"}</option>`).join("");
  return `<div class="card stack"><h2 style="font-size:18px">Connect a provider</h2>
      <p class="small muted" style="margin:0">Connect a source of intelligence once. Cynqra discovers the models it offers, measures them on its own work, and the Intelligence Router picks which one powers each worker. A worker never holds a key: the connection keeps a reference to its credential, and only the Intelligence Gateway reads it, for one call at a time. Name an environment variable, or keep the key in Cynqra's secrets file on this computer.</p>
      <div class="row wrap" style="gap:8px">
        <select id="c_type" aria-label="Provider type">${opts}</select>
        <input type="text" id="c_name" placeholder="Name" style="width:160px" aria-label="Connection name">
        <input type="text" id="c_endpoint" placeholder="Endpoint URL (blank: the provider's own)" style="flex:1;min-width:240px" aria-label="Endpoint">
        <select id="c_server" aria-label="Local server"><option value="">Local server: n/a</option><option value="ollama">Ollama</option><option value="endpoint">A server at the endpoint</option><option value="llama">This computer</option></select></div>
      <div class="row wrap" style="gap:8px">
        <select id="c_auth" aria-label="Authentication"><option value="env">Key in an environment variable</option><option value="secret">Key kept in Cynqra's secrets file</option><option value="none">No key</option></select>
        <input type="text" id="c_env" placeholder="variable name, e.g. OPENAI_API_KEY" style="width:230px" aria-label="Environment variable">
        <input type="password" id="c_secret" placeholder="key (secrets file only)" style="width:190px" aria-label="Key" autocomplete="off">
        <input type="text" id="c_models" placeholder="models to offer (blank: all it lists)" style="flex:1;min-width:200px" aria-label="Models">
        <input type="number" id="c_in" step="0.01" placeholder="$ in / M" style="width:95px" aria-label="Price in">
        <input type="number" id="c_out" step="0.01" placeholder="$ out / M" style="width:95px" aria-label="Price out">
        <input type="number" id="c_rpm" placeholder="calls / min" style="width:95px" aria-label="Rate limit">
        <button class="btn primary sm" id="connect">Connect</button></div></div>
    <h2 style="font-size:18px;margin:6px 0 0">Provider connections</h2>
    <div class="grid2">${supConns().map(connCard).join("") || '<p class="muted">No provider connected yet.</p>'}</div>
    <h2 style="font-size:18px;margin:6px 0 0">Intelligence Registry</h2>
    <p class="small muted" style="margin:0">What each connection offers, with the facts its provider gives and what Cynqra has measured. Nothing here is a hand-made score.</p>
    <div class="grid2">${models.map(intelCard).join("") || '<p class="muted">No intelligence registered yet.</p>'}</div>`;
}

function regScreen() {
  return `<div class="wiz"><div class="wiz-top"><div class="row"><span class="wordmark">Cynqra</span><span class="muted small">Intelligence</span></div>
    <div class="row"><button class="btn sm primary" data-reg-close="1">Done</button></div></div>
    <div class="view">${S.err ? `<div class="err" role="alert">${esc(S.err)}</div>` : ""}${vIntelligence()}</div></div>`;
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
    ["Review", ["REVIEW", "AWAITING_FOUNDER", "APPROVED", "FAILED"]], ["Verified", ["VERIFIED"]]];
  const note = (t) => {
    if (t.status === "BLOCKED") return `<span class="small" style="color:var(--amber-ink)">Blocked: ${esc((t.blocker || {}).description)}</span>`;
    if (t.status === "REWORK") return `<span class="small" style="color:var(--red)">Rework: ${esc((t.feedback || "").split("\n")[0])}</span>`;
    if (t.status === "AWAITING_FOUNDER") return `<span class="small" style="color:var(--amber-ink)">Needs you: ${esc(t.risk_tier)} risk</span>`;
    if (t.status === "PLANNED") return `<span class="small muted">${t.dependencies.length ? "Depends on " + esc(t.dependencies.join(", ")) : "Ready"}</span>`;
    if (t.status === "REVIEW") return `<span class="small" style="color:var(--blue)">Completed by the worker. Not yet verified.</span>`;
    if (t.status === "VERIFIED") return `<span class="small" style="color:var(--green)">${esc(statusText(t))}</span>`;
    if (t.status === "ASSIGNED") return `<span class="small" style="color:var(--accent-ink)">Handoff received${(t.answers || []).length ? ", Blocker answered" : ""}</span>`;
    return `<span class="small muted">${esc(statusText(t))}</span>`;
  };
  const colHtml = cols.map(([name, sts]) => `<div class="col"><span class="caps" style="font-weight:600">${name}</span>
    ${ts.filter((t) => sts.includes(t.status)).map((t) => `<div class="tcard ${active === t.id ? "active" : ""} ${fresh("t:" + t.id + ":" + t.status)}"><span class="meta">${esc(t.id)} · ${esc(t.owner_worker_id)} · ${esc(t.risk_tier)}</span>
      <span class="ttl">${esc(t.title)}</span>${note(t)}</div>`).join("")}</div>`).join("");
  const tape = (st.protocols || []).slice().reverse().map((p) => `<div class="pobj ${esc(p.kind)} ${fresh("p:" + p.id)}"><span class="h">${esc(p.kind)} · ${esc(p.sender)} to ${esc(p.to)} · ${esc(p.task_id)}</span>
    <span class="small">${esc(p.summary)}</span>${p.artifacts && p.artifacts.length ? `<span class="small muted mono">${esc(p.artifacts.join(", "))}</span>` : ""}</div>`).join("");
  return `<p class="small muted" style="margin:0">Completed means a worker says it is done. Verified means the Verification Service agrees.</p>
    <div class="work"><div class="cols">${colHtml}</div>
    <div class="tape card"><h2 style="font-size:17px">Protocol tape</h2><span class="small muted">Every message between workers is a structured object. No free chat.</span>${tape || `<span class="muted small">No messages yet.</span>`}</div></div>`;
}

function vDecisions() {
  const st = S.st, pend = st.decisions.pending || [], main = pend.filter((d) => !d.in_digest), dig = pend.filter((d) => d.in_digest);
  const card = (d, big) => {
    const extra = d.kind === "decision" ? `<label class="lbl" for="edit_${d.id}">Edit the rule before approving (optional)</label>
        <textarea class="note" id="edit_${d.id}">${esc(d.recommendation)}</textarea>` : d.kind === "budget_breaker" ?
      `<label class="lbl" for="usd_${d.id}">New budget, US dollars</label><input type="number" id="usd_${d.id}" step="0.5" value="${esc((Math.max(st.budget.settings.budget_usd, st.budget.ledger.spent_total) * 1.5).toFixed(2))}">` : "";
    const side = d.extra && d.extra.side_action ? `<div class="deny"><span class="h">${esc(d.extra.side_action.status.toUpperCase())} · external_message</span><span class="small">${esc(d.extra.side_action.summary)} ${esc(d.extra.side_action.reason)}</span></div>` : "";
    return `<div class="dcard ${fresh("d:" + d.id)}"><div class="between"><span class="mono small muted">${esc(d.id)} · from ${esc(wt(d.source))}</span>${riskPill(d.risk)}</div>
      <h2>${esc(KIND_TITLE[d.kind] || d.kind)}${d.task_id ? `: ${esc(d.task_id)}` : ""}</h2>
      <div class="dgrid"><div><span class="caps">Problem</span><p>${esc(d.problem)}</p></div><div><span class="caps">Recommendation</span><p>${esc(d.recommendation)}</p></div>
        <div><span class="caps">Evidence</span><p>${esc((d.evidence_refs || []).join("; ") || "none")}</p></div><div><span class="caps">What would change this</span><p>${esc(d.what_would_change_this)}</p></div></div>
      <div class="dline"><span><b>Cost</b>${esc(d.cost)}</span><span><b>Risk</b>${esc(d.risk)}</span><span><b>Confidence</b>${esc(d.confidence)}</span>${["escalation", "budget_breaker"].includes(d.kind) ? `<span><b>Severity</b>${esc(d.severity)}</span>` : ""}</div>
      ${side}${extra}
      <label class="lbl" for="note_${d.id}">Reason, if you reject or ask for more</label><textarea class="note" id="note_${d.id}" data-keep="yes"></textarea>
      <div class="row"><button class="btn primary" data-decide="approve" data-id="${d.id}" ${S.busy ? "disabled" : ""}>Approve</button>
        <button class="btn" data-decide="reject" data-id="${d.id}" ${S.busy ? "disabled" : ""}>Reject</button>
        ${EVIDENCE_KINDS.includes(d.kind) ? `<button class="btn" data-decide="request_evidence" data-id="${d.id}" ${S.busy ? "disabled" : ""}>Request more evidence</button>` : ""}</div></div>`;
  };
  const answered = (st.decisions.answered || []).map((d) => `<div class="kv"><span>${esc(KIND_TITLE[d.kind] || d.kind)}${d.task_id ? " · " + esc(d.task_id) : ""}</span>
    <span style="color:${d.status === "approved" ? "var(--green)" : "var(--red)"}">${esc(d.outcome_label)}</span></div>`).join("") || `<span class="muted small">Nothing yet.</span>`;
  const denied = (st.denied || []).map((a) => `<div class="deny"><span class="h">DENY · ${esc(a.action_type)} · ${esc(a.worker_id)} · ${esc(a.task_id)}</span><span class="small">${esc(a.policy_reason)}</span></div>`).join("") || `<span class="muted small">Nothing stopped yet.</span>`;
  return `<p class="small muted" style="margin:0">Every answer is kept as a label (D-10). Escalations today: ${st.metrics.escalations_today} of ${st.metrics.escalation_budget} (D-29).</p>
    <div class="dec"><div class="dec-main">${main.map((d, i) => card(d, i === 0)).join("") || `<div class="card"><p class="muted" style="margin:0">Nothing waits on you. The organization is working.</p></div>`}
      ${dig.length ? `<div class="card"><h3 style="font-size:15px">Daily digest, over the escalation budget</h3>${dig.map((d) => card(d, false)).join("")}</div>` : ""}</div>
      <div class="dec-side"><div class="card stack"><h3 style="font-size:15px">Answered</h3>${answered}</div>
        <div class="card stack"><h3 style="font-size:15px">Stopped by policy, nothing for you to do</h3>${denied}</div></div></div>`;
}

function vPerformance() {
  const st = S.st;
  if (!(st.performance || []).length) return `<div class="card"><p class="muted">No organization yet.</p></div>`;
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
    <td title="${esc(e.aggregate_id)}">${esc(e.correlation_id)}</td><td>${esc(e.actor_id)}</td><td class="pd-${esc(e.policy_decision)}">${esc(e.policy_decision)}</td>
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
  return `<p class="small muted" style="margin:0">Events are append only; the database refuses updates and deletes. A correction is a new event. Payloads carry ids and hashes, never personal data (D-22).</p>
    <div class="audit"><div class="card evt"><table><colgroup><col style="width:46px"><col style="width:86px"><col style="width:204px"><col><col style="width:110px"><col style="width:150px"><col style="width:96px"></colgroup><thead><tr><th>Seq</th><th>Time</th><th>Event</th><th title="Correlation id">Correlation</th><th>Actor</th><th>Policy</th><th>Refs</th></tr></thead><tbody>${rows}</tbody></table></div>
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
    const label = names[s] || s.charAt(0) + s.slice(1).toLowerCase();
    return `<div class="${c}">${esc(label)}</div>`;
  }).join("");
  const health = log.HEALTH_CHECK ? log.HEALTH_CHECK.note : "not yet";
  const smoke = log.SMOKE_TEST ? (log.SMOKE_TEST.results || []).map((r) => `${r.check} ${r.ok ? "passed" : "failed"}`).join(", ") : "not yet";
  const acc = (st.decisions.pending || []).find((d) => d.kind === "accept_delivery");
  const tr = st.transition;
  const cats = [["Full repository", "repository"], ["Documents and specs", "documents_and_designs"], ["Decision history with labels", "decision_history"],
    ["Event log", "event_log"], ["Organization configuration", "organization_configuration"], ["Infrastructure configuration", "infrastructure_configuration"]];
  const ready = ["delivered", "accepted"].includes(st.meta.phase);
  return `<div class="card stack"><div class="between"><h2 style="font-size:17px">Deployment lifecycle${dep ? ", " + esc(dep.id.replace("_", " ")) : ""}</h2>
      ${dep ? `<span class="pill ${dep.status === "live" ? "green" : dep.status === "awaiting_approval" ? "amber" : "red"}">${esc(dep.status.replace("_", " "))}</span>` : `<span class="pill grey">Not started</span>`}</div>
    <div class="stepper">${stepper}</div>
    <div class="row small" style="gap:28px;flex-wrap:wrap"><span><span class="muted">URL</span> ${st.live_url ? `<a href="${esc(st.live_url)}" target="_blank" rel="noopener" class="mono" id="live-link">${esc(st.live_url.replace("http://", ""))}</a>` : "not live yet"}</span>
      <span><span class="muted">Health</span> ${esc(health)}</span><span><span class="muted">Smoke</span> ${esc(smoke)}</span>
      <span><span class="muted">Approved by</span> ${esc(dep && dep.approved_by ? dep.approved_by : "not yet (D-21)")}</span></div></div>
    ${S.st.final ? companyPack(S.st.final) : ""}
    ${finalReport()}
    <div class="two"><div class="card stack"><h2 style="font-size:17px">Export bundle</h2>
      ${cats.map(([l]) => `<div class="kv"><span>${l}</span><span style="color:${ready ? "var(--green)" : "var(--muted)"};font-weight:600">${ready ? "included" : "after delivery"}</span></div>`).join("")}
      <a class="btn" href="/api/export" style="display:inline-flex;align-items:center;justify-content:center;text-decoration:none;color:var(--ink);margin-top:auto" id="export">Download export bundle</a></div>
    <div class="card stack"><h2 style="font-size:17px">Transition record</h2>
      ${tr ? `<div class="kv"><span>Problem</span><span style="text-align:right">${esc(tr.problem)}</span></div>
        <div class="kv"><span>Change</span><span style="text-align:right">${esc(tr.proposed_change)}</span></div>
        <div class="kv"><span>Result</span><span style="text-align:right">${esc(tr.actual_result)}</span></div>
        <div class="kv"><span>Cost and interventions</span><span class="mono">${esc(tr.cost)} · ${esc(st.metrics.founder_interventions)} interventions</span></div>
        <div class="kv"><span>Approval</span><span>${tr.approval ? "accepted by the founder" : "waiting on you"}</span></div>` : `<p class="muted">Written when every task is verified and the product is live.</p>`}
      ${acc ? `<button class="btn dark" data-decide="approve" data-id="${acc.id}" style="margin-top:auto">Accept delivery</button>` : ""}</div></div>`;
}

/* ---------- events ---------- */
function bind() {
  $$("[data-view]").forEach((b) => b.onclick = () => { S.view = b.dataset.view; S.err = ""; if (S.view === "audit") loadReplay().then(() => paint(true)); paint(true); });
  $$(".mode input").forEach((r) => r.onchange = () => { if (r.checked) S.mode = r.value; paint(true); });
  const sc = $("#scenario");
  if (sc) sc.onchange = () => { S.scenario = sc.value; const x = scenario(); if (x) { $("#messy").value = x.messy; $("#coname").value = x.title; } paint(true); };
  const on = (id, fn) => { const el = document.getElementById(id); if (el) el.onclick = fn; };
  on("structure", () => {
    const isNew = S.st.meta.phase === "new", name = isNew ? $("#coname").value : "", messy = $("#messy").value;
    const mode = (($("input[name=mode]:checked") || {}).value) || S.mode;
    act(async () => {
      if (isNew) await api("/api/company", { name, mode, scenario: S.scenario });
      await api("/api/objective/draft", { messy });
    });
  });
  on("submit", () => {
    const fields = {}; $$("[data-field]").forEach((i) => fields[i.dataset.field] = i.value);
    const constraints = {}; $$("[data-constraint]").forEach((i) => constraints[i.dataset.constraint] = i.value);
    const usd = Number($("#usd").value), tv = Number($("#tv").value);
    act(async () => {
      await api("/api/objective/fields", { fields });
      await api("/api/objective/guardrails", { budget_usd: usd, time_value_per_hour: tv, constraints });
      await api("/api/objective/submit", {});
    });
  });
  on("approve-workforce", (ev) => {
    const id = ev.currentTarget.dataset.id, roles = [];
    $$("[data-role]").forEach((i) => { if (Number(i.value) > 0) roles.push({ role: i.dataset.role, quantity: Number(i.value), why: "founder override", ...(i.dataset.field ? { field: i.dataset.field, title: i.dataset.title } : {}) }); });
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
  on("guide-toggle", () => { S.guide = !S.guide; paint(true); });
  on("guide-off", () => { S.guide = false; paint(true); });
  on("resume", () => act(() => api("/api/run/resume", {})));
  on("auto", () => act(() => api("/api/run/auto", { on: !S.st.auto.on })));
  on("kill", () => act(() => api("/api/killswitch", { on: !S.st.meta.frozen })));
  on("reset", () => { if (window.confirm("Archive this run and start a new one? Nothing is deleted.")) act(async () => { await api("/api/reset", {}); S.view = "company"; S.seen = -1; S.mode = "demo"; }); });
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
    const spec = { type: v("c_type"), name: v("c_name"), endpoint: v("c_endpoint"), models: v("c_models"),
      auth: method === "env" ? { method, env_var: v("c_env") } : method === "secret" ? { method, secret: v("c_secret") } : { method } };
    if (v("c_server")) spec.server = v("c_server");
    if (v("c_in") !== "" || v("c_out") !== "") spec.price_per_m = [Number(v("c_in") || 0), Number(v("c_out") || 0)];
    if (v("c_rpm") !== "") spec.rate_limits = { calls_per_minute: Number(v("c_rpm")) };
    const sec = $("#c_secret"); if (sec) sec.value = "";  // the key leaves the page with this request only
    act(() => api("/api/connections", spec));
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
