# Non-Qwen, non-gpt-oss open-weight model families for local laptop agentic coding (as of 26 Sep 2026)

How this was researched (read this first): the session's egress proxy blocked huggingface.co, ollama.com, mistral.ai, blog.google, ai.google.dev, arxiv.org, aider.chat, artificialanalysis.ai, reddit.com, swebench.com, z.ai, ibm.com, nvidia.com and similar sites (policy 403 / EGRESS_BLOCKED). Only GitHub was reachable. So:
- **Primary-source numbers** come from vendor GitHub READMEs and figures (Z.ai GLM, NVIDIA Nemotron, ByteDance Seed-OSS, IBM Granite 4.0/4.1/4.2, Moonshot Kimi-Linear, Meta llama-models, Microsoft PhiCookBook, Ollama), the Aider leaderboard's raw YAML on GitHub, and Ollama and llama.cpp GitHub issues and PRs.
- **Everything else** (Hugging Face model cards, Ollama tag sizes, Gemma 4 and Devstral numbers) comes from web-search result summaries. These point to the URLs cited, but I could not open those pages. Treat them as "reported, not directly verified" and re-check the flagged numbers on the model cards before the numbers are used in a decision.

## Q1. Model inventory: release date, total/active params, context, license, thinking toggle, laptop fit at 4-bit

### Takeaway
As of Sep 2026 the laptop-relevant (≤~35B, ≤~24 GB at Q4) non-Qwen, non-gpt-oss contenders for agentic coding are:
- **GLM-4.7-Flash**: 30B-A3B, MIT, Jan 2026.
- **Devstral Small 2**: 24B dense, Apache 2.0, Dec 2025.
- **Gemma 4**: 26B-A4B MoE, 31B dense and 12B, Apache 2.0, Apr and Jun 2026.
- **Meta Muse Glimmer**: 30B dense, Apache 2.0, 10 Aug 2026.
- **NVIDIA Nemotron 3 Nano / Nemotron-Cascade 2 / Nemotron 3.5 Lightning**: all 30B-A3B, NVIDIA open licenses, Dec 2025, Mar 2026 and Aug 2026.
- **IBM Granite 4.2**: 3B/8B/30B dense, Apache 2.0, 25 Aug 2026.
- **ByteDance Seed-OSS-36B**: Apache 2.0, Aug 2025.

Other models are superseded (Gemma 3/3n, Llama 3.x, Phi-4, Mistral Small 3.x, DeepSeek R1 distills), or too big for a 64 GB laptop (GLM-4.5-Air 106B, Mistral Small 4 119B, Llama 4 Scout 109B, GLM-5.x, DeepSeek V4, Kimi K2/K3, Nemotron 3 Super/Ultra).

### Cited Findings

**Mistral**
- Devstral 2 family released 9 Dec 2025, in two sizes: Devstral 2 (123B) and Devstral Small 2 (24B) — [Mistral announcement tweet, 9 Dec 2025](https://x.com/MistralAI/status/1998407335308358028); [Mistral news](https://mistral.ai/news/devstral-2-vibe-cli/)
  - Licenses: "Devstral 2 (123B) under a modified MIT license, and Devstral Small (24B) under Apache 2.0" — [MistralAI on X](https://x.com/MistralAI/status/1998407335308358028)
  - Reported restriction on the 123B's modified MIT license: companies with more than $20M in monthly revenue need a separate commercial license — [VentureBeat via search summary](https://venturebeat.com/ai/mistral-launches-powerful-devstral-2-coding-model-including-open-source)
  - Both sizes have a 256K context window. Devstral Small 2 is a 24B dense model that accepts image input and runs on consumer hardware (RTX 4090 or a 32 GB Mac) — [DigitalOcean](https://www.digitalocean.com/community/tutorials/devstral-2-mistral-coding-open-weight-model); [Cline blog](https://cline.bot/blog/devstral-2-release); [HF card (not opened)](https://huggingface.co/mistralai/Devstral-Small-2-24B-Instruct-2512)
- Mistral Small 4 (released 16 Mar 2026):
  - 119B MoE with 6.5B active parameters, 256K context, Apache 2.0.
  - One hybrid model covering instruct, reasoning (with a toggle between instant and reasoning modes), vision and coding.
  - Scores 27 on the Artificial Analysis Intelligence Index in reasoning mode, vs 15 for Small 3.2.
  - Sources: [Artificial Analysis on X, ~20 Mar 2026](https://x.com/ArtificialAnlys/status/2034960206736892365); [HF card (not opened)](https://huggingface.co/mistralai/Mistral-Small-4-119B-2603)
- Mistral Small 3.2 (24B, June 2025):
  - Function calling improved: about 78% on BFCL v2 multi-turn, up from 71% in Small 3.1.
  - HumanEval Plus 92.9%, IFEval 84.8%.
  - Sources: [MarkTechPost, 21 Jun 2025](https://www.marktechpost.com/2025/06/21/mistral-ai-releases-mistral-small-3-2-enhanced-instruction-following-reduced-repetition-and-stronger-function-calling-for-ai-integration/); [OpenRouter (not opened)](https://openrouter.ai/mistralai/mistral-small-3.2-24b-instruct)
- Ministral 3 (2 Dec 2025):
  - 3B, 8B and 14B sizes, each in Base, Instruct and Reasoning variants; Apache 2.0.
  - Vision, 256K context, native function calling and JSON output.
  - Ministral 3 14B reasoning scores LiveCodeBench 0.646, AIME25 0.850 and GPQA-D 0.712.
  - Source: [HF card (not opened)](https://huggingface.co/mistralai/Ministral-3-14B-Reasoning-2512)
- Mistral's own Vibe CLI README now defaults to `active_model = "mistral-medium-3.5"`. The coding CLI is built around the API models — [mistral-vibe README](https://github.com/mistralai/mistral-vibe)

**Google**
- Gemma 4 release date: 2 Apr 2026 under Apache 2.0 — [Wikipedia](https://en.wikipedia.org/wiki/Gemma_(language_model)); Artificial Analysis covered the launch on ~4 Apr 2026 — [AA on X](https://x.com/ArtificialAnlys/status/2040241636089729451)
  - One secondary source instead gives 31 Mar 2026 for the family, 16 Apr 2026 for the MTP drafters and 3 Jun 2026 for "Gemma 4 12B Unified" — [Analytics Vidhya](https://www.analyticsvidhya.com/blog/2026/06/google-gemma-4-12b/)
- Gemma 4 sizes:
  - The launch had four: E2B (2.3B effective), E4B (4.5B effective), 26B A4B (25.2B total / 3.8B active MoE) and 31B dense (30.7B).
  - A 12B ("Unified": text, image, audio and video input) was added in June 2026.
  - Sources: [search summary of model card](https://ai.google.dev/gemma/docs/core/model_card_4); [Analytics Vidhya](https://www.analyticsvidhya.com/blog/2026/06/google-gemma-4-12b/)
- Gemma 4 context and modalities: up to 256K context on the larger sizes; text and image input; audio on E2B, E4B and 12B; native function calling — [Gemma 4 model card (via search)](https://ai.google.dev/gemma/docs/core/model_card_4)
- Gemma 4 thinking toggle:
  - Thinking is turned on with a `<|think|>` token in the system prompt, or with the chat-template kwarg `{"enable_thinking": false}` (for example `llama-server --chat-template-kwargs '{"enable_thinking": false}'`).
  - Thoughts must NOT be stripped between function calls within one model turn.
  - 26B-A4B and 31B "may occasionally generate a thought channel even when thinking mode is explicitly turned off"; the documented fix is to add an empty thinking token.
  - Source: [Gemma 4 prompt formatting doc (via search)](https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4)
- Gemma 3 and 3n are superseded by Gemma 4. Ollama's README now uses `gemma4` as its example default model — [ollama README](https://github.com/ollama/ollama)

**Zhipu / Z.ai**
- GLM-4.7-Flash:
  - Z.ai's GitHub lists it as "the lightweight 30B-A3B model GLM-4.7-Flash" (BF16, HF + ModelScope), with its own `glm4_moe_lite` architecture in transformers, vLLM and SGLang — [zai-org/GLM-4.5 README (covers 4.5/4.6/4.7)](https://github.com/zai-org/GLM-4.5)
  - Released in January 2026; context up to ~200K — [Medium guide (via search)](https://medium.com/@zh.milo/glm-4-7-flash-the-ultimate-2026-guide-to-local-ai-coding-assistant-93a43c3f8db3); [llm-stats](https://llm-stats.com/blog/research/glm-4.7-flash-launch)
- GLM-4.x thinking controls:
  - Thinking is ON by default in vLLM/SGLang. Disable it with `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`.
  - Tool parser is `glm47`, and tools use the OpenAI-style tool format.
  - "Preserved Thinking" for agentic use requires `"enable_thinking": true, "clear_thinking": false`.
  - Source: [zai-org/GLM-4.5 README](https://github.com/zai-org/GLM-4.5)
- GLM-4.5 / GLM-4.5-Air: GLM-4.5-Air is 106B total / 12B active, MIT, a hybrid thinking/non-thinking model. BF16 inference needs 4×H100 (FP8 needs 2×) — [zai-org/GLM-4.5 README](https://github.com/zai-org/GLM-4.5)
- GLM-4.6 and GLM-4.7 are 355B-A32B, so not laptop-class — [zai-org/GLM-4.5 README](https://github.com/zai-org/GLM-4.5)
- GLM-5 generation: GLM-5, 5.1, 5.2 and 5.3 are all 744B-A40B. GLM-5.3-Flash is 320B-A18B, with `reasoning_effort` low/high/max (default max) — [zai-org/GLM-5 README](https://github.com/zai-org/GLM-5)
  - GLM-5.3-Flash weights were published 26 Aug 2026 under MIT — [progressiverobot via search](https://www.progressiverobot.com/2026/08/28/glm-5-3-flash-open-weight-320b-model/)
  - No GLM-5 "Air" exists; HF discussions show users asking for one — [HF discussion](https://huggingface.co/zai-org/GLM-5.2/discussions/3)
  - The "Flash" name no longer means laptop-size in the GLM-5 generation.

**IBM Granite**
- Granite 4.0:
  - Sizes: micro, h-micro, h-tiny, h-small and 8B (dense, dense-hybrid and MoE-hybrid); Apache 2.0.
  - Explicitly markets tool use, "structured JSON output" and FIM code completion.
  - Source: [granite-4.0 README](https://github.com/ibm-granite/granite-4.0-language-models)
- Granite 4.1:
  - Released 29 Apr 2026 — [search: datanorth/IBM](https://datanorth.ai/news/ibm-releases-granite-4-1)
  - Dense 3B, 8B and 30B; about 15T training tokens; context up to 512K; Apache 2.0; tool calling and JSON-schema output examples — [granite-4.1 README](https://github.com/ibm-granite/granite-4.1-language-models)
- Granite 4.2:
  - Released 25 Aug 2026 — [MarkTechPost via search](https://www.marktechpost.com/2026/08/25/ibm-releases-granite-4-2-bringing-native-reasoning-and-agentic-rl-to-open-enterprise-models/)
  - Dense 3B, 8B and 30B, post-trained on the Granite 4.1 bases; Apache 2.0.
  - First Granite generation with native thinking. Toggle it with `enable_thinking=True/False` in the chat template, plus a `low_effort=True` mode; tool calling includes reasoning ("thinks about which tool to call") — [granite-4.2 README](https://github.com/ibm-granite/granite-4.2-language-models)
  - Context: 128K; the 30B extends to 512K — [explainx via search](https://www.explainx.ai/blog/ibm-granite-4-2-open-reasoning-models-august-2026)

**Microsoft Phi**
- Phi-4-reasoning: 14B dense, MIT, context expanded from 16K to 32K, LiveCodeBench 53.8 (vendor) — [HF card via search](https://huggingface.co/microsoft/Phi-4-reasoning)
- Newest Phi releases in the official cookbook are Phi-4-mini(-flash)-reasoning and Phi-4-Reasoning-Vision-15B (Mar 2026). There is no Phi-5 in the cookbook — [PhiCookBook README](https://github.com/microsoft/PhiCookBook); [Wikipedia via search](https://en.wikipedia.org/wiki/Phi_(language_model))
  - A Spheron blog titled "Deploy Microsoft Phi-5" exists, but no official Microsoft Phi-5 release was found — [Spheron](https://www.spheron.network/blog/deploy-phi-5-gpu-cloud/)

**Meta**
- The llama-models README still lists Llama 4 (4/5/2025; Scout-17B-16E with 10M context, Maverick-17B-128E with 1M) as its latest Llama. Scout needs "a single GPU with 80GB" at Int4 — [meta-llama/llama-models README](https://github.com/meta-llama/llama-models)
- **Muse Glimmer (new, notable):**
  - Released 10 Aug 2026 — [AI at Meta on X, 10 Aug 2026](https://x.com/AIatMeta/status/2086757844544811485); [MarkTechPost](https://www.marktechpost.com/2026/08/10/meta-ai-releases-muse-glimmer/)
  - 30B dense (not MoE) multimodal model, distilled from Muse Spark, Apache 2.0 — [VentureBeat](https://venturebeat.com/technology/meta-returns-to-open-source-with-muse-glimmer-an-apache-2-0-licensed-30b-parameter-ai-model-optimized-for-agents-available-now); [HF (not opened)](https://huggingface.co/meta-models/Muse-Glimmer-30B)
  - Context 131,072+ tokens; knowledge cutoff 4 Jan 2026 — [NVIDIA NIM ref via search](https://docs.api.nvidia.com/nim/reference/meta-muse-glimmer-30b)
  - Controllable reasoning strength: low, medium, high and xhigh. Meta's approximately 4-bit builds are under 20 GB — [Ollama blog via search](https://ollama.com/blog/muse-glimmer)

**DeepSeek**
- DeepSeek V4 (24 Apr 2026, MIT):
  - V4-Pro is 1.6T / 49B active; V4-Flash is 284B / 13B active; both have 1M context.
  - V4-Flash "fits on a single 80GB GPU when quantized", so it is not laptop-class — [MorphLLM via search](https://www.morphllm.com/deepseek-v4); [winbuzzer](https://winbuzzer.com/2026/04/27/deepseek-v4-open-weights-launch-xcxwbn/)
- An Ollama issue mentions `deepseek-v4.1-flash`, which suggests a V4.1 Flash exists — [ollama #18527](https://github.com/ollama/ollama/issues?q=nemotron)
- No small (laptop-size) DeepSeek release was found in 2026. The R1 distills (2025) are the only small DeepSeek-branded models.

**Moonshot Kimi**
- The only small Kimi model is Kimi-Linear-48B-A3B (Base and Instruct, 1M context, 5.7T training tokens). It is an architecture research release: its README headline results are MMLU-Pro 51.0 and RULER 84.3, and it gives no coding or agentic numbers — [Kimi-Linear README](https://github.com/MoonshotAI/Kimi-Linear)
- The main Kimi line is huge. Kimi K3 (16 Jul 2026) has 2.8T params — [Kimi K3 blog via search](https://www.kimi.ai/blog/kimi-k3)

**ByteDance Seed**
- Seed-OSS-36B-Base/Instruct:
  - Released 20 Aug 2025; 36B dense; 512K native context; Apache 2.0.
  - Thinking budget control: `thinking_budget` in tokens (-1 = unlimited, the default; 0 = direct answer; multiples of 512 recommended).
  - vLLM tool parser `seed_oss`.
  - Source: [seed-oss README](https://github.com/ByteDance-Seed/seed-oss)

**NVIDIA**
- Nemotron 3 Nano:
  - 31.6B total / 3.6B active hybrid Mamba-Transformer MoE, up to 1M context, "budget-controlled reasoning" — [NVIDIA-NeMo/Nemotron README](https://github.com/NVIDIA-NeMo/Nemotron)
  - Released Dec 2025 — [vLLM blog 15 Dec 2025](https://blog.vllm.ai/2025/12/15/run-nvidia-nemotron-3-nano.html)
  - Disable reasoning with `chat_template_kwargs: {"enable_thinking": false}` or `--reasoning-budget 0` — [NVIDIA RAG docs via search](https://docs.nvidia.com/rag/latest/enable-nemotron-thinking.html)
- Nemotron 3 Nano 4B (~17 Mar 2026): runs in about 5 GB of memory, `ollama run nemotron-3-nano:4b` — [Ollama on X](https://x.com/ollama/status/2034046614286028961)
- Nemotron-Cascade-2-30B-A3B:
  - Released 19–20 Mar 2026; reasoning-focused; 1M context; NVIDIA Open Model License (commercial use allowed).
  - Gold-level results at IMO and IOI 2025.
  - Sources: [MarkTechPost 20 Mar 2026](https://www.marktechpost.com/2026/03/20/nvidia-releases-nemotron-cascade-2-an-open-30b-moe-with-3b-active-parameters-delivering-better-reasoning-and-strong-agentic-capabilities/); [AA model page (not opened)](https://artificialanalysis.ai/models/nemotron-cascade-2-30b-a3b)
- Nemotron 3.5 Lightning:
  - 30B total / 3B active hybrid Mamba-Transformer MoE with Multi-Token Prediction, "built for the high-volume execution layer of long-running agents".
  - Weights, data and recipes are under OpenMDW-1.1.
  - Source: [NVIDIA-NeMo/Nemotron README](https://github.com/NVIDIA-NeMo/Nemotron); [lightning35 doc](https://github.com/NVIDIA-NeMo/Nemotron/blob/main/docs/nemotron/lightning35/README.md)
  - Released 11 Aug 2026 — [DataCamp via search](https://www.datacamp.com/blog/nemotron-3-5-lightning)
- Nemotron 3 Super (120.6B / 12.7B active) and Ultra (550B / 55B active) are not laptop-class — [Nemotron README](https://github.com/NVIDIA-NeMo/Nemotron)

### Inferences
Laptop memory fit at Q4 is estimated from the Ollama download sizes in Q3, plus KV cache and OS headroom.

**~16 GB laptops**
- Gemma 4 E4B and 12B.
- Granite 4.1/4.2 3B and 8B.
- Nemotron 3 Nano 4B.
- Ministral 3 8B/14B.
- Phi-4 family.
- Devstral Small 2 (15 GB) and Gemma 4 26B-A4B (~15–18 GB) are only borderline on 16 GB unified memory and are realistic only with a small context.

**~32 GB laptops**
- Devstral Small 2 24B.
- Gemma 4 26B-A4B and 31B.
- GLM-4.7-Flash (19 GB).
- Muse Glimmer (18 GB).
- Granite 30B (17 GB).
- Nemotron 3 Nano 30B (24 GB).
- Seed-OSS-36B (my estimate: ~20–22 GB at Q4, not sourced).

**~64 GB laptops**
- All of the above, with long contexts.
- GLM-4.5-Air (106B-A12B) at Q4 is roughly 60+ GB (inferred from parameter count). It is a borderline, bad fit.
- Mistral Small 4 (119B) at Q4 is roughly 65–70 GB (inferred), so it does not fit.
- Llama 4 Scout needs an 80 GB-class footprint at Int4 per Meta.

**Other inferences**
- Among the MoE A3B/A4B models, decode speed on laptops should be far higher than for the dense 24–31B models (Devstral Small 2, Gemma 4 31B, Muse Glimmer, Granite 30B, Seed-OSS 36B). This matters for a multi-agent PoC making many sequential calls.
- Devstral Small 2 appears to be a non-reasoning instruct model; none of the sources I saw mention a thinking toggle. This is an inference, not verified on the card.

### Gaps
- Could not open Hugging Face model cards, the Gemma 4 model card, mistral.ai, or ollama.com (egress policy). Exact card numbers for Gemma 4, Devstral Small 2, GLM-4.7-Flash and Muse Glimmer come from search summaries and need re-verification.
- Release dates not directly verified from primary sources:
  - GLM-4.7-Flash: "January 2026" only; the exact day was not confirmed.
  - Granite 4.0: early Oct 2025 from memory, not sourced.
  - Kimi-Linear: late Oct 2025 from memory, not sourced.
- Codestral's current status: Codestral 25.01 shows up on Aider as an API model. I did not confirm whether any 2025–2026 Codestral has downloadable weights. The original Codestral 22B used a non-production license (from memory, not verified).
- Whether Mistral released an open-weight "Devstral Small 3" or a successor after Dec 2025: none found in search.

## Q2. Published benchmark numbers (SWE-bench Verified, Aider polyglot, LiveCodeBench, HumanEval+/EvalPlus, BFCL, tau/tau2, IFEval)

### Takeaway
On vendor-reported agentic-coding numbers, the ranking at laptop size is Muse Glimmer 30B (SWE-bench Verified 76.0, a single secondary report) > Devstral Small 2 (68.0) > GLM-4.7-Flash (59.2) > Seed-OSS-36B (56) > Nemotron 3.5 Lightning (51.6) > Nemotron 3 Nano (38.8).
- Gemma 4 leads on LiveCodeBench, BFCL v4 and τ-bench style tool use (per IBM's independent-of-Google comparison), but Google does not publish SWE-bench Verified for it.
- Almost all numbers are vendor-reported. The few independent sources (Aider polyglot, last updated Oct 2025) do not cover any of the 2026 laptop models.
- The same model's SWE-bench Verified score varies by 25+ points depending on harness, as shown by gpt-oss-20b below.

### Cited Findings
**SWE-bench Verified (vendor-reported unless noted)**
- Devstral Small 2 (24B): **68.0%**; Devstral 2 (123B): 72.2% — [Cline blog](https://cline.bot/blog/devstral-2-release); [Mistral news](https://mistral.ai/news/devstral-2-vibe-cli/)
  - Conflict: a MorphLLM "best Ollama models" page (Aug 2026) says "Devstral-Small-2-24B scores 46.8%". 46.8% was the original Devstral Small (May 2025) score, so that page appears to conflate versions — [MorphLLM](https://www.morphllm.com/best-ollama-models)
- GLM-4.7-Flash: **59.2%**, vs Qwen3-30B-A3B-Thinking-2507 at 22.0% and GPT-OSS-20B at 34.0% (as measured in Z.ai's table) — [search summary of HF card/Medium](https://medium.com/@zh.milo/glm-4-7-flash-the-ultimate-2026-guide-to-local-ai-coding-assistant-93a43c3f8db3); [llm-stats](https://llm-stats.com/blog/research/glm-4.7-flash-launch)
- Nemotron 3 Nano 30B-A3B (OpenHands harness): **38.76** vs Qwen3-30B-A3B 22.00 and GPT-OSS-20B 34.00 — [Nemotron 3 Nano paper via search](https://arxiv.org/pdf/2512.20848)
- Seed-OSS-36B-Instruct:
  - **56** (OpenHands) and 47 (AgentLess 4×10).
  - In the same table: Qwen3-30B-A3B-Thinking-2507 31 (OpenHands) / 33.5 (AgentLess); Qwen3-32B 23.4 / 39.7; OAI-OSS-20B "(60.7)" (the value in parentheses is OpenAI's self-reported number).
  - Multi-SWE-Bench: Seed-OSS 17.
  - Source: [seed-oss README](https://github.com/ByteDance-Seed/seed-oss)
- Nemotron 3.5 Lightning: **51.56**, plus Terminal-Bench 2.1 24.58, IFBench (loose) 71.88, GPQA-D 75.44 and MMLU-Pro 81.94. It trails Qwen3.6-35B-A3B on 11 of 12 comparable rows in NVIDIA's own table — [digitalapplied / layer3labs via search](https://www.digitalapplied.com/blog/nvidia-nemotron-3-5-lightning-30b-a3b-efficiency-tier-2026)
- Muse Glimmer 30B:
  - SWE-bench Verified **76.0**, from a single search summary citing DataCamp/Meta; treat as unverified — [DataCamp](https://www.datacamp.com/blog/muse-glimmer)
  - SWE-Bench Pro 51.2 (vs Qwen3.6-27B 50.2); MCP Atlas 75.5 (vs Gemma 4 31B 54.2); Terminal-Bench 2.1 52% (vs Qwen3.6 27B 61%) — [search summary of Wavect / Artificial Analysis / layer3labs](https://artificialanalysis.ai/articles/muse-glimmer)
  - Qwen3.6 27B beats Muse Glimmer on SWE-bench Verified, Terminal-Bench 2.1 and OSWorld per the same reporting. The HN consensus quoted there: "barely edges out Qwen3.6 27B except for tool-calling skills".
- gpt-oss-20b harness sensitivity: 60.7 (OpenAI self-report, as quoted in the Seed-OSS table) vs 34.0 (measured by NVIDIA/Z.ai with OpenHands) — [seed-oss README](https://github.com/ByteDance-Seed/seed-oss); [Nemotron 3 Nano paper via search](https://arxiv.org/pdf/2512.20848)
- Granite 4.2 SWE numbers:
  - IBM reports SWE-Bench **Pro**, not Verified: 30B 33.3 vs Gemma 4 31B 29.7 vs Qwen3.6 27B 40.6; 8B 19.1.
  - Terminal-Bench 2.1: 30B 29.2 vs Gemma 4 31B 44.9, Nemotron 3 Super 38.4, Qwen3.6 27B 56.0; 8B 20.6 vs Gemma 4 26B-A4B 35.7 and Nemotron 3 Nano 7.2.
  - Sources: [granite-4.2 30B figure](https://github.com/ibm-granite/granite-4.2-language-models/blob/main/figures/30b-comparison.png); [8B figure](https://github.com/ibm-granite/granite-4.2-language-models/blob/main/figures/8b-comparison.png)
  - Search summaries wrongly relabel these as "SWE-bench Verified 57.00 / 47.67"; the figures say SWE Bench Pro — [eesel via search](https://www.eesel.ai/blog/granite-4-2) vs the README figures.

**LiveCodeBench v6**
- Gemma 4 (Google, reported as from the model card): 31B **80.0**, 26B-A4B **77.1**, 12B 72.0, E4B 52.0, E2B 44.0. Codeforces ELO: 2150 / 1718 / 1659 / 940 / 633. Gemma 3 27B scored 29.1 LCB and 110 ELO — [search summary of model card](https://ai.google.dev/gemma/docs/core/model_card_4); [gemmai4.com (unofficial)](https://gemmai4.com/benchmark/)
- IBM's own measurement of the same models ran higher: Gemma 4 31B **83.0**, Gemma 4 26B-A4B **80.3**, Nemotron 3 Nano 67.2, Nemotron 3 Super 73.7, Granite 4.2 30B 75.8 / 8B 73.2, Qwen3.6 27B 78.5 — [granite-4.2 figures](https://github.com/ibm-granite/granite-4.2-language-models)
- GLM-4.7-Flash 64.0 vs Qwen3-30B-A3B-Thinking 66.0, GPT-OSS-20B 61.0 and Nemotron-3-Nano 68.3 — [search summary citing the HF card table](https://medium.com/@zh.milo/glm-4-7-flash-the-ultimate-2026-guide-to-local-ai-coding-assistant-93a43c3f8db3)
- Seed-OSS-36B-Instruct 67.4, vs OAI-OSS-20B 63.8 and Qwen3-30B-A3B-Thinking-2507 60.3 (66 self-reported) — [seed-oss README](https://github.com/ByteDance-Seed/seed-oss)
- Nemotron-Cascade-2-30B-A3B: 87.2 (LCB v6, 2408–2505). NVIDIA says it "underperforms" Qwen3.5-35B-A3B on BFCL v4 and τ²-Bench — [Cascade 2 paper via search](https://arxiv.org/html/2603.19220)
- Ministral 3 14B Reasoning 64.6; Phi-4-reasoning 53.8 — [HF cards via search](https://huggingface.co/mistralai/Ministral-3-14B-Reasoning-2512); [Phi-4-reasoning](https://huggingface.co/microsoft/Phi-4-reasoning)

**Tool use: BFCL, τ²-bench and τ³-bench**
- IBM-measured BFCL v4:
  - Gemma 4 31B **69.7**, Granite 4.2 30B 61.8, Qwen3.6 27B 61.0, Nemotron 3 Super 59.6.
  - Gemma 4 26B-A4B **64.4**, Nemotron 3 Nano 59.3, Granite 4.2 8B 52.4.
  - Source: [granite-4.2 figures](https://github.com/ibm-granite/granite-4.2-language-models)
- IBM-measured τ³-bench:
  - Gemma 4 31B 70.0, Qwen3.6 27B 70.4, Granite 4.2 30B 62.0, Nemotron 3 Super 61.9.
  - Gemma 4 26B-A4B 61.7, Granite 4.2 8B 58.1, Nemotron 3 Nano 45.1.
  - Source: [granite-4.2 figures](https://github.com/ibm-granite/granite-4.2-language-models)
- IBM-measured IFBench: Gemma 4 31B 78.5, Gemma 4 26B-A4B 76.3, Granite 4.2 8B 79.3 / 30B 75.3, Nemotron 3 Nano 68.7, Qwen3.6 27B 67.3 — [granite-4.2 figures](https://github.com/ibm-granite/granite-4.2-language-models)
- NVIDIA-reported: Nemotron 3 Nano BFCL v4 53.76 vs Qwen3-30B-A3B 46.40; τ²-bench average 49.04 vs Qwen3-30B-A3B 47.70 and GPT-OSS-20B 47.50 — [Nemotron 3 Nano paper via search](https://arxiv.org/pdf/2512.20848)
- GLM-4.7-Flash τ²-bench: 79.5 (Z.ai-reported) — [search summary](https://medium.com/@zh.milo/glm-4-7-flash-the-ultimate-2026-guide-to-local-ai-coding-assistant-93a43c3f8db3)
- Gemma 4 τ²-bench (conflicting reports):
  - 31B = **86.4%** (vs Gemma 3 27B 6.6%); 12B = 69.0%; 26B-A4B = 68.2% — [search summary](https://huggingface.co/google/gemma-4-12B)
  - Another summary gives 31B = **76.9%** vs Gemma 3 27B 16.2% — [search summary](https://ai.google.dev/gemma/docs/core/model_card_4)
  - The numbers conflict; verify on the card.
- Seed-OSS-36B: TAU1-Retail 70.4, TAU1-Airline 46, IFEval 85.8 — [seed-oss README](https://github.com/ByteDance-Seed/seed-oss)
- Muse Glimmer: Tau3-Banking 24% vs Qwen3.6 27B 17% — [search summary of AA](https://artificialanalysis.ai/articles/muse-glimmer)

**HumanEval / EvalPlus**
- Mistral Small 3.2: HumanEval+ 92.9, MBPP pass@5 78.33 — [MarkTechPost](https://www.marktechpost.com/2025/06/21/mistral-ai-releases-mistral-small-3-2-enhanced-instruction-following-reduced-repetition-and-stronger-function-calling-for-ai-integration/)
- Seed-OSS-36B-Base: HumanEval 76.8, MBPP 80.6 — [seed-oss README](https://github.com/ByteDance-Seed/seed-oss)
- The 2026 cards mostly no longer report HumanEval/EvalPlus (the benchmark is saturated).

**Aider polyglot (independent; the leaderboard data was last updated 3 Oct 2025)**
- DeepSeek-V3.2-Exp (Reasoner) 74.2%; Kimi K2 59.1%; gpt-oss-120b (high) 41.8%; Qwen3 32B 40.0%; Llama 4 Maverick 15.6% (whole format); Codestral 25.01 11.1%; gemma-3-27b-it **4.9%**.
- No Devstral, GLM-4.x-Flash, Gemma 4, Granite, Nemotron, Muse Glimmer, Seed-OSS or Phi-4 entries.
- Source: [Aider polyglot_leaderboard.yml](https://github.com/Aider-AI/aider/blob/main/aider/website/_data/polyglot_leaderboard.yml)

**Artificial Analysis Intelligence Index (independent, but the index version changed over time)**
- "Sub-32B" article: Gemma 4 26B-A4B (Reasoning) 31, GLM-4.7-Flash (Reasoning) 30, Nemotron Cascade 2 28, Nemotron 3 Nano and gpt-oss-20b (high) ~24 — [AA sub-32B article via search](https://artificialanalysis.ai/articles/sub-32b-open-weights)
- Gemma 4 31B 39; Qwen3.6 27B 46 (~30 Apr 2026) — [AA on X](https://x.com/ArtificialAnlys/status/2049881951260283097)
- Conflicting values: another AA comparison page shows Qwen3 Coder 30B A3B 10 (estimated) vs Devstral Small 2 at 8, and gpt-oss-20b (high) at 9. This looks like a different or rescaled index version — [AA comparison](https://artificialanalysis.ai/models/comparisons/devstral-small-2-vs-qwen3-coder-30b-a3b-instruct)

### Inferences
- For "write a small stdlib Python module + unittest tests, then fix from failing test output", the most predictive public signals are SWE-bench Verified/Pro and Terminal-Bench (iterative fix loops), and BFCL/τ-bench (tool-call hygiene).
  - On the agentic-coding signals, Devstral Small 2, GLM-4.7-Flash and Muse Glimmer lead the non-Qwen field.
  - On tool hygiene, Gemma 4 leads by IBM's measurement.
  - Nemotron 3 Nano's Terminal-Bench 2.1 score of 7.2 (IBM-measured) is a red flag for iterative fix loops.
- LiveCodeBench-style competitive coding (where Gemma 4 and Cascade 2 shine) overstates fitness for multi-file agentic work.
  - The biggest example: Cascade 2 scores 87.2 LCB but is explicitly weaker on BFCL and τ².
  - Gemma 3 27B scored only 4.9% on Aider polyglot despite decent HumanEval.
- Vendor comparison baselines have shifted: 2026 cards compare against Qwen3.5/3.6 (27B, 35B-A3B), not Qwen3-Coder-30B-A3B. Qwen3-Coder-30B-A3B and gpt-oss-20b are now "2025 baselines".

### Gaps
- No independent SWE-bench Verified run found for Devstral Small 2, GLM-4.7-Flash, Gemma 4 or Muse Glimmer. SWE-rebench (swe-rebench.com) lists Devstral-Small-2-24B, but the site was blocked, so no numbers.
- The BFCL official leaderboard (gorilla.cs.berkeley.edu) was blocked, and its data CSV was not found on GitHub. The BFCL numbers above are vendor or IBM-measured only.
- The Aider leaderboard has not been updated since Oct 2025, so it has no 2026 local models.
- Devstral Small 2's Terminal-Bench, SWE-bench Multilingual, BFCL and τ² numbers were not found.
- Gemma 4 τ²-bench values conflict (86.4 vs 76.9 for the 31B).
- The Muse Glimmer SWE-bench Verified value (76.0) is single-sourced.

## Q3. Ollama library tags, download sizes, and listed capabilities

### Takeaway
All of the main 2026 laptop candidates have official Ollama library entries: `gemma4`, `devstral-small-2`, `glm-4.7-flash`, `nemotron-3-nano`, `nemotron-3.5-lightning`, `granite4.1`/`granite4.2`, `muse-glimmer` and `phi4-reasoning`. Their Q4 downloads cluster at 15–24 GB for the ~24–31B class. Ollama lists "tools" and "thinking" for glm-4.7-flash; tool/thinking badges for the others could not be confirmed because ollama.com was blocked.

### Cited Findings
- `devstral-small-2:24b` → Q4_K_M, **15 GB**; `:24b-instruct-2512-q8_0` 26 GB; `-fp16` 48 GB; a `:24b-cloud` tag also exists — [ollama.com/library/devstral-small-2 via search](https://ollama.com/library/devstral-small-2/tags)
  - The older `devstral` (Small 1.x) library entry still exists — [ollama devstral](https://ollama.com/library/devstral)
- `glm-4.7-flash` (latest = q4_K_M) **19 GB**; q8_0 32 GB; bf16 60 GB; capabilities "tools thinking" — [ollama.com/library/glm-4.7-flash via search](https://ollama.com/library/glm-4.7-flash/tags)
- `gemma4` tags: `gemma4:e2b`, `gemma4:e4b`, `gemma4:12b`, `gemma4:26b`, `gemma4:31b`:
  - Reported sizes: e2b ~1.5 GB at Q4 (other guides say ~6 GB VRAM); e4b ~5 GB (other guides say ~9 GB VRAM); 12b ~8 GB; 26b ~14–18 GB (one guide: ~15 GB on disk); 31b ~19–20 GB on disk / ~22 GB VRAM.
  - Sources: [ollama gemma4 tags via search](https://ollama.com/library/gemma4/tags); [gemma4:26b](https://ollama.com/library/gemma4:26b); [gemma4:31b](https://ollama.com/library/gemma4:31b); [theaitechpulse guide](https://www.theaitechpulse.com/gemma4-ollama-guide-2026)
  - `gemma4` is Ollama's README example model — [ollama README](https://github.com/ollama/ollama)
- `nemotron-3-nano:30b` (= `:30b-a3b-q4_K_M`) **24 GB**, 1M context; `:30b-a3b-q8_0` 34 GB; `:30b-a3b-fp16` 63 GB; `:30b-q4_k_xl` 23 GB — [ollama nemotron-3-nano tags via search](https://ollama.com/library/nemotron-3-nano/tags)
  - `nemotron-3-nano:4b` exists (about 5 GB of memory) — [Ollama on X](https://x.com/ollama/status/2034046614286028961)
- `nemotron-3.5-lightning:30b`, `:30b-a3b` and `:30b-mlx` (an Apple-Silicon MLX build) — [ollama nemotron-3.5-lightning via search](https://ollama.com/library/nemotron-3.5-lightning/tags)
- `granite4.1`: 3b 2.1 GB, 8b 5.3 GB, 30b 17 GB (30b-q2_K 11 GB); 128K context listed — [ollama granite4.1 via search](https://ollama.com/library/granite4.1/tags). A `granite4.2` library entry also exists — [ollama granite4.2](https://ollama.com/library/granite4.2/tags)
- `muse-glimmer`: the default tag is an **18 GB** quantized build with 128K context; runs on Ollama's MLX engine with DFlash speculative decoding (1.5–1.8× faster on Apple Silicon) — [Ollama blog via search](https://ollama.com/blog/muse-glimmer); [ollama.com/library/muse-glimmer](https://ollama.com/library/muse-glimmer)
- `phi4` (Q4_K_M default), `phi4-reasoning:14b` and `phi4-reasoning:plus` / `:14b-plus-q4_K_M`, `phi4-mini-reasoning` — [ollama phi4-reasoning via search](https://ollama.com/library/phi4-reasoning)
- Ollama now has `ollama launch <claude|codex|opencode|...>` integrations for running local models inside coding agents — [ollama README](https://github.com/ollama/ollama)

### Inferences
- Default tags for memory planning (Q4, before KV cache):
  - 16 GB machines: `gemma4:12b`, `granite4.2:8b`, `nemotron-3-nano:4b`.
  - 32 GB machines: `devstral-small-2:24b`, `gemma4:26b`, `glm-4.7-flash`, `muse-glimmer`, `gemma4:31b`, `granite4.2:30b`, `nemotron-3.5-lightning:30b`.
  - `nemotron-3-nano:30b` (24 GB) is heavier than the other A3B models because of its Mamba hybrid packaging.

### Gaps
- Could not open ollama.com, so the exact capability badges (tools/thinking/vision) for gemma4, devstral-small-2, nemotron-3-nano, granite4.2 and muse-glimmer are unconfirmed.
- Other unconfirmed Ollama details:
  - granite4.2 tag sizes.
  - Seed-OSS on Ollama (no official library entry found; community GGUFs exist, e.g. unsloth, per [search](https://huggingface.co/unsloth/Seed-OSS-36B-Instruct-GGUF)).
  - Whether phi4 lists "tools".

## Q4. Community / independent evidence on strict-JSON, tool-calling and multi-file code generation reliability locally

### Takeaway
The dominant real-world risk in 2026 is the runtime's per-model tool-call parsers and renderers (Ollama, llama.cpp), more than the models themselves. There are active, recent bugs for Gemma 4, GLM-4.7(-Flash) and Devstral Small 2 that can silently corrupt or drop tool calls or file content. For strict JSON, grammar-constrained decoding (Ollama's `format` = JSON Schema) is the reliable path. Ollama only fixed its thinking-model plus `format` path on 22 Sep 2026.

### Cited Findings
**GLM-4.7 / GLM-4.7-Flash**
- Ollama's GLM-4.7 tool-call parser strips leading and trailing newlines from string arguments (for example, file content `"two spaces\n"` becomes `"two spaces"`). It reuses Qwen3-Coder trimming logic, while GLM's template adds no padding.
  - Affects v0.34.4 through v0.40.0-rc0, and GLM-4.6/4.7/4.7-Flash.
  - Reported 26 Sep 2026; fix PR #18663 is open.
  - Source: [ollama #18658](https://github.com/ollama/ollama/issues/18658)

**Gemma 4**
- Bugs found running Gemma 4 A4B and Qwen A3B through a coding agent (4 Aug 2026):
  - Gemma 4 "occasionally emits tool-call closing tags without the final `}`".
  - Truncated tool calls at token limits reach callers as if complete, which "silently writes a truncated file".
  - A repetition guard aborts after 31 identical tokens and reports success.
  - Source: [ollama #17562](https://github.com/ollama/ollama/issues/17562)
- The Ollama gemma4 renderer drops tool parameters named `description`, `type`, `properties`, `required` or `nullable` from `properties` while still listing them as required. Fix PR opened 17 Sep 2026 — [ollama PR #18503](https://github.com/ollama/ollama/pull/18503)
- `gemma4:26b` under concurrent decode loses EOS and runs to num_predict (opened 14 Sep 2026). This matters for multi-agent concurrency — [ollama issues list](https://github.com/ollama/ollama/issues?q=glm-4.7-flash) (#18442)
- llama.cpp:
  - The PEG→GBNF `until()` bug left Gemma 4 tool calls partly unconstrained. With `tool_choice: required`, "approximately 1 in 15–25 generations produces structurally invalid JSON". Closed around 19 Sep 2026 — [llama.cpp #29089](https://github.com/ggml-org/llama.cpp/issues/29089)
  - Open issues: "gemma4 thinking starts to emit progressively long trailing garbage" (#28827, 13 Sep 2026) and a GGML_ASSERT abort on Gemma 4 31B (#29391) — [llama.cpp issues](https://github.com/ggml-org/llama.cpp/issues?q=gemma+4+tool+call)

**Devstral Small 2**
- When a tool has a parameter literally named `name`, Ollama silently returns an empty response with no tool call. The Mistral `[TOOL_CALLS]name[ARGS]{...}` parser confuses the two. Workaround: rename the parameter. Reported 26 Jun 2026; PR #16942 open — [ollama #16932](https://github.com/ollama/ollama/issues/16932)
- An older dev.to test found the original Devstral (2025) "completely fails the tool calling test". This predates Devstral Small 2 — [dev.to](https://dev.to/techgirl1908/is-devstral-really-agent-friendly-5e5k)

**Cross-model runtime stability**
- On an M3 Max (128 GB, macOS), sustained multi-turn tool-call loops on `/v1/chat/completions` crashed the runner.
  - Models: gemma4 26b/31b, mistral-small3.2, glm-4.7-flash, nemotron-cascade-2 and others.
  - Failure rate: 72% across 138 runs and seven models; described as a regression from 0.19.x.
  - Reported 1 May 2026; closed 7 Jun 2026.
  - Source: [ollama #15923](https://github.com/ollama/ollama/issues/15923)

**Structured outputs with thinking models**
- Before 22 Sep 2026, Ollama ran thinking models with `format` in two passes. This dropped content at the thinking/format boundary, leaked stray tokens into JSON on MLX, and "forced JSON inside thinking, producing invalid structures".
- PR #18479 (merged 22 Sep 2026) makes it single-pass and fixes #18441, #17544, #14196 and #10929.
- Source: [ollama PR #18479](https://github.com/ollama/ollama/pull/18479)
- An open proposal and PR adds token-budgeted thinking in Ollama (4 Aug 2026) — [ollama #17561/#17566](https://github.com/ollama/ollama/issues?q=glm-4.7-flash)

**Constrained decoding and JSON-benchmark evidence**
- Ollama/llama.cpp JSON-schema constrained decoding (via the `format` parameter, compiled to GBNF) guarantees syntactically valid, schema-shaped JSON. It does not guarantee correct content — [InsiderLLM guide via search](https://insiderllm.com/guides/structured-output-local-llms/)
- Research note: without constraints, "Gemma systematically wraps JSON in markdown fences — rendering all outputs unparseable despite 88.4% underlying task accuracy". The Gemma version was not identified in the snippet; likely Gemma 3 — [arXiv 2605.02363 via search](https://arxiv.org/pdf/2605.02363)
- A structured-output benchmark ranks GLM-4.7 at the top (0.830), ahead of Qwen3.5-35B (0.828). This is the full GLM-4.7, not Flash — [InsiderLLM via search](https://insiderllm.com/guides/structured-output-local-llms/)
- Mistral says Devstral's tool calling is "the best in the Mistral lineup" for multi-step OpenClaw runs. This is a vendor-adjacent blog — [haimaker.ai](https://haimaker.ai/blog/best-mistral-models-for-openclaw/)
- An Unsloth HF discussion offers an Ollama Modelfile "to fix tool calling within GLM-4.7-Flash GGUF", which shows that early GGUF templates needed community fixes — [HF discussion (not opened)](https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF/discussions/23)

### Inferences
- For Cynqra's PoC:
  - Prefer JSON-mode (`format` schema) responses that carry file contents as JSON string fields, over native tool calls that write files, at least for GLM on Ollama until #18663 ships. Tool-arg trimming breaks trailing newlines, and possibly Python indentation at file starts.
  - Pin an Ollama version that includes PR #18479 if the models run in thinking mode with `format`. Otherwise disable thinking for the JSON-emitting agents.
  - Avoid tool parameters named `name` (Devstral) and `description`/`type`/`required` (Gemma 4).
  - Add a post-parse validator plus a retry. Truncation-at-num_predict and missing-brace failures are documented.
- Multi-agent concurrency against a single Ollama server has a known Gemma 4 EOS bug. Serializing requests, or setting a generous `num_predict` and checking `done_reason`, is prudent.

### Gaps
- r/LocalLLaMA threads could not be fetched (reddit blocked), and search returned no specific Reddit reports for these models. The community evidence here comes from GitHub issues instead.
- No independent head-to-head test of multi-file stdlib-plus-unittest generation for these models was found.
- No published JSON-validity rates (unconstrained) per model for Devstral Small 2, GLM-4.7-Flash, Gemma 4, Muse Glimmer or Granite 4.2.

## Q5. Which credibly match or beat Qwen3-Coder-30B-A3B or gpt-oss-20b at similar memory, and which are clearly weaker

### Takeaway
**Credible matches or betters at ~15–24 GB Q4**, all on vendor numbers:
- GLM-4.7-Flash: same 30B-A3B shape, SWE-V 59.2 vs gpt-oss-20b 34 in Z.ai's harness, τ² 79.5, MIT.
- Devstral Small 2: 24B dense, SWE-V 68.0, Apache 2.0, but slower on laptops and with no thinking mode.
- Gemma 4 26B-A4B: best tool-use and BFCL scores in IBM's cross-vendor figures and strong LCB, but no published SWE-bench Verified and several open Ollama/llama.cpp tool-call bugs.
- Muse Glimmer 30B dense: newest, and possibly the strongest on agentic tool use, but its numbers are thinly verified and dense 30B is slow on laptops.

**Plausible but secondary:** Nemotron 3.5 Lightning (SWE-V 51.6, speed-focused), Granite 4.2 30B/8B (good BFCL/IFBench, weaker on Terminal-Bench) and Seed-OSS-36B (SWE-V 56, but 36B dense and Aug 2025).

**Clearly weaker for this use case:** Nemotron 3 Nano 30B, Nemotron-Cascade 2 (reasoning specialist), Gemma 3/3n, Phi-4 family, Llama 3.x/4, Mistral Small 3.x, Ministral 3, Codestral, DeepSeek R1 distills and Kimi-Linear.

### Cited Findings
- GLM-4.7-Flash vs the baselines: SWE-bench Verified 59.2 vs GPT-OSS-20B 34.0 and Qwen3-30B-A3B-Thinking 22.0; LiveCodeBench v6 64.0 vs GPT-OSS-20B 61.0 and Qwen3-30B-A3B-Thinking 66.0 (Z.ai table) — [search summary](https://medium.com/@zh.milo/glm-4-7-flash-the-ultimate-2026-guide-to-local-ai-coding-assistant-93a43c3f8db3)
  - AA Intelligence Index: GLM-4.7-Flash 30 vs gpt-oss-20b (high) ~24 — [AA sub-32B via search](https://artificialanalysis.ai/articles/sub-32b-open-weights)
- Devstral Small 2 SWE-bench Verified 68.0% — [Cline](https://cline.bot/blog/devstral-2-release). One AA comparison rates Qwen3 Coder 30B A3B "more intelligent" (10 vs 8) but Devstral Small 2 faster via API (139.2 vs 90.6 tok/s) — [AA comparison via search](https://artificialanalysis.ai/models/comparisons/devstral-small-2-vs-qwen3-coder-30b-a3b-instruct)
- Gemma 4 26B-A4B:
  - IBM-measured: BFCL v4 64.4, τ³ 61.7, LCB 80.3, Terminal-Bench 2.1 35.7. These beat Nemotron 3 Nano (59.3 / 45.1 / 67.2 / 7.2) and Granite 4.2 8B — [granite-4.2 8B figure](https://github.com/ibm-granite/granite-4.2-language-models/blob/main/figures/8b-comparison.png)
  - AA index 31 vs gpt-oss-20b ~24 — [AA via search](https://artificialanalysis.ai/articles/sub-32b-open-weights)
- Muse Glimmer: Meta's own "outperforms Gemma4-31B and Qwen3.6-27B across virtually every agentic benchmark" claim is contradicted by the AA/HN summary that Qwen3.6 27B wins 4 of 7 rows, including SWE-bench Verified — [MindStudio via search](https://www.mindstudio.ai/blog/meta-muse-glimmer-30b-open-weights); [AA article via search](https://artificialanalysis.ai/articles/muse-glimmer)
- Nemotron 3 Nano:
  - SWE-V 38.76 (OpenHands) edges gpt-oss-20b's 34.0 in NVIDIA's harness — [paper via search](https://arxiv.org/pdf/2512.20848)
  - But IBM measured Terminal-Bench 2.1 at 7.2 and τ³ at 45.1 — [granite-4.2 figure](https://github.com/ibm-granite/granite-4.2-language-models/blob/main/figures/8b-comparison.png)
  - NVIDIA itself now positions Nemotron 3.5 Lightning as the agent-execution model; Lightning trails Qwen3.6-35B-A3B on 11 of 12 rows — [digitalapplied via search](https://www.digitalapplied.com/blog/nvidia-nemotron-3-5-lightning-30b-a3b-efficiency-tier-2026)
- Nemotron-Cascade-2 "underperforms on agentic benchmarks like BFCL v4 and τ²-Bench" relative to Qwen3.5-35B-A3B, despite LCB 87.2 — [Cascade 2 paper via search](https://arxiv.org/html/2603.19220)
- Gemma 3 27B: Aider polyglot 4.9%; Codestral 25.01 11.1%; Llama 4 Maverick 15.6% — [Aider leaderboard data](https://github.com/Aider-AI/aider/blob/main/aider/website/_data/polyglot_leaderboard.yml)
- Mistral Small 3.2: AA index 15 vs Mistral Small 4's 27 — [AA on X](https://x.com/ArtificialAnlys/status/2034960206736892365). Small 4 (119B) is too big for most laptops.
- Kimi-Linear-48B-A3B publishes no coding or agentic benchmarks — [Kimi-Linear README](https://github.com/MoonshotAI/Kimi-Linear)
- Phi-4-reasoning: 32K context, LCB 53.8 — [HF via search](https://huggingface.co/microsoft/Phi-4-reasoning). This context is short for multi-file agent transcripts.
- Seed-OSS-36B beats Qwen3-30B-A3B-Thinking-2507 in ByteDance's table: SWE-V (OpenHands) 56 vs 31, LCB 67.4 vs 60.3, TAU1-Retail 70.4 vs 58.7 — [seed-oss README](https://github.com/ByteDance-Seed/seed-oss)

### Inferences
- **Best like-for-like swap for Qwen3-Coder-30B-A3B** (same A3B speed class, ~19 GB): GLM-4.7-Flash. Caveats: it is thinking-by-default (disable it for JSON agents, or budget it) and has the open Ollama newline-trim bug for tool args.
- **Best "just write correct code" non-Qwen option on a 32 GB laptop**: Devstral Small 2 24B. It is purpose-built for agentic coding, Apache 2.0 and non-thinking (lower latency variance), but dense, so perhaps 1/3–1/2 the decode speed of an A3B MoE (inferred).
- **Best tool-calling / JSON discipline candidate**: Gemma 4 26B-A4B (or 31B on 32 GB+), on IBM's BFCL/τ³/IFBench figures. Mitigate the known runtime bugs with schema-constrained `format` output and validators.
- **Watch-list**: Muse Glimmer 30B. It is newest (Aug 2026) with strong reported agentic and tool scores and an 18 GB Ollama build, but it needs independent verification, and a dense 30B will be slow on non-Apple laptops.
- **For the multi-agent PoC comparison matrix**, a sensible shortlist to benchmark locally against Qwen3-Coder-30B-A3B and gpt-oss-20b on Cynqra's own stdlib-plus-unittest tasks:
  1. `glm-4.7-flash`
  2. `devstral-small-2:24b`
  3. `gemma4:26b`
  4. `muse-glimmer`
  5. Optionally `granite4.2:30b` or `nemotron-3.5-lightning` as speed/enterprise alternates
- The published numbers are too harness-dependent to settle this without a local run: gpt-oss-20b is 60.7 vs 34.0 on SWE-V depending on harness.

### Gaps
- No source directly compares any of these against **Qwen3-Coder-30B-A3B** specifically. 2026 vendor tables compare against Qwen3-30B-A3B-Thinking, Qwen3.5-35B-A3B or Qwen3.6-27B/35B-A3B. The Qwen3-Coder-30B-A3B baseline numbers themselves are left to the Qwen-focused research notes.
- No independent (non-vendor) SWE-bench Verified or Aider polyglot numbers exist in my sources for GLM-4.7-Flash, Devstral Small 2, Gemma 4, Muse Glimmer, Granite 4.2 or Nemotron 3.5 Lightning.
- No measured laptop tokens/sec comparisons were collected, beyond vendor claims:
  - Nemotron 3.5 Lightning claims up to 4× throughput.
  - Muse Glimmer DFlash claims 1.5–1.8× on Apple Silicon.
  - GLM-4.7-Flash is reported at 60–100 tok/s on RTX 3090/4090 ([search summary](https://www.datacamp.com/tutorial/glm-4-7-flash-locally)).
