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


def _post(url: str, payload: dict, headers: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise RuntimeError(f"HTTP {exc.code} from provider: {detail}") from exc


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
    usage = data.get("usage") or {}
    return {
        "text": (data["choices"][0]["message"]["content"] or ""),
        "tokens_in": int(usage.get("prompt_tokens") or 0),
        "tokens_out": int(usage.get("completion_tokens") or 0),
        "estimated": False,
    }


def _anthropic(prompt: str, model: str, max_tokens: int = 1500) -> dict:
    data = _post(
        ANTHROPIC_URL,
        {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        },
        {
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
    )
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    usage = data.get("usage") or {}
    return {
        "text": "".join(parts),
        "tokens_in": int(usage.get("input_tokens") or 0),
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
