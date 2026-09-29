// Records the product demo video from the real running POC: the Bluedip demo, from the founder's idea to a live
// product and the next cycle, told as the founder sees it.
// Usage: node record_demo.js <base_url> <out_dir>
// Writes JPEG frames with timestamps to <out_dir>/frames and <out_dir>/frames.json, and a log of every caption and
// highlight to <out_dir>/beats.json so each one can be checked frame by frame.
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
const CAPTION_TOP = H - 150;        // the caption band: a highlight ends above it, a click target too
const WORK_DELAY = 0.6;             // seconds between the team's steps while the video watches them
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const { chromium } = loadPlaywright();
  const opts = {};
  for (const p of ["/opt/pw-browsers/chromium-1194/chrome-linux/chrome"]) if (fs.existsSync(p)) opts.executablePath = p;
  const browser = await chromium.launch(opts);
  const context = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: DSF, locale: "en-IN", timezoneId: "Asia/Kolkata" });
  await context.addInitScript({ path: path.join(__dirname, "overlay.js") });
  const page = await context.newPage();
  const errors = [], beats = [], problems = [];
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

  // ---------- the product ----------
  const api = async (p, body) => {
    const r = await fetch(base + p, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return r.json();
  };
  const state = () => api("/api/state");
  const waitFor = async (pred, what, timeout = 180000) => {
    const t0 = Date.now();
    while (Date.now() - t0 < timeout) {
      const st = await state();
      if (pred(st)) return st;
      await sleep(200);
    }
    throw new Error("timed out waiting for " + what);
  };
  const task = (st, id) => (st.tasks || []).find((t) => t.id === id) || {};
  const reworked = (st, id) => (st.verifications || []).some((v) => v.task_id === id && v.verdict === "REQUIRES_REWORK");
  const pending = (st, kind) => (st.decisions.pending || []).some((d) => d.kind === kind);
  const work = (on) => api("/api/run/auto", on ? { on: true, delay: WORK_DELAY } : { on: false });

  // ---------- the presentation ----------
  const D = (fn, ...args) => page.evaluate(([f, a]) => window.__demo[f](...a), [fn, args]);
  const loc = (t) => (typeof t === "string" ? page.locator(t).first() : t);
  const handles = async (targets) => {
    const hs = [];
    for (const t of [].concat(targets)) {
      if (typeof t === "function") { hs.push(await t()); continue; }
      const l = loc(t);
      await l.waitFor({ state: "visible", timeout: 30000 });
      hs.push(await l.elementHandle());
    }
    return hs;
  };
  const safeTop = () => page.evaluate(() => (document.querySelector("header.top") ? 78 : 18));
  // The camera: bring the targets into the space between the top (or the sticky header) and the caption band, with an
  // eased scroll, first inside any scrolling panel that holds them, then the page. What already sits well inside
  // stays put; what fits is centred; what is taller starts at the top.
  const frame = async (targets) => {
    const hs = await handles(targets);
    const top = await safeTop();
    await page.evaluate(async ([els, top, bottom]) => {
      const D = window.__demo;
      const holder = (e) => {
        for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) {
          const cs = getComputedStyle(p);
          if (/(auto|scroll)/.test(cs.overflowY) && p.scrollHeight > p.clientHeight + 2) return p;
        }
        return null;
      };
      const inner = holder(els[0]);
      if (inner) {
        const r = els[0].getBoundingClientRect(), c = inner.getBoundingClientRect();
        if (r.top < c.top + 6 || r.bottom > c.bottom - 6) await D.scroll(inner, inner.scrollTop + r.top - c.top - 12);
      }
      const rs = els.map((e) => e.getBoundingClientRect());
      const u = { top: Math.min(...rs.map((r) => r.top)), bottom: Math.max(...rs.map((r) => r.bottom)) };
      const h = u.bottom - u.top, room = bottom - top;
      if (u.top >= top + 10 && u.bottom <= bottom - 10) return;
      const at = h + 40 <= room ? top + (room - h) / 2 : top + 14;
      const se = document.scrollingElement, max = se.scrollHeight - se.clientHeight;
      let y = Math.max(0, Math.min(max, window.scrollY + u.top - at));
      if (!document.querySelector("header.top")) {
        // no fixed header hides the top edge here, so it must fall between lines of text, not through one
        const uTop = u.top + window.scrollY, uBottom = u.bottom + window.scrollY;
        const lines = [...document.querySelectorAll("h1,h2,h3,p,li,label,td,th,b,span,a,button,input,textarea,select,.caps,.pill,.tag,.small")]
          .map((e) => e.getBoundingClientRect()).filter((r) => r.height > 0 && r.height < 170)
          .map((r) => ({ top: r.top + window.scrollY, bottom: r.bottom + window.scrollY }));
        // the nearest position to the one wanted where the edge cuts no line and the target still sits in the frame
        // clean: no line is cut by the edge, or sits pressed against it
        const clean = (v) => v <= 0 || !lines.some((r) => r.top < v + 10 && r.bottom > v - 2);
        const fits = (v) => uTop - v >= top - 4 && (h + 20 > room || uBottom - v <= bottom - 6);
        const y0 = y;
        for (let d = 0; d <= 220; d++) {
          const c = [y0 - d, y0 + d].find((v) => v >= 0 && v <= max && clean(v) && fits(v));
          if (c !== undefined) { y = c; break; }
        }
      }
      await D.scroll(null, y);
    }, [hs, top, CAPTION_TOP]);
    await sleep(120);
    return hs;
  };
  let spotted = [];
  // A highlight: framed first, drawn a little outside the target, never cut by the caption band. merge: one box
  // around all the targets.
  const spot = async (targets, tone = "", { merge = false, point = true } = {}) => {
    await frame(targets);
    const hs = await handles(targets);  // found again: the screen may have been redrawn while the camera moved
    const top = await safeTop();
    let rects = await page.evaluate((els) => els.map((e) => { const r = e.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom }; }), hs);
    if (merge) rects = [{ l: Math.min(...rects.map((r) => r.l)), t: Math.min(...rects.map((r) => r.t)), r: Math.max(...rects.map((r) => r.r)), b: Math.max(...rects.map((r) => r.b)) }];
    const boxes = rects.map((r) => {
      const x1 = Math.max(r.l - 9, 4), x2 = Math.min(r.r + 9, W - 4), y1 = Math.max(r.t - 9, top - 6), y2 = Math.min(r.b + 9, CAPTION_TOP - 6);
      if (r.b + 9 > CAPTION_TOP - 6 || r.t - 9 < top - 6) problems.push({ what: "highlight cut", target: String(targets).slice(0, 80), rect: r });
      return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
    });
    await D("spots", boxes, tone);
    spotted = boxes;
    if (point) {
      const b = boxes[boxes.length - 1];
      await D("cursor", b.x + b.w - 34, b.y + b.h - 30, 700);
    }
    await sleep(550);
  };
  const clear = async () => { spotted = []; await D("clearSpots"); await sleep(250); };
  // Reading time: a second and a half to find the caption, then about 200 words a minute.
  const readMs = (text) => 1500 + text.split(/\s+/).length * 300;
  const say = async (text, label, min = 0) => {
    beats.push({ label, text, wall: Date.now() / 1000, spots: spotted });
    await D("caption", text, label || "", "bottom");
    await sleep(Math.max(min, readMs(text)) + 400);
  };
  const unsay = async () => { await D("caption", ""); await sleep(450); };
  const moveTo = async (target, ms = 800) => {
    await frame(target);
    const [h] = await handles(target);
    const b = await h.boundingBox();
    await D("cursor", b.x + Math.min(b.width / 2, 60), b.y + b.height / 2, ms);
    await sleep(ms + 80);
  };
  const click = async (target) => {
    await moveTo(target);
    await D("ripple");
    await loc(target).click();
    await sleep(350);
  };
  const hideGuide = () => page.evaluate(() => { const g = document.getElementById("guide-off"); if (g) g.click(); });
  const top = async () => { await page.evaluate(() => window.__demo.scroll(null, 0)); await sleep(150); };
  const veil = async (on) => { await D("veil", on); await sleep(on ? 340 : 380); };
  // Moving between screens: the pointer goes to the sidebar, the screen fades, the new one arrives at its top.
  const nav = async (view) => {
    beats.push({ label: "~nav", text: view, wall: Date.now() / 1000, spots: [] });
    await unsay();
    await clear();
    await moveTo(`button.nav[data-view="${view}"]`, 700);
    await D("ripple");
    await veil(true);
    await page.click(`button.nav[data-view="${view}"]`);
    await sleep(450);
    await hideGuide();
    await page.evaluate(() => window.scrollTo(0, 0));
    await sleep(150);
    await veil(false);
  };
  // Opening another page: the screen fades, the page loads under the veil, and it fades back in.
  const openPage = async (url, ready, prep) => {
    beats.push({ label: "~page", text: url, wall: Date.now() / 1000, spots: [] });
    await unsay();
    await clear();
    await veil(true);
    await page.evaluate(() => { window.name = "demo-veil"; });
    await page.goto(url);
    await page.waitForSelector(ready);
    await page.evaluate(() => document.fonts.ready);
    await hideGuide();
    if (prep) await prep();
    await sleep(300);
    await veil(false);
  };
  const chapter = async (num, title, sub, prep) => {
    beats.push({ label: "~chapter", text: title, wall: Date.now() / 1000, spots: [] });
    await unsay();
    await clear();
    await D("card", `<div class="dc-wrap"><span class="dc-num in">${num}</span><span class="dc-chap in" style="animation-delay:.12s">${title}</span>
      <span class="dc-bar"></span><span class="dc-line in" style="animation-delay:.35s;font-size:28px;color:#3E4140">${sub}</span></div>`);
    const t0 = Date.now();
    await sleep(700);
    await D("veil", false);  // a veil left from the step before is lifted under the card
    if (prep) await prep();
    await sleep(Math.max(0, 3600 - (Date.now() - t0)));
    await D("hideCard");
    await sleep(700);
  };
  // The moments of the team's work, in the order they happen. A watcher holds the work the instant the next one is
  // true, so the screen shows it as it happens, not a step later.
  const watch = { queue: [], busy: false, timer: null };
  const expect = (...preds) => { watch.queue.push(...preds.map((pred) => ({ pred, hit: false, shown: false }))); };
  const brief = (st) => Object.fromEntries(["t_06", "t_07", "t_10", "t_11", "t_16"].map((id) => [id, task(st, id).status]));
  const watching = (on) => {
    if (!on) { clearInterval(watch.timer); return; }
    watch.timer = setInterval(async () => {
      const next = watch.queue.find((m) => !m.hit);
      if (watch.busy || !next) return;
      watch.busy = true;
      try {
        const st = await state();
        if (next.pred(st)) {
          await work(false);
          next.hit = true;
          beats.push({ label: "~caught", text: String(watch.queue.indexOf(next)), wall: Date.now() / 1000, spots: [], tasks: brief(st) });
        }
      } catch (e) { /* the next tick tries again */ } finally { watch.busy = false; }
    }, 60);
  };
  const caught = async (i, what) => {
    const t0 = Date.now();
    while (!watch.queue[i].hit) { if (Date.now() - t0 > 180000) throw new Error("timed out waiting for " + what); await sleep(100); }
  };
  // After a moment is shown the team goes on, unless the next moment already happened and is being held.
  const goOn = async (i) => {
    watch.queue[i].shown = true;
    const next = watch.queue[i + 1];
    if (!next || !next.hit) await work(true);
  };
  // A moment in the team's work: held when it happens, explained, then the team goes on.
  const moment = async (i, what, targets, text, label, opt = {}) => {
    await caught(i, what);
    await sleep(900);  // the screen catches up with the held state
    await spot(targets, opt.tone || "", opt);
    await say(text, label);
    await unsay();
    await clear();
    await goOn(i);
    await top();
  };

  // ---------- title ----------
  await page.goto(base + "/");
  await page.waitForSelector("#structure");
  await page.evaluate(() => document.fonts.ready);
  await hideGuide();
  await D("card", `<div class="dc-wrap"><span class="dc-word in">Cynqra</span><span class="dc-bar"></span>
    <span class="dc-line in" style="animation-delay:.5s">Describe what you want to build.</span>
    <span class="dc-line in" style="animation-delay:1.1s">Get it <i>working in the real world</i>, within your budget,</span>
    <span class="dc-line in" style="animation-delay:1.7s">without coordinating anyone.</span>
    <span class="dc-foot in" style="animation-delay:2.6s">Proof of concept, recorded from the real running software. Demo mode: the team's words come from a script. The code, the checks, the numbers and the deploy are real.</span></div>`);
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });
  await sleep(8200);

  // ---------- 01 the idea ----------
  const messy = (await state()).scenarios.find((x) => x.id === "bluedip").messy;
  await chapter("01", "Your idea", "A founder, a dream idea and a budget.", async () => { await page.fill("#messy", ""); await page.evaluate(() => window.scrollTo(0, 0)); });
  await sleep(600);
  await click("#messy");
  await D("caption", "A restaurant owner's idea, in their own words: fill the quiet hours with offers that earn money.", "Founder", "bottom");
  beats.push({ label: "Founder", text: "typing the idea", wall: Date.now() / 1000, spots: [] });
  await page.locator("#messy").pressSequentially(messy, { delay: 12 });
  await sleep(1400);
  await unsay();
  await click("#structure");
  await page.waitForSelector("#submit");
  await sleep(700);
  await hideGuide();
  await top();
  await sleep(500);
  await spot([".field.inf >> nth=0", ".field.inf >> nth=1"], "amber");
  await say("Cynqra turns it into a brief and marks the two things it guessed, so you check exactly those.", "Brief");
  await spot(".field:has(#usd)");
  await say("A hard budget, in dollars. Nothing is spent past it.", "Budget");
  await spot(".field:has(#f_stage)");
  await say("What you bring. Cynqra proposes cofounders only for what you don't do yourself.", "You");
  await unsay();
  await clear();
  await click("#submit");
  await D("caption", "You hand it over. You don't name a team.", "You decide", "bottom");
  await page.waitForSelector("#approve-workforce");
  await sleep(2600);

  // ---------- 02 what you'll get, and who delivers it ----------
  await chapter("02", "What you'll get", "And the team that delivers it, every seat checked.", async () => { await hideGuide(); await page.evaluate(() => window.scrollTo(0, 0)); });
  await sleep(900);
  await spot(".wiz-left .card >> nth=0");
  await say("Three outcomes, five risks that must not happen, and the guesses the idea rests on, riskiest first. The team is built from this list and nothing else.", "Outcome");
  const ctoBlockEnd = async () => (await page.locator(".wiz-right .tbl tbody tr.cof-row").nth(1).elementHandle()).evaluateHandle((e) => e.previousElementSibling);
  await spot([".wiz-right .tbl thead", ctoBlockEnd], "", { merge: true });
  await say("Three cofounders, each choosing its own team. Every seat says who asked for it, what it owns, and what would be left undone without it.", "Team");
  await spot(".wiz-left .card >> nth=1");
  await say("Why this team: every requirement has exactly one owner, and every risk has someone watching it. The confidence comes from these checks.", "Why");
  await spot(".wiz-right details");
  await say("An independent check tried to cut every seat. It cut a Security Expert that owned nothing, and kept the Designer: the only one on the owner's screen.", "Challenge");
  await unsay();
  await clear();
  await click('[data-team-option="lean"]');
  await sleep(500);
  const leanNote = page.locator(".wiz-right div.small", { has: page.locator("b", { hasText: "What the recommended team adds" }) }).first();
  await spot([".wiz-right [role=radiogroup]", leanNote], "", { merge: true });
  await say("Beside it, the lean team: ten seats instead of thirteen, with fewer specialists. In live mode you can choose it.", "Lean");
  await unsay();
  await clear();
  await click('[data-team-option="recommended"]');
  await sleep(400);
  await click("#approve-workforce");
  await D("caption", "You approve the team once.", "You decide", "bottom");
  await page.waitForSelector("#approve-plan");
  await sleep(1400);
  await veil(true);
  await hideGuide();
  await page.evaluate(() => window.scrollTo(0, 0));
  await sleep(200);
  await veil(false);
  await sleep(600);
  await spot(page.locator(".wiz-left .card", { has: page.locator(".caps", { hasText: "When each member starts" }) }));
  await say("Each member joins with its first task. Anyone with no work would leave before anything starts.", "Plan");
  await spot(page.locator(".wiz-left .card", { has: page.locator(".caps", { hasText: "Budget" }) }));
  await say("Every task is priced against your budget before work starts. The demo's scripted team costs nothing; real AI is priced in dollars.", "Budget");
  await unsay();
  await clear();
  await click("#approve-plan");
  await waitFor((st) => st.auto.on, "the run to start");
  await work(false);
  await D("veil", true);
  await D("caption", "You approve the plan and the budget once. From here the team runs itself.", "You decide", "bottom");
  await page.waitForSelector("header.top");
  await sleep(4200);

  // ---------- 03 the team at work ----------
  expect((st) => reworked(st, "t_06"), (st) => reworked(st, "t_07"), (st) => pending(st, "decision"),
    (st) => Number(task(st, "t_10").review_rounds || 0) > 0, (st) => (task(st, "t_11").answers || []).length > 0,
    (st) => reworked(st, "t_11"), (st) => ((st.workforce || {}).ceo_notices || []).some((n) => n.kind === "settled_by_cofounder"),
    (st) => pending(st, "deploy"));
  await chapter("03", "The team at work", "Cofounders run their areas. Every piece of work is checked before it counts.", async () => {
    await hideGuide();
    await page.click('button.nav[data-view="work"]');
    await page.waitForSelector(".tape");
    await page.evaluate(() => window.scrollTo(0, 0));
    watching(true);
    await work(true);
  });
  await sleep(500);
  await D("caption", "Everyone works at the same time. Cofounders hand out the work, answer their team's questions and review it before it counts.", "Work", "bottom");
  beats.push({ label: "Work", text: "board overview", wall: Date.now() / 1000, spots: [] });
  for (let i = 0; i < 4; i++) { await moveTo(page.locator(".col > .caps").nth(i), 900); await sleep(900); }
  await moveTo(".tape", 900);
  await sleep(1800);
  await unsay();
  await moment(0, "the forecast sent back", '.tcard[data-task="t_06"]',
    "The footfall forecast loses to last week's numbers on days it has not seen. The platform sends it back.", "Checked", { tone: "red" });
  await moment(1, "the financial model sent back", '.tcard[data-task="t_07"]',
    "The CFO's model says a restaurant is worth ₹49,975. The platform recomputes it from the model's own figures: ₹43,725. Back it goes.", "Numbers", { tone: "red" });
  await caught(2, "the rule on money");
  await nav("decisions");
  await page.waitForSelector(".dcard");
  await spot([".dcard > .between", ".dcard .dline"], "amber", { merge: true });
  await say("A rule on money cannot be undone, so it comes to you: how far an offer may go.", "You decide");
  await unsay();
  await clear();
  await click('.dcard button[data-decide="approve"]');
  await D("caption", "Approved. The rule goes into the company's memory.", "You decide", "bottom");
  await sleep(2600);
  await nav("work");
  await goOn(2);
  await moment(3, "the screen sent back", ['.tcard[data-task="t_10"]'],
    "The Chief Product Officer sends the Designer's screen back: it hid the money an offer loses.", "Reviewed", { tone: "amber" });
  await moment(4, "a question answered",
    ['.pobj.Blocker[data-task="t_11"]'],
    "When a member is unsure, it asks instead of guessing. The Backend Engineer asks which food cost to use; the Revenue Specialist answers. You are not interrupted.", "Questions");
  await moment(5, "the cap caught", '.tcard[data-task="t_11"]',
    "A test catches an estimate that ignored the owner's cap of 15 customers. Fixed before it counts.", "Checked", { tone: "red" });
  await moment(6, "the merge settled",
    '.tcard[data-task="t_16"]', "Merging the finished code can be undone, so the CTO settles it, and you are told instead of asked.", "Settled");
  await caught(7, "going live");
  watching(false);
  await nav("decisions");
  await page.waitForSelector(".dcard");
  await spot([".dcard > .between", ".dcard .dline"], "red", { merge: true });
  await say("Going live cannot be undone. It waits for you.", "You decide");
  await spot(".dcard .deny", "red");
  await say("The team also wanted to email the pilot restaurants. The rules stopped it: no team member sends messages outside the company.", "Stopped");
  await unsay();
  await clear();
  await click('.dcard button[data-decide="approve"]');
  await work(true);
  await D("caption", "Approved. Build, test, preview, health and smoke checks, then live.", "You decide", "bottom");
  const live = await waitFor((st) => st.live_url && pending(st, "accept_delivery"), "delivery");
  await work(false);
  await sleep(2200);

  // ---------- 04 live ----------
  await chapter("04", "It's live", "The working product, and everything you need to run it.", async () => {
    await page.click('button.nav[data-view="delivery"]');
    await page.waitForSelector(".stepper .live");
    await hideGuide();
    await page.evaluate(() => window.scrollTo(0, 0));
  });
  await sleep(500);
  await spot(".stepper");
  await say("All ten stages ran for real on this machine: build, test, preview, checks, and live.", "Live");
  await clear();
  await moveTo("#live-link");
  await D("ripple");
  // The live product opens in the same tab: Cynqra's own pages refuse to be embedded in another site, and stay that way.
  await openPage(live.live_url, "#meals .meal");
  await sleep(700);
  await spot(".card:has(#chart)");
  await say("Bluedip, live, as the owner sees it: footfall and revenue for the day, hour by hour.", "Bluedip");
  await spot("#meals");
  await say("A recommended offer, or none, for breakfast, lunch and dinner.", "Bluedip");
  await unsay();
  await clear();
  await click("#preview");
  await page.locator("#estimate .est").waitFor({ timeout: 10000 });
  await sleep(500);
  await spot("#estimate", "red");
  await say("The owner's own idea, 50% off from 1 pm to 4 pm, fills seats and loses money after food cost.", "Bluedip");
  await unsay();
  await clear();
  const disc = page.locator('input[name="discount"]');
  await click(disc);
  await disc.fill("20");
  await sleep(500);
  await click("#preview");
  await sleep(1000);
  await spot("#estimate");
  await say("At 20% off, the same window earns money. Numbers the owner can check.", "Bluedip");
  await openPage(base + "/", "header.top", async () => {
    await page.click('button.nav[data-view="delivery"]');
    await page.waitForSelector('[data-pack="measures"]');
    await page.evaluate(() => window.scrollTo(0, 0));
  });
  await sleep(500);
  await spot('[data-pack="measures"]');
  await say("The Company Pack: how you'll know it worked, with a target and a line below which to rethink.", "Company Pack");
  await spot('[data-pack="numbers"]');
  await say("The business numbers, recomputed by the platform: margin, payback, the month Bluedip stops losing money, and the funding it needs.", "Company Pack");
  await spot('[data-pack="steps"]');
  await say("And the next steps only you can take, such as showing the app to five owners.", "Company Pack");
  await unsay();
  await clear();
  await click('.view button[data-decide="approve"]');
  await D("caption", "You accept delivery.", "You decide", "bottom");
  await waitFor((st) => st.meta.phase === "accepted", "accepted");
  await sleep(2600);

  // ---------- 05 it keeps going ----------
  await chapter("05", "It keeps going", "Tell Cynqra what users said. The same team builds the next version.", async () => {
    await page.click('button.nav[data-view="company"]');
    await page.waitForSelector("#fb_text");
    await page.evaluate(() => window.scrollTo(0, 0));
  });
  await sleep(500);
  await spot(page.locator(".card", { has: page.locator("h2", { hasText: "Your update" }) }));
  await say("Your update, built from the record: what's done, what it cost, what was settled for you, and what the checks caught.", "Update");
  await unsay();
  await clear();
  await click("#fb_text");
  await page.locator("#fb_text").pressSequentially("Owners want yesterday's real covers next to the forecast.", { delay: 30 });
  await sleep(500);
  await click("#fb-save");
  await sleep(900);
  await spot(page.locator(".card", { has: page.locator("h2", { hasText: "What's next for your product" }) }));
  await say("What users said goes into the next cycle. You approve its plan and budget once; the release before it stays as the way back.", "Next cycle");
  await unsay();
  await clear();

  // ---------- end card ----------
  const st = await state();
  const m = st.metrics;
  const dep = (st.deployments || []).slice(-1)[0] || {};
  const settled = ((st.workforce || {}).ceo_notices || []).filter((n) => n.kind === "settled_by_cofounder").length;
  const cut = (((st.proposal || {}).challenge || {}).removed || []).length;
  const tiles = [
    [m.founder_interventions, "times you were needed, idea to live"],
    [m.tasks_verified, `of ${m.tasks_total} pieces of work checked`],
    [m.defects_caught_before_verified, "mistakes caught before they counted"],
    [cut, "seat cut before you saw the team"],
    [m.blockers_cleared_without_founder, "questions settled inside the team"],
    [settled, "decision settled for you, and told"],
    [(dep.test_ids || []).length, "tests passing in the live release"],
    [10, "deployment stages, health and smoke checked"],
  ].map(([v, l], i) => `<div class="dc-tile in" style="animation-delay:${0.4 + i * 0.12}s"><b data-to="${v}">0</b><span>${l}</span></div>`).join("");
  await D("card", `<div class="dc-wrap" style="width:1240px"><span class="dc-word in" style="font-size:72px">Cynqra</span>
    <span class="dc-line in" style="animation-delay:.2s">From an idea to a <i>working, checked, live product</i>, within budget.</span>
    <div class="dc-tiles">${tiles}</div>
    <span class="dc-foot in" style="animation-delay:1.6s">Proof of concept in demo mode. The run on real AI models is next. Run it yourself: see README.md.</span></div>`, true);
  await sleep(400);
  await D("countUp");
  await sleep(9000);

  const stopWall = Date.now() / 1000;
  await cdp.send("Page.stopScreencast");
  await sleep(300);
  const last = frames[frames.length - 1];
  const end = last ? last.t + Math.max(0.1, stopWall - last.wall) : 0;
  fs.writeFileSync(path.join(out, "frames.json"), JSON.stringify({ frames, end, errors }, null, 1));
  fs.writeFileSync(path.join(out, "beats.json"), JSON.stringify({ start: frames.length ? frames[0].wall : 0, beats, problems }, null, 1));
  console.log(JSON.stringify({ ok: errors.length === 0 && problems.length === 0, frames: frames.length, seconds: frames.length ? Math.round(end - frames[0].t) : 0, errors, problems }));
  await browser.close();
})().catch((e) => { console.log(JSON.stringify({ ok: false, errors: [String(e && e.stack || e)] })); process.exit(1); });
