"""Confidence Scorer — combines RTM + adversarial scores into ConfidenceScore."""
from __future__ import annotations

import math

from skuld.models import ConfidenceScore
from skuld.rtm_scorer import assign_tier


def compute_confidence(
    rtm_score: float,
    adversarial_score: float | None,
    gaps: list[str],
    rtm_details: dict,
    weights: tuple[float, float] = (0.70, 0.30),
) -> ConfidenceScore:
    """Combine RTM and adversarial scores into a final ConfidenceScore.

    If adversarial_score is None (deterministic-only mode), the overall score
    equals rtm_score directly. Otherwise the weighted combination is used.
    The result is clamped to [0.0, 100.0].
    """
    if not math.isfinite(rtm_score):
        raise ValueError(f"rtm_score must be finite, got {rtm_score}")
    if adversarial_score is not None and not math.isfinite(adversarial_score):
        raise ValueError(f"adversarial_score must be finite, got {adversarial_score}")

    if any(w < 0.0 for w in weights):
        raise ValueError(f"Weights must be non-negative, got {weights}")
    if sum(weights) == 0.0:
        raise ValueError("Weights must not both be zero")

    if adversarial_score is None:
        overall = rtm_score
    else:
        overall = weights[0] * rtm_score + weights[1] * adversarial_score

    overall = max(0.0, min(100.0, overall))

    return ConfidenceScore(
        overall=overall,
        rtm_score=rtm_score,
        adversarial_score=adversarial_score,
        rtm_details=dict(rtm_details),
        gaps=list(gaps),
        tier=assign_tier(overall),
    )


def compute_confidence_from_detailed(
    rtm_detailed: dict,
    adversarial_score: float | None,
    weights: tuple[float, float] = (0.70, 0.30),
) -> ConfidenceScore:
    """Convenience wrapper that extracts fields from score_rtm_detailed() output.

    Pulls 'composite' as rtm_score, 'gaps' as gaps, and passes remaining
    keys as rtm_details.
    """
    for key in ("composite", "gaps"):
        if key not in rtm_detailed:
            raise ValueError(f"rtm_detailed missing required key '{key}'")

    composite = rtm_detailed["composite"]
    gaps = rtm_detailed["gaps"]
    rtm_tier = rtm_detailed.get("tier", "low")
    rtm_details = {k: v for k, v in rtm_detailed.items() if k not in ("composite", "gaps", "tier")}
    # Preserve RTM tier in details for reference
    rtm_details["rtm_tier"] = rtm_tier

    return compute_confidence(
        rtm_score=composite,
        adversarial_score=adversarial_score,
        gaps=gaps,
        rtm_details=rtm_details,
        weights=weights,
    )
