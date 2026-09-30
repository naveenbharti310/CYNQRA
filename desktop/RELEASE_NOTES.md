**You bring the vision. Cynqra creates the organisation that can build it.**

**What this is:** Cynqra as a desktop app, a proof of concept. **Why try it:** to see an idea become a
working product in seven steps, with the organisation it needs built around you and every piece of work checked.
**How:**

1. **Start with the free demo.** A founder describes Bluedip, an app that predicts a restaurant's
   footfall and revenue hour by hour and estimates what an offer will really do. You approve the plan,
   define yourself, approve the team and budget, watch it being built, open the live app, and audit it
   against the original objective before accepting it. Nothing to download or connect for the demo.
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

**0.2.2 (Windows):** the Intelligence screen.
- **An intelligence inventory**, not a list of model ids: every model your providers offer, with its readable name,
  its publisher (who made it), its access provider (who serves it to you) and its type. Search it ("coding",
  "OCR", "fast", "reasoning", "multimodal") and filter it by access provider, publisher, capability, speed, cost,
  context and input.
- **A detail view for every model:** capabilities, input types, cost on your connection and its list price
  elsewhere, measured speed, context, longest answer, tools, release date, your provider's rate limit, and what
  Cynqra measured when it evaluated it.
- **Everything comes from your providers**, normalized into Cynqra's registry; nothing is a built-in list and no
  model is a default.
- **Plain words:** your key is "Securely stored" and never shown; a connection is "Connected by you".
- This release is built for **Windows only**.

**0.2.1** (built into 0.2.2; never published on its own): Cynqra starts from nothing and chooses nothing for you by name.
- **A first visit is empty.** No project, no idea, no model. Cynqra asks what you want to build, who it is for, the
  result you want and anything it must or must not do, writes the brief from your answers, and asks for a budget.
  The demo is one click away ("Watch a demo instead").
- **Only this year's models.** A connected provider offers only the chat models released in the last 12 months,
  the newest of each family, not its whole catalogue (Google and NVIDIA together listed 111). **Search and choose
  models** shows everything, newest first, with release dates.
- **Cynqra evaluates, then assigns.** Each new model plans a brief and writes code that must pass its tests; each
  seat then goes to the model measured best at that seat's work: planning for a cofounder, code for an engineer.
- **Google's new "AQ." keys** work; **Kimi K3** can be told to think less and answer faster.

**0.2.0:** everything since 0.1.2, in one installer:
- **The seven steps**, from your idea to an audited product you accept, with the organisation built around you
  (you define yourself at step 3) and a real name for every AI team member. A replacement brings a new person, and
  the one before stays in the history with their record.
- **Free online AI works properly:** Google Gemini, NVIDIA Build, Mistral and Z.ai can be connected with their
  free keys. A busy free tier is waited out instead of stopping the work, a platform that refuses Cynqra's JSON
  format is asked in a simpler one, and thinking models get room to answer. The settings for each are in the guide.
- **Every screen redesigned** for phones, tablets and desktops, with errors shown next to the button you pressed.

**0.1.2:** an engineer's reply carries only the files it writes or changes, and the other files are kept,
so fixing one test no longer means rewriting every file; a reply cut off at the model's output limit keeps
the files it finished and asks for the rest.

**0.1.1:** the verifier reads test results even when the app under test logs requests, and names the test
that hung or crashed; a rework that repeats an earlier attempt exactly is answered with some temperature
instead of the same failing code; engineers are told how to test a server without hanging; an objective
field the model leaves empty is inferred in one short follow-up for the founder to check.

Every file here was built by GitHub Actions from the `cynqra` branch, installed on a fresh Windows,
macOS and Linux machine, self-tested, and run with a real open model before it was published.
