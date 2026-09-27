# poc/: the product's code

Start with the [README](../README.md) at the top of the repository. This folder holds:

| Path | What it is |
| --- | --- |
| `run_poc.py` | Starts Cynqra in the browser |
| `desktop.py` | The desktop app, and its command-line checks (`--selftest`, `--check-model`, `--e2e`, `--workforce`) |
| `live_check.py` | A real-model run from the command line, with a hard spend cap |
| `workforce_demo.py` | The real-model demonstration the `cynqra-workforce` workflow runs |
| `cynqra/` | The engine. [docs/2_HOW_IT_WORKS.md](../docs/2_HOW_IT_WORKS.md) says what each file does |
| `cynqra/intelligence_layer/` | Provider connections, credentials, the Intelligence Registry, Router and Gateway |
| `ui/` | The web screens |
| `scenarios/` | The two scripted demos |
| `tests/` | The automated tests; [TEST_REPORT.md](TEST_REPORT.md) describes them |
| `demo/` | Scripts that record the demo for the replay page |
