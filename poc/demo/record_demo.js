// Records the animated product demo from the real running POC.
// Usage: node record_demo.js <base_url> <out_dir>
// Writes JPEG frames with timestamps to <out_dir>/frames and <out_dir>/frames.json.
// make_video.py starts a fresh server, runs this, and encodes the MP4.
const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

function loadPlaywright() {
  try { return require("playwright"); } catch (e) { /* fall through */ }
  return require(path.join(execSync("npm root -g").toString().trim(), "playwright"));
}

const base = process.argv[2];
const out = process.argv[3];
const W = 1600, H = 900, DSF = 1.2; // 1920 x 1080 frames
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const { chromium } = loadPlaywright();
  const opts = {};
  for (const p of ["/opt/pw-browsers/chromium-1194/chrome-linux/chrome"]) if (fs.existsSync(p)) opts.executablePath = p;
  const browser = await chromium.launch(opts);
  const context = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: DSF, locale: "en-IN", timezoneId: "Asia/Kolkata" });
  await context.addInitScript({ path: path.join(__dirname, "overlay.js") });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));

  const framesDir = path.join(out, "frames");
  fs.rmSync(framesDir, { recursive: true, force: true });
  fs.mkdirSync(framesDir, { recursive: true });
  const frames = [];
  const cdp = await context.newCDPSession(page);
  cdp.on("Page.screencastFrame", async (f) => {
    const file = path.join(framesDir, `f${String(frames.length).padStart(6, "0")}.jpg`);
    fs.writeFileSync(file, Buffer.from(f.data, "base64"));
    frames.push({ file: path.basename(file), t: f.metadata.timestamp, wall: Date.now() / 1000 });
    try { await cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }); } catch (e) { /* page closing */ }
  });

  // ---------- helpers ----------
  const api = async (p, body) => {
    const r = await fetch(base + p, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return r.json();
  };
  const state = () => api("/api/state");
  const waitFor = async (pred, what, timeout = 120000) => {
    const t0 = Date.now();
    while (Date.now() - t0 < timeout) {
      const st = await state();
      if (pred(st)) return st;
      await sleep(200);
    }
    throw new Error("timed out waiting for " + what);
  };
  const hasEvent = (st, fn) => (st.events || []).some(fn);
  const D = (fn, ...args) => page.evaluate(([f, a]) => window.__demo[f](...a), [fn, args]);
  const box = async (sel) => {
    const loc = typeof sel === "string" ? page.locator(sel).first() : sel;
    await loc.waitFor({ state: "visible", timeout: 30000 });
    return loc.boundingBox();
  };
  const moveTo = async (sel, ms = 850) => {
    const b = await box(sel);
    await D("cursor", b.x + b.width / 2, b.y + b.height / 2, ms);
    await sleep(ms + 60);
  };
  const click = async (sel) => {
    await moveTo(sel);
    await D("ripple");
    const loc = typeof sel === "string" ? page.locator(sel).first() : sel;
    await loc.click();
    await sleep(300);
  };
  const say = async (text, label, hold = 3800) => { await D("caption", text, label || ""); await sleep(hold); };
  const spot = async (sels, tone) => {
    const rects = [];
    for (const s of [].concat(sels)) {
      const b = await box(s);
      rects.push({ x: b.x, y: b.y, w: b.width, h: b.height });
    }
    await D("spots", rects, tone || "");
  };
  const clear = () => D("clearSpots");
  const chapter = async (num, title, sub) => {
    await D("caption", "");
    await D("card", `<div class="dc-wrap"><span class="dc-num in">${num}</span><span class="dc-chap in" style="animation-delay:.12s">${title}</span>
      <span class="dc-bar"></span><span class="dc-line in" style="animation-delay:.35s;font-size:28px;color:#3E4140">${sub}</span></div>`);
    await sleep(2900);
    await D("hideCard");
    await sleep(650);
  };
  const nav = async (view) => { await D("caption", ""); await click(`button.nav[data-view="${view}"]`); };

  // ---------- title ----------
  await page.goto(base + "/");
  await page.waitForSelector("#structure");
  await page.evaluate(() => document.fonts.ready);
  await D("card", `<div class="dc-wrap"><span class="dc-word in">Cynqra</span><span class="dc-bar"></span>
    <span class="dc-line in" style="animation-delay:.5s">Type one objective.</span>
    <span class="dc-line in" style="animation-delay:1.1s">Approve a handful of decisions.</span>
    <span class="dc-line in" style="animation-delay:1.7s">Walk away with a <i>live product</i>.</span>
    <span class="dc-foot in" style="animation-delay:2.6s">Proof of concept, recorded from the real running software. Demo mode: the workers' words are scripted. The code, the tests and the deploy are real.</span></div>`);
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });
  await sleep(7200);
  await D("hideCard");
  await sleep(500);

  // ---------- 01 objective ----------
  const messy = (await state()).scenarios.find((x) => x.id === "candidate_tracker").messy;
  await page.fill("#messy", "");
  await chapter("01", "Objective", "One sentence in. Seven fields out.");
  await click("#messy");
  await D("caption", "The founder writes one messy sentence.", "Founder");
  await page.locator("#messy").pressSequentially(messy, { delay: 24 });
  await sleep(900);
  await click("#structure");
  await page.waitForSelector("#submit");
  await sleep(600);
  await spot([".field.inf >> nth=0", ".field.inf >> nth=1"], "amber");
  await say("Cynqra structures it into seven fields and marks the two it guessed, so nothing is silently assumed.", "Objective", 5200);
  await clear();
  await spot(".field.inf >> nth=1", "amber");
  await moveTo(".field.inf >> nth=1");
  await say("Every field stays editable before anything starts.", "", 3000);
  await clear();
  await moveTo("#usd");
  await spot("#usd");
  await say("The budget, in US dollars, is a hard cap. Constraints are optional. The founder names the outcome, not the team.", "Budget", 4600);
  await clear();
  await click("#submit");
  await D("caption", "Submitting the objective is founder decision 1.", "Decision 1");
  await page.waitForSelector("#approve-workforce");
  await sleep(2400);

  // ---------- 02 workforce, roadmap and budget ----------
  await chapter("02", "Workforce, roadmap and budget", "Cynqra builds the organization the objective needs. You approve it.");
  await spot(".wiz-left .card");
  await say("The objective became requirements by area, grouped into workstreams with a critical path.", "Requirements", 4600);
  await spot(".wiz-right .card");
  await say("From its role catalog Cynqra proposes a CTO, a PM and two engineers, each with the reason and the requirements it covers. Verification is a platform service, not a worker.", "Workforce", 6200);
  await clear();
  await click("#approve-workforce");
  await D("caption", "Approving the workforce is founder decision 2.", "Decision 2");
  await page.waitForSelector("#approve-plan");
  await sleep(1400);
  await spot(".wiz-left .card >> nth=0");
  await say("The Intelligence Router gives every worker a model from measured evidence. Here the registry holds only the demo script.", "Intelligence", 5000);
  await spot(".plan-table");
  await say("Milestones and tasks with owners, acceptance criteria and verification gates. The platform sets every risk tier, not the model.", "Roadmap", 5200);
  await spot(".wiz-left .card >> nth=1");
  await say("The budget in dollars, in layers: inference, tools, infrastructure, verification and the reserve.", "Budget", 4600);
  await clear();
  await click("#approve-plan");
  await waitFor((st) => st.auto.on, "the UI to start the run");
  await api("/api/run/auto", { on: false });
  await D("caption", "Approving the roadmap and budget is founder decision 3.", "Decision 3");
  await page.waitForSelector("header.top");
  await sleep(2200);

  // ---------- 03 work and decisions ----------
  await chapter("03", "The organization works", "Workers build, verification checks, you only see what needs you.");
  await api("/api/run/auto", { on: true, delay: 1.8 });
  await nav("work");
  await page.waitForSelector(".tape");
  await sleep(700);
  await spot(".tape");
  await say("Workers act only through the Tool Gateway, inside their own workspace. Every message between them is a stamped protocol object.", "Protocol", 5600);
  await clear();
  await waitFor((st) => (st.tasks || []).find((t) => t.id === "t_01" && t.status === "VERIFIED"), "t_01 verified");
  await say("The PM's documents are checked against their types' rules and the objective before anyone builds on them.", "Verification", 3800);
  await waitFor((st) => (st.decisions.pending || []).some((d) => d.kind === "decision"), "product rule decision");
  await sleep(900);
  await spot("header.top .pill.amber");
  await say("A product rule changes what the product means. That is MEDIUM risk, so it goes to the founder.", "D-17", 4200);
  await clear();
  await nav("decisions");
  await page.waitForSelector(".dcard");
  await sleep(500);
  await spot([".dcard .dgrid", ".dcard .dline"]);
  await say("Every card carries the problem, evidence, recommendation, cost, risk, confidence and what would change the answer.", "Inbox", 6000);
  await spot(".dcard textarea.note >> nth=0");
  await say("The founder can edit the rule before approving. Every answer is kept with its label.", "Inbox", 4000);
  await clear();
  await click('.dcard button[data-decide="approve"]');
  await D("caption", "Founder decision 4. The engineers start building.", "Decision 4");
  await sleep(1500);
  await nav("work");
  await waitFor((st) => hasEvent(st, (e) => e.event_type === "verification.completed" && e.payload.verdict === "REQUIRES_REWORK"), "rework");
  await sleep(300);
  await say("Engineer A's first attempt fails a test. Verification sends it back before anything counts as done.", "Verification", 4600);
  await waitFor((st) => (st.tasks || []).find((t) => t.id === "t_03" && t.status === "VERIFIED"), "t_03 verified");
  await say("The second attempt passes. Completed and verified are separate states.", "Verification", 3600);
  await waitFor((st) => hasEvent(st, (e) => e.event_type === "task.blocked"), "blocker");
  await say("Engineer B is missing an input and raises a Blocker instead of guessing.", "Blocker", 3800);
  await waitFor((st) => (st.tasks || []).find((t) => t.id === "t_04" && (t.answers || []).length), "blocker answered");
  await say("The PM answers it from the spec and the decided rule. The founder never hears about it.", "Blocker", 4400);
  await waitFor((st) => (st.decisions.pending || []).some((d) => d.kind === "review_merge"), "merge decision");
  await sleep(700);
  await nav("decisions");
  await page.waitForSelector(".dcard");
  await spot(".dcard .dgrid > div >> nth=2");
  await say("Merging to main is MEDIUM. The CTO proposes with evidence: the full suite passes on the release candidate.", "Decision 5", 5400);
  await clear();
  await click('.dcard button[data-decide="approve"]');
  await D("caption", "Founder decision 5. Main runs the full suite again after the merge.", "Decision 5");
  await waitFor((st) => (st.decisions.pending || []).some((d) => d.kind === "deploy"), "deploy decision");
  await sleep(900);
  await page.waitForSelector(".dcard .deny");
  await spot(".dcard .pill.red", "red");
  await say("A production deploy is HIGH risk. It always waits for the founder.", "D-21", 4200);
  await spot([".dcard .deny", ".dec-side .card >> nth=1"], "red");
  await say("The CTO also tried to email the recruiters. Policy denied it outright. Nothing for the founder to do.", "Policy", 5600);
  await clear();
  await click('.dcard button[data-decide="approve"]');
  await D("caption", "Founder decision 6. Deploying.", "Decision 6");
  await sleep(800);

  // ---------- 04 live ----------
  const live = await waitFor((st) => st.live_url && (st.decisions.pending || []).some((d) => d.kind === "accept_delivery"), "delivery");
  await chapter("04", "Live and handed over", "Deployed, checked, exported, replayable.");
  await nav("delivery");
  await page.waitForSelector(".stepper .live");
  await spot(".stepper");
  await say("Build, test, package, preview, verify, approval, deploy, health, smoke, live. All ten stages ran for real on this machine.", "Deploy", 5800);
  await clear();
  await moveTo("#live-link");
  await D("ripple");
  await D("openWindow", live.live_url);
  await say("This is the product the organization built: a candidate tracker, with 16 passing tests behind it.", "Live product", 3800);
  const fr = page.frameLocator("#demo-frame");
  const day = (n) => new Date(Date.now() - n * 86400000).toISOString().slice(0, 10);
  const add = async (name, daysAgo) => {
    await click(fr.locator("#name"));
    await fr.locator("#name").pressSequentially(name, { delay: 45 });
    await fr.locator("#applied").fill(day(daysAgo));
    await sleep(300);
    await click(fr.locator("button[type=submit]"));
    await sleep(600);
  };
  await D("caption", "A recruiter adds two candidates.", "Live product");
  await add("Priya Shah", 12);
  await add("Jordan Lee", 2);
  await spot(fr.locator("#rows tr >> nth=0"), "amber");
  await say("Priya has not moved for twelve days, so she is flagged. That is the rule the founder approved.", "Live product", 4600);
  await clear();
  const reason = fr.locator('select[aria-label="Stuck reason for Priya Shah"]');
  await moveTo(reason);
  await D("ripple");
  await reason.selectOption("waiting_on_candidate");
  await sleep(700);
  await say("Flagged plus a named reason means stuck.", "Live product", 3000);
  await click(fr.locator('button[data-filter="stuck"]'));
  await sleep(500);
  await spot(fr.locator("table"));
  await say("The founder sees who is stuck without asking anyone.", "Live product", 3800);
  await clear();
  await D("closeWindow");
  await D("caption", "");
  await sleep(900);
  await spot(".two .card >> nth=1");
  await say("The transition record states the problem, the change, the result, the cost and the founder interventions.", "Delivery", 4600);
  await clear();
  await click('.view button[data-decide="approve"]');
  await D("caption", "Accepting delivery is founder decision 7.", "Decision 7");
  await waitFor((st) => st.meta.phase === "accepted", "accepted");
  await sleep(1400);
  await spot(".two .card >> nth=0");
  await say("One download holds the repository, documents, decisions, event log and configuration. The founder can walk away with everything.", "Export", 5200);
  await clear();
  await nav("audit");
  await page.waitForSelector(".replay .ok-banner");
  await sleep(400);
  await spot(".replay");
  await say("Any task replays from the append only event log: who acted, on what authority, with which tools, and how it was verified.", "Audit", 5600);
  await clear();
  await nav("company");
  await sleep(500);
  await spot(".tiles");
  await say("Seven founder decisions for the whole build. Everything else the organization handled, and the record shows it.", "Company", 5200);
  await clear();
  await D("caption", "");

  // ---------- end card ----------
  const st = await state();
  const m = st.metrics;
  const dep = (st.deployments || []).slice(-1)[0] || {};
  const tiles = [
    [m.founder_interventions, "founder decisions, start to live"],
    [m.tasks_verified, `of ${m.tasks_total} tasks verified`],
    [(dep.test_ids || []).length, "product tests passing in the release"],
    [(st.workers || []).length, "workers synthesized from the objective"],
    [m.defects_caught_before_verified, "defect caught before verified"],
    [m.blockers_cleared_without_founder, "Blocker cleared without the founder"],
    [m.actions_stopped_by_policy, "prohibited action stopped by policy"],
    [10, "deployment stages, health and smoke checked"],
  ].map(([v, l], i) => `<div class="dc-tile in" style="animation-delay:${0.4 + i * 0.12}s"><b data-to="${v}">0</b><span>${l}</span></div>`).join("");
  await D("card", `<div class="dc-wrap" style="width:1240px"><span class="dc-word in" style="font-size:72px">Cynqra</span>
    <span class="dc-line in" style="animation-delay:.2s">From one sentence to a <i>live, tested, exportable product</i>.</span>
    <div class="dc-tiles">${tiles}</div>
    <span class="dc-foot in" style="animation-delay:1.6s">Proof of concept. Not gate evidence: S1, S2 and S3 v2 still decide Milestone 2. Run it yourself with RUN_POC.bat. Live mode needs an API key.</span></div>`, true);
  await sleep(400);
  await D("countUp");
  await sleep(8200);

  const stopWall = Date.now() / 1000;
  await cdp.send("Page.stopScreencast");
  await sleep(300);
  const last = frames[frames.length - 1];
  const end = last ? last.t + Math.max(0.1, stopWall - last.wall) : 0;
  fs.writeFileSync(path.join(out, "frames.json"), JSON.stringify({ frames, end, errors }, null, 1));
  console.log(JSON.stringify({ ok: errors.length === 0, frames: frames.length, seconds: frames.length ? Math.round(end - frames[0].t) : 0, errors }));
  await browser.close();
})().catch((e) => { console.log(JSON.stringify({ ok: false, errors: [String(e && e.stack || e)] })); process.exit(1); });
