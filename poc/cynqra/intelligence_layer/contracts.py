"""The supply subsystem's contract: its four records, the call it executes, and the errors it raises.

Everything outside cynqra/supply works with these shapes through IntelligenceSupply, the registry, the gateway and
the adapters' interface; nothing reads the subsystem's tables directly. They are the API a standalone service
would expose.

CREDENTIAL (credentials.py) authorizes a connection
    id, method ("env": the name of an environment variable; "secret": a value in the secrets file; "none"), env_var,
    label, created_at. The secret value is never in a record, an event, a response or an export.

PROVIDER CONNECTION (connections.py) how Cynqra may reach a provider
    id, type (a provider type: adapters.adapter_types()), name, endpoint, auth_method ("api_key" or "none"),
    credential_id, account, region, server (local: "llama", "ollama", "endpoint" or "command"), models (an optional
    allow list), settings (provider options, such as a reasoning effort), machine_usd_per_hour (local), rate_limits,
    status ("new", "connected", "error"), status_note, permission, offered (the models discovered), origin
    ("founder", "environment", "app", "demo"), created_at, checked_at, metadata.

INTELLIGENCE (registry.py) what an intelligence is and how well it performs
    id, name, provider, ref (the provider's own model name), connection_id, runtime, version, context, tools,
    json_schema, modalities, mcp, local, price_in, price_out (USD per million tokens), compute_usd_per_hour,
    license, commercial_use, params, hardware, fallback_id, status ("active", "retired"), status_note, fault,
    health, regression {status, version, at, evidence}, source ("discovered", "registered"), registered_at.
    Measured: every call (tokens, seconds, dollars, speed, error) and every verified or rejected attempt (task
    kind, attempt, cost, time, failure); derived: stats and profile (success, first pass, cost, latency,
    throughput, reliability, benchmark, by version).

WORKER INTELLIGENCE BINDING (cynqra/binding.py, in each run, not in this subsystem)
    worker_id, intelligence_id, version (pinned), reason, by, candidates, bound_at, history.

REQUEST (gateway.invoke)
    prompt, max_tokens, want_json, schema, temperature, partial
RESPONSE
    text, tokens_in, tokens_out, estimated, latency_s, error (None or the reason), truncated, model (the label),
    model_id (the intelligence id), and the provider's speed figures when it reports them.
"""
from __future__ import annotations


class SupplyError(ValueError):
    """A supply operation that cannot be done: an unknown provider type, a bad connection, a missing credential."""


AUTH_METHODS = ("api_key", "none")  # OAuth and IAM arrive with the adapters that need them (Bedrock: IAM)
CREDENTIAL_METHODS = ("env", "secret", "none")
LOCAL_SERVERS = ("llama", "ollama", "endpoint", "command")
REQUEST_KEYS = ("prompt", "max_tokens", "want_json", "schema", "temperature", "partial")
# Provider options a connection may set; everything else a call needs comes from the adapter.
SETTINGS = ("CYNQRA_EFFORT", "CYNQRA_THINK", "CYNQRA_NUM_PREDICT", "CYNQRA_NUM_CTX", "CYNQRA_TEMPERATURE",
            "CYNQRA_SEED", "CYNQRA_TIMEOUT", "CYNQRA_KEEP_ALIVE")
