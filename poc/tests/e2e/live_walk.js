// Live mode through the real UI in Chromium, with whatever model the server was started with.
// Usage: node live_walk.js <base_url> <screenshot_dir> "<objective>" [--reject-plan-once]
// Clicks what a founder clicks: Live mode, structure, confirm, (optionally ask for a different
// plan once), approve, then every decision card, "Try the same step again" after a model
// error, and accept delivery. Then opens the live product. Waits are long because a real
// model answers each step. Prints one JSON line: {"ok", "phase", "steps", "errors", "live_url"}.
const path = require("path");
const { execSync } = require("child_process");
function loadPlaywright() {
  try { return require("playwright"); } catch (e) { /* fall through */ }
  return require(path.join(execSync("npm root -g").toString().trim(), "playwright"));
}
(async () => {
  const { chromium } = loadPlaywright();
  const [base, shots, objective] = process.argv.slice(2, 5);
  const rejectOnce = process.argv.includes("--reject-plan-once");
  const LONG = 45 * 60 * 1000;
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [], steps = [];
  let n = 0;
  page.on("pageerror", (e) => errors.push(String(e)));
  const shot = async (name) => { await page.screenshot({ path: path.join(shots, `${String(++n).padStart(2, "0")}_${name}.png`) }); };
  const head = async () => (await page.textContent("header.top").catch(() => "")) || "";
  let result = { ok: false };
  try {
    await page.goto(base + "/");
    await page.waitForSelector("#structure");
    await page.check("#m-live input");
    await page.fill("#coname", "Live UI check");
    await page.fill("#messy", objective);
    await page.click("#structure");
    steps.push("live mode chosen, objective sent");
    await page.waitForSelector("#confirm", { timeout: LONG });
    const pill = await page.textContent(".wiz-top .pill");
    if (!/Live mode/.test(pill)) errors.push(`mode pill says ${pill}`);
    steps.push(`objective structured, ${await page.$$eval(".field.inf", (e) => e.length)} inferred fields`);
    await shot("objective");
    await page.click("#confirm");
    await page.waitForSelector("#approve-plan:not([disabled])", { timeout: LONG });
    steps.push(`plan proposed: ${await page.$$eval(".plan-table tbody tr", (r) => r.length)} tasks`);
    await shot("plan");
    if (rejectOnce) {
      const first = await page.getAttribute("#approve-plan", "data-id");
      await page.click("#replan");
      await page.waitForFunction((id) => { const b = document.querySelector("#approve-plan"); return b && !b.disabled && b.dataset.id !== id; },
        first, { timeout: LONG });
      steps.push(`asked for a different plan; new plan: ${await page.$$eval(".plan-table tbody tr", (r) => r.length)} tasks`);
      await shot("plan_again");
    }
    await page.click("#approve-plan");
    await page.waitForSelector("nav.side", { timeout: 60000 });
    steps.push("organization and plan approved, run started");
    for (let i = 0; i < 60; i++) {
      await page.waitForFunction(() => /Waiting on you|Delivered and accepted|Stopped/.test(document.querySelector("header.top")?.textContent || ""),
        null, { timeout: LONG });
      const h = await head();
      if (/Delivered and accepted/.test(h)) { steps.push("delivery accepted"); break; }
      if (/Stopped/.test(h)) {
        const retry = await page.$("#resume");
        if (!retry) throw new Error("run stopped with no way to retry: " + (await page.textContent(".notice").catch(() => "")));
        steps.push("model error shown: " + ((await page.textContent(".notice")) || "").slice(0, 160));
        await shot("stopped");
        await retry.click();
        await page.waitForFunction(() => !/Stopped/.test(document.querySelector("header.top")?.textContent || ""), null, { timeout: 60000 });
        steps.push("Try the same step again clicked, run resumed");
        continue;
      }
      await page.click('button.nav[data-view="decisions"]');
      await page.waitForSelector('.dcard [data-decide="approve"]:not([disabled])', { timeout: 60000 });
      const title = (await page.textContent(".dcard h2")) || "";
      await shot("decision_" + title.replace(/[^A-Za-z0-9]+/g, "_").slice(0, 40));
      await page.click('.dcard [data-decide="approve"]');
      steps.push("approved: " + title);
      await page.waitForFunction((t) => !Array.from(document.querySelectorAll(".dcard h2")).some((h) => h.textContent === t) ||
        /Delivered and accepted/.test(document.querySelector("header.top")?.textContent || ""), title, { timeout: 60000 });
      await page.click('button.nav[data-view="work"]').catch(() => {});
    }
    await page.click('button.nav[data-view="delivery"]');
    await page.waitForSelector("#live-link", { timeout: 60000 });
    await shot("delivery");
    const live = await page.getAttribute("#live-link", "href");
    const product = await browser.newPage({ viewport: { width: 1200, height: 800 } });
    product.on("pageerror", (e) => errors.push("product: " + String(e)));
    const resp = await product.goto(live);
    await product.waitForTimeout(800);
    await product.screenshot({ path: path.join(shots, `${String(++n).padStart(2, "0")}_live_product.png`), fullPage: true });
    steps.push(`live product ${live} answered ${resp.status()}`);
    await page.click('button.nav[data-view="audit"]');
    await page.waitForSelector(".ok-banner, .bad-banner", { timeout: 60000 });
    steps.push("replay: " + (await page.textContent(".ok-banner, .bad-banner")));
    await shot("audit");
    result = { ok: errors.length === 0 && resp.status() === 200, live_url: live };
  } catch (e) {
    errors.push(String(e));
    await shot("failure").catch(() => {});
  }
  const phase = /Delivered and accepted/.test(await head()) ? "accepted" : "not accepted";
  console.log(JSON.stringify({ ...result, phase, steps, errors }));
  await browser.close();
})();
