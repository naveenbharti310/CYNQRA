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

27 Sep 2026, fifth pass: a caller that can use part of a reply passes
partial=True. A local reply cut off at max_tokens then comes back with
truncated=True instead of as an error: an engineer's files that were
complete before the cut are kept, and only the rest is asked for again.

27 Sep 2026, sixth pass: Hugging Face Inference Providers. HF_TOKEN and
CYNQRA_HF_MODEL (a model id, optionally with a provider suffix such as
openai/gpt-oss-120b:cerebras) send calls to the router's OpenAI-compatible
endpoint (HF_ROUTER_URL, default https://router.huggingface.co/v1). These
are paid calls on someone else's hardware: token counts are the provider's
own, rate limits and server errors are retried, a JSON Schema is sent as
response_format, and a refused token or spent credit reads as what it is.

27 Sep 2026, seventh pass: one process, many models. complete(route=...)
sends one call to one model: the route holds that model's settings under
the same names as the environment (kind, label, CYNQRA_LOCAL_BASE_URL,
CYNQRA_HF_MODEL, CYNQRA_NUM_PREDICT, ...), and they overlay the process
environment for that call only, on that thread; a key set to None counts
as unset. Cynqra's provider adapters build routes, so each worker can run on
a different model; a route carries the connection's endpoint
(CYNQRA_ANTHROPIC_URL, CYNQRA_OPENAI_URL, CYNQRA_LOCAL_BASE_URL,
HF_ROUTER_URL) and its credential for that one call, and nothing is kept.
Two faults can be set on a route, for proving that
Cynqra notices and replaces a failing model: offline (the model cannot be
reached) and CYNQRA_MAX_REPLY (a hard cap on the reply, so a real model
really runs out of room). Neither invents an answer.

30 Sep 2026, eighth pass: hosted OpenAI-compatible providers that are not
Hugging Face or OpenAI (Google Gemini, NVIDIA Build, Mistral, Z.ai,
OpenRouter). Their calls go through the same path as a local server, which
was built for a laptop. Three things differ for a hosted API:
  * A free tier answers "too many requests" often. Such a call is now retried
    (HOSTED_RETRY_WAITS_S, honouring the provider's retry-after up to a
    minute) before it counts as the provider's side; a laptop's server is
    still never retried.
  * Not every provider accepts a strict JSON Schema. A reply of HTTP 400 or
    422 about response_format is sent again with plain JSON mode, then with
    no format at all; the prompt still asks for JSON and the caller still
    checks it. What a provider accepted is remembered for the process, so
    later calls do not pay for the refusal again.
  * Thinking models spend part of the reply on thinking, so a hosted call
    gets at least HOSTED_MIN_REPLY tokens of room, as Hugging Face calls do.
"""
from __future__ import annotations

import http.client
import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request

class _Overlay:
    """The process environment, overlaid by the route of the call in progress on this thread."""

    def get(self, key: str, default=None):
        route = getattr(_LOCAL, "route", None) or {}
        if key in route:
            return route[key] if route[key] is not None else default
        return os.environ.get(key, default)

    def __getitem__(self, key: str):
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value


_LOCAL = threading.local()
_ENV = _Overlay()

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MIN_MAX_TOKENS = 16000
TIMEOUT_S = 600
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 529}  # the provider's side: worth a wait and a retry
RETRY_WAITS_S = (2.0, 6.0)
# a hosted free tier limits calls per minute: waits that outlast a one-minute window
HOSTED_RETRY_WAITS_S = (5.0, 15.0, 30.0, 60.0)
HOSTED_MIN_REPLY = 16000
# what each hosted provider accepted as response_format, by (endpoint, model): "json_schema", "json_object" or "none"
_JSON_MODE: dict[tuple[str, str], str] = {}
_JSON_MODES = ("json_schema", "json_object", "none")
EFFORTS = {"low", "medium", "high", "xhigh", "max"}


def resolve() -> dict | None:
    route = getattr(_LOCAL, "route", None)
    if route and route.get("kind"):
        return {"kind": route["kind"], "label": route.get("label") or route["kind"], "tokens": "measured",
                "local": bool(route.get("local"))}
    cmd = _ENV.get("CYNQRA_S1_MODEL_CMD")
    if cmd:
        return {"kind": "cmd", "label": "shell command", "tokens": "estimated"}
    if _ENV.get("CYNQRA_OLLAMA_MODEL"):
        return {"kind": "ollama", "label": _ENV["CYNQRA_OLLAMA_MODEL"], "tokens": "measured", "local": True}
    if _ENV.get("CYNQRA_LOCAL_BASE_URL"):
        return {"kind": "local", "label": _ENV.get("CYNQRA_MODEL", "local-model"), "tokens": "measured",
                "local": True}
    if _ENV.get("HF_TOKEN") and _ENV.get("CYNQRA_HF_MODEL"):
        return {"kind": "hf", "label": _ENV["CYNQRA_HF_MODEL"], "tokens": "measured"}
    if _ENV.get("OPENAI_API_KEY"):
        return {
            "kind": "openai",
            "label": _ENV.get("CYNQRA_MODEL", "gpt-4o-mini"),
            "tokens": "measured",
        }
    if _ENV.get("ANTHROPIC_API_KEY"):
        return {
            "kind": "anthropic",
            "label": _ENV.get("CYNQRA_MODEL", "claude-sonnet-5"),
            "tokens": "measured",
        }
    return None


class _Retryable(RuntimeError):
    def __init__(self, msg: str, wait: float | None = None):
        super().__init__(msg)
        self.wait = wait


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A call that carries a key never follows a redirect: urllib would send the key on to wherever it points."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


# Who is calling, on every request. Without it Python's own signature is sent, and a provider behind a bot filter
# refuses the call before it reads the key (Groq answered HTTP 403, Cloudflare error 1010).
USER_AGENT = "cynqra/1.0"


def _post_once(url: str, body: bytes, headers: dict, timeout: float = TIMEOUT_S) -> dict:
    req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT, **headers}, method="POST")
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:800]  # long enough to hold a limit's name
        except Exception:
            pass
        msg = f"HTTP {exc.code} from provider: {detail}"
        if exc.code in RETRY_STATUS:
            wait = None
            try:
                wait = min(60.0, float(exc.headers.get("retry-after")))
            except (TypeError, ValueError):
                pass
            raise _Retryable(msg, wait) from exc
        raise RuntimeError(msg) from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as exc:
        # a dropped connection or a reply cut off in transit (RemoteDisconnected, IncompleteRead) is the network's
        raise _Retryable(f"network error: {type(exc).__name__}: {exc}") from exc


def _post(url: str, payload: dict, headers: dict, timeout: float = TIMEOUT_S, retry: bool = True,
          waits: tuple = RETRY_WAITS_S) -> dict:
    body = json.dumps(payload).encode("utf-8")
    for wait in (tuple(waits) if retry else ()) + (None,):
        try:
            return _post_once(url, body, headers, timeout)
        except _Retryable as exc:
            if wait is None:
                raise RuntimeError(str(exc)) from exc
            time.sleep(exc.wait if exc.wait is not None else wait)
    raise RuntimeError("unreachable")


def _openai(prompt: str, model: str, max_tokens: int = 1500) -> dict:
    data = _post(
        _ENV.get("CYNQRA_OPENAI_URL") or OPENAI_URL,
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_completion_tokens": max_tokens,
        },
        {
            "Authorization": f"Bearer {_ENV['OPENAI_API_KEY']}",
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
    effort = (_ENV.get("CYNQRA_EFFORT") or "").strip().lower()
    if effort:
        if effort not in EFFORTS:
            raise ValueError(f"CYNQRA_EFFORT must be one of {sorted(EFFORTS)}, not {effort!r}")
        payload["output_config"] = {"effort": effort}
    data = _post(
        _ENV.get("CYNQRA_ANTHROPIC_URL") or ANTHROPIC_URL,
        payload,
        {
            "x-api-key": _ENV["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            # a key not scoped to one workspace must name the workspace each request runs in
            **({"anthropic-workspace-id": _ENV.get("ANTHROPIC_WORKSPACE_ID")}
               if _ENV.get("ANTHROPIC_WORKSPACE_ID") else {}),
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
    host = (_ENV.get("OLLAMA_HOST") or "127.0.0.1:11434").strip().rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host.replace("://0.0.0.0", "://127.0.0.1")


def _local_timeout() -> float:
    try:
        return float(_ENV.get("CYNQRA_TIMEOUT") or 1800)
    except ValueError:
        return 1800.0


def _cap(tokens: int) -> int:
    """A route's CYNQRA_MAX_REPLY fault caps every reply, whatever the caller asked for."""
    cap = int(_ENV.get("CYNQRA_MAX_REPLY") or 0)
    return min(tokens, cap) if cap else tokens


def _ollama(prompt: str, model: str, max_tokens: int, want_json: bool, schema: dict | None = None,
            temperature: float | None = None, partial: bool = False) -> dict:
    num_ctx = int(_ENV.get("CYNQRA_NUM_CTX") or 32768)
    answer = _cap(int(_ENV.get("CYNQRA_NUM_PREDICT") or 0) or max(max_tokens, 8192))
    if len(prompt) // 4 + answer > num_ctx:  # four characters a token is a floor, so this only refuses sure failures
        raise ValueError(f"the prompt (about {len(prompt) // 4} tokens at least) plus {answer} for the answer does not "
                         f"fit num_ctx={num_ctx}; raise CYNQRA_NUM_CTX")
    options: dict = {"num_ctx": num_ctx, "num_predict": answer}
    if temperature is not None:
        options["temperature"] = temperature
    elif _ENV.get("CYNQRA_TEMPERATURE"):
        options["temperature"] = float(_ENV["CYNQRA_TEMPERATURE"])
    if _ENV.get("CYNQRA_SEED"):
        options["seed"] = int(_ENV["CYNQRA_SEED"])
    payload: dict = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False,
                     "options": options, "keep_alive": _ENV.get("CYNQRA_KEEP_ALIVE", "30m"),
                     "shift": False, "truncate": False}
    if want_json:
        payload["format"] = schema or "json"
    think = (_ENV.get("CYNQRA_THINK") or "").strip().lower()
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
    cut = data.get("done_reason") == "length"
    if cut and not partial:
        raise RuntimeError(f"reply truncated at num_predict={answer} or num_ctx={num_ctx}")
    msg = data.get("message") or {}
    text = msg.get("content") or ""
    if not text.strip():
        raise RuntimeError("the model returned no answer" + (" (only thinking)" if msg.get("thinking") else ""))
    return {"text": text, "tokens_in": int(data.get("prompt_eval_count") or 0),
            "tokens_out": int(data.get("eval_count") or 0), "estimated": False, "truncated": cut}


def _local_openai(prompt: str, model: str, max_tokens: int, want_json: bool = False, schema: dict | None = None,
                  temperature: float | None = None, partial: bool = False) -> dict:
    """LM Studio or llama-server. Their context size is set when the server loads the model (-c 32768)."""
    base = _ENV["CYNQRA_LOCAL_BASE_URL"].rstrip("/")
    hosted = _ENV.get("local") is False  # a hosted provider reached as an OpenAI-compatible server, not a laptop's
    headers = {"Content-Type": "application/json"}
    if _ENV.get("CYNQRA_LOCAL_API_KEY"):
        # Every provider, Google included: its OpenAI-compatible route reads only Authorization and ignores
        # x-goog-api-key ("Missing or invalid Authorization header"), for AIza and AQ. keys alike
        headers["Authorization"] = f"Bearer {_ENV['CYNQRA_LOCAL_API_KEY']}"
    floor = HOSTED_MIN_REPLY if hosted else 8192
    payload: dict = {"model": model, "messages": [{"role": "user", "content": prompt}],
                     "max_tokens": _cap(int(_ENV.get("CYNQRA_NUM_PREDICT") or 0) or max(max_tokens, floor)), "stream": False}
    key = (base, model)
    mode = _JSON_MODE.get(key, "json_schema") if want_json and schema else "none"
    _json_format(payload, mode, schema)
    think = (_ENV.get("CYNQRA_THINK") or "").strip().lower()
    if think == "false":
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    elif think in ("low", "medium", "high"):  # gpt-oss: reasoning can be kept low, not switched off
        payload["chat_template_kwargs"] = {"reasoning_effort": think}
    if hosted and (_ENV.get("CYNQRA_EFFORT") or "").lower() in ("low", "medium", "high"):
        # how long a thinking model thinks before answering (Kimi K3 defaults to its maximum, which is slow)
        payload["reasoning_effort"] = _ENV["CYNQRA_EFFORT"].lower()
    if temperature is not None or _ENV.get("CYNQRA_TEMPERATURE"):
        payload["temperature"] = temperature if temperature is not None else float(_ENV["CYNQRA_TEMPERATURE"])
    if _ENV.get("CYNQRA_SEED"):
        payload["seed"] = int(_ENV["CYNQRA_SEED"])
    try:
        # No transport retries: the request is deterministic (seed, temperature 0), so sending it again would
        # spend minutes of a laptop's time for the same answer. The caller retries with its own temperature.
        while True:
            try:
                data = _post(base + "/chat/completions", payload, headers, _local_timeout(), retry=hosted,
                             waits=HOSTED_RETRY_WAITS_S)
                break
            except RuntimeError as exc:
                if mode == "none" or not _format_refused(str(exc)):
                    raise
                mode = _JSON_MODES[_JSON_MODES.index(mode) + 1]  # the provider refused this format: a plainer one
                _json_format(payload, mode, schema)
        if want_json and schema:
            _JSON_MODE[key] = mode
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
    cut = choice.get("finish_reason") == "length"
    if cut and not partial:
        raise RuntimeError("reply truncated at max_tokens")
    usage = data.get("usage") or {}
    out = {"text": choice["message"].get("content") or "", "tokens_in": int(usage.get("prompt_tokens") or 0),
           "tokens_out": int(usage.get("completion_tokens") or 0), "estimated": False, "truncated": cut}
    t = data.get("timings") or {}  # llama-server's own measurement of this call
    if t.get("predicted_per_second"):
        out["speed"] = {"read_tps": round(float(t.get("prompt_per_second") or 0), 1),
                        "write_tps": round(float(t["predicted_per_second"]), 1),
                        # prompt tokens the server reused from its cache instead of reading them again
                        "cached": int(t.get("cache_n") or 0)}
    return out


def _json_format(payload: dict, mode: str, schema: dict | None) -> None:
    """Ask for JSON the way this provider accepts: a strict schema, plain JSON mode, or nothing (the prompt asks)."""
    if mode == "json_schema":
        payload["response_format"] = {"type": "json_schema",
                                      "json_schema": {"name": "result", "strict": True, "schema": schema}}
    elif mode == "json_object":
        payload["response_format"] = {"type": "json_object"}
    else:
        payload.pop("response_format", None)


_FORMAT_REFUSED = re.compile(r"response_format|json_schema|json_object|structured output|response format|"
                             r"responseschema|response_schema", re.I)


def _format_refused(error: str) -> bool:
    """The provider refused the request because of how JSON was asked for, not because of the prompt or the key."""
    return bool(re.search(r"HTTP (400|422)\b", error)) and bool(_FORMAT_REFUSED.search(error))


def _hf(prompt: str, model: str, max_tokens: int, want_json: bool = False, schema: dict | None = None,
        temperature: float | None = None, partial: bool = False) -> dict:
    """Hugging Face Inference Providers: the router's OpenAI-compatible chat completions."""
    base = (_ENV.get("HF_ROUTER_URL") or "https://router.huggingface.co/v1").rstrip("/")
    payload: dict = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False,
                     # reasoning models spend part of max_tokens thinking, so the floor leaves room for the answer
                     "max_tokens": _cap(max(max_tokens, int(_ENV.get("CYNQRA_NUM_PREDICT") or 16000))),
                     "temperature": temperature if temperature is not None else float(_ENV.get("CYNQRA_TEMPERATURE") or 0)}
    if want_json and schema:
        payload["response_format"] = {"type": "json_schema",
                                      "json_schema": {"name": "result", "strict": True, "schema": schema}}
    if (_ENV.get("CYNQRA_EFFORT") or "").lower() in ("low", "medium", "high"):
        payload["reasoning_effort"] = _ENV["CYNQRA_EFFORT"].lower()
    headers = {"Authorization": f"Bearer {_ENV['HF_TOKEN']}", "Content-Type": "application/json"}
    try:
        data = _post(base + "/chat/completions", payload, headers)
    except RuntimeError as exc:
        text = str(exc)
        if "HTTP 401" in text or "HTTP 403" in text:
            raise RuntimeError("Hugging Face refused the token: it needs the permission to make calls to Inference "
                               "Providers") from exc
        if "HTTP 402" in text:
            raise RuntimeError("the Hugging Face account has no inference credit left") from exc
        raise
    choice = data["choices"][0]
    cut = choice.get("finish_reason") == "length"
    if cut and not partial:
        raise RuntimeError(f"reply truncated at max_tokens={payload['max_tokens']}")
    usage = data.get("usage") or {}
    text = choice["message"].get("content") or ""
    if not text.strip() and not cut:
        raise RuntimeError("the model returned no answer")
    return {"text": text, "tokens_in": int(usage.get("prompt_tokens") or 0),
            "tokens_out": int(usage.get("completion_tokens") or 0), "estimated": False, "truncated": cut}


def _cmd(prompt: str) -> dict:
    cmd = _ENV["CYNQRA_S1_MODEL_CMD"]
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
             temperature: float | None = None, partial: bool = False, route: dict | None = None) -> dict:
    if route is None:
        return _complete(prompt, max_tokens, want_json, schema, temperature, partial)
    before = getattr(_LOCAL, "route", None)
    _LOCAL.route = route
    try:
        if route.get("offline"):
            return {"text": "", "tokens_in": 0, "tokens_out": 0, "estimated": False, "latency_s": 0.0,
                    "model": route.get("label"), "kind": route.get("kind"),
                    "error": f"RuntimeError: {route.get('label')} is offline (a fault set on it in the model registry)"}
        return _complete(prompt, max_tokens, want_json, schema, temperature, partial)
    finally:
        _LOCAL.route = before


def _complete(prompt: str, max_tokens: int, want_json: bool, schema: dict | None, temperature: float | None,
              partial: bool) -> dict:
    """Returns text, tokens_in, tokens_out, estimated, latency_s, error.

    max_tokens defaults to 1500, the S1 setting. S2 passes a larger value
    because workers return code and tests inside one protocol object.
    want_json asks a local Ollama model for constrained JSON output, shaped by
    schema when one is given. partial=True returns a local reply cut off at
    max_tokens, marked truncated=True, instead of an error.
    """
    model = resolve()
    if model is None:
        raise RuntimeError("No model. Set CYNQRA_OLLAMA_MODEL (a local Ollama model), CYNQRA_LOCAL_BASE_URL, "
                           "HF_TOKEN with CYNQRA_HF_MODEL, CYNQRA_S1_MODEL_CMD, OPENAI_API_KEY or ANTHROPIC_API_KEY.")
    start = time.time()
    try:
        if model["kind"] == "cmd":
            out = _cmd(prompt)
        elif model["kind"] == "ollama":
            out = _ollama(prompt, model["label"], max_tokens, want_json, schema, temperature, partial)
        elif model["kind"] == "local":
            out = _local_openai(prompt, model["label"], max_tokens, want_json, schema, temperature, partial)
        elif model["kind"] == "hf":
            out = _hf(prompt, model["label"], max_tokens, want_json, schema, temperature, partial)
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
