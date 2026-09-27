# 4. Run and test

Everything runs on Python 3.10 or newer, with the standard library only. Nothing to install.

## Run it

| To... | Do this |
| --- | --- |
| **Watch a demo** (free, scripted words, real code and deploy) | `python3 poc/run_poc.py`, then choose **Demo** |
| **Run a real project with an online AI** | Start as above, choose **Live**, click **Connect a provider** (OpenAI-compatible such as Hugging Face or OpenAI, or Anthropic), name the key's environment variable or paste it into Cynqra's secrets file. Or set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` before starting. |
| **Run with a model on your own computer** | Install the desktop app (below) and open **This computer** to download a model. No key needed. |
| **Install the desktop app** | Download it from the repository's **Releases** page (Windows, macOS, Linux), or run `python3 poc/desktop.py` |

Never paste a key into a chat or a document. Keys live only in environment variables, Cynqra's secrets file
(readable only by you), or GitHub secrets.

## Test it

```
cd poc
python3 -m unittest discover -s tests -t tests
```

About 4 minutes, 240 tests. The browser test runs only if Node and Playwright are installed; otherwise it is skipped
and says so. `poc/TEST_REPORT.md` describes every test module.

To check a real model from the command line: `python3 poc/desktop.py --check-model <model>` (a model on this
computer), or `python3 poc/live_check.py` (the model your environment names, with a hard spend cap).

## Build the desktop app

```
python3 desktop/build.py --target linux-x64      # or windows-x64, macos-arm64
```

Details in `desktop/README.md`. The version number is in `desktop/VERSION`.

## GitHub (automatic runs)

The repository is **private**, so GitHub gives 2,000 free machine minutes a month (Windows counts double, macOS ten
times). Heavy runs therefore start only when asked.

| Workflow | Runs when | What it does |
| --- | --- | --- |
| `cynqra-desktop` | Every push to `cynqra`: tests only. Add `[build]` to the commit message, or use **Run workflow**, to build and install on all three systems. `[e2e]` adds a full real-model project; `[release]` publishes the installers. | Tests, builds, install checks |
| `cynqra-workforce` | `[workforce]` in the commit message, or **Run workflow** (choose `local`, `hf` or `both`) | A full project on real models: three open models on a machine, or the newest Hugging Face models |
| `cynqra-model-race` | `[race]` | Which laptop model is fastest without losing quality |
| `cynqra-model-scan` | When its file changes | Lists open models on Hugging Face |
| `cynqra-spikes`, `cynqra-hf` | `[spikes]`, `[hf]` | Earlier experiments, kept for reference (code in `archive/02_harness`) |

**Secret:** `HF_TOKEN` (Settings → Secrets and variables → Actions) lets the Hugging Face runs call models. It needs
only the "Make calls to Inference Providers" permission.

## Branches

`main` and `cynqra` hold the same code. Work is pushed to both; the workflows run on `cynqra`.
