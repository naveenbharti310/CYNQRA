**Describe the company you want to build. Cynqra assembles the expert team it needs, checks every
piece of their work, and asks you only what a CEO should decide.**

**What this is:** Cynqra as a desktop app, a proof of concept. **Why try it:** to see an expert team
built from an idea, working like a real company, with every piece of work checked. **How:**

1. **Start with the free demo.** A founder describes Bluedip, an app that predicts a restaurant's
   footfall and revenue hour by hour and estimates what an offer will really do. Cynqra builds the team
   the idea needs (a Data Scientist, a Restaurant Revenue Management Specialist, a CFO, a Market
   Analyst, a Legal and Compliance Advisor and more); the checks catch two mistakes; the app goes live
   and the founder receives the Company Pack. Nothing to download or connect for the demo.
2. **Then run your own idea** with an online AI provider, or with an open model on this computer: no
   account, no key, and after the one-time model download nothing leaves the machine.

For a model on this computer, pick the recommended one: **Qwen3.6 35B-A3B**, the strongest open coding model that
fits a laptop, in the size your memory holds (20.6 GB for 32 GB and up, 12.3 GB for 24 GB, 11.4 GB for
16 GB). The app downloads it once and runs it locally, on the GPU when there is a suitable one.

The full guide, with what to test and troubleshooting: [docs/4_RUN_AND_TEST.md](https://github.com/naveenbharti310/CYNQRA/blob/main/docs/4_RUN_AND_TEST.md)

**Measured on GitHub's machines** (16 GB, 4 processor threads, no GPU), with an earlier, software-only
team (a CTO, a PM and two engineers) building a small order-tracking app, from the founder's sentence
to a deployed, healthy product whose tests pass:
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
