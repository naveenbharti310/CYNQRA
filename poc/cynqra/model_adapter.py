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
import random
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
# An overloaded model (HTTP 503 or 529, "high demand") is not out of quota but out of capacity for a moment: paid run
# 37589136743 met Google's "This model is currently experiencing high demand" again and again. It is asked again
# soon, each wait doubling, spread at random so the team's workers do not all come back at the same instant
OVERLOAD_STATUS = {503, 529}
OVERLOAD_WAITS_S = (2.0, 4.0, 8.0, 16.0, 32.0)
_OVERLOAD = re.compile(r"high demand|overloaded|try again later|\bUNAVAILABLE\b", re.I)
HOSTED_MIN_REPLY = 16000
# what each hosted provider accepted as response_format, by (endpoint, model): "json_schema", "json_object" or "none"
_JSON_MODE: dict[tuple[str, str], str] = {}
# (endpoint, model) pairs whose provider refused reasoning_effort: asked without it from then on
_NO_EFFORT: set[tuple[str, str]] = set()
_EFFORT_REFUSED = re.compile(r"reasoning[_ ]effort|reasoning", re.I)
CALL_EFFORTS = ("low", "medium", "high")


def reply_limit(max_tokens: int, local: bool, kind: str = "") -> int:
    """The most a call may write, reasoning included: what the transport sends as the provider's output limit. A
    hosted OpenAI-compatible, Hugging Face or Anthropic call is given at least HOSTED_MIN_REPLY (a thinking model
    spends part of it thinking); OpenAI's own API (kind "openai", _openai) and a model on this computer are sent
    what was asked for. What a budget reservation must cover, and no more."""
    return int(max_tokens) if local or kind == "openai" else max(int(max_tokens), HOSTED_MIN_REPLY)


class _Truncated(RuntimeError):
    """A reply cut off at its output limit: the provider bills the tokens all the same, so they are kept."""

    def __init__(self, msg: str, usage: dict):
        super().__init__(msg)
        self.usage = usage
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
    def __init__(self, msg: str, wait: float | None = None, overload: bool = False):
        super().__init__(msg)
        self.wait = wait
        self.overload = overload


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A call that carries a key never follows a redirect: urllib would send the key on to wherever it points."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


# Who is calling, on every request. Without it Python's own signature is sent, and a provider behind a bot filter
# refuses the call before it reads the key (Groq answered HTTP 403, Cloudflare error 1010).
USER_AGENT = "cynqra/1.0"


# Pacing from the provider's own rate-limit headers (R7 of the architecture review). A provider that says how many
# requests or tokens are left in its window, and when the window resets, is not called again until it has room: the
# calls of every worker on that key wait together instead of each running into a 429 and backing off on its own.
# A Retry-After on a refusal holds every call on that key, not only the refused one.
LIMIT_HEADERS = (  # (remaining, reset): OpenAI, Groq, NVIDIA, Mistral and most OpenAI-compatible APIs; Anthropic; IETF
    ("x-ratelimit-remaining-requests", "x-ratelimit-reset-requests", 0),
    ("x-ratelimit-remaining-tokens", "x-ratelimit-reset-tokens", 4000),
    ("anthropic-ratelimit-requests-remaining", "anthropic-ratelimit-requests-reset", 0),
    ("anthropic-ratelimit-input-tokens-remaining", "anthropic-ratelimit-input-tokens-reset", 4000),
    ("anthropic-ratelimit-output-tokens-remaining", "anthropic-ratelimit-output-tokens-reset", 1000),
    ("x-ratelimit-remaining", "x-ratelimit-reset", 0),
    ("ratelimit-remaining", "ratelimit-reset", 0),
)
PACE_MAX_WAIT_S = 120.0  # one wait is never longer; the call then goes, and a refusal is retried as before
_PACE: dict[str, float] = {}  # key (host and a digest of the credential) -> not before (time.time())
_PACE_LOCK = threading.Lock()
_PACE_STATS = {"waits": 0, "seconds": 0.0}
_DURATION = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")
_RETRY_DELAY = re.compile(r'"retryDelay"\s*:\s*"([^"]+)"')


def _seconds_until(value) -> float | None:
    """A reset as providers write it: "20ms", "6m0s", "1h2m3.5s", plain seconds, or an RFC 3339 time."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    parts = _DURATION.findall(text)
    if parts and "".join(n + u for n, u in parts) == text.replace(" ", ""):
        return sum(float(n) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[u] for n, u in parts)
    try:
        from datetime import datetime
        return max(0.0, datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() - time.time())
    except ValueError:
        return None


def _pace_key(url: str, headers: dict) -> str:
    import hashlib
    from urllib.parse import urlsplit
    cred = next((str(v) for k, v in headers.items()
                 if k.lower() in ("authorization", "x-api-key", "x-goog-api-key", "api-key")), "")
    return urlsplit(url).netloc + "|" + hashlib.sha256(cred.encode("utf-8")).hexdigest()[:12]


def _limit_wait(reply_headers, retry_after: float | None = None) -> float:
    """How long the provider's headers say to hold the next call on this key."""
    wait = float(retry_after or 0)
    get = (lambda k: reply_headers.get(k)) if reply_headers is not None else (lambda k: None)
    for remaining, reset, floor in LIMIT_HEADERS:
        try:
            left = float(get(remaining))
        except (TypeError, ValueError):
            continue
        if left <= floor:
            wait = max(wait, _seconds_until(get(reset)) or 0.0)
    return min(wait, PACE_MAX_WAIT_S)


def _note_limits(url: str, headers: dict, reply_headers, retry_after: float | None = None) -> None:
    wait = _limit_wait(reply_headers, retry_after)
    if wait > 0:
        key = _pace_key(url, headers)
        with _PACE_LOCK:
            _PACE[key] = max(_PACE.get(key, 0.0), time.time() + wait)


def _await_pace(url: str, headers: dict) -> None:
    key = _pace_key(url, headers)
    with _PACE_LOCK:
        wait = min(PACE_MAX_WAIT_S, _PACE.get(key, 0.0) - time.time())
        if wait > 0:
            _PACE_STATS["waits"] += 1
            _PACE_STATS["seconds"] += wait
    if wait > 0:
        time.sleep(wait)


def pace_stats() -> dict:
    with _PACE_LOCK:
        return {"waits": _PACE_STATS["waits"], "seconds": round(_PACE_STATS["seconds"], 1)}


def _post_once(url: str, body: bytes, headers: dict, timeout: float = TIMEOUT_S) -> dict:
    req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT, **headers}, method="POST")
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            _note_limits(url, headers, getattr(resp, "headers", None))
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
                delay = _RETRY_DELAY.search(detail)  # Google says it in the body: "retryDelay": "37s"
                wait = min(60.0, _seconds_until(delay.group(1)) or 0.0) if delay else None
            _note_limits(url, headers, getattr(exc, "headers", None), wait)  # every call on this key holds
            raise _Retryable(msg, wait, overload=exc.code in OVERLOAD_STATUS or bool(_OVERLOAD.search(detail))) \
                from exc
        raise RuntimeError(msg) from exc
    except TimeoutError as exc:
        raise _timed_out(timeout) from exc
    except (urllib.error.URLError, ConnectionError, http.client.HTTPException) as exc:
        if isinstance(getattr(exc, "reason", None), TimeoutError):
            raise _timed_out(timeout) from exc
        # a dropped connection or a reply cut off in transit (RemoteDisconnected, IncompleteRead) is the network's
        raise _Retryable(f"network error: {type(exc).__name__}: {exc}") from exc


def _timed_out(timeout: float) -> RuntimeError:
    """The provider held the call open for the whole limit. Sending it again would wait as long again (one call held
    real run 37044180144 for 51 minutes, five attempts of ten), so it fails now, as the provider's side: the work
    waits, or a stand-in covers it. A refusal that comes back fast (429, 5xx, a dropped connection) is still retried."""
    return RuntimeError(f"network error: the provider timed out after {timeout:.0f} s")


def _tokens_out(usage: dict) -> int:
    """Output tokens as the provider bills them: the reply, plus hidden reasoning a provider reports only in its total
    (Google's OpenAI-compatible route counts thoughts in total_tokens, not in completion_tokens, and bills them as
    output: paid run 37589136743 measured 170 tokens in 186 s). A provider whose completion_tokens already includes
    its reasoning (OpenAI) leaves nothing over."""
    out = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or 0)
    return max(out, total - int(usage.get("prompt_tokens") or 0)) if total else out


def _tokens_cached(usage: dict) -> int:
    """Input tokens the provider read from its prompt cache, billed at its cached rate: OpenAI's and Google's
    OpenAI-compatible prompt_tokens_details.cached_tokens, DeepSeek's prompt_cache_hit_tokens, Anthropic's
    cache_read_input_tokens. Never more than the prompt."""
    details = usage.get("prompt_tokens_details") or {}
    n = int((details.get("cached_tokens") if isinstance(details, dict) else 0) or usage.get("prompt_cache_hit_tokens")
            or usage.get("cache_read_input_tokens") or 0)
    total = int(usage.get("prompt_tokens") or 0) or (int(usage.get("input_tokens") or 0) + n
                                                     + int(usage.get("cache_creation_input_tokens") or 0))
    return max(0, min(n, total))


def _cache_reported(usage: dict) -> bool:
    """Whether the provider's usage says anything about its prompt cache, so a run can tell "no cache hits" from "the
    provider does not report them". Google's OpenAI-compatible route has been reported to leave them out; and Gemini
    caches no prompt under its minimum (4,096 tokens for the Gemini 3 models: adapters.CACHE_MIN_TOKENS)."""
    details = usage.get("prompt_tokens_details")
    return (isinstance(details, dict) and "cached_tokens" in details) or any(
        k in usage for k in ("prompt_cache_hit_tokens", "cache_read_input_tokens", "cached_tokens"))


def _post(url: str, payload: dict, headers: dict, timeout: float = TIMEOUT_S, retry: bool = True,
          waits: tuple = RETRY_WAITS_S) -> dict:
    """One call, retried on the provider's side. A hosted model that is overloaded is retried on the short, spread
    schedule (OVERLOAD_WAITS_S); a limit or a dropped connection on the given waits; the provider's Retry-After wins."""
    body = json.dumps(payload).encode("utf-8")
    attempt, waited = 0, False
    while True:
        if not waited:  # the provider's headers may hold this key; a call that just slept its Retry-After goes
            _await_pace(url, headers)
        try:
            return _post_once(url, body, headers, timeout)
        except _Retryable as exc:
            schedule = OVERLOAD_WAITS_S if exc.overload and waits is HOSTED_RETRY_WAITS_S else tuple(waits)
            if not retry or attempt >= len(schedule):
                raise RuntimeError(str(exc)) from exc
            spread = random.uniform(0.75, 1.25) if schedule is OVERLOAD_WAITS_S else 1.0
            time.sleep(exc.wait if exc.wait is not None else schedule[attempt] * spread)
            waited = exc.wait is not None
            attempt += 1


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
        _hosted_timeout(),
    )
    if data["choices"][0].get("finish_reason") == "length":
        raise RuntimeError(f"reply truncated at max_completion_tokens={max_tokens}")
    usage = data.get("usage") or {}
    return {
        "text": (data["choices"][0]["message"]["content"] or ""),
        "tokens_in": int(usage.get("prompt_tokens") or 0),
        "tokens_out": _tokens_out(usage),
        "tokens_cached": _tokens_cached(usage), "cache_reported": _cache_reported(usage),
        "estimated": False,
    }


def _hosted_timeout() -> float:
    """A hosted call's limit: the route's (the gateway sets one from the model's own answer times, or a probe's
    shorter one), else TIMEOUT_S."""
    try:
        return float(_ENV.get("CYNQRA_TIMEOUT") or TIMEOUT_S)
    except ValueError:
        return float(TIMEOUT_S)


def _anthropic(prompt: str, model: str, max_tokens: int = 1500, effort: str | None = None) -> dict:
    payload = {
        "model": model,
        "max_tokens": max(max_tokens, ANTHROPIC_MIN_MAX_TOKENS),
        "messages": [{"role": "user", "content": prompt}],
    }
    fixed = (_ENV.get("CYNQRA_EFFORT") or "").strip().lower()
    if fixed and fixed not in EFFORTS:
        raise ValueError(f"CYNQRA_EFFORT must be one of {sorted(EFFORTS)}, not {fixed!r}")
    key = ("anthropic", model)
    # the connection's own setting wins; else the call's (the work's risk, the escalation ladder, a review's
    # round), unless this model refused it before
    chosen = fixed or (effort if effort in CALL_EFFORTS and key not in _NO_EFFORT else "")
    if chosen:
        payload["output_config"] = {"effort": chosen}
    headers = {
        "x-api-key": _ENV["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
        # a key not scoped to one workspace must name the workspace each request runs in
        **({"anthropic-workspace-id": _ENV.get("ANTHROPIC_WORKSPACE_ID")}
           if _ENV.get("ANTHROPIC_WORKSPACE_ID") else {}),
    }
    url = _ENV.get("CYNQRA_ANTHROPIC_URL") or ANTHROPIC_URL
    try:
        data = _post(url, payload, headers, _hosted_timeout())
    except RuntimeError as exc:
        if chosen and not fixed and "HTTP 400" in str(exc) and "effort" in str(exc).lower():
            _NO_EFFORT.add(key)  # this model takes no effort setting: asked again without it, and from now on
            payload.pop("output_config", None)
            data = _post(url, payload, headers, _hosted_timeout())
        else:
            raise
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
        "tokens_cached": _tokens_cached(usage), "cache_reported": _cache_reported(usage),
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
                  temperature: float | None = None, partial: bool = False, effort: str | None = None) -> dict:
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
    elif hosted and effort in CALL_EFFORTS and (base, model) not in _NO_EFFORT:
        # how long to think, from the work's risk (ModelSource): a thinking model's default is its most, which is
        # slow and spends the reply's room on reasoning (paid run 37589136743: cut-off replies, 3-5 minute calls)
        payload["reasoning_effort"] = effort
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
                if "reasoning_effort" in payload and re.search(r"HTTP (400|422)\b", str(exc)) \
                        and _EFFORT_REFUSED.search(str(exc)):
                    _NO_EFFORT.add(key)  # this provider does not take it: asked without it, now and from now on
                    payload.pop("reasoning_effort")
                    continue
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
    usage = data.get("usage") or {}
    if cut and not partial:
        raise _Truncated("reply truncated at max_tokens", {"tokens_in": int(usage.get("prompt_tokens") or 0),
                                                            "tokens_out": _tokens_out(usage),
                                                            "tokens_cached": _tokens_cached(usage),
                                                            "cache_reported": _cache_reported(usage)})
    out = {"text": choice["message"].get("content") or "", "tokens_in": int(usage.get("prompt_tokens") or 0),
           "tokens_out": _tokens_out(usage), "tokens_cached": _tokens_cached(usage),
           "cache_reported": _cache_reported(usage), "estimated": False, "truncated": cut}
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
        data = _post(base + "/chat/completions", payload, headers, _hosted_timeout())
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
            "tokens_out": _tokens_out(usage), "tokens_cached": _tokens_cached(usage),
            "cache_reported": _cache_reported(usage), "estimated": False, "truncated": cut}


# Claude through Claude Code on this computer (kind "claude_cli"): `claude -p`, Claude Code's print mode, the documented
# way to call Claude from a script, signed in as this computer's Claude Code is. Each call is the model alone: no tools,
# no MCP servers, no session kept, Cynqra's own short system prompt instead of Claude Code's, from an empty folder so no
# project file is read, and without the variables that would relay its output into the Claude Code session it runs
# beside. Tokens and cost are the CLI's own report (list prices), so nothing is estimated.
CLAUDE_CLI_SYSTEM = ("You are one member of a company's AI team, working through Cynqra. Answer the request exactly as "
                     "it asks, in the format it asks for. You have no tools: write everything in your reply.")
CLAUDE_CLI_RELAY_ENV = ("CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN",
                        "CLAUDE_CODE_POST_FOR_SESSION_INGRESS_V2", "CLAUDE_CODE_TEE_SDK_STDOUT",
                        "CLAUDE_CODE_REMOTE_SEND_KEEPALIVES", "CLAUDE_CODE_REMOTE_TOOLS_FORWARD",
                        "CLAUDE_CODE_SYNC_SESSION_REFS", "CLAUDE_CODE_SYNC_SKILLS", "CLAUDE_CODE_DIAGNOSTICS_FILE")
_CLAUDE_CLI_DIR: list = []


def claude_cli() -> str | None:
    """The claude command on this computer (CYNQRA_CLAUDE_CLI names another), or None when there is none."""
    import shutil
    named = (_ENV.get("CYNQRA_CLAUDE_CLI") or "").strip()
    if named:
        return named if os.path.isfile(named) or shutil.which(named) else None
    return shutil.which("claude")


def _claude_cli(prompt: str, model: str, max_tokens: int, partial: bool = False, effort: str | None = None) -> dict:
    import tempfile
    exe = claude_cli()
    if not exe:
        raise RuntimeError("Claude Code is not installed on this computer (no claude command)")
    if not _CLAUDE_CLI_DIR:
        _CLAUDE_CLI_DIR.append(tempfile.mkdtemp(prefix="cynqra_claude_"))  # empty: no project file is read
    key = ("claude_cli", model)
    cmd = [exe, "-p", "--no-session-persistence", "--tools", "", "--strict-mcp-config",
           "--system-prompt", CLAUDE_CLI_SYSTEM, "--model", model, "--output-format", "json"]
    if effort in CALL_EFFORTS and key not in _NO_EFFORT:
        cmd += ["--effort", effort]
    env = {k: v for k, v in os.environ.items() if k not in CLAUDE_CLI_RELAY_ENV}
    env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(max(int(max_tokens), HOSTED_MIN_REPLY))
    timeout = float(_ENV.get("CYNQRA_TIMEOUT") or TIMEOUT_S)
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, env=env,
                              cwd=_CLAUDE_CLI_DIR[0], check=False)
    except subprocess.TimeoutExpired as exc:
        raise _timed_out(timeout) from exc
    try:
        data = json.loads(proc.stdout or "")
    except ValueError:
        raise RuntimeError(f"Claude Code answered no result (exit {proc.returncode}): "
                           f"{(proc.stderr or proc.stdout or '').strip()[:300]}") from None
    if data.get("is_error"):
        why = str(data.get("result") or data.get("subtype") or "error")
        if "--effort" in cmd and "effort" in why.lower():
            _NO_EFFORT.add(key)  # this model takes no effort setting: asked again without it
            return _claude_cli(prompt, model, max_tokens, partial, None)
        raise RuntimeError(f"Claude Code: {why[:300]}")
    u = data.get("usage") or {}
    cached = int(u.get("cache_read_input_tokens") or 0)
    tin = int(u.get("input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0) + cached
    tout = int(u.get("output_tokens") or 0)
    cut = data.get("stop_reason") == "max_tokens"
    if cut and not partial:
        raise _Truncated(f"reply truncated at max_tokens={max(int(max_tokens), HOSTED_MIN_REPLY)}",
                         {"tokens_in": tin, "tokens_out": tout, "tokens_cached": cached, "cache_reported": True})
    served = next(iter(data.get("modelUsage") or {}), "") or model
    return {"text": str(data.get("result") or ""), "tokens_in": tin, "tokens_out": tout, "tokens_cached": cached,
            "cache_reported": True, "estimated": False, "truncated": cut,
            "usd_reported": round(float(data.get("total_cost_usd") or 0.0), 6), "served_model": served}


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


# --- record, replay and journal --------------------------------------------------------------------------------
# CYNQRA_CASSETTE names a file; CYNQRA_CASSETTE_MODE is "record" (every call's request and answer are kept there:
# the model, the prompt, the reply, its tokens and seconds; never a key, which travels only in headers, and anything
# shaped like one is scrubbed) or "replay" (calls are answered from the file, so a whole run can be tested again at
# no cost; a call the file does not hold fails, and is counted). Ids, times and people's names that differ between
# runs are normalized, so the same work finds the same answer. CYNQRA_REPLAY_SPEED replays at that fraction of the
# recorded time (0, the default: at once).
# A run's own journal (journal(), set by the engine for each call it makes) is the durable form: an answer the
# journal holds is used again, so a run reopened after a crash or a restart never pays twice for a call it already
# made; anything else is asked live and journaled. A failure is never journaled, so it is always asked again.
_CASSETTE_LOCK = threading.Lock()
_STORES: dict[str, dict] = {}
_VOLATILE = (
    (re.compile(r"\b(co|obj|org|plan|dec|sd|rep|ce|wp|v|cal)_[0-9a-f]{6,}\b"), r"\1_*"),
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?([+-]\d{2}:?\d{2}|Z)?"), "<time>"),
)


def _cassette_mode() -> str:
    return (os.environ.get("CYNQRA_CASSETTE_MODE") or "").strip().lower() if os.environ.get("CYNQRA_CASSETTE") else ""


def _route_of_calls() -> tuple[str, str | None]:
    """(mode, file) for this call: the process's record or replay, else the run's own journal, else nothing."""
    mode = _cassette_mode()
    if mode in ("record", "replay"):
        return mode, os.environ["CYNQRA_CASSETTE"]
    path = getattr(_LOCAL, "journal", None)
    return ("journal", path) if path else ("", None)


class journal:
    """with journal(path): the calls made on this thread are journaled in path (see above)."""

    def __init__(self, path):
        self.path, self.before = str(path) if path else None, None

    def __enter__(self):
        self.before = getattr(_LOCAL, "journal", None)
        _LOCAL.journal = self.path
        return self

    def __exit__(self, *exc):
        _LOCAL.journal = self.before
        return False


_PEOPLE: list = []


def _normalized(text: str) -> str:
    """The call as it would be in any run: the ids, times and people's names a run draws for itself (people.py
    draws a team's names per project) made the same, for matching only; the prompt sent is never changed."""
    if not _PEOPLE:
        from .people import FIRST, LAST
        _PEOPLE.append(re.compile(r"\b(?:" + "|".join(map(re.escape, FIRST)) + r")(?:\s+(?:"
                                  + "|".join(map(re.escape, LAST)) + r"))?\b"))
    for pattern, repl in _VOLATILE:
        text = pattern.sub(repl, text)
    return _PEOPLE[0].sub("<person>", text)


def cassette_key(kind: str, request: dict) -> str:
    import hashlib
    body = json.dumps({"kind": kind, **request}, sort_keys=True, default=str, ensure_ascii=False)  # "Tomás", not "Tom\u00e1s"
    return hashlib.sha256(_normalized(body).encode("utf-8")).hexdigest()


def _store(path: str) -> dict:
    """The recorded calls in a file, by key, loaded once."""
    if path not in _STORES:
        calls: dict[str, list] = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:  # a record cut off by a crash while it was written: not an answer
                        continue
                    if isinstance(row, dict) and row.get("key"):
                        calls.setdefault(row["key"], []).append(row)
        _STORES[path] = {"calls": calls, "used": {}, "hits": 0, "misses": 0}
    return _STORES[path]


def forget(path: str | None = None) -> None:
    """Drop what was loaded (all files, or one), as a new process would."""
    with _CASSETTE_LOCK:
        if path is None:
            _STORES.clear()
        else:
            _STORES.pop(str(path), None)


def cassette_stats(path: str | None = None) -> dict:
    path = str(path or os.environ.get("CYNQRA_CASSETTE") or "")
    s = _STORES.get(path) or {}
    return {"hits": s.get("hits", 0), "misses": s.get("misses", 0), "path": path or None}


def cassette_record(key: str, kind: str, label: str, answer, path: str | None = None) -> None:
    from .db import scrub
    row = {"key": key, "kind": kind, "label": label, "answer": answer}
    line = (scrub(json.dumps(row, default=str)) + "\n").encode("utf-8")
    with _CASSETTE_LOCK, open(path or os.environ["CYNQRA_CASSETTE"], "ab+") as f:
        f.seek(0, os.SEEK_END)
        if f.tell() > 0:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":  # the last record was cut off by a crash: this one starts on a line of its own
                line = b"\n" + line
        f.write(line)


def cassette_replay(key: str, path: str | None = None, keep_last: bool = True):
    """The recorded answer for a call, in the order they were recorded: a call asked twice gets the second answer
    the second time, then keeps the last (keep_last) or, for a journal, nothing (asked live). None when the file
    holds none."""
    with _CASSETTE_LOCK:
        c = _store(str(path or os.environ["CYNQRA_CASSETTE"]))
        rows = c["calls"].get(key) or []
        i = c["used"].get(key, 0)
        if not rows or (i >= len(rows) and not keep_last):
            c["misses"] += 1
            return None
        c["used"][key] = i + 1
        c["hits"] += 1
        return rows[min(i, len(rows) - 1)]["answer"]


def _replayed_or_recorded(call, prompt: str, max_tokens: int, want_json: bool, schema: dict | None,
                          temperature: float | None, partial: bool, effort: str | None) -> dict:
    mode, path = _route_of_calls()
    if not mode:
        return call()
    model = resolve() or {}
    label = str(model.get("label") or "")
    key = cassette_key("model_call", {"model": label, "prompt": prompt, "max_tokens": max_tokens,
                                      "want_json": want_json, "schema": schema, "temperature": temperature,
                                      "partial": partial, "effort": effort})
    if mode in ("replay", "journal"):
        answer = cassette_replay(key, path, keep_last=mode == "replay")
        if answer is not None:
            speed = float(os.environ.get("CYNQRA_REPLAY_SPEED") or 0) if mode == "replay" else 0.0
            if speed > 0:
                time.sleep(float(answer.get("latency_s") or 0) * speed)
            if mode == "replay":  # a replayed run meters every answer as it was recorded
                return {**{k: v for k, v in answer.items() if k != "call_uid"}, "journaled": False}
            return {**answer, "journaled": True}  # its call_uid says whether this run already charged it
        if mode == "replay":
            return {"text": "", "tokens_in": 0, "tokens_out": 0, "estimated": True, "latency_s": 0.0, "model": label,
                    "kind": model.get("kind"), "error": "RuntimeError: replay: the recording holds no answer for "
                                                        "this call (the prompt changed since it was recorded)"}
    out = call()
    if mode == "record" or not out.get("error"):  # a journal keeps answers only: a failure is asked again
        if not out.get("error"):
            import uuid
            out["call_uid"] = uuid.uuid4().hex  # one id per answer: metered and charged once (Engine.record_call)
        cassette_record(key, "model_call", label, out, path)
    return out


def complete(prompt: str, max_tokens: int = 1500, want_json: bool = False, schema: dict | None = None,
             temperature: float | None = None, partial: bool = False, route: dict | None = None,
             effort: str | None = None) -> dict:
    args = (prompt, max_tokens, want_json, schema, temperature, partial, effort)
    if route is None:
        return _replayed_or_recorded(lambda: _complete(*args), *args)
    before = getattr(_LOCAL, "route", None)
    _LOCAL.route = route
    try:
        if route.get("offline"):
            return {"text": "", "tokens_in": 0, "tokens_out": 0, "estimated": False, "latency_s": 0.0,
                    "model": route.get("label"), "kind": route.get("kind"),
                    "error": f"RuntimeError: {route.get('label')} is offline (a fault set on it in the model registry)"}
        return _replayed_or_recorded(lambda: _complete(*args), *args)
    finally:
        _LOCAL.route = before


def _complete(prompt: str, max_tokens: int, want_json: bool, schema: dict | None, temperature: float | None,
              partial: bool, effort: str | None = None) -> dict:
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
            out = _local_openai(prompt, model["label"], max_tokens, want_json, schema, temperature, partial, effort)
        elif model["kind"] == "hf":
            out = _hf(prompt, model["label"], max_tokens, want_json, schema, temperature, partial)
        elif model["kind"] == "openai":
            out = _openai(prompt, model["label"], max_tokens)
        elif model["kind"] == "claude_cli":
            out = _claude_cli(prompt, model["label"], max_tokens, partial, effort)
        else:
            out = _anthropic(prompt, model["label"], max_tokens, effort)
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
        billed = getattr(exc, "usage", None) or {}  # a cut-off reply's tokens are billed: kept, not zeroed
        out = {
            "text": "",
            "tokens_in": int(billed.get("tokens_in") or 0),
            "tokens_out": int(billed.get("tokens_out") or 0),
            "tokens_cached": int(billed.get("tokens_cached") or 0),
            "cache_reported": bool(billed.get("cache_reported")),
            "estimated": not billed,
            "error": f"{'RuntimeError' if isinstance(exc, _Truncated) else type(exc).__name__}: {exc}",
        }
    out["latency_s"] = round(time.time() - start, 3)
    out["model"] = model["label"]
    out["kind"] = model["kind"]
    return out
