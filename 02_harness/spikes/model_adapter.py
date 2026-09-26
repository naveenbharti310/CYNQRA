"""One way for every spike to reach a model, and one way to count tokens.

Order of resolution:
  1. CYNQRA_S1_MODEL_CMD  a shell command, prompt on stdin, text on stdout
  2. OPENAI_API_KEY
  3. ANTHROPIC_API_KEY
  4. nothing, and the spikes refuse to score

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


def _post_once(url: str, body: bytes, headers: dict) -> dict:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
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


def _post(url: str, payload: dict, headers: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    for wait in RETRY_WAITS_S + (None,):
        try:
            return _post_once(url, body, headers)
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


def complete(prompt: str, max_tokens: int = 1500) -> dict:
    """Returns text, tokens_in, tokens_out, estimated, latency_s, error.

    max_tokens defaults to 1500, the S1 setting. S2 passes a larger value
    because workers return code and tests inside one protocol object.
    """
    model = resolve()
    if model is None:
        raise RuntimeError("No model. Set CYNQRA_S1_MODEL_CMD, OPENAI_API_KEY, or ANTHROPIC_API_KEY.")
    start = time.time()
    try:
        if model["kind"] == "cmd":
            out = _cmd(prompt)
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
