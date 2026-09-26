// Browser end to end test (A16): the whole journey through the real UI in Chromium.
// Usage: node walk.js <base_url> [screenshot_dir]
// Prints one JSON line: {"ok": bool, "phase": "...", "errors": [...], "steps": [...]}
const path = require("path");
const { execSync } = require("child_process");
function loadPlaywright() {
  try { return require("playwright"); } catch (e) { /* fall through */ }
  const root = execSync("npm root -g").toString().trim();
  return require(path.join(root, "playwright"));
}
(async () => {
  const { chromium } = loadPlaywright();
  const base = process.argv[2];
  const shots = process.argv[3];
  const opts = {};
  const fs = require("fs");
  for (const p of ["/opt/pw-browsers/chromium-1194/chrome-linux/chrome"]) if (fs.existsSync(p)) opts.executablePath = p;
  const browser = await chromium.launch(opts);
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [], steps = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  const shot = async (n) => { if (shots) await page.screenshot({ path: path.join(shots, n + ".png") }); };
  try {
    await page.goto(base + "/");
    await page.waitForSelector("#structure");
    await page.click("#structure");
    await page.waitForSelector("#confirm");
    steps.push("objective structured");
    const inferred = await page.$$eval(".field.inf", (els) => els.length);
    if (inferred !== 2) errors.push(`expected 2 inferred fields, saw ${inferred}`);
    await shot("01_objective");
    await page.fill("#f_priorities", "Seeing who is stuck first, then adding candidates");
    await page.fill("#cap", "150");
    await page.click("#confirm");
    await page.waitForSelector("#approve-plan");
    const st = await page.evaluate(async () => (await (await fetch("/api/state")).json()));
    if (st.budget.cap !== 150) errors.push(`budget cap edit was lost: ${st.budget.cap}`);
    if (st.objective.structured.priorities !== "Seeing who is stuck first, then adding candidates") errors.push("objective edit was lost");
    if (st.meta.mode !== "demo") errors.push(`mode is ${st.meta.mode}, expected demo`);
    steps.push("founder edits to a field and the budget cap were kept");
    steps.push("plan proposed");
    await shot("02_plan");
    await page.click("#approve-plan");
    for (let i = 0; i < 8; i++) {
      await page.waitForFunction(() => /Waiting on you|Delivered/.test(document.querySelector("header.top")?.textContent || ""), null, { timeout: 90000 });
      const head = await page.textContent("header.top");
      if (/Delivered and accepted/.test(head)) break;
      await page.click('button[data-view="decisions"]');
      await page.waitForSelector('button[data-decide="approve"]');
      const title = await page.textContent(".dcard h2");
      steps.push("founder approved: " + title.trim());
      await shot(`03_decision_${i}`);
      await page.click('button[data-decide="approve"]');
      await page.waitForTimeout(600);
    }
    let replay = "";
    for (const v of ["company", "organization", "work", "evolution", "audit", "delivery"]) {
      await page.click(`button[data-view="${v}"]`);
      await page.waitForTimeout(500);
      if (v === "audit") {
        await page.waitForSelector(".replay .ok-banner", { timeout: 15000 });
        replay = await page.textContent(".replay");
        steps.push("replay checked in the audit view");
      }
      await shot(`04_${v}`);
    }
    await page.click('button[data-view="work"]');
    await page.waitForTimeout(800);
    await page.click('button[data-view="work"]');
    await page.waitForTimeout(50);
    const opacity = Number(await page.$eval(".tcard", (el) => getComputedStyle(el).opacity));
    if (opacity < 0.99) errors.push(`cards replay their fade in on every repaint (opacity ${opacity} just after one)`);
    steps.push("a repaint does not replay the card animation");
    await page.click('button[data-view="delivery"]');
    await page.waitForTimeout(300);
    const live = await page.getAttribute("#live-link", "href");
    const app = await browser.newPage();
    await app.goto(live);
    await app.fill("#name", "Priya Shah");
    await app.click("button[type=submit]");
    await app.waitForSelector("td");
    const rows = await app.$$eval("#rows tr", (r) => r.length);
    steps.push(`live product has ${rows} candidate row(s)`);
    const phase = await page.evaluate(async () => (await (await fetch("/api/state")).json()).meta.phase);
    const ok = phase === "accepted" && rows >= 1 && /Replay complete/.test(replay) && errors.length === 0;
    console.log(JSON.stringify({ ok, phase, errors, steps }));
  } catch (e) {
    console.log(JSON.stringify({ ok: false, phase: null, errors: errors.concat(String(e)), steps }));
  }
  await browser.close();
})();
