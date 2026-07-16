"""RTM Scorer — deterministic scoring from traceability matrix entries."""
from __future__ import annotations

from skuld.models import AcceptanceCriterion, RTMEntry
from skuld.rtm_builder import find_gaps

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

_WEIGHT_AC_COVERAGE = 0.30
_WEIGHT_NEGATIVE = 0.25
_WEIGHT_EDGE = 0.20
_WEIGHT_DISTRIBUTION = 0.15
_WEIGHT_ORPHAN_PENALTY = 0.10

_REQUIRED_TYPES = {"functional", "negative", "edge-case"}

_TIER_HIGH = 80.0
_TIER_MEDIUM = 50.0


# ---------------------------------------------------------------------------
# Sub-score functions
# ---------------------------------------------------------------------------


def _compute_ac_coverage(
    rtm_entries: list[RTMEntry], ac_list: list[AcceptanceCriterion]
) -> float:
    """Ratio of ACs that have at least one RTM entry. 0.0–1.0."""
    if not ac_list:
        return 1.0
    valid_ac_ids = {ac.id for ac in ac_list}
    covered = {e.ac_id for e in rtm_entries if e.ac_id in valid_ac_ids}
    return len(covered) / len(ac_list)


def _compute_negative_coverage(
    rtm_entries: list[RTMEntry], ac_list: list[AcceptanceCriterion]
) -> float:
    """Ratio of ACs that have at least one negative test entry. 0.0–1.0."""
    if not ac_list:
        return 1.0
    valid_ac_ids = {ac.id for ac in ac_list}
    covered = {
        e.ac_id for e in rtm_entries
        if e.test_type == "negative" and e.ac_id in valid_ac_ids
    }
    return len(covered) / len(ac_list)


def _compute_edge_coverage(
    rtm_entries: list[RTMEntry], ac_list: list[AcceptanceCriterion]
) -> float:
    """Ratio of ACs that have at least one edge-case test entry. 0.0–1.0."""
    if not ac_list:
        return 1.0
    valid_ac_ids = {ac.id for ac in ac_list}
    covered = {
        e.ac_id for e in rtm_entries
        if e.test_type == "edge-case" and e.ac_id in valid_ac_ids
    }
    return len(covered) / len(ac_list)


def _compute_type_distribution(rtm_entries: list[RTMEntry]) -> float:
    """Score based on whether all required test types are present.

    Returns 1.0 if all three types (functional, negative, edge-case) exist,
    proportionally less for missing types.
    """
    if not rtm_entries:
        return 0.0

    present_types: set[str] = set()
    for e in rtm_entries:
        if e.test_type in _REQUIRED_TYPES:
            present_types.add(e.test_type)

    return len(present_types) / len(_REQUIRED_TYPES)


def _compute_orphan_penalty(
    rtm_entries: list[RTMEntry], ac_list: list[AcceptanceCriterion]
) -> float:
    """Ratio of entries referencing ACs not in the canonical list. 0.0–1.0."""
    if not rtm_entries:
        return 0.0
    valid_ac_ids = {ac.id for ac in ac_list}
    orphans = sum(1 for e in rtm_entries if e.ac_id not in valid_ac_ids)
    return orphans / len(rtm_entries)


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------


def score_rtm(
    rtm_entries: list[RTMEntry], ac_list: list[AcceptanceCriterion]
) -> float:
    """Weighted composite RTM score. Returns 0.0–100.0."""
    if not ac_list:
        return 0.0
    return score_rtm_detailed(rtm_entries, ac_list)["composite"]


def score_rtm_detailed(
    rtm_entries: list[RTMEntry], ac_list: list[AcceptanceCriterion]
) -> dict:
    """Score RTM and return detailed breakdown for ConfidenceScore.rtm_details."""
    if not ac_list:
        return {
            "ac_coverage": 0.0,
            "negative_coverage": 0.0,
            "edge_coverage": 0.0,
            "type_distribution": 0.0,
            "orphan_penalty": 0.0,
            "composite": 0.0,
            "tier": "low",
            "gaps": [],
        }

    ac_cov = _compute_ac_coverage(rtm_entries, ac_list)
    neg_cov = _compute_negative_coverage(rtm_entries, ac_list)
    edge_cov = _compute_edge_coverage(rtm_entries, ac_list)
    dist = _compute_type_distribution(rtm_entries)
    orphan = _compute_orphan_penalty(rtm_entries, ac_list)

    positive_sum = (
        _WEIGHT_AC_COVERAGE * ac_cov
        + _WEIGHT_NEGATIVE * neg_cov
        + _WEIGHT_EDGE * edge_cov
        + _WEIGHT_DISTRIBUTION * dist
    )
    positive_weights = _WEIGHT_AC_COVERAGE + _WEIGHT_NEGATIVE + _WEIGHT_EDGE + _WEIGHT_DISTRIBUTION
    normalized = positive_sum / positive_weights if positive_weights > 0 else 0.0
    raw = (normalized - _WEIGHT_ORPHAN_PENALTY * orphan) * 100.0
    composite = max(0.0, min(100.0, raw))
    gaps = find_gaps(rtm_entries, ac_list)

    return {
        "ac_coverage": round(ac_cov, 4),
        "negative_coverage": round(neg_cov, 4),
        "edge_coverage": round(edge_cov, 4),
        "type_distribution": round(dist, 4),
        "orphan_penalty": round(orphan, 4),
        "composite": round(composite, 2),
        "tier": assign_tier(composite),
        "gaps": gaps,
    }


def assign_tier(score: float) -> str:
    """Map numeric score to tier label."""
    if score >= _TIER_HIGH:
        return "high"
    if score >= _TIER_MEDIUM:
        return "medium"
    return "low"
