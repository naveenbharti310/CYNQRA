"""One way for every spike to reach a model, and one way to count tokens.

Order of resolution:
  1. CYNQRA_S1_MODEL_CMD    a shell command, prompt on stdin, text on stdout
  2. CYNQRA_OLLAMA_MODEL    an open model served by Ollama on this machine
  3. CYNQRA_LOCAL_BASE_URL  any OpenAI compatible local server (LM Studio,
                            llama.cpp llama-server), model in CYNQRA_MODEL
  4. OPENAI_API_KEY
  5. ANTHROPIC_API_KEY
  6. nothing, and the spikes refuse to score

Token counts from an API are real. Token counts from a shell command are
estimated from characters and marked estimated. An estimated count may not
be reported as a measured S2 result.

Change log
26 Sep 2026, acting CTO. The Anthropic default was claude-sonnet-4-20250514,
which Anthropic retired on 15 June 2026. Every call with an Anthropic key and
no CYNQRA_MODEL would have failed. Default is now claude-sonnet-5. A shell
command that exits non zero is now an error, not a reply. Any error is
reported in the "error" field and callers must treat it as an unrun call.

26 Sep 2026, second pass, before the first real call. Checked against the
current Messages API reference:
  * claude-sonnet-5 rejects temperature with HTTP 400 (sampling parameters
    were removed on the 5 family and Opus 4.7 onward). Every Anthropic call
    would have failed. temperature is no longer sent to Anthropic.
  * Sonnet 5 thinks by default and thinking tokens count against max_tokens.
    A 1500 token cap could be spent on thinking and truncate the answer.
    Anthropic calls now get at least ANTHROPIC_MIN_MAX_TOKENS of room.
    Billing is by tokens actually used, so this raises no cost by itself.
  * stop_reason was never read. A truncated reply (max_tokens) or a safety
    refusal (refusal) now raises, so it is an unrun call, never a short answer.
  * A transient 429, 5xx or 529 overload used to stop a whole run. Such
    calls are retried twice with backoff; anything else fails at once.
  * CYNQRA_EFFORT (low, medium, high, xhigh, max) optionally sets
    output_config.effort on Anthropic calls. Unset means the model default.

26 Sep 2026, third pass: local open models, so the POC runs on a laptop with
no API key. Ollama is called on its native /api/chat, which reports real
token counts (prompt_eval_count, eval_count) and takes the settings that
matter locally:
  * num_ctx (CYNQRA_NUM_CTX, default 32768). Ollama's own default is far
    smaller and it truncates an overlong prompt silently, so the window is
    always sent, and a prompt that clearly cannot fit is refused up front.
  * format: the caller's JSON Schema when it has one, else "json". A schema
    is enforced as a grammar, so the reply parses and has the right keys;
    plain "json" only promises some object. Code is not sent this way: long
    code inside JSON strings is where local models go wrong, so callers ask
    for code as plain file blocks with no format at all.
  * shift and truncate false: an overlong prompt becomes an HTTP 400 instead
    of Ollama silently cutting out its middle (instructions included).
  * seed (CYNQRA_SEED) and num_predict (CYNQRA_NUM_PREDICT, default the
    larger of the caller's max_tokens and 8192) come from the local config.
  * A retry may pass its own temperature, so a second attempt is not a
    replay of the first.
  * think (CYNQRA_THINK: true, false, low, medium, high); unset leaves the
    model's own default. temperature (CYNQRA_TEMPERATURE); unset leaves the
    model's recommended default from its Ollama template.
  * done_reason "length" means the answer was cut off; that is an error.
  * keep_alive keeps the model loaded between the calls of one run.
Local generation on a CPU is slow, so CYNQRA_TIMEOUT (seconds, default 1800
for local servers) replaces the 600 second limit there.

26 Sep 2026, fourth pass: the desktop app's llama-server, checked against the
real b11201 build. A local OpenAI-compatible call is not retried by this
module: the request is deterministic, so a resend costs minutes for the same
answer, and a timeout after CYNQRA_TIMEOUT must not become three. llama-server
answers an unparseable finished reply with HTTP 500 ("does not match the
expected ... format") and an overlong prompt with HTTP 400
exceed_context_size_error; both now read as what they are.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MIN_MAX_TOKENS = 16000
TIMEOUT_S = 600
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}
RETRY_WAITS_S = (2.0, 6.0)
EFFORTS = {"low", "medium", "high", "xhigh", "max"}


def resolve() -> dict | None:
    cmd = os.environ.get("CYNQRA_S1_MODEL_CMD")
    if cmd:
        return {"kind": "cmd", "label": "shell command", "tokens": "estimated"}
    if os.environ.get("CYNQRA_OLLAMA_MODEL"):
        return {"kind": "ollama", "label": os.environ["CYNQRA_OLLAMA_MODEL"], "tokens": "measured", "local": True}
    if os.environ.get("CYNQRA_LOCAL_BASE_URL"):
        return {"kind": "local", "label": os.environ.get("CYNQRA_MODEL", "local-model"), "tokens": "measured",
                "local": True}
    if os.environ.get("OPENAI_API_KEY"):
        return {
            "kind": "openai",
            "label": os.environ.get("CYNQRA_MODEL", "gpt-4o-mini"),
            "tokens": "measured",
        }
    if os.environ.get("ANTHROPIC_API_KEY"):
        return {
            "kind": "anthropic",
            "label": os.environ.get("CYNQRA_MODEL", "claude-sonnet-5"),
            "tokens": "measured",
        }
    return None


class _Retryable(RuntimeError):
    def __init__(self, msg: str, wait: float | None = None):
        super().__init__(msg)
        self.wait = wait


def _post_once(url: str, body: bytes, headers: dict, timeout: float = TIMEOUT_S) -> dict:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        msg = f"HTTP {exc.code} from provider: {detail}"
        if exc.code in RETRY_STATUS:
            wait = None
            try:
                wait = min(30.0, float(exc.headers.get("retry-after")))
            except (TypeError, ValueError):
                pass
            raise _Retryable(msg, wait) from exc
        raise RuntimeError(msg) from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise _Retryable(f"network error: {exc}") from exc


def _post(url: str, payload: dict, headers: dict, timeout: float = TIMEOUT_S, retry: bool = True) -> dict:
    body = json.dumps(payload).encode("utf-8")
    for wait in (RETRY_WAITS_S if retry else ()) + (None,):
        try:
            return _post_once(url, body, headers, timeout)
        except _Retryable as exc:
            if wait is None:
                raise RuntimeError(str(exc)) from exc
            time.sleep(exc.wait if exc.wait is not None else wait)
    raise RuntimeError("unreachable")


def _openai(prompt: str, model: str, max_tokens: int = 1500) -> dict:
    data = _post(
        OPENAI_URL,
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_completion_tokens": max_tokens,
        },
        {
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
    )
    if data["choices"][0].get("finish_reason") == "length":
        raise RuntimeError(f"reply truncated at max_completion_tokens={max_tokens}")
    usage = data.get("usage") or {}
    return {
        "text": (data["choices"][0]["message"]["content"] or ""),
        "tokens_in": int(usage.get("prompt_tokens") or 0),
        "tokens_out": int(usage.get("completion_tokens") or 0),
        "estimated": False,
    }


def _anthropic(prompt: str, model: str, max_tokens: int = 1500) -> dict:
    payload = {
        "model": model,
        "max_tokens": max(max_tokens, ANTHROPIC_MIN_MAX_TOKENS),
        "messages": [{"role": "user", "content": prompt}],
    }
    effort = (os.environ.get("CYNQRA_EFFORT") or "").strip().lower()
    if effort:
        if effort not in EFFORTS:
            raise ValueError(f"CYNQRA_EFFORT must be one of {sorted(EFFORTS)}, not {effort!r}")
        payload["output_config"] = {"effort": effort}
    data = _post(
        ANTHROPIC_URL,
        payload,
        {
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
    )
    stop = data.get("stop_reason")
    if stop == "refusal":
        details = data.get("stop_details") or {}
        raise RuntimeError(f"model refused (category {details.get('category')}): {details.get('explanation') or ''}")
    if stop == "max_tokens":
        raise RuntimeError(f"reply truncated at max_tokens={payload['max_tokens']}")
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    usage = data.get("usage") or {}
    return {
        "text": "".join(parts),
        "tokens_in": int(usage.get("input_tokens") or 0)
        + int(usage.get("cache_read_input_tokens") or 0)
        + int(usage.get("cache_creation_input_tokens") or 0),
        "tokens_out": int(usage.get("output_tokens") or 0),
        "estimated": False,
    }


def ollama_host() -> str:
    host = (os.environ.get("OLLAMA_HOST") or "127.0.0.1:11434").strip().rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host.replace("://0.0.0.0", "://127.0.0.1")


def _local_timeout() -> float:
    try:
        return float(os.environ.get("CYNQRA_TIMEOUT") or 1800)
    except ValueError:
        return 1800.0


def _ollama(prompt: str, model: str, max_tokens: int, want_json: bool, schema: dict | None = None,
            temperature: float | None = None) -> dict:
    num_ctx = int(os.environ.get("CYNQRA_NUM_CTX") or 32768)
    answer = int(os.environ.get("CYNQRA_NUM_PREDICT") or 0) or max(max_tokens, 8192)
    if len(prompt) // 4 + answer > num_ctx:  # four characters a token is a floor, so this only refuses sure failures
        raise ValueError(f"the prompt (about {len(prompt) // 4} tokens at least) plus {answer} for the answer does not "
                         f"fit num_ctx={num_ctx}; raise CYNQRA_NUM_CTX")
    options: dict = {"num_ctx": num_ctx, "num_predict": answer}
    if temperature is not None:
        options["temperature"] = temperature
    elif os.environ.get("CYNQRA_TEMPERATURE"):
        options["temperature"] = float(os.environ["CYNQRA_TEMPERATURE"])
    if os.environ.get("CYNQRA_SEED"):
        options["seed"] = int(os.environ["CYNQRA_SEED"])
    payload: dict = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False,
                     "options": options, "keep_alive": os.environ.get("CYNQRA_KEEP_ALIVE", "30m"),
                     "shift": False, "truncate": False}
    if want_json:
        payload["format"] = schema or "json"
    think = (os.environ.get("CYNQRA_THINK") or "").strip().lower()
    if think:
        payload["think"] = {"true": True, "false": False}.get(think, think)
    try:
        data = _post(ollama_host() + "/api/chat", payload, {"Content-Type": "application/json"}, _local_timeout())
    except RuntimeError as exc:
        if "Connection refused" in str(exc) or "Errno 111" in str(exc) or "10061" in str(exc):
            raise RuntimeError(f"Ollama is not running at {ollama_host()}. Start the Ollama app, or run: ollama serve") from exc
        if "not found" in str(exc) and "HTTP 404" in str(exc):
            raise RuntimeError(f"model {model} is not installed. Run: ollama pull {model}") from exc
        if "HTTP 400" in str(exc) and "context length" in str(exc):
            raise RuntimeError(f"the prompt is longer than num_ctx={num_ctx}; raise CYNQRA_NUM_CTX") from exc
        raise
    if data.get("done_reason") == "length":
        raise RuntimeError(f"reply truncated at num_predict={answer} or num_ctx={num_ctx}")
    msg = data.get("message") or {}
    text = msg.get("content") or ""
    if not text.strip():
        raise RuntimeError("the model returned no answer" + (" (only thinking)" if msg.get("thinking") else ""))
    return {"text": text, "tokens_in": int(data.get("prompt_eval_count") or 0),
            "tokens_out": int(data.get("eval_count") or 0), "estimated": False}


def _local_openai(prompt: str, model: str, max_tokens: int, want_json: bool = False, schema: dict | None = None,
                  temperature: float | None = None) -> dict:
    """LM Studio or llama-server. Their context size is set when the server loads the model (-c 32768)."""
    base = os.environ["CYNQRA_LOCAL_BASE_URL"].rstrip("/")
    headers = {"Content-Type": "application/json"}
    if os.environ.get("CYNQRA_LOCAL_API_KEY"):
        headers["Authorization"] = f"Bearer {os.environ['CYNQRA_LOCAL_API_KEY']}"
    payload: dict = {"model": model, "messages": [{"role": "user", "content": prompt}],
                     "max_tokens": int(os.environ.get("CYNQRA_NUM_PREDICT") or 0) or max(max_tokens, 8192), "stream": False}
    if want_json and schema:
        payload["response_format"] = {"type": "json_schema",
                                      "json_schema": {"name": "result", "strict": True, "schema": schema}}
    think = (os.environ.get("CYNQRA_THINK") or "").strip().lower()
    if think == "false":
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    elif think in ("low", "medium", "high"):  # gpt-oss: reasoning can be kept low, not switched off
        payload["chat_template_kwargs"] = {"reasoning_effort": think}
    if temperature is not None or os.environ.get("CYNQRA_TEMPERATURE"):
        payload["temperature"] = temperature if temperature is not None else float(os.environ["CYNQRA_TEMPERATURE"])
    if os.environ.get("CYNQRA_SEED"):
        payload["seed"] = int(os.environ["CYNQRA_SEED"])
    try:
        # No transport retries: the request is deterministic (seed, temperature 0), so sending it again would
        # spend minutes of a laptop's time for the same answer. The caller retries with its own temperature.
        data = _post(base + "/chat/completions", payload, headers, _local_timeout(), retry=False)
    except RuntimeError as exc:
        text = str(exc)
        if "exceed_context_size" in text or "exceeds the available context size" in text:
            raise RuntimeError("the prompt is longer than the model's context window; use a model with a larger "
                               "context, or a smaller objective") from exc
        if "does not match the expected" in text:
            raise RuntimeError("the model's answer did not follow the required format (the server could not parse it)") from exc
        if "Connection refused" in text or "Errno 111" in text or "10061" in text:
            raise RuntimeError(f"the model server at {base} is not running") from exc
        raise
    choice = data["choices"][0]
    if choice.get("finish_reason") == "length":
        raise RuntimeError("reply truncated at max_tokens")
    usage = data.get("usage") or {}
    out = {"text": choice["message"].get("content") or "", "tokens_in": int(usage.get("prompt_tokens") or 0),
           "tokens_out": int(usage.get("completion_tokens") or 0), "estimated": False}
    t = data.get("timings") or {}  # llama-server's own measurement of this call
    if t.get("predicted_per_second"):
        out["speed"] = {"read_tps": round(float(t.get("prompt_per_second") or 0), 1),
                        "write_tps": round(float(t["predicted_per_second"]), 1)}
    return out


def _cmd(prompt: str) -> dict:
    cmd = os.environ["CYNQRA_S1_MODEL_CMD"]
    proc = subprocess.run(
        cmd, input=prompt, text=True, capture_output=True, shell=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"model command exited {proc.returncode}: {(proc.stderr or '').strip()[:300]}"
        )
    text = proc.stdout or ""
    return {
        "text": text,
        "tokens_in": max(1, len(prompt) // 4),
        "tokens_out": max(1, len(text) // 4),
        "estimated": True,
    }


def complete(prompt: str, max_tokens: int = 1500, want_json: bool = False, schema: dict | None = None,
             temperature: float | None = None) -> dict:
    """Returns text, tokens_in, tokens_out, estimated, latency_s, error.

    max_tokens defaults to 1500, the S1 setting. S2 passes a larger value
    because workers return code and tests inside one protocol object.
    want_json asks a local Ollama model for constrained JSON output, shaped by
    schema when one is given.
    """
    model = resolve()
    if model is None:
        raise RuntimeError("No model. Set CYNQRA_OLLAMA_MODEL (a local Ollama model), CYNQRA_LOCAL_BASE_URL, "
                           "CYNQRA_S1_MODEL_CMD, OPENAI_API_KEY or ANTHROPIC_API_KEY.")
    start = time.time()
    try:
        if model["kind"] == "cmd":
            out = _cmd(prompt)
        elif model["kind"] == "ollama":
            out = _ollama(prompt, model["label"], max_tokens, want_json, schema, temperature)
        elif model["kind"] == "local":
            out = _local_openai(prompt, model["label"], max_tokens, want_json, schema, temperature)
        elif model["kind"] == "openai":
            out = _openai(prompt, model["label"], max_tokens)
        else:
            out = _anthropic(prompt, model["label"], max_tokens)
        out["error"] = None
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        KeyError,
        IndexError,
        OSError,
        ValueError,
        TypeError,
        RuntimeError,
    ) as exc:
        out = {
            "text": "",
            "tokens_in": 0,
            "tokens_out": 0,
            "estimated": True,
            "error": f"{type(exc).__name__}: {exc}",
        }
    out["latency_s"] = round(time.time() - start, 3)
    out["model"] = model["label"]
    out["kind"] = model["kind"]
    return out
