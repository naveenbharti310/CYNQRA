#!/usr/bin/env bash
# Cynqra installer for macOS and Linux. Run from the project folder:   ./install.sh [ollama-model-tag]
# Installs Ollama if needed, picks the model for this machine (or the one you name), downloads it,
# writes poc/local_config.json and runs the doctor. Safe to run again.
set -euo pipefail
cd "$(dirname "$0")"
HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
case "$HOST" in http*) URL="$HOST" ;; *) URL="http://$HOST" ;; esac
say() { printf '\n== %s\n' "$*"; }

say "1 of 5  Python 3.10 or newer"
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10+ is missing."
  if [ "$(uname)" = "Darwin" ]; then echo "Install it from https://www.python.org/downloads/ (or: brew install python), then run ./install.sh again."
  else echo "Install it with your package manager (for example: sudo apt install python3), then run ./install.sh again."; fi
  exit 1
fi
"$PY" --version

say "2 of 5  Ollama, which runs the open model on this machine"
if ! command -v ollama >/dev/null 2>&1; then
  if [ "$(uname)" = "Darwin" ]; then
    if command -v brew >/dev/null 2>&1; then brew install ollama
    else echo "Download Ollama from https://ollama.com/download/mac, open it once, then run ./install.sh again."; exit 1; fi
  else
    echo "Installing Ollama with its official script (it may ask for your password)."
    curl -fsSL https://ollama.com/install.sh | sh
  fi
fi
ollama --version || true

say "3 of 5  Starting Ollama"
if ! curl -fsS "$URL/api/version" >/dev/null 2>&1; then
  if [ "$(uname)" = "Darwin" ] && open -a Ollama >/dev/null 2>&1; then :
  elif command -v systemctl >/dev/null 2>&1 && systemctl start ollama >/dev/null 2>&1; then :
  else nohup ollama serve >"${TMPDIR:-/tmp}/ollama.log" 2>&1 & fi
  for _ in $(seq 1 30); do curl -fsS "$URL/api/version" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "$URL/api/version" || { echo "Ollama did not start. Open the Ollama app, or run: ollama serve"; exit 1; }
echo

say "4 of 5  Choosing and downloading the model (several GB the first time)"
if [ "${1:-}" != "" ]; then MODEL="$("$PY" poc/cynqra_cli.py setup --print-model --model "$1")"
else MODEL="$("$PY" poc/cynqra_cli.py setup --print-model)"; fi
echo "Model: $MODEL  (settings in poc/local_config.json)"
ollama pull "$MODEL"

say "5 of 5  Checking everything"
"$PY" poc/cynqra_cli.py doctor
echo
echo "Next:  ./cynqra run        (or: $PY poc/cynqra_cli.py run)"
