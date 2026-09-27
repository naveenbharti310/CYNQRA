"""The secrets layer: what authorizes a provider connection.

A credential is a reference, kept apart from workers, intelligence and connections:

  env      the name of an environment variable that holds the key; Cynqra stores the name, never the value
  secret   a key the founder entered in the app, kept in the secrets file (secrets/credentials.json beside the
           control plane's database, readable only by this user), never in the database, an event or an export
  none     a provider that needs no key (a model on this machine, a local server)

Only the Intelligence Gateway resolves a credential, for one call, and nothing it resolves is stored elsewhere.
OAuth and IAM (for Bedrock) are further methods for the adapters that need them.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path

from ..db import now
from .contracts import CREDENTIAL_METHODS, SupplyError


class CredentialError(SupplyError):
    pass


class Credentials:
    def __init__(self, store, secrets_dir: Path):
        self.store = store
        self.dir = Path(secrets_dir)
        self.file = self.dir / "credentials.json"
        self.lock = threading.RLock()

    # --- the secrets file ------------------------------------------------------------------------------------
    def _secrets(self) -> dict:
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, data: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, self.file)
        try:
            os.chmod(self.file, 0o600)
        except OSError:
            pass  # Windows keeps the file in the user's own profile folder, which only that user can read

    # --- credentials -----------------------------------------------------------------------------------------
    def create(self, method: str, env_var: str = "", secret: str = "", label: str = "") -> dict:
        if method not in CREDENTIAL_METHODS:
            raise CredentialError(f"credential method must be one of {', '.join(CREDENTIAL_METHODS)}")
        env_var = (env_var or "").strip()
        if method == "env" and not env_var.replace("_", "").isalnum():
            raise CredentialError("name the environment variable that holds the key, such as ANTHROPIC_API_KEY")
        if method == "secret" and not (secret or "").strip():
            raise CredentialError("the key is empty")
        cid = "cred_" + uuid.uuid4().hex[:10]
        rec = {"id": cid, "method": method, "env_var": env_var if method == "env" else "", "label": label,
               "created_at": now()}
        with self.lock:
            if method == "secret":
                data = self._secrets()
                data[cid] = secret.strip()
                self._write(data)
            self.store.put("credential", cid, rec)
        return dict(rec)

    def get(self, cid: str) -> dict:
        rec = self.store.get("credential", cid)
        if rec is None:
            raise CredentialError(f"no credential {cid}")
        return rec

    def status(self, cid: str) -> tuple[bool, str]:
        """Whether the credential can authorize a call now, said without revealing it."""
        rec = self.store.get("credential", cid)
        if rec is None:
            return False, "its credential is missing"
        if rec["method"] == "env" and not os.environ.get(rec["env_var"]):
            return False, f"{rec['env_var']} is not set"
        if rec["method"] == "secret" and not self._secrets().get(cid):
            return False, "its stored key is missing"
        return True, "present"

    def resolve(self, cid: str) -> str | None:
        """The secret itself, for one call. Only the Intelligence Gateway and discovery call this."""
        rec = self.get(cid)
        if rec["method"] == "none":
            return None
        value = os.environ.get(rec["env_var"]) if rec["method"] == "env" else self._secrets().get(cid)
        if not value:
            raise CredentialError(self.status(cid)[1])
        return value

    def public(self, cid: str) -> dict:
        rec = self.get(cid)
        ok, why = self.status(cid)
        return {"id": cid, "method": rec["method"], "env_var": rec["env_var"], "present": ok, "status": why}

    def delete(self, cid: str) -> None:
        with self.lock:
            data = self._secrets()
            if data.pop(cid, None) is not None:
                self._write(data)
            self.store.delete("credential", cid)
