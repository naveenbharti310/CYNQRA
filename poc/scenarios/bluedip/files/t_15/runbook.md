# Bluedip release 1: runbook

**What:** how to run Bluedip, check it and roll it back. **Why:** a restaurant must be able to trust that the
service is up during its services. **How:** one process, one data file, and every release kept. Covers r_12.

## Run

`PORT=8080 DATA_FILE=bluedip.json python app.py` on the company's own host. `GET /health` answers 200 when it is
up. The first start shows a sample restaurant, marked as sample on the page, until the owner's own history arrives.
The smoke checks in smoke.json run after every release; the live run uses only the read-only ones, so real offers
are never touched.

## Rollback

Stop the process and start the previous release's folder with the same DATA_FILE. The data file is kept across
releases, and every release is kept as a package, so going back loses no offer and no history.
