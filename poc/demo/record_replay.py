#!/usr/bin/env python3
"""Record a complete demo run of the real engine as replay frames for the guided demo.

  python poc/demo/record_replay.py [out_dir]      default poc/demo/replay_build

Runs the demo journey with the real engine, gateway, verification and deployment: the
candidate tracker's code is written, tested, merged and deployed on this machine. After
every engine step and every founder decision it saves exactly what GET /api/state would
return, plus the audit replay of every task, answers to the organization graph, the export
bundle's manifest, and screenshots of the live product taken while it runs.

build_demo.py turns the result into one HTML page. Nothing in the frames is edited.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
POC = HERE.parent
sys.path.insert(0, str(POC))

from cynqra import policy  # noqa: E402
from cynqra.engine import Engine  # noqa: E402
from cynqra.intelligence import ScriptedSource  # noqa: E402

SCENARIO = json.loads((POC / "scenarios" / "candidate_tracker" / "scenario.json").read_text(encoding="utf-8"))


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "replay_build"
    if out.exists():
        shutil.rmtree(out)
    (out / "shots").mkdir(parents=True)
    work = Path(tempfile.mkdtemp(prefix="cynqra_replay_"))
    e = Engine(work / "run", intelligence=ScriptedSource())
    frames: list[dict] = []
    auto = {"on": False, "delay": 0.9}

    def frame(trigger: str, last: dict | None = None) -> None:
        s = e.snapshot()
        s["auto"] = dict(auto)
        s["last_step"] = last or {}
        frames.append({"trigger": trigger, "state": s})

    frame("start")
    e.create_company("Harbor Recruiting", "demo")
    e.draft_objective(SCENARIO["messy"])
    frame("structure")
    e.set_guardrails(budget_cap=120)
    e.confirm_objective()
    frame("confirm")
    plan = [d for d in e.pending_decisions() if d["kind"] == "approve_plan"][0]
    e.decide(plan["id"], "approve")
    auto["on"] = True
    frame("decide", {"did": "plan approved"})
    shots: dict = {}
    for _ in range(300):
        if e.meta["phase"] == "accepted":
            break
        r = e.step()
        if r["did"] != "idle":
            frame("step", r)
            if r["did"] == "verified" and e.live_url() and not shots:
                shots = product_shots(e.live_url(), out / "shots")
            continue
        pend = e.pending_decisions()
        if not pend:
            raise SystemExit(f"run went idle with nothing to decide: {r}")
        d = pend[0]
        e.decide(d["id"], "approve")
        if e.meta["phase"] == "accepted":
            auto["on"] = False
        frame("decide", {"did": "approved", "decision": d["id"], "kind": d["kind"]})
    if e.meta["phase"] != "accepted":
        raise SystemExit("the demo run did not reach accepted")

    replays = {t["id"]: e.replay(t["id"]) for t in e.tasks()}
    graph = {"approves": {a: policy.who_may(a) for a in policy.RISK},
             "owns": {t["id"]: e.graph("owns", t["id"]) for t in e.tasks()},
             "depends": {t["id"]: e.graph("depends", t["id"]) for t in e.tasks()}}
    export = sorted(e.paths["exports"].glob("*.zip"))[-1]
    with zipfile.ZipFile(export) as z:
        manifest = json.loads(z.read("manifest.json"))
    manifest["name"] = export.name
    manifest["bytes"] = export.stat().st_size
    tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-v"], cwd=e.paths["main"],
                           capture_output=True, text=True, timeout=300)
    data = {"recorded_at": frames[-1]["state"]["meta"].get("created_at"), "frames": frames, "replays": replays,
            "graph": graph, "export": manifest, "product_shots": shots,
            "product_tests": {"passed": tests.returncode == 0, "ran": (tests.stderr.split("Ran ")[-1].split(" ")[0]
                                                                       if "Ran " in tests.stderr else "0")}}
    (out / "replay.json").write_text(json.dumps(data, separators=(",", ":"), default=str), encoding="utf-8")
    e.close()
    shutil.rmtree(work, ignore_errors=True)
    print(f"{len(frames)} frames, {len(json.dumps(data)) // 1024} KB, product shots: {sorted(shots)}")
    return 0


PRODUCT_JS = r"""
const path = require("path"); const { execSync } = require("child_process");
let pw; try { pw = require("playwright"); } catch (e) { pw = require(path.join(execSync("npm root -g").toString().trim(), "playwright")); }
(async () => {
  const [url, dir] = process.argv.slice(2);
  const b = await pw.chromium.launch(); const p = await b.newPage({ viewport: { width: 1100, height: 720 } });
  await p.goto(url); await p.waitForTimeout(500);
  await p.screenshot({ path: path.join(dir, "product_empty.png") });
  const ago = (n) => { const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10); };
  for (const [n, days] of [["Priya Shah", 10], ["Arjun Mehta", 0]]) {
    await p.fill("#name", n); await p.fill("#applied", ago(days));
    await p.click("#add button[type=submit]"); await p.waitForTimeout(400);
  }
  await p.screenshot({ path: path.join(dir, "product_in_use.png") });
  await b.close();
})();
"""


def product_shots(url: str, folder: Path) -> dict:
    """Screenshots of the live product while it runs. Skipped, and said so, without Node and Playwright."""
    script = folder / "_shot.js"
    script.write_text(PRODUCT_JS, encoding="utf-8")
    try:
        subprocess.run(["node", str(script), url, str(folder)], check=True, timeout=120, capture_output=True)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"product screenshots skipped: {exc}")
        return {}
    finally:
        script.unlink(missing_ok=True)
    return {p.stem: p.name for p in folder.glob("product_*.png")}


if __name__ == "__main__":
    sys.exit(main())
