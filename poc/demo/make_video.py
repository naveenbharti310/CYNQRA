#!/usr/bin/env python3
"""Record the Cynqra product demo video from the real running POC.

    python poc/demo/make_video.py [--out poc/demo/out]

Starts a fresh POC server on a free port with an empty data folder, drives it with
record_demo.js in headless Chromium (Node and Playwright needed), captures frames through
the browser's screencast, and encodes a 1920 x 1080 H.264 MP4 with ffmpeg. Nothing in the
video is staged outside the product: every screen is the POC doing the real work.
"""
from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
POC = HERE.parent
FPS = 30


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def encode(out: Path, name: str) -> Path:
    out = Path(out).resolve()
    meta = json.loads((out / "frames.json").read_text())
    frames = meta["frames"]
    if len(frames) < 10:
        raise SystemExit("too few frames were captured")
    # Resample to a constant 30 fps on the real capture clock: each output frame shows the
    # newest screencast frame at that instant, so the video runs at true speed.
    seq = out / "seq"
    shutil.rmtree(seq, ignore_errors=True)
    seq.mkdir()
    t0, t_end = frames[0]["t"], meta["end"] + 1.5
    j = 0
    for k in range(int((t_end - t0) * FPS) + 1):
        now = t0 + k / FPS
        while j + 1 < len(frames) and frames[j + 1]["t"] <= now:
            j += 1
        (seq / f"{k:06d}.jpg").symlink_to(out / "frames" / frames[j]["file"])
    mp4 = out / name
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(seq / "%06d.jpg"),
                    "-vf", "scale=1920:1080:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-preset", "slow",
                    "-crf", "20", "-movflags", "+faststart", str(mp4)], check=True)
    shutil.rmtree(seq, ignore_errors=True)
    return mp4


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--name", default="Cynqra_POC_demo.mp4")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for tool in ("node", "ffmpeg"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} is not installed")
    data = Path(tempfile.mkdtemp(prefix="cynqra_video_"))
    port = free_port()
    env = {k: v for k, v in __import__("os").environ.items()
           if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CYNQRA_S1_MODEL_CMD", "CYNQRA_MODEL")}
    server = subprocess.Popen([sys.executable, str(POC / "run_poc.py"), "--port", str(port), "--no-browser",
                               "--data", str(data)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/api/state", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        run = subprocess.run(["node", str(HERE / "record_demo.js"), base, str(out)], capture_output=True, text=True,
                             timeout=900)
        result = json.loads([x for x in run.stdout.splitlines() if x.startswith("{")][-1])
        print(json.dumps(result))
        if not result.get("ok"):
            return 1
    finally:
        server.terminate()
        server.wait(timeout=10)
        shutil.rmtree(data, ignore_errors=True)
    mp4 = encode(out, args.name)
    print(f"wrote {mp4}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
