# 4. Run and test

**What** this covers: how to run Cynqra, test it and build it, and what each run proves. **Why** it matters: a
claim about Cynqra is only as good as the run behind it, and anyone should be able to repeat it. **How:** everything
runs on Python 3.10 or newer, with the standard library only; nothing to install.

## Run it

| To... | Do this | What it shows |
| --- | --- | --- |
| **Watch the demo** (free, scripted words; real code, models, tests and going live) | `python3 poc/run_poc.py`, choose **Watch a demo instead**, press **Make it a brief** | The Bluedip project through all seven steps, from the founder's words to a live app, audited and accepted. Two smaller demos are in the list. |
| **Run your own idea with an online AI** | Start as above (Cynqra opens on your own idea, with nothing filled in), click **Connect a provider** and paste your key into Cynqra's secrets file. Cynqra offers the provider's models released in the last 12 months, evaluates each one on its own work, then chooses a model for every team member. Answer the four questions, press **Make it a brief**, and set a budget. | What real AI models do with your idea |
| **Run with a model on your own computer** | Install the desktop app (below) and open **This computer** to download a model. No key needed. | The same, privately, more slowly |
| **Install the desktop app** | Download it from the repository's **Releases** page (Windows, macOS, Linux), or run `python3 poc/desktop.py` | Cynqra in its own window |

**On Windows, the quickest way to try every change:** clone the repository once, then double-click
`Start-Cynqra.cmd` in its folder. Each start fetches the newest version (`git pull`) and opens Cynqra, so a fix is
ready the moment it is pushed, with no installer, no build and no GitHub minutes. It needs Python 3.10+ and Git for
Windows, installed once. Local models on this computer need the installed app (it bundles llama-server); online
providers work from here.

Never paste a key into a chat or a document. Keys live only in environment variables, Cynqra's secrets file
(readable only by you), or GitHub secrets.

## What Cynqra decides for you, and what it never assumes

A first visit is empty: no project name, no idea, no model. Cynqra asks four questions (what you want to build, who it
is for, the result you want, anything it must or must not do) and writes the brief from your answers; it asks for a
budget before it plans. It starts no model by itself.

When a provider is connected with no models named, Cynqra reads when each model was first released (the provider's
own dates when it gives real ones, else OpenRouter's public catalogue, read at most once a day) and offers only the
chat models released in the last 12 months, the newest version of each family. Video, music, speech, robotics, safety
filters and aliases are left out. **Search and choose models** on the connection lists everything, newest first, to
add or remove any. Each new model is then evaluated on Cynqra's own work (planning a brief, and writing code that must
pass its tests), and the Router gives each seat the model measured best at that seat's kind of work: planning for a
cofounder, code for an engineer (`poc/tests/test_first_run.py`).

## Connect a free online AI

**What:** the settings for the online platforms that give free use, so a real team can be tested at no cost. **Why:**
a free tier limits how often it can be called and some do not accept every way of asking for JSON; Cynqra now waits
out a busy reply, falls back to plain JSON when a provider refuses a schema, and gives thinking models room to answer
(`poc/tests/test_hosted_providers.py`). **How:** open **Intelligence**, then **Connect a provider**, and fill in:

| Field | Google Gemini | NVIDIA Build | Mistral | Z.ai |
| --- | --- | --- | --- | --- |
| Get a key | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | [build.nvidia.com](https://build.nvidia.com) | [console.mistral.ai](https://console.mistral.ai) | [z.ai/model-api](https://z.ai/model-api) |
| Provider | OpenAI-compatible API | OpenAI-compatible API | OpenAI-compatible API | OpenAI-compatible API |
| Endpoint URL | `https://generativelanguage.googleapis.com/v1beta/openai` | `https://integrate.api.nvidia.com/v1` | `https://api.mistral.ai/v1` | `https://api.z.ai/api/paas/v4` |
| Models to offer | `gemini-3.5-flash-lite` (500 free calls a day; the newest Flash gives about 20) | `moonshotai/kimi-k3` | the Devstral and Mistral Medium names in the console | `glm-4.7-flash` (as the console names it) |
| Price in and out | 0 and 0 | 0 and 0 | 0 and 0 | 0 and 0 |
| Thinking effort | the model's own default | Low (Kimi K3 thinks at its maximum unless told, at about 10 tokens a second) | the model's own default | the model's own default |
| Calls per minute | 12 | 30 | 30 | 5 |

Leave **Local server** as "Not a local server" and keep the key in **Cynqra's secrets file** (or name an environment
variable). Models to offer may be left blank: Cynqra then offers only the newest ones (see above). Always enter the price: a model Cynqra has no price for is counted at the highest price, and
the budget stop would end a free run early. Free tiers may keep what is sent to them, so test with sample ideas.

## Test it

```
cd poc
python3 -m unittest discover -s tests -t tests
```

The suite size changes as the implementation evolves; use the test runner output as the current count.
`poc/tests/test_objective_intelligence.py` covers the objective intelligence control loop: the evidence model and the
selection rule (pure), the evidence store's isolation, idempotency and concurrency, budget reservations under
concurrent workers, the objective lifecycle, acceptance integrity, adversarial guards (false verification, stale
decisions and bindings, duplicates, races, a calibration candidate moving its own bar), and a closed-loop live run on
test-double models that really differ. **What they prove:** the machinery works end to end, including all three demos and the
failure paths. **What they do not prove:** the quality of real AI output; that is what the real-model runs are for.
The browser test runs only if Node and Playwright are installed; otherwise it is skipped and says so.
`poc/TEST_REPORT.md` describes every test module.

To check a real model from the command line: `python3 poc/desktop.py --check-model <model>` (a model on this
computer), or `python3 poc/live_check.py` (the model your environment names, with a hard spend cap).

## Build the desktop app

```
python3 desktop/build.py --target linux-x64      # or windows-x64, macos-arm64
```

Details in `desktop/README.md`. The version number is in `desktop/VERSION`.

## GitHub (automatic runs)

**Why they start only when asked:** the repository is private, so GitHub gives 2,000 free machine minutes a month
(Windows counts double, macOS ten times).

| Workflow | Runs when | What it proves |
| --- | --- | --- |
| `cynqra-desktop` | Pushes to `main`: tests only. Add `[build]` to the commit message, or use **Run workflow**, to build and install on all three systems. `[e2e]` adds a small real-model project; `[release]` publishes the installers. | The tests pass; the app builds and installs everywhere |
| `cynqra-workforce` | `[workforce]` in a `main` commit message, or **Run workflow** (choose `local`, `hf` or `both`) | **The Bluedip idea, run by real AI models**, nothing scripted: the test of whether real models can do what the demo shows. `hf` uses the newest Hugging Face models; `local` uses three open models on a machine and is slow for a full company. |
| `cynqra-model-race` | `[race]` in a `main` commit message | Which laptop model is fastest without losing quality |
| `cynqra-model-scan` | When its workflow file changes on `main` | Which open models Hugging Face offers |
| `cynqra-hosted-intelligence` | **Run workflow** only: the providers (NVIDIA, Groq and Mistral by default, joined with `+`; Google Gemini when asked for; Claude only when asked for), how many models, and optionally an objective, whether to carry it to delivery, a time limit, the providers' price (`0,0` for free tiers; empty: list prices, or the worst-case price for an unlisted model) and a budget | Discovery and qualification of hosted models from `GEMINI_API_KEY` / `NVIDIA_API_KEY` / `GROQ_API_KEY` / `MISTRAL_API_KEY` (Groq and Mistral free tiers are paced below their stated per-minute limits) (and, when asked for, the Claude key: secret `ANTHROPIC_API_KEY`, else `Claude_key`, with `anthropic_workspace_id` for a key not scoped to one workspace), every model each key can reach listed and a bounded, provider-fair set examined. With an objective, it runs through the objective intelligence loop to its first bindings (requirements, workforce, plan, calibration, a decision per work item) or, with `to_delivery`, on to delivery, an examination founder approving recommendations and refusing the budget breaker and account problems. The job log and the evidence artifact carry a selection report: each work item's choice beside what the global prior alone would have chosen from the same snapshot, the verified outcomes, and calibration's head-to-head. It shows what those models did on that objective in that run, nothing more. `objective_set: p1-validation` runs three materially different objectives (location tracking, a multi-tenant SaaS, a research analysis) one after another against the same Intelligence Layer and adds a comparison of each objective's own choices by kind of work, never a ranking; `max_minutes` and `budget_usd` then apply to each. While it runs, the job log shows each objective run's events as they are saved (`live #<seq> <event> <subject> …`: every decision proposed and committed, binding, stand-in, reroute, rework, verification and founder decision), read only from the run's store after each write commits, so nothing appears that did not happen; selection, reselection and reroute lines carry the persisted decision (its id, work item, worker, evidence version, candidates, eligible and excluded, selection, mode, risk tier, policy, ranking and reason), and key-shaped strings are redacted. The same lines are rebuilt from a finished run with `cd poc && python3 -m cynqra.live_events <run folder>`. Watch it on the run's job page, step "Discover and examine candidates". The job ends by auditing its own data root (`cynqra.run_audit`, below). |
| `cynqra-run-audit` | **Run workflow** only, with the run ID of a finished `cynqra-hosted-intelligence` run | Every control of the P1 completion mandate (sections 3 to 7 and 10) read back from what that run persisted: identity, lifecycle, candidates and their qualification, calibration on the objective's own work, every SelectionDecision (fields, immutability, replay from its snapshot, the prior's choice), the work, independent verification, provenance and attribution of every evidence record, reselection and replacement, version isolation, worker identity, budget reservations, production verification, the founder-visible events (owed, present, and none reporting what did not happen), the event chain, discovery, Objective A/B isolation, and a scan proving the job's keys appear in no persisted file. A control the run never reached is reported as not exercised, never as passed. The artifact is downloaded inside Actions; the verdicts and tables are in the job log and kept as an artifact. Locally: `cd poc && python3 -m cynqra.run_audit <data root> [--json out.json] [--secret-env NAME ...]`. |
| `cynqra-spikes`, `cynqra-hf` | `[spikes]`, `[hf]` in a `main` commit message | Earlier experiments, kept for reference (code in `archive/02_harness`) |

**Secret:** `HF_TOKEN` (Settings → Secrets and variables → Actions) lets the Hugging Face runs call models. It needs
only the "Make calls to Inference Providers" permission.

## Branches

`main` is the source-of-truth branch. Historical feature branches may remain for audit context, but active workflows run from `main`.
