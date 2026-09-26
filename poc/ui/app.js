"use strict";
/* Cynqra POC web UI. Plain JavaScript, no build step. Polls /api/state and renders.
   Screens follow the mockups in poc/design/mockups (Book 0 sections 21 and 22). */

const S = {
  st: null, view: "company", worker: "w_eng_b", replayTask: null, replay: null, replayKey: "",
  seen: -1, sig: "", err: "", busy: false, graph: null, mode: "demo", shown: new Set(), guide: true, modelOpen: false,
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
  objective_change: "Objective change", approve_plan: "Organization and plan", confirm_objective: "Confirm objective",
};
const WORKER_TITLE = { w_cto: "CTO", w_pm: "PM", w_eng_a: "Engineer A", w_eng_b: "Engineer B", orchestrator: "Orchestrator", verification: "Verification", founder: "Founder" };
const VIEWS = [["company", "Company"], ["organization", "Organization"], ["work", "Work"], ["decisions", "Decisions"],
  ["evolution", "Evolution"], ["audit", "Audit"], ["delivery", "Delivery"]];
const wt = (id) => WORKER_TITLE[id] || id;

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
    const st = await api("/api/state");
    S.st = st;
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
    S.modelOpen, rtSignature()].join("|");
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
  $("#app").innerHTML = (model ? modelScreen() : ["new", "objective", "planning"].includes(phase) ? wizard() : shell()) + g;
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
    else if (e.event_type === "decision.created" && !["confirm_objective"].includes(p.kind)) { msg = `Needs you: ${KIND_TITLE[p.kind] || p.kind}`; kind = "warn"; }
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

/* ---------- wizard: objective, then organization and plan ---------- */
function wizard() {
  const st = S.st, phase = st.meta.phase, obj = st.objective;
  const top = `<div class="wiz-top"><div class="row"><span class="wordmark">Cynqra</span><span class="muted small">${esc(st.company ? st.company.name : "New company")}</span></div>
    <div class="row">${guideToggle()}${modePill()}</div></div>`;
  if (phase === "planning") return `<div class="wiz">${top}${planStep()}</div>`;
  const modeChoice = phase === "new" ? `
      <label class="lbl" for="coname">Company name</label>
      <input type="text" id="coname" value="Harbor Recruiting">
      ${isDesktop() ? "" : `<div class="modes" role="radiogroup" aria-label="Intelligence">
        <label class="mode ${S.mode === "demo" ? "on" : ""}" id="m-demo"><input type="radio" name="mode" value="demo" ${S.mode === "demo" ? "checked" : ""}>Demo: scripted workers</label>
        <label class="mode ${S.mode === "live" ? "on" : ""}" id="m-live"><input type="radio" name="mode" value="live" ${S.mode === "live" ? "checked" : ""}>Live: a real model</label>
      </div>`}` : "";
  const right = obj ? objectiveCard(obj) : `<div class="card" style="flex:1;display:flex;align-items:center;justify-content:center"><p class="muted">Your structured objective appears here.</p></div>`;
  return `<div class="wiz">${top}<div class="wiz-body">
    <div class="wiz-left">
      <div class="steps"><span class="on">1 Objective</span><span>2 Organization and plan</span><span>3 Run</span></div>
      <h1 class="hero">Tell Cynqra what you want to achieve.</h1>
      <p class="lede">One sentence is enough. Cynqra turns it into a structured objective, proposes the organization to pursue it, and brings you only the decisions that need you.</p>
      ${modeChoice}
      <label class="lbl" for="messy">Your objective</label>
      <textarea class="big" id="messy">${esc(obj ? obj.statement : st.demo_messy)}</textarea>
      <div class="row"><button class="btn primary" id="structure" ${S.busy ? "disabled" : ""}>${obj ? "Structure it again" : "Structure my objective"}</button></div>
      <div class="err" role="alert">${esc(S.err)}</div>
      <p class="small muted" style="margin:0">${isDesktop() ? `Every word the CTO, the PM and the engineers write comes from ${esc(rt().model_name || "the model")}, running on this computer. Nothing leaves it. On a laptop each step takes minutes; the Work view shows what the model is doing.`
        : "Demo mode: the words the workers write come from a prepared script, and every screen says so. Code is still written, tested and deployed for real. Live mode uses a model through the Cynqra model registry and needs an API key on this machine."}</p>
    </div>
    <div class="wiz-right">${right}</div></div></div>`;
}

function objectiveCard(obj) {
  const st = S.st;
  const fields = Object.keys(FIELD_LABELS).map((k) => {
    const inf = obj.inferred_fields.includes(k);
    return `<div class="field ${inf ? "inf" : ""}"><div class="between caps"><span>${FIELD_LABELS[k]}</span>
      <span class="tag ${inf ? "inferred" : "stated"}">${inf ? "Inferred, check it" : "Stated"}</span></div>
      <textarea rows="2" id="f_${k}" data-field="${k}" data-keep="no" aria-label="${FIELD_LABELS[k]}">${esc(obj.structured[k])}</textarea></div>`;
  }).join("");
  return `<div class="card stack" style="flex:1">
    <div class="between"><h2 style="font-size:20px">Structured objective</h2><span class="small muted">Version ${obj.version}, not yet confirmed · ${esc(obj.intelligence)}</span></div>
    ${obj.notice ? `<div class="notice">${esc(obj.notice)}</div>` : ""}
    <div class="fields">${fields}
      <div class="field" style="border-style:dashed"><div class="caps">Guardrails</div>
        <div class="between"><label for="cap">Budget cap, work units</label><input type="number" id="cap" data-keep="no" min="20" value="${esc(st.budget.cap)}" style="width:110px"></div>
        <div class="between small"><span>Autonomy</span><span>L1: low risk only (D-5)</span></div></div>
    </div>
    <div class="between" style="margin-top:auto;padding-top:14px;border-top:1px solid var(--line)">
      <span class="small muted">Confirming counts as one founder intervention.</span>
      <button class="btn dark" id="confirm" ${S.busy ? "disabled" : ""}>Confirm objective</button></div></div>`;
}

function planStep() {
  const st = S.st;
  const d = (st.decisions.pending || []).find((x) => x.kind === "approve_plan");
  const rows = (st.tasks || []).map((t) => `<tr><td class="mono">${esc(t.id)}</td><td>${esc(t.title)}</td><td>${esc(wt(t.owner_worker_id))}</td>
    <td>${riskPill(t.risk_tier)}</td><td class="mono small">${esc((t.dependencies || []).join(", ") || "none")}</td><td class="small">${esc(t.verification_method)}</td></tr>`).join("");
  const workers = (st.workers || []).map((w) => `<div class="kv"><span>${esc(w.title)}</span><span>${esc(w.intelligence_source_id)}</span></div>`).join("");
  return `<div class="wiz-body">
    <div class="wiz-left">
      <div class="steps"><span>1 Objective</span><span class="on">2 Organization and plan</span><span>3 Run</span></div>
      <h1 class="hero">Your organization and plan.</h1>
      <p class="lede">The fixed template for the MVP: a CTO, a PM and two engineers. The Verification Service checks their work and is not a worker. Nothing starts until you approve.</p>
      <div class="card stack"><div class="caps">Organization, fixed_mvp_4</div>${workers}
        <div class="kv"><span>Verification Service</span><span>platform, not a worker</span></div></div>
      <div class="err" role="alert">${esc(S.err)}</div>
    </div>
    <div class="wiz-right"><div class="card stack">
      <div class="between"><h2 style="font-size:20px">Plan: ${(st.tasks || []).length} tasks</h2><span class="small muted">${esc(d ? d.cost : "")}</span></div>
      <table class="plan-table"><thead><tr><th>Task</th><th>Title</th><th>Owner</th><th>Risk</th><th>Depends on</th><th>Verified by</th></tr></thead><tbody>${rows}</tbody></table>
      <p class="small muted" style="margin:0">MEDIUM and HIGH work comes back to you before it happens (D-17, D-21). Approving counts as one founder intervention.</p>
      <div class="row"><button class="btn primary" id="approve-plan" data-id="${esc(d ? d.id : "")}" ${S.busy || !d ? "disabled" : ""}>Approve organization and plan</button>
        <button class="btn" id="replan" data-id="${esc(d ? d.id : "")}" ${S.busy || !d ? "disabled" : ""}>Ask for a different plan</button></div>
    </div></div></div>`;
}

/* ---------- desktop app: the open model on this computer ---------- */
const isDesktop = () => !!(S.st && S.st.desktop && S.st.runtime);
const rt = () => (S.st && S.st.runtime) || {};
const gb = (b) => (b >= 1073741824 ? (b / 1073741824).toFixed(1) : (b / 1073741824).toFixed(2));
const RT_WORKING = ["downloading", "checking", "starting"];

function rtSignature() {
  if (!isDesktop()) return "";
  const r = rt();
  return [r.state, r.model, Math.floor((r.done || 0) / 52428800), Math.round((r.rate || 0) / 1048576), r.error, r.gpu,
    r.busy ? Math.floor(r.busy.tokens / 25) : -1, (r.catalog || []).map((m) => `${m.installed}:${m.partial_gb}`).join()].join(",");
}

function showModelScreen() {
  if (!isDesktop()) return false;
  if (S.modelOpen) return true;
  return rt().state !== "ready" && S.st.meta.phase === "new";
}

function modelActivity() {
  if (!isDesktop()) return "";
  const b = rt().busy;
  if (!b) return "";
  const what = b.tokens ? `Model writing: ${b.tokens.toLocaleString()} tokens` : `Model reading a ${(b.prompt || 0).toLocaleString()}-token prompt`;
  return `<span class="pill blue" title="What the model on this computer is doing right now"><i class="dot pulse"></i>${what}</span>`;
}

function modelBanner() {
  if (!isDesktop() || rt().state === "ready") return "";
  const r = rt(), working = RT_WORKING.includes(r.state);
  return `<div class="notice">${working ? `The model is ${r.state === "downloading" ? "downloading" : "starting"}; the run continues when it is ready.`
    : "The model is not running, so the organization cannot work."} <button class="btn sm primary" data-model-open="1">Open model settings</button></div>`;
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
  const back = S.st.meta.phase !== "new" || r.state === "ready";
  return `<div class="wiz"><div class="wiz-top"><div class="row"><span class="wordmark">Cynqra</span><span class="muted small">Model</span></div>
      <div class="row">${back && S.modelOpen ? `<button class="btn sm" data-model-close="1">Back</button>` : ""}<button class="btn sm" data-app-quit="1">Quit</button></div></div>
    <div class="wiz-body"><div class="wiz-left">
      <h1 class="hero">The model your organization runs on.</h1>
      <p class="lede">Cynqra's CTO, PM and engineers are an open-weight model running on this computer through llama.cpp. It is downloaded once; after that no prompt, answer or code leaves this computer.</p>
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
  if (isDesktop()) return `<span class="pill blue wrap">Model: ${esc(rt().model_name || "not running")}${rt().state === "ready" ? ", this computer" : ""}</span>`;
  if (st.meta.mode === "live") return `<span class="pill blue">Live mode: ${esc(st.intelligence || "model")}</span>`;
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
  const st = S.st, b = st.budget, pct = Math.min(100, Math.round((100 * b.spent) / Math.max(1, b.cap)));
  const pend = (st.decisions.pending || []).filter((d) => !d.in_digest).length;
  const nav = VIEWS.map(([k, label]) => `<button class="nav ${S.view === k ? "on" : ""}" data-view="${k}"${S.view === k ? ' aria-current="page"' : ""}>
    <span>${label}</span>${k === "decisions" && pend ? `<span class="badge">${pend}</span>` : ""}</button>`).join("");
  const running = st.meta.phase === "running";
  const views = { company: vCompany, organization: vOrg, work: vWork, decisions: vDecisions, evolution: vEvolution, audit: vAudit, delivery: vDelivery };
  return `<div class="shell">
    <nav class="side" aria-label="Main"><div class="brand"><span class="wordmark">Cynqra</span><span class="small muted">${esc(st.company ? st.company.name : "")}</span></div>
      ${nav}
      <div class="foot">${modePill()}
        <button class="btn danger ${st.meta.frozen ? "on" : ""}" id="kill">${st.meta.frozen ? "Release kill switch" : "Kill switch"}</button>
        <button class="btn sm" id="reset" title="Archive this run and start again">New run</button>${guideToggle()}
        ${isDesktop() ? `<div class="row" style="gap:8px"><button class="btn sm" data-model-open="1">Model</button><button class="btn sm" data-app-quit="1">Quit</button></div>` : ""}</div></nav>
    <main class="main">
      <header class="top"><h1>${VIEWS.find((v) => v[0] === S.view)[1]}</h1>
        <div class="row small" style="gap:20px">
          <div class="row" style="gap:8px"><span>Budget</span><div class="meter ${pct >= 95 ? "bad" : pct >= 80 ? "warn" : ""}" role="img" aria-label="Budget ${pct} percent used"><i style="width:${pct}%"></i></div>
            <span class="mono">${b.spent} / ${b.cap}</span></div>
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
  const obj = st.objective && st.objective.status === "confirmed";
  const org = st.organization && st.organization.status === "active";
  const cls = (done, now, work) => done ? "done" : now ? "now" : work ? "work" : "";
  const build = by("spec").concat(by("decision"), by("code"));
  return [
    ["Objective", cls(obj)], ["Organization", cls(org, !org && obj)],
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
        <span class="caps">Objective, confirmed version ${esc(o.version)}</span>
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
  return `<div class="org"><div class="card tree">
      <div class="node founder"><b>Founder</b><small>Objective, budget, HIGH risk, proposals</small></div><div class="vline"></div>
      <div class="nodes">${node("w_cto", "Reviews, merges, proposes deploys")}<div class="node svc"><b>Verification Service</b><small style="color:var(--accent-ink)">Not a worker. Tests, lint, review</small></div></div>
      <div class="vline"></div>${node("w_pm", "Specs, plans, assigns, clears Blockers")}<div class="vline"></div>
      <div class="nodes">${node("w_eng_a", "Backend and tests")}${node("w_eng_b", "Web app and tests")}</div>
      <div class="card stack" style="margin-top:28px;width:100%;background:var(--paper);border:0">
        <label class="lbl" for="gq">Ask the organization graph</label>
        <div class="row"><select id="gq"><option value="approves">Who approves</option><option value="owns">Who owns</option><option value="depends">What depends on</option></select>
          <input type="text" id="gs" value="merge_to_main" aria-label="Action type or task id" style="flex:1"><button class="btn sm" id="ask">Ask</button></div>${ans}</div></div>
    <div class="card side-panel stack"><div><span class="caps">Worker ${esc(w.id)}</span><h2 style="font-size:22px">${esc(w.title)}</h2></div>
      <div class="kv"><span>Intelligence</span><span>${esc(w.intelligence_source_id)}</span></div>
      <div class="kv"><span>Capabilities</span><span>${esc((w.capabilities || []).join(", "))}</span></div>
      <div class="kv"><span>Reports to</span><span>${esc(wt(w.reports_to))}</span></div>
      <div class="kv"><span>Current work</span><span>${esc(cur)}</span></div>
      <div class="kv"><span>Verified, first pass</span><span class="mono">${p.verified || 0}, ${p.first_pass || 0}</span></div>
      <div class="kv"><span>Reworks, Blockers raised</span><span class="mono">${p.reworks || 0}, ${p.blockers || 0}</span></div>
      <h3 style="font-size:15px;margin-top:6px">Authority (${esc(st.policy.version)})</h3>${auth}
      <p class="small muted" style="margin:6px 0 0">Identity stays when the intelligence changes: switch to a live model and the role, memory and history carry over.</p></div></div>`;
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
      `<label class="lbl" for="cap_${d.id}">New cap, work units</label><input type="number" id="cap_${d.id}" value="${esc(st.budget.cap + 60)}">` : "";
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
        <button class="btn" data-decide="request_evidence" data-id="${d.id}" ${S.busy ? "disabled" : ""}>Request more evidence</button></div></div>`;
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

function vEvolution() {
  const ev = S.st.evolution;
  if (!ev) return `<div class="card"><p class="muted">No organization yet.</p></div>`;
  const rows = ev.workers.map((w) => `<tr><td>${esc(w.title)}</td><td class="mono">${w.verified || 0}</td><td class="mono">${w.first_pass || 0}</td><td class="mono">${w.reworks || 0}</td><td class="mono">${w.blockers || 0}</td></tr>`).join("");
  return `<p class="small muted" style="margin:0">View only in the MVP (Book 1 P1). Nothing here changes the organization by itself.</p>
    <div class="two"><div class="card stack"><span class="caps">Organizational review</span><h2 class="serif" style="font-size:26px">${esc(ev.title)}</h2>
      <div><span class="caps">Recommendation</span><p style="margin:4px 0 0">${esc(ev.recommendation)}</p></div>
      <div><span class="caps">What would change this</span><p style="margin:4px 0 0">${esc(ev.change)}</p></div>
      <span class="pill grey" style="align-self:flex-start">Status: ${esc(ev.status)}</span></div>
    <div class="card"><h2 style="font-size:17px;margin-bottom:8px">Worker performance</h2><table class="plan-table"><thead><tr><th>Worker</th><th>Verified</th><th>First pass</th><th>Reworks</th><th>Blockers</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
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
  $$(".mode input").forEach((r) => r.onchange = () => { if (r.checked) S.mode = r.value; $$(".mode").forEach((m) => m.classList.toggle("on", m.contains(r) && r.checked)); });
  const on = (id, fn) => { const el = document.getElementById(id); if (el) el.onclick = fn; };
  on("structure", () => {
    const isNew = S.st.meta.phase === "new", name = isNew ? $("#coname").value : "", messy = $("#messy").value;
    const mode = isDesktop() ? "live" : ((($("input[name=mode]:checked") || {}).value) || S.mode);
    act(async () => {
      if (isNew) await api("/api/company", { name, mode });
      await api("/api/objective/draft", { messy });
    });
  });
  on("confirm", () => {
    const fields = {}; $$("[data-field]").forEach((i) => fields[i.dataset.field] = i.value);
    const cap = Number($("#cap").value);
    act(async () => {
      await api("/api/objective/fields", { fields });
      await api("/api/objective/guardrails", { budget_cap: cap });
      await api("/api/objective/confirm", {});
    });
  });
  on("approve-plan", (ev) => act(async () => {
    await api(`/api/decisions/${ev.currentTarget.dataset.id}`, { action: "approve" });
    await api("/api/run/auto", { on: true });
    S.view = "work";
  }));
  on("replan", (ev) => act(() => api(`/api/decisions/${ev.currentTarget.dataset.id}`, { action: "reject", note: "Ask for a different plan" })));
  on("step", () => act(() => api("/api/run/step", {})));
  on("guide-toggle", () => { S.guide = !S.guide; paint(true); });
  on("guide-off", () => { S.guide = false; paint(true); });
  on("resume", () => act(() => api("/api/run/resume", {})));
  on("auto", () => act(() => api("/api/run/auto", { on: !S.st.auto.on })));
  on("kill", () => act(() => api("/api/killswitch", { on: !S.st.meta.frozen })));
  on("reset", () => { if (window.confirm("Archive this run and start a new one? Nothing is deleted.")) act(async () => { await api("/api/reset", {}); S.view = "company"; S.seen = -1; S.mode = isDesktop() ? "live" : "demo"; }); });
  on("ask", () => {
    const q = $("#gq").value, subject = $("#gs").value.trim();
    act(async () => {
      try { S.graph = await api(`/api/graph?q=${encodeURIComponent(q)}&subject=${encodeURIComponent(subject)}`); }
      catch (e) { S.graph = { error: e.message }; }
    });
  });
  $$("[data-worker]").forEach((b) => b.onclick = () => { S.worker = b.dataset.worker; paint(true); });
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
    const noteEl = document.getElementById(`note_${id}`), editEl = document.getElementById(`edit_${id}`), capEl = document.getElementById(`cap_${id}`);
    const edited = {}, note = noteEl ? noteEl.value : "";
    if (editEl && editEl.value.trim() && editEl.value.trim() !== (d.recommendation || "").trim()) edited.recommendation = editEl.value.trim();
    if (capEl) edited.cap = Number(capEl.value);
    act(() => api(`/api/decisions/${id}`, { action, note, edited }));
  });
}

refresh(true);
setInterval(() => refresh(false), 700);
