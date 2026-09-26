# Run Cynqra on your laptop

Cynqra's organization runs on your own machine with an open-source model: a CTO, a PM and two
engineers plan, write real code, run real tests, fix their own failures, merge and deploy a
working web app on your laptop. You make the founder's decisions in the terminal. No API key,
no cloud, no cost per run.

## 1. Install (once, 10 to 30 minutes, mostly the model download)

Get the project first: `git clone` it, or copy the folder.

| Your laptop | Do this |
| --- | --- |
| Windows | Double click `INSTALL.bat` |
| macOS or Linux | In a terminal, in the project folder: `./install.sh` |

The installer checks Python (3.10 or newer), installs [Ollama](https://ollama.com) if it is
missing, picks the model for your memory, downloads it, writes `poc/local_config.json` and runs
the doctor. It is safe to run again. To pick a model yourself: `./install.sh qwen3.6:27b` or
`INSTALL.bat qwen3.6:27b`.

## 2. Check

    ./cynqra doctor            (Windows: CYNQRA.bat doctor)
    ./cynqra doctor --full     also has the model write a small module and pass its tests

Every line should say PASS. A WARN line says what to do.

## 3. Run it

    ./cynqra run               (Windows: double click CYNQRA.bat)

It asks what you want to build, in a sentence or two, then:

1. shows the structured objective; you confirm or edit it
2. shows the organization and the plan; you approve it or ask for another
3. the organization works; each step prints as it happens, with the model's speed
4. it stops when it needs you: a product rule, the merge, the production deploy, delivery.
   You approve, reject with a reason, or edit the rule
5. at the end the product is running on your machine: open the address it prints

`./cynqra run --yes "your objective"` runs unattended and approves every decision (they are all
listed in the report). Every run writes a report to `poc/live_reports/` and keeps everything the
organization produced in `poc/data/cli_runs/`. `./cynqra ui` shows the same engine in the browser.

## Which model, and how long a run takes

From the research in `poc/research/local_open_models_2026-09.md` (September 2026). The installer
chooses by memory; `./cynqra setup --model <tag>` changes it.

| Laptop | Model the installer picks | Other choices | Expected time per run |
| --- | --- | --- | --- |
| 32 GB or more (Mac or PC) | `qwen3.6:35b` | `qwen3.6:27b` stronger but 3 to 4 times slower; `gpt-oss:20b` faster fallback | Mac or GPU: about 10 to 60 min. CPU only: about 35 min to 3 h |
| 16 to 24 GB | `qwen3.5:9b` | `qwen3.5:4b` smaller; `gpt-oss:20b` only with a 6 to 8 GB NVIDIA GPU or a 24 GB Mac | CPU only: 1.5 to 4.5 h. Better: use a teammate's bigger machine (below) |

These times are estimates from published speeds, not yet measured on your machines. Recording
the real numbers is part of the test (see "What to send back").

**Why these.** `qwen3.6:35b` has the strongest published coding results that fit 32 GB, and only
3 billion of its parameters work on each token, so it is fast without a GPU. Dense models of 24B
and more take 15 to 25 minutes a call on a laptop CPU. The published scores are the vendors' own;
no independent 2026 comparison exists, which is why `bench` exists.

## Compare models on your own laptop

    ./cynqra bench qwen3.6:35b gpt-oss:20b qwen3.5:9b

Each model structures three objectives, writes a plan, and writes a store with its tests, fixing
it from the failures for up to three rounds. It prints a table and saves it to
`poc/live_reports/bench_*.json`. Pull a model first with `ollama pull <tag>`. The full test of a
model is a whole run: `./cynqra run --yes "..."` after `./cynqra setup --model <tag>`.

## Share one strong machine with the team

A 16 GB laptop without a GPU is too slow for a live demo. One 32 GB or larger machine can serve
the model to the others on a trusted network (office or home, never a public network):

On the strong machine, make Ollama listen on the network and restart it:

- macOS: `launchctl setenv OLLAMA_HOST 0.0.0.0`, then quit and reopen Ollama
- Windows: set the user environment variable `OLLAMA_HOST` to `0.0.0.0`, then restart Ollama
- Linux: `sudo systemctl edit ollama`, add `Environment="OLLAMA_HOST=0.0.0.0"`, then `sudo systemctl restart ollama`

On each other laptop: `./cynqra setup --model qwen3.6:35b --host http://<strong machine's IP>:11434`
then `./cynqra doctor`. The engineers' code still runs and deploys on your own laptop; only the
thinking happens on the shared machine.

## What is real here

- The model is an open-weight model running on your machine through Ollama. Its words are not scripted.
- The engineers are agents: they write files, run their own tests through the gateway (checked
  by policy and recorded), read the failures and fix them before handing over. Then independent
  verification runs every test again, including earlier tasks' tests, and starts the app.
- Policy, budgets, the founder's decisions, the append-only event log, the deploy with health
  and smoke checks, and the export are the same engine as always.

Limits: the worker code runs in a folder with a cleaned environment, not a container; the
deployment target is a local process; one run at a time per machine.

## Settings (poc/local_config.json)

Written by the installer; an environment variable of the same meaning overrides it.

| Key | Meaning | Default |
| --- | --- | --- |
| `model` | Ollama tag | chosen by memory |
| `host` | where Ollama runs | `http://127.0.0.1:11434` |
| `num_ctx`, `num_predict` | context window and answer length, sent with every call | 32768 and 8192 (24576 and 6144 on the 16 GB tier) |
| `think` | model reasoning: `false`, or `low` for gpt-oss | false |
| `temperature`, `seed` | 0 and 42 for repeatable answers; a retry uses 0.4 | |
| `self_checks` | how many times an engineer may test and fix its own work | 2 |

Every call to Ollama goes to its native `/api/chat` with a JSON schema for structured answers
(code comes back as plain file blocks, never escaped inside JSON), `shift: false` and
`truncate: false` so an overlong prompt is an error instead of being cut silently, and
`keep_alive` so the model stays loaded through a run. LM Studio or llama.cpp's `llama-server`
also work: set `local_base_url` (for example `http://127.0.0.1:1234/v1`) and `local_model` instead
of `model`, and set the context size when the server loads the model.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Ollama is not running` | open the Ollama app, or run `ollama serve` |
| `model ... is not installed` | `ollama pull <tag>` |
| `the prompt is longer than num_ctx` | raise `num_ctx` in `poc/local_config.json` (memory permitting) |
| `reply truncated` | raise `num_predict`; on the 16 GB tier use a smaller objective |
| very slow, fans loud | plug in to mains power; close the browser and IDE; or share a bigger machine |
| `[WARN] Ollama: version` | update Ollama to 0.34.4 or newer |
| a run stopped with a model error | at the prompt choose retry; the same step runs again and nothing was lost |

## What to send back after testing

For each laptop: the `doctor --full` output, the `bench` table, and one full run's report from
`poc/live_reports/` (it holds every call's real token counts and times). Those numbers replace the
estimates above and decide the model for the next milestone.
