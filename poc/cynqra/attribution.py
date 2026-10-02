"""Failure attribution: what caused a failure, and whether it may teach Cynqra anything about the intelligence.

Only a failure the intelligence is causally responsible for updates its quality evidence. Everything else is kept
on the record, marked contaminated, and never learned from (mandate 15):

  provider       the provider's side: an outage, HTTP 408/409/425/429 or 5xx, a timeout, a dropped connection
  account        no credit, or a refused key: the founder's to fix
  network        the network between Cynqra and the provider
  tool           a governed tool that broke (a command timed out, a runtime error), not the request for it
  environment    this machine: the budget breaker, the kill switch, a disk or interpreter problem
  specification  a missing input or an ambiguous requirement: a Blocker, a frozen acceptance criterion tampered with
  verification   the check itself was wrong: a false rejection later confirmed
  execution      the platform's own execution failed around the work
  cancelled      the work was stopped (the kill switch, an objective change) before it could finish
  human          a person's decision (an override, a directed reroute) rather than the intelligence's work
  intelligence   incorrect work despite valid requirements and tools: a failed check, a protocol violation, an unsafe
                 tool request, a reply cut off or unreadable

HTTP 503 is a provider failure; a database that will not open is an environment failure; an ambiguous requirement
is a specification failure; incorrect code against valid requirements and working tools is an intelligence failure.
"""
from __future__ import annotations

import re

CAUSES = ("provider", "account", "network", "tool", "environment", "specification", "verification", "execution",
          "cancelled", "human", "intelligence")
INTELLIGENCE = "intelligence"

# Why a call failed. The provider's HTTP status says it best ("HTTP 402 from provider: ..."); the words of the
# message are read only when there is no status, and only as whole phrases, so a port number such as :40312 or a
# local "insufficient memory" is never mistaken for a refused key or an empty account. Anything unrecognised counts
# as the provider's side, the cautious reading: waiting costs time, replacing a capable AI costs its record.
_STATUS = re.compile(r"\bHTTP (\d{3})\b")
_CREDIT = re.compile(r"credits?\b|billing|payment required|insufficient[_ ](quota|credit|balance|funds)", re.I)
# A free tier's limit often names billing (Google: "check your plan and billing details"; Groq links its billing page
# under "Please try again in 26m3s"): the limit's name, or the provider saying when to try again, marks a limit that
# passes (a rate limit, the provider's side), not an empty account
_PER_MINUTE = re.compile(r"per ?minute|(?:retry|try again) in \d", re.I)
PHRASES = (
    ("no_credit", _CREDIT),
    ("access", re.compile(r"invalid api key|unauthori[sz]ed|forbidden|authentication|is not set\b|"
                          r"credential is missing|stored key is missing", re.I)),
    ("rate_limit", re.compile(r"rate limit|too many requests", re.I)),
    ("timeout", re.compile(r"timed out|\btimeout\b", re.I)),
    ("withdrawn", re.compile(r"\bretired\b|connection was removed|regression check", re.I)),
    # the provider answered, but the AI's own reply could not be used: its fault, never the provider's
    ("reply", re.compile(r"reply truncated|did not return a JSON object|did not follow the required format|"
                         r"returned no answer", re.I)),
)


def diagnose(error: str) -> str:
    """Why a call failed: outage, timeout, rate_limit, no_credit, access, withdrawn (the AI can no longer be used) or
    reply (its own reply was unusable). None but reply says the AI cannot do the work; that is known only from its
    work (verification, cut-offs, protocol violations, its measured record)."""
    e = error or ""
    m = _STATUS.search(e)
    if m:
        code = int(m.group(1))
        if code == 429 and _PER_MINUTE.search(e):  # a free tier's per-minute limit, however its message words it
            return "rate_limit"
        # an empty account: 402, or a 400/403/429 that says so (one provider answers a low credit balance with 400)
        if code == 402 or (code in (400, 403, 429) and _CREDIT.search(e)):
            return "no_credit"
        if code in (401, 403):
            return "access"
        if code == 404:  # the provider no longer serves this model
            return "withdrawn"
        if code == 429:
            return "rate_limit"
        if code in (408, 504):
            return "timeout"
        return "outage"
    for cause, pattern in PHRASES:
        if pattern.search(e):
            return cause
    return "outage"


# a call's diagnosis, as an attribution
CALL_CAUSE = {"outage": "provider", "timeout": "provider", "rate_limit": "provider", "no_credit": "account",
              "access": "account", "withdrawn": "provider", "reply": INTELLIGENCE}
_NETWORK = re.compile(r"network error|could not reach|connection (refused|reset)|remote end closed|name resolution|"
                      r"temporarily unavailable", re.I)
_ENVIRONMENT = re.compile(r"no space left|disk full|permission denied|read-only file system|database is locked|"
                          r"unable to open database|python[0-9.]*: (not found|command not found)|"
                          r"cannot allocate memory|\[errno (28|13|30)\]", re.I)
_TOOL = re.compile(r"command timed out after|not in the runtime allowlist|runtime (read|write) limit|"
                   r"tool .* (crashed|failed to start)", re.I)


def call_failure(error: str) -> dict:
    """A failed model call, attributed. HTTP 408/409/425/429 and 5xx, timeouts, network failures, a remote end that
    closed and temporary unavailability are the provider's side: inconclusive about the intelligence."""
    cause = diagnose(error)
    kind = CALL_CAUSE.get(cause, "provider")
    if kind == "provider" and _NETWORK.search(error or ""):
        kind = "network"
    return failure(kind, cause, error)


def verification_failure(feedback: str, checks: dict | None = None) -> dict:
    """A failed verification of delivered work: the intelligence's, unless the check could not run because of this
    machine (a full disk, a locked database, a missing interpreter) or a broken tool."""
    text = (feedback or "") + " " + str((checks or {}).get("output") or "")
    if _ENVIRONMENT.search(text):
        return failure("environment", "the verifier could not run on this machine", feedback)
    if _TOOL.search(text):
        return failure("tool", "a governed tool failed during verification", feedback)
    return failure(INTELLIGENCE, "the work failed its verification", feedback)


def tool_failure(status: str, reason: str) -> dict:
    """A governed tool request that did not execute. A request the rules refuse (a path outside the workspace, a
    credential in a file, a tool not on the list) is the intelligence's; the breaker, the kill switch and a tool
    that broke are not."""
    r = reason or ""
    if re.search(r"kill switch|breaker|budget", r, re.I):
        return failure("environment", "the platform had paused work", r)
    if _TOOL.search(r) or _ENVIRONMENT.search(r):
        return failure("tool", "the tool itself failed", r)
    if status == "requires_approval":
        return failure("human", "the action waits for an approval", r)
    return failure(INTELLIGENCE, "the request broke the workspace or tool rules", r)


def failure(kind: str, why: str, detail: str = "") -> dict:
    if kind not in CAUSES:
        raise ValueError(f"unknown failure attribution {kind!r}")
    return {"kind": kind, "reason": why[:200], "detail": (detail or "")[:300],
            "attributable_to_intelligence": kind == INTELLIGENCE}


def clean(attribution: dict | None) -> bool:
    """Whether a record may update intelligence quality: a success, or a failure the intelligence caused."""
    return attribution is None or bool(attribution.get("attributable_to_intelligence"))
