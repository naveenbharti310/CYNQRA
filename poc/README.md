# poc/: the product's code

**What:** everything Cynqra runs: the engine, the screens, the demos and the tests. **Why** it is laid out this way:
the engine knows nothing about screens or demos, so each can change without the others. **How** to start: the
[README](../README.md) at the top of the repository; [docs/2_HOW_IT_WORKS.md](../docs/2_HOW_IT_WORKS.md) says where
each step of a project is in the code.

| Path | What it is |
| --- | --- |
| `run_poc.py` | Starts Cynqra in the browser |
| `desktop.py` | The desktop app, and its command-line checks (`--selftest`, `--check-model`, `--e2e`, `--workforce`) |
| `live_check.py` | A real-model run from the command line, with a hard spend cap |
| `workforce_demo.py` | The real-model run of the Bluedip idea that the `cynqra-workforce` workflow starts |
| `cynqra/` | The engine |
| `cynqra/intelligence_layer/` | Provider connections, credentials, the Intelligence Registry, Router and Gateway |
| `ui/` | The web screens, and the guide (`tour.js`) that explains each step in plain words |
| `scenarios/` | The scripted demos: `bluedip` (opens first), `candidate_tracker`, `restaurant_forecast`. Each worker's words are scripted; the code in `files/` is real and is tested and deployed for real |
| `tests/` | The automated tests; [TEST_REPORT.md](TEST_REPORT.md) says what each proves |
| `demo/` | Scripts that record the demo video |
| `live_reports/` | Reports of earlier real-model runs |
