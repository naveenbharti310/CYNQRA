# Local LLM runtimes for laptops and strict JSON output (as of 26 September 2026)

Scope: Ollama, llama.cpp (llama-server), LM Studio, vLLM, plus MLX / mlx-lm and llamafile. The target is a Python app that uses only the standard library (urllib), runs on Windows, macOS and Linux laptops, and needs exactly one strict JSON object per call. Some string values hold whole Python files.

Method note: most Ollama and llama.cpp facts come from reading the source and docs at HEAD on 2026-09-26. I used git clones of github.com/ollama/ollama (HEAD 16b4376, committed 2026-09-26) and github.com/ggml-org/llama.cpp (HEAD committed 2026-09-26), mapped commits to release tags with `git tag --contains`, and took dates from the tag commits. The network proxy blocked lmstudio.ai, docs.vllm.ai and huggingface.co. For those I read the same docs from their GitHub source repos: lmstudio-ai/docs, vllm-project/vllm/docs, ml-explore/mlx-lm, mozilla-ai/llamafile and QwenLM/Qwen3. The version snapshot on 2026-09-26 is: Ollama v0.34.4 (tagged 2026-09-23), llama.cpp build tag b11201, vLLM tag v0.30.0, mlx-lm v0.31.3, llamafile 0.10.6, and LM Studio 0.4.x (the newest in its API changelog is 0.4.1).

## Q1. Install ease per OS, licensing, and whether a non-engineer can install it

### Takeaway
Ollama is the easiest runtime for a non-engineer on all three operating systems. It has a GUI installer on Windows (no admin rights needed) and macOS, a one-line script on Linux, runs as a background service or login item, and is MIT-licensed. LM Studio is just as friendly but proprietary: it is free for personal and internal business use, and redistribution or SaaS is not allowed. llama.cpp is MIT and installs with winget or brew, but the user must pick a model file and start the server with flags. vLLM is built for GPU servers, not laptops. mlx-lm is Apple-only and says it is "not recommended for production". llamafile is a single-file executable under Apache 2.0, but it is in a rebuild phase (0.10.x) and some features are missing.

### Cited Findings
**Ollama**
- Install commands: macOS `curl -fsSL https://ollama.com/install.sh | sh` or the manual `Ollama.dmg`; Windows PowerShell `irm https://ollama.com/install.ps1 | iex` or the manual `OllamaSetup.exe`; Linux `curl -fsSL https://ollama.com/install.sh | sh`. A Homebrew formula also exists. — [Ollama README](https://github.com/ollama/ollama/blob/main/README.md)
- License: MIT ("Copyright (c) Ollama"). — [Ollama LICENSE](https://github.com/ollama/ollama/blob/main/LICENSE)
- Windows: "The Ollama install does not require Administrator, and installs in your home directory by default". It needs at least 4 GB for the binaries. Requirements are Windows 10 22H2 or newer (Home or Pro), NVIDIA driver 551.61 or newer for NVIDIA cards, and for AMD either a ROCm v7 / HIP7 driver stack or a Vulkan-capable Radeon driver. Binaries go to `%LOCALAPPDATA%\Programs\Ollama` (added to the user PATH). Models and config go to `%HOMEPATH%\.ollama` and logs to `%LOCALAPPDATA%\Ollama`. After install, "Ollama will run in the background". — [docs/windows.mdx](https://github.com/ollama/ollama/blob/main/docs/windows.mdx)
- macOS: drag `Ollama.app` from the dmg into Applications. On first start the app offers to link the CLI into `/usr/local/bin`. Requirements: "Apple M series (CPU and GPU support) or x86 (CPU only)". — [docs/macos.mdx](https://github.com/ollama/ollama/blob/main/docs/macos.mdx)
- Linux: install script or tarballs (`ollama-linux-amd64.tar.zst`, `-rocm`, `arm64`). Running as a systemd service is the recommended setup. — [docs/linux.mdx](https://github.com/ollama/ollama/blob/main/docs/linux.mdx)
- On Windows and macOS, Ollama "register[s] as a login item during installation", so it starts automatically. — [docs/faq.mdx](https://github.com/ollama/ollama/blob/main/docs/faq.mdx)
- Ollama binds 127.0.0.1:11434 by default (`OLLAMA_HOST` changes it). — [docs/faq.mdx](https://github.com/ollama/ollama/blob/main/docs/faq.mdx)
- Architecture change in v0.30.0 (tagged 2026-06-01): the commit "runner: Remove CGO engines, use llama-server exclusively for GGML models (#16031)" (2026-05-29) made Ollama run upstream `llama-server` as a subprocess for all GGUF models. An MLX runner also exists for `-mlx` models. — [commit 9db4bdba](https://github.com/ollama/ollama/commit/9db4bdba); [llm/llama_server.go header](https://github.com/ollama/ollama/blob/main/llm/llama_server.go)

**llama.cpp / llama-server**
- License MIT. The quick start offers llama.app, Docker, prebuilt binaries from the releases page, or building from source. The unified CLI is `llama cli -hf ggml-org/Qwen3.5-0.8B-GGUF` and `llama serve -hf ...` ("Launch OpenAI-compatible API server"). — [llama.cpp README](https://github.com/ggml-org/llama.cpp/blob/master/README.md)
- Package managers: `winget install llama.cpp` (Windows), `brew install llama.cpp` (macOS and Linux), `sudo port install llama.cpp` (MacPorts), and `nix profile install nixpkgs#llama-cpp`. — [docs/install.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md)
- The latest build tag seen via `git ls-remote` on 2026-09-26 is `b11201`. llama.cpp ships many numbered builds rather than semantic versions. — [llama.cpp tags](https://github.com/ggml-org/llama.cpp/tags)

**LM Studio**
- There are three pieces. The desktop GUI app downloads models from Hugging Face and serves OpenAI- and Anthropic-compatible endpoints. `llmster` is a "headless daemon – a standalone background service that can run without a GUI". `lms` is the CLI (`lms get`, `lms load`, `lms server start`), and the server listens on `http://localhost:1234`. — [LM Studio docs: LM Studio vs llmster vs lms](https://github.com/lmstudio-ai/docs/blob/main/0_app/1_basics/lmstudio-vs-llmster-vs-lms.md) (published at lmstudio.ai/docs)
- llmster install: `curl -fsSL https://lmstudio.ai/install.sh | bash`. The docs include a systemd unit for Linux. — [headless_llmster.mdx](https://github.com/lmstudio-ai/docs/blob/main/1_developer/0_core/headless_llmster.mdx)
- The `lms` CLI is MIT licensed (github.com/lmstudio-ai/lms). — [LM Studio CLI docs](https://github.com/lmstudio-ai/docs/blob/main/3_cli/index.mdx)
- The app is proprietary. Since 2025-07-08 it has been "free for use at work", with no separate commercial license needed. The terms allow "personal and / or internal business purposes" and forbid sublicensing, distribution, service-bureau, ASP or SaaS use. — [LM Studio blog: free for work](https://lmstudio.ai/blog/free-for-work); [Simon Willison summary](https://simonwillison.net/2025/Jul/8/lm-studio-is-free-for-use-at-work/); [LM Studio App Terms](https://lmstudio.ai/app-terms) (terms wording from search-result summaries; lmstudio.ai itself was blocked for direct fetch)

**vLLM**
- Install with `uv pip install vllm` (or pip). The README lists NVIDIA, AMD and Intel GPUs, x86/ARM/PowerPC CPUs, and hardware plugins including Apple Silicon. — [vLLM README](https://github.com/vllm-project/vllm/blob/main/README.md)
- The latest tag seen on 2026-09-26 is v0.30.0. — [vLLM tags](https://github.com/vllm-project/vllm/tags)

**MLX / mlx-lm**
- `mlx_lm.server` starts an HTTP server on `localhost:8080`. The docs warn: "The MLX LM server is not recommended for production as it only implements basic security checks." `--kv-bits` quantizes the KV cache, and "A quantized KV cache does not support batching". — [mlx-lm SERVER.md](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md)
- Latest tag: v0.31.3. — [mlx-lm tags](https://github.com/ml-explore/mlx-lm/tags)

**llamafile**
- A single-file executable (llama.cpp plus Cosmopolitan Libc) that "runs locally on most operating systems and CPU architectures, with no installation". It is Apache 2.0 and now maintained by Mozilla.ai. Versions from 0.10.0 on use a new build system aligned with recent llama.cpp but "might be missing some of the features you were accustomed to". — [llamafile README](https://github.com/mozilla-ai/llamafile/blob/main/README.md)
- Latest tag: 0.10.6. — [llamafile tags](https://github.com/mozilla-ai/llamafile/tags)

### Inferences
- Ollama is the only candidate that meets all of these at once: an MIT license the app can depend on without legal review, a no-admin Windows GUI installer, a dmg on macOS, a background service on every OS, and one CLI command to fetch a model (`ollama pull <model>`). A non-engineer can install it.
- LM Studio is equally easy to install. Its proprietary terms are fine when each user installs it themselves, but they rule out bundling or redistributing it with the app.
- llama-server is technically the most capable and transparent option, but a non-engineer would have to choose GGUF files and launch flags. It suits power users or a later "bundled server" design.
- vLLM, mlx-lm and llamafile should not be the primary target. vLLM is aimed at GPU servers, mlx-lm is Apple-only and not production-hardened, and llamafile 0.10.x is mid-rewrite.

### Gaps
- I could not fetch LM Studio's download page to confirm current installer formats (exe / dmg / AppImage) or its minimum OS versions.
- vLLM platform matrix: I have no fetched source confirming that Windows is unsupported natively (WSL is commonly needed) or that macOS is CPU-only. docs.vllm.ai was blocked.
- llamafile's historical Windows 4 GB executable-size limit was not re-verified for 0.10.x.
- I did not capture exact release dates for llama.cpp b11201, vLLM v0.30.0 or LM Studio 0.4.x.

## Q2. HTTP APIs: endpoints, request/response fields, token usage, streaming and timeouts

### Takeaway
Use Ollama's native `POST /api/chat` with `"stream": false`. It is the only Ollama endpoint that accepts every knob this app needs (`format` schema, `think`, `options.num_ctx`, `keep_alive`, `truncate`/`shift`), and it returns token counts as `prompt_eval_count` and `eval_count`. The OpenAI-compatible `/v1/chat/completions` endpoints (Ollama, llama-server, LM Studio) return the standard `usage` object and accept `response_format`. On Ollama, though, that endpoint cannot set the context size per request.

### Cited Findings
**Ollama native API (`/api/chat`, `/api/generate`)**
- Chat request fields include `model`, `messages`, `think` (boolean or a level such as `"low"`, `"medium"`, `"high"` or `"max"`), `format` ("`json` or a JSON schema"), `options` (Modelfile parameters such as `temperature`), `stream`, and `keep_alive` (default `5m`). For `stream`: "if `false` the response will be returned as a single response object, rather than a stream of objects". Streaming is therefore the default. — [docs/api.md](https://github.com/ollama/ollama/blob/main/docs/api.md)
- Chat responses return `message.content` and, for thinking models, `message.thinking`. Generate responses return `response` and `thinking`. — [docs/capabilities/thinking.mdx](https://github.com/ollama/ollama/blob/main/docs/capabilities/thinking.mdx)
- Usage fields: `total_duration`, `load_duration`, `prompt_eval_count` ("How many input tokens were in the prompt"), `prompt_eval_cached_count`, `prompt_eval_duration`, `eval_count` (output tokens), and `eval_duration`, all durations in nanoseconds. "For endpoints that return streaming responses, usage fields are included as part of the final chunk, where `done` is `true`." — [docs/api/usage.mdx](https://github.com/ollama/ollama/blob/main/docs/api/usage.mdx)
- `done_reason` is `"stop"` or `"length"` in the runner's `DoneReason` enum, plus `"unload"` for unload calls. — [llm/server.go](https://github.com/ollama/ollama/blob/main/llm/server.go); [docs/api.md](https://github.com/ollama/ollama/blob/main/docs/api.md)
- Example of a full options object from the docs: `{"model":"llama3.2","prompt":"Why is the sky blue?","stream":false,"options":{"num_keep":5,"seed":42,"num_predict":100,"top_k":20,"top_p":0.9,"min_p":0.0,"temperature":0.8,"repeat_penalty":1.2,"presence_penalty":1.5,"frequency_penalty":1.0,"stop":["\n","user:"],"num_ctx":1024,"num_batch":2,"num_gpu":1,"main_gpu":0,"use_mmap":true,"num_thread":8}}` — [docs/api.md "Generate request (With options)"](https://github.com/ollama/ollama/blob/main/docs/api.md)
- Chat and generate requests also accept `truncate` ("truncates the chat history messages if the rendered prompt exceeds the context length limit") and `shift` ("shifts the chat history when hitting the context length limit instead of erroring"). Both were added in v0.12.6 (commit 6544e147, 2025-10-11). — [api/types.go](https://github.com/ollama/ollama/blob/main/api/types.go); [commit 6544e147](https://github.com/ollama/ollama/commit/6544e147)

**Ollama OpenAI-compatible API (`/v1/chat/completions`)**
- Supported request fields: `model`, `messages`, `frequency_penalty`, `presence_penalty`, `response_format`, `seed`, `stop`, `stream`, `stream_options.include_usage`, `temperature`, `top_p`, `max_tokens`, `tools`, `reasoning_effort` and `reasoning.effort`. Not supported: `tool_choice`, `logit_bias`, `user`, `n`, and logprobs. The API key is "required but ignored". — [docs/api/openai-compatibility.mdx](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx)
- "The OpenAI API does not have a way of setting the context size for a model. If you need to change the context size, create a `Modelfile`" (`PARAMETER num_ctx <context size>`, then `ollama create mymodel`). — [docs/api/openai-compatibility.mdx](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx)
- The code maps `response_format.type == "json_object"` to format `"json"` and `"json_schema"` to `response_format.json_schema.schema`. Other fields such as `strict` are not read. — [openai/openai.go](https://github.com/ollama/ollama/blob/main/openai/openai.go)
- v0.32.6 changed the streaming wire format for chat completions to match OpenAI's ("openai: match openai's streaming wire format for chat completions (#17485)", 2026-08-03). — [commit 8edecb5c](https://github.com/ollama/ollama/commit/8edecb5c)

**llama-server**
- `/v1/chat/completions` supports both streaming and non-streaming. The docs say "no strong claims of compatibility with OpenAI API spec is being made". `/completion`-specific options are also accepted. — [tools/server/README.md](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- Responses include a standard `usage` object (`completion_tokens`, `prompt_tokens`, `total_tokens`, `prompt_tokens_details.cached_tokens`) and a `timings` object (`cache_n`, `prompt_n`, `predicted_n`, and per-second rates). "The total number of tokens in context is equal to `prompt_n + cache_n + predicted_n`". — [tools/server/README.md](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- Server timeout: `-to, --timeout N`, "server read/write timeout in seconds (default: 3600)" (env `LLAMA_ARG_TIMEOUT`). `--api-key` is optional. — [tools/server/README.md](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- The `/completion` response has a `truncated` boolean that is true when prompt tokens plus predicted tokens exceeded `n_ctx`. `stop_type` `limit` means `n_predict` was hit. `n_predict` defaults to -1 (infinite). — [tools/server/README.md](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)

**LM Studio**
- OpenAI-compatible `POST http://localhost:1234/v1/chat/completions`. The native v1 REST API at `/api/v1/*` became official in LM Studio 0.4.0; it includes stateful chats, auth tokens, and model download, load and unload. 0.4.1 added the Anthropic-compatible `POST /v1/messages`. — [LM Studio API changelog](https://github.com/lmstudio-ai/docs/blob/main/1_developer/api-changelog.md)
- `POST /api/v1/models/load` accepts `context_length`, `eval_batch_size`, `flash_attention` (llama.cpp engine only), `num_experts` and `echo_load_config`. — [LM Studio REST load docs](https://github.com/lmstudio-ai/docs/blob/main/1_developer/2_rest/load.md)
- Per-request `"ttl"` in seconds for JIT-loaded models, and `lms load --ttl <seconds>` (0.3.9, 2025-01-30). — [LM Studio API changelog](https://github.com/lmstudio-ai/docs/blob/main/1_developer/api-changelog.md)

**mlx-lm**
- The OpenAI-style server returns a `usage` dictionary. Its request parameters include `max_tokens` and repetition, presence and frequency penalties. SERVER.md documents no `response_format` or JSON-schema parameter. — [mlx-lm SERVER.md](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md)

### Inferences
- With `"stream": false` the server sends nothing until generation finishes. Python's `urllib.request.urlopen(..., timeout=T)` applies T to each blocking socket operation, so T must be longer than the whole generation, which can take several minutes for a whole Python file on a CPU-only laptop. A timeout of 600–1800 s is reasonable. The alternative is `"stream": true`, reading NDJSON lines from Ollama (or SSE `data:` lines from `/v1`) and keeping a total deadline. Streaming also gives progress feedback and lets the app detect stalls. (This is general Python and HTTP behaviour; I fetched no source for it.)
- Ollama applies no server-side cap on generation time; the only related knob is the model-load stall timeout (see Q6). The client timeout therefore governs, and a client disconnect cancels generation (`DoneReasonConnectionClosed` exists in the runner).
- To detect a truncated JSON output, check `done_reason == "length"` on Ollama or `finish_reason == "length"` on the `/v1` endpoints, then retry with a larger `num_predict` or `num_ctx`.

### Gaps
- The fetched sources give no documented Ollama server-side HTTP read/write timeout for long generations.
- I did not verify LM Studio's native `/api/v1/chat` response fields for token usage. The OpenAI-compatible path returns `usage` per its OpenAI-compatibility claim, but I did not confirm this field by field.

## Q3. Structured outputs: exact semantics, versions, OpenAI-compatible support, reliability with long code strings

### Takeaway
On Ollama, `"format": "json"` only forces some well-formed JSON object, while `"format": {<JSON Schema>}` (v0.5.0+, Dec 2024) constrains decoding to the schema. Since v0.30.0 the schema is compiled into a GBNF grammar by llama-server's own converter. Both forms also work through `/v1/chat/completions` (`response_format: {"type":"json_schema","json_schema":{"schema":...}}`). The grammar's string rule forbids raw control characters, so newlines, quotes and backslashes inside code strings must be escaped, and a completed response is always parseable. What remains is output truncated at `num_predict` or context (check `done_reason`), whitespace run-on (seen with `format:"json"`'s unbounded `ws` and in an MLX-engine bug), and silently ignored schema keywords.

### Cited Findings
**Ollama `format` semantics and history**
- `"format": "json"` enables JSON mode: "When `format` is set to `json`, the output will always be a well-formed JSON object. It's important to also instruct the model to respond in JSON." — [docs/api.md](https://github.com/ollama/ollama/blob/main/docs/api.md)
- Passing a JSON Schema object enables structured outputs: "The model will generate a response that matches the schema." — [docs/api.md](https://github.com/ollama/ollama/blob/main/docs/api.md)
- Example from the docs: `curl -X POST http://localhost:11434/api/chat -d '{"model":"gpt-oss","messages":[{"role":"user","content":"Tell me about Canada."}],"stream":false,"format":{"type":"object","properties":{"name":{"type":"string"},"capital":{"type":"string"},"languages":{"type":"array","items":{"type":"string"}}},"required":["name","capital","languages"]}}'`. Tips: "It is ideal to also pass the JSON schema as a string in the prompt to ground the model's response". Lower the temperature (for example to `0`). "Structured outputs work through the OpenAI-compatible API via `response_format`". "Ollama's Cloud currently does not support structured outputs." — [docs/capabilities/structured-outputs.mdx](https://github.com/ollama/ollama/blob/main/docs/capabilities/structured-outputs.mdx)
- Schema support shipped in v0.5.0 (tagged 2024-12-04): "api: structured outputs - chat endpoint (#7900)" and "api: add generate endpoint for structured outputs (#7939)". — [commit 630e7dc6](https://github.com/ollama/ollama/commit/630e7dc6); [PR #7900](https://github.com/ollama/ollama/pull/7900)
- Implementation since v0.30.0: "a JSON schema is passed to llama-server via its json_schema field and the "json" format as a builtin grammar via the grammar field. A format that applies after a response's thinking is sent as a grammar built around the GBNF llama-server itself derives from the schema." Derived grammars are cached per schema (64 entries). — [llm/llama_server.go](https://github.com/ollama/ollama/blob/main/llm/llama_server.go)
- MLX runner: structured output support was added 2026-08-14 (commit 147509c0) and compiled as xgrammar structural tags from 2026-09-03 (commit b68365a0). — [Ollama git history](https://github.com/ollama/ollama/commits/main)

**Escaping and whitespace in the grammar (relevant to Python-file string values)**
- Ollama's builtin `"json"` grammar has this string rule: `string ::= "\"" ( [^"\\\x7F\x00-\x1F] | "\\" (["\\/bfnrt] | "u" [0-9a-fA-F]{4}) )* "\""`. Whitespace is `ws ::= ([ \t\n] ws)?`, which is unbounded. — [llm/llama_server.go (grammarJSON)](https://github.com/ollama/ollama/blob/main/llm/llama_server.go)
- llama.cpp's JSON-schema-to-grammar converter uses the same `char` rule (`[^"\\\x7F\x00-\x1F] | [\\] (["\\bfnrt] | "u" [0-9a-fA-F]{4})`) but a bounded space rule: `SPACE_RULE = | " " | "\n"{1,2} [ \t]{0,20}`. — [common/json-schema-to-grammar.cpp](https://github.com/ggml-org/llama.cpp/blob/master/common/json-schema-to-grammar.cpp)
- llama.cpp schema caveats: "`additionalProperties` defaults to `false` (produces faster grammars + reduces hallucinations)". "`"additionalProperties": true` may produce keys that contain unescaped newlines." "Unsupported features are skipped silently." `pattern`s must start with `^` and end with `$`. Remote `$ref`s are not supported in C++. String formats lack `uri` and `email`. There is no `patternProperties`. "Grammars currently have performance gotchas" (issue #4218), and `x? x? x?...` repetition may be "extremely slow". — [grammars/README.md](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)
- MLX-engine bug: with a JSON schema the output "never terminates — model emits whitespace until num_predict is reached". Opened 2026-09-21 on v0.34.2 (gemma4:e2b-mlx). The identical request works on the GGUF/llama.cpp engine. The report is closed, and PR #18569 caps grammar whitespace at 32. — [issue #18567](https://github.com/ollama/ollama/issues/18567); [PR #18569](https://github.com/ollama/ollama/pull/18569)
- Older JSON-mode whitespace reports: "JSON mode should disallow trailing whitespace" (#2577) and "JSON Mode + Streaming + OpenAI API + Llama3 = never sends STOP, and a lot of whitespace after the JSON" (#4446). Only titles were checked, not status. — [issue #2577](https://github.com/ollama/ollama/issues/2577); [issue #4446](https://github.com/ollama/ollama/issues/4446)

**llama-server structured output**
- `/completion` and other completion endpoints take a `json_schema` body field (for example `{}` for any JSON) and a raw `grammar` (GBNF) field. — [tools/server/README.md](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- `/v1/chat/completions` takes `response_format` as `{"type": "json_object"}`, `{"type": "json_object", "schema": {...}}` or `{"type": "json_schema", "schema": {...}}` (server README). The grammars README also lists `{ type: "json_schema", json_schema: {"schema": ...} }`. — [tools/server/README.md](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md); [grammars/README.md](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)
- With a `json_schema` present, the chat autoparser builds a grammar of `reasoning + space() + content(schema(json(), "response-format", ...)) + end()`. The generator source also accepts an optional ```` ```json ```` fence around the schema content. — [docs/autoparser.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/autoparser.md); [common/chat-auto-parser-generator.cpp](https://github.com/ggml-org/llama.cpp/blob/master/common/chat-auto-parser-generator.cpp)

**LM Studio**
- `/v1/chat/completions` takes `response_format: {"type":"json_schema","json_schema":{"name":"joke_response","strict":"true","schema":{...}}}`. The JSON arrives as a string in `choices[0].message.content`. GGUF models use llama.cpp grammar-based sampling and MLX models use Outlines. Caveat: "Not all models are capable of structured output, particularly LLMs below 7B parameters." — [LM Studio structured output docs](https://github.com/lmstudio-ai/docs/blob/main/1_developer/3_openai-compat/structured-output.md)

**vLLM**
- `response_format` with `json_schema`, or `extra_body={"structured_outputs": {"json": ...}}`. The old `guided_json`, `guided_regex`, `guided_choice`, `guided_grammar` and `guided_decoding_backend` fields were "removed in v0.12.0". Backends are xgrammar, guidance, outlines and lm-format-enforcer, selected with `--structured-outputs-config.backend`, default `auto`. — [vLLM docs/features/structured_outputs.md](https://github.com/vllm-project/vllm/blob/main/docs/features/structured_outputs.md)

**mlx-lm**
- SERVER.md documents no `response_format` or JSON-schema option. — [mlx-lm SERVER.md](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md)

### Inferences
- Under grammar-constrained decoding the model cannot emit a raw newline or unescaped `"` inside a JSON string (the `char` rule excludes `\x00-\x1F` and bare `"`), so each newline in a Python file must be written as the two characters `\n`. Once the closing brace is emitted the output is syntactically valid JSON and `json.loads` restores the exact file text. The failure modes that remain are (a) running out of tokens mid-string, with `done_reason` `"length"`, which leaves unparseable JSON, and (b) quality loss or unwanted `\t`/`\u` choices from the escaping burden. The escaping burden is my inference; I found no benchmark.
- Prefer a full JSON Schema over `"format": "json"`. The schema grammar has bounded whitespace (at most 2 newlines plus 20 tabs or spaces), while the builtin `json` grammar's `ws` is unbounded, which is the pattern behind historical "endless whitespace" reports. The schema also pins keys and required fields.
- Make the schema simple and grammar-friendly: `"type":"object"`, explicit `properties`, `required`, and `additionalProperties: false`. Avoid `pattern`, `format:"uri"`, `patternProperties` and remote `$ref`, since unsupported keywords are skipped silently. Avoid `maxLength` on code strings, because it would truncate files.
- Stick to GGUF models on Ollama (not `-mlx` tags) for strict JSON in September 2026. The MLX engine had two JSON bugs in the same month (#18441 and #18567).
- Keep validating in Python anyway: `json.loads`, key and type checks, then `compile(src, path, "exec")` to syntax-check any returned Python file, with one retry on failure.

### Gaps
- I found no quantitative study of constrained-decoding reliability for long code strings (for example files over 500 lines) in any of these runtimes.
- I did not test whether Ollama's `/v1` path honours `strict`. The code ignores it and the schema is always enforced when present.

## Q4. Context window: Ollama default num_ctx (history), how to set it, and silent truncation; llama-server and LM Studio equivalents

### Takeaway
Ollama's default context is set by total VRAM, not by the model, as of v0.15.5 (Feb 2026): 4096 tokens under about 24 GiB of VRAM, 32768 for 24–48 GiB, and 262144 at 48 GiB or more. Most laptops therefore still get 4096. On the default settings, Ollama silently drops old chat messages, and for an overlong single prompt it keeps only the first `num_keep` (4) tokens and drops the middle, logging only a warning. The app should always send `options.num_ctx` explicitly, sized to prompt plus expected output. llama-server behaves differently: when a request exceeds the context it returns an error (`exceed_context_size_error`) rather than truncating.

### Cited Findings
**Ollama default and history**
- Current docs: "Ollama defaults to the following context lengths based on VRAM: < 24 GiB VRAM: 4k context; 24-48 GiB VRAM: 32k context; >= 48 GiB VRAM: 256k context." "Tasks which require large context like web search, agents, and coding tools should be set to at least 64000 tokens." — [docs/context-length.mdx](https://github.com/ollama/ollama/blob/main/docs/context-length.mdx)
- Code: `totalVRAM >= 47 GiB → 262144; >= 23 GiB → 32768; default 4096`, logged as `"vram-based default context"`. — [server/routes.go](https://github.com/ollama/ollama/blob/main/server/routes.go)
- The env var help text reads `OLLAMA_CONTEXT_LENGTH`: "Context length to use unless otherwise specified (default: 4k/32k/256k based on VRAM)". — [envconfig/config.go](https://github.com/ollama/ollama/blob/main/envconfig/config.go)
- The FAQ is stale and contradicts the above: "By default, Ollama uses a context window size of 4096 tokens." — [docs/faq.mdx](https://github.com/ollama/ollama/blob/main/docs/faq.mdx); contradicted by [docs/context-length.mdx](https://github.com/ollama/ollama/blob/main/docs/context-length.mdx) and the code.
- Version history, from commits mapped to tags:
  - v0.5.13 (2025-03-03) made the context length settable with `OLLAMA_CONTEXT_LENGTH` ("config: allow setting context length through env var (#8938)"). — [commit 314573bf](https://github.com/ollama/ollama/commit/314573bf)
  - v0.6.7 (2025-04-30) raised the default to 4096 ("config: update default context length to 4096", 2025-04-28, after a revert and re-land of #10364). The previous default was 2048; the commit title confirms the change to 4096, and the 2048 figure comes from prior knowledge. — [commit 44b466ee](https://github.com/ollama/ollama/commit/44b466ee)
  - v0.15.5 (2026-02-05) introduced "server: use tiered VRAM-based default context length" (commit dated 2026-01-27). — [commit 0334ffa6](https://github.com/ollama/ollama/commit/0334ffa6)
- The effective context is also capped at the model's trained context length. When `num_ctx` was not set by the user ("numCtxAuto"), Ollama may lower it on a load out-of-memory (32768 → 4096) (`reduceAutoNumCtxForLoadOOM`, `nextLowerAutoNumCtx`). — [server/sched.go](https://github.com/ollama/ollama/blob/main/server/sched.go)
- There are three ways to set it. Per request: `"options": {"num_ctx": 4096}`. Globally: `OLLAMA_CONTEXT_LENGTH=8192 ollama serve`. Interactively: `/set parameter num_ctx 4096`. Per model: a Modelfile with `PARAMETER num_ctx <n>` plus `ollama create`, which is the only way that works through `/v1`. The app also has a context slider in settings, and `ollama ps` shows the allocated CONTEXT. — [docs/faq.mdx](https://github.com/ollama/ollama/blob/main/docs/faq.mdx); [docs/context-length.mdx](https://github.com/ollama/ollama/blob/main/docs/context-length.mdx); [docs/api/openai-compatibility.mdx](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx)
- Memory: "Required RAM will scale by `OLLAMA_NUM_PARALLEL` * `OLLAMA_CONTEXT_LENGTH`". llama-server is launched with `-c NumCtx*numParallel`. — [docs/faq.mdx](https://github.com/ollama/ollama/blob/main/docs/faq.mdx); [llm/llama_server.go](https://github.com/ollama/ollama/blob/main/llm/llama_server.go)

**Ollama overflow behaviour (silent truncation)**
- For chat history, `chatPrompt` "truncates any messages that exceed the context window of the model, making sure to always include 1) the latest message and 2) system messages". It drops messages from the front and only emits a Debug log: "truncating input messages which exceed context length". `truncate` defaults to true when omitted (`req.Truncate == nil || *req.Truncate`). — [server/prompt.go](https://github.com/ollama/ollama/blob/main/server/prompt.go); [server/routes.go](https://github.com/ollama/ollama/blob/main/server/routes.go)
- For a single prompt longer than `num_ctx`, when truncation is on the runner either returns HTTP 400 "the prompt is longer than the context length currently available to the model; shorten the prompt, adjust the context length in settings, or use a model with a longer context length" (context shift disabled), or, with context shift enabled, keeps the first `num_keep` tokens (+BOS), discards the middle, and logs `slog.Warn("truncating input prompt", ...)`. — [llm/llama_server.go `completionPromptForRequest`](https://github.com/ollama/ollama/blob/main/llm/llama_server.go)
- Context shift is on by default: `resolveContextShift` returns the request's `shift` if set, otherwise `supportsContextShift(model)`, which is true for all but deepseek2-family models. The `num_keep` default is 4. — [server/sched.go](https://github.com/ollama/ollama/blob/main/server/sched.go); [api/types.go DefaultOptions](https://github.com/ollama/ollama/blob/main/api/types.go)
- Related changes in v0.30.9 (2026-06-16): "server: context shift for context windows larger than 8k, add error when hitting context limit (#16712)" and "llm: context shift allow shiftable prompts (#16764)". — [commit bbb40a0a](https://github.com/ollama/ollama/commit/bbb40a0a); [commit 0f047fee](https://github.com/ollama/ollama/commit/0f047fee)

**llama-server**
- `-c, --ctx-size N`: "size of the prompt context (default: 0, 0 = loaded from model)" (env `LLAMA_ARG_CTX_SIZE`). `--context-shift` defaults to disabled. `-np, --parallel` defaults to -1 (auto). `--kv-unified-per-slot N` sets a per-slot limit. — [tools/server/README.md](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- `--fit [on|off]` is on by default ("adjust unset arguments to fit in device memory"). `--fit-ctx` sets the minimum context it may choose, default 4096. — [common/arg.cpp](https://github.com/ggml-org/llama.cpp/blob/master/common/arg.cpp); [common/common.h](https://github.com/ggml-org/llama.cpp/blob/master/common/common.h)
- Overflow: "request (%d tokens) exceeds the available context size (%d tokens), try increasing it" (or "input ... is larger than the max context size ... skipping"), with error type `exceed_context_size_error`. — [tools/server/server-context.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/server-context.cpp); [server-common.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/server-common.cpp)

**LM Studio**
- Context is set at load time: `POST /api/v1/models/load` with `"context_length": 16384`, or `lms load --context-length`. `lms load --estimate-only <model>` (0.3.27, 2025-09-24) prints estimated memory and honours `--context-length`. — [LM Studio load docs](https://github.com/lmstudio-ai/docs/blob/main/1_developer/2_rest/load.md); [API changelog](https://github.com/lmstudio-ai/docs/blob/main/1_developer/api-changelog.md)

### Inferences
- On a typical 16–32 GB laptop (integrated or under-24 GB GPU), Ollama's default is 4096 tokens. That is far too small for prompts that embed whole Python files plus a JSON answer, and the default overflow behaviour silently discards the start of the prompt, including the instructions and schema text. The app must always send `options.num_ctx`, for example 16384 or 32768 depending on RAM, and should compare the returned `prompt_eval_count` with its own estimate.
- To turn silent truncation into an error, send `"truncate": false` and/or `"shift": false` in the Ollama request. Per the code, `shift:false` disables context shift, so an overlong prompt returns HTTP 400 instead of being middle-truncated. This is inferred from reading the code and should be tested against v0.34.4.
- On Apple Silicon, the "VRAM" in the tier logic is the GPU-visible share of unified memory. A 32 GB Mac may land in the 4k or 32k tier depending on what Metal reports (unverified; see Gaps).
- On llama-server, `-c 0` means the model's full trained context. For 128k–256k models this can be large, although `--fit` shrinks it to fit memory (minimum 4096). Always pass an explicit `-c`.

### Gaps
- I did not find how Ollama computes "VRAM" on Apple Silicon unified memory, so I cannot say which tier a 16/32/64 GB Mac gets.
- I could not locate LM Studio's default context length when a model is JIT-loaded through the API, or what LM Studio does when a prompt exceeds it.
- I did not re-verify the exact `contextShiftPromptLimit` formula (how many tokens Ollama keeps after truncation).

## Q5. Thinking/reasoning models: `think` parameter, output fields, Qwen3 switches, and interaction with `format`

### Takeaway
Ollama's `think` field takes `true`/`false`/`null` or a model-defined level string (gpt-oss: `"low"|"medium"|"high"`, default `"medium"`). The reasoning comes back in `message.thinking`, separate from `message.content`. Combining thinking with `format` was buggy from 2025 through mid-September 2026 (gpt-oss via the OpenAI SDK, gemma4 and qwen3.5 with `think:false`, `/api/generate` ignoring think, an MLX stray "."). v0.34.4 (2026-09-23) reworked it so one generation leaves the thinking unconstrained and constrains only the content after the end-of-thinking marker. For strict JSON the safest choices are a non-thinking model or `think:false` on v0.31.2 or later, preferably v0.34.4 or later.

### Cited Findings
**Ollama `think` semantics**
- `think`: "`true`: request thinking output. `false`: request no thinking output, if the model permits it. `null`: use the model default. A string: select a supported level from `thinking.values`." `/api/show` returns `"thinking": {"values": ["low","medium","high"], "default": "medium"}` for gpt-oss. `values: [false]` means no thinking support. Unsupported names fall back to the model default. — [docs/capabilities/thinking.mdx](https://github.com/ollama/ollama/blob/main/docs/capabilities/thinking.mdx)
- API docs list the levels `"low"`, `"medium"`, `"high"` and `"max"`. "max" was accepted from v0.22.0 (commit c2ebb4d5, 2026-04-24), and the thinking-level constraint was loosened in v0.17.7 (#14625). — [docs/api.md](https://github.com/ollama/ollama/blob/main/docs/api.md); [commit c2ebb4d5](https://github.com/ollama/ollama/commit/c2ebb4d5); [commit 122c68c1](https://github.com/ollama/ollama/commit/122c68c1)
- The `think` field was introduced in v0.9.0 (2025-05-28, "add thinking support to the api and cli (#10584)"). — [commit 5f57b0ef](https://github.com/ollama/ollama/commit/5f57b0ef)
- OpenAI-compatible equivalents are `reasoning_effort` and `reasoning.effort`, with `"none"` requesting no thinking. For GPT-OSS, `"minimal"` maps to `"low"` and `"xhigh"`/`"ultra"` map to `"high"`. — [docs/api/openai-compatibility.mdx](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx)

**Qwen3 switches**
- "`enable_thinking=False`: Passing `enable_thinking=False` to `tokenizer.apply_chat_template` will strictly prevent the model from generating thinking content." "`/think` and `/no_think` instructions: Use those words in the system or user message to signify whether Qwen3 should think. In multi-turn conversations, the latest instruction is followed." "Qwen3-Instruct-2507 supports only non-thinking mode and does not generate `<think></think>` blocks". — [QwenLM/Qwen3 README](https://github.com/QwenLM/Qwen3/blob/main/README.md)

**llama-server reasoning controls**
- Server flags: `--reasoning-format` (`none` leaves thoughts in `message.content`; `deepseek` puts them in `message.reasoning_content`; `deepseek-legacy`; default `auto`), `-rea, --reasoning [on|off|auto]`, `--reasoning-budget N` (-1 unlimited, 0 immediate end), and `--reasoning-effort LEVEL`. Per request: `chat_template_kwargs: {"enable_thinking": false}`, `reasoning_effort: "none"` (disables thinking) and `reasoning_format`. — [tools/server/README.md](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)

**LM Studio**
- gpt-oss reasoning is returned in `choices.message.reasoning` (non-streaming) and `choices.delta.reasoning` (streaming) from 0.3.23 (2025-08-12). DeepSeek R1 uses `reasoning_content` (0.3.9). `/v1/responses` supports `reasoning.effort` for gpt-oss-20b (0.3.29, 2025-10-06). — [LM Studio API changelog](https://github.com/lmstudio-ai/docs/blob/main/1_developer/api-changelog.md)

**vLLM**
- Structured outputs work with reasoning when the server runs with `--reasoning-parser` (for example `deepseek_r1`), returning `message.reasoning` and `message.content`. Caveat: "When using Qwen3 Coder models with reasoning enabled, structured outputs might become disabled if the reasoning content does not get parsed into the `reasoning` field separately (v0.11.2+)." — [vLLM structured_outputs.md](https://github.com/vllm-project/vllm/blob/main/docs/features/structured_outputs.md)

**Ollama think + format bugs and fixes (chronological)**
- #11691, "Structured output with OpenAI SDK and gpt-oss:20b not working": opened 2025-08-05 on Ollama 0.11.0, invalid JSON ("expected value at line 1 column 1"), closed and linked to PR #14288. — [issue #11691](https://github.com/ollama/ollama/issues/11691); [PR #14288](https://github.com/ollama/ollama/pull/14288)
- v0.12.4: "routes: structured outputs for gpt-oss (#12460)" (2025-10-08). — [commit 77060d46](https://github.com/ollama/ollama/commit/77060d46)
- #14440, "Structured outputs not enforced for gpt-oss:20b when streaming + thinking" (title from search; status not checked). — [issue #14440](https://github.com/ollama/ollama/issues/14440)
- #15260, "`think=false` breaks `format` (structured output) for `gemma4` — format constraint silently ignored": opened 2026-04-03 on v0.20.0. Root cause: format masking was deferred until an end-of-thinking token that never arrives when `think=false`. Mirrors the qwen3.5 bug #14645. Closed via PRs #15678 and #15392. The fix "server: apply format when think=false for gemma4" shipped in v0.21.1. — [issue #15260](https://github.com/ollama/ollama/issues/15260); [commit 5d102160](https://github.com/ollama/ollama/commit/5d102160)
- #15386, "Gemma4:31b Structured Output inconsistent with Reasoning / Thinking" (title only). — [issue #15386](https://github.com/ollama/ollama/issues/15386)
- v0.31.2 (2026-07-07): "server: apply format constraint for all thinking parsers when think=false (#15901)". — [commit 892e7f6b](https://github.com/ollama/ollama/commit/892e7f6b)
- #17544, "`/api/generate` silently ignores think when format is set; `/api/chat` does not": opened 2026-08-03 on v0.32.5 (qwen3:0.6b). The generate path applied the grammar from the first token, so thinking came back empty. Closed via #18479 and #17705. — [issue #17544](https://github.com/ollama/ollama/issues/17544)
- #18441, "MLX: structured output with thinking enabled prefixes JSON content with a stray '.'": opened 2026-09-14 on v0.34.0 (qwen3.8:27b-mlx). It failed 7–8 out of 10 times with thinking on and never with `think:false`, on both `/api/chat` and `/v1/chat/completions`. Closed by PR #18479. — [issue #18441](https://github.com/ollama/ollama/issues/18441); [PR #18479](https://github.com/ollama/ollama/pull/18479)
- v0.34.4 (tagged 2026-09-23) contains the fixes. Commit 5a0ff311 ("server: apply structured outputs in a single pass on thinking models", Fixes #18441 and #17544) explains that before this change "A format on a thinking model ran two generations: an unconstrained one, cancelled once the parser reported content, then a re-rendered prompt with the parsed thinking under the grammar... needed a harmony prompt hack... on MLX could leak a stray first token into the JSON. The generate endpoint never deferred at all." After it: one request "names the strings ending the response's thinking... and the runner constrains only the content after them in a single generation". "A raw generate prompt names no strings... and its format applies from the first token as before." A format now applies to whatever follows the thinking, with harmony (gpt-oss) as an exception for tool calls. Companion commit 2ff052b7 builds a GBNF (`thinkingGrammar`) that "leaves the text before a closing string unconstrained and requires the format after it", and says "A response that ends before a closing string is delivered unchanged." — [commit 5a0ff311](https://github.com/ollama/ollama/commit/5a0ff311); [commit 2ff052b7](https://github.com/ollama/ollama/commit/2ff052b7); [llm/gbnf.go](https://github.com/ollama/ollama/blob/main/llm/gbnf.go)

### Inferences
- The think+format path was rewritten only three days before this snapshot, so it is new code. For a strict-JSON app the lowest-risk setup is a non-thinking or instruct model, or an explicit `"think": false`, on Ollama v0.34.4 or later (at least v0.31.2), on GGUF rather than MLX.
- If thinking is used (for better code), watch for the case where the model hits `num_predict` before the end-of-thinking marker. The response then carries no content at all ("delivered unchanged"). Size `num_predict` generously, check `message.content` is non-empty, and retry with `think:false`.
- gpt-oss cannot fully disable thinking on the native API (its values are only `low`/`medium`/`high`), so `"think":"low"` is its minimum. On `/v1`, `reasoning_effort:"none"` "requests no thinking output" for GPT-OSS.
- Setting a minimum Ollama version (for example ≥ 0.34.4) and checking `GET /api/version` at startup is worthwhile.

### Gaps
- I did not find whether the new single-pass path covers `/v1/chat/completions` with `response_format` in every case. Commit 5a0ff311 says "Both handlers", meaning chat and generate, and #18441 mentions the `/v1` path.
- I did not check the current status of #14440 and #15386.
- I found no independent reports yet on v0.34.4's behaviour in the field, since it is three days old.

## Q6. Other gotchas: defaults, keep_alive, concurrency, flash attention, KV cache, Windows

### Takeaway
Ollama's built-in default sampling is `temperature 0.8`, `top_k 40`, `top_p 0.9`, `num_predict -1`, `num_keep 4`. Models unload after 5 minutes idle (`keep_alive`). One request per model runs at a time (`OLLAMA_NUM_PARALLEL=1`) with a queue of 512. Flash attention is automatic where supported, and the KV cache is f16 unless `OLLAMA_KV_CACHE_TYPE` is set to `q8_0` or `q4_0` (global, requires flash attention). Environment variables are set per OS (launchctl, a systemd override, or Windows user environment variables), and Ollama must be restarted to pick them up.

### Cited Findings
- `DefaultOptions` in the code: `NumPredict: -1`, `NumKeep: 4`, `Temperature: 0.8`, `TopK: 40`, `TopP: 0.9`, `RepeatPenalty: 1.0`, `NumCtx: envconfig.ContextLength()` (0 means auto). Model Modelfile `PARAMETER`s override these. — [api/types.go](https://github.com/ollama/ollama/blob/main/api/types.go)
- keep_alive: "By default models are kept in memory for 5 minutes before being unloaded". The per-request `keep_alive` takes a duration string ("10m"), a number of seconds, any negative value (keep loaded forever), or `0` (unload immediately). `OLLAMA_KEEP_ALIVE` sets the global default, and the request value overrides it. `ollama stop <model>` unloads. — [docs/faq.mdx](https://github.com/ollama/ollama/blob/main/docs/faq.mdx); [envconfig/config.go](https://github.com/ollama/ollama/blob/main/envconfig/config.go)
- `OLLAMA_LOAD_TIMEOUT`: "How long to allow model loads to stall before giving up (default "5m")". — [envconfig/config.go](https://github.com/ollama/ollama/blob/main/envconfig/config.go)
- Concurrency: `OLLAMA_NUM_PARALLEL` defaults to 1. `OLLAMA_MAX_LOADED_MODELS` defaults to 3 × the number of GPUs, or 3 for CPU. `OLLAMA_MAX_QUEUE` defaults to 512, and beyond it the server "will respond with a 503 error". "Parallel request processing for a given model results in increasing the context size by the number of parallel requests." — [docs/faq.mdx](https://github.com/ollama/ollama/blob/main/docs/faq.mdx); [envconfig/config.go](https://github.com/ollama/ollama/blob/main/envconfig/config.go)
- Flash attention: "Ollama uses Flash Attention automatically when the selected backend and devices support it. To force Flash Attention on, set `OLLAMA_FLASH_ATTENTION=1`... To disable it, set `OLLAMA_FLASH_ATTENTION=0`." The llama-server runner auto-detects `--flash-attn`. — [docs/faq.mdx](https://github.com/ollama/ollama/blob/main/docs/faq.mdx); [llm/llama_server.go](https://github.com/ollama/ollama/blob/main/llm/llama_server.go)
- KV cache: `OLLAMA_KV_CACHE_TYPE` defaults to `f16`. `q8_0` uses about half the memory "with a very small loss in precision" and is recommended if not using f16. `q4_0` uses about a quarter "with a small-medium loss in precision that may be more noticeable at higher context sizes". It is a global option, applies "when Flash Attention is enabled", and models with high GQA counts (for example Qwen2) may be more affected. — [docs/faq.mdx](https://github.com/ollama/ollama/blob/main/docs/faq.mdx)
- llama-server equivalents: `-fa, --flash-attn [on|off|auto]` (default auto), `-ctk/-ctv` (`--cache-type-k/v`, default f16; allowed f32, f16, bf16, q8_0, q4_0, q4_1, iq4_nl, q5_0, q5_1), and `--jinja` (default enabled). — [tools/server/README.md](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- Setting env vars per OS: on Mac, `launchctl setenv OLLAMA_HOST "0.0.0.0:11434"` then restart the app. On Linux, `systemctl edit ollama.service` with `Environment="..."`. On Windows, quit Ollama from the taskbar, add user environment variables in Settings or Control Panel (for example `OLLAMA_HOST`, `OLLAMA_MODELS`), then restart. — [docs/faq.mdx](https://github.com/ollama/ollama/blob/main/docs/faq.mdx)
- Windows specifics: "Windows with Radeon GPUs currently default to 1 model maximum due to limitations in ROCm v5.7" (FAQ note). Unicode progress characters may render as squares in older Windows 10 terminal fonts. To stop autostart, disable Ollama under Task Manager → Startup apps. — [docs/faq.mdx](https://github.com/ollama/ollama/blob/main/docs/faq.mdx); [docs/windows.mdx](https://github.com/ollama/ollama/blob/main/docs/windows.mdx)
- Ollama allows CORS from 127.0.0.1 and 0.0.0.0 by default (`OLLAMA_ORIGINS` adds more). This does not affect a urllib client. — [docs/faq.mdx](https://github.com/ollama/ollama/blob/main/docs/faq.mdx)

### Inferences
- Always send `temperature: 0` (or a low value) and an explicit `num_predict` cap for JSON tasks, because the default 0.8 with an unlimited `num_predict` works against determinism and bounded latency.
- Send `keep_alive` (for example `"30m"`) on each call so the model does not reload between steps of a multi-call workflow. The first call after an idle unload pays the load time, which can be tens of seconds on laptops. Budget the client timeout for it or preload with an empty request.
- Leave `OLLAMA_NUM_PARALLEL=1` on laptops and serialize calls in the app. Parallel slots multiply the KV memory for the context.
- Suggesting `OLLAMA_KV_CACHE_TYPE=q8_0` is a reasonable memory saver for users who need 32k context on 16 GB machines, but it needs a server restart and is global, so it should be optional advice rather than a requirement.

### Gaps
- I did not verify whether the ROCm v5.7 note in the FAQ is stale given the Windows docs now reference ROCm v7. The two docs are inconsistent.

## Q7. Recommendation and exact call recipe for a stdlib-only Python client

### Takeaway
Recommend Ollama ≥ v0.34.4 (at least v0.31.2), called with native `POST http://127.0.0.1:11434/api/chat` and `"stream": false` (or streaming with a total deadline). Send a full JSON Schema in `format`, `"think": false`, and explicit `options.num_ctx`, `num_predict` and `temperature: 0`. Also send `keep_alive`, and optionally `"shift": false` so overflow raises an error instead of truncating silently. Parse `message.content` with `json.loads`, check `done_reason == "stop"`, and record `prompt_eval_count` and `eval_count`. Keep an OpenAI-compatible fallback path (`/v1/chat/completions` with `response_format.json_schema`) so LM Studio (port 1234) and llama-server (port 8080) users can point the app at their server. On those, context is set at server or model load rather than per request.

### Cited Findings
- Native Ollama supports every needed parameter per request (`format` schema, `think`, `options.num_ctx`, `keep_alive`, `truncate`, `shift`), whereas `/v1` cannot set `num_ctx`. — [docs/api.md](https://github.com/ollama/ollama/blob/main/docs/api.md); [docs/api/openai-compatibility.mdx](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx); [api/types.go](https://github.com/ollama/ollama/blob/main/api/types.go)
- The schema request shape comes from the Ollama docs (see Q3), and LM Studio's `response_format` shape comes from the LM Studio docs (see Q3). — [structured-outputs.mdx](https://github.com/ollama/ollama/blob/main/docs/capabilities/structured-outputs.mdx); [LM Studio structured output](https://github.com/lmstudio-ai/docs/blob/main/1_developer/3_openai-compat/structured-output.md)
- llama-server's per-request thinking switch is `chat_template_kwargs: {"enable_thinking": false}` or `reasoning_effort: "none"`, and its `response_format` accepts a JSON schema. — [tools/server/README.md](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)

Example request for Ollama, the primary path. Field names are verified against the docs and code above. The model name and sizes are illustrative.
```json
POST http://127.0.0.1:11434/api/chat
{
  "model": "qwen3:8b",
  "messages": [
    {"role": "system", "content": "Reply with ONE JSON object matching this schema: {...schema text...}"},
    {"role": "user", "content": "..."}
  ],
  "stream": false,
  "think": false,
  "format": {
    "type": "object",
    "properties": {
      "summary": {"type": "string"},
      "files": {"type": "array", "items": {
        "type": "object",
        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"], "additionalProperties": false}}
    },
    "required": ["summary", "files"],
    "additionalProperties": false
  },
  "keep_alive": "30m",
  "shift": false,
  "options": {"num_ctx": 32768, "num_predict": 8192, "temperature": 0}
}
```
The response fields to read are `message.content` (a JSON string), `message.thinking` (if any), `done`, `done_reason` (`"stop"` or `"length"`), `prompt_eval_count`, `eval_count` and `total_duration` (in nanoseconds).

Example request for OpenAI-compatible servers (Ollama, LM Studio, llama-server):
```json
POST http://127.0.0.1:{11434|1234|8080}/v1/chat/completions
{
  "model": "<model id>",
  "messages": [...],
  "stream": false,
  "temperature": 0,
  "max_tokens": 8192,
  "response_format": {"type": "json_schema",
                      "json_schema": {"name": "result", "strict": true, "schema": { ...same schema... }}},
  "reasoning_effort": "none"
}
```
Read `choices[0].message.content`, `choices[0].finish_reason`, and `usage.prompt_tokens` / `usage.completion_tokens`. LM Studio's docs example shows `"strict": "true"` as a string, and Ollama ignores `strict`. For llama-server, `chat_template_kwargs: {"enable_thinking": false}` is the documented per-request switch for Qwen-style templates.

### Inferences
- Ollama wins on install ease, license, cross-OS service behaviour, and per-request control of context, thinking, schema and keep-alive, all over plain JSON HTTP that urllib handles easily. Since v0.30.0 it runs upstream llama-server underneath, so its grammar engine matches llama.cpp's.
- Client hardening checklist, inferred from the findings above:
  1. At startup, `GET /api/version` (enforce ≥ 0.34.4, or at least ≥ 0.31.2) and `GET /api/tags` / `POST /api/show` to confirm the model exists and read its `thinking` capabilities.
  2. Size `num_ctx` from an estimate of prompt plus output tokens, and never rely on the default (4096 on under-24 GB-VRAM machines).
  3. Treat `done_reason == "length"`, an empty `content`, or a `json.loads` failure as retryable: retry once with a larger `num_predict`/`num_ctx` or `think:false`.
  4. After parsing, validate keys and types manually (standard library only) and run `compile()` on any Python source strings.
  5. Use a long urllib timeout (600 s or more) for non-streaming calls, or stream with a total deadline.
  6. Avoid `-mlx` model tags for strict JSON until the September 2026 MLX grammar fixes have settled.

### Gaps
- Which specific open models behave best under these constraints is covered by the sibling notes file, not here.
- None of this was run on real laptops in this session; the Ollama `shift:false` / `truncate:false` error behaviour in particular should be tested before relying on it.
