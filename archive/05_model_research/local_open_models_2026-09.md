# Qwen3.6 on Ollama should power Cynqra's laptops

Cynqra should use **Qwen3.6-35B-A3B (Ollama tag `qwen3.6:35b`) on Ollama v0.34.4 or later** as its default on every laptop with 32 GB or more. Laptops with 16 GB should drop to **Qwen3.5-9B (`qwen3.5:9b`)**, and every machine that can hold it should keep **gpt-oss-20b (`gpt-oss:20b`)** as a fallback from a different model family. The Qwen choice rests on vendor numbers: 73.4 on SWE-bench Verified for the 35B-A3B, against 60.7 that OpenAI reports for gpt-oss-20b and 34.0 when third parties ran gpt-oss-20b in their own harness. The 35B-A3B is a mixture-of-experts model with only 3B of its 35B parameters active per token, so it generates text at gpt-oss speed and still fits in 32 GB. **No independent 2026 head-to-head of these models exists**, so the ranking is provisional until the team runs a local bake-off on Cynqra's own tasks.

The runtime matters as much as the model. Ollama combines an MIT license, a Windows installer that needs no admin rights, a macOS dmg, a one-line Linux script, and per-request control of schema, thinking and context size. Its defaults, however, work against this workload:

- The context window is 4,096 tokens on any machine with less than 24 GiB of VRAM.
- Prompts that exceed the context are truncated silently.
- The built-in temperature is 0.8.
- The code path that combines thinking with structured output was rewritten only on 23 September 2026.

Every request should therefore carry a full JSON Schema in `format`, `think: false` (`"low"` for gpt-oss), an explicit `num_ctx`, `temperature: 0`, and `shift`/`truncate` set to false. The app should validate, compile and test every reply. Estimated wall-clock time is about 0.5–2 minutes per call on 32 GB+ Apple Silicon and on GPU laptops, 2–6 minutes on 32 GB CPU-only machines, and 5–9 minutes on 16 GB CPU-only machines. A 15–30-call run therefore takes anywhere from under ten minutes to more than four hours.

## Qwen3.6-35B-A3B leads on vendor paper, the only paper there is

Figures in this report carry one of these tags:

| Tag | Meaning |
|---|---|
| **[V]** | Reported by the model's maker |
| **[I]** | Measured by someone else: an independent leaderboard, users filing GitHub issues, or a competing vendor such as IBM, NVIDIA or Z.ai, named where it matters |
| **[S]** | Seen only in a search-engine snippet, because the researchers' proxy blocked Hugging Face, ollama.com, qwen.ai, arXiv and most blogs |
| **[E]** | An estimate derived in the research notes or in this report |

Tags combine: [V,S] is a vendor claim read only through a snippet. Every [S] number needs one confirmation click before anyone quotes it as final.

Three facts frame every comparison. First, the only neutral coding leaderboard with relevant rows is Aider polyglot, and it has **no entry after 3 October 2025** ([Aider leaderboard data](https://github.com/Aider-AI/aider/blob/main/aider/website/_data/polyglot_leaderboard.yml)). No 2026 candidate therefore has an independent coding score.

Second, the test harness moves scores more than the model does. OpenAI's card puts gpt-oss-20b at **60.7** on SWE-bench Verified ([OpenAI model card](https://cdn.openai.com/pdf/419b6906-9da6-406c-a19d-1bb078ac7637/oai_gpt-oss_model_card.pdf)). NVIDIA and Z.ai measured the same model at **34.0** in the OpenHands harness ([Nemotron 3 Nano paper](https://arxiv.org/pdf/2512.20848)) [I,S]. That 27-point swing is larger than the gap between most candidates.

Third, the cross-vendor measurements that do exist come from competitors. IBM's Granite 4.2 figures run Qwen and Gemma through one harness ([granite-4.2 figures](https://github.com/ibm-granite/granite-4.2-language-models)), which is useful but not neutral. Artificial Analysis is the one genuinely independent aggregator, and its index reached the researchers only through snippets:

- Qwen3.6-27B scored 46 and Gemma 4 31B scored 39 ([AA on X](https://x.com/ArtificialAnlys/status/2049881951260283097)).
- In the sub-32B comparison, Gemma 4 26B-A4B scored 31, GLM-4.7-Flash 30 and gpt-oss-20b about 24 ([AA sub-32B](https://artificialanalysis.ai/articles/sub-32b-open-weights)) [I,S].

| Model | Released | Total / active parameters | Native context | License | Ollama tag (download) [S] |
|---|---|---|---|---|---|
| Qwen3.6-35B-A3B | 2026-04-16 | 35B / 3B, MoE with Gated DeltaNet hybrid attention | 262K | Apache 2.0 | `qwen3.6:35b` (23 GB) |
| Qwen3.6-27B | 2026-04-22 | 27B dense | 262K | Apache 2.0 | `qwen3.6:27b` (18 GB) |
| Qwen3.8-27B | 2026-08-14 | 27.78B dense | 262K | Apache 2.0 | `qwen3.8:27b` (18 GB, q4_K_M) |
| Qwen3.5-9B / 4B | 2026-03-02 | 9B / 4B dense | 256K | Apache 2.0 | `qwen3.5:9b` (6.6 GB), `qwen3.5:4b` (3.4 GB) |
| gpt-oss-20b | 2025-08-05 | 21B / 3.6B, MoE, native MXFP4 | 131K | Apache 2.0 | `gpt-oss:20b` (14 GB) |
| GLM-4.7-Flash | Jan 2026 | 30B / 3B, MoE | ~200K [S] | MIT | `glm-4.7-flash` (19 GB) |
| Devstral Small 2 | 2025-12-09 | 24B dense | 256K | Apache 2.0 | `devstral-small-2:24b` (15 GB) |
| Gemma 4 26B-A4B | 2026-04-02 | 25.2B / 3.8B, MoE | 256K | Apache 2.0 | `gemma4:26b` (~14–18 GB) |
| Muse Glimmer | 2026-08-10 | 30B dense | 131K | Apache 2.0 | `muse-glimmer` (18 GB) |
| Qwen3-Coder-Next | 2026-02-04 | 80B / 3B, MoE | 256K | Apache 2.0 | `qwen3-coder-next` (52 GB) |

Sources for the table:

- **Qwen dates and model list:** the official README, fetched directly ([QwenLM/Qwen3.8](https://github.com/QwenLM/Qwen3.8)).
- **gpt-oss specs:** the fetched repository ([openai/gpt-oss](https://github.com/openai/gpt-oss)).
- **Other families:** vendor READMEs and announcements ([zai-org GLM](https://github.com/zai-org/GLM-4.5), [Mistral on X](https://x.com/MistralAI/status/1998407335308358028), [Gemma on Wikipedia](https://en.wikipedia.org/wiki/Gemma_(language_model)), [MarkTechPost on Muse Glimmer](https://www.marktechpost.com/2026/08/10/meta-ai-releases-muse-glimmer/)).
- **Ollama tags and sizes:** library pages seen only as snippets ([qwen3.6](https://ollama.com/library/qwen3.6/tags), [qwen3.5](https://ollama.com/library/qwen3.5/tags), [qwen3.8](https://ollama.com/library/qwen3.8/tags), [gpt-oss](https://ollama.com/library/gpt-oss/tags), [glm-4.7-flash](https://ollama.com/library/glm-4.7-flash/tags), [devstral-small-2](https://ollama.com/library/devstral-small-2/tags), [gemma4](https://ollama.com/library/gemma4/tags), [qwen3-coder-next](https://ollama.com/library/qwen3-coder-next/tags)). Confirm each with `ollama pull` and `ollama show` before relying on it.

| Model | Agentic-coding evidence | JSON / tool-call evidence | Thinking control |
|---|---|---|---|
| Qwen3.6-35B-A3B | SWE-bench Verified 73.4, Terminal-Bench 2.0 51.5 [V,S] | Ollama #17871: with `think:false` and `format:"json"`, the model returned its reasoning as a JSON object on 3 of 14 documents (open) [I] | Thinks by default; `think:false` |
| Qwen3.6-27B | SWE-bench Verified 77.2 and SWE-bench Pro 53.5 [V,S]. IBM measured SWE-bench Pro 40.6 and Terminal-Bench 2.1 56.0 [I] | IBM measured BFCL v4 61.0 and τ³-bench 70.4 [I] | `think:false` |
| Qwen3.8-27B | Terminal-Bench 2.1 73.0, against 63.4 for Qwen3.6-27B; no SWE-bench Verified figure found [V,S] | Ollama #17778: HTTP 500 in multi-step tool loops (open, 44 comments) [I] | Levels low/medium/xhigh, default xhigh; reportedly not settable through Ollama [S] |
| Qwen3.5-9B | No model-specific coding number retrieved | Ollama #18094: under a grammar it silently swaps `"` for `'` [I] | Thinks by default; `think:false` |
| gpt-oss-20b | SWE-bench Verified 60.7 at high reasoning [V]; 34.0 in OpenHands [I,S] | Ollama #17638: tool-call 500s on about 2 in 5 long-argument calls; 8 of 8 valid on llama-server [I] | low/medium/high; cannot be switched off |
| GLM-4.7-Flash | SWE-bench Verified 59.2 [V,S] | τ²-bench 79.5 [V,S]; Ollama #18658 strips newlines from tool-call strings [I] | Thinks by default |
| Devstral Small 2 | SWE-bench Verified 68.0 [V] | Ollama #16932: a tool parameter literally named `name` produces an empty reply [I] | No thinking mode found [E] |
| Gemma 4 26B-A4B | No SWE-bench Verified figure. IBM measured Terminal-Bench 2.1 35.7 and LiveCodeBench 80.3 [I] | IBM measured BFCL v4 64.4 and IFBench 76.3 [I]; Ollama #17562 reports a missing closing brace [I] | May emit a thought channel even with thinking off [S] |
| Muse Glimmer | SWE-bench Verified 76.0 from a single source [V,S] | No local evidence | low → xhigh [S] |

Within those limits, Qwen3.6-35B-A3B is the best balance for Cynqra. Among 3B-active models that fit a 32 GB laptop, it posts the highest vendor agentic-coding score ([Qwen blog](https://qwen.ai/blog?id=qwen3.6-35b-a3b)) [V,S]. It is Apache 2.0, and Ollama documents `"think": false` for every qwen3.6 tag ([Ollama qwen3.6](https://ollama.com/library/qwen3.6)) [S]. The person who reported the Qwen3.8 tool-loop failure also found "no issues with qwen 3.5 or 3.6 27b/35b variants with same code" ([ollama #17778](https://github.com/ollama/ollama/issues/17778)).

Its most relevant open defect is **#17871**:

- **What happens:** with `think:false` plus `format:"json"`, the q8_0 build returned its own reasoning as a syntactically valid but useless object, for example `{"thought": ...}`.
- **How reliably:** deterministically, on 3 of 14 documents at temperature 0.
- **Origin:** a regression between Ollama 0.31.2 and 0.32.14 ([ollama #17871](https://github.com/ollama/ollama/issues/17871)).
- **Likely mitigation (to confirm):** a full JSON Schema in `format` should block that shape, because the grammar then admits only the schema's keys. This is an inference to confirm in testing, not a documented fix.

gpt-oss-20b is the right fallback but the wrong default. In its favor:

- It is smaller: 15.5 GB total at a 32k context, measured by the llama.cpp maintainers ([llama.cpp #15396](https://github.com/ggml-org/llama.cpp/discussions/15396)) [I].
- It ships in native MXFP4 precision, so there is no quantization-loss question.
- It has the richest independent speed data of any candidate.

Against it:

- Its reasoning cannot be switched off; the lowest level is "low" ([Ollama thinking docs](https://github.com/ollama/ollama/blob/main/docs/capabilities/thinking.mdx)).
- It works only through the harmony response format ([openai/gpt-oss](https://github.com/openai/gpt-oss)).
- Its Ollama tool-call path still fails on long arguments, while the same weights on llama-server gave 8 of 8 valid calls at 74 rather than 61 tokens/s ([ollama #17638](https://github.com/ollama/ollama/issues/17638)).

One search summary described a June 2026 "gpt-oss-8b" under a new license. OpenAI's repository contradicts it: it lists only the 20b and 120b models, under Apache 2.0 ([openai/gpt-oss](https://github.com/openai/gpt-oss)).

The dense 27B Qwens are the quality upgrade, not the default. Qwen3.6-27B beats the 35B-A3B on vendor SWE-bench Verified (77.2 against 73.4) and has the highest Artificial Analysis index score reported for any laptop-class model (46). But a community test found the 35B-A3B **3.5–4× faster at generation and 2–2.4× faster at prompt processing** ([zoliben](https://zoliben.com/en/posts/2026-04-23-qwen-36-35b-vs-27b-benchmark-results/)) [S].

Qwen3.8-27B, released 14 August 2026, reports large vendor gains ([kingy.ai](https://kingy.ai/blog/qwen3-8-27b-specs-benchmarks-local-hardware/)) [V,S], but it has three open problems:

- Under Ollama it throws HTTP 500 in tool loops (#17778).
- A secondary source says Ollama's generic template prevents setting its reasoning effort ([NxCode](https://www.nxcode.io/resources/news/qwen3-8-27b-local-agent-model-2026)) [S].
- A Hugging Face thread is titled "This model cannot stop thinking" ([HF discussion #113](https://huggingface.co/Qwen/Qwen3.8-27B/discussions/113)).

It belongs on llama-server with `--jinja` until those settle.

Outside the Qwen family, four models earn a bake-off slot, and none displaces the default:

- **GLM-4.7-Flash** has the same 30B-A3B shape, an MIT license and a vendor SWE-bench Verified score of 59.2 ([Medium summary of Z.ai's card](https://medium.com/@zh.milo/glm-4-7-flash-the-ultimate-2026-guide-to-local-ai-coding-assistant-93a43c3f8db3)) [V,S].
- **Devstral Small 2** scores 68.0 [V] and has no thinking mode to fight, but it runs at dense-24B speed ([Cline](https://cline.bot/blog/devstral-2-release)).
- **Gemma 4 26B-A4B** leads IBM's tool-use measurements. However, it carries open tool-call bugs in both Ollama and llama.cpp, and Google's own docs say it "may occasionally generate a thought channel even when thinking mode is explicitly turned off" ([Gemma 4 prompt formatting](https://ai.google.dev/gemma/docs/core/prompt-formatting-gemma4)) [S].
- **Muse Glimmer**'s 76.0 rests on one snippet ([DataCamp](https://www.datacamp.com/blog/muse-glimmer)) [S], and Artificial Analysis's write-up has Qwen3.6-27B winning four of seven comparable rows ([AA on Muse Glimmer](https://artificialanalysis.ai/articles/muse-glimmer)) [I,S].

Clearly weaker for this job:

- **Nemotron 3 Nano:** IBM measured a Terminal-Bench 2.1 score of **7.2** ([granite-4.2 8B figure](https://github.com/ibm-granite/granite-4.2-language-models/blob/main/figures/8b-comparison.png)), a red flag for fix-from-test-output loops.
- **Nemotron 3.5 Lightning:** trails Qwen3.6-35B-A3B on 11 of 12 rows in NVIDIA's own table ([digitalapplied](https://www.digitalapplied.com/blog/nvidia-nemotron-3-5-lightning-30b-a3b-efficiency-tier-2026)) [V,S].
- **The 2025 Qwen3-Coder-30B-A3B and Qwen3-30B-A3B-2507:** superseded at the same footprint.
- **Gemma 3 27B:** 4.9% on Aider polyglot ([Aider leaderboard data](https://github.com/Aider-AI/aider/blob/main/aider/website/_data/polyglot_leaderboard.yml)).

Qwen3-Coder-Next (52 GB at Q4) and gpt-oss-120b (65 GB) are beyond laptop range.

## Memory sets the tier and active parameters set the wait

Resident memory is roughly the sum of four parts:

- the weights;
- the KV cache, which holds the attention state for every token in the context;
- about 1 GB of compute buffers;
- the operating system and running apps. On Windows 11, a browser and an IDE typically hold 4–6 GB on their own [E].

The one measured anchor is gpt-oss-20b: 12.0 GB of model data, reaching 14.9 GB total at 8k context and **15.5 GB at 32k** ([llama.cpp #15396](https://github.com/ggml-org/llama.cpp/discussions/15396)) [I]. The 2026 hybrid-attention models shrink the KV term sharply. Qwen3.8-27B measures **34 KiB per token** with a q8_0 KV cache ([llama.cpp #23470](https://github.com/ggml-org/llama.cpp/discussions/23470)) [I]. A conventional dense 24B needs roughly 160 KiB per token at f16 [E].

Apple Silicon adds a trap. By general knowledge the notes could not verify, macOS lets the GPU use only about two-thirds of unified memory on machines with 36 GB or less and about three-quarters above that; the limit is adjustable with `sysctl iogpu.wired_limit_mb`. Under that assumption a 32 GB Mac gives the GPU about 21 GB, which is less than `qwen3.6:35b` needs.

| Ollama tag | Download [S] | KV cache at 32k (f16) | Resident at 32k [E] | Where it fits [E] |
|---|---|---|---|---|
| `qwen3.5:4b` | 3.4 GB | not measured | ~5–7 GB | every tier |
| `qwen3.5:9b` | 6.6 GB | ≤4.5 GiB (upper bound from Qwen3-8B's conventional layout) | ~8–12 GB | 16 GB machines at 24k context with q8_0 KV |
| `gpt-oss:20b` | 14 GB | 0.75 GiB | **15.5 GB, measured [I]** | 32 GB+; 16 GB machines only with a 6–8 GB GPU sharing the load; 24 GB Macs only with a raised GPU limit |
| `qwen3.6:27b`, `qwen3.8:27b` | 18 GB | ~2.1 GiB, from the measured 34 KiB/token at q8_0 | ~21 GB | 32 GB Windows/Linux; borderline on 32 GB Macs; comfortable at 48 GB+ |
| `qwen3.6:35b` | 23 GB | ~0.8 GiB, from a snippet's "~200MB per slot at 8K" ([7minai](https://7minai.com/qwen-3-6-local-coding/)) [S] | ~25 GB | 32 GB Windows/Linux with a lean desktop; 32–36 GB Macs only after raising the GPU limit; comfortable at 48 GB+ |
| `devstral-small-2:24b` | 15 GB | ~5 GiB, if it keeps Mistral Small 3.1's layout | ~21 GB | 32 GB+, but at dense-24B speed |
| `gemma4:26b` | ~14–18 GB | ~0.65 GiB, scaled from 5.2 GiB at 262k ([Kaitchup](https://kaitchup.substack.com/p/gemma-4-31b-and-26b-a4b-architecture)) [S] | ~16–20 GB | 32 GB+ |
| `qwen3-coder-next` | 52 GB | — | >53 GB | above the default GPU share even on 64 GB Macs |

Speed splits along two physical limits.

- **Generation is limited by memory bandwidth** divided by the bytes of *active* weights, so a 3B-active MoE generates like a small dense model. On the same Ryzen AI 9 HX 370 CPU, an 80B-A3B MoE generated at **7.74 tokens/s** against **3.54 tokens/s** for a dense 32B ([llama.cpp #19480](https://github.com/ggml-org/llama.cpp/issues/19480)) [I].
- **Prompt processing (prefill) is limited by compute.** It runs at thousands of tokens/s on NVIDIA GPUs and hundreds on M-series Pro/Max chips, but only tens to low hundreds on laptop CPUs.

Measured gpt-oss-20b anchors from the llama.cpp guide [I]:

| Hardware | Prefill at 8k (tokens/s) | Generation (tokens/s) |
|---|---|---|
| M1 Pro 32 GB | 437 | 45.7 |
| M4 Max | 1,030 | 92.4 |
| RTX 3090 | 5,170 | 162 |

The M5 generation delivers roughly **3.5×** the prefill speed of the M4 at similar bandwidth ([llama.cpp #4167](https://github.com/ggml-org/llama.cpp/discussions/4167)) [I]. On an ultraportable CPU, a dense 14B generated at just **5.83 tokens/s** (Framework 13, Ryzen AI 5 340) ([geerlingguy/ai-benchmarks](https://github.com/geerlingguy/ai-benchmarks)) [I].

The per-call estimates below assume 10k tokens in and 2k tokens out. They exclude model load time (5–30 s on the first call) and any thinking tokens. The `qwen3.6:35b` row borrows Qwen3-30B-A3B's figures, since both have about 3B active parameters.

| Tier and example hardware | Model | Per call [E] | Per 15–30-call run [E] |
|---|---|---|---|
| 16 GB CPU-only (Zen 4/5 or Core Ultra) | dense 8–9B (`qwen3.5:9b`) | 5.5–9 min | 1.4–4.5 h |
| 16 GB + RTX 4060/4070 Laptop, 8 GB | dense 8–9B fully on GPU | 1–1.2 min | 15–36 min |
| same | `gpt-oss:20b` split across GPU and CPU | 1–2 min | 15–60 min |
| 32 GB CPU-only | `gpt-oss:20b` | 2.2–4.3 min | 33 min–2.2 h |
| same | 30–35B-A3B MoE (`qwen3.6:35b`) | 2.8–5.6 min | 42 min–2.8 h |
| same | dense 24–27B | 16–27 min | impractical |
| Mac M1/M2, 16 GB | dense 8B | 3–5 min | 45 min–2.5 h |
| Mac M4, 16 GB | dense 8B | 2.5–3 min | 38 min–1.5 h |
| Mac M1 Pro, 32 GB | `gpt-oss:20b` (measured base rates) | ~1.2 min | 18–36 min |
| Mac M4 Pro, 32 GB | 3–3.6B-active MoE | 45–55 s | 11–28 min |
| Mac M4 Max, 64 GB | 3–3.6B-active MoE | ~33 s | 8–17 min |
| same | dense 24B | 2–2.3 min | 30 min–1.2 h |

The runtime can erase much of that budget. Three reports show large gaps against Ollama:

| Setup | Ollama | Alternative |
|---|---|---|
| Qwen3.5-35B-A3B on an M4 Max ([benchmark](https://antekapetanovic.com/blog/qwen3.5-apple-silicon-benchmark/)) [S] | 40–46 tokens/s | ~70 on llama.cpp; 108–115 on MLX |
| RTX 3090 Ti on Windows ([ollama #14579](https://github.com/ollama/ollama/issues/14579)) [I] | 15–20 tokens/s | ~100 on llama.cpp |

The Windows report cites an Ollama version inconsistent with its date.

Since v0.30.0 (June 2026), Ollama runs upstream `llama-server` as a subprocess for every GGUF model ([commit 9db4bdba](https://github.com/ollama/ollama/commit/9db4bdba)), so the older gaps have probably narrowed. A post-0.30 report still found gpt-oss at 61 against 74 tokens/s (#17638), so the team should measure rather than assume.

Two workload details move the numbers further:

- **Thinking tokens are invisible output.** They are billed against generation time, which is why this report turns thinking off for the JSON roles.
- **Prefix caching can cut prefill sharply.** Ollama reports reused prompt tokens as `prompt_eval_cached_count` ([usage docs](https://github.com/ollama/ollama/blob/main/docs/api/usage.mdx)). With one server slot (`OLLAMA_NUM_PARALLEL=1`), four alternating roles will keep overwriting each other's cache unless every role's prompt opens with the same shared block: project spec, current files, then role-specific instructions. That ordering is an inference, but on CPU tiers, where a 10k-token prefill costs 2–4 minutes, it is the cheapest speed-up available.

## Ollama offers the most control but ships defaults that truncate silently

| | Ollama ≥ 0.34.4 | llama.cpp `llama-server` (b11201) | LM Studio 0.4.x | vLLM 0.30.0 |
|---|---|---|---|---|
| License and install | MIT; no-admin Windows installer, macOS dmg, Linux script; runs as a background service | MIT; `winget` or `brew`; user picks the GGUF file and flags | Proprietary; free for personal and internal work, no redistribution or SaaS; GUI plus headless `llmster` | Python package aimed at GPU servers |
| Strict JSON | `format` = JSON Schema, compiled to a GBNF grammar by llama-server since v0.30.0; `response_format` on `/v1` | `json_schema` or `grammar` fields; `response_format` on `/v1/chat/completions` | `response_format` `json_schema`; llama.cpp grammars for GGUF, Outlines for MLX; warns that models under 7B may fail | `response_format` or `structured_outputs`; xgrammar, guidance, outlines or lm-format-enforcer; `guided_*` removed in v0.12.0 |
| Default context | 4,096 under 24 GiB VRAM, 32,768 at 24–48 GiB, 262,144 at ≥48 GiB (since v0.15.5) | `-c 0` = model's trained context, shrunk by `--fit` to fit memory (floor 4,096) | set at load time (`context_length`); API default not found | not researched |
| Overflow behaviour | Silent: drops the oldest messages; an overlong single prompt keeps its first 4 tokens and drops the middle, with only a log warning; `shift:false` returns HTTP 400 | Error `exceed_context_size_error`; context shift is off by default | not documented in the sources | not researched |
| Per-request context size | yes, through `options.num_ctx` on the native API only | no, server flag | no, load time | no |
| Thinking control | `think`: true, false or a level; reasoning returned in `message.thinking` | `--reasoning`, `--reasoning-budget`, `--reasoning-format`; per request `chat_template_kwargs` or `reasoning_effort:"none"` | gpt-oss reasoning in `message.reasoning`; `reasoning.effort` on `/v1/responses` | `--reasoning-parser qwen3`; structured output can switch off for Qwen3-Coder models if the reasoning is not parsed separately |
| Live bugs relevant here | #17871, #17778, #18094, #17638, #18658 | Gemma 4 trailing garbage (#28827); q4 KV prefill collapse on Qwen hybrid models (#29371) | none found | extra text after the JSON with gpt-oss [S] |

Sources for the table:

- **Ollama:** [install docs](https://github.com/ollama/ollama/blob/main/docs/windows.mdx), [context-length docs](https://github.com/ollama/ollama/blob/main/docs/context-length.mdx), [prompt.go](https://github.com/ollama/ollama/blob/main/server/prompt.go), [llama_server.go](https://github.com/ollama/ollama/blob/main/llm/llama_server.go).
- **llama-server:** the [server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) and [llama.cpp #29371](https://github.com/ggml-org/llama.cpp/issues/29371).
- **LM Studio:** [structured-output docs](https://github.com/lmstudio-ai/docs/blob/main/1_developer/3_openai-compat/structured-output.md) and ["free for work"](https://lmstudio.ai/blog/free-for-work).
- **vLLM:** [structured-output docs](https://github.com/vllm-project/vllm/blob/main/docs/features/structured_outputs.md).

The context default is the most dangerous. Since v0.15.5 (February 2026), Ollama sizes its default context by VRAM, not by model ([commit 0334ffa6](https://github.com/ollama/ollama/commit/0334ffa6)), so almost every laptop gets **4,096 tokens**. Ollama's FAQ still says 4,096 for everyone, which the code contradicts. A 16k-token Cynqra prompt then overflows, and overflow is silent by default:

- For chat history, `truncate` defaults to true and drops messages from the front, keeping the system and latest messages.
- For a single overlong prompt, context shift (on for nearly every model) keeps the first `num_keep` tokens, 4 by default, and discards the middle, logging only a warning ([sched.go](https://github.com/ollama/ollama/blob/main/server/sched.go); [api/types.go](https://github.com/ollama/ollama/blob/main/api/types.go)).

Either way the model can lose the very schema and instructions it is supposed to follow. Setting `"shift": false` makes the runner return HTTP 400 instead. That behaviour is read from the code and must be tested on v0.34.4.

The OpenAI-compatible `/v1/chat/completions` endpoint "does not have a way of setting the context size" ([Ollama OpenAI compatibility](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx)). That alone is reason to call the native `/api/chat`. By contrast, llama-server refuses an overlong request with an error ([server-context.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/server-context.cpp)), which is the safer default.

Structured output is solid when used as documented:

- **Two modes.** `"format": "json"` guarantees only *some* well-formed object. `"format": {schema}` (v0.5.0+) constrains decoding to the schema ([Ollama API docs](https://github.com/ollama/ollama/blob/main/docs/api.md)).
- **Escaping.** The grammar's string rule forbids raw control characters and unescaped quotes, so every newline in a Python file is emitted as `\n`, and `json.loads` restores the exact text ([json-schema-to-grammar.cpp](https://github.com/ggml-org/llama.cpp/blob/master/common/json-schema-to-grammar.cpp)).
- **Whitespace.** The schema grammar caps whitespace; the built-in `json` grammar does not, which is the pattern behind historical "endless whitespace" reports.
- **Unsupported keywords are skipped silently** ([grammars README](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)).
- **Known Ollama schema bugs:** a `pattern` keyword makes the schema fail ([#12726](https://github.com/ollama/ollama/issues/12726)), key order is not preserved ([#8461](https://github.com/ollama/ollama/issues/8461)), and top-level arrays are mishandled ([#8000](https://github.com/ollama/ollama/issues/8000)).
- **Residual risk: the escaping burden itself.** Under grammar constraint, `qwen3.5:9b` and `gemma4:e4b` silently replaced double quotes with single quotes, producing "schema-valid but content-altered output with no error" ([ollama #18094](https://github.com/ollama/ollama/issues/18094)). Python source inside a JSON string is exactly that case.

Thinking combined with `format` had been fragile for a year. Fixes landed in stages:

- **v0.12.4** fixed structured output for gpt-oss.
- **v0.21.1** fixed Gemma 4 ignoring the format when `think:false`.
- **v0.31.2** (July 2026) applied the format under `think:false` for all models' thinking parsers ([commit 892e7f6b](https://github.com/ollama/ollama/commit/892e7f6b)).
- **v0.34.4** (tagged 23 September 2026) finally generates in a single pass: thinking is left unconstrained and only the content after the end-of-thinking marker is constrained ([commit 5a0ff311](https://github.com/ollama/ollama/commit/5a0ff311); [PR #18479](https://github.com/ollama/ollama/pull/18479)).

That code is three days old at the time of writing. Separately, Ollama's MLX engine had two JSON bugs in the same month:

- a stray "." prefix on the JSON ([#18441](https://github.com/ollama/ollama/issues/18441));
- whitespace that "never terminates" until `num_predict` is reached ([#18567](https://github.com/ollama/ollama/issues/18567)).

Cynqra should therefore use GGUF tags, not the `-mlx` variants, for strict JSON.

Two more design decisions follow from the evidence:

- **Use `format`, not tool calls.** Almost every open bug above lives in per-model tool-call parsers: gpt-oss harmony (#17638), Qwen3.8 tool loops (#17778), GLM newline trimming ([#18658](https://github.com/ollama/ollama/issues/18658)), Devstral's `name` parameter ([#16932](https://github.com/ollama/ollama/issues/16932)) and the Gemma 4 renderer ([PR #18503](https://github.com/ollama/ollama/pull/18503)). Cynqra needs one JSON object per call, so requesting it through `format` sidesteps that whole class of failures.
- **Treat the other runtimes as escape hatches.** llama-server is the fix for gpt-oss tool calls and for Qwen3.8's thinking controls. LM Studio suits individuals who install it themselves but cannot be bundled or redistributed ([Simon Willison](https://simonwillison.net/2025/Jul/8/lm-studio-is-free-for-use-at-work/)). vLLM belongs on a shared NVIDIA server, where Qwen's README prescribes `--reasoning-parser qwen3 --tool-call-parser qwen3_coder` ([QwenLM/Qwen3.8](https://github.com/QwenLM/Qwen3.8)).

## Pin one model per tier and every field of every request

On 32 GB tiers nothing larger than `qwen3.6:35b` fits, so the "upgrade" column trades speed for quality rather than adding size.

| Laptop tier | Default | Smaller fallback | Upgrade | `num_ctx` / `num_predict` |
|---|---|---|---|---|
| 16 GB Windows/Linux (CPU-only or ≤8 GB GPU); 16–24 GB Macs | `qwen3.5:9b` | `qwen3.5:4b` | `gpt-oss:20b` with `think:"low"`, only with a 6–8 GB NVIDIA GPU or on a 24 GB Mac with a raised GPU limit | 24576 / 6144, plus `OLLAMA_KV_CACHE_TYPE=q8_0` |
| 32 GB Windows/Linux | `qwen3.6:35b` | `gpt-oss:20b` | `qwen3.6:27b`: dense, stronger on vendor numbers, 3.5–4× slower; use where long runs are acceptable | 32768 / 8192 |
| 32–36 GB Macs | `qwen3.6:35b`, once `ollama ps` shows 100% GPU (raise the wired-memory limit if not) | `gpt-oss:20b` | `qwen3.6:27b` | 32768 / 8192 |
| 48–64 GB Macs | `qwen3.6:35b` | `gpt-oss:20b` | `qwen3.6:27b`; `qwen3.8:27b` via llama-server `--jinja` once its thinking control is verified | 32768 / 8192 (65536 is affordable) |

Why 32,768 tokens:

- It covers a 16k prompt plus an 8k answer with margin.
- Ollama's docs recommend "at least 64000 tokens" for coding tools ([context-length docs](https://github.com/ollama/ollama/blob/main/docs/context-length.mdx)), but Cynqra's calls are bounded single shots, and doubling the context doubles the KV memory on machines that are already tight.
- The client should estimate prompt tokens before sending and refuse any call where the estimate plus `num_predict` exceeds `num_ctx`.

Every call goes to the native endpoint with these fields:

```json
POST http://127.0.0.1:11434/api/chat
{
  "model": "qwen3.6:35b",
  "messages": [
    {"role": "system", "content": "<shared project context> <role instructions> Reply with ONE JSON object matching this schema: <schema text>"},
    {"role": "user", "content": "<task, current files, failing test output>"}
  ],
  "stream": false,
  "format": {"type": "object", "properties": {"...": "..."}, "required": ["..."], "additionalProperties": false},
  "think": false,
  "shift": false,
  "truncate": false,
  "keep_alive": "30m",
  "options": {"num_ctx": 32768, "num_predict": 8192, "temperature": 0, "seed": 42}
}
```

Every field name is verified against Ollama's docs and code ([api.md](https://github.com/ollama/ollama/blob/main/docs/api.md); [structured outputs](https://github.com/ollama/ollama/blob/main/docs/capabilities/structured-outputs.mdx)).

**Temperature 0** overrides the built-in 0.8 ([api/types.go](https://github.com/ollama/ollama/blob/main/api/types.go)) and follows Ollama's structured-output advice. At temperature 0, though, a retry of the same prompt repeats the same mistake. Retries should therefore append the validation or test error and raise the temperature to about 0.4. That value is an estimate to tune in the bake-off.

**Per-model overrides:**

- `gpt-oss:20b` takes `"think": "low"`, because "false" is not among its levels.
- The 16 GB tier uses the smaller `num_ctx` and `num_predict` from the table, and should ask engineers for one file per call.

**Schema rules:**

- Keep a top-level object.
- Set `required` and `additionalProperties: false`.
- Do not use `pattern`, `format:"uri"`, top-level arrays or `maxLength` on code strings.
- Repeat the schema text in the prompt, as Ollama advises.

**Server-side settings:**

- Require Ollama **≥ 0.34.4**, checked at startup with `GET /api/version`.
- Leave `OLLAMA_NUM_PARALLEL=1`, because parallel slots multiply KV memory ([FAQ](https://github.com/ollama/ollama/blob/main/docs/faq.mdx)).
- Set `OLLAMA_CONTEXT_LENGTH=32768` so that `/v1` or ad-hoc clients are not stuck at 4,096.
- Optionally set `OLLAMA_KV_CACHE_TYPE=q8_0`. This needs flash attention, which Ollama enables automatically where supported. Across three models on 500 questions, q8_0 changed at most 4 answers; q4_0 changed **375 of 500** on Qwen2.5-7B ([llama.cpp #23470](https://github.com/ggml-org/llama.cpp/discussions/23470)) [I], and it collapses prefill on Qwen hybrid models (#29371). Use q8_0 and never q4_0.

**The client** is standard-library only:

- Use a urllib timeout of at least 1,800 s on CPU tiers, or stream with a total deadline.
- Treat each of these as retryable: `done_reason` other than `"stop"`, empty content, a `json.loads` failure, a missing key, a `compile()` failure on any Python string, or HTTP 400.
- Log `prompt_eval_count`, `prompt_eval_cached_count`, `eval_count` and the durations on every call.
- Switch to the fallback model per run, never per call. On 32 GB machines both models cannot stay loaded, so every switch pays a multi-gigabyte reload.
- For LM Studio (port 1234) or llama-server (port 8080), keep a `/v1/chat/completions` adapter that sends `response_format: {"type":"json_schema","json_schema":{"name":"result","strict":true,"schema":{...}}}`. Disable thinking with `chat_template_kwargs: {"enable_thinking": false}` or `reasoning_effort: "none"`. The context size is set at server or model load (`-c 32768`, or LM Studio's `context_length`).

## Ten risks the laptop bake-off has to retire

Nothing above has been run on the team's laptops, and no independent 2026 study compares these models on strict JSON or multi-file Python. Before committing, the team should test each risk below on at least one machine per tier. The pass bars are suggested thresholds [E].

| # | Risk | Evidence | Test | Pass bar [E] |
|---|---|---|---|---|
| 1 | Context silently truncated | 4,096-token default and silent truncation ([context docs](https://github.com/ollama/ollama/blob/main/docs/context-length.mdx)) | Send a 16k-token prompt and compare `prompt_eval_count` with the app's estimate; send an oversize prompt with `shift:false` and confirm HTTP 400 | Zero silent truncations |
| 2 | Reasoning leaks into the JSON | [#17871](https://github.com/ollama/ollama/issues/17871); Gemma 4 thought channel; Qwen3.8 "cannot stop thinking" | 50 calls per role with `think:false`; count non-empty `message.thinking` and schema failures | ≥98% schema-valid on the first attempt |
| 3 | Code altered inside valid JSON | Quote swapping ([#18094](https://github.com/ollama/ollama/issues/18094)); newline stripping ([#18658](https://github.com/ollama/ollama/issues/18658)) | Have the model echo a known 200-line Python file verbatim inside the schema; diff it; run `ast.parse` on every file | Byte-identical in ≥19 of 20 attempts |
| 4 | Output cut off at `num_predict` | Truncated tool calls reported as complete ([#17562](https://github.com/ollama/ollama/issues/17562)) | Log `done_reason` and `eval_count` on every engineer call | `"length"` on <2% of calls, recovered by retry |
| 5 | Memory pressure and swapping | Estimated 21–25 GB for the 27B/35B tags against 32 GB machines | Run with the IDE and browser open; check `ollama ps` for 100% GPU versus a CPU/GPU split, and watch OS memory pressure | No swapping; 100% GPU on Macs |
| 6 | Speed far below the estimates | Ollama vs llama.cpp gaps ([#14579](https://github.com/ollama/ollama/issues/14579), [#17638](https://github.com/ollama/ollama/issues/17638)) | Time full runs; repeat one run on llama-server with the same GGUF file | Runs fit the team's time budget |
| 7 | Thermal and battery throttling | 9.87 against 13.41 tokens/s on battery vs mains ([Framework 13 test](https://msf.github.io/blogpost/local-llm-performance-framework13.html)) [S] | 30 back-to-back calls, on battery and on mains | Document the gap; require mains power if it exceeds 25% |
| 8 | Runner instability over long loops | 72% crash rate across 138 runs in an older release ([#15923](https://github.com/ollama/ollama/issues/15923)); lost end-of-sequence under concurrency ([#18442](https://github.com/ollama/ollama/issues/18442)) | Five full runs back to back with `OLLAMA_NUM_PARALLEL=1` | No crashes or hangs |
| 9 | Fix loop stalls at temperature 0 | Deterministic decoding repeats the same patch (inference) | Rounds-to-green with retries at temperature 0 versus 0.4 | Most tasks go green within 3 rounds |
| 10 | Version drift | The thinking-plus-format path was rewritten on 2026-09-23 ([commit 5a0ff311](https://github.com/ollama/ollama/commit/5a0ff311)) | Pin the Ollama version and model digests; rerun the micro-benchmark after any upgrade | Results unchanged after an upgrade |

The bake-off should run in two stages, because full runs are expensive. Seven models × 10 tasks × 3 repeats × 20 minutes would take about 70 machine-hours.

**Stage 1** is a cheap micro-benchmark:

- **Models:** `qwen3.6:35b`, `gpt-oss:20b`, `qwen3.5:9b`, `qwen3.6:27b`, `glm-4.7-flash`, `devstral-small-2:24b` and `gemma4:26b`. Optionally add `qwen3.8:27b` on llama-server.
- **Calls:** each model answers 50 calls per role, using Cynqra's real CTO, PM and engineer schemas.
- **Measures:** schema-validity rate, `ast.parse` rate, verbatim-echo fidelity (risk 3), `done_reason` distribution, tokens and seconds per call.
- **Second arm for engineer calls:** grammar-constrained `format` against unconstrained output that is validated and retried. If grammar pressure corrupts code, as #18094 suggests it can, the unconstrained arm will show it.

**Stage 2** runs the top three models end to end:

- **Tasks:** the JSON-file store, the `http.server` app and the `unittest` suite.
- **Repeats:** five tasks, three runs each, on one machine per tier.
- **Recorded per run:** final test pass rate, fix rounds needed, wall-clock time and peak memory.
- **Decision rule:** choose the fastest model within a few points of the best green rate, and keep the harness so the test can be rerun when the next model ships.

## Conclusion

The research changes where the risk lies. The choice between plausible 2026 models matters less than the plumbing around them. On paper, several candidates can write a small standard-library module and fix it from test output. What breaks runs in practice is a 4,096-token default, silent middle truncation, tool-call parsers that change strings, grammars that swap quotes, and thinking-plus-format code three days old. That makes the team's first deliverable a model-agnostic, validating client: version check, explicit context sizing, `done_reason` handling, `compile()` and test execution. Once that exists, swapping `qwen3.6:35b` for next month's release costs one tag change and one bake-off rerun.

Since v0.30.0, Ollama has been a manager wrapped around llama-server. Choosing between the two is now about templates, parsers and defaults rather than inference speed, so a thin `/v1` adapter gives the team a way around per-model bugs without rewriting anything.

The tier analysis also shows that 16 GB CPU-only laptops cannot give an interactive proof of concept, at 1.4–4.5 hours per run. Those machines are better used as clients of a teammate's 48–64 GB Mac or a shared GPU box. That server must be started with `OLLAMA_HOST` set to listen beyond its default 127.0.0.1 ([Ollama FAQ](https://github.com/ollama/ollama/blob/main/docs/faq.mdx)), and exposed only on a trusted network. The 16 GB machines are also better used as overnight runners than as the platform the demo depends on. Open-weight releases arrived monthly through 2026, so the bake-off harness is worth more than any single verdict in this report.
