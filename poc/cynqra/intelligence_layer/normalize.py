"""Discovery normalized into the Intelligence Registry: what a provider lists becomes an intelligence Cynqra understands.

Three things are kept apart, because they are different facts:

  access provider   the connection it is reached through and paid for (NVIDIA Build, Google Gemini API, a laptop)
  publisher         the organization that made the model (Moonshot AI, Google, NVIDIA, Z.ai)
  model             the intelligence itself (Kimi K3)

One model can be reached through several access providers; Google can be both publisher and access provider.

Where each fact comes from, in order: the provider's own listing; a public model catalogue (OpenRouter's, read at most
once a day, no key: names, publishers, descriptions, input types, supported features, context, list prices, release
dates, for open and closed models alike); and what the model's own name says (its publisher's prefix, "coder",
"flash"). Nothing comes from a list written into Cynqra. What Cynqra measures on its own work (success, speed, cost)
is kept by the registry beside these facts and always outranks them.
"""
from __future__ import annotations

import os
import re
import time
import urllib.parse

CATALOGUE_URL = "https://openrouter.ai/api/v1/models"
_CACHE: dict = {"at": 0.0, "url": None, "map": {}}
_TRIM = re.compile(r"-(instruct|it|chat|preview|latest|exp|v\d+(\.\d+)*|\d{2}-\d{4}|\d{4}-\d{2}-\d{2}|\d{8})$")
# first-party APIs: the host is the publisher when the listing gives no prefix
HOST_PUBLISHER = {"generativelanguage.googleapis.com": "google", "api.anthropic.com": "anthropic",
                  "api.openai.com": "openai", "api.mistral.ai": "mistralai", "api.z.ai": "z-ai",
                  "api.deepseek.com": "deepseek", "api.moonshot.ai": "moonshotai",
                  "api.llama.com": "meta-llama"}
FAST_WORDS = ("flash", "lite", "lightning", "nano", "mini", "turbo", "fast", "instant", "haiku", "small")
CODE_WORDS = ("coder", "codestral", "devstral", "code")
LONG_CONTEXT = 200_000


def model_key(ref: str) -> str:
    """A model's name without its publisher, provider suffix, "instruct"/"preview" tags or date stamps, so one model
    matches across catalogues: models/gemini-3.8-flash and google/gemini-3.8-flash-preview are one model."""
    n = ref.lower().removeprefix("models/").split("/")[-1].split(":")[0]
    prev = None
    while prev != n:
        prev, n = n, _TRIM.sub("", n)
    return n


def catalogue() -> dict[str, dict]:
    """The public catalogue by model_key. Unreachable, it is empty and every fact comes from the provider and the
    name. CYNQRA_MODEL_DATES_URL names another catalogue in the same format, or 0 for none."""
    from .adapters import _get_json, SupplyError
    url = os.environ.get("CYNQRA_MODEL_DATES_URL", CATALOGUE_URL)
    if url in ("", "0"):
        return {}
    if _CACHE["url"] == url and time.time() - _CACHE["at"] < 86400:
        return _CACHE["map"]
    try:
        data = _get_json(url, {}, timeout=15)
    except SupplyError:
        data = {}
    out: dict[str, dict] = {}
    for x in (data.get("data") or []) if isinstance(data, dict) else []:
        if isinstance(x, dict) and x.get("id"):
            k = model_key(x["id"])
            if k not in out or (x.get("created") or 9e12) < (out[k].get("created") or 9e12):
                out[k] = x
    _CACHE.update(at=time.time(), url=url, map=out)
    return out


def _pretty(slug: str) -> str:
    """nemotron-3.5-lightning-30b-a3b -> Nemotron 3.5 Lightning 30B A3B; kimi-k3 -> Kimi K3"""
    return " ".join(w.upper() if re.fullmatch(r"\d+(\.\d+)?[bkm]|a\d+b", w) else w[:1].upper() + w[1:]
                    for w in re.split(r"[-_ ]+", slug) if w)


def _per_million(v) -> float | None:
    try:
        return round(float(v) * 1_000_000, 4)
    except (TypeError, ValueError):
        return None


def describe(ref: str, facts: dict, host: str) -> dict:
    """The normalized facts of one discovered model."""
    rec = catalogue().get(model_key(ref)) or {}
    publisher = ref.split("/")[0].lower() if "/" in ref and not ref.startswith("models/") else ""
    if not publisher:
        publisher = HOST_PUBLISHER.get(host, "") or (rec.get("id", "").split("/")[0] if "/" in rec.get("id", "") else "")
    rname = str(rec.get("name") or "")
    pub_name, _, model_name = rname.partition(": ") if ": " in rname else ("", "", rname)
    base = ref.removeprefix("models/").split("/")[-1]
    name = facts.get("name") if facts.get("name") and facts.get("name") != ref else (model_name or _pretty(base))
    arch = rec.get("architecture") or {}
    inputs = [m for m in (arch.get("input_modalities") or facts.get("modalities") or ["text"]) if m]
    params = set(rec.get("supported_parameters") or [])
    desc = re.sub(r"\s+", " ", str(rec.get("description") or "")).strip()[:900]
    text = f"{ref} {model_name} {desc}".lower()
    context = int(facts.get("context") or rec.get("context_length") or (rec.get("top_provider") or {}).get(
        "context_length") or 0)
    caps = []
    if "reasoning" in params or "include_reasoning" in params or re.search(r"\breason", text):
        caps.append("reasoning")
    if any(w in base.lower() for w in CODE_WORDS) or re.search(r"\bcod(e|ing)\b", desc.lower()):
        caps.append("coding")
    if "tools" in params or "tool_choice" in params:
        caps.append("tool use")
    if re.search(r"\bagent", text):
        caps.append("agentic")
    if "structured_outputs" in params or "response_format" in params:
        caps.append("structured output")
    if context >= LONG_CONTEXT:
        caps.append("long context")
    if any(m != "text" for m in inputs):
        caps.append("multimodal")
    if "image" in inputs:
        caps.append("vision")
    if re.search(r"\bocr\b|document|pdf", text) and "image" in inputs:
        caps.append("document reading")
    fast = any(re.search(rf"(^|[-_ ]){w}($|[-_ ])", base.lower()) for w in FAST_WORDS)
    kind = ("Coding" if "coding" in caps and any(w in base.lower() for w in CODE_WORDS) else
            "Reasoning / Agentic" if "reasoning" in caps and "agentic" in caps else
            "Agentic" if "agentic" in caps else "Reasoning" if "reasoning" in caps else
            "Multimodal" if "multimodal" in caps else "General")
    price = rec.get("pricing") or {}
    return {"display_name": name, "publisher": publisher, "publisher_name": pub_name or _pretty(publisher) if publisher else "",
            "capabilities": caps, "input_modalities": inputs, "type": kind, "speed": "fast" if fast else "",
            "context": context or None, "description": desc,
            "max_output": int((rec.get("top_provider") or {}).get("max_completion_tokens") or 0) or None,
            "list_price_in": _per_million(price.get("prompt")), "list_price_out": _per_million(price.get("completion")),
            "released": facts.get("released") or (float(rec["created"]) if isinstance(rec.get("created"), (int, float))
                                                  else None),
            "catalogued": bool(rec)}


def host_of(endpoint: str) -> str:
    return (urllib.parse.urlparse(endpoint or "").hostname or "").lower()
