Cynqra as a desktop app: a CTO, a PM and two engineers plan, code, test, fix and deploy a working
web app on your laptop, powered by an open-weight model running on the laptop itself (llama.cpp).
No account, no API key; after the one-time model download nothing leaves the machine.

**Install**

- **Windows 10/11:** run `Cynqra-Setup-…-windows-x64.exe`. SmartScreen: *More info*, then *Run anyway* (not code-signed).
- **Mac (Apple silicon):** open `Cynqra-…-macos-arm64.dmg`, drag Cynqra to Applications. First open: System Settings > Privacy & Security > *Open Anyway* (not notarized).
- **Linux:** `tar xzf Cynqra-…-linux-x64.tar.gz && ./Cynqra/install.sh`

On first launch, pick the recommended model: **Qwen3.6 35B-A3B** (20.6 GB) with 32 GB of memory or
more, **Qwen3.5 9B** (5.3 GB) with 16 to 24 GB. The app downloads it once and runs it locally.

The full guide, with what to test and troubleshooting: [CYNQRA_DESKTOP.md](https://github.com/naveenbharti310/Passway/blob/cynqra/CYNQRA_DESKTOP.md)

Every file here was built by GitHub Actions from the `cynqra` branch, installed on a fresh Windows,
macOS and Linux machine, self-tested, and run with a real open model before it was published.
