"""Provider connections: how Cynqra is allowed to reach an intelligence provider.

A founder connects a provider once: its type (OpenAI-compatible, Anthropic, local/self-hosted), where it is, how it
authenticates, and optionally which of its models to offer, its account, region, rate limit and options. The
connection keeps a reference to its credential (credentials.py), never the secret. Discovery then registers the
models it offers in the Intelligence Registry; the Intelligence Router, not the founder, decides which worker runs on
which of them.

Every connection change is an event in the control plane's audit log. Removing a connection deletes its credential
and retires the intelligence it offered; the measured record of that intelligence is kept.
"""
from __future__ import annotations

import ipaddress
import socket
import threading
import uuid
from urllib.parse import urlparse

from ..db import now
from .contracts import AUTH_METHODS, SupplyError



LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


def check_endpoint(endpoint: str, auth_method: str) -> None:
    """An endpoint is a web address. A key travels only encrypted (https), except to this computer: over plain http
    anyone on the network between here and the server could read it."""
    if not endpoint:
        return
    u = urlparse(endpoint)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ConnectionsError("the endpoint must be a web address starting with https:// (or http:// for a server "
                               "on this computer or one that needs no key)")
    host = (u.hostname or "").lower()
    if auth_method != "none" and u.scheme == "http" and host not in LOCAL_HOSTS:
        raise ConnectionsError("a key is only sent over https:// to another computer; over http:// anyone on the "
                               "network could read it")
    # Never let a provider connection carrying credentials target a private, loopback, link-local, multicast or
    # otherwise non-public address. This blocks common SSRF and DNS-rebinding targets at connection setup.
    if auth_method != "none" and host not in LOCAL_HOSTS:
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, u.port or (443 if u.scheme == "https" else 80),
                                                                  type=socket.SOCK_STREAM)}
        except socket.gaierror as exc:
            raise ConnectionsError(f"the endpoint hostname does not resolve: {host}") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved
                    or ip.is_unspecified):
                raise ConnectionsError("the endpoint resolves to a private or otherwise non-public network address")

class ConnectionsError(SupplyError):
    pass


class Connections:
    def __init__(self, store, credentials, adapters):
        self.store = store
        self.credentials = credentials
        self.adapters = adapters
        self.lock = threading.RLock()

    def create(self, spec: dict, origin: str = "founder") -> dict:
        spec = dict(spec or {})
        ptype = spec.get("type")
        if ptype not in self.adapters:
            raise ConnectionsError(f"provider type must be one of {', '.join(t for t in self.adapters if t != 'demo_script')}")
        spec["origin"] = origin
        spec = self.adapters[ptype].normalize(spec)
        auth = dict(spec.get("auth") or {"method": "none"})
        method = auth.get("method") or "none"
        if method in ("env", "secret"):
            auth_method = "api_key"
        elif method == "none":
            auth_method = "none"
        else:
            raise ConnectionsError("auth.method is env (an environment variable's name), secret (a key kept in the "
                                   "secrets file) or none")
        if auth_method not in self.adapters[ptype].auth_methods or auth_method not in AUTH_METHODS:
            raise ConnectionsError(f"a {self.adapters[ptype].title} connection authenticates with "
                                   f"{' or '.join(self.adapters[ptype].auth_methods)}")
        check_endpoint(spec.get("endpoint") or "", auth_method)
        models = spec.get("models") or []
        if isinstance(models, str):
            models = [m.strip() for m in models.split(",")]
        name = str(spec.get("name") or "").strip() or self.adapters[ptype].title
        with self.lock:
            cred = self.credentials.create(method, env_var=auth.get("env_var", ""), secret=auth.get("secret", ""),
                                           label=name)
            conn = {"id": "conn_" + uuid.uuid4().hex[:8], "type": ptype, "name": name,
                    "endpoint": spec.get("endpoint") or "", "server": spec.get("server") or "",
                    "auth_method": auth_method, "credential_id": cred["id"],
                    "account": str(spec.get("account") or ""), "region": str(spec.get("region") or ""),
                    "models": [m for m in models if m], "settings": dict(spec.get("settings") or {}),
                    "price_per_m": spec.get("price_per_m") or None,
                    "machine_usd_per_hour": float(spec.get("machine_usd_per_hour") or 0),
                    "rate_limits": dict(spec.get("rate_limits") or {}), "permission": "connected by you"
                    if origin == "founder" else f"from the {origin}", "status": "new", "status_note": "",
                    "offered": [], "origin": origin, "metadata": dict(spec.get("metadata") or {}),
                    "created_at": now(), "checked_at": None}
            self.store.put("connection", conn["id"], conn)
        self._audit("connection.created", conn["id"], {"type": ptype, "title": name, "auth_method": auth_method,
                    "credential": cred["method"], "origin": origin})
        return conn

    EDITABLE = ("name", "models", "settings", "rate_limits", "price_per_m", "machine_usd_per_hour", "account",
                "region", "metadata")

    def update(self, cid: str, changes: dict) -> dict:
        """Change what a connection offers or how it is used. Its type, endpoint and credential are its identity:
        to change those, connect again."""
        bad = [k for k in changes if k not in self.EDITABLE]
        if bad:
            raise ConnectionsError(f"cannot change {', '.join(bad)}; connect the provider again instead")
        with self.lock:
            c = self.get(cid)
            for k, v in changes.items():
                if k == "models" and isinstance(v, str):
                    v = [m.strip() for m in v.split(",") if m.strip()]
                c[k] = float(v or 0) if k == "machine_usd_per_hour" else v
            self.store.put("connection", cid, c)
        self._audit("connection.updated", cid, {"changed": sorted(changes)})
        return c

    def get(self, cid: str) -> dict:
        c = self.store.get("connection", cid)
        if c is None:
            raise ConnectionsError(f"no provider connection {cid}")
        return c

    def find_id(self, cid: str | None) -> dict | None:
        return self.store.get("connection", cid) if cid else None

    def find(self, origin: str, name: str) -> dict | None:
        return next((c for c in self.all() if c["origin"] == origin and c["name"] == name), None)

    def all(self) -> list[dict]:
        return self.store.all("connection")

    def set_status(self, cid: str, status: str, note: str = "", offered: list | None = None) -> dict:
        with self.lock:
            c = self.get(cid)
            c.update({"status": status, "status_note": note[:300], "checked_at": now()})
            if offered is not None:
                c["offered"] = offered
            self.store.put("connection", cid, c)
        self._audit("connection.checked", cid, {"status": status, "note": note[:200]})
        return c

    def remove(self, cid: str) -> None:
        c = self.get(cid)
        with self.lock:
            self.credentials.delete(c["credential_id"])
            self.store.delete("connection", cid)
        self._audit("connection.removed", cid, {"title": c["name"]})

    def public(self, cid: str) -> dict:
        """The connection as the product shows it: its credential described, never revealed."""
        c = dict(self.get(cid))
        c["credential"] = self.credentials.public(c["credential_id"])
        return c

    def _audit(self, event_type: str, cid: str, payload: dict) -> None:
        self.store.append(company_id="control_plane", event_type=event_type, aggregate_type="connection",
                          aggregate_id=cid, actor_type="service", actor_id="provider_connections", payload=payload,
                          correlation_id=cid)
