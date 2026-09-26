# Cynqra desktop app

Cynqra as an app on your laptop. Download it, install it, open it. A CTO, a PM and two engineers
plan, write real code, run real tests, fix their own failures, merge and deploy a working web app
on your laptop. You make the founder's decisions in the app. The intelligence is an open-weight
model that runs on your laptop: no account, no API key, and after the first download nothing
leaves the machine.

**Download:** https://github.com/naveenbharti310/Passway/releases (the newest `cynqra-v…` release)

| Your laptop | File | Size |
| --- | --- | --- |
| Windows 10 or 11, 64-bit | `Cynqra-Setup-<version>-windows-x64.exe` | about 90 MB |
| Mac with Apple silicon (M1 to M4), macOS 12 or newer | `Cynqra-<version>-macos-arm64.dmg` | about 60 MB |
| Linux, 64-bit (Ubuntu 22.04 or newer, or similar) | `Cynqra-<version>-linux-x64.tar.gz` | about 80 MB |

Each file has a `.sha256` next to it if you want to check the download.

## 1. Install

**Windows.** Run the installer. It installs for you only, needs no administrator rights, and adds
Cynqra to the Start menu (and, if you tick it, the desktop). This proof of concept is not
code-signed, so Windows SmartScreen says "Windows protected your PC": click **More info**, then
**Run anyway**.

**Mac.** Open the `.dmg` and drag Cynqra into Applications. The app is not notarized by Apple, so
the first time macOS refuses to open it. Open **System Settings > Privacy & Security**, scroll
down to "Cynqra was blocked", click **Open Anyway**, and confirm. After that it opens normally.
(Or, in Terminal: `xattr -dr com.apple.quarantine /Applications/Cynqra.app`.)

**Linux.** `tar xzf Cynqra-*-linux-x64.tar.gz && ./Cynqra/install.sh`. Cynqra is then in your
applications menu, and `~/.local/bin/cynqra` starts it. The window opens in Chrome, Chromium,
Edge or Brave if one is installed, otherwise in your default browser.

## 2. First launch: choose the model

Cynqra shows the models it can run, with the one for your laptop's memory marked
**Recommended**. Click it. The app downloads the model once from its publisher on Hugging Face
(it resumes if interrupted and checks the file's SHA-256), starts it with llama.cpp, and goes to
the first screen.

| Model | Download | For | Why |
| --- | --- | --- | --- |
| **Qwen3.6 35B-A3B** | 20.6 GB | 32 GB of memory or more | The strongest open coding model that fits a laptop. Only 3B of its 35B parameters work on each token, so it is fast even without a GPU |
| **Qwen3.5 9B** | 5.3 GB | 16 to 24 GB | Follows Cynqra's formats well and leaves room in 16 GB |
| Qwen3.6 27B | 15.7 GB | 32 GB Mac, or a 24 GB GPU | Stronger on hard code, three to four times slower |
| Qwen3.5 4B | 2.6 GB | Any | Quick check that everything works; its code fails checks more often |

The choice comes from Cynqra's September 2026 research (`poc/research/`). Macs use their GPU
through Metal automatically. On Windows and Linux the model runs on the processor; if you have an
NVIDIA or AMD card with 8 GB or more, set **Graphics card** to On in the Model screen (Cynqra falls
back to the processor by itself if the card cannot hold the model).

## 3. Use it

1. **Objective.** Say what you want built, in a sentence or two. Cynqra's model structures it into
   seven fields; check the ones marked Inferred, edit anything, set the budget, and confirm.
2. **Organization and plan.** The CTO proposes the plan for the fixed four-worker organization.
   Approve it, or ask for another.
3. **The organization works.** The Work view shows each task moving, the protocol messages between
   workers, and, at the top, what the model is doing right now (reading a prompt, or how many tokens
   it has written). Engineers run their own tests and fix failures before handing over; the
   Verification Service runs every test again.
4. **Your decisions.** When something needs you (a product rule, the merge, the production deploy,
   accepting delivery), a card appears under Decisions: approve, reject with a reason, or edit.
5. **The product is live.** Delivery shows its address on your laptop. Open it and use it. Download
   the export bundle for the code, the documents, the decisions and the event log.

**Model** (bottom left) switches or stops the model. **Quit** stops the model and the deployed
product. Closing the window does the same. **New run** archives the run and starts again.

How long a run takes depends on the laptop. On a processor alone a step takes minutes, and a whole
run of one to two dozen model calls takes from under an hour (35B-A3B on a fast machine, or any Mac)
to a few hours (9B on a 16 GB laptop without a GPU). The measured numbers from GitHub's machines are
in the release notes.

## Where things are

| | Windows | Mac | Linux |
| --- | --- | --- | --- |
| The app | `%LOCALAPPDATA%\Programs\Cynqra` | `/Applications/Cynqra.app` | `~/.local/share/cynqra-app` |
| Models, runs, reports, logs | `%LOCALAPPDATA%\Cynqra` | `~/Library/Application Support/Cynqra` | `~/.local/share/cynqra` |

Inside the data folder: `runtime/models/` the downloaded model, `runs/` every run (the current one
and archived ones, each with its SQLite event log and the product's code), `reports/`,
`runtime/llama-server.log` and `app.log`.

## Check an installation

The app has three built-in checks. Run them from a terminal with the app's own Python:

| | Windows (PowerShell) | Mac | Linux |
| --- | --- | --- | --- |
| Start command, `$C` | `& "$env:LOCALAPPDATA\Programs\Cynqra\python\python.exe" "$env:LOCALAPPDATA\Programs\Cynqra\app\desktop.py"` | `/Applications/Cynqra.app/Contents/MacOS/Cynqra` | `~/.local/bin/cynqra` |

- `$C --selftest --online`: the bundled Python and llama-server run, the app serves its page, the
  engine runs tests and deploys on this machine, and every model file is where the app expects it.
- `$C --check-model qwen3.5-9b`: the model downloads and starts, structures an objective, and writes
  a small module that must pass its own tests (fixing it for up to three rounds).
- `$C --e2e qwen3.5-9b "your objective"`: a whole unattended run through the app's own API,
  approving every decision; it writes a report with every model call's real token counts and time.

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| The model did not start | The Model screen shows llama-server's own message. Usually memory: close other apps, or pick a smaller model |
| Download stops | Click the model again: it resumes where it stopped |
| Very slow, fans loud | Plug in to power; close the browser and IDE; on Windows or Linux with a GPU, turn on Graphics card |
| A step stopped with a model error | Click **Try the same step again**. Nothing was lost |
| The window does not open (Linux) | Install Chrome or Chromium, or open the address printed by `~/.local/bin/cynqra --headless` |

## Uninstall

Windows: Settings > Apps > Cynqra > Uninstall; it asks whether to delete the models and runs too.
Mac: move Cynqra to the Bin; delete `~/Library/Application Support/Cynqra` for the models and runs.
Linux: delete `~/.local/share/cynqra-app`, `~/.local/share/cynqra`, `~/.local/bin/cynqra` and
`~/.local/share/applications/cynqra.desktop`.

## What is real, and the limits

- The model is an open-weight model running on your laptop in llama.cpp. Its words are not scripted.
- The engineers' code is written to disk, their tests run in a subprocess, verification runs every
  test again, and the product is started as a real process with health and smoke checks.
- Policy, budgets, the founder's decisions, the append-only event log and the export are the same
  engine as in the rest of the proof of concept.

Limits: the workers' code runs in a folder with a cleaned environment, not a container; the
deployment target is your laptop; one run at a time; the installers are not code-signed.

## How it is built and tested

`desktop/build.py` assembles each installer from pinned, checksummed parts: CPython 3.12 from
python-build-standalone, llama.cpp's `llama-server` release build (b11201), and the app from `poc/`.
GitHub Actions (`.github/workflows/cynqra-desktop.yml`) builds all three on GitHub's Windows, macOS
and Linux machines, installs each one the way a user would, runs the self-test, opens the window,
and has a real model do Cynqra's work. With `[e2e]` in the commit message it also runs a whole
Cynqra journey with Qwen3.5 9B on Windows and Linux. See `desktop/README.md`.
