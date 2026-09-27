# Covers forecast: runbook

Covers r_09.

## Run

`PORT=8080 DATA_FILE=covers.json python app.py` on the office computer. `GET /health` answers 200 when it is up.
The first start seeds a sample history, marked on the page, until real covers are recorded.

## Rollback

Stop the process and start the previous release's folder with the same DATA_FILE: the history file is kept
across releases, and every release is kept as a package.
