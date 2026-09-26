"""Checks derived from the confirmed objective and decision_001.
Not from the S3 seed file. Kit only.

26 Sep 2026, acting CTO. Two probes added for the rule "errors must surface":
write_persists reads a valid write back through list(), and failure_surfaces
injects a storage failure into a valid write and requires an error. They have
new ids on purpose. run_s3.py still maps s3_06 to write_surfaces, so rerunning
S3 v1 does not turn its recorded miss into a catch after the fact. See
spikes/s3/S3_V1_RESTATEMENT.md.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path


def load_store(store_py: Path):
    spec = importlib.util.spec_from_file_location("store_under_test", store_py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_store(store_py: Path) -> list[dict]:
    findings = []
    mod = load_store(store_py)
    Err = getattr(mod, "CandidateError", Exception)
    Store = mod.CandidateStore

    s = Store()
    try:
        s.create("  ")
        findings.append({"id": "empty_name", "caught": True, "how": "create accepted blank name"})
    except Err:
        findings.append({"id": "empty_name", "caught": False, "how": "create rejected blank name"})
    except Exception as e:
        findings.append({"id": "empty_name", "caught": True, "how": f"unexpected {type(e).__name__}"})

    s = Store()
    a = s.create("A")
    b = s.create("B")
    listed = s.list()
    if len(listed) != 2:
        findings.append({"id": "list_all", "caught": True, "how": f"list returned {len(listed)} of 2"})
    else:
        findings.append({"id": "list_all", "caught": False, "how": "list returned both"})

    stage = a.get("stage") if isinstance(a, dict) else None
    if stage != "applied":
        findings.append({"id": "starts_applied", "caught": True, "how": f"create stage={stage!r}"})
    else:
        findings.append({"id": "starts_applied", "caught": False, "how": "create starts applied"})

    s = Store()
    rec = s.create("C")
    cid = rec["id"]
    if hasattr(s, "set_stage"):
        try:
            s.set_stage(cid, "ghost")
            findings.append({"id": "unknown_stage", "caught": True, "how": "ghost stage accepted"})
        except Err:
            findings.append({"id": "unknown_stage", "caught": False, "how": "ghost stage rejected"})
        try:
            s.set_stage("no_such", "interview")
            findings.append({"id": "unknown_id", "caught": True, "how": "unknown id accepted"})
        except Err:
            findings.append({"id": "unknown_id", "caught": False, "how": "unknown id rejected"})
        try:
            s.set_stage(cid, "interview")
            findings.append({"id": "write_surfaces", "caught": False, "how": "valid set_stage returned"})
        except Exception as e:
            findings.append({"id": "write_surfaces", "caught": True, "how": f"valid write raised {type(e).__name__}"})
    else:
        findings.append({"id": "unknown_stage", "caught": True, "how": "no set_stage"})
        findings.append({"id": "unknown_id", "caught": True, "how": "no set_stage"})
        findings.append({"id": "write_surfaces", "caught": True, "how": "no set_stage"})

    findings.extend(_error_surfacing(Store, Err))
    return findings


class _FailingStorage(dict):
    """A storage map whose reads fail, standing in for a broken disk or DB."""

    def __getitem__(self, key):
        raise OSError("injected storage failure")


def _error_surfacing(Store, Err) -> list[dict]:
    out = []
    s = Store()
    if not hasattr(s, "set_stage"):
        return [
            {"id": "write_persists", "caught": True, "how": "no set_stage"},
            {"id": "failure_surfaces", "caught": True, "how": "no set_stage"},
        ]
    rec = s.create("D")
    cid = rec["id"]
    try:
        s.set_stage(cid, "interview")
        rows = [r for r in s.list() if isinstance(r, dict) and r.get("id") == cid]
        if not rows or rows[0].get("stage") != "interview":
            out.append({"id": "write_persists", "caught": True, "how": "valid write not visible on read back"})
        else:
            out.append({"id": "write_persists", "caught": False, "how": "valid write read back"})
    except Exception as e:
        out.append({"id": "write_persists", "caught": True, "how": f"valid write raised {type(e).__name__}"})

    s = Store()
    rec = s.create("E")
    storage = getattr(s, "_items", None)
    if not isinstance(storage, dict):
        out.append({"id": "failure_surfaces", "caught": None, "how": "store has no _items map to fail; probe not applicable"})
        return out
    s._items = _FailingStorage(storage)
    try:
        result = s.set_stage(rec["id"], "interview")
        out.append({"id": "failure_surfaces", "caught": True, "how": f"storage failed but set_stage returned {result!r}"})
    except Exception:
        out.append({"id": "failure_surfaces", "caught": False, "how": "storage failure surfaced as an error"})
    return out


def lint_specs(paths: list[Path]) -> list[dict]:
    hits = []
    for p in paths:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        low = text.lower()
        if re.search(r"stuck.{0,80}(7\s*day|elapsed|no stage change|clock)", low, re.S) and not re.search(
            r"named reason|waiting_on_recruiter", low
        ):
            hits.append({"file": p.name, "id": "stuck_clock", "what": "stuck defined as a clock"})
        if "public careers" in low or "public career" in low:
            hits.append({"file": p.name, "id": "public_site", "what": "public careers site"})
        if "applicant" in low and ("log in" in low or "login" in low):
            hits.append({"file": p.name, "id": "applicant_login", "what": "applicant login"})
        if "dashboard" in low and ("success" in low or "pretty" in low):
            hits.append({"file": p.name, "id": "dashboard_success", "what": "dashboard as success"})
    return hits
