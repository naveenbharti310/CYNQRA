"""The control plane's policies: explicit, versioned and discoverable in one place (mandate 57).

Every material decision names the exact policy version it was made under, and a selection decision stores the full
body of the policies it used (controller.py), so a historical decision is replayed against the rules it was made
under, never against today's.

  system         what the platform is and the boundaries it never crosses
  authority      who may do what: the D-27/D-28 matrix (policy.py, POLICY_VERSION); referenced, not copied here
  objective      the objective's lifecycle states and which changes are material
  inheritance    what evidence a new objective version may inherit from the version before it
  selection      how an intelligence is chosen for a piece of work: hard constraints first, then evidence, with
                 cost, quality, risk and latency traded off per risk tier, never through a universal model score
  evidence       how evidence becomes selection authority: levels, weights, caps, maturity, staleness
  risk           how a work item's risk and importance are set
  budget         reservations before spend, and how much calibration and exploration may draw
  verification   what counts as independent verification, and how much each kind of check is worth
  calibration    how cold-start objective calibration is bounded and when it stops
  replacement    when an intelligence is kept, rerouted or replaced
  isolation      which evidence may cross objectives, workspaces and tenants
  retention      how long evidence keeps selection authority, and what deleting an artifact keeps

A policy body is plain data. Changing any rule changes its version; the version string is what a decision records.
"""
from __future__ import annotations

import copy

from . import policy as authority
from .db import canonical, digest

SYSTEM = {
    "version": "system-2026-10-01.1",
    "body": {
        "worker_is_not_intelligence": True,
        "credentials_never_in_evidence": True,
        "unverified_means_unknown": True,
        "no_universal_model_ranking": True,
        "worker_runtime_is_not_a_security_sandbox": True,
        "production_verification_required": True,
    },
}

OBJECTIVE = {
    "version": "objective-2026-10-01.1",
    "body": {
        "states": ["OBJECTIVE_CREATED", "OBJECTIVE_ACCEPTED", "OBJECTIVE_DECOMPOSED", "OBJECTIVE_EXECUTING",
                   "OBJECTIVE_PAUSED", "OBJECTIVE_BLOCKED", "OBJECTIVE_COMPLETED", "OBJECTIVE_VERIFIED",
                   "OBJECTIVE_CLOSED", "OBJECTIVE_CANCELLED", "OBJECTIVE_SUPERSEDED", "OBJECTIVE_REOPENED"],
        # a change to any of these fields, or to the requirements and acceptance criteria, is material: it makes a
        # new objective version. The others are editorial.
        "material_fields": ["product", "target_customer", "primary_outcome", "success_criteria", "constraints",
                            "business_outcome"],
        "editorial_fields": ["priorities"],
    },
}

INHERITANCE = {
    "version": "inheritance-2026-10-01.1",
    "body": {
        # what a new version inherits, by what changed. "full": the evidence keeps its objective authority (only
        # editorial fields changed); "prior_only": it is demoted to historical evidence of the previous version,
        # never objective evidence; "none": nothing carries over.
        "none_if_changed": ["product", "target_customer", "primary_outcome"],
        "prior_only_if_changed": ["success_criteria", "constraints", "business_outcome", "acceptance_criteria",
                                  "requirements"],
        "prior_relevance": 0.5,
    },
}

EVIDENCE = {
    "version": "evidence-2026-10-02.1",
    "body": {
        # The hierarchy, strongest first. A level's samples weigh what is written here, times their relevance,
        # verification quality, recency and version integrity; the lower levels are capped, so a long history
        # informs a new objective without outvoting what the objective itself shows, and one objective result does
        # not outvote a mature history either.
        "levels": {"objective_verified": 1, "objective_partial": 2, "historical": 3, "global": 4,
                   "capability": 5, "reputation": 6},
        "weight": {"objective_verified": 1.0, "objective_partial": 0.5, "historical": 0.5, "global": 0.25},
        "cap": {"objective_verified": None, "objective_partial": 6.0, "historical": 8.0, "global": 4.0},
        "relevance": {"same_work_item": 1.0, "same_class": 1.0, "same_requirement": 0.85,
                      "same_kind_other_role": 0.7, "proxy_kind": 0.35, "other_kind": 0.15},
        "historical_half_life_days": 90.0,
        "environment_change_factor": 0.5,  # a changed verifier or tool environment halves an item's authority
        "severity_factor": {"critical": 1.5, "major": 1.0, "minor": 0.5},
        # a success counts by how much of it was the intelligence's own: a person correcting or overriding the work
        # takes credit away; a person choosing which intelligence works (a directed reroute) does not
        "autonomy_success": {"autonomous": 1.0, "human_assisted": 0.6, "human_corrected": 0.3,
                             "human_override": 0.0, "human_directed_reroute": 1.0, "human_rejected": 0.0},
        "prior": [1.0, 1.0],  # unknown is uniform: unverified is neither bad nor best
        "z": 1.2816,  # an 80% band around the mean: lcb and ucb
        "maturity": {"thin": 0.5, "developing": 3.0, "mature": 8.0},
        "version_inheritance": "none",  # another served version's evidence never applies to this one
    },
}

RISK = {
    "version": "risk-2026-10-01.1",
    "body": {
        # importance raises a work item's tier: a requirement in these areas is critical to the company
        "critical_areas": ["security", "legal", "finance"],
        "tier_order": ["LOW", "MEDIUM", "HIGH"],
    },
}

SELECTION = {
    "version": "selection-2026-10-02.1",
    "body": {
        "rule": ("Select the candidate that satisfies all hard constraints and has the strongest policy-consistent "
                 "evidence for the specific work item, objective version and acceptance criteria, subject to risk, "
                 "budget, latency and evidence sufficiency."),
        # what makes a candidate infeasible for the work, whatever its strength (router.hard_constraints)
        "hard_constraints": ["qualified", "available", "context", "output_limit", "modality", "capability",
                             "protocol", "founder_constraints", "excluded"],
        # enforced outside selection, so never traded for quality either
        "enforced_elsewhere": {"budget_cap": "reservations and the breaker at spend time; selection prefers "
                                             "candidates whose expected cost fits the headroom",
                               "tenant_and_workspace_scope": "evidence isolation (the isolation policy)"},
        # Tradeoffs per risk tier. quality_first: the strongest evidenced quality, cost breaking ties. balanced and
        # economy: among candidates whose evidenced quality clears the floor, the lowest expected cost of a verified
        # result (money and the founder's time); when none clears it, quality first.
        "tiers": {
            "HIGH": {"tradeoff": "quality_first", "floor": "lcb", "quality_floor": 0.5, "explore": False},
            "MEDIUM": {"tradeoff": "balanced", "floor": "lcb", "quality_floor": 0.35, "explore": True},
            "LOW": {"tradeoff": "economy", "floor": "mean", "quality_floor": 0.4, "explore": True},
        },
        "attempts": 3,
        "min_context": 8192,
        "output_tokens": {"code": 8000, "forecast": 8000, "document": 3000, "default": 1500},
        "exploration": {
            # explore only when the incumbent's objective evidence is at least this mature, the challenger's is
            # thinner, and the challenger's upper bound beats the incumbent's mean
            "incumbent_maturity": "developing", "challenger_maturity": ["none", "thin"],
            "max_per_objective": 3, "budget_fraction": 0.1,
        },
        # a challenger replaces a working incumbent only on verified superiority
        "superiority": "challenger_mean_above_incumbent_ucb_or_lcb_above_mean",
    },
}

BUDGET = {
    "version": "budget-2026-10-01.1",
    "body": {
        # every model call during governed execution reserves its upper-bound cost before it starts; a call that
        # would take spent + reserved past the cap does not start
        "reservation_basis": "upper_bound",
        "reserve_in_phases": ["running"],
        "prompt_chars_per_token": 4,
        "unknown_tokens_per_second": 8.0,
    },
}

VERIFICATION = {
    "version": "verification-2026-10-01.1",
    "body": {
        # how much a check is worth as evidence about the intelligence that produced the work
        "quality": {"deterministic_platform": 1.0, "deterministic_with_own_tests": 0.8, "human": 1.0,
                    "independent_intelligence": 0.7, "self_review": 0.1, "protocol_only": 0.4,
                    "worker_claim": 0.0},
        # work at these tiers needs a verifier other than the producing intelligence; when the reviewer would run on
        # the producer's own intelligence, the review is routed to another qualified one
        "independent_review_tiers": ["HIGH"],
        "max_attempts": 3,
    },
}

CALIBRATION = {
    "version": "calibration-2026-10-01.1",
    "body": {
        "enabled": True,
        "kinds": ["code", "forecast", "document"],  # what the platform can verify before the work is real
        "max_classes": 3,
        "max_candidates": 3,
        "max_rounds": {"LOW": 1, "MEDIUM": 2, "HIGH": 2},
        "budget_fraction": 0.1,  # of the cap, and never more than what is left of it
        "stop": ["evidence_sufficiency", "candidate_separation", "coverage", "risk", "budget",
                 "information_value", "acceptance_coverage", "max_rounds"],
        "sufficient_maturity": "developing",
        "author_conflict_factor": 0.5,  # a candidate that wrote the work item it is tested on counts half
        "unmet_dependency_factor": 0.5,
    },
}

REPLACEMENT = {
    "version": "replacement-2026-10-02.1",
    "body": {
        "max_replacements": 2,
        "max_bad_replies": 3,
        "max_cut_offs": 3,  # replies in a row cut off at the model's output limit before its AI is evaluated
        "thresholds": {
            "min_verifications": 2,     # judge quality only after this many verifications on this worker and model
            "acceptance_rate": 0.5,     # below this, alternatives are evaluated
            "protocol_violations": 3,   # invalid protocol objects in this run
            "min_calls": 2,
            "failure_rate": 0.5,        # failed calls / calls
            "cost_vs_forecast": 3.0,    # cost per verified task over this multiple of the forecast per task
        },
        "provider_outage_replaces": False,
        "single_noisy_failure_replaces": False,
    },
}

ISOLATION = {
    "version": "isolation-2026-10-02.1",
    "body": {
        "objective_evidence_scope": "objective",  # objective evidence is usable only by its own objective
        # other objectives' evidence is a prior only inside the same workspace; "tenant" shares priors across a
        # tenant's workspaces. Qualification evidence is global and is not scoped.
        "historical_scope": "workspace",
        "cross_tenant": "deny",  # no aggregation policy permits cross-tenant evidence in this build
    },
}

RETENTION = {
    "version": "retention-2026-10-01.1",
    "body": {
        "archive_after_days": 365,
        "keep_on_artifact_deletion": ["hash", "verification", "decision_refs", "causal_links"],
    },
}

POLICIES = {"system": SYSTEM, "objective": OBJECTIVE, "inheritance": INHERITANCE, "selection": SELECTION,
            "evidence": EVIDENCE, "risk": RISK, "budget": BUDGET, "verification": VERIFICATION,
            "calibration": CALIBRATION, "replacement": REPLACEMENT, "isolation": ISOLATION, "retention": RETENTION}


def version(name: str) -> str:
    if name == "authority":
        return authority.POLICY_VERSION
    return POLICIES[name]["version"]


def body(name: str) -> dict:
    """A copy: a caller can never change the rules in place."""
    if name == "authority":
        return {"matrix": authority.MATRIX, "risk": authority.RISK}
    return copy.deepcopy(POLICIES[name]["body"])


def fingerprint(names) -> str:
    """The content hash of the named policies' bodies, as recorded with a decision."""
    return digest({n: {"version": version(n), "body": body(n)} for n in sorted(names)})


def catalog() -> list[dict]:
    """Every policy the control plane decides by: its name, version and content hash."""
    out = [{"name": "authority", "version": authority.POLICY_VERSION,
            "hash": digest(canonical({"matrix": authority.MATRIX, "risk": authority.RISK}))}]
    for name, p in POLICIES.items():
        out.append({"name": name, "version": p["version"], "hash": digest(p["body"])})
    return out


def effective(store=None) -> dict:
    """The policies a run decides by: the defaults, adjusted by the founder's own governance where a rule is theirs
    to set (whether calibration runs). Returned as {name: {"version", "body"}}."""
    out = {n: {"version": p["version"], "body": copy.deepcopy(p["body"])} for n, p in POLICIES.items()}
    if store is not None:
        from . import settings as project_settings
        s = project_settings.get(store)
        if s.get("objective_calibration") is False:
            out["calibration"]["body"]["enabled"] = False
            out["calibration"]["version"] += "+founder-off"
    return out
