#!/bin/sh
cd "$(dirname "$0")"
echo "Open http://127.0.0.1:8765"
exec python3 server.py
