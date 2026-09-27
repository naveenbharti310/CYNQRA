# Cynqra's intelligence supply (V1)

This file maps the product owner's locked V1 decisions ("Intelligence Supply Architecture V1 implementation
decisions", 27 September 2026) to the code in `poc/`. Each decision has one place in the code, and a test holds
it. What is designed for but not built is marked as such.

```
                         CYNQRA (control plane)
        ┌───────────────────────────┬──────────────────────────────────────────────┐
        │ Workforce Engine          │ Intelligence Layer   cynqra/intelligence_layer/ │
        │  workers: identity, role, │  Intelligence Registry   registry.py            │
        │  authority, history       │  Intelligence Router     router.py              │
        │  bindings   binding.py    │  Provider Connections    connections.py         │
        │                           │  Credentials (secrets)   credentials.py         │
        └─────────────┬─────────────┴──────────────────────────────────────────────┘
                      │ worker's call: (intelligence id, request)
                Intelligence Gateway   gateway.py: entry, connection, credential for this call only
                      │
                Provider adapters      adapters.py
          OpenAI-compatible    Anthropic    Local / self-hosted    [AWS Bedrock: designed for, later]
```

## The four records are separate

**Worker ≠ intelligence ≠ provider connection ≠ credential.**

| Record | Holds | Never holds | Where |
| --- | --- | --- | --- |
| Worker | identity, role, authority, reporting line, tasks, history | a model, a key | the run's store (`worker`) |
| Binding | which intelligence powers the worker now, the pinned version, the Router's table, every earlier binding | a key | the run's store (`binding`), `cynqra/binding.py` |
| Intelligence | the facts its provider gives (ref, version, context, price, licence) and what Cynqra measured | a key, a URL | the control store (`intelligence`), `registry.py` |
| Provider connection | type, endpoint, auth method, a reference to its credential, models to offer, rate limit, options | the secret | the control store (`connection`), `connections.py` |
| Credential | how to get the secret: an environment variable's name, a key in the secrets file, or none | (it is the secrets layer) | `root/secrets/credentials.json`, mode 0600; `credentials.py` |

The Intelligence Layer is a package inside the control plane, with its own schema and contracts
(`contracts.py`). It is not a network service in V1. Its records live in Cynqra's existing store (`db.py`),
in the control database `control/control.db` beside the runs, so what is measured on one project carries over to
the next.

## The flow

1. **Connect.** A founder connects a provider once (`POST /api/connections`, the Intelligence screen):
   its type, endpoint, how it authenticates, and optionally which models to offer, their prices, a rate limit and
   provider options. The key is named (an environment variable) or kept in the secrets file; the page sends it
   once and never shows it again. The desktop app connects "This computer" itself, and a process whose
   environment names a model (`HF_TOKEN`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, a local server, a model command)
   gets a connection for it (`IntelligenceSupply.connect_environment`).
2. **Discover and register.** The adapter lists what the connection offers. Hugging Face's router gives each
   model's price and context. With no list available, the models are registered at the most expensive list price,
   and the connection's status says why. Each model becomes a registry entry. What a connection no longer offers
   is retired, and its measured record is kept.
3. **Choose.** The Intelligence Router scores every available intelligence for a worker's kinds of work:
   the chance of passing verification (from recorded outcomes, with the same prior for all), expected cost and
   expected time. It binds the worker to the best one. It owns no credentials. One intelligence can power many
   workers, and two workers of the same role can run on different ones. Staffing is refined once the roadmap
   says what each worker will actually do.
4. **Execute.** A worker's call goes through the Intelligence Gateway. The Gateway reads the binding's
   intelligence and pinned version, the connection, and the credential for this call only. The adapter then
   shapes the call for its provider, and `model_adapter.py` carries it. The Gateway also enforces the rate limit.
   It refuses a retired intelligence and one that failed its regression check, and it applies faults set for
   proving replacement.
5. **Measure.** Every call is metered in dollars against the connection's prices, and every verification is
   recorded as an outcome for that intelligence and kind of work. The next choice reads those outcomes.
6. **Replace.** The Replacement Engine decides keep, reroute or replace from evidence. When an intelligence goes
   down it prefers the fallback the founder set. When an intelligence reports a new version, the worker continues
   only after a regression check on the worker's kind of work passes, and the binding then pins the new version.
   Each change is a new binding with the old one in its history. The worker's identity, role, authority and
   history never change, and no worker is created.
7. **Audit.** Every connection change, discovery, registration, retirement, fault and fallback is an event in
   the control plane's log (`company_id` `control_plane`). Every binding, version change and replacement is an
   event in the run's log.

## Provider adapters

| Type | Adapter | Authentication | Discovery |
| --- | --- | --- | --- |
| `openai_compatible` | `OpenAICompatibleAdapter`: OpenAI, Hugging Face's router, any compatible server | API key or none | `/models`, with Hugging Face's prices and context |
| `anthropic` | `AnthropicAdapter`: the Messages API | API key | `/v1/models` |
| `local` | `LocalInferenceAdapter`: the desktop app's llama-server (downloads and swaps models), Ollama, a self-hosted server, a model command | none or API key | the app's catalog, or the models named |
| `bedrock` | not built. It is planned, listed as planned, and refused if connected. It is one adapter added to `adapters.py`, with IAM as a credential method | | |

### Hugging Face is an aggregator, not a provider

Hugging Face Inference Providers is one OpenAI-compatible router (`https://router.huggingface.co/v1`) in front of
partner companies that actually run the models (DeepInfra, Together, Fireworks, Groq, Cerebras, Nebius, Novita and
others); Hugging Face runs a few small models itself (HF Inference, mostly CPU). A Hugging Face token authenticates
the call, and Hugging Face bills the account at the partner's price (PRO includes $2 of credit a month), unless a
partner's own key is stored in Hugging Face, in which case the partner bills. Sources: the Inference Providers
[overview](https://huggingface.co/docs/inference-providers/index),
[pricing and billing](https://huggingface.co/docs/inference-providers/pricing) and
[chat completion](https://huggingface.co/docs/inference-providers/en/tasks/chat-completion) pages, checked 27
September 2026.

So in Cynqra Hugging Face is one provider connection (type `openai_compatible`, flavor `hf`) whose credential is
the Hugging Face token, and every model registered through it records `served_by`, the company serving it:

- discovery takes the cheapest live company that supports structured output, and keeps the one already serving a
  model while it is live, so a model's record is not moved by a cheaper newcomer;
- every call names it (`Qwen/Qwen3.8-27B:deepinfra`), so what is metered and billed is what was chosen;
- the same model served by another company is a new version (`served_version`: `<version>@<company>`): its record
  starts apart, and a worker bound to it continues only after its regression check.

A Hugging Face subscription is a monthly credit, not unlimited access; Cynqra's dollar budget and its "no credit
left" failure (a provider error, reported, never worked around) are what keep a project inside it.

A new provider type is a subclass of `ProviderAdapter` with four methods: `normalize`, `discover`, `route`,
`reachable`. Workers, bindings, the registry and the Router do not change
(`test_a_new_adapter_plugs_in_without_touching_workers_registry_or_router`).

## The ten demonstrations

`poc/tests/test_intelligence_supply.py` runs each one against test doubles in seconds. Its answers are not
results. The same code runs on real models in `.github/workflows/cynqra-workforce.yml`, where three local models
are connected, probed and staffed, and on Hugging Face when `HF_TOKEN` is set as a repository secret.

| # | Demonstration | Test |
| --- | --- | --- |
| 1 | Connect several sources of intelligence | `test_three_provider_types_connect_and_discover` |
| 2 | Discover and register their models | the same, and `test_discovery_retires_what_is_gone_and_keeps_its_record` |
| 3 | Create workers | `test_workers_hold_no_intelligence_and_many_can_share_one` |
| 4 | Evaluate | `test_a_better_intelligence_is_detected_and_the_worker_rebound` (the Performance and Replacement Engines) |
| 5 | Different models for different workers | `test_different_workers_are_bound_to_different_intelligence_by_evidence` |
| 6 | Execute real tasks | `test_a_run_executes_through_the_gateway_and_is_metered` |
| 7 | Record metrics | the same: every call priced, every verification an outcome |
| 8 | Detect a better model | `test_a_better_intelligence_is_detected_and_the_worker_rebound` |
| 9 | Reassign, preserving identity | the same, `test_a_new_version_is_regression_checked_before_the_worker_continues`, `test_the_fallback_is_preferred_when_an_intelligence_goes_down` |
| 10 | Audit events | `test_every_supply_decision_is_an_audit_event` |

Credentials: `test_credentials_live_only_in_the_secrets_layer`. The key is absent from the control database and
from everything the product shows, the secrets file is 0600, and the Anthropic call carried the key the Gateway
resolved for it. The HTTP API: `test_server.ApiTests.test_provider_connections_over_http`.

## Not built in V1

- AWS Bedrock (designed for, above).
- The registry's evidence is per installation, not per tenant. The architecture review (section 6) describes the
  per-company scoping for a multi-tenant control plane.
- The secrets layer is a file on this computer (0600). A hosted control plane would put a secrets manager behind
  the same `Credentials` interface.
