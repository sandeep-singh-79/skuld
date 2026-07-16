"""Tests for skuld.confidence_scorer — T7 Confidence Scorer."""
from __future__ import annotations

import pytest

from skuld.confidence_scorer import compute_confidence, compute_confidence_from_detailed
from skuld.models import ConfidenceScore


class TestComputeConfidence:
    """Unit tests for compute_confidence()."""

    def test_rtm_only_when_adversarial_none(self):
        """When adversarial_score is None, overall = rtm_score (100% weight)."""
        result = compute_confidence(
            rtm_score=72.5,
            adversarial_score=None,
            gaps=["missing negative for AC-2"],
            rtm_details={"ac_coverage": 0.8},
        )
        assert result.overall == 72.5

    def test_weighted_combination_70_30(self):
        """Default weights: 70% RTM + 30% adversarial."""
        result = compute_confidence(
            rtm_score=80.0,
            adversarial_score=60.0,
            gaps=[],
            rtm_details={},
        )
        expected = 0.70 * 80.0 + 0.30 * 60.0  # 56 + 18 = 74.0
        assert result.overall == pytest.approx(expected)

    def test_custom_weights(self):
        """Custom weights (0.60, 0.40) applied correctly."""
        result = compute_confidence(
            rtm_score=80.0,
            adversarial_score=60.0,
            gaps=[],
            rtm_details={},
            weights=(0.60, 0.40),
        )
        expected = 0.60 * 80.0 + 0.40 * 60.0  # 48 + 24 = 72.0
        assert result.overall == pytest.approx(expected)

    def test_clamp_to_zero(self):
        """Negative result is clamped to 0.0."""
        # Artificially force a negative by passing negative scores
        result = compute_confidence(
            rtm_score=-10.0,
            adversarial_score=-20.0,
            gaps=[],
            rtm_details={},
        )
        assert result.overall == 0.0

    def test_clamp_to_hundred(self):
        """Result over 100.0 is clamped to 100.0."""
        result = compute_confidence(
            rtm_score=120.0,
            adversarial_score=110.0,
            gaps=[],
            rtm_details={},
        )
        assert result.overall == 100.0

    def test_perfect_scores(self):
        """Both scores 100.0 → overall 100.0."""
        result = compute_confidence(
            rtm_score=100.0,
            adversarial_score=100.0,
            gaps=[],
            rtm_details={},
        )
        assert result.overall == 100.0

    def test_zero_scores(self):
        """Both scores 0.0 → overall 0.0."""
        result = compute_confidence(
            rtm_score=0.0,
            adversarial_score=0.0,
            gaps=[],
            rtm_details={},
        )
        assert result.overall == 0.0

    def test_gaps_preserved(self):
        """Gaps list is passed through unchanged."""
        gaps = ["no edge-case for AC-1", "no negative for AC-3"]
        result = compute_confidence(
            rtm_score=60.0,
            adversarial_score=None,
            gaps=gaps,
            rtm_details={},
        )
        assert result.gaps == gaps

    def test_rtm_details_preserved(self):
        """RTM details dict is passed through unchanged."""
        details = {"ac_coverage": 0.9, "negative_coverage": 0.5, "tier": "high"}
        result = compute_confidence(
            rtm_score=85.0,
            adversarial_score=None,
            gaps=[],
            rtm_details=details,
        )
        assert result.rtm_details == details

    def test_returns_confidence_score_dataclass(self):
        """Return value is a ConfidenceScore instance."""
        result = compute_confidence(
            rtm_score=50.0,
            adversarial_score=70.0,
            gaps=[],
            rtm_details={},
        )
        assert isinstance(result, ConfidenceScore)


class TestComputeConfidenceFromDetailed:
    """Unit tests for compute_confidence_from_detailed()."""

    def test_extracts_composite_and_gaps(self):
        """Extracts composite as rtm_score and gaps from detailed dict."""
        rtm_detailed = {
            "ac_coverage": 0.8,
            "negative_coverage": 0.6,
            "edge_coverage": 0.4,
            "type_distribution": 1.0,
            "orphan_penalty": 0.0,
            "composite": 75.0,
            "tier": "medium",
            "gaps": ["no edge-case for AC-2"],
        }
        result = compute_confidence_from_detailed(
            rtm_detailed=rtm_detailed,
            adversarial_score=60.0,
        )
        expected_overall = 0.70 * 75.0 + 0.30 * 60.0  # 52.5 + 18 = 70.5
        assert result.overall == pytest.approx(expected_overall)
        assert result.rtm_score == 75.0
        assert result.adversarial_score == 60.0
        assert result.gaps == ["no edge-case for AC-2"]
        # rtm_details should contain the non-composite, non-gaps keys
        assert "ac_coverage" in result.rtm_details
        assert "composite" not in result.rtm_details
        assert "gaps" not in result.rtm_details

    def test_adversarial_none_fallback(self):
        """When adversarial_score is None, uses RTM-only mode."""
        rtm_detailed = {
            "ac_coverage": 1.0,
            "negative_coverage": 1.0,
            "edge_coverage": 1.0,
            "type_distribution": 1.0,
            "orphan_penalty": 0.0,
            "composite": 90.0,
            "tier": "high",
            "gaps": [],
        }
        result = compute_confidence_from_detailed(
            rtm_detailed=rtm_detailed,
            adversarial_score=None,
        )
        assert result.overall == 90.0
        assert result.adversarial_score is None


class TestInputValidation:
    """Tests for input validation in compute_confidence()."""

    def test_nan_rtm_score_raises(self):
        with pytest.raises(ValueError, match="finite"):
            compute_confidence(float("nan"), None, [], {})

    def test_inf_adversarial_raises(self):
        with pytest.raises(ValueError, match="finite"):
            compute_confidence(50.0, float("inf"), [], {})

    def test_negative_weights_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            compute_confidence(50.0, 50.0, [], {}, weights=(1.5, -0.5))

    def test_zero_weights_raises(self):
        with pytest.raises(ValueError, match="zero"):
            compute_confidence(50.0, 50.0, [], {}, weights=(0.0, 0.0))

    def test_mutation_isolation(self):
        gaps = ["gap1"]
        details = {"ac_coverage": 0.5}
        cs = compute_confidence(80.0, None, gaps, details)
        gaps.append("gap2")
        details["new_key"] = "mutated"
        assert len(cs.gaps) == 1
        assert "new_key" not in cs.rtm_details

    def test_tier_field_populated(self):
        cs = compute_confidence(85.0, None, [], {})
        assert cs.tier == "high"

    def test_tier_from_detailed(self):
        detailed = {"composite": 75.0, "gaps": ["gap1"], "tier": "medium", "ac_coverage": 0.8}
        cs = compute_confidence_from_detailed(detailed, None)
        assert cs.tier == "medium"

    def test_from_detailed_missing_key_raises(self):
        with pytest.raises(ValueError, match="missing required key"):
            compute_confidence_from_detailed({"gaps": []}, None)  # missing "composite"

    def test_tier_derived_from_overall_not_rtm(self):
        """When adversarial drags overall below RTM tier threshold, tier reflects overall."""
        detailed = {
            "composite": 90.0,  # RTM tier would be "high"
            "gaps": [],
            "tier": "high",
            "ac_coverage": 1.0,
        }
        # Adversarial score of 0 → overall = 0.7*90 + 0.3*0 = 63 → "medium"
        result = compute_confidence_from_detailed(detailed, adversarial_score=0.0)
        assert result.overall == pytest.approx(63.0, abs=0.1)
        assert result.tier == "medium"  # NOT "high"

    def test_rtm_tier_preserved_in_details(self):
        """RTM-specific tier is kept in rtm_details for reference."""
        detailed = {
            "composite": 90.0,
            "gaps": [],
            "tier": "high",
            "ac_coverage": 1.0,
        }
        result = compute_confidence_from_detailed(detailed, adversarial_score=0.0)
        assert result.rtm_details["rtm_tier"] == "high"


class TestScorerIntegration:
    """Integration test chaining score_rtm_detailed → compute_confidence_from_detailed."""

    def test_full_pipeline_chain(self):
        """Real objects through scorer pipeline — no hand-crafted dicts."""
        from skuld.models import AcceptanceCriterion, RTMEntry
        from skuld.rtm_scorer import score_rtm_detailed

        acs = [
            AcceptanceCriterion(id="AC-1", description="Login works"),
            AcceptanceCriterion(id="AC-2", description="Error shown"),
        ]
        entries = [
            RTMEntry(ac_id="AC-1", test_case_id="TC-1", test_type="functional"),
            RTMEntry(ac_id="AC-1", test_case_id="TC-2", test_type="negative"),
            RTMEntry(ac_id="AC-1", test_case_id="TC-3", test_type="edge-case"),
            RTMEntry(ac_id="AC-2", test_case_id="TC-4", test_type="functional"),
            RTMEntry(ac_id="AC-2", test_case_id="TC-5", test_type="negative"),
        ]

        detailed = score_rtm_detailed(entries, acs)
        result = compute_confidence_from_detailed(detailed, adversarial_score=None)

        assert result.overall == detailed["composite"]
        assert result.tier in ("high", "medium", "low")
        assert isinstance(result.gaps, list)
        assert result.adversarial_score is None
        assert result.rtm_details["rtm_tier"] == detailed["tier"]
