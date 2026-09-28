# Qwen family and OpenAI gpt-oss as local laptop models for a multi-agent coding PoC (state as of 2026-09-26)

Method note for the report writer: this session could fetch full pages only from github.com and raw.githubusercontent.com. Hugging Face, qwen.ai, ollama.com, openai.com, arxiv.org, aider.chat, gorilla.cs.berkeley.edu, modelscope.cn, unsloth.ai and dev.to were all blocked by the egress proxy. Those pages appear below only through search-result snippets, and they are labeled "(via search snippet)". Treat snippet-derived numbers as needing one confirmation click before they are quoted as final. Items labeled "(fetched)" were read directly: the GitHub READMEs, GitHub issues and the Aider leaderboard data file.

## 1. Which Qwen models (up to Sept 2026) fit laptops, and what are their specs and thinking toggles?

### Takeaway
As of September 2026 the current laptop-sized open-weight Qwen models are Qwen3.8-27B (dense, released 2026-08-14), Qwen3.6-27B (dense, 2026-04-22) and Qwen3.6-35B-A3B (MoE, 3B active, 2026-04-16). All three are Apache 2.0, have a 262K native context and think by default, with thinking that can be switched off. The Qwen3.5 small and medium models (Feb-Mar 2026) are the previous generation. Qwen3-Coder-30B-A3B, Qwen3-30B-A3B-2507, the Qwen3 dense models and Qwen2.5-Coder are all 2024-2025 releases and now superseded. Qwen3.7 never shipped open weights. Qwen3-Coder-Next (80B-A3B) is real but needs a machine with about 64 GB.

### Cited Findings

**Official release timeline (fetched from the QwenLM GitHub READMEs):**
- 2025-09-11: Qwen3-Next-80B-A3B ultra-sparse MoE released. 2026-02-16: Qwen3.5 first release (397B-A17B MoE). 2026-02-24: Qwen3.5-122B-A10B, Qwen3.5-35B-A3B and Qwen3.5-27B. 2026-03-02: Qwen3.5-9B, 4B, 2B and 0.8B. 2026-04-16: Qwen3.6-35B-A3B. 2026-04-22: Qwen3.6-27B. 2026-08-12: Qwen3.8-2.4T-A95B. 2026-08-14: Qwen3.8-27B. — [QwenLM/Qwen3.8 README](https://github.com/QwenLM/Qwen3.8); the same list appears at [raw README of QwenLM/Qwen3.6](https://raw.githubusercontent.com/QwenLM/Qwen3.6/main/README.md), which now carries the 3.8 content.
- The README lists these open-weight models: Qwen3.8 27B and 2.4T-A95B; Qwen3.6 27B and 35B-A3B; Qwen3.5 397B-A17B, 122B-A10B, 35B-A3B, 27B, 9B, 4B, 2B and 0.8B. Qwen3.8 is also available through the QwenCloud API, which is OpenAI- and Anthropic-compatible. — [QwenLM/Qwen3.8](https://github.com/QwenLM/Qwen3.8)
- For vLLM and SGLang the README says to deploy with `--reasoning-parser qwen3 --tool-call-parser qwen3_coder` (vLLM also adds `--enable-auto-tool-choice`), and to use a context length of 262144. It says reasoning depth "can be tuned with `reasoning_effort`" and that reasoning from earlier messages is kept through `preserve_thinking`. llama.cpp (GGUF) and MLX (mlx-lm, mlx-vlm) are named as supported. Ollama is not mentioned in the README. — [QwenLM/Qwen3.8](https://github.com/QwenLM/Qwen3.8), [QwenLM/Qwen3.6 raw README](https://raw.githubusercontent.com/QwenLM/Qwen3.6/main/README.md)

**Qwen3.8-27B (newest laptop-class Qwen, Aug 2026):**
- Released 2026-08-14. It has 27.78B parameters, is dense, takes text, image and video input, is Apache 2.0 and has a native 262,144-token context. — (via search snippet) [Qwen/Qwen3.8-27B HF card](https://huggingface.co/Qwen/Qwen3.8-27B), [kingy.ai summary](https://kingy.ai/blog/qwen3-8-27b-specs-benchmarks-local-hardware/), [QwenLM/Qwen3.8](https://github.com/QwenLM/Qwen3.8)
- According to a secondary source, the chat template has reasoning levels low, medium and xhigh, with xhigh as the default. Turning thinking off cut time-to-answer from 2.18 s to 0.21 s in that source's test. The same source reports that "Ollama replaces the model's own template with a generic one", so the reasoning-effort control cannot be set through Ollama, and it recommends llama-server `--jinja` instead. — (via search snippet) [NxCode](https://www.nxcode.io/resources/news/qwen3-8-27b-local-agent-model-2026). This is a secondary claim and was not verified against Ollama's Modelfile.
- There is a Hugging Face discussion titled "This model cannot stop thinking". — [HF discussion #113](https://huggingface.co/Qwen/Qwen3.8-27B/discussions/113) (title only; content not read)

**Qwen3.8-2.4T-A95B:** 2.4T total and 95B active parameters, released 2026-08-12. It is text-only, has thinking required-on, and uses a custom "Qwen3.8-Max License", not Apache. — (via search snippet) [llm-stats](https://llm-stats.com/blog/research/qwen3-8-max-open-weights). It is **far out of laptop scope**.

**Qwen3.7:** The 3.7-Max API went live May 19, 2026 and 3.7-Plus reached GA on June 1, 2026. As of June 15, 2026 no Qwen3.7-27B or 35B-A3B repository existed under the Qwen organization on Hugging Face, and 3.7 is described as "a skipped generation" for open weights. — (via search snippet) [InsiderLLM open-weights watch](https://insiderllm.com/guides/qwen-3-7-preview-scored-57-aai-27b-35b-open-weights-watch/), [Buttondown/InsiderLLM](https://buttondown.com/insiderllm/archive/qwen-37s-open-weights-are-overdue-by-the-math-not/). This is consistent with the official GitHub news list above, which jumps from 3.6 (April) to 3.8 (August). — [QwenLM/Qwen3.8](https://github.com/QwenLM/Qwen3.8)

**Qwen3.6-35B-A3B (Apr 2026):**
- 35B total and 3B active parameters, sparse MoE. It is a hybrid of Gated DeltaNet linear attention and gated attention, with a 262K native context that YaRN extends to 1M. It takes text, image and video, is Apache 2.0 and was released 2026-04-16. — (via search snippet) [Qwen blog](https://qwen.ai/blog?id=qwen3.6-35b-a3b), [MarkTechPost 2026-04-16](https://www.marktechpost.com/2026/04/16/qwen-team-open-sources-qwen3-6-35b-a3b-a-sparse-moe-vision-language-model-with-3b-active-parameters-and-agentic-coding-capabilities/)
- Qwen describes it as "surpassing its predecessor Qwen3.5-35B-A3B by a wide margin and rivaling much larger dense models such as Qwen3.5-27B and Gemma4-31B". This is a vendor claim. — (via search snippet) [Qwen blog](https://qwen.ai/blog?id=qwen3.6-35b-a3b)

**Qwen3.6-27B (Apr 2026):** Dense, released 2026-04-22. Qwen claims it "outperforms Qwen3.5-397B-A17B on every major coding benchmark", which is a vendor claim. — [QwenLM GitHub](https://github.com/QwenLM/Qwen3.8); (via search snippet) [Qwen blog](https://qwen.ai/blog?id=qwen3.6-27b)

**Qwen3.6 thinking controls:**
- Thinking is off when `chat_template_kwargs: {"enable_thinking": false}` is set, or `--chat-template-kwargs '{"enable_thinking": false}'` in llama.cpp and vLLM. On the Alibaba Model Studio API the top-level `"enable_thinking": False` is used instead. — (via search snippet) [Qwen/Qwen3.6-27B HF card](https://huggingface.co/Qwen/Qwen3.6-27B)
- `preserve_thinking` is new in 3.6. By default only the thinking for the latest user turn is kept, and the model was additionally trained to reuse thinking traces from earlier messages. — (via search snippet) [Qwen/Qwen3.6-27B HF card](https://huggingface.co/Qwen/Qwen3.6-27B)
- On Ollama, "Qwen 3.6 thinks by default — you can pass `"think": false` in /api/chat". — (via search snippet) [ollama.com/library/qwen3.6](https://ollama.com/library/qwen3.6)
- A community write-up documents a fix for "CoT leakage into tool turns" in the Qwen3.6-27B jinja template, dated 2026-05-02. — [allanchan339 blog](https://allanchan339.github.io/bug-fixes/2026/05/02/Qwen36-27B-updated-jinja.html) (title only; page blocked)

**Qwen3.5 (Feb-Mar 2026, previous generation):** The medium series (27B, 35B-A3B, 122B-A10B) came out Feb 24, 2026 and the small series (0.8B, 2B, 4B, 9B) on Mar 2, 2026. All support thinking and non-thinking modes and are Apache 2.0. — (via search snippet) [codersera guide](https://codersera.com/blog/qwen-3-5-complete-guide-2026/); dates confirmed by [QwenLM/Qwen3.8](https://github.com/QwenLM/Qwen3.8). The Qwen3.5 models are natively multimodal (text and image). — (via search snippet) [Qwen3.5 blog](https://qwen.ai/blog?id=qwen3.5), [ollama qwen3.5](https://ollama.com/library/qwen3.5)

**Qwen3-Coder-Next (Feb 2026):**
- Released 2026-02-04. It has 80B total and 3B active parameters and is built on Qwen3-Next-80B-A3B-Base (hybrid attention plus MoE). It was "agentically trained at scale" and is Apache 2.0 with a 262K native context. — (via search snippet) [Qwen blog](https://qwen.ai/blog?id=qwen3-coder-next), [DEV](https://dev.to/thousand_miles_ai/qwen3-coder-next-80b-total-3b-active-706-on-swe-bench-2g5o). The technical report is arXiv 2603.00729, dated 2026-03-03. — [arXiv](https://arxiv.org/pdf/2603.00729)
- The official README lists it as non-thinking, with 256K native context and 1M via YaRN. — [QwenLM/Qwen3-Coder README (fetched)](https://raw.githubusercontent.com/QwenLM/Qwen3-Coder/main/README.md)
- It needs a machine with about 64 GB. At Q4_K_M it needs about 52 GB. — (via search snippet) [localaimaster](https://localaimaster.com/models/qwen-3-coder-next), [ollama tags](https://ollama.com/library/qwen3-coder-next/tags)

**Qwen3-Coder-30B-A3B-Instruct (July 2025, older):** 30B total and 3B active parameters, 256K native context and 1M via YaRN, non-thinking only. The README says it "supports only non-thinking mode and does not generate `<think></think>` blocks". Function calling "relies on our new tool parser" in SGLang and vLLM, which is the XML-style qwen3_coder format. — [QwenLM/Qwen3-Coder README (fetched)](https://raw.githubusercontent.com/QwenLM/Qwen3-Coder/main/README.md). The Qwen3-Coder family was first released July 23, 2025 under Apache 2.0. — (via search snippet) [TechNow](https://tech-now.io/en/blogs/qwen3-coder-ollama-open-source-dream-stack-for-coders/). Ollama describes qwen3-coder:30b as 30B total with 3.3B activated. — (via search snippet) same source.

**Qwen3-30B-A3B-Instruct-2507 / Thinking-2507 (July 2025, older):**
- The Instruct model has 30.5B total and 3.3B active parameters and runs in non-thinking mode only. — (via search snippet) [OpenRouter](https://openrouter.ai/qwen/qwen3-30b-a3b-instruct-2507)
- The 2507 refresh dropped hybrid thinking in favor of separate Instruct and Thinking models, and the Instruct models have a 256K context. — (via search snippet) [Simon Willison 2025-07-30](https://simonwillison.net/2025/Jul/30/qwen3-30b-a3b-thinking-2507/), [Unsloth Qwen3-2507 docs](https://unsloth.ai/docs/models/tutorials/qwen3-how-to-run-and-fine-tune/qwen3-2507)

**Original Qwen3 dense 4B/8B/14B/32B (Apr 2025, older):** These launched at the end of April 2025 with hybrid thinking. Thinking can be switched per turn with `/think` and `/no_think` in the prompt when `enable_thinking=True`. — (via search snippet) [Qwen docs](https://qwen.readthedocs.io/), [Unsloth](https://unsloth.ai/docs/models/tutorials/qwen3-how-to-run-and-fine-tune/qwen3-2507)

**Qwen2.5-Coder (late 2024, oldest):** Six sizes, from 0.5B through 1.5B, 3B, 7B and 14B up to 32B. — (via search snippet) [ollama qwen2.5-coder](https://ollama.com/library/qwen2.5-coder)

### Inferences
- **Current laptop shortlist (Sept 2026):** Qwen3.6-35B-A3B (MoE, fast), Qwen3.6-27B and Qwen3.8-27B (dense, stronger, slower), plus Qwen3.5-9B for 16 GB machines.
  - Qwen3-Coder-30B-A3B and Qwen3-30B-A3B-2507 are superseded. The Qwen3.6-35B-A3B has the same 3B-active footprint and a newer agentic-coding post-train.
  - Qwen2.5-Coder and the original Qwen3 dense models are two generations old.
- **Thinking and JSON:** All 3.5, 3.6 and 3.8 models think by default. For a "return one strict JSON object" workload, thinking will probably need to be off, or the app will need to strip the reasoning channel.
  - With Qwen3.8 under Ollama, thinking control may not work at all (see Q5). That makes llama.cpp `--jinja`, vLLM or MLX the safer runtime for 3.8.
- **Qwen3-Coder-Next** is only realistic on 64 GB+ unified-memory Macs. It needs about 52 GB at Q4, which leaves little headroom for KV cache at 16k-token prompts on a 64 GB machine.

### Gaps
- The exact published context lengths of the original Qwen3 dense models (4B/8B/14B/32B) and of Qwen3-30B-A3B-Thinking-2507 were not verified, because the Hugging Face cards were blocked.
- The exact release date of Qwen3-Coder-30B-A3B was not verified. Only the family date of July 23, 2025 was found.
- Whether Qwen3.8 has any open-weight sizes other than 27B and 2.4T-A95B: the official README lists only those two, and no 3.8-35B-A3B or 3.8 small models were found.
- The exact Qwen3.8-27B `reasoning_effort` values and how to fully disable thinking come from a secondary source (NxCode), not from the model card.

## 2. gpt-oss-20b and gpt-oss-120b: specs, MXFP4 memory, reasoning effort, harmony, license, tool calling, 2026 updates

### Takeaway
gpt-oss is still the same two August 2025 models, gpt-oss-20b (21B total, 3.6B active, runs in 16 GB) and gpt-oss-120b (117B total, 5.1B active, needs 80 GB). Both are Apache 2.0 and ship as MXFP4 MoE weights. They require the harmony response format and have low, medium and high reasoning effort. The only official follow-up found is gpt-oss-safeguard (Oct 2025). Claims of a 2026 "gpt-oss-8b" or a new license are not supported by primary sources.

### Cited Findings
- **Sizes:** gpt-oss-120b has "117B parameters with 5.1B active parameters" and gpt-oss-20b has "21B parameters with 3.6B active parameters". The 120b fits "into a single 80GB GPU" and the 20b runs "within 16GB of memory". — [openai/gpt-oss README (fetched)](https://github.com/openai/gpt-oss)
- **Precision:** "MXFP4 quantization of the MoE weights"; other tensors are BF16. "All evals were performed with the same MXFP4 quantization." — [openai/gpt-oss (fetched)](https://github.com/openai/gpt-oss)
- **License:** "Permissive Apache 2.0 license." — [openai/gpt-oss (fetched)](https://github.com/openai/gpt-oss)
- **Harmony format:** The models "were trained using our harmony response format and should only be used with this format; otherwise, they will not work correctly." — [openai/gpt-oss (fetched)](https://github.com/openai/gpt-oss)
- **Reasoning effort:** Users can "adjust the reasoning effort (low, medium, high)". — [openai/gpt-oss (fetched)](https://github.com/openai/gpt-oss). In Ollama, `think` accepts "low", "medium" and "high", and medium is the default. — (via search snippet) [Ollama thinking docs](https://docs.ollama.com/capabilities/thinking)
- **Tools:** Supported capabilities are "function calling, web browsing, Python code execution, and Structured Outputs". — [openai/gpt-oss (fetched)](https://github.com/openai/gpt-oss)
- **Release and exact counts:** Released 2025-08-05. Exact counts are 116.83B total / 5.13B active and 20.91B total / 3.61B active, with a 131,072-token context. — (via search snippet) [Morph](https://www.morphllm.com/gpt-oss); the model card PDF is dated August 5, 2025 — [OpenAI model card PDF](https://cdn.openai.com/pdf/419b6906-9da6-406c-a19d-1bb078ac7637/oai_gpt-oss_model_card.pdf)
- **2026 updates:**
  - gpt-oss-safeguard, a policy-classification fine-tune, shipped in October 2025 and is on Ollama as `gpt-oss-safeguard` in 20b and 120b. — (via search snippet) [ollama gpt-oss-safeguard](https://ollama.com/library/gpt-oss-safeguard)
  - gpt-oss-120b became an MLPerf Inference v6.0 benchmark in March 2026, according to a secondary and low-authority source. — (via search snippet) [FrankX](https://www.frankx.ai/blog/gpt-oss-analysis-2026)
- **Conflict or likely fabrication:** One search summary claimed "OpenAI shipped ... on June 9, 2026 ... gpt-oss-8b, gpt-oss-20b, and gpt-oss-120b", with 256K context and an "OpenAI Open Weight License 1.0". — (via search snippet) [freeainews](https://freeainews.com/open-source/openai-gpt-oss-open-weight-2026/). This is **contradicted** by the official repo, which lists only 120b and 20b under Apache 2.0 ([openai/gpt-oss](https://github.com/openai/gpt-oss)), and by the HF announcement, which covers two models ([HF blog](https://huggingface.co/blog/welcome-openai-gpt-oss)). A search for "gpt-oss-8b" found no primary source. Treat gpt-oss-8b as **not existing**.

### Inferences
- **gpt-oss-20b** is the only gpt-oss model that fits a 16-32 GB laptop, at a 14 GB download.
  - gpt-oss-120b (65 GB) fits only on 96-128 GB machines and is out of scope for this PoC except as a note.
  - Because the MXFP4 weights are the native release format, there is no "quantization quality loss" question with gpt-oss-20b, unlike GGUF quants of the Qwen models.
- **Harmony risks:** Because harmony is mandatory, every runtime (Ollama, llama.cpp, LM Studio, vLLM) must render and parse it correctly. Most gpt-oss tool-call and JSON failures in the wild are runtime or template issues, not weight issues (see Q5).

### Gaps
- The Ollama-specific context default for gpt-oss (listed as 128K on ollama.com) against the model's 131,072 maximum was not re-verified.
- No official OpenAI statement from 2026 about a gpt-oss successor was found. The OpenAI help-center release notes were blocked.

## 3. Published benchmark numbers (with who measured and when)

### Takeaway
Vendor numbers put the 2026 Qwen models far ahead on agentic coding. On SWE-bench Verified the vendor figures are Qwen3.6-27B 77.2, Qwen3.6-35B-A3B 73.4, Qwen3.5-27B 72.4 and Qwen3-Coder-Next 70.6, against gpt-oss-20b at 60.7 and gpt-oss-120b at 62.4. The only independent coding leaderboard with relevant rows, Aider polyglot, stopped adding entries in October 2025, so none of the 2026 Qwen models have independent Aider scores. No usable BFCL numbers for these exact models could be retrieved.

### Cited Findings

**Vendor-reported agentic coding numbers:**

| Model | SWE-bench Verified | Other results | Source |
|---|---|---|---|
| Qwen3.6-35B-A3B | 73.4 | Terminal-Bench 2.0 51.5; QwenWebBench 1,397 | (via search snippet) [Qwen blog, Apr 2026](https://qwen.ai/blog?id=qwen3.6-35b-a3b) |
| Qwen3.6-27B | 77.2 | SWE-bench Pro 53.5; Terminal-Bench 2.0 59.3 | (via search snippet) [Qwen blog](https://qwen.ai/blog?id=qwen3.6-27b), [HF card](https://huggingface.co/Qwen/Qwen3.6-27B) |
| Qwen3.5-27B | 72.4 | — | (via search snippet) [Qwen 3.6-27B blog / buildfastwithai](https://www.buildfastwithai.com/blogs/qwen3-6-27b-review-2026) |
| Qwen3-Coder-Next | 70.6 (SWE-Agent scaffold) | — | (via search snippet) [Qwen blog](https://qwen.ai/blog?id=qwen3-coder-next), [DEV](https://dev.to/thousand_miles_ai/qwen3-coder-next-80b-total-3b-active-706-on-swe-bench-2g5o) |
| Qwen3-Coder-30B-A3B | 50.3 | — | (via search snippet) [search result set incl. ssojet](https://ssojet.com/blog/best-local-llms-coding) |
| gpt-oss-120b (high) | 62.4 | Tau-Bench Retail 67.8; Aider polyglot 44.4 | [OpenAI model card, Aug 5 2025](https://cdn.openai.com/pdf/419b6906-9da6-406c-a19d-1bb078ac7637/oai_gpt-oss_model_card.pdf), (via search snippet) [arXiv 2508.10925](https://arxiv.org/html/2508.10925v1) |
| gpt-oss-20b (high) | 60.7 | Tau-Bench Retail 54.8; Aider polyglot 34.2 | same as above |

- Qwen3.6-27B Terminal-Bench 2.0 methodology: Harbor/Terminus-2 harness, 3h timeout, 32 CPU / 48 GB RAM, temperature 1.0, top_p 0.95, top_k 20, max_tokens 80K, 256K context, averaged over 5 runs.
- Qwen3-Coder-Next: some sources report 74.2 instead of 70.6, which is a **conflict** between sources.
- Qwen3-Coder-30B-A3B: the source of 50.3 is unclear, and the vendor card may differ (see Gaps).
- Qwen3.6-35B-A3B MCPMark (tool use) 37.0% — (via search snippet) [buildfastwithai](https://www.buildfastwithai.com/blogs/qwen3-6-35b-a3b-review) (secondary, vendor-derived).
- **Qwen3.8-27B:** The official card compares it with Qwen3.6-27B: Terminal-Bench 2.1 63.4 → 73.0; DeepSWE 1.1 13.3 → 42.2; OSWorld-Verified 63.9 → 84.3; SWE-MM 25.7 → 38.6. These are vendor figures, Aug 2026. — (via search snippet) [kingy.ai](https://kingy.ai/blog/qwen3-8-27b-specs-benchmarks-local-hardware/), [HF card](https://huggingface.co/Qwen/Qwen3.8-27B). No SWE-bench Verified number for Qwen3.8-27B was retrieved.

**Community and independent results:**
- A community "engineered agent stack" claims Qwen3.6-27B-FP8 reaches 90.0% on SWE-bench Verified. This is self-reported with a custom scaffold and not comparable to vendor numbers. — [QwenLM/Qwen3 discussion #1846](https://github.com/QwenLM/Qwen3/discussions/1846)
- **Aider polyglot** (independent, measured by Aider). The rows below are fetched from the leaderboard data file, [Aider polyglot_leaderboard.yml (fetched)](https://github.com/Aider-AI/aider/blob/main/aider/website/_data/polyglot_leaderboard.yml). The most recent date anywhere in the file is **2025-10-03**, so there are no entries for Qwen3-Coder-30B-A3B, Qwen3.5, Qwen3.6, Qwen3.8, Qwen3-Coder-Next or gpt-oss-20b.

| Model | Pass rate | Well-formed edits | Edit format | Date | Notes |
|---|---|---|---|---|---|
| gpt-oss-120b (high) | 41.8% | 79.1% | diff | 2025-08-06 | — |
| Qwen3 32B | 40.0% | 83.6% | diff | 2025-05-08 | via OpenRouter |
| Qwen3 235B-A22B | 59.6% | 92.9% | diff | 2025-05-09 | no-think |
| Qwen2.5-Coder-32B-Instruct | 16.4% | 99.6% | whole | 2024-12-26 | — |
| Qwen2.5-Coder-32B-Instruct | 8.0% | 71.6% | diff | 2024-12-22 | — |

- Aider's independently measured 41.8% for gpt-oss-120b is slightly below OpenAI's self-reported 44.4.
- **BFCL:** A search surfaced a third-party paper reporting BFCL v4 overall 40.06 for Qwen3-8B and 43.10 for Qwen3-32B ("base, 0-shot"). This is not from the official leaderboard, so the setting is unclear. — (via search snippet) [search result](https://gorilla.cs.berkeley.edu/leaderboard.html) (official leaderboard page blocked). The Qwen3-Coder BFCL-v3 evaluation found "room for improvement in multi-turn and parallel calls". — (via search snippet) [EvalScope Qwen3-Coder eval](https://evalscope.readthedocs.io/en/latest/best_practice/qwen3_coder.html)
- **Tool-use rankings in the Qwen3.5 cards:** The Qwen3.5 small-model cards rank tool use by an average over BFCL-V4, VITA-Bench, DeepPlanning, Tool-Decathlon and MCP-Mark. The exact per-model numbers were not retrievable. — (via search snippet) [Qwen/Qwen3.5-9B card](https://huggingface.co/Qwen/Qwen3.5-9B)

### Inferences
- On vendor numbers, any 2026 Qwen model (27B dense or 35B-A3B) is well ahead of gpt-oss-20b for agentic coding: roughly 72-77 against 61 on SWE-bench Verified. The gap is likely smaller on the PoC's much simpler task of writing one small Python file plus unittest tests and then fixing it.
- Note the harness differences: Qwen uses its own scaffolds or SWE-Agent, while OpenAI's gpt-oss runs are at high reasoning. Nobody independent has run all of these side by side.
- The PoC should run its own small eval, for example 10 tasks × 3 runs per model, rather than rely on these numbers. There is no independent 2026 leaderboard that covers both families.

### Gaps
- Official BFCL v4 leaderboard rows for gpt-oss-20b, Qwen3.6 and Qwen3.8 could not be retrieved (site blocked).
- tau2-bench, IFEval, LiveCodeBench and EvalPlus numbers for Qwen3.6, Qwen3.8 and Qwen3.5 are only in the HF cards, which were blocked. No numbers were retrieved.
- The Qwen3-Coder-30B-A3B vendor SWE-bench Verified number could not be confirmed; the snippet gave 50.3.
- The SWE-bench Verified number for Qwen3.5-35B-A3B was not found.
- The official LiveCodeBench leaderboard was not checked (blocked).

## 4. Exact Ollama tags, download sizes, and "tools"/"thinking" capability badges

### Takeaway
All relevant models are in the official Ollama library.

| Model | Tag | Download size | Fits |
|---|---|---|---|
| Qwen3.5 small | `qwen3.5:9b` | 6.6 GB | 16 GB laptops |
| gpt-oss | `gpt-oss:20b` | 14 GB | 16 GB laptops |
| Qwen3.5 medium | `qwen3.5:27b` | 17 GB | 32 GB laptops |
| Qwen3.6 dense | `qwen3.6:27b` | 18 GB | 32 GB laptops |
| Qwen3.8 dense | `qwen3.8:27b` | 18 GB | 32 GB laptops |
| Qwen3.6 MoE | `qwen3.6:35b` | 23 GB | 32 GB laptops |
| Qwen3.5 MoE | `qwen3.5:35b` | 24 GB | 32 GB laptops |
| Qwen3-Coder-Next | `qwen3-coder-next` | 52 GB | 64 GB machines only |

The qwen3.6 and gpt-oss pages show both "tools" and "thinking" badges.

### Cited Findings
- **gpt-oss:** `gpt-oss:20b` is 14 GB and `gpt-oss:120b` is 65 GB. Both have a 128K context and text input, and the page carries the badges "tools thinking cloud". — (via search snippet) [ollama.com/library/gpt-oss](https://ollama.com/library/gpt-oss), [tags](https://ollama.com/library/gpt-oss/tags)
- **qwen3.6:**
  - `qwen3.6:27b` is 18 GB and `qwen3.6:35b`/latest is 23 GB. Both have a 256K context and take text and image input.
  - There are MLX variants: `qwen3.6:27b-mlx` (19 GB) and `35b-mlx` (24 GB).
  - Other tags seen include `qwen3.6:27b-q4_K_M`, `qwen3.6:27b-coding-mxfp8` and `qwen3.6:35b-a3b`.
  - The capabilities are "vision, tools, and thinking". "Every tag supports tools and thinking; Qwen 3.6 thinks by default", and `"think": false` turns thinking off.
  - — (via search snippet) [ollama qwen3.6](https://ollama.com/library/qwen3.6), [tags](https://ollama.com/library/qwen3.6/tags), [qwen3.6:35b-a3b](https://ollama.com/library/qwen3.6:35b-a3b), [qwen3.6:27b-coding-mxfp8](https://ollama.com/library/qwen3.6:27b-coding-mxfp8)
- **qwen3.5:**
  - Sizes: `qwen3.5:0.8b` 1.0 GB, `2b` 2.7 GB, `4b` 3.4 GB, `9b` 6.6 GB, `27b` 17 GB and `35b` 24 GB.
  - All have a 256K context and take text and image input.
  - — (via search snippet) [ollama qwen3.5 tags](https://ollama.com/library/qwen3.5/tags), [qwen3.5:9b](https://ollama.com/library/qwen3.5:9b), [qwen3.5:27b](https://ollama.com/library/qwen3.5:27b), [needtoknowit](https://needtoknowit.com.au/blog/best-ollama-models-to-download/)
- **qwen3.8:**
  - The default `qwen3.8:27b` is q4_K_M, an 18 GB download with a 256K context and vision.
  - Larger tags are `q8_0` at 30 GB and `bf16` at 56 GB. Other tags include `27b-mxfp8`, `27b-mlx`, `27b-nvfp4`, `27b-q8_0` and `27b-q4_K_M`.
  - — (via search snippet) [ollama qwen3.8 tags](https://ollama.com/library/qwen3.8/tags), [qwen3.8:27b](https://ollama.com/library/qwen3.8:27b), [Yotta Labs](https://www.yottalabs.ai/post/how-to-run-qwen-3-8-with-ollama-2026)
- **qwen3-coder-next:** The default is Q4_K_M at 52 GB, and Q8_0 is 85 GB. — (via search snippet) [ollama qwen3-coder-next tags](https://ollama.com/library/qwen3-coder-next/tags), [qwen3-coder-next:q4_K_M](https://ollama.com/library/qwen3-coder-next:q4_K_M)
- **qwen3-coder:** `qwen3-coder:30b` (30B total / 3.3B active) is in the official library. A user reports that local `qwen3-coder:30b` follows JSON-schema `format` correctly, while the cloud 480b tag ignored the schema. — [ollama issue #12362 (fetched)](https://github.com/ollama/ollama/issues/12362); tag listing (via search snippet) [ollama qwen3-coder](https://ollama.com/library/qwen3-coder)
- **qwen2.5-coder:** Six sizes, 0.5B, 1.5B, 3B, 7B, 14B and 32B. — (via search snippet) [ollama qwen2.5-coder](https://ollama.com/library/qwen2.5-coder)
- **Broken quants:** The `qwen2.5-coder:3b-instruct` q2_K/q3_K_* library artifacts are reported "functionally broken (0% on code tasks)". — [ollama issue #18252](https://github.com/ollama/ollama/issues/18252) (title fetched via GitHub search)
- **Ollama version in use:** Recent issues reference Ollama 0.32.6-0.32.15 (Aug-Sep 2026). — [#17638](https://github.com/ollama/ollama/issues/17638), [#18094](https://github.com/ollama/ollama/issues/18094)

### Inferences
- **16 GB laptop:** `gpt-oss:20b` (14 GB) or `qwen3.5:9b` (6.6 GB). A 27B at Q4 (17-18 GB) will not fit alongside 16k-token KV cache and the OS.
- **32 GB laptop:** `qwen3.6:35b` (23 GB, MoE, fastest), `qwen3.6:27b` or `qwen3.8:27b` (18 GB, dense, slower), or `gpt-oss:20b` with lots of headroom.
- **64 GB laptop:** all of the above, and `qwen3-coder-next` becomes borderline possible.
- **Apple Silicon:** The `-mlx` tags exist for qwen3.6 and qwen3.8 and are likely the faster choice on Macs. This was not benchmarked here.

### Gaps
- Exact download sizes for `qwen3-coder:30b`, `qwen3:4b/8b/14b/32b` and `qwen2.5-coder:7b/14b/32b` were not verified because ollama.com was blocked. One search summary gave a wrong size list for qwen3 that matched qwen2.5, so it was discarded.
- Whether the `qwen3-coder` and `qwen2.5-coder` library pages show a "tools" badge was not verified.
- Whether `qwen3.8` shows a "thinking" badge was not verified.

## 5. Independent evidence on strict-JSON / tool-call reliability and multi-file Python in practice

### Takeaway
There is no independent head-to-head JSON-schema-adherence benchmark for these models. What exists is a steady stream of open Ollama bugs (Aug-Sep 2026) in both families:
- **gpt-oss:** harmony tool-call parse errors, meaning HTTP 500s and tool calls that never complete.
- **Qwen3.6:** reasoning leaking into `format: json` output when `think:false`.
- **Qwen3.8:** 500s in tool loops and uncontrollable thinking.
- **qwen3-coder:** lost or garbled XML tool calls.
- **All models:** grammar-constrained decoding that silently alters strings.

The practical conclusion is to use `format` with a JSON schema, validate every response, and retry. llama.cpp `--jinja` repeatedly appears as the more reliable runtime for gpt-oss and Qwen3.8.

### Cited Findings

**gpt-oss on Ollama:**
- **Issue #17638 (2026-08-09, open, Ollama 0.32.6):** `gpt-oss:20b` returns HTTP 500 "error parsing tool call". The model emits an array-wrapped `[{"input": …}]`, which Ollama's parser rejects.
  - The failure is non-deterministic, "roughly 2 in 5". It is triggered by an apply_patch-style tool with one large string argument, a prior tool result of about 1.6 KB, and a long tool description: 2/5 failures with a 1224 B description against 0/5 with a 105 B one.
  - The same weights served by llama.cpp `llama-server --jinja` gave "8/8 valid tool calls" and ran "~74 tok/s against ~61" under Ollama.
  - — [ollama #17638 (fetched)](https://github.com/ollama/ollama/issues/17638)
- **Issue #12187 (2025-09-04, open, 40 comments):** "GPT-OSS not completing tool calls". — [ollama #12187](https://github.com/ollama/ollama/issues/12187)
- **Issue #12884 (2025-10-31, open):** "error parsing tool call ... invalid character ... after top-level value" with gpt-oss via /api/chat. — [ollama #12884](https://github.com/ollama/ollama/issues/12884)
- **Issue #12763 (2025-10-24, open):** The gpt-oss template ignores `enum` in array tool parameters and renders `any[]`. — [ollama #12763 (fetched)](https://github.com/ollama/ollama/issues/12763)
- **Structured output elsewhere:**
  - Hugging Face threads report "tool calling not working as expected" and "Unable to Structured output" for gpt-oss-20b. — [HF gpt-oss-20b #80](https://huggingface.co/openai/gpt-oss-20b/discussions/80), [HF #111](https://huggingface.co/openai/gpt-oss-20b/discussions/111) (titles via search)
  - A search summary reports that vLLM with xgrammar "often generates random text or random JSON after the correct JSON" for gpt-oss. — (via search snippet; underlying source not opened)

**Qwen on Ollama:**
- **Issue #17871 (2026-08-19, open, 9 comments):** `qwen3.6:35b-a3b-q8_0` with `think: false` plus `format: "json"` returns "the model's reasoning serialized as a syntactically valid JSON object instead of the requested schema".
  - Example outputs are `{"thought": ...}` and `{"thought_process": [...]}`.
  - It is deterministic, failing on 3 of 14 documents at temperature 0 and seed 42 with num_ctx 32768.
  - It is a regression between Ollama 0.31.2 and 0.32.14, with no fix at the time of reading.
  - — [ollama #17871 (fetched)](https://github.com/ollama/ollama/issues/17871)
- **Issue #17778 (2026-08-15, open, 44 comments):** `qwen3.8:27b-q4_K_M` returns 500 "no user query found in messages" after tool results are handed back in multi-step tool loops, on Ollama 0.32.13. The reporter notes "No issues with qwen 3.5 or 3.6 27b/35b variants with same code." — [ollama #17778 (fetched)](https://github.com/ollama/ollama/issues/17778)
- **Issue #18094 (2026-08-28, Ollama 0.32.15):** Under grammar-constrained `format`, `qwen3.5:9b` (and gemma4:e4b) "silently replac[e] the double quotes from the source text with single quotes" instead of escaping them. gemma3:12b truncates instead. The reporter warns this gives "schema-valid but content-altered output with no error". — [ollama #18094 (fetched)](https://github.com/ollama/ollama/issues/18094)
- **Other qwen3-coder issues (Sep 2026):**
  - The tool call is silently lost when the model puts reasoning before it. — [#18530](https://github.com/ollama/ollama/issues/18530)
  - The parser changes number arguments outside the int64 range. — [#18421](https://github.com/ollama/ollama/issues/18421)
  - Tool-schema keys render in random order, which busts the prompt cache. — [#18430](https://github.com/ollama/ollama/issues/18430)
- **Older qwen3 parser issues (Mar 2026):**
  - The qwen3 tool-call parser returns 500 when output is truncated. — [#14570](https://github.com/ollama/ollama/issues/14570)
  - "qwen tool call parsing failed … XML syntax error … unexpected EOF". — [#14834](https://github.com/ollama/ollama/issues/14834)

**Generic Ollama structured-output limits that affect all models:**
- Tool-parameter JSON-Schema constraints (minimum, maximum, default and so on) are "silently dropped at parse time". — [#17142](https://github.com/ollama/ollama/issues/17142)
- The `pattern` keyword causes "invalid JSON schema in format". — [#12726 (fetched)](https://github.com/ollama/ollama/issues/12726)
- Object key order is not preserved. — [#8461 (fetched)](https://github.com/ollama/ollama/issues/8461)
- Top-level arrays are mishandled. — [#8000 (fetched)](https://github.com/ollama/ollama/issues/8000)

**Positive reports:**
- Local `qwen3-coder:30b` followed a JSON reply schema generated by invopop/jsonschema. — [#12362 (fetched)](https://github.com/ollama/ollama/issues/12362)
- A gemma4 structured-output issue says the same RAG pipeline works "with other models such as nemo, gpt-oss, qwen, deepseek". — [#15576 (fetched)](https://github.com/ollama/ollama/issues/15576)

**Community opinion (weak, unattributed search summaries):**
- "Qwen3-4b-instruct-2507 is more useful with tools than the gpt-oss-120b", while gpt-oss:20b "does an excellent job at instruction following". Some users say gpt-oss fails "when requiring a JSON response format". — (via search snippet) [HF gpt-oss-20b discussions](https://huggingface.co/openai/gpt-oss-20b/discussions/80), [glukhov.org Ollama+Qwen3 structured output](https://www.glukhov.org/llm-performance/ollama/llm-structured-output-with-ollama-in-python-and-go/). The r/LocalLLaMA threads themselves could not be opened.

**Speed, dense 27B against 35B-A3B:** A community test found the 35B-A3B "3.5-4x faster at token generation and 2-2.4x faster at prompt processing" than the 27B, while "the 27B delivers better quality". — (via search snippet) [zoliben.com Qwen 3.6 35B vs 27B, 2026-04-23](https://zoliben.com/en/posts/2026-04-23-qwen-36-35b-vs-27b-benchmark-results/). Prompt-processing speed matters here because of the PoC's 3k-16k-token prompts.

### Inferences
- **What the app should do for strict JSON:**
  - Send an explicit JSON schema in `format`, not just `"json"`.
  - Set `think: false` for the Qwen models, but validate every reply, because #17871 shows `{"thought": ...}` objects that are schema-invalid yet syntactically valid JSON.
  - Keep schemas simple: a top-level object, no `pattern`, no reliance on key order.
  - Keep retry-with-error-feedback logic.
- **Tool calls against plain JSON:** For gpt-oss-20b, avoid Ollama tool-calling for large string arguments such as whole files. Asking for a single JSON object through `format` (response-format mode) is likely more reliable than the tool-call path, though that is not tested here.
  - Alternatively, serve gpt-oss-20b through llama.cpp `--jinja`, which a detailed issue report shows gave 8/8 valid calls against 1/3 end-to-end via Ollama.
- **Multi-file Python:** No independent multi-file Python evidence for these exact 2026 models was found. SWE-bench Verified (vendor) and Aider 2025 rows are the closest proxies, and a local eval is warranted.
- **Grammar-constrained decoding and code:** It can silently rewrite quotes (#18094). For the PoC, Python code embedded as a JSON string value, which is full of `"` and newlines, is exactly the risky case.
  - The app should compare the embedded code against a syntax check (`ast.parse`) and run the tests. It should not trust schema validity alone.

### Gaps
- No independent, quantified JSON-schema-adherence benchmark covering Qwen3.6, Qwen3.8 or gpt-oss-20b was found, for example JSONSchemaBench or a similar 2026 study.
- No r/LocalLLaMA thread content could be read (reddit not reachable), so community sentiment is from search summaries only.
- The llama.cpp (ggml-org) GitHub issues on these models were not searched in this session. Only ollama/ollama was searched.
- Whether Ollama fixed #17871, #17638 or #17778 after the dates above is unknown. All three were open when fetched on 2026-09-26.
