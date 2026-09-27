# Implementation decisions

Opened 26 September 2026 by the acting CTO. Owner: CTO.

The Canon governance addendum v0.2 says the CTO "records exact technology choices
separately as implementation decisions". This is that record. It is not a sixth book and
ratifies nothing in Book 4. Every row stays inside the binding properties in the Book 2
v0.4 addendum. Any row can be replaced by the hired CTO in their first week, with a line
saying why.

None of this starts M2. It exists so that when S1 and S2 are scored and M2 opens, the
first engineer builds instead of choosing.

Status: Chosen (build to it), Proposed (leaning, not yet needed), Open.

## The M2 set

G1 (runtime safe) needs sandbox, Tool Gateway, policy enforcement, secrets isolation,
budget breaker, kill switch and audit. These rows cover exactly that.

| ADR | Choice | Why | Revisit when |
| --- | --- | --- | --- |
| ADR-2 State | Chosen. One Postgres. An events table that is insert only: the app role has no UPDATE or DELETE grant, and a trigger rejects both. Read models are rebuilt from events. | Book 2 principle 1 and D-18. Postgres is already the Book 2 buy decision. | Event volume outgrows one table, not before M3. |
| ADR-2 and D-22 | Chosen. Personal data lives in subject tables encrypted with a per subject data key, wrapped by a per company key. Events carry subject references only. Erasure deletes the subject rows and destroys the subject key. Company key destruction is the fallback. | This is the Hybrid the founder chose, built so that counsel can still pick option 1 or 2 without a schema change. | Counsel answers D-22. |
| ADR-1 Orchestration | Chosen. Durable workflows as a library on the same Postgres (DBOS Transact for Python), not a separate workflow cluster. Protocol messages go out through an outbox table written in the same transaction as their event. | One database to run and back up. Temporal needs its own cluster and 10 to 20 hours of ops a month self hosted; a two person team cannot carry that in M2. | Workers in more than one language, or throughput a single Postgres cannot hold. |
| ADR-3 Runtime isolation | Chosen. One disposable gVisor (runsc) container per worker session, on a Linux host we control. No network by default. Egress only through an allowlisting proxy. One workspace volume per session, deleted at the end. No credentials inside the container. | Every binding property in the addendum (disposable, scoped filesystem, no shared credentials, allowlisted egress, no host access) is ours to enforce and test. gVisor gives a user space kernel without needing KVM. | Ops load hurts, then a hosted Firecracker sandbox (E2B class), provided its egress allowlist can be proven in a test. |
| ADR-5 Tool Gateway | Chosen. One service in front of every tool, in the order the addendum fixes: request, identity, policy, budget, target validation, execution, result sanitizing, audit event. Short lived tokens scoped to one action. | Addendum contract, taken literally. | No trigger. |
| ADR-6 Policy | Chosen. Policy rows in Postgres keyed by role, action class, risk tier and environment, returning ALLOW, DENY or REQUIRE_APPROVAL, versioned, evaluated in process by the Gateway through the canonical policy.evaluate signature. Default DENY. Every DENY and REQUIRE_APPROVAL writes an event. | The fixed template has four roles and an empty L2 list (D-23). A policy language (OPA, Cedar) is more machinery than four roles need. | Delegation lists grow at L2, or a customer asks for policy they can read. |
| ADR-11 Secrets | Chosen. The cloud provider's secret manager. Secrets are injected into the Tool Gateway only, never into worker containers or any model context. | Addendum invariant: secrets never enter contexts that read untrusted content. | No trigger. |
| ADR-4 Model routing | Chosen. spikes/model_adapter.py is the seed of the registry. Exact model ids are pinned. A model change reruns the S1 corpus as the regression gate. | On 26 September the adapter's Anthropic default turned out to be a model retired on 15 June 2026. Pinning without a gate fails silently; that is the case study. | M2 registry build. |
| ADR-7 Verification | Chosen for M1. LOW: kit probes and prior tests (kit/verify.py, kit/contract_checks.py). MEDIUM: kit/model_review.py, a reviewer that is not the worker, on a different model family from the worker where one is available. HIGH: the founder. | Book 2 tiers, now all three exist. S3 v2 measures them. | S3 v2 result. |

## Not needed for M2

| ADR | Status | Note |
| --- | --- | --- |
| ADR-8 Memory and context | Proposed | Layered context as run_s2.py does it: company, role, task, listed artifacts only. |
| ADR-9 Frontend | Proposed | No dashboards until a run breaks in a way paper cannot carry. Rule unchanged. |
| ADR-10 Tenancy | Proposed | company_id on every row from the first migration costs nothing and is recommended now. Full isolation list from the addendum is an M3 item. |
| ADR-12 Prompt injection | Proposed | Needs the Gateway first. Untrusted content labeling lands with ADR-5. |

## Sources read for this record

Model retirement: platform.claude.com model deprecations page, read 26 Sep 2026.
Durable execution and sandbox comparisons: public 2026 comparisons of Temporal, Restate
and DBOS, and of Docker, gVisor, Firecracker and hosted sandboxes. Treat vendor numbers as
claims to verify in the first M2 week, not facts.
