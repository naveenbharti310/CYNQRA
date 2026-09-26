# Building the Cynqra desktop app

`build.py` turns `poc/` into an installable app for one platform. GitHub Actions runs it on each
platform (`.github/workflows/cynqra-desktop.yml`); you can also run it on a machine of that platform:

    python desktop/build.py --target windows-x64    # Windows, needs Inno Setup 6 (iscc)
    python desktop/build.py --target macos-arm64    # macOS on Apple silicon
    python desktop/build.py --target linux-x64      # Linux

Output: `dist/Cynqra-Setup-<v>-windows-x64.exe`, `dist/Cynqra-<v>-macos-arm64.dmg`,
`dist/Cynqra-<v>-linux-x64.tar.gz`, each with a `.sha256`. The version is in `VERSION`.

## What is inside

| Part | Source | Pinned |
| --- | --- | --- |
| Python 3.12 (relocatable, stripped; Tk and IDLE removed) | python-build-standalone | `PBS_TAG`, checked against its `SHA256SUMS` |
| `llama-server`: CPU and Vulkan builds (Windows, Linux), Metal build (macOS) | llama.cpp releases | `LLAMA_TAG`, checked against GitHub's published SHA-256 |
| Visual C++ runtime DLLs that llama-server imports (Windows) | the build machine's System32 | found by reading llama-server's PE import table |
| pywebview, for a native window (macOS only); certifi, a fallback for HTTPS certificates | PyPI | `PYWEBVIEW`, `CERTIFI` |
| The app: `poc/desktop.py`, `poc/cynqra/`, `poc/ui/`, `poc/scenarios/`, `poc/live_check.py` | this repository | precompiled |

Layout: `python/`, `llama/<cpu|vulkan|metal>/`, `app/`. On Windows the Start menu shortcut runs
`python\pythonw.exe -X utf8 app\desktop.py`; on macOS `Cynqra.app/Contents/MacOS/Cynqra` is a
launcher script and everything else is in `Contents/Resources` (ad-hoc signed: every Mach-O file,
then the bundle); on Linux `cynqra` is the launcher and `install.sh` adds the menu entry.

The window: Microsoft Edge in app mode on Windows (every Windows 10 and 11 has it), pywebview
(WebKit) on macOS, Chrome or Chromium in app mode on Linux. The app serves its UI and API on
127.0.0.1 only, starts `llama-server` on another 127.0.0.1 port, and stops both when the window
closes or Quit is chosen.

Acceleration: macOS uses the Metal build with `-ngl auto` (llama.cpp fits the layers to memory).
Windows and Linux ship a CPU build and a Vulkan build; on Automatic the app asks the Vulkan build
for its devices (`--list-devices`) and uses it with `-ngl auto` when there is a discrete NVIDIA, AMD
or Intel Arc card with 6 GB or more. Every start that fails falls back to the next option, ending
with the processor alone.

## The models

`poc/cynqra/runtime.py` holds the catalog: each model names the exact GGUF file at its publisher
on Hugging Face and mirrors of the same quantization. Size and SHA-256 are read from Hugging Face
at download time and checked. `desktop.py --selftest --online` confirms every file is still there
at the expected size; the workflow runs it on every build.

## Icons

`make_icon.py` draws the icon with the standard library and writes `icon/cynqra.png`, `.ico`,
`.icns` and `poc/ui/icon.png`.

## Updating llama.cpp or Python

Change `LLAMA_TAG` or `PBS_TAG`/`PY_VERSION` in `build.py` and push. The workflow downloads,
verifies, installs and runs a real model on all three platforms, so a release that breaks
anything fails there, not on a teammate's laptop.
