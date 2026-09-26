"use strict";
/* Guided demo: the real Cynqra UI (app.js, unchanged) over a recorded run of the real engine.
   This file stands in for the server. GET /api/state returns the recorded state of the
   current step; the founder's buttons move to the next recorded step. Nothing is generated
   here: every state was captured by poc/demo/record_replay.py. It loads before app.js. */
window.CYNQRA_GUIDED_DEMO = true;
(() => {
  const R = JSON.parse(document.getElementById("replay-data").textContent);
  const IMG = JSON.parse(document.getElementById("replay-images").textContent);
  const frames = R.frames;
  const last = frames.length - 1;
  const fin = frames[last].state;
  const m = fin.metrics;

  const closing = [
    { frame: last, view: "delivery", modal: "product", chapter: "Live and handed over", title: "The product is real",
      body: `What the engineers wrote is a working candidate tracker, deployed to its own address on the recording machine. Here it is in use during the recording: two candidates added, and the one whose application is ten days old is flagged. Its ${R.product_tests.ran} tests pass when rerun on their own.` },
    { frame: last, view: "audit", chapter: "Audit", title: "Every step can be replayed",
      body: "Events are append only: the database refuses updates and deletes. Pick any task on the right and Cynqra rebuilds who acted, under what authority, which policy decisions applied, which intelligence and tools were used, and which tests verified it. Every task here replays 8 of 8 facts." },
    { frame: last, view: "organization", chapter: "Authority", title: "Authority is written down, not implied",
      body: "Each worker has a row of authority: executes, proposes, or not allowed. External messages are prohibited for every worker, which is why the CTO's email was stopped. Try the graph: ask who approves merge_to_main." },
    { frame: last, view: "company", chapter: "Result", title: "One sentence in, a live product out",
      body: `${m.founder_interventions} founder decisions. ${m.tasks_verified} of ${m.tasks_total} tasks verified, ${m.defects_caught_before_verified} defect caught before it counted, ${m.blockers_cleared_without_founder} Blocker cleared without the founder, ${m.actions_stopped_by_policy} action stopped by policy, ${fin.budget.spent} of ${fin.budget.cap} work units spent, ${m.events} events on record.` },
    { frame: last, view: "company", modal: "real", chapter: "What is real", title: "Not a mock-up, and not only a script",
      body: "In this recording the workers' words come from a prepared script, as the Demo label says. Everything else is real: the code was written to disk, tested, merged and deployed, and every record was produced by the engine. The same engine has also run with a real Claude model writing every word, on objectives it had never seen." },
  ];
  const beats = frames.map((f, i) => ({ frame: i })).concat(closing);

  let beat = 0, playing = false, timer = null;
  const $ = (s) => document.querySelector(s);
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const json = (obj, status = 200) => new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json" } });

  function stateNow() {
    const s = clone(frames[beats[beat].frame].state);
    s.policy = s.policy || fin.policy;
    return s;
  }

  /* ---- the server this page stands in for ---- */
  const realFetch = window.fetch.bind(window);
  window.fetch = async (url, opts) => {
    const path = typeof url === "string" ? url : url.url;
    if (!path.startsWith("/api/")) return realFetch(url, opts);
    const u = new URL(path, "http://replay.local");
    const post = opts && opts.method === "POST";
    const body = post && opts.body ? JSON.parse(opts.body) : {};
    if (!post) {
      if (u.pathname === "/api/state") return json(stateNow());
      const rp = u.pathname.match(/^\/api\/replay\/(t_\w+)$/);
      if (rp) return R.replays[rp[1]] ? json(R.replays[rp[1]]) : json({ error: "unknown task" }, 400);
      if (u.pathname === "/api/graph") {
        const ans = (R.graph[u.searchParams.get("q")] || {})[u.searchParams.get("subject")];
        return ans ? json(ans) : json({ error: "In this recording, ask about a task id (t_01 to t_06) or an action type such as merge_to_main." }, 400);
      }
      return json({ error: "not found" }, 404);
    }
    const next = beats[beat + 1] && frames[beats[beat + 1].frame];
    const advanceIf = (trigger) => { if (next && next.trigger === trigger && beats[beat + 1].frame !== beats[beat].frame) go(beat + 1); };
    if (u.pathname === "/api/objective/draft") advanceIf("structure");
    else if (u.pathname === "/api/objective/confirm") advanceIf("confirm");
    else if (u.pathname.startsWith("/api/decisions/")) {
      if (body.action !== "approve") return json({ error: "This recording follows the approve path. In the live app, rejecting sends the work back with your reason, and asking for evidence returns the card to the worker." }, 400);
      advanceIf("decide");
    } else if (u.pathname === "/api/run/step") go(beat + 1);
    else if (u.pathname === "/api/run/auto") { setPlaying(!!body.on); return json({ on: playing, delay: 0.9 }); }
    else if (u.pathname === "/api/killswitch") return json({ error: "The kill switch works in the live app: it freezes every worker at once. This recording does not use it." }, 400);
    else if (u.pathname === "/api/reset") go(0);
    return json({ ok: true });
  };

  /* ---- presenter ---- */
  function narration(b) {
    if (b.title) return b;
    return CynqraTour.narrate(frames[b.frame].state) || { chapter: "", title: "", body: "" };
  }

  function go(i) {
    beat = Math.max(0, Math.min(beats.length - 1, i));
    const b = beats[beat], n = narration(b);
    closeModal();
    if (typeof S !== "undefined") {
      S.err = "";
      const view = b.view || n.view;
      if (view && view !== S.view) window.scrollTo(0, 0);
      if (view) S.view = view;
      if (view === "audit") { S.replayTask = "t_03"; S.replayKey = ""; }
      if (b.view === "organization") S.graph = R.graph.approves.merge_to_main;
      refresh(true);
    }
    $("#g-chapter").textContent = n.chapter || "";
    $("#g-title").textContent = n.title || "";
    $("#g-body").textContent = n.body || "";
    $("#g-count").textContent = `${beat + 1} / ${beats.length}`;
    $("#g-bar").style.width = `${(100 * (beat + 1)) / beats.length}%`;
    $("#g-back").disabled = beat === 0;
    $("#g-next").textContent = beat === beats.length - 1 ? "Start again" : "Next";
    if (b.modal) setTimeout(() => openModal(b.modal), 350);
    if (playing) schedule();
  }

  function schedule() {
    clearTimeout(timer);
    if (!playing) return;
    if (beat >= beats.length - 1) { setPlaying(false); return; }
    const n = narration(beats[beat]);
    timer = setTimeout(() => go(beat + 1), Math.min(14000, 4200 + 38 * (n.body || "").length));
  }

  function setPlaying(on) {
    playing = on;
    $("#g-play").textContent = on ? "Pause" : "Play";
    $("#g-play").setAttribute("aria-pressed", String(on));
    if (on) schedule(); else clearTimeout(timer);
  }

  /* ---- dialogs for what a recording cannot open live ---- */
  function openModal(kind) {
    const box = $("#g-modal-body");
    if (kind === "product") {
      box.innerHTML = `<h2>The live product, as it ran</h2>
        <p>Captured from the product's own address during the recording, after two candidates were added. Priya applied ten days ago, so she is flagged under the rule the founder decided.</p>
        <img alt="The candidate tracker built by the organization, with two candidates and one flagged" src="${IMG.product_in_use}">
        <p class="g-note">It runs on the machine that ran Cynqra. In the local app (RUN_POC.bat) the Delivery link opens it for real.</p>`;
    } else if (kind === "export") {
      const e = R.export, cats = Object.entries(e.categories).map(([k, v]) => `<li><b>${k.replace(/_/g, " ")}</b> <span>${v} file${v > 1 ? "s" : ""}</span></li>`).join("");
      box.innerHTML = `<h2>The export bundle</h2><p><span class="mono">${e.name}</span>, ${(e.bytes / 1024).toFixed(0)} KB, ${Object.keys(e.files).length} files, each with its hash in the manifest. Everything the founder needs to leave with:</p>
        <ul class="g-list">${cats}</ul><p class="g-note">${(e.non_portable || []).join(" ")}</p>`;
    } else if (kind === "real") {
      box.innerHTML = `<h2>The same engine with a real model</h2>
        <p>Two runs on 26 September 2026, on objectives Cynqra had never seen, with Claude writing every worker's words. Every task verified, each product went live and was used in a browser. Token counts in those runs are estimated, so they say nothing about cost; a measured run needs an API key.</p>
        <div class="g-figs"><figure><img alt="Dog walk tracker built from a real model run, walker view with one walk done" src="${IMG.dogwalks}"><figcaption>A dog walking company: walks assigned by the owner, each walker sees only today's walks and marks them done with a note. Run through this same UI in live mode, including a rejected plan and a provider outage recovered with Try the same step again.</figcaption></figure>
        <figure><img alt="Cake order tracker built from a real model run, with an overdue order" src="${IMG.bakery}"><figcaption>A bakery: custom cake orders with pickup dates, due in the next three days (a rule the founder decided), paid and picked up.</figcaption></figure></div>`;
    }
    $("#g-modal").hidden = false;
    $("#g-modal-close").focus();
  }
  function closeModal() { const mdl = $("#g-modal"); if (mdl) mdl.hidden = true; }

  /* ---- wiring ---- */
  document.addEventListener("DOMContentLoaded", () => {
    const bar = $("#g-panel");
    const fit = () => document.documentElement.style.setProperty("--guide-h", bar.offsetHeight + "px");
    if (window.ResizeObserver) new ResizeObserver(fit).observe(bar);
    fit();
    $("#g-next").onclick = () => go(beat === beats.length - 1 ? 0 : beat + 1);
    $("#g-back").onclick = () => go(beat - 1);
    $("#g-play").onclick = () => setPlaying(!playing);
    $("#g-modal-close").onclick = closeModal;
    $("#g-modal").onclick = (ev) => { if (ev.target.id === "g-modal") closeModal(); };
    $("#g-start").onclick = () => { $("#g-welcome").hidden = true; go(0); $("#g-next").focus(); };
    $("#g-explore").onclick = () => { $("#g-welcome").hidden = true; go(last); };
    $("#g-real").onclick = () => openModal("real");
    document.addEventListener("click", (ev) => {
      const a = ev.target.closest && ev.target.closest("#live-link, #export");
      if (!a) return;
      ev.preventDefault();
      openModal(a.id === "export" ? "export" : "product");
    }, true);
    document.addEventListener("keydown", (ev) => {
      if (ev.target.closest && ev.target.closest("input, textarea, select")) return;
      if (ev.key === "Escape") { closeModal(); $("#g-welcome").hidden = true; return; }
      if (!$("#g-welcome").hidden) return;
      if (ev.key === "ArrowRight" || ev.key === "PageDown") { ev.preventDefault(); go(beat + 1); }
      else if (ev.key === "ArrowLeft" || ev.key === "PageUp") { ev.preventDefault(); go(beat - 1); }
      else if (ev.key === " " && !(ev.target.closest && ev.target.closest("button"))) { ev.preventDefault(); setPlaying(!playing); }
    });
    go(0);
  });
})();
