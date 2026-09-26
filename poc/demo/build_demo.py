#!/usr/bin/env python3
"""Build the guided demo: one self-contained page that explains Cynqra end to end.

  python poc/demo/build_demo.py            records a fresh run if needed, then builds

Writes:
  03_pages/how-cynqra-works.html     double click to open, works offline, no install
  poc/demo/out/how-cynqra-works.artifact.html   the same page without the document
                                     wrapper, for publishing as a shareable link

The page is the real app (ui/app.js and ui/app.css, unchanged) over a recorded run of the
real engine (record_replay.py), plus the presenter layer in guided/ and the narration in
ui/tour.js. Fonts, frames and screenshots are inlined, so nothing is fetched.
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
POC = HERE.parent
ROOT = POC.parent
UI = POC / "ui"
BUILD = HERE / "replay_build"
OUT = HERE / "out"
REAL = {"dogwalks": POC / "live_reports" / "ui_20260926_dogwalks" / "13_product_walker.png",
        "bakery": POC / "live_reports" / "live_20260926_170520_product.png"}


def data_uri(path: Path, kind: str) -> str:
    return f"data:{kind};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def inline_fonts(css: str) -> str:
    return re.sub(r"url\((fonts/[^)]+\.woff2)\)", lambda m: f"url({data_uri(UI / m.group(1), 'font/woff2')})", css)


def script_json(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), default=str).replace("</", "<\\/")


def body_html(recorded: str) -> str:
    return f"""<div id="app" aria-live="polite"></div>
<div class="toasts" id="toasts" role="status" aria-live="polite"></div>
<section class="g-panel" id="g-panel" aria-label="Guided demo">
  <div class="g-text"><span class="g-chapter" id="g-chapter"></span><h2 class="g-title" id="g-title"></h2><p class="g-body" id="g-body"></p></div>
  <div class="g-controls"><button class="btn" id="g-back" type="button">Back</button><button class="btn" id="g-play" type="button" aria-pressed="false">Play</button><button class="btn primary" id="g-next" type="button">Next</button><span class="g-count" id="g-count"></span></div>
  <div class="g-track" aria-hidden="true"><i id="g-bar"></i></div>
  <div class="g-meta"><span>A recorded run of the real Cynqra engine in demo mode, {recorded}. The screens above are the real app; you can click around them at any step.</span><button id="g-real" type="button">See it with a real model</button></div>
</section>
<div class="g-overlay g-welcome" id="g-welcome">
  <div class="g-card" role="dialog" aria-modal="true" aria-labelledby="g-w-title">
    <span class="g-kicker">Cynqra · guided demo</span>
    <h1 id="g-w-title">How Cynqra works</h1>
    <p>A founder writes one sentence. Cynqra builds the organization to deliver it: a CTO, a PM and two engineers who plan, build, verify and ship, and who bring the founder only the decisions that need a founder.</p>
    <p>This is one complete run of the real engine, recorded step by step. In order, you will see:</p>
    <ol class="g-steps">
      <li>one sentence become a structured objective</li>
      <li>the organization and the plan the founder approves</li>
      <li>work move between workers as structured messages, with a defect caught and a Blocker cleared without the founder</li>
      <li>policy stop an email no worker is allowed to send</li>
      <li>a product go live, with a record of every step</li>
    </ol>
    <div class="g-row"><button class="btn primary" id="g-start" type="button">Start the tour</button><button class="btn" id="g-explore" type="button">Explore the finished run</button></div>
    <span class="g-keys">Use <kbd>→</kbd> and <kbd>←</kbd> or the buttons at the bottom. <kbd>Space</kbd> plays and pauses.</span>
  </div>
</div>
<div class="g-overlay" id="g-modal" hidden>
  <div class="g-card" role="dialog" aria-modal="true"><button class="btn sm g-close" id="g-modal-close" type="button">Close</button><div id="g-modal-body"></div></div>
</div>"""


def main() -> int:
    if not (BUILD / "replay.json").exists():
        subprocess.run([sys.executable, str(HERE / "record_replay.py"), str(BUILD)], check=True)
    replay = json.loads((BUILD / "replay.json").read_text(encoding="utf-8"))
    for f in replay["frames"][:-1]:
        f["state"].pop("policy", None)  # identical in every frame; the page restores it from the last
    images = {"product_in_use": data_uri(BUILD / "shots" / "product_in_use.png", "image/png")}
    images.update({k: data_uri(p, "image/png") for k, p in REAL.items()})
    recorded = str(replay["recorded_at"])[:10]
    head = ("<title>How Cynqra Works</title>\n"
            f"<style>\n{inline_fonts((UI / 'app.css').read_text(encoding='utf-8'))}\n</style>\n"
            f"<style>\n{(HERE / 'guided' / 'demo.css').read_text(encoding='utf-8')}\n</style>\n")
    scripts = (f'<script type="application/json" id="replay-data">{script_json(replay)}</script>\n'
               f'<script type="application/json" id="replay-images">{script_json(images)}</script>\n'
               f"<script>\n{(UI / 'tour.js').read_text(encoding='utf-8')}\n</script>\n"
               f"<script>\n{(HERE / 'guided' / 'demo.js').read_text(encoding='utf-8')}\n</script>\n"
               f"<script>\n{(UI / 'app.js').read_text(encoding='utf-8')}\n</script>\n")
    body = body_html(recorded)
    OUT.mkdir(exist_ok=True)
    artifact = OUT / "how-cynqra-works.artifact.html"
    artifact.write_text(head + body + "\n" + scripts, encoding="utf-8")
    page = ROOT / "03_pages" / "how-cynqra-works.html"
    page.write_text('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                    f"{head}</head>\n<body>\n{body}\n{scripts}</body>\n</html>\n", encoding="utf-8")
    print(f"{page.relative_to(ROOT)}  {page.stat().st_size // 1024} KB")
    print(f"{artifact.relative_to(ROOT)}  {artifact.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
