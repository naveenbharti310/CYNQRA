# 4. Run and test

**What** this covers: how to run Cynqra, test it and build it, and what each run proves. **Why** it matters: a
claim about Cynqra is only as good as the run behind it, and anyone should be able to repeat it. **How:** everything
runs on Python 3.10 or newer, with the standard library only; nothing to install.

## Run it

| To... | Do this | What it shows |
| --- | --- | --- |
| **Watch the demo** (free, scripted words; real code, models, tests and going live) | `python3 poc/run_poc.py`, choose **Demo**, press **Make it a brief** | The Bluedip project from the founder's words to a live app and the Company Pack. Two smaller demos are in the list. |
| **Run your own idea with an online AI** | Start as above, choose **Live**, click **Connect a provider** (OpenAI-compatible such as Hugging Face or OpenAI, or Anthropic), and name the key's environment variable or paste it into Cynqra's secrets file. Or set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` before starting. | What real AI models do with your idea |
| **Run with a model on your own computer** | Install the desktop app (below) and open **This computer** to download a model. No key needed. | The same, privately, more slowly |
| **Install the desktop app** | Download it from the repository's **Releases** page (Windows, macOS, Linux), or run `python3 poc/desktop.py` | Cynqra in its own window |

Never paste a key into a chat or a document. Keys live only in environment variables, Cynqra's secrets file
(readable only by you), or GitHub secrets.

## Test it

```
cd poc
python3 -m unittest discover -s tests -t tests
```

About 5 minutes, 264 tests. **What they prove:** the machinery works end to end, including all three demos and the
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
| `cynqra-desktop` | Every push to `cynqra`: tests only. Add `[build]` to the commit message, or use **Run workflow**, to build and install on all three systems. `[e2e]` adds a small real-model project; `[release]` publishes the installers. | The tests pass; the app builds and installs everywhere |
| `cynqra-workforce` | `[workforce]` in the commit message, or **Run workflow** (choose `local`, `hf` or `both`) | **The Bluedip idea, run by real AI models**, nothing scripted: the test of whether real models can do what the demo shows. `hf` uses the newest Hugging Face models; `local` uses three open models on a machine and is slow for a full company. |
| `cynqra-model-race` | `[race]` | Which laptop model is fastest without losing quality |
| `cynqra-model-scan` | When its file changes | Which open models Hugging Face offers |
| `cynqra-spikes`, `cynqra-hf` | `[spikes]`, `[hf]` | Earlier experiments, kept for reference (code in `archive/02_harness`) |

**Secret:** `HF_TOKEN` (Settings → Secrets and variables → Actions) lets the Hugging Face runs call models. It needs
only the "Make calls to Inference Providers" permission.

## Branches

`main` and `cynqra` hold the same code. Work is pushed to both; the workflows run on `cynqra`.
