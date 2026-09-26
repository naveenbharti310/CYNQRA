#!/usr/bin/env python3
"""Start the Cynqra POC and open it in the browser.

  python poc/run_poc.py                 http://127.0.0.1:8750
  python poc/run_poc.py --port 9000 --no-browser

Live mode needs ANTHROPIC_API_KEY or OPENAI_API_KEY set before starting.
Data lives in poc/data. A reset archives the run; nothing is deleted.
"""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cynqra.server import App, make_server  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Cynqra POC")
    ap.add_argument("--port", type=int, default=8750)
    ap.add_argument("--data", default=str(HERE / "data"))
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    app = App(Path(args.data))
    server = make_server(app, args.port)
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"Cynqra POC running at {url}  (Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
