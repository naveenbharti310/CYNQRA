Cynqra as a desktop app: a CTO, a PM and two engineers plan, code, test, fix and deploy a working
web app on your laptop, powered by an open-weight model running on the laptop itself (llama.cpp).
No account, no API key; after the one-time model download nothing leaves the machine.

**Install**

- **Windows 10/11:** run `Cynqra-Setup-…-windows-x64.exe`. SmartScreen: *More info*, then *Run anyway* (not code-signed).
- **Mac (Apple silicon):** open `Cynqra-…-macos-arm64.dmg`, drag Cynqra to Applications. First open: System Settings > Privacy & Security > *Open Anyway* (not notarized).
- **Linux:** `tar xzf Cynqra-…-linux-x64.tar.gz && ./Cynqra/install.sh`

On first launch, pick the recommended model: **Qwen3.6 35B-A3B**, the strongest open coding model that
fits a laptop, in the size your memory holds (20.6 GB for 32 GB and up, 12.3 GB for 24 GB, 11.4 GB for
16 GB). The app downloads it once and runs it locally, on the GPU when there is a suitable one.

The full guide, with what to test and troubleshooting: [docs/4_RUN_AND_TEST.md](https://github.com/naveenbharti310/CYNQRA/blob/main/docs/4_RUN_AND_TEST.md)

**Measured on GitHub's machines** (16 GB, 4 processor threads, no GPU), a whole Cynqra run for a bakery
order app, from the founder's sentence to a deployed, healthy product whose tests pass:
- gpt-oss 20B on 0.1.1: passed in **50 minutes**, 10 model calls, every task verified at its first check.
- Qwen3.6 35B-A3B 2-bit on 0.1.0: passed in 4 hours on Windows, most of it one task going round in
  circles; 0.1.1 fixed that loop. On 0.1.1 its code replies then outgrew the 2-bit model's output limit
  and were thrown away whole; 0.1.2 keeps the finished files and asks only for the rest.
A current laptop is two to four times faster than these machines, and a Mac or a graphics card faster still.

**0.1.2:** an engineer's reply carries only the files it writes or changes, and the other files are kept,
so fixing one test no longer means rewriting every file; a reply cut off at the model's output limit keeps
the files it finished and asks for the rest.

**0.1.1:** the verifier reads test results even when the app under test logs requests, and names the test
that hung or crashed; a rework that repeats an earlier attempt exactly is answered with some temperature
instead of the same failing code; engineers are told how to test a server without hanging; an objective
field the model leaves empty is inferred in one short follow-up for the founder to check.

Every file here was built by GitHub Actions from the `cynqra` branch, installed on a fresh Windows,
macOS and Linux machine, self-tested, and run with a real open model before it was published.
