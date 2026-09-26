# Local open-weight LLMs on ordinary laptops: memory needs and speed (as of September 2026)

Research date: 2026-09-26. Workload assumed throughout: 15-30 calls per run, prompts 3k-16k tokens, outputs 500-4000 tokens (JSON with Python files), context of at least 16k-32k.

**Source-access note for the report writer.** This session's network proxy blocked huggingface.co, ollama.com, arxiv.org, unsloth.ai, localscore.ai, reddit and most blogs. Only GitHub pages were fetched in full: llama.cpp discussions and issues, the Ollama docs in the ollama/ollama repo, the openai/gpt-oss README, the QwenLM READMEs, the google-deepmind/gemma source and the geerlingguy/ai-benchmarks README. Anything marked **(snippet)** comes only from a search-engine summary of a page that could not be opened, so treat it as lower confidence. Anything marked **ESTIMATE** is my own calculation, and the derivation is shown.

---

## 1. File size, RAM/VRAM needs (including KV cache at 16k/32k) and fit in 16 / 32 / 64 GB

### Takeaway
- **16 GB laptops:** Q4_K_M dense 7-8B models (Qwen3-8B, Qwen2.5-Coder-7B) fit with a 16k-32k context. 14B models are tight: they fit at 16k but not comfortably at 32k on Windows.
- **Not in 16 GB:** gpt-oss-20b needs about 15.5 GB at 32k (measured), and Qwen3-30B-A3B/Coder-30B needs about 22 GB at 32k (ESTIMATE). Neither fits in 16 GB of system RAM alongside Windows. gpt-oss-20b does fit on a 16 GB laptop that also has a 6-8 GB GPU, by splitting experts between GPU and CPU.
- **32 GB:** every listed model fits, including the 3B-active MoEs and Devstral 24B.
- **64 GB Macs:** everything fits comfortably, including the 2026 Qwen3.6-35B-A3B and 27B dense models.

### Cited Findings

**Official memory statements**
- The gpt-oss README says: "The models were post-trained with MXFP4 quantization of the MoE weights, making gpt-oss-120b run on a single 80GB GPU ... and the gpt-oss-20b model run within 16GB of memory." — [openai/gpt-oss README](https://github.com/openai/gpt-oss/blob/main/README.md)
- The llama.cpp gpt-oss guide (by the llama.cpp maintainers, August 2025) gives this memory table for gpt-oss-20b. Model data is 12.0 GB, compute buffers 2.7 GB, KV cache per 8,192 tokens 0.2 GB. The total is 14.9 GB at 8,192 tokens and 15.5 GB at 32,768 tokens. For gpt-oss-120b, model data is 61.0 GB and the total is 64.0 GB at 8,192 tokens. — [llama.cpp discussion #15396](https://github.com/ggml-org/llama.cpp/discussions/15396)

**Download sizes in Ollama (default tag, about Q4_K_M)** (snippet: ollama.com was blocked, so these come from aggregator pages)
- qwen3:8b 5.2 GB, gemma3:12b 8.1 GB, qwen3-coder:30b 18 GB (one source says 19 GB), devstral:24b 14 GB, qwen3:14b about 9 GB. — [ComputingForGeeks Ollama cheat sheet](https://computingforgeeks.com/ollama-models-cheat-sheet/), [Morph best Ollama models](https://www.morphllm.com/best-ollama-models) (snippet)
- "Qwen3:30b is a 19GB download; plan for 32GB+ of system memory." — [LocalAIMaster CPU-only guide](https://localaimaster.com/blog/run-llm-cpu-only) (snippet)
- A secondary sizing site says gpt-oss-20b "Q4_K_M requires 17.3 GB", which exceeds an 8 GB RTX 4060. — [willitrunai](https://willitrunai.com/can-run/gpt-oss-20b-on-rtx-4060-8gb) (snippet). This conflicts with the llama.cpp guide's 12.0 GB of model data for the native MXFP4 file. Prefer the llama.cpp figure: gpt-oss should be run in its native MXFP4, not re-quantized to Q4_K_M.

**Architecture parameters used for the KV math (section 4)**
- **gpt-oss-20b:** 24 layers, 64 query heads, 8 KV heads. Layers alternate between dense attention and a 128-token sliding window. MoE with 32 experts, top-4 routing, 3.6B active parameters. — [gpt-oss model card](https://cdn.openai.com/pdf/419b6906-9da6-406c-a19d-1bb078ac7637/oai_gpt-oss_model_card.pdf) (snippet)
- **Qwen3 family** (per the Qwen3 technical report): Qwen3-8B has 36 layers and 8 KV heads; Qwen3-14B has 40 layers and 8 KV heads; Qwen3-30B-A3B has 48 layers and 4 KV heads. — [Qwen3 Technical Report](https://arxiv.org/pdf/2505.09388) (snippet)
- **Qwen2.5-Coder:** the 14B has 48 layers, 40 query heads and 8 KV heads. The 7B has 28 layers, 28 query heads and 4 KV heads. Both support 131,072 tokens of context. — [Qwen2.5-Coder-14B model card](https://huggingface.co/Qwen/Qwen2.5-Coder-14B), [Qwen2.5-Coder-7B model card](https://huggingface.co/Qwen/Qwen2.5-Coder-7B) (snippet)
- **Qwen3-Coder:** "native support for 256K tokens, extendable up to 1M tokens using Yarn". — [QwenLM/Qwen3-Coder README](https://github.com/QwenLM/Qwen3-Coder)
- **Mistral Small 3.1 24B (the base of Devstral Small):** 40 layers, head dimension 128, 32 attention heads, 8 KV heads, 128k context. — [Mistral-Small-3.1-24B model card](https://huggingface.co/mistralai/Mistral-Small-3.1-24B-Instruct-2503) (snippet)
- **Gemma 3** (from Google's reference implementation):
  - 12B: 48 layers, 16 heads, head_dim 256, 8 KV heads, sliding_window_size 1024.
  - 27B: 62 layers, 32 heads, head_dim 128, 16 KV heads, sliding_window_size 1024.
  - Attention pattern: 5 LOCAL_SLIDING layers followed by 1 GLOBAL layer.
  - Source: [google-deepmind/gemma `_gemma.py`](https://github.com/google-deepmind/gemma/blob/main/gemma/gm/nn/_gemma.py)

**2026 laptop-class models**
- **Qwen3.5, 3.6 and 3.8 releases** (from the official Qwen GitHub README):
  - 2026-02-24: Qwen3.5-35B-A3B and Qwen3.5-27B.
  - 2026-03-02: Qwen3.5-9B, 4B, 2B and 0.8B.
  - 2026-04-16: Qwen3.6-35B-A3B.
  - 2026-04-22: Qwen3.6-27B.
  - 2026-08-14: Qwen3.8-27B.
  - Architecture: "Gated Delta Networks combined with sparse Mixture-of-Experts". — [QwenLM Qwen3.5/3.6/3.8 README](https://github.com/QwenLM/Qwen3.6)
- **Qwen3.6-35B-A3B architecture:** it "mixes Gated DeltaNet (linear attention) + Gated Attention + sparse MoE". It has 256 experts, with 8 routed and 1 shared expert active. The model needs "~200MB of KV cache per ... slot at 8K context". — [7minai](https://7minai.com/qwen-3-6-local-coding/) (snippet, secondary)
- **Measured KV size of a 2026 hybrid model:** Qwen3.8-27B at 65K context uses 34 KiB/token with q8_0/q8_0 KV and 26 KiB/token with q8_0/q4_0. — [llama.cpp discussion #23470](https://github.com/ggml-org/llama.cpp/discussions/23470)
- **Gemma 4:**
  - Released 2026-04-02 under Apache 2.0.
  - Sizes: E2B, E4B, 26B A4B (MoE, about 4B active) and 31B dense. One source also lists a 12B.
  - Context: 128K for E2B/E4B and 256K for the larger models.
  - KV cache at the full 262K context: about 20.8 GiB for 31B and about 5.2 GiB for 26B A4B.
  - Sources: [Gemma 4 overview](https://ai.google.dev/gemma/docs/core), [Kaitchup](https://kaitchup.substack.com/p/gemma-4-31b-and-26b-a4b-architecture) (snippets; Gemma 4 tech report [arXiv 2607.02770](https://arxiv.org/pdf/2607.02770) not fetchable)
- **Ollama's own docs now show gemma4 as the example model:** `gemma4:latest ... 9.6 GB 100% GPU 131072` context. — [Ollama docs: context-length](https://github.com/ollama/ollama/blob/main/docs/context-length.mdx)

### Inferences

**ESTIMATE: total memory = weights + KV (f16) + about 1 GB compute buffers.** The 1 GB is my allowance. The gpt-oss guide measured 2.7 GB of compute buffers with large batch settings, so smaller `-ub` values use less. OS and app overhead is not included; Windows 11 plus a browser and IDE commonly takes 4-6 GB (general knowledge, not measured here).

| Model (Q4_K_M; MXFP4 for gpt-oss) | Weights | KV f16 @16k | KV f16 @32k | Total @16k | Total @32k | Total @32k with q8_0 KV |
|---|---|---|---|---|---|---|
| gpt-oss-20b (MoE, 3.6B active) | 12.0 GB | 0.38 GiB | 0.75 GiB | ~15 GB (measured 14.9 @8k) | **15.5 GB (measured)** | ~15.1 GB |
| Qwen3-30B-A3B-2507 / Qwen3-Coder-30B-A3B (MoE, ~3.3B active) | ~18-19 GB | 1.50 GiB | 3.00 GiB | ~21 GB | ~22-23 GB | ~21 GB |
| Qwen3-8B | 5.2 GB | 2.25 GiB | 4.50 GiB | ~8.5 GB | ~10.7 GB | ~8.6 GB |
| Qwen3-14B | ~9 GB | 2.50 GiB | 5.00 GiB | ~12.7 GB | ~15.4 GB | ~12.9 GB |
| Qwen2.5-Coder-7B | ~4.7 GB* | 0.88 GiB | 1.75 GiB | ~6.6 GB | ~7.6 GB | ~6.7 GB |
| Qwen2.5-Coder-14B | ~9 GB* | 3.00 GiB | 6.00 GiB | ~13.2 GB | ~16.4 GB | ~13.4 GB |
| Devstral Small 24B | 14 GB | 2.50 GiB | 5.00 GiB | ~17.7 GB | ~20.4 GB | ~17.9 GB |
| Gemma 3 12B (sliding-window KV supported) | 8.1 GB | 1.31 GiB | 2.31 GiB | ~10.5 GB | ~11.6 GB | ~10.4 GB |
| Gemma 3 27B (sliding-window KV supported) | ~17 GB* | 1.66 GiB | 2.91 GiB | ~19.8 GB | ~21.1 GB | ~19.7 GB |

\*ESTIMATE from the rule of thumb that Q4_K_M averages about 4.85 bits per weight, so bytes ≈ parameters × 0.61: 7.6B → 4.6 GB, 14.8B → 9.0 GB, 27B → about 16.5 GB plus the vision tower. Not verified against ollama.com, which was blocked.

**Which models fit in each tier**
- **16 GB Windows/Linux, CPU-only.** Once the OS is running, roughly 10-11 GB is usable. Comfortable: Qwen2.5-Coder-7B and Qwen3-8B (both at 32k with q8_0 KV), Gemma 3 12B. Marginal: Qwen3-14B and Qwen2.5-Coder-14B at 16k. Does not fit: gpt-oss-20b (15.5 GB), Qwen3-30B-A3B Q4_K_M, Devstral 24B, Gemma 3 27B. Qwen3-30B-A3B would only fit at about Q2/Q3 or by paging from disk.
- **16 GB RAM plus a 6-8 GB GPU.** Pooled memory is about 22-24 GB. gpt-oss-20b becomes feasible with `--n-cpu-moe`, which keeps attention and some experts on the GPU and the rest in RAM. Qwen3-30B-A3B Q4_K_M, split roughly 7 GB VRAM and 12 GB RAM, is possible but leaves little room for Windows. The dense 8B fits almost fully in 8 GB VRAM at 16k only if the KV cache is q8_0 (5.2 + 1.2 + about 0.7 GB).
- **32 GB RAM.** Every model above fits, including the 3B-active MoEs at 32k and Devstral 24B. Whether it is fast enough is a separate question (sections 2-3).
- **Apple Silicon.** Only part of unified memory can be wired to the GPU by default. It is commonly about two-thirds on machines with 36 GB or less and about three-quarters above that, adjustable with `sysctl iogpu.wired_limit_mb`. This is general knowledge and was not verified in this session.
  - 16 GB Mac: about 10.5-11 GB for the GPU. 8B dense and Gemma 3 12B are fine; gpt-oss-20b (15.5 GB) does not fit by default.
  - 32 GB Mac: about 21 GB. gpt-oss-20b is comfortable. Qwen3-30B-A3B/Coder Q4_K_M fits at 16k and is borderline at 32k unless KV is q8_0 or the wired limit is raised.
  - 64 GB Mac: everything listed fits, plus the 2026 Qwen3.6-35B-A3B, Qwen3.6/3.8-27B, Gemma 4 26B-A4B and 31B.

**Why 2026 hybrid models matter for laptops.** They cut KV cache a lot. Qwen3.8-27B measures 34 KiB/token at q8_0, which implies about 68 KiB/token at f16 and about 2.1 GiB at 32k. A conventional 24B dense model such as Devstral needs about 160 KiB/token f16, or 5 GiB at 32k.

### Gaps
- Exact current Ollama library sizes and default quantization tags could not be read (ollama.com blocked). The sizes above come from aggregator snippets or the bits-per-weight estimate.
- Qwen3.5-9B / Qwen3.6-35B-A3B GGUF file sizes and exact layer/KV configuration could not be verified (Hugging Face blocked).
- Gemma 4 sizes and KV figures come only from secondary snippets; the "12B" member of Gemma 4 is uncertain.
- The Apple GPU wired-memory limit fractions are from general knowledge, not a fetched source.

---

## 2. Measured prompt-processing (prefill) and generation speed by hardware; MoE vs dense

### Takeaway
- **Generation speed tracks memory bandwidth divided by active-weight bytes.** So 3-4B-active MoEs (gpt-oss-20b, Qwen3-30B-A3B) generate about 2-3× faster than a dense 8B and about 5-8× faster than a dense 24B on the same machine.
- **Prefill tracks compute.** It is thousands of tokens/s on any NVIDIA GPU, hundreds on M-Pro/Max Macs (and far more on M5), and only tens to low hundreds on laptop CPUs. On CPU-only laptops, prefill of 10k-token prompts is the dominant cost.

### Cited Findings

**Apple Silicon, llama.cpp Metal, gpt-oss-20b MXFP4** (llama.cpp guide, August 2025 builds, e.g. c8d0d14/6310). Source: [llama.cpp #15396](https://github.com/ggml-org/llama.cpp/discussions/15396)

| Chip | pp2048 (t/s) | pp8192 (t/s) | tg128 (t/s) |
|---|---|---|---|
| M1 Pro 32GB | 515.76 | 437.22 | 45.68 |
| M4 Max 36GB | 1277.42 | 1030.28 | 92.36 |
| M3 Ultra | 2816.47 | 2308.17 | 115.52 |

The M3 Ultra run used `-fa 1 -b 2048 -ub 2048`.

**Apple Silicon comparative table, Llama 2 7B, llama.cpp** (pp512 / tg128 in t/s; "BW" is memory bandwidth). Original rows are from build 8e672ef (Nov 2023); M5 rows are from build c1d0e7a (Aug 25, 2026). Source: [llama.cpp #4167](https://github.com/ggml-org/llama.cpp/discussions/4167)

| Chip | BW (GB/s) | Q4_0 pp512 | Q4_0 tg128 | Q8_0 tg128 |
|---|---|---|---|---|
| M1 | 68 | 117.96 | 14.15 | 7.91 |
| M1 Pro | 200 | 266.25 | 36.41 | — |
| M1 Max | 400 | 530.06 | 61.19 | — |
| M2 | 100 | 179.57 | 21.91 | — |
| M2 Pro | 200 | 341.19 | 38.86 | — |
| M2 Max | 400 | 671.31 | 65.95 | — |
| M3 Pro | 150 | 341.67 | 30.74 | — |
| M3 Max | 400 | 759.70 | 66.31 | — |
| M4 | 120 | 221.29 | 24.11 | — |
| M4 Pro | 273 | 439.78 | 50.74 | — |
| M4 Max | 546 | 885.68 | 83.06 | — |
| M5 Pro | 307 | 1620.64 | 66.33 | — |
| M5 Max | 614 | 3219.99 | 119.92 | — |

- The M5 generation roughly 3.5-3.7× the prompt-processing speed of the M4 at similar bandwidth, while generation rises only in line with bandwidth.

**Apple Silicon, MoE coders and 2026 models** (all snippets)
- Qwen3-Coder-30B-A3B on M1 Max 32GB/64GB with llama.cpp: best reported prompt processing about 132.1 t/s and generation about 58.5 t/s. Another report gives about 49 t/s on an M1 Max 32GB at 120K context with the KV cache and flash attention tuned. — [siliconscore](https://siliconscore.com/models/qwen3-coder-30b-a3b/) (snippet). The 132 t/s prefill looks low next to gpt-oss on M1 Pro (437-516); the test conditions are unknown.
- Qwen3.5-35B-A3B on M4 Max: MLX reached 108-115 t/s, versus about 70 t/s for llama.cpp and 40-46 t/s for Ollama. — [Ante Kapetanovic benchmark](https://antekapetanovic.com/blog/qwen3.5-apple-silicon-benchmark/) (snippet)
- gpt-oss-20b on M4 Pro with oMLX: about 350 t/s prompt processing and 36.5 t/s generation (with 96% caching). Elsewhere the same source says 63 t/s generation. — [agileguy.ca](https://www.agileguy.ca/opencode-fully-local/) (snippet; internally inconsistent, low confidence)

**NVIDIA, llama.cpp CUDA, Llama 2 7B Q4_0** (no flash attention). Source: [llama.cpp #15013](https://github.com/ggml-org/llama.cpp/discussions/15013)

| GPU | pp512 (t/s) | tg128 (t/s) | Build |
|---|---|---|---|
| RTX 3050 Laptop 6GB | 1147.01 | 37.39 | 12127de, July 2026 |
| RTX 4050 Laptop 6GB | 1725.85 | 43.72 | d79d8f3, Aug 2025 |
| RTX 3060 12GB (desktop) | 2137.50 | 75.57 | 9c35706, Aug 2025 |
| RTX 4060 Ti 8GB | 3394.63 | 63.86 | 89d1029, Aug 2025 |
| RTX 5060 12GB | 5184.75 | 127.54 | — |
| RTX 4070 Ti SUPER 16GB | 6924.53 | 132.26 | — |

- The page summary returned no RTX 4060 Laptop or 4070 Laptop rows.

**NVIDIA with gpt-oss-20b** (source: [llama.cpp #15396](https://github.com/ggml-org/llama.cpp/discussions/15396))
- Full GPU runs:
  - RTX 3090: pp2048 5170.56, pp8192 4771.74, tg128 161.77 t/s.
  - RTX 4080 SUPER 16GB: pp2048 8170.95, pp8192 7989.22, pp32768 6739.51, tg128 186.51 t/s.
  - RTX 4090: pp2048 8078.28, tg128 225.22 t/s.
- Partial offload on a 12 GB card (RTX 3060 with Ryzen 7 5700X):
  - 16K context: "67 tok/sec initial generation rate" with `-ncmoe 2`.
  - 32K context: "56 tok/sec" with `-ncmoe 3`.
  - 75 tok/s at 2K context.
- For an 8 GB RTX 2060, the guide suggests "32k context, 16 layers on the CPU".
- Ollama generation ("eval rate") for gpt-oss 20b: RTX 3060 (desktop) 83.96 t/s, RTX 4070 Ti 163.14 t/s. — [geerlingguy/ai-benchmarks](https://github.com/geerlingguy/ai-benchmarks)
- On 8-12 GB cards, gpt-oss-20b is "in CPU-offload territory at 30 tok/s or worse". 16 GB of system RAM is "the practical floor and 32GB is comfortable" when about 6-7 GiB of experts are offloaded. — [aliteq](https://aliteq.com/gpt-oss-20b-8gb-12gb-gpu-moe-offload-2026) (snippet)

**CPU-only and iGPU laptops**
- **AMD Ryzen AI 9 HX PRO 370** (Zen 5, 12 cores / 24 threads), 96 GB DDR5-5600 dual-channel, CPU-only, llama.cpp build 7973. Generation: qwen2.5-coder:32b Q4_K_M 3.54 t/s; Qwen3-Coder-Next (80B-A3B) Q4_K_M 7.74 t/s. Best performance came at 12 threads (the physical cores) and got worse with SMT. A server reference (EPYC 9454P) reached 63.10 t/s on Qwen3-30B MoE. Issue dated Feb 10, 2026. — [llama.cpp issue #19480](https://github.com/ggml-org/llama.cpp/issues/19480)
- **Ollama CPU generation on a Framework 13** (Ryzen AI 5 340, 16GB): DeepSeek-R1 14b (a dense 14B at Q4) 5.83 t/s; llama3.2:3b 23.81 t/s. The Framework Desktop board (Ryzen AI Max+ 395, 128GB) on CPU ran the 14B at 11.37 t/s. A Dell XPS 13 (Intel Core 5 320) iGPU ran llama3.2:3b at 23.88 t/s. — [geerlingguy/ai-benchmarks](https://github.com/geerlingguy/ai-benchmarks)
- **CPU prefill anchor** (desktop Ryzen 9 7950X, 16 threads, LLaMA-3.1-8B, mainline llama.cpp, Dec 24, 2024): pp512 of 153.52 t/s at Q4_0, 147.92 at Q8_0 and 75.52 at Q5_K_S. The ik_llama.cpp fork managed 254-274 t/s. On an M2 Max's CPU cores, Q4_0 pp512 was 114.63 t/s. These tables measured generation with only 2-4 threads, so their generation numbers are not representative. — [ik_llama.cpp discussion #164](https://github.com/ikawrakow/ik_llama.cpp/discussions/164)
- **Old APU iGPU (Vulkan):** Qwen3-30B-A3B-Thinking on an AMD Renoir iGPU (8 CUs, 16 GB DDR4) got pp512 about 55-89 t/s and tg128 about 20-21 t/s. Qwen3-Next-80B-A3B on the same machine got pp512 about 32-35 and tg128 about 8.8 t/s. Dated Dec 4, 2025. — [llama.cpp issue #17751](https://github.com/ggml-org/llama.cpp/issues/17751)
- **Vulkan iGPU, Llama 2 7B Q4_0:** an Intel Core Ultra 200-series iGPU got pp512 864.99 and tg128 24.37 t/s. Intel Iris Xe (i7-1185G7) got pp512 42.02 and tg128 7.28 (January 2025). — [llama.cpp #10879](https://github.com/ggml-org/llama.cpp/discussions/10879)
- **Snippets for high-end and laptop CPUs:**
  - CPU-only Qwen3-30B-A3B on a desktop Ryzen 9 9950X with DDR5-6400 (about 88 GB/s) reached over 30 t/s generation, described as best case. Typical modern 32 GB systems see 12-15 t/s at 4-bit. — [LocalAIMaster](https://localaimaster.com/blog/run-llm-cpu-only) (snippet)
  - On a Ryzen AI 9 HX 370, Qwen3 30B Q8_0 peaks above 23 t/s and settles around 18 t/s interactively. — [Medium, F. Giampietro](https://medium.com/@federicogiampietro/enough-with-nvidia-qwen3-next-80b-8-bit-on-ryzen-ai-9-hx370-3cd616671428) (snippet)
  - On a Framework 13 (Strix Point, DDR5-5600, 89.6 GB/s), Qwen3-8B Q4_K_M got about 9.87 t/s on battery and 13.41 t/s plugged in. The snippet labels this prompt processing, but the values look like generation. — [msf.github.io](https://msf.github.io/blogpost/local-llm-performance-framework13.html) (snippet; page blocked)

### Inferences

**MoE vs dense.** On the same M1 Pro, gpt-oss-20b (3.6B active) generates at 45.7 t/s, versus 36.4 t/s for a dense 7B Q4_0. Bandwidth scaling says a dense 8B Q4_K_M runs at about 30 t/s and a dense 24B Q4_K_M at about 10-11 t/s on that chip (ESTIMATE: tg ≈ 36.4 × 3.8 GB / model GB). On CPU laptops, the 80B-A3B MoE (7.74 t/s) beat a dense 32B (3.54 t/s) on the same HX 370. This confirms that active parameters, not total, set generation speed.

**Prefill for MoE vs dense.** Prefill compute scales with active parameters, about 2 × active FLOPs per token. A 3B-active MoE should therefore prefill about 2-2.5× faster than a dense 8B on CPU. On GPUs, gpt-oss-20b prefill (5170 t/s on RTX 3090) is in the same range as a dense 7B. ESTIMATE, consistent with the tables above.

**ESTIMATE: RTX 4060 Laptop (8 GB, 128-bit GDDR6, about 256 GB/s)** should sit between the 4050 Laptop (1726 / 43.7) and the 4060 Ti (3395 / 63.9) on Llama-7B Q4_0. That is roughly 2000-2500 t/s prefill and 40-45 t/s generation. For a fully-offloaded Qwen3-8B Q4_K_M at 10k depth, expect roughly 1200-1800 t/s prefill and 30-38 t/s generation. The RTX 4070 Laptop (8 GB, same bus width) would be similar in generation and about 20-30% faster in prefill.

**ESTIMATE: typical 2024-2026 x86 laptop CPU, CPU-only** (8-12 cores, dual-channel DDR5-5600 at about 60-70 GB/s effective):

| Model | Prefill (t/s) | Generation (t/s) | Derivation |
|---|---|---|---|
| Dense 7-8B Q4_K_M | 40-90 | 7-12 | Prefill: about half to two-thirds of the 16-core desktop 7950X's 75-153 t/s. Generation: bandwidth/weights ≈ 65/5 × 0.7 efficiency. |
| Dense 14B | 20-45 | 4-6 | Generation matches the geerlingguy 5.83 t/s. |
| gpt-oss-20b / Qwen3-30B-A3B | 80-200 | 12-25 | Matches the HX 370 18-23 t/s and 9950X 30 t/s snippets. |

### Gaps
- No fetchable measured llama-bench rows for RTX 4060 Laptop or 4070 Laptop GPUs with the target models. The laptop GPU figures above are interpolated.
- No fetchable primary llama-bench numbers for Qwen3-30B-A3B or Qwen3-Coder-30B-A3B on M1-M4 Pro/Max at 16k-32k depth. The only data are snippet-level. LocalScore (localscore.ai), which would have covered this, was blocked.
- No measured CPU-only prefill numbers at 10k+ depth on laptop CPUs with Q4_K_M. Prefill also slows with depth, and I found no laptop CPU data quantifying that.
- Speed at depth (how generation degrades at 16k-32k) is only measured for gpt-oss on GPU and Apple chips (pp8192/pp32768). On an M1 Pro, pp drops about 15% from 2k to 8k.

---

## 3. Wall-clock time for one 10k-token prompt plus 2k-token answer, by tier

### Takeaway
- **CPU-only 16 GB laptops:** 7-8B dense models take about 4-9 minutes per call, 14B takes 10-17 minutes, and the best-fitting MoEs don't fit. That is too slow for an interactive POC of 15-30 calls, which comes to 1-4+ hours per run.
- **6-8 GB NVIDIA GPU, M-Pro/Max Mac with 32-64 GB, or M5-class Mac:** 3B-active MoE models (gpt-oss-20b, Qwen3-30B-A3B/Coder, Qwen3.6-35B-A3B) bring a call down to about 0.5-2 minutes. That makes a 15-30-call run 10-45 minutes.

### Cited Findings
- **Measured inputs used for the estimates below:**
  - gpt-oss-20b on M1 Pro: pp8192 437.22, tg128 45.68.
  - gpt-oss-20b on M4 Max: pp8192 1030.28, tg128 92.36.
  - RTX 3060 12GB with `-ncmoe 2`: 67 t/s generation at 16K.
  - Source: [llama.cpp #15396](https://github.com/ggml-org/llama.cpp/discussions/15396)
- **Laptop-class measured generation rates:**
  - 14B dense on Ryzen AI 5 340 CPU (Ollama): 5.83 t/s. — [geerlingguy/ai-benchmarks](https://github.com/geerlingguy/ai-benchmarks)
  - Dense 32B on HX 370 CPU: 3.54 t/s.
  - 80B-A3B MoE on HX 370 CPU: 7.74 t/s. — [llama.cpp #19480](https://github.com/ggml-org/llama.cpp/issues/19480)
- **Ollama's default context is 4k below 24 GiB of VRAM.** Its docs say "< 24 GiB VRAM: 4k context; 24-48 GiB VRAM: 32k context; >= 48 GiB VRAM: 256k context", and that coding tools "should be set to at least 64000 tokens". — [Ollama docs: context-length](https://github.com/ollama/ollama/blob/main/docs/context-length.mdx)

### Inferences

**ESTIMATE: wall-clock time** = 10,000 / prefill rate + 2,000 / generation rate. Rates are taken at about 10k depth, with a 5-15% depth penalty applied to short-context benchmark numbers. The formula ignores model load time (5-30 s on first call) and any reasoning or thinking tokens.

| Tier | Model | Prefill t/s | Gen t/s | Per call | 15-30 calls |
|---|---|---|---|---|---|
| **16 GB CPU-only** (Zen 4/5 or Core Ultra, DDR5) | Qwen2.5-Coder-7B Q4_K_M | 50-90 | 8-12 | **~4.5-7.5 min** | 1.1-3.8 h |
| | Qwen3-8B Q4_K_M | 40-80 | 7-10 | **~5.5-9 min** | 1.4-4.5 h |
| | Qwen3-14B Q4_K_M (16k max) | 20-40 | 4-6 | **~10-17 min** | 2.5-8.5 h |
| **32 GB CPU-only** | gpt-oss-20b MXFP4 | 80-200 | 15-25 | **~2.2-4.3 min** | 33 min-2.2 h |
| | Qwen3-30B-A3B / Coder Q4_K_M | 60-150 | 12-20 | **~2.8-5.6 min** | 42 min-2.8 h |
| | Devstral 24B Q4_K_M | 10-25 | 2.5-3.5 | **~16-27 min** | impractical |
| **16 GB + RTX 4060/4070 Laptop 8 GB** | Qwen3-8B, fully on GPU (q8_0 KV, 16k) | 1200-1800 | 30-38 | **~1-1.2 min** | 15-36 min |
| | gpt-oss-20b, `--n-cpu-moe` about 10-16 | 400-1500 | 20-35 | **~1-2 min** | 15-60 min |
| | Qwen2.5-Coder-14B / Qwen3-14B (partial offload) | 500-1000 | 10-18 | **~2-3.5 min** | 30 min-1.7 h |
| **Mac M1/M2 base 16 GB** | Qwen3-8B Q4_K_M | 80-150 | 11-18 | **~3-5 min** | 45 min-2.5 h |
| **Mac M4 base 16 GB** | Qwen3-8B Q4_K_M | 150-190 | 18-21 | **~2.5-3 min** | 38 min-1.5 h |
| **Mac M1 Pro 32 GB** | gpt-oss-20b (measured base rates) | ~430 | ~42 | **~1.2 min** | 18-36 min |
| **Mac M4 Pro 32 GB** | gpt-oss-20b / Qwen3-Coder-30B-A3B | 600-750 | 50-65 | **~45-55 s** | 11-28 min |
| **Mac M4 Max 64 GB** | gpt-oss-20b (measured base rates) | ~1000 | ~85 | **~33 s** | 8-17 min |
| | Devstral 24B Q4_K_M (dense) | ~250 | ~20-24 | **~2-2.3 min** | 30 min-1.2 h |
| **Mac M5 Pro/Max** | 3B-active MoE | about 3.5× the M4 figure | ~M4 × BW ratio | prefill becomes negligible | — |

**Too slow for an interactive POC on CPU-only 16 GB laptops:**
- Every dense model of 14B or more (10+ minutes per call).
- In practice, dense 7-8B models too (5-9 minutes per call).
- All 20B+ models, which don't fit.

On CPU-only machines, the 10k-token prefill alone takes about 2-4 minutes for an 8B model. Output length adds about 1.5-5 minutes on top of that for every 2k tokens.

**Prompt-prefix caching can reduce prefill cost.** If the 15-30 calls share a long common prefix (system prompt, spec, prior files) and the runtime reuses the KV prefix (llama-server does this per slot; Ollama reuses the cache for identical prefixes), later calls pay prefill only for the new suffix. Structuring prompts as stable prefix plus variable suffix could cut CPU-tier times sharply. This is an inference and not measured here.

**Reasoning models add hidden output tokens.** gpt-oss (reasoning effort levels) and Qwen3 thinking modes emit reasoning tokens before the JSON answer. Use gpt-oss with low reasoning effort, or the non-thinking Qwen3-2507-Instruct / Qwen3-Coder variants, to keep output near the 2k budget.

**Ollama users must raise the context length.** On most laptops (under 24 GiB VRAM), 10k-16k prompts will not fit the 4k default. Set `OLLAMA_CONTEXT_LENGTH` or `num_ctx` to at least 20k-40k. This also raises memory use per the KV table.

### Gaps
- No end-to-end measured "10k in, 2k out" timings were found for any laptop. Every per-call figure above is an ESTIMATE built from pp/tg benchmarks.
- Thermal throttling during 15-30 back-to-back long calls on thin-and-light laptops is not quantified. Battery vs plugged-in differences also matter: one snippet showed 9.87 vs 13.41 t/s on a Framework 13.

---

## 4. KV cache per 1k tokens; effect of flash attention and q8_0 KV cache (Ollama / llama.cpp)

### Takeaway
- **Per-1k-token KV cost at f16 varies about 6×:**
  - About 23 MiB for gpt-oss-20b (only 12 full-attention layers × 8 KV heads × 64 dims).
  - About 55 MiB for Qwen2.5-Coder-7B.
  - About 94 MiB for Qwen3-30B-A3B.
  - 140-190 MiB for the dense 8-14B Qwen models and Devstral.
  - Up to 375-485 MiB for Gemma 3 if sliding-window caching is not used.
- **q8_0 KV cache** halves this with a negligible measured quality change. It requires flash attention in Ollama.
- **q4_0 KV cache** is model-dependent and can badly hurt Qwen2.5-7B.

### Cited Findings
- **KV per token for gpt-oss-20b:** "KV cache per 8,192 tokens (GB): 0.2". — [llama.cpp #15396](https://github.com/ggml-org/llama.cpp/discussions/15396)
- **Ollama on flash attention:** "Flash Attention is a feature of most modern models that can significantly reduce memory usage as the context size grows. Ollama uses Flash Attention automatically when the selected backend and devices support it. To force Flash Attention on, set `OLLAMA_FLASH_ATTENTION=1` ... To disable it, set `OLLAMA_FLASH_ATTENTION=0`." — [Ollama FAQ](https://github.com/ollama/ollama/blob/main/docs/faq.mdx)
- **Ollama on KV cache quantization:**
  - "The K/V context cache can be quantized to significantly reduce memory usage when Flash Attention is enabled", set via `OLLAMA_KV_CACHE_TYPE` (default `f16`), and it is "a global option" applying to all models.
  - `q8_0` "uses approximately 1/2 the memory of f16 with a very small loss in precision, this usually has no noticeable impact on the model's quality (recommended if not using f16)".
  - `q4_0` "uses approximately 1/4 the memory of f16 with a small-medium loss in precision that may be more noticeable at higher context sizes".
  - "Models that have a high GQA count (e.g. Qwen2) may see a larger impact on precision from quantization."
  - Source: [Ollama FAQ](https://github.com/ollama/ollama/blob/main/docs/faq.mdx)
- **Ollama parallel requests multiply memory:** "`OLLAMA_NUM_PARALLEL` ... default 1. Required RAM will scale by `OLLAMA_NUM_PARALLEL` * `OLLAMA_CONTEXT_LENGTH`." — [Ollama FAQ](https://github.com/ollama/ollama/blob/main/docs/faq.mdx)
- **Measured KV quality impact on 500 ARC-Challenge questions** (llama.cpp CUDA, May-Sept 2026):
  - q8_0/q8_0 changed 0-4 answers across three models; q8_0/q5_1 changed 1-5; q8_0/q4_0 changed 1-11.
  - q4_0/q4_0 changed 375/500 answers on Qwen2.5-7B.
  - 99th-percentile KL divergence on Qwen3.8-27B: q8_0/q8_0 0.006425; q8_0/q5_1 0.007628; q8_0/q4_0 0.012340.
  - Throughput variance between cache types was small (q8_0/q5_1 reached 847.33 t/s on Qwen3.6).
  - Source: [llama.cpp discussion #23470](https://github.com/ggml-org/llama.cpp/discussions/23470)
- **Search summary of the same discussion area:** q8_0 K+V produced "0 flips across 1,600 deep-context comparisons to 41K tokens". q4_0 results were strongly model-dependent: Qwen3.6-27B 2/500, Qwen3.8-27B 3/500, Mistral-7B 34/500, Qwen2.5-7B 375/500. — [llama.cpp discussions #23470 / #22411](https://github.com/ggml-org/llama.cpp/discussions/22411) (snippet)
- **Mismatched K/V types can slow flash attention:** "The fused Flash Attention kernels only support matching K/V quantization types. If they don't match, it silently falls back to the slower non-fused implementation." — [llama.cpp discussion #22411](https://github.com/ggml-org/llama.cpp/discussions/22411) (snippet, HIP-specific PSA)
- **Quantized KV has a CUDA flash-attention inefficiency** that gets worse with context length (open issue). A linked report says "4-bit KV cache (q4_1/q4_0) collapses prefill to ~34 t/s on qwen35 hybrid (RTX 3090)". — [llama.cpp issue #29371](https://github.com/ggml-org/llama.cpp/issues/29371)

### Inferences

**ESTIMATE: KV cache per 1k tokens.** Formula: 2 (K and V) × layers-with-growing-KV × KV heads × head_dim × 2 bytes (f16). q8_0 is 34 bytes per 32 values, so ×0.53 of f16.

| Model | f16 per 1k tokens | f16 @16k | f16 @32k | q8_0 @16k | q8_0 @32k |
|---|---|---|---|---|---|
| gpt-oss-20b (12 full layers; 12 layers with 128-token window, about 3 MiB fixed) | 23.4 MiB | 0.38 GiB | 0.75 GiB | 0.20 | 0.40 |
| Qwen3-30B-A3B-2507 / Qwen3-Coder-30B-A3B (48 × 4 × 128) | 93.8 MiB | 1.50 | 3.00 | 0.80 | 1.59 |
| Qwen3-8B (36 × 8 × 128) | 140.6 MiB | 2.25 | 4.50 | 1.20 | 2.39 |
| Qwen3-14B (40 × 8 × 128) | 156.3 MiB | 2.50 | 5.00 | 1.33 | 2.66 |
| Qwen2.5-Coder-7B (28 × 4 × 128) | 54.7 MiB | 0.88 | 1.75 | 0.46 | 0.93 |
| Qwen2.5-Coder-14B (48 × 8 × 128) | 187.5 MiB | 3.00 | 6.00 | 1.59 | 3.19 |
| Devstral Small 24B (40 × 8 × 128) | 156.3 MiB | 2.50 | 5.00 | 1.33 | 2.66 |
| Gemma 3 12B with sliding-window cache (8 global layers + 320 MiB fixed window) | 62.5 MiB | 1.31 | 2.31 | 0.70 | 1.23 |
| Gemma 3 12B without sliding-window cache (all 48 layers full) | 375 MiB | 6.00 | 12.00 | 3.19 | 6.38 |
| Gemma 3 27B with sliding-window cache (10 global layers + 416 MiB fixed) | 78.1 MiB | 1.66 | 2.91 | 0.88 | 1.54 |
| Gemma 3 27B without sliding-window cache | 484 MiB | 7.75 | 15.50 | 4.12 | 8.23 |
| Qwen3.8-27B (2026 hybrid; measured at q8_0) | ~68 MiB | ~1.1 | ~2.1 | 0.53 | 1.06 |

**Cross-checks.** The gpt-oss row reproduces the guide's 0.2 GB per 8,192 tokens (192 MiB). The Qwen3.8-27B row is derived from the measured 34 KiB/token at q8_0/q8_0 in [#23470](https://github.com/ggml-org/llama.cpp/discussions/23470). Architecture parameters are sourced in section 1. Qwen3's head_dim of 128 comes from the model configs, which could not be fetched this session (Hugging Face blocked), so treat those Qwen3 rows as high-confidence but not re-verified.

**Practical guidance:**
- Enable flash attention and q8_0 for both K and V. Keep K and V the same type so the fused kernels stay on the fast path.
- On a 16 GB laptop this saves about 1.1-2.2 GB at 16-32k for Qwen3-8B/14B, often the difference between fitting and swapping.
- Avoid q4_0 KV for Qwen2.5-family models.
- The KV memory the MoE models save is small compared with their weights: 18-19 GB of weights for Qwen3-30B-A3B versus 1.5-3 GB of KV.

**Flash attention's other memory saving.** Besides enabling KV quantization, flash attention avoids materializing the attention-score matrix, which shrinks compute buffers at long context. No size numbers were found (see Gaps).

### Gaps
- No measured numbers found for how much flash attention alone shrinks compute buffers at 16k/32k on these models.
- No measured laptop-specific speed penalty for q8_0 KV (CPU, Metal, laptop CUDA). Discussion #23470 reports "minimal variance" on desktop CUDA only.
- Whether Ollama's current engine uses sliding-window-sized KV for Gemma 3 and gpt-oss (versus full-size) was not verified from a fetched source. If not, the Gemma 3 KV is the "without sliding-window" row.

---

## 5. Evidence specific to Windows laptops (Ollama on Windows, Vulkan/CUDA)

### Takeaway
- **Ollama on Windows supports NVIDIA via CUDA** (driver 551.61+), AMD via ROCm v7 or Vulkan, and other GPUs and iGPUs via Vulkan, which is on by default.
- **Throughput risks:** there is a reported 5× gap between Ollama and llama.cpp on Windows for a 2026 hybrid MoE, and older data show Vulkan well behind CUDA on NVIDIA.
- **For NVIDIA laptops, use the CUDA path,** and consider llama.cpp's llama-server directly if Ollama underperforms on a given model.

### Cited Findings
- **Ollama Windows requirements:** "Windows 10 22H2 or newer"; "NVIDIA 551.61 or newer Drivers if you have an NVIDIA card"; "AMD ROCm v7 / HIP7-capable driver stack for ROCm acceleration, or a Vulkan-capable AMD Radeon driver for Vulkan acceleration". — [Ollama docs: windows](https://github.com/ollama/ollama/blob/main/docs/windows.mdx)
- **Vulkan on Windows is on by default:**
  - "Vulkan is enabled by default and is the recommended fallback" for RDNA2 systems without ROCm v7.
  - "If a mixed iGPU/dGPU system selects an unstable Vulkan iGPU, set `GGML_VK_VISIBLE_DEVICES` to the discrete GPU index."
  - Windows download assets include `ollama-windows-amd64-rocm.zip` and an `ollama-windows-amd64-mlx.zip` "MLX (CUDA)" build.
  - Source: [Ollama docs: windows](https://github.com/ollama/ollama/blob/main/docs/windows.mdx)
- **Ollama GPU docs:**
  - "Additional GPU support on Windows and Linux is provided via Vulkan. Vulkan is enabled by default when the backend is installed. On Windows most GPU vendors drivers come bundled with Vulkan support and require no additional setup steps."
  - Vulkan can be disabled with `OLLAMA_VULKAN=0` or `GGML_VK_VISIBLE_DEVICES=-1`.
  - NVIDIA requires compute capability 5.0+ and driver 550+.
  - Source: [Ollama docs: gpu](https://github.com/ollama/ollama/blob/main/docs/gpu.mdx)
- **Ollama vs llama.cpp on Windows 11** (RTX 3090 Ti, 64 GB, Qwen3.5-35B-A3B at Q4): Ollama gave "around 15 to 20 tokens per second" versus llama.cpp's "100 tokens per second even with default settings ... context 160000". Posted March 3, 2026, with no maintainer response visible. The reported "Ollama version 0.7.15" looks inconsistent with a 2026 date and may be misreported. — [ollama/ollama issue #14579](https://github.com/ollama/ollama/issues/14579)
- **Another Qwen3.5 comparison:** llama.cpp was 1.4× faster (136 vs 99 t/s). — [search snippet, 2026 Qwen3.5 benchmark roundup](https://www.glukhov.org/llm-performance/benchmarks/best-llm-on-16gb-vram-gpu/) (snippet; attribution uncertain)
- **Vulkan vs CUDA on one NVIDIA card** (RTX 3080, Llama 2 7B Q4_0, Dec 18, 2024 build): Vulkan pp512 1706.07 and tg128 62.16 versus CUDA pp512 4499.47 and tg128 131.01. This is old data; the Vulkan backend has improved since. — [llama.cpp #10879](https://github.com/ggml-org/llama.cpp/discussions/10879)
- **Windows laptop iGPUs via Vulkan** (Llama 2 7B Q4_0): Intel Core Ultra 200-series iGPU got pp512 864.99 and tg128 24.37. Intel Iris Xe got 42.02 and 7.28. — [llama.cpp #10879](https://github.com/ggml-org/llama.cpp/discussions/10879)
- **Ryzen AI 9 HX 370:** ROCm was reported 41% faster at prompt processing and Vulkan 2× faster at text generation. — [search snippet, HX 370 articles](https://medium.com/@federicogiampietro/enough-with-nvidia-qwen3-next-80b-8-bit-on-ryzen-ai-9-hx370-3cd616671428) (snippet)
- **On AMD HIP, only symmetric KV quantization** (for example q8_0/q8_0) takes the fast fused flash-attention path. — [llama.cpp #22411](https://github.com/ggml-org/llama.cpp/discussions/22411) (snippet)

### Inferences
- **NVIDIA laptops:** Ollama's CUDA backend is the default path; driver version is the main prerequisite. Vulkan on an NVIDIA laptop is a fallback and was historically about 2× slower.
- **Intel Core Ultra (Lunar Lake / Arrow Lake / Panther Lake) and AMD Ryzen AI laptops without a dGPU:** the Vulkan iGPU path can prefill 5-10× faster than the CPU. The Core Ultra 200-series iGPU at 865 t/s on 7B Q4_0 compares with roughly 75-150 t/s for a strong CPU. Generation stays bandwidth-bound at about the same level as the CPU. This makes an iGPU laptop with 32 GB of RAM a meaningfully better tier than a CPU-only one for 10k-token prompts. This is an inference from the #10879 and ik_llama #164 numbers, measured on different models and dates.
- **Windows memory overhead:** Windows 11 plus a browser and IDE typically keeps 4-6 GB resident. On 16 GB Windows laptops, the 15.5 GB gpt-oss-20b figure is therefore not practical without a dGPU sharing the load. This is general knowledge, not measured here.

### Gaps
- No fetched, dated benchmark of Ollama on Windows vs Linux on the same laptop hardware.
- No fetched RTX 4060 Laptop / 4070 Laptop Windows numbers with the target models. Laptop GPU TGP (35-140 W) varies widely and affects prefill.
- No current (2026) Vulkan vs CUDA comparison on the same NVIDIA laptop GPU was fetched; the only one is from December 2024.
- NPU acceleration (Intel/AMD/Qualcomm) for these models in Ollama/llama.cpp was not researched. None of the fetched sources showed NPU paths in Ollama.
