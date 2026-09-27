# 3. Status and roadmap

Last updated: 27 September 2026.

## Where things stand

**Cynqra is a working proof of concept, not yet a product.** The whole flow exists and is tested. It has not yet
been proven end to end on strong real AI models in its current form.

| Area | Status |
| --- | --- |
| The full flow (idea → team → plan → parallel work → checks → delivery) | ✅ Built. 237 automated tests pass. |
| Demo mode (scripted words; real code, tests and deploy) | ✅ Works end to end, two scenarios. |
| Team built from the idea, with Specialists named from it | ✅ Built and tested. |
| Team works in parallel, hands over, asks each other | ✅ Built and tested. |
| Best AI per member, measured; swapped when it fails | ✅ Built and tested. |
| Connections to OpenAI-compatible, Anthropic, local models, Hugging Face | ✅ Built. Bedrock planned. |
| Installable desktop app (Windows, macOS, Linux) | ✅ Builds and installs; version 0.1.2. |
| **A full project on strong real models, current design** | ❌ **Not yet done.** See "Real-model results". |
| Web research and calculation tools for the experts | ❌ Not built. |
| Checks of document substance (facts, numbers, consistency) | ❌ Not built; documents are checked for structure and trust sections only. |
| Hosted web product (accounts, workspaces, billing) | ❌ Not built. Today it runs on one computer. |

**What the automated tests prove:** the machinery works. They use stand-in AIs (test doubles), so they do not prove
the quality of real AI output. `poc/TEST_REPORT.md` lists every test.

## Real-model results so far

| Date | What ran | Result |
| --- | --- | --- |
| 27 Sep | Earlier design, one Windows machine, open model (Qwen3.6 35B, 2-bit) | **Passed:** built, tested, deployed, accepted. 20 AI calls, 3 h 15 min, on a slow CPU. |
| 27 Sep | Same, two Linux machines | Ran out of time (340 min) while reworking the web app. |
| 27 Sep | Current design, three open models on a CPU | Team proposed and approved; stopped by a bug in the test script (fixed). |
| 27 Sep | Hugging Face: GLM-4.7, Kimi K2.5, Qwen3.5 | Probes: GLM and Kimi wrote working code first time; Qwen failed. Then the account's free credit ran out. |

**Waiting on:** Hugging Face PRO (the founder is buying it), to run a full project on the newest online models.

## What to build next, in order

| # | What | Why |
| --- | --- | --- |
| 1 | **The exam:** 20 real ideas, run end to end. Measure CEO decisions, time, cost and quality, against a single AI. | Proof before more features. Every later change is measured against it. |
| 2 | **Founder conversations:** show 10–20 target founders a result; ask if they would pay. | Confirms demand and price. |
| 3 | **Speed:** online models by default; smaller tasks; faster rescue when a task fails twice. | Real runs took hours. |
| 4 | **Tools for the experts:** web research with sources; a calculator for the CFO; real tool use for building, or hand building to proven coding agents. | Experts need current facts, not memory. |
| 5 | **Checks of substance:** facts against sources, numbers recomputed, documents consistent with each other, an independent reviewer. | Trust is the product. |
| 6 | **Kickoff agreements:** before parallel work starts, the team agrees on how the parts connect and the key facts. | Parallel work must fit together. |
| 7 | **Company memory:** a shared knowledge base; a CEO change updates every affected document. | The team must stay consistent over time. |
| 8 | **Field playbooks:** what companies in a field usually need, as a starting point the idea adjusts. | Better teams, faster. |
| 9 | **CEO experience:** plain decision cards, grouped decisions, phone notifications. | Less of the CEO's time. |
| 10 | **Hosted web product:** accounts, separate data per customer, secrets manager, AI included in the price, billing. | To sell it. |
| 11 | **Security:** AI-written code run in a sandbox; content from the web or colleagues treated as data, never as instructions. | Before any launch. |

## Known limits

- Workers answer in text; they do not yet use tools (search, calculators, file editing).
- One model on a laptop answers one call at a time; laptop models are slow (5 to 10 words a second).
- The evidence for choosing models is thin (1 to 3 trial tasks per model) until more projects run.
- The desktop app keeps everything on one computer; there is no multi-user version.
