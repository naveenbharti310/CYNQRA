"""Bounded candidate sets: which intelligence to spend a limited qualification or calibration budget on.

This decides priority, never quality. Not every available model is called for every objective (mandate 11): a
bounded set is chosen that is fair across providers and diverse across model families, and inside each family the
newest release stands for it. Metadata (stated capabilities, context, whether a public catalogue knows it) orders
the set; a version or release date only picks the newest member of a family and never ranks one family above
another, and nothing here says which model is better. What a candidate can do is learned from its verified work.
"""
from __future__ import annotations

import re

from .adapters import _family as _release

USEFUL = {"reasoning", "coding", "agentic", "tool use", "long context", "structured output"}


# A release stage at the end of a name, with any date after it: vendor-3.1-pro-preview is a release of the vendor's Pro
# family, as vendor-2.5-flash-preview-05-20 is of Flash; vendor-pro-latest names whichever Pro the provider moves it to
_STAGE = re.compile(r"-(?:preview|latest|exp|experimental|beta|alpha)(?:-\d+)*$")


def _name(ref: str) -> str:
    """A model's name without publisher, serving suffix or release stage."""
    value = str(ref or "").lower().split("/")[-1].split(":")[0]
    prev = None
    while prev != value:
        prev, value = value, _STAGE.sub("", value)
    return value


def family_key(ref: str) -> str:
    """A model's family: its name without publisher, serving suffix, release stage or version numbers, so
    vendor/model-k2.6 and vendor/model-k3 are one family, as are vendor-model-4-6 and vendor-model-5 (a version written
    with dashes, or with a release date after it) and vendor-2.5-pro and vendor-3.1-pro-preview, and only the newest
    of them takes a place in a bounded set."""
    return re.sub(r"#(?:-#)+(?![a-z])", "#", re.sub(r"\d+(?:\.\d+)*", "#", _name(ref)))


def _families(models: list[dict]) -> dict[str, str]:
    """Each model's family. A name with no version of its own (vendor-pro-latest, an alias the provider moves to each
    new release) belongs to the versioned family it names, when there is one: a moving alias is not a pinned version,
    so it never takes that family's place ahead of a pinned release."""
    fam = {m["id"]: family_key(m.get("ref") or m["id"]) for m in models}
    lines: dict[str, str] = {}
    for k in sorted(set(fam.values())):
        if "#" in k.split("-"):
            lines.setdefault("-".join(p for p in k.split("-") if p != "#"), k)
    return {mid: lines.get(k, k) if "#" not in k.split("-") else k for mid, k in fam.items()}


def _newest_first(m: dict) -> tuple:
    """Inside a family, newest first: a pinned version before a moving alias, then the higher version the provider's
    own name gives (3.8 Flash before 2.5 Flash, 3.1 Pro Preview before 2.5 Pro), a stable release before a preview of
    the same version, and only then the later release date. A date the public catalogue does not have is unknown,
    never old, so it never puts an old release first."""
    ref = str(m.get("ref") or m.get("id"))
    name = _name(ref)
    return (bool(re.search(r"\d", name)), _release(ref)[1], name == ref.lower().split("/")[-1].split(":")[0],
            float(m.get("released") or 0))


def provider_key(m: dict) -> str:
    return str(m.get("connection_id") or m.get("access_provider") or m.get("provider") or "unknown")


def priority(m: dict) -> tuple:
    """Calibration priority across families, highest first: still to be qualified, more of the capabilities Cynqra's
    work uses stated, known to the public catalogue, a larger context. Never the release date, never the provider."""
    caps = {str(x).lower() for x in m.get("capabilities") or []}
    regression = (m.get("regression") or {}).get("status", "unverified")
    qualification = {"unverified": 2, "passed": 1, "not applicable": 1, "failed": 0}.get(regression, 2)
    return (qualification, len(caps & USEFUL), int(bool(m.get("catalogued"))), int(m.get("context") or 0))


def _order(models: list[dict]) -> list[dict]:
    """Newest of each family first inside it; families by priority, then by name for a stable order."""
    fams: dict[str, list[dict]] = {}
    fam_of = _families(models)
    for m in models:
        fams.setdefault(fam_of[m["id"]], []).append(m)
    heads, tails = [], []
    for members in fams.values():
        members.sort(key=lambda m: str(m.get("ref") or m.get("id")))
        members.sort(key=_newest_first, reverse=True)
        heads.append(members[0])
        tails.extend(members[1:])
    key = lambda m: (tuple(-x for x in priority(m)), str(m.get("ref") or m.get("id")))  # noqa: E731
    return sorted(heads, key=key) + sorted(tails, key=key)


def select(entries: list[dict], limit: int, prefer: list[str] | None = None) -> list[dict]:
    """A bounded set of at most limit candidates: the preferred ones first (an incumbent with evidence), then one per
    provider in turn, one per family, by priority; then the remaining capacity by priority."""
    limit = max(1, int(limit))
    active = [m for m in entries if m.get("status") != "retired"]
    fam_of = _families(active)
    chosen: list[dict] = []
    ids: set[str] = set()
    for pid in prefer or []:
        m = next((x for x in active if x["id"] == pid), None)
        if m is not None and m["id"] not in ids and len(chosen) < limit:
            chosen.append(m)
            ids.add(m["id"])
    families = {fam_of[m["id"]] for m in chosen}
    groups: dict[str, list[dict]] = {}
    for m in active:
        groups.setdefault(provider_key(m), []).append(m)
    for p in groups:
        groups[p] = _order(groups[p])
    while len(chosen) < limit:
        progressed = False
        for p in sorted(groups):
            pick = next((m for m in groups[p] if m["id"] not in ids and fam_of[m["id"]] not in families), None)
            if pick is None:
                continue
            chosen.append(pick)
            ids.add(pick["id"])
            families.add(fam_of[pick["id"]])
            progressed = True
            if len(chosen) >= limit:
                break
        if not progressed:
            break
    rest = [m for m in _order(active) if m["id"] not in ids]
    chosen.extend(rest[: max(0, limit - len(chosen))])
    return chosen[:limit]


def examine(entries: list[dict], limit: int, run_one, served=lambda result: True) -> tuple[list[dict], list[dict]]:
    """Qualification work on a bounded set, in select's order. A candidate its provider turns out not to serve (it
    lists the model, then answers HTTP 404, "no longer available to new users") gives its place to the next, so the
    limit counts models that can be used; at most twice the limit are tried. Returns the candidates tried and their
    results, in order."""
    limit = max(1, int(limit))
    tried, results = [], []
    for m in select(entries, len(entries)):
        if len(tried) >= 2 * limit or sum(1 for r in results if served(r)) >= limit:
            break
        tried.append(m)
        results.append(run_one(m))
    return tried, results


def details(entries: list[dict], selected: list[dict], limit: int) -> dict:
    """Why each model was or was not chosen: enough to explain the bounded set later."""
    ids = {m["id"] for m in selected}
    active = [m for m in entries if m.get("status") != "retired"]
    providers: dict[str, int] = {}
    for m in active:
        providers[provider_key(m)] = providers.get(provider_key(m), 0) + 1
    return {
        "discovered_models": len(entries), "active_models": len(active), "provider_counts": providers,
        "discovered_refs": sorted(str(m.get("ref") or "") for m in active), "selected_count": len(selected),
        "requested_limit": limit,
        "selection_policy": "metadata-only calibration priority; provider/family diversity; newest of each family; "
                            "no model-quality ranking",
        "unselected_top": [{"id": m["id"], "ref": m.get("ref"), "provider": provider_key(m),
                            "regression": (m.get("regression") or {}).get("status", "unverified"),
                            "capabilities": m.get("capabilities") or [], "context": m.get("context"),
                            "released": m.get("released")}
                           for m in _order([m for m in active if m["id"] not in ids])[:20]],
    }
