"""The live view of a run: its persisted events, printed as they are saved (observability only).

This is a projection of the event log, never a second source of events. It reads the run's store and nothing else:
an event appears only once its write has committed (the store holds its lock for a whole transaction, and a
transaction that fails is rolled back with its events), in the order the events were saved, each exactly once. It
never writes, and nothing in selection, routing, execution, evidence or policy knows it is there. The same lines can
be rebuilt from a finished run's store, so the console need not have been watched:

    python3 -m cynqra.live_events <run folder or its cynqra.db>

A line shows who and what, never the work itself: only named payload fields, and for a selection the persisted
decision it reports (candidates, eligible and excluded, the selection, the evidence version, the policy, the ranking
and the reason). Anything shaped like a provider key, or equal to a key in this environment, is redacted.
"""
from __future__ import annotations

import os
import re
import sys
import threading
from pathlib import Path

# the decision record the selection events report (controller.KIND), read, never written
DECISION_KIND = "selection_decision"
SELECTION_EVENTS = ("intelligence.candidate_set.created", "intelligence.selection.proposed",
                    "intelligence.selection.committed", "intelligence.reselection.triggered", "intelligence.rerouted",
                    "worker.bound")
# what a line shows of an event's payload: who, what, why
KEYS = ("task_id", "worker_id", "from", "to", "intelligence_id", "selected", "mode", "kind", "verdict", "attempt",
        "cause", "status", "method", "decision_id", "evidence_version", "binding_version", "scope", "why", "reason",
        "headline")
# provider keys by shape, and the environment variables that may hold one
KEY_SHAPES = re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}|AIza[0-9A-Za-z_\-]{30,}|nvapi-[A-Za-z0-9_\-]{20,}|"
                        r"hf_[A-Za-z0-9]{30,}|gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{40,}")
SECRET_ENV = ("GEMINI_API_KEY", "NVIDIA_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "HF_TOKEN", "CLAUDE_KEY",
              "CLAUDE_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY")


def redact(text: str, secrets: tuple[str, ...] = ()) -> str:
    for value in secrets:
        if value and len(value) >= 8:
            text = text.replace(value, "[redacted]")
    return KEY_SHAPES.sub("[redacted]", text)


def _short(v, n: int = 160) -> str:
    s = str(v)
    return s if len(s) <= n else s[: n - 1] + "…"


def _decision(store, e: dict) -> dict | None:
    p = e.get("payload") or {}
    did = p.get("decision_id") or (e["aggregate_id"] if e.get("aggregate_type") == DECISION_KIND else None)
    return store.get(DECISION_KIND, did) if did else None


def _decision_parts(d: dict, event_type: str) -> list[str]:
    """What a selection event reports, from its persisted decision: enough to understand it without the log."""
    parts = [f"decision={d['decision_id']}", f"work_item={d.get('work_item_id')}", f"worker={d.get('worker_id')}",
             f"purpose={d.get('purpose')}", f"evidence_version={d.get('evidence_version')}"]
    if event_type in ("intelligence.candidate_set.created", "intelligence.selection.proposed"):
        excluded: dict[str, int] = {}
        for x in d.get("excluded_candidates") or []:
            why = ((x.get("violations") or [{}])[0]).get("constraint") or "excluded"
            excluded[why] = excluded.get(why, 0) + 1
        eligible = [x if isinstance(x, str) else x.get("id") for x in d.get("eligible_candidates") or []]
        parts += [f"candidates={len(d.get('candidate_set') or [])}", f"eligible=[{', '.join(eligible[:8])}"
                  + (", …" if len(eligible) > 8 else "") + "]",
                  "excluded={" + ", ".join(f"{k}: {v}" for k, v in sorted(excluded.items())) + "}"]
    if event_type != "intelligence.candidate_set.created":
        sel = (d.get("selected_intelligence") or {}).get("id")
        parts += [f"selected={sel}", f"mode={d.get('selection_mode')}", f"tier={d.get('tier')}",
                  f"policy={d.get('selection_policy_version')}"]
        rank = [f"{r['id']} {r.get('quality')} [{r.get('lcb')}–{r.get('ucb')}] by {r.get('decisive_level')}"
                for r in (d.get("ranking") or [])[:3]]
        if rank:
            parts.append("ranking=" + "; ".join(rank))
        if event_type in ("intelligence.selection.proposed", "intelligence.reselection.triggered"):
            parts.append(f"reason={_short(d.get('selection_reason') or '', 240)}")
    return parts


def event_line(e: dict, store=None, secrets: tuple[str, ...] = ()) -> str:
    """One persisted event as a line: its sequence number, type and subject, then what it says."""
    p = e.get("payload") or {}
    parts = [f"{k}={_short(p[k])}" for k in KEYS if p.get(k) not in (None, "", [], {})]
    d = _decision(store, e) if store is not None and e["event_type"] in SELECTION_EVENTS else None
    if d is not None:
        shown = {"decision_id", "selected", "mode", "evidence_version", "binding_version", "reason"}
        parts = [x for x in parts if x.split("=", 1)[0] not in shown] + _decision_parts(d, e["event_type"])
    return redact(f"  live #{e['seq']} {e['event_type']} {e['aggregate_id']} " + " ".join(parts), secrets)


def env_secrets() -> tuple[str, ...]:
    return tuple(v for v in (os.environ.get(n, "") for n in SECRET_ENV) if v)


def lines(store, after: int = 0) -> list[str]:
    """A run's events as the live view showed them (or would have), from its store."""
    s = env_secrets()
    return [event_line(e, store, s) for e in store.events(after=after)]


class EventTail:
    """Prints a run's events to the log as they are saved. Read-only: it calls the store's events() and get(), never
    a write, so it cannot change what the run does; it shows nothing that was not saved and nothing twice."""

    def __init__(self, store, log=print, every: float = 5.0):
        self.store, self.log, self.every, self.seq = store, log, every, 0
        self.secrets = env_secrets()
        self._stop = threading.Event()
        self._lock = threading.Lock()  # one flush at a time: the loop's and the final one never print the same event
        self._thread = threading.Thread(target=self._loop, daemon=True, name="cynqra-live-events")

    def start(self) -> "EventTail":
        self._thread.start()
        return self

    def flush(self) -> int:
        with self._lock:
            n = 0
            for e in self.store.events(after=self.seq):
                self.log(event_line(e, self.store, self.secrets))
                self.seq = e["seq"]
                n += 1
            return n

    def _loop(self) -> None:
        while not self._stop.wait(self.every):
            try:
                self.flush()
            except Exception:  # noqa: BLE001 - the live view never stops the run; the store keeps every event
                pass

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=30)
        self.flush()


def main(argv: list[str] | None = None) -> int:
    from .db import Store
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python3 -m cynqra.live_events <run folder or its cynqra.db>")
        return 2
    path = Path(args[0])
    store = Store(str(path / "cynqra.db" if path.is_dir() else path))
    try:
        for x in lines(store):
            print(x)
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
