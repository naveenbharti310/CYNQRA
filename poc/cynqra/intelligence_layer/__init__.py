"""The Intelligence Layer: what intelligence exists, which worker runs on which, and how it is reached.

A subsystem of the Cynqra control plane with its own domain model, storage and contract (contracts.py). It runs in
process and keeps its records in the control plane's database; nothing outside this package reads those records
directly, so it can later be extracted into a service without redesigning the domain.

    WORKER  !=  INTELLIGENCE  !=  PROVIDER CONNECTION  !=  CREDENTIAL

  credentials.py   the secrets layer: what authorizes a connection. Only the gateway reads a secret, per call.
  connections.py   provider connections: how Cynqra may reach a provider (type, endpoint, auth method, account,
                   region, status, rate limits, the models it offers). Holds a credential reference, never a secret.
  adapters.py      one adapter per provider type (OpenAI-compatible, Anthropic, local/self-hosted; Bedrock later):
                   discovery, reachability and the provider-specific form of a call.
  registry.py      the Intelligence Registry: what each intelligence is and how well it has performed. No secrets,
                   no endpoints, no workers.
  router.py        the Intelligence Router: which available intelligence should power a worker for its workload.
                   It reads the registry and owns no credentials.
  gateway.py       the Intelligence Gateway: one execution interface for every provider. A worker's call arrives
                   as (intelligence id, request) and leaves as a response; the worker never knows the provider.

    CYNQRA ──┬── Workforce Engine (roles, synthesis, the workers)      ─┐
             └── Intelligence Layer (registry, router)                 ─┴─▶ worker, through its binding
                                                                            (cynqra/binding.py, in each run)
                                        Intelligence Gateway ◀── worker
                                     ┌──────────┼──────────┐
                                  OpenAI    Anthropic    Local        [Bedrock later]
"""
from __future__ import annotations

from pathlib import Path

from ..db import Store
from .adapters import adapter_types, make_adapters
from .connections import Connections, ConnectionsError
from .contracts import SupplyError
from .credentials import CredentialError, Credentials
from .gateway import IntelligenceGateway, VersionChanged
from .registry import IntelligenceRegistry, RegistryError

__all__ = ["IntelligenceSupply", "SupplyError", "CredentialError", "ConnectionsError", "RegistryError",
           "VersionChanged", "adapter_types"]


class IntelligenceSupply:
    """The subsystem's entry point: its store, its four parts, and the operations that span them."""

    def __init__(self, root: Path, runtime=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = Store(str(self.root / "control.db"))
        self.runtime = runtime  # the desktop app's model manager, for the local adapter's managed llama-server
        self.adapters = make_adapters(runtime=runtime)
        self.credentials = Credentials(self.store, self.root / "secrets")
        self.connections = Connections(self.store, self.credentials, self.adapters)
        self.registry = IntelligenceRegistry(self.store, reachable=self._reachable)
        self.gateway = IntelligenceGateway(self.registry, self.connections, self.credentials, self.adapters)

    # --- the intelligence supply flow: connect, discover, register -------------------------------------------
    def connect(self, spec: dict, origin: str = "founder") -> dict:
        """Connect a provider once; its intelligence is discovered and registered. Returns the public connection and
        the registry entries it now offers."""
        conn = self.connections.create(spec, origin=origin)
        entries = self.discover(conn["id"])
        return {"connection": self.connections.public(conn["id"]), "intelligence": entries}

    def discover(self, connection_id: str) -> list[dict]:
        conn = self.connections.get(connection_id)
        adapter = self.adapters[conn["type"]]
        conn["_served_by"] = {m["ref"]: m.get("served_by") for m in self.registry.models()
                              if m["connection_id"] == connection_id and m.get("served_by")}
        try:
            found = adapter.discover(conn, self.credentials.resolve(conn["credential_id"]))
        except SupplyError as exc:
            self.connections.set_status(connection_id, "error", str(exc))
            raise
        found = [self._normalize(f, conn, adapter) for f in found]
        note = conn.get("_listing_note") or ""
        self.connections.set_status(connection_id, "connected", f"{len(found)} model(s) offered" + (
            f"; {note}" if note else ""), offered=[f["ref"] for f in found])
        refs = {f["ref"] for f in found}
        for m in self.registry.models():  # what the connection no longer offers is retired; its record is kept
            if m["connection_id"] == connection_id and m["ref"] not in refs and m.get("source") == "discovered":
                self.registry.retire(m["id"], "no longer offered by its provider connection")
        return [self.registry.register(f, connection_id=connection_id) for f in found]

    @staticmethod
    def _normalize(f: dict, conn: dict, adapter) -> dict:
        """One discovered model, normalized (normalize.py): its publisher and the access provider it is reached
        through kept apart, its capabilities, input types, context and dates from the provider's listing and the public
        catalogue, and the connection's rate limit as a structured fact the Router can read."""
        from .normalize import describe, host_of
        out = dict(f)
        if not f.get("local") and adapter.type not in ("demo_script", "local"):
            host = host_of(conn.get("endpoint") or getattr(adapter, "DEFAULT", ""))
            out.update({k: v for k, v in describe(f["ref"], f, host).items() if v not in (None, "", [])})
        out.update(access_provider=conn.get("name") or adapter.title, access_type=adapter.title,
                   rate_limit_per_min=int((conn.get("rate_limits") or {}).get("calls_per_minute") or 0) or None)
        # A price Cynqra does not know is the worst case only until the public catalogue names the model's list
        # price (paid run 37589136743: Gemini at $10/$50 per million against Google's $0.50/$3 and $2/$12 stopped an
        # objective at its cap and left calibration no budget). A catalogue price of 0 is a free variant's, not this
        # model's, so it is not taken.
        lin, lout = out.get("list_price_in"), out.get("list_price_out")
        if out.get("price_source") == "unknown" and lin and lout and float(lin) > 0 and float(lout) > 0:
            out.update(price_in=float(lin), price_out=float(lout), price_source="catalogue")
        return out

    def catalog(self, connection_id: str) -> dict:
        """Everything the connection's provider lists, whether it is offered now or not, so the founder can search it
        and choose which models Cynqra may use. Nothing is registered by looking."""
        import copy
        conn = copy.deepcopy(self.connections.get(connection_id))
        chosen = list(conn.get("models") or [])
        conn["models"], conn["_all"] = [], True
        adapter = self.adapters[conn["type"]]
        found = [self._normalize(f, conn, adapter) for f in adapter.discover(conn, self.credentials.resolve(conn["credential_id"]))]
        from .adapters import current
        fresh = set(current([f["ref"] for f in found], {f["ref"]: f.get("released") for f in found}))
        active = {m["ref"] for m in self.registry.models() if m["connection_id"] == connection_id}
        rows = [{"ref": f["ref"], "name": f.get("display_name") or f.get("name") or f["ref"], "context": f.get("context"),
                 "publisher_name": f.get("publisher_name") or "", "type": f.get("type") or "",
                 "capabilities": f.get("capabilities") or [], "description": f.get("description") or "",
                 "released": f.get("released"), "current": f["ref"] in fresh, "offered": f["ref"] in active}
                for f in found]
        # newest first; models with no known date last
        rows.sort(key=lambda x: (-(x["released"] or 0), x["ref"].lower()))
        return {"connection_id": connection_id, "limited": bool(chosen), "dates": any(r["released"] for r in rows),
                "models": rows}

    def connect_environment(self) -> list[dict]:
        """The intelligence this process's environment names (API keys, a local server, a model command), connected
        with credentials that reference the environment variables, never copies of them."""
        out = []
        for spec in self.adapters.environment_specs():
            existing = self.connections.find(origin="environment", name=spec["name"])
            if existing and list(existing.get("models") or []) != [m for m in spec.get("models") or [] if m]:
                # the environment is what an environment connection offers: a model it names, or no longer names
                # (every model the key reaches is then discovered), replaces what an earlier start saved
                self.connections.update(existing["id"], {"models": [m for m in spec.get("models") or [] if m]})
            conn_id = existing["id"] if existing else self.connections.create(spec, origin="environment")["id"]
            try:
                out += self.discover(conn_id)
            except SupplyError:
                continue  # its status says why; another source may still serve
        return out

    def qualify(self, entries: list[dict] | None = None, limit: int = 3, log=lambda s: None) -> list[dict]:
        """Global qualification for discovered intelligence that has none yet (mandate 16): a discovered model is
        not qualified until its qualification work passes (probe.py). Bounded: at most limit candidates its provider
        serves, fair across providers and diverse across families, the newest of each (candidates.py), and only ones
        that can be reached now. A provider failure leaves a model unverified (inconclusive), never failed. Returns
        the probe results."""
        from .. import attribution
        from ..probe import probe  # the probe drives a model source; imported here to keep the layer acyclic
        from .candidates import examine
        pool = entries if entries is not None else self.registry.models()
        pending = []
        for m in pool:
            m = self.registry.get(m["id"])
            if m.get("status") == "retired" or m.get("runtime") == "scripted":
                continue
            if (m.get("regression") or {}).get("status") != "unverified" or not self._reachable(m)[0]:
                continue
            pending.append(m)
        local = [m for m in pending if m.get("local")][:1]  # a model on this computer loads gigabytes: one at a time

        def one(m: dict) -> dict:
            try:
                return probe(self, m["id"], log=log)
            except Exception as exc:  # noqa: BLE001 - a probe that cannot run leaves the model unverified
                return {"model_id": m["id"], "passed": False, "qualification_status": "inconclusive",
                        "error": str(exc)[:300]}

        def served(r: dict) -> bool:  # a model its provider lists but no longer serves gives its place to the next
            return not (r.get("error") and attribution.diagnose(r["error"]) == "withdrawn")

        if not pending:
            return []
        # hosted candidates are examined side by side; a model on this computer is one of them at most (above)
        return examine([m for m in pending if not m.get("local")] + local, limit, one, served, parallel=limit)[1]

    def remove_connection(self, connection_id: str) -> None:
        for m in self.registry.models():
            if m["connection_id"] == connection_id:
                self.registry.retire(m["id"], "its provider connection was removed")
        self.connections.remove(connection_id)

    def _reachable(self, entry: dict) -> tuple[bool, str]:
        """Whether the intelligence can be reached now: its connection exists and is usable, the credential is
        present, and the adapter can reach the model (a local model downloaded, say)."""
        conn = self.connections.find_id(entry.get("connection_id"))
        if conn is None:
            return False, "no provider connection"
        if conn.get("status") == "error":
            return False, f"connection {conn['name']}: {conn.get('status_note') or 'error'}"
        ok, why = self.credentials.status(conn["credential_id"])
        if not ok:
            return False, why
        return self.adapters[conn["type"]].reachable(conn, entry)

    def snapshot(self) -> dict:
        try:  # what this computer's settings name, connected when a live project starts
            env = [s["name"] for s in self.adapters.environment_specs()]
        except Exception:  # noqa: BLE001 - a setting that cannot be read names nothing
            env = []
        return {"connections": [self.connections.public(c["id"]) for c in self.connections.all()],
                "intelligence": self.registry.snapshot(), "provider_types": adapter_types(), "environment": env}

    def close(self) -> None:
        self.store.close()
