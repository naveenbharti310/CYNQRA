# 3. Status and roadmap

Last updated: 30 September 2026.

**What** this covers: what works today, what is proven, and what comes next. **Why** it matters: the vision is only
as good as the proof behind it. **How** to read it: the status table first, then what real AI models have done so
far, then the next steps in order, each with its reason.

## What works today

**Cynqra is a working proof of concept. It is not a product yet.** The whole flow exists and is tested. It has not yet
been proven end to end on strong real AI models in its current form.

| Area | Status |
| --- | --- |
| The seven-step journey: describe the idea, approve the plan, define yourself, approve the team and budget, watch it being built, receive the product, audit and refine | ✅ Built. Every screen follows it. 313 automated tests pass. |
| Define yourself: the organisation is constructed again around the founder's background (live mode); an area the founder leads gets no AI cofounder and reports to the founder | ✅ Built and tested with stand-in AIs; not yet tried on a real model. In a demo the founder and the organisation are part of the script. A domain expert still gets a Specialist for their own field when the platform's coverage rule needs one. |
| Audit and rework: every requirement of the objective checked against the delivered product; a rework plans, builds and releases only what should change | ✅ Built and tested. |
| Demo mode (scripted words; real code, models, tests and going live) | ✅ Works end to end. It opens on Bluedip: three cofounders and the ten team members they chose (fourteen seats proposed and one cut by the independent challenge), seventeen tasks, three mistakes caught by the checks, one piece of work sent back by a cofounder, two questions settled inside the team, the founder asked twice while it is built (a rule on money, going live; the CTO settled the merge), then the audit (15 of 15 requirements met) and acceptance. Two smaller demos are in the list. |
| Cofounders proposed from the idea, each choosing its own team, Specialists named from it | ✅ Built and tested. |
| Every seat earns its place: one owner per requirement, who asked for each seat, an independent challenge, the lean team beside the recommended one, members with no work removed | ✅ Built and tested. Asks the founder nothing more. |
| The guesses an idea rests on, riskiest first and tested early; measures of success | ✅ Built and tested. Kept in the record; the screens leave them out, since Cynqra is responsible for the product, not the business. |
| The financial model's numbers recomputed by the platform | ✅ Built and tested. |
| Decisions that can be undone settled by the accountable cofounder; the founder told | ✅ Built and tested. |
| After launch: live checks, the next cycle on the live product, the foundations checklist, the track record across projects | ✅ Built and tested. The demos script a second cycle for the candidate tracker only. |
| Cofounders run their areas: hand out, answer doubts, review before work counts, endorse proposals to the founder | ✅ Built and tested. |
| Team works in parallel | ✅ Built and tested. |
| Best AI per member, measured | ✅ Built and tested. |
| When a member stops: finds out why first; replaces only an AI that cannot do the work, and tells the founder the cost | ✅ Built and tested. |
| Prediction models checked on data they have not seen | ✅ Built and tested (a backtest against last week's numbers). |
| Connections to OpenAI-compatible, Anthropic, local models, Hugging Face | ✅ Built. Bedrock planned. |
| Installable desktop app (Windows, macOS, Linux) | ✅ Builds and installs; version 0.1.2. |
| **A full project on strong real models, current design** | ❌ **Not yet done.** See "Real-model results". |
| Web research and calculation tools for the experts | ❌ Not built. |
| Checks of document substance | Partly: the financial model's numbers are recomputed, and foundation documents must mark assumptions and list sources. Facts are not yet checked against their sources. |
| Hosted web product (accounts, workspaces, billing) | ❌ Not built. Today it runs on one computer. |

**What the automated tests prove:** the machinery works. They use stand-in AIs (test doubles) and the demo's
prepared script, so they do not prove the quality of real AI output. `poc/TEST_REPORT.md` lists every test.

## Real-model results so far

| Date | What ran | Result |
| --- | --- | --- |
| 27 Sep | Earlier design, one Windows machine, open model (Qwen3.6 35B, 2-bit), a small order-tracking app | **Passed:** built, tested, deployed, accepted. 20 AI calls, 3 h 15 min, on a slow CPU. |
| 27 Sep | Same, two Linux machines | Ran out of time (340 min) while reworking the web app. |
| 27 Sep | Current design, three open models on a CPU | Team proposed and approved; stopped by a bug in the test script (fixed). |
| 27 Sep | Hugging Face: GLM-4.7, Kimi K2.5, Qwen3.5 | Probes: GLM and Kimi wrote working code first time; Qwen failed. Then the account's free credit ran out. |

**Next real run:** the Bluedip idea, on the newest online models through Hugging Face, once the founder has
Hugging Face PRO. Nothing in it is scripted: it is the test of whether real AI models can do what the demo shows.

## What to build next, in order

| # | What | Why this, and why now |
| --- | --- | --- |
| 1 | **The Bluedip run on real models**, then **the exam:** 20 real ideas, run end to end, measuring CEO decisions, time, cost and quality, against a single AI | Proof before more features. Every later change is measured against it. |
| 2 | **Founder conversations:** show 10 to 20 target founders the Bluedip result; ask if they would pay, and how much | Confirms demand, price and the first buyer. |
| 3 | **Speed:** online models by default; smaller tasks; faster rescue when a task fails twice | Real runs took hours. |
| 4 | **Tools for the experts:** web research with sources; a calculator for the CFO; real tool use for building, or hand building to proven coding agents | Experts need current facts; a model's memory goes out of date. |
| 5 | **Checks of substance:** facts against their sources, documents consistent with each other (the financial model's numbers are already recomputed) | Trust is the product. |
| 6 | **Kickoff agreements:** before parallel work starts, the team agrees on how the parts connect and the key facts | Parallel work must fit together. |
| 7 | **Company memory:** a shared knowledge base; a CEO change updates every affected document | The team must stay consistent over time. |
| 8 | **Field playbooks:** what companies in a field usually need, as a starting point the idea adjusts | Better teams, faster. |
| 9 | **CEO experience:** plain decision cards, grouped decisions, phone notifications | Less of the founder's time; a pitch that shows the product. |
| 10 | **Hosted web product:** accounts, separate data per customer, secrets manager, AI included in the price, billing | To sell it. |
| 11 | **Security:** AI-written code run in a sandbox; content from the web or colleagues treated as data to read, with no power to give orders | Before any launch. |

## Known limits

- **Code the AI team writes runs on this computer without a sandbox**, as the same user, when it is tested and put
  live. Keys are kept out of its environment, but it could read files the user can read. Run only ideas you trust
  on a computer that holds nothing sensitive until the sandbox (roadmap 11) is built.
- A release whose code listens on every network address (so anyone on the same network could use it) is refused
  before preview. The check looks for the usual ways of writing that in the code. It can miss an unusual one, so
  the sandbox is still needed.
- Times are recorded in Indian Standard Time.
- The desktop app's model server (llama-server) answers anything on this computer without a password, on a
  random port. A website that found the port could make the model work for it; it cannot read Cynqra's data.
  A per-start password is the fix, once it can be tested on the desktop builds.
- The demo products (Bluedip and the others) have no accounts: anything on this computer can use them while
  they run. They are demonstrations; a product meant for customers needs sign-in, which the team would build.
- The deployed product is a process on this computer; it stops when Cynqra closes and does not start again with it.
- Workers answer in text; they do not yet use tools (search, calculators, file editing).
- One model on a laptop answers one call at a time; laptop models are slow (5 to 10 words a second).
- A cofounder does one thing at a time, like every member: with a large team, its hand-outs and reviews can make the
  others wait. How much this slows a real run is to be measured on real models.
- A cofounder's proposal of its own team is written in that cofounder's role by the AI Cynqra uses for planning;
  each cofounder gets its own AI once the organization is approved.
- The evidence for choosing models is thin (1 to 3 trial tasks per model) until more projects run.
- The desktop app keeps everything on one computer; there is no multi-user version.
- The demo video (`poc/demo/`, recorded 29 September 2026, about 7 minutes 25 seconds) shows the Bluedip demo in demo
  mode; a video of a run on real AI models comes after that run.
- The independent challenge of a team runs on the same AI Cynqra uses for planning, with its own brief to make the
  team smaller; what is cut is decided by the platform's removal test. Running it on a different AI
  when more than one is connected is a next step.
- In the demos, the lean team is shown but cannot be chosen, because each script plans the recommended team; only
  the candidate tracker has a scripted second cycle. In live mode both work for any idea.
- A cycle after launch must ship a code change; a cycle of documents only is not supported yet.
- The business numbers are checked for arithmetic, for sensible ranges (no negative churn, a price above zero) and
  for where each input comes from; whether an assumption is realistic is for the founder and a professional to judge.
- If the founder chooses the lean team in live mode and the plan for it cannot be made, the run stops like any failed
  planning step; going back to the recommended team means starting a new run.
