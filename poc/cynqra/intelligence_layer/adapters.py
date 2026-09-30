"""Provider adapters: everything provider-specific about reaching intelligence, behind one interface.

    ProviderAdapter
    ├── OpenAICompatibleAdapter   OpenAI, and any server that speaks its chat completions (Hugging Face's router,
    │                             vLLM, LM Studio, llama-server on another machine)
    ├── AnthropicAdapter          Anthropic's Messages API
    ├── LocalInferenceAdapter     a model on this machine or a self-hosted one: the desktop app's llama-server,
    │                             Ollama, a local OpenAI-compatible endpoint, or a model command
    ├── DemoScriptAdapter         not a provider: a demo scenario's script, so a demo run is staffed like any run
    └── (Bedrock, later)          an adapter class and an entry in make_adapters(); nothing else changes

An adapter answers three questions for its provider type:

    discover(connection, secret)   which models the connection offers, with the facts the provider states
    reachable(connection, entry)   whether one of them can be reached now
    route(connection, secret, entry)  the provider-specific form of one call, for the transport
                                   (cynqra/model_adapter.py, the wire formats shared with the spikes)

Workers, the registry, the router and the bindings never see any of this.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .contracts import LOCAL_SERVERS, SETTINGS, SupplyError

# USD per million tokens, input and output: first-party list prices, checked 26 Sep 2026. A hosted model not listed
# is priced at the most expensive row unless its connection states a price, so a budget errs on the safe side.
LIST_PRICES = {
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-fable-5-1": (10.00, 50.00),
    "gpt-4o-mini": (0.15, 0.60),
}
WORST_PRICE = (10.00, 50.00)
# Provider types designed for but not built in V1. Listed so the product can say so; they cannot be connected.
PLANNED = {"bedrock": "AWS Bedrock (IAM authentication): planned after V1; it is an adapter added here"}
NOT_CHAT = ("embed", "tts", "whisper", "dall-e", "moderation", "image", "audio", "realtime", "transcribe", "search",
            "davinci", "babbage", "computer-use",
            # what a provider lists that cannot do a team member's work: video, music, speech, robotics, safety
            # filters, rerankers, parsers and detectors
            "veo", "lyria", "banana", "robotics", "-live", "translate", "aqa", "guard", "safety", "reward", "rerank",
            "parse", "detector", "calibration", "deplot", "kosmos", "clip", "riva", "cosmos", "neva", "vila", "fuyu",
            "retriever", "ocr", "asr", "speech", "customtools", "antigravity")
RECENT_DAYS = 365  # a model first listed within a year counts as current
_DATES: dict = {"at": 0.0, "url": None, "map": {}}
_TRIM = re.compile(r"-(instruct|it|chat|preview|latest|exp|v\d+(\.\d+)*|\d{2}-\d{4}|\d{4}-\d{2}-\d{2}|\d{8})$")


def model_key(ref: str) -> str:
    """A model's name without its vendor, provider suffix, "instruct"/"preview" tags or date stamps, so the same model
    matches across catalogues: models/gemini-3.8-flash and google/gemini-3.8-flash-preview are one model."""
    n = ref.lower().removeprefix("models/").split("/")[-1].split(":")[0]
    prev = None
    while prev != n:
        prev, n = n, _TRIM.sub("", n)
    return n


def release_dates() -> dict[str, float]:
    """When each model was first listed (Unix time), from OpenRouter's public catalogue: no key, open and closed
    models alike. Read at most once a day; unreachable, it is an empty map and nothing is judged by date.
    CYNQRA_MODEL_DATES_URL names another catalogue in the same format, or 0 for none."""
    url = os.environ.get("CYNQRA_MODEL_DATES_URL", "https://openrouter.ai/api/v1/models")
    if url in ("", "0"):
        return {}
    if _DATES["url"] == url and time.time() - _DATES["at"] < 86400:
        return _DATES["map"]
    try:
        data = _get_json(url, {}, timeout=15)
    except SupplyError:
        data = {}
    out: dict[str, float] = {}
    for x in (data.get("data") or []) if isinstance(data, dict) else []:
        if isinstance(x, dict) and x.get("id") and isinstance(x.get("created"), (int, float)):
            k = model_key(x["id"])
            out[k] = min(out.get(k, float("inf")), float(x["created"]))
    _DATES.update(at=time.time(), url=url, map=out)
    return out


def _family(ref: str) -> tuple[str, tuple]:
    """A model's family and version: gemini-3.8-flash is ("gemini-#-flash", (3, 8))."""
    k = model_key(ref)
    return re.sub(r"\d+(\.\d+)*", "#", k), tuple(float(x) for x in re.findall(r"\d+(?:\.\d+)?", k))


def dated(listing: dict[str, dict]) -> dict[str, float | None]:
    """When each listed model was released: the provider's own date when its dates are real (they differ from model
    to model), else the public catalogue's, else unknown."""
    own = {r: m.get("created") for r, m in listing.items() if isinstance(m.get("created"), (int, float))}
    real = len(set(own.values())) > max(1, len(own) // 4)
    pub = release_dates()
    return {r: (float(own[r]) if real and r in own else pub.get(model_key(r))) for r in listing}


def current(refs: list[str], when: dict[str, float | None]) -> list[str]:
    """The models worth offering: released within RECENT_DAYS, and only the newest version in each family. With no
    release date known for any of them, the newest version in each family."""
    cut = time.time() - RECENT_DAYS * 86400 if any(when.get(r) for r in refs) else None
    best: dict[str, tuple] = {}
    for r in refs:
        if cut is not None and (when.get(r) or 0) < cut:
            continue
        fam, ver = _family(r)
        if fam not in best or ver > best[fam][0]:
            best[fam] = (ver, r)
    return sorted(r for _, r in best.values())


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A call that carries a key never follows a redirect: urllib would send the key on to wherever it points."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _get_json(url: str, headers: dict, timeout: float = 30.0):
    req = urllib.request.Request(url, headers=headers)
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SupplyError(f"{url} answered HTTP {exc.code}: {exc.read()[:200].decode(errors='replace')}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SupplyError(f"could not reach {url}: {exc}") from exc


def _auth_headers(base: str, secret: str | None) -> dict:
    """Google takes its key in x-goog-api-key (its "AQ." keys are refused as a Bearer token); the rest take Bearer."""
    if not secret:
        return {}
    if (urllib.parse.urlparse(base).hostname or "").endswith(".googleapis.com"):
        return {"x-goog-api-key": secret}
    return {"Authorization": f"Bearer {secret}"}


def _allow(conn: dict) -> list[str]:
    return [m for m in conn.get("models") or [] if m]


def _price(conn: dict, ref: str) -> tuple[float, float]:
    if conn.get("price_per_m"):
        return tuple(float(x) for x in conn["price_per_m"])  # type: ignore[return-value]
    return LIST_PRICES.get(ref, WORST_PRICE)


HOSTED_TIMEOUT_S = 1200  # a free hosted endpoint can write at 10 tokens/s (Kimi K3 on NVIDIA); after 20 min it is stuck


def _hosted(route: dict, conn: dict) -> dict:
    """A hosted provider's call gives up after HOSTED_TIMEOUT_S unless its connection (or, for a connection made
    from the environment, the environment) sets CYNQRA_TIMEOUT; the call then fails like any provider error, and
    the retry and the Replacement Engine take over."""
    env = os.environ.get("CYNQRA_TIMEOUT") if conn.get("origin") == "environment" else None
    route["CYNQRA_TIMEOUT"] = route.get("CYNQRA_TIMEOUT") or env or str(HOSTED_TIMEOUT_S)
    return route


def _settings(conn: dict) -> dict:
    """A founder's connection carries its own provider options; everything else is unset for its calls, so one
    connection's options never reach another's. A connection made from the environment keeps the environment's."""
    if conn.get("origin") == "environment":
        return {}
    given = conn.get("settings") or {}
    return {k: (str(given[k]) if given.get(k) not in (None, "") else None) for k in SETTINGS}


class ProviderAdapter:
    type = ""
    title = ""
    auth_methods: tuple = ("api_key",)

    def normalize(self, spec: dict) -> dict:
        """Check and complete a connection spec for this provider."""
        return spec

    def discover(self, conn: dict, secret: str | None) -> list[dict]:
        raise NotImplementedError

    def reachable(self, conn: dict, entry: dict) -> tuple[bool, str]:
        return True, "available"

    def route(self, conn: dict, secret: str | None, entry: dict) -> dict:
        raise NotImplementedError

    def environment_specs(self, primary: dict | None) -> list[dict]:
        """Connections for what the process environment names for this provider type."""
        return []

    def describe(self) -> dict:
        return {"type": self.type, "title": self.title, "auth_methods": list(self.auth_methods), "implemented": True}


class OpenAICompatibleAdapter(ProviderAdapter):
    type = "openai_compatible"
    title = "OpenAI-compatible API"
    auth_methods = ("api_key", "none")
    DEFAULT = "https://api.openai.com/v1"

    def normalize(self, spec: dict) -> dict:
        ep = (spec.get("endpoint") or "").strip().rstrip("/")
        if ep and not ep.startswith(("http://", "https://")):
            raise SupplyError("the endpoint must be an http or https URL, such as https://api.openai.com/v1")
        spec["endpoint"] = ep
        return spec

    @staticmethod
    def _host(conn: dict) -> str:
        return urllib.parse.urlparse(conn.get("endpoint") or OpenAICompatibleAdapter.DEFAULT).hostname or ""

    FLAVORS = {"router.huggingface.co": "hf", "api.openai.com": "openai"}

    @classmethod
    def flavor(cls, conn: dict) -> str:
        """Which OpenAI-compatible API this is: Hugging Face's router, OpenAI's, or any other server. The endpoint's
        host says so, unless the connection names it (an HF router reached through a proxy or mirror)."""
        return (conn.get("metadata") or {}).get("flavor") or cls.FLAVORS.get(cls._host(conn), "server")

    def discover(self, conn: dict, secret: str | None) -> list[dict]:
        allow = _allow(conn)
        hf = self.flavor(conn) == "hf"
        listing: dict[str, dict] = {}
        if not allow or hf:
            base = conn.get("endpoint") or self.DEFAULT
            try:
                data = _get_json(base + "/models", _auth_headers(base, secret))
                # Google lists "models/gemini-..."; its chat route takes the name without the prefix
                listing = {m["id"].removeprefix("models/"): m for m in (data.get("data") or [])
                           if isinstance(m, dict) and m.get("id")}
            except SupplyError:
                if not allow:
                    raise
                # the founder named the models: they are registered, priced at the safe default, and the
                # connection's status says the listing could not be read
                conn["_listing_note"] = "the model listing could not be read; stated models priced at the safe default"
        chat = [i for i in listing if not any(x in i.lower() for x in NOT_CHAT)]
        when = dated({r: listing[r] for r in chat}) if chat and not hf else {}
        if allow or hf or conn.get("_all"):
            refs = allow or chat
        else:
            # nothing named: the models released within a year, newest of each family; the rest stay searchable
            refs = current(chat, when)
            older = len(chat) - len(refs)
            if not any(when.values()):
                conn["_listing_note"] = ("release dates could not be read, so the newest version of each model "
                                         "family is offered; search the list to change it")
            elif older:
                conn["_listing_note"] = f"{older} older or duplicate model(s) left out; search the list to add one"
        out, unavailable = [], []
        for ref in refs:
            facts = {"ref": ref, "name": ref, "provider": self._host(conn), "runtime": "openai_compatible_api",
                     "local": False, "modalities": ["text"], "json_schema": True, "tools": True,
                     "released": when.get(ref)}
            if hf and listing:
                try:
                    facts.update(self._hf(ref, listing, (conn.get("_served_by") or {}).get(ref)))
                except SupplyError as exc:  # listed, or named, but no provider serves it now: not offered
                    unavailable.append(str(exc))
                    continue
            elif hf:
                facts["price_in"], facts["price_out"] = _price(conn, ref)
            else:
                facts["price_in"], facts["price_out"] = _price(conn, ref)
            out.append(facts)
        if unavailable:
            note = f"{len(unavailable)} not offered now ({'; '.join(unavailable[:3])}{'; ...' if len(unavailable) > 3 else ''})"
            conn["_listing_note"] = "; ".join(x for x in (conn.get("_listing_note"), note) if x)
        if allow and not out:
            raise SupplyError("none of the named models is offered: " + "; ".join(unavailable))
        return out

    @staticmethod
    def _hf(ref: str, listing: dict, keep: str | None = None) -> dict:
        """Hugging Face's router is an aggregator: it lists each model's live providers (the companies serving it)
        with their price and context. The one named after ':' in ref; else the one already serving it (keep), while
        it is live, so the measured record stays that company's; else the cheapest live one with structured output.
        The call names it (route), so what is measured and billed is what was chosen."""
        base, _, want = ref.partition(":")
        entry = listing.get(base)
        if entry is None:
            raise SupplyError(f"{base} is not offered by Hugging Face Inference Providers")
        live = [p for p in entry.get("providers") or [] if p.get("status") == "live"]
        if want:
            live = [p for p in live if p.get("provider") == want]
        elif keep and any(p.get("provider") == keep for p in live):
            live = [p for p in live if p.get("provider") == keep]
        if not live:
            raise SupplyError(f"{ref}: no live provider")
        p = min(live, key=lambda p: (not p.get("supports_structured_output"),
                                     (p.get("pricing") or {}).get("input", 1e9)))
        pr = p.get("pricing") or {}
        return {"name": ref, "provider": p.get("provider") or "", "served_by": p.get("provider") or "",
                "context": int(p.get("context_length") or 0),
                "price_in": float(pr.get("input") or WORST_PRICE[0]), "price_out": float(pr.get("output") or WORST_PRICE[1]),
                "json_schema": bool(p.get("supports_structured_output")), "tools": bool(p.get("supports_tools"))}

    def route(self, conn: dict, secret: str | None, entry: dict) -> dict:
        ep, flavor = conn.get("endpoint") or "", self.flavor(conn)
        r = {"label": entry["ref"], "local": False, **_settings(conn)}
        if flavor == "hf":
            sb = entry.get("served_by")
            if sb and ":" not in entry["ref"]:  # pinned to the company whose price and record Cynqra holds
                r["label"] = f"{entry['ref']}:{sb}"
            r.update({"kind": "hf", "HF_TOKEN": secret, **({"HF_ROUTER_URL": ep} if ep else {})})
            _hosted(r, conn)
        elif flavor == "openai":
            r.update({"kind": "openai", "OPENAI_API_KEY": secret,
                      **({"CYNQRA_OPENAI_URL": ep + "/chat/completions"} if ep else {})})
            _hosted(r, conn)
        else:
            r.update({"kind": "local", "CYNQRA_LOCAL_BASE_URL": ep, "CYNQRA_LOCAL_API_KEY": secret})
        return r

    def environment_specs(self, primary: dict | None) -> list[dict]:
        out = []
        if os.environ.get("HF_TOKEN") and os.environ.get("CYNQRA_HF_MODEL"):
            out.append({"type": self.type, "name": "Hugging Face (environment)",
                        "endpoint": (os.environ.get("HF_ROUTER_URL") or "https://router.huggingface.co/v1").rstrip("/"),
                        "auth": {"method": "env", "env_var": "HF_TOKEN"}, "models": [os.environ["CYNQRA_HF_MODEL"]],
                        "metadata": {"flavor": "hf"}, **(_env_price())})
        if os.environ.get("OPENAI_API_KEY"):
            label = primary["label"] if primary and primary["kind"] == "openai" else "gpt-4o-mini"
            out.append({"type": self.type, "name": "OpenAI (environment)", "endpoint": "",
                        "auth": {"method": "env", "env_var": "OPENAI_API_KEY"}, "models": [label], **(_env_price())})
        return out


class AnthropicAdapter(ProviderAdapter):
    type = "anthropic"
    title = "Anthropic API"
    DEFAULT = "https://api.anthropic.com"
    VERSION = "2023-06-01"

    def normalize(self, spec: dict) -> dict:
        ep = (spec.get("endpoint") or "").strip().rstrip("/")
        if ep.endswith("/v1"):
            ep = ep[:-3]
        if ep and not ep.startswith(("http://", "https://")):
            raise SupplyError("the endpoint must be an http or https URL, such as https://api.anthropic.com")
        spec["endpoint"] = ep
        return spec

    def discover(self, conn: dict, secret: str | None) -> list[dict]:
        allow = _allow(conn)
        names: dict[str, str] = {}
        if not allow:
            data = _get_json((conn.get("endpoint") or self.DEFAULT) + "/v1/models?limit=100",
                             {"x-api-key": secret or "", "anthropic-version": self.VERSION})
            names = {m["id"]: m.get("display_name") or m["id"] for m in data.get("data") or [] if m.get("id")}
        out = []
        for ref in allow or list(names):
            pin, pout = _price(conn, ref)
            out.append({"ref": ref, "name": names.get(ref, ref), "provider": "Anthropic", "runtime": "anthropic_api",
                        "local": False, "price_in": pin, "price_out": pout, "modalities": ["text", "image"],
                        "json_schema": True, "tools": True, "mcp": True})
        return out

    def route(self, conn: dict, secret: str | None, entry: dict) -> dict:
        ep = conn.get("endpoint") or ""
        return _hosted({"kind": "anthropic", "label": entry["ref"], "local": False, "ANTHROPIC_API_KEY": secret,
                        **({"CYNQRA_ANTHROPIC_URL": ep + "/v1/messages"} if ep else {}), **_settings(conn)}, conn)

    def environment_specs(self, primary: dict | None) -> list[dict]:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return []
        label = primary["label"] if primary and primary["kind"] == "anthropic" else "claude-sonnet-5"
        return [{"type": self.type, "name": "Anthropic (environment)", "endpoint": "",
                 "auth": {"method": "env", "env_var": "ANTHROPIC_API_KEY"}, "models": [label], **(_env_price())}]


class LocalInferenceAdapter(ProviderAdapter):
    """Intelligence not behind a proprietary API: a model on this machine or a self-hosted server."""
    type = "local"
    title = "Local / self-hosted inference"
    auth_methods = ("none", "api_key")

    def __init__(self, runtime=None):
        self.runtime = runtime  # the desktop app's llama-server manager (cynqra/runtime.py)

    def normalize(self, spec: dict) -> dict:
        server = spec.get("server") or ("llama" if not spec.get("endpoint") else "endpoint")
        if server not in LOCAL_SERVERS:
            raise SupplyError(f"a local connection's server is one of {', '.join(LOCAL_SERVERS)}")
        if server == "llama" and self.runtime is None and spec.get("origin") != "environment":
            raise SupplyError("models on this machine are managed by the desktop app")
        if server == "endpoint" and spec.get("origin") != "environment" and not str(spec.get("endpoint") or "").startswith(
                ("http://", "https://")):
            raise SupplyError("a local endpoint needs its URL, such as http://127.0.0.1:8080/v1")
        spec["server"] = server
        spec["endpoint"] = (spec.get("endpoint") or "").strip().rstrip("/")
        return spec

    def discover(self, conn: dict, secret: str | None) -> list[dict]:
        server, allow, ep = conn["server"], _allow(conn), conn.get("endpoint") or ""
        rate = float(conn.get("machine_usd_per_hour") or 0)
        base = {"local": True, "price_in": 0.0, "price_out": 0.0, "compute_usd_per_hour": rate,
                "hardware": "this machine", "modalities": ["text"], "json_schema": True, "tools": False}
        if server == "llama":
            from ..runtime import CATALOG
            refs = allow or [m["id"] for m in CATALOG if not m.get("hidden")]
            out = []
            for ref in refs:
                c = next((m for m in CATALOG if m["id"] == ref), None)
                if c is None:
                    raise SupplyError(f"{ref} is not in the desktop app's model catalog")
                out.append({**base, "ref": ref, "name": c["name"], "provider": ref.split("-")[0].capitalize(),
                            "runtime": "llama.cpp", "context": c["ctx"], "size_gb": c.get("size_gb"),
                            "hardware": f"this machine, {c['min_gb']} GB of memory or more",
                            "license": c.get("license", ""), "predict": c["predict"], "think": c["think"]})
            return out
        if server == "ollama":
            if not allow:
                host = ep or "http://" + (os.environ.get("OLLAMA_HOST") or "127.0.0.1:11434").replace("http://", "")
                allow = [m["name"] for m in _get_json(host.rstrip("/") + "/api/tags", {}).get("models") or []]
            return [{**base, "ref": r, "name": r, "provider": "Ollama", "runtime": "ollama"} for r in allow]
        if server == "endpoint":
            if not allow:
                data = _get_json(ep + "/models", {"Authorization": f"Bearer {secret}"} if secret else {})
                allow = [m["id"] for m in data.get("data") or [] if m.get("id")]
            return [{**base, "ref": r, "name": r, "provider": "self-hosted", "runtime": "openai_compatible_server"}
                    for r in allow]
        refs = allow or ["model command"]  # a command: one model, whatever the command runs; tokens are estimated
        return [{**base, "ref": r, "name": r, "provider": "command", "runtime": "command", "hardware": "a command"}
                for r in refs]

    def reachable(self, conn: dict, entry: dict) -> tuple[bool, str]:
        if conn.get("server") != "llama":
            return True, "available"
        rt = self.runtime
        if rt is None:
            return False, "no model runtime in this process"
        if not rt.installed(entry["ref"]):
            return False, "not downloaded on this machine"
        if not rt.servers:
            return False, "llama-server is missing"
        return True, "available"

    def route(self, conn: dict, secret: str | None, entry: dict) -> dict:
        server, ep = conn["server"], conn.get("endpoint") or ""
        r = {"label": entry["ref"], "local": True, **_settings(conn)}
        if server == "llama":
            base = self._serve(entry["ref"])
            r.update({"kind": "local", "label": entry["name"], "CYNQRA_LOCAL_BASE_URL": base + "/v1",
                      "CYNQRA_LOCAL_API_KEY": None, "CYNQRA_TEMPERATURE": r.get("CYNQRA_TEMPERATURE") or "0",
                      "CYNQRA_SEED": r.get("CYNQRA_SEED") or "42",
                      "CYNQRA_NUM_PREDICT": r.get("CYNQRA_NUM_PREDICT") or str(entry.get("predict") or 8192),
                      "CYNQRA_THINK": r.get("CYNQRA_THINK") or entry.get("think") or None})
        elif server == "ollama":
            r.update({"kind": "ollama", **({"OLLAMA_HOST": ep.replace("http://", "")} if ep else {})})
        elif server == "endpoint":
            r.update({"kind": "local", **({"CYNQRA_LOCAL_BASE_URL": ep} if ep else {}), "CYNQRA_LOCAL_API_KEY": secret})
        else:
            r.update({"kind": "cmd", **({"CYNQRA_S1_MODEL_CMD": ep} if ep else {})})
        return r

    def _serve(self, ref: str) -> str:
        """One llama-server serves one model: this one is started if another is loaded (a swap takes seconds)."""
        from ..runtime import ModelRuntimeError
        rt = self.runtime
        if rt is None:
            raise SupplyError("no model runtime in this process")
        try:
            with rt.lock:
                if rt.status.get("model") == ref and rt.status.get("state") == "ready" and rt.base:
                    return rt.base
                rt.stop()
                return rt.start(ref)
        except ModelRuntimeError as exc:
            raise SupplyError(f"the model on this machine could not start: {exc}") from exc

    def environment_specs(self, primary: dict | None) -> list[dict]:
        out = []
        if os.environ.get("CYNQRA_S1_MODEL_CMD"):
            out.append({"type": self.type, "server": "command", "name": "Model command (environment)",
                        "auth": {"method": "none"}, "models": ["shell command"]})
        if os.environ.get("CYNQRA_OLLAMA_MODEL"):
            out.append({"type": self.type, "server": "ollama", "name": "Ollama (environment)",
                        "auth": {"method": "none"}, "models": [os.environ["CYNQRA_OLLAMA_MODEL"]]})
        if os.environ.get("CYNQRA_LOCAL_BASE_URL"):
            key = {"method": "env", "env_var": "CYNQRA_LOCAL_API_KEY"} if os.environ.get("CYNQRA_LOCAL_API_KEY") \
                else {"method": "none"}
            out.append({"type": self.type, "server": "endpoint", "name": "Local server (environment)", "auth": key,
                        "models": [os.environ.get("CYNQRA_MODEL") or "local-model"]})
        return out


class DemoScriptAdapter(ProviderAdapter):
    """A demo scenario's prepared script. It stands in a demo run's own registry so the demo is staffed, bound and
    metered like any run, but it is not a provider: nobody connects it, and the Gateway never calls it (the
    scripted source answers the demo's questions itself, and every word is labelled as scripted)."""
    type = "demo_script"
    title = "Demo script (not a provider)"
    auth_methods = ("none",)

    def normalize(self, spec: dict) -> dict:
        if spec.get("origin") != "demo":
            raise SupplyError("a demo script is not a provider; it exists only in a demo run")
        return spec

    def discover(self, conn: dict, secret: str | None) -> list[dict]:
        return [{"ref": s, "name": f"Scripted demo ({s})", "provider": "Cynqra demo script", "runtime": "scripted",
                 "local": True, "price_in": 0.0, "price_out": 0.0, "hardware": "no model", "license": "not a model"}
                for s in _allow(conn)]

    def route(self, conn: dict, secret: str | None, entry: dict) -> dict:
        raise SupplyError("the demo script answers the demo's questions itself; it takes no calls")

    def describe(self) -> dict:
        return {**super().describe(), "connectable": False}


def _env_price() -> dict:
    try:
        return {"price_per_m": [float(x) for x in os.environ["CYNQRA_PRICE_PER_M"].split(",")][:2]}
    except (KeyError, ValueError):
        return {}


class Adapters(dict):
    """The provider types this installation can connect, by type."""

    def environment_specs(self) -> list[dict]:
        from .. import model_adapter
        primary = model_adapter.resolve()
        return [s for a in self.values() for s in a.environment_specs(primary)]


def make_adapters(runtime=None) -> Adapters:
    return Adapters({a.type: a for a in (OpenAICompatibleAdapter(), AnthropicAdapter(), LocalInferenceAdapter(runtime),
                                         DemoScriptAdapter())})


def adapter_types() -> list[dict]:
    """The provider types a founder can connect, and the ones planned."""
    return [a.describe() for a in make_adapters().values() if a.describe().get("connectable", True)] + [
        {"type": t, "title": note.split(" (")[0], "note": note, "implemented": False} for t, note in PLANNED.items()]
