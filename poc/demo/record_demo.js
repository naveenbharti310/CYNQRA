// Records the product demo video from the real running POC: the Bluedip demo, from the founder's idea to a live
// product and the next cycle, told as the founder sees it.
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
  const waitFor = async (pred, what, timeout = 180000) => {
    const t0 = Date.now();
    while (Date.now() - t0 < timeout) {
      const st = await state();
      if (pred(st)) return st;
      await sleep(250);
    }
    throw new Error("timed out waiting for " + what);
  };
  const task = (st, id) => (st.tasks || []).find((t) => t.id === id) || {};
  const reworked = (st, id) => (st.verifications || []).some((v) => v.task_id === id && v.verdict === "REQUIRES_REWORK");
  const pending = (st, kind) => (st.decisions.pending || []).some((d) => d.kind === kind);
  const D = (fn, ...args) => page.evaluate(([f, a]) => window.__demo[f](...a), [fn, args]);
  const loc = (sel) => (typeof sel === "string" ? page.locator(sel).first() : sel);
  const box = async (sel) => {
    const l = loc(sel);
    await l.waitFor({ state: "visible", timeout: 30000 });
    await l.scrollIntoViewIfNeeded();
    let b = await l.boundingBox();
    if (b && (b.y + Math.min(b.height, 420) > H - 170 || b.y < 0)) {  // keep it clear of the caption at the bottom
      await l.evaluate((e) => e.scrollIntoView({ block: "center" }));
      await sleep(250);
      b = await l.boundingBox();
      if (b && b.y + Math.min(b.height, 420) > H - 170) {
        await l.evaluate((e, dy) => { const s = e.closest(".view") || document.scrollingElement; s.scrollBy(0, dy); },
                         b.y + Math.min(b.height, 420) - (H - 190));
        await sleep(200);
        b = await l.boundingBox();
      }
    }
    await sleep(120);
    return b;
  };
  const moveTo = async (sel, ms = 800) => {
    const b = await box(sel);
    await D("cursor", b.x + b.width / 2, b.y + b.height / 2, ms);
    await sleep(ms + 60);
  };
  const click = async (sel) => {
    await moveTo(sel);
    await D("ripple");
    await loc(sel).click();
    await sleep(300);
  };
  const say = async (text, label, hold = 3800) => { await D("caption", text, label || ""); await sleep(hold); };
  const beat = async (text, label, hold = 4200) => { await say(text, label, hold); await D("caption", ""); };
  const spot = async (sels, tone) => {
    const rects = [];
    for (const s of [].concat(sels)) {
      const b = await box(s);
      rects.push({ x: b.x, y: Math.max(b.y, 8), w: b.width, h: Math.min(b.height, H - 150 - Math.max(b.y, 8)) });
    }
    await D("spots", rects, tone || "");
  };
  const clear = () => D("clearSpots");
  const hideGuide = async () => { const g = page.locator("#guide-off"); if (await g.count()) await g.first().click(); };
  const chapter = async (num, title, sub) => {
    await D("caption", "");
    await D("card", `<div class="dc-wrap"><span class="dc-num in">${num}</span><span class="dc-chap in" style="animation-delay:.12s">${title}</span>
      <span class="dc-bar"></span><span class="dc-line in" style="animation-delay:.35s;font-size:28px;color:#3E4140">${sub}</span></div>`);
    await sleep(3000);
    await D("hideCard");
    await sleep(650);
  };
  const nav = async (view) => { await D("caption", ""); await click(`button.nav[data-view="${view}"]`); await sleep(300); await hideGuide(); };

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
  await sleep(7600);
  await D("hideCard");
  await sleep(500);

  // ---------- 01 the idea ----------
  const messy = (await state()).scenarios.find((x) => x.id === "bluedip").messy;
  await page.fill("#messy", "");
  await chapter("01", "Your idea", "A founder, a dream idea and a budget.");
  await click("#messy");
  await D("caption", "A restaurant owner's idea, in their own words: fill the quiet hours with offers that earn money.", "Founder");
  await page.locator("#messy").pressSequentially(messy, { delay: 9 });
  await sleep(700);
  await click("#structure");
  await page.waitForSelector("#submit");
  await sleep(700);
  await hideGuide();
  await spot([".field.inf >> nth=0", ".field.inf >> nth=1"], "amber");
  await say("Cynqra turns it into a brief and marks the two things it guessed, so you check exactly those.", "Brief", 5000);
  await spot("#usd");
  await say("A hard budget, in dollars.", "Budget", 2800);
  await spot(".field:has(#f_stage)");
  await say("What you bring. Cynqra proposes cofounders only for what you don't do yourself.", "You", 4200);
  await clear();
  await click("#submit");
  await D("caption", "You hand it over. You don't name a team.", "You decide");
  await page.waitForSelector("#approve-workforce");
  await sleep(1800);
  await hideGuide();

  // ---------- 02 what you'll get, and who delivers it ----------
  await chapter("02", "What you'll get", "And the smallest team that delivers it.");
  await spot(".wiz-left .card >> nth=0");
  await say("Three outcomes, five risks that must not happen, and the guesses the idea rests on, riskiest first. The team is built from this list and nothing else.", "Outcome", 6400);
  await spot(".wiz-right .tbl");
  await say("Three cofounders, each choosing a team. Every seat says who asked for it, what it owns, and what would be left undone without it.", "Team", 6200);
  await spot(".wiz-left .card >> nth=1");
  await say("Why this team: every requirement has one owner, every risk someone watching it. The confidence comes from these checks.", "Why", 5600);
  await clear();
  await click(".wiz-right details summary");
  await spot(".wiz-right details");
  await say("An independent check tried to cut every seat. It cut a Security Expert that owned nothing, and kept the Designer: the only one on the owner's screen.", "Challenge", 6600);
  await clear();
  await click('[data-team-option="lean"]');
  await spot('[data-team-option="lean"]');
  await say("The lean team does the same work with ten seats instead of thirteen. You choose.", "Lean", 4400);
  await clear();
  await click('[data-team-option="recommended"]');
  await click("#approve-workforce");
  await D("caption", "You approve the team once.", "You decide");
  await page.waitForSelector("#approve-plan");
  await sleep(1500);
  await hideGuide();
  await spot(page.locator(".wiz-left .card", { has: page.locator(".caps", { hasText: "When each member starts" }) }));
  await say("Each member joins with its first task. Anyone with no work would leave before anything starts.", "Plan", 4800);
  await spot(page.locator(".wiz-left .card", { has: page.locator(".caps", { hasText: "Budget" }) }));
  await say("Every task is priced against your budget before anything starts.", "Budget", 3600);
  await clear();
  await click("#approve-plan");
  await waitFor((st) => st.auto.on, "the run to start");
  await api("/api/run/auto", { on: false });
  await D("caption", "You approve the plan and the budget once. From here the team runs itself.", "You decide");
  await page.waitForSelector("header.top");
  await sleep(2000);
  await hideGuide();

  // ---------- 03 the team at work ----------
  await chapter("03", "The team at work", "Cofounders run their areas. Every piece of work is checked before it counts.");
  await api("/api/run/auto", { on: true, delay: 0.8 });
  await nav("work");
  await page.waitForSelector(".tape");
  await sleep(600);
  await spot(".cols");
  await say("Everyone works at the same time. Cofounders hand out the work, answer their team's questions and review it.", "Work", 5200);
  await clear();
  await waitFor((st) => reworked(st, "t_06"), "the forecast sent back");
  await beat("The footfall forecast loses to last week's numbers on days it has not seen. The platform sends it back.", "Checked", 4600);
  await waitFor((st) => reworked(st, "t_07"), "the financial model sent back");
  await beat("The CFO's model says a restaurant is worth ₹49,975. The platform recomputes it from the model's own figures: ₹43,725. Back it goes.", "Numbers", 6000);
  await waitFor((st) => pending(st, "decision"), "the rule on money");
  await nav("decisions");
  await page.waitForSelector(".dcard");
  await sleep(400);
  await spot(".dcard");
  await say("A rule on money cannot be undone, so it comes to you: how far an offer may go.", "You decide", 5000);
  await clear();
  await click('.dcard button[data-decide="approve"]');
  await D("caption", "Approved. The rule goes into the company's memory.", "You decide");
  await sleep(1400);
  await nav("work");
  await waitFor((st) => Number(task(st, "t_10").review_rounds || 0) > 0, "the screen sent back");
  await beat("The Chief Product Officer sends the Designer's screen back: it hid the money an offer loses.", "Reviewed", 4600);
  await waitFor((st) => (task(st, "t_11").answers || []).length > 0, "a question answered");
  await beat("The Backend Engineer asks the Revenue Specialist which food cost to use, and gets an answer. You are not interrupted.", "Questions", 5000);
  await waitFor((st) => reworked(st, "t_11"), "the cap caught");
  await beat("A test catches an estimate that ignored the owner's cap of 15 customers. Fixed before it counts.", "Checked", 4400);
  await waitFor((st) => ((st.workforce || {}).ceo_notices || []).some((n) => n.kind === "settled_by_cofounder"), "the merge settled");
  await beat("Merging the finished code can be undone, so the CTO settles it, and you are told instead of asked.", "Settled", 5000);
  await waitFor((st) => pending(st, "deploy"), "going live");
  await nav("decisions");
  await page.waitForSelector(".dcard");
  await sleep(400);
  await spot(".dcard .pill.red", "red");
  await say("Going live cannot be undone. It waits for you.", "You decide", 3600);
  await clear();
  await click('.dcard button[data-decide="approve"]');
  await D("caption", "Approved. Build, test, preview, health and smoke checks, then live.", "You decide");
  await sleep(800);

  // ---------- 04 live ----------
  const live = await waitFor((st) => st.live_url && pending(st, "accept_delivery"), "delivery");
  await api("/api/run/auto", { on: false });
  await chapter("04", "It's live", "The working product, and everything you need to run it.");
  await nav("delivery");
  await page.waitForSelector(".stepper .live");
  await spot(".stepper");
  await say("All ten stages ran for real on this machine.", "Live", 3400);
  await clear();
  await moveTo("#live-link");
  await D("ripple");
  await D("caption", "");
  // The live product opens in the same tab: Cynqra's own pages refuse to embed another site, and stay that way.
  await page.goto(live.live_url);
  await page.evaluate(() => document.fonts.ready);
  const fr = page;
  await fr.locator("#meals .meal").first().waitFor({ timeout: 20000 });
  await sleep(600);
  await spot(fr.locator(".card:has(#chart)"));
  await say("Bluedip, live, as the owner sees it: footfall and revenue for the day, hour by hour.", "Bluedip", 4400);
  await spot(fr.locator("#meals"));
  await say("A recommended offer, or none, for breakfast, lunch and dinner.", "Bluedip", 3600);
  await clear();
  await click(fr.locator("#preview"));
  await fr.locator("#estimate .est").waitFor({ timeout: 10000 });
  await spot(fr.locator("#estimate"), "red");
  await say("The owner's own idea, 50% off from 1 pm to 4 pm, fills seats and loses money after food cost.", "Bluedip", 5400);
  await clear();
  const disc = fr.locator('input[name="discount"]');
  await click(disc);
  await disc.fill("20");
  await click(fr.locator("#preview"));
  await sleep(900);
  await spot(fr.locator("#estimate"));
  await say("At 20% off, the same window earns money. Numbers the owner can check.", "Bluedip", 4800);
  await clear();
  await D("caption", "");
  await page.goto(base + "/");
  await page.waitForSelector("header.top");
  await sleep(500);
  await hideGuide();
  await nav("delivery");
  await page.waitForSelector(".stepper .live");
  await spot(page.locator("h3", { hasText: "How you'll know it worked" }).locator("xpath=following-sibling::div[1]"));
  await say("The Company Pack: how you'll know it worked, with a target and a line below which to rethink.", "Company Pack", 5000);
  await spot(page.locator("h3", { hasText: "The numbers, recomputed by the platform" }));
  await moveTo(page.locator("h3", { hasText: "The numbers, recomputed by the platform" }));
  await say("The business numbers, recomputed by the platform: margin, payback, the month Bluedip stops losing money, and the funding it needs.", "Company Pack", 5600);
  await spot(page.locator("h3", { hasText: "Next steps only you can take" }));
  await say("And the next steps only you can take, such as showing the app to five owners.", "Company Pack", 4400);
  await clear();
  await click('.view button[data-decide="approve"]');
  await D("caption", "You accept delivery.", "You decide");
  await waitFor((st) => st.meta.phase === "accepted", "accepted");
  await sleep(1400);

  // ---------- 05 it keeps going ----------
  await chapter("05", "It keeps going", "Tell Cynqra what users said. The same team builds the next version.");
  await nav("company");
  await sleep(500);
  await spot(page.locator(".card", { has: page.locator("h2", { hasText: "Your update" }) }));
  await say("Your update, built from the record: what's done, what it cost, what was settled for you, and what the checks caught.", "Update", 5600);
  await clear();
  await click("#fb_text");
  await page.locator("#fb_text").pressSequentially("Owners want yesterday's real covers next to the forecast.", { delay: 26 });
  await click("#fb-save");
  await sleep(700);
  await spot(page.locator(".card", { has: page.locator("h2", { hasText: "What's next for your product" }) }));
  await say("What users said goes into the next cycle. You approve its plan and budget once; the release before it stays as the way back.", "Next cycle", 6200);
  await clear();
  await D("caption", "");

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
