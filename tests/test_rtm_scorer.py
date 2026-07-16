"""Tests for skuld.rtm_scorer — deterministic RTM scoring."""
from __future__ import annotations

import pytest

from skuld.models import AcceptanceCriterion, RTMEntry
from skuld.rtm_scorer import (
    _compute_ac_coverage,
    _compute_edge_coverage,
    _compute_negative_coverage,
    _compute_orphan_penalty,
    _compute_type_distribution,
    assign_tier,
    score_rtm,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ac(id: str) -> AcceptanceCriterion:
    return AcceptanceCriterion(id=id, description=f"AC {id}")


def _entry(ac_id: str, test_type: str = "functional", tc_id: str | None = None) -> RTMEntry:
    return RTMEntry(
        ac_id=ac_id,
        test_case_id=tc_id or f"TC-{ac_id}-{test_type}",
        test_type=test_type,
    )


# ---------------------------------------------------------------------------
# TestComputeACCoverage
# ---------------------------------------------------------------------------


class TestComputeACCoverage:
    def test_all_acs_covered(self):
        acs = [_ac("AC-1"), _ac("AC-2"), _ac("AC-3")]
        entries = [_entry("AC-1"), _entry("AC-2"), _entry("AC-3")]
        assert _compute_ac_coverage(entries, acs) == 1.0

    def test_no_acs_covered(self):
        acs = [_ac("AC-1"), _ac("AC-2")]
        entries = [_entry("AC-99")]  # references non-existent AC
        assert _compute_ac_coverage(entries, acs) == 0.0

    def test_partial_coverage(self):
        acs = [_ac("AC-1"), _ac("AC-2"), _ac("AC-3"), _ac("AC-4")]
        entries = [_entry("AC-1"), _entry("AC-3")]
        assert _compute_ac_coverage(entries, acs) == pytest.approx(0.5)

    def test_empty_ac_list(self):
        entries = [_entry("AC-1")]
        assert _compute_ac_coverage(entries, []) == 1.0

    def test_empty_entries(self):
        acs = [_ac("AC-1"), _ac("AC-2")]
        assert _compute_ac_coverage([], acs) == 0.0


# ---------------------------------------------------------------------------
# TestComputeNegativeCoverage
# ---------------------------------------------------------------------------


class TestComputeNegativeCoverage:
    def test_all_acs_have_negative(self):
        acs = [_ac("AC-1"), _ac("AC-2")]
        entries = [
            _entry("AC-1", "negative"),
            _entry("AC-2", "negative"),
        ]
        assert _compute_negative_coverage(entries, acs) == 1.0

    def test_no_negatives(self):
        acs = [_ac("AC-1"), _ac("AC-2")]
        entries = [_entry("AC-1", "functional"), _entry("AC-2", "functional")]
        assert _compute_negative_coverage(entries, acs) == 0.0

    def test_partial_negative(self):
        acs = [_ac("AC-1"), _ac("AC-2"), _ac("AC-3")]
        entries = [
            _entry("AC-1", "negative"),
            _entry("AC-2", "functional"),
            _entry("AC-3", "functional"),
        ]
        assert _compute_negative_coverage(entries, acs) == pytest.approx(1 / 3)

    def test_empty_ac_list(self):
        entries = [_entry("AC-1", "negative")]
        assert _compute_negative_coverage(entries, []) == 1.0


# ---------------------------------------------------------------------------
# TestComputeEdgeCoverage
# ---------------------------------------------------------------------------


class TestComputeEdgeCoverage:
    def test_all_acs_have_edge(self):
        acs = [_ac("AC-1"), _ac("AC-2")]
        entries = [
            _entry("AC-1", "edge-case"),
            _entry("AC-2", "edge-case"),
        ]
        assert _compute_edge_coverage(entries, acs) == 1.0

    def test_no_edge_cases(self):
        acs = [_ac("AC-1"), _ac("AC-2")]
        entries = [_entry("AC-1", "functional"), _entry("AC-2", "negative")]
        assert _compute_edge_coverage(entries, acs) == 0.0

    def test_partial_edge(self):
        acs = [_ac("AC-1"), _ac("AC-2"), _ac("AC-3"), _ac("AC-4")]
        entries = [
            _entry("AC-1", "edge-case"),
            _entry("AC-2", "edge-case"),
            _entry("AC-3", "functional"),
            _entry("AC-4", "functional"),
        ]
        assert _compute_edge_coverage(entries, acs) == pytest.approx(0.5)

    def test_empty_ac_list(self):
        entries = [_entry("AC-1", "edge-case")]
        assert _compute_edge_coverage(entries, []) == 1.0


# ---------------------------------------------------------------------------
# TestComputeTypeDistribution
# ---------------------------------------------------------------------------


class TestComputeTypeDistribution:
    def test_balanced_distribution(self):
        # 40% functional, 30% negative, 30% edge-case → all above minimums
        entries = [
            _entry("AC-1", "functional", "TC-1"),
            _entry("AC-1", "functional", "TC-2"),
            _entry("AC-1", "functional", "TC-3"),
            _entry("AC-2", "functional", "TC-4"),
            _entry("AC-2", "negative", "TC-5"),
            _entry("AC-2", "negative", "TC-6"),
            _entry("AC-2", "negative", "TC-7"),
            _entry("AC-3", "edge-case", "TC-8"),
            _entry("AC-3", "edge-case", "TC-9"),
            _entry("AC-3", "edge-case", "TC-10"),
        ]
        assert _compute_type_distribution(entries) == pytest.approx(1.0)

    def test_all_functional_no_others(self):
        """Only one type present → distribution = 1/3."""
        entries = [_entry("AC-1", "functional"), _entry("AC-2", "functional")]
        result = _compute_type_distribution(entries)
        assert abs(result - 1/3) < 0.01

    def test_empty_entries(self):
        assert _compute_type_distribution([]) == 0.0


# ---------------------------------------------------------------------------
# TestComputeOrphanPenalty
# ---------------------------------------------------------------------------


class TestComputeOrphanPenalty:
    def test_no_orphans(self):
        acs = [_ac("AC-1"), _ac("AC-2")]
        entries = [_entry("AC-1"), _entry("AC-2")]
        assert _compute_orphan_penalty(entries, acs) == 0.0

    def test_all_orphans(self):
        acs = [_ac("AC-1")]
        entries = [_entry("AC-99"), _entry("AC-100")]
        assert _compute_orphan_penalty(entries, acs) == 1.0

    def test_mixed(self):
        acs = [_ac("AC-1"), _ac("AC-2")]
        entries = [_entry("AC-1"), _entry("AC-2"), _entry("AC-99"), _entry("AC-100")]
        assert _compute_orphan_penalty(entries, acs) == pytest.approx(0.5)

    def test_empty_entries(self):
        acs = [_ac("AC-1")]
        assert _compute_orphan_penalty([], acs) == 0.0


# ---------------------------------------------------------------------------
# TestScoreRTM
# ---------------------------------------------------------------------------


class TestScoreRTM:
    def test_perfect_score(self):
        acs = [_ac("AC-1"), _ac("AC-2"), _ac("AC-3")]
        # Each AC has functional, negative, and edge-case entries → perfect coverage
        entries = []
        for ac in acs:
            entries.append(_entry(ac.id, "functional", f"TC-{ac.id}-func"))
            entries.append(_entry(ac.id, "negative", f"TC-{ac.id}-neg"))
            entries.append(_entry(ac.id, "edge-case", f"TC-{ac.id}-edge"))
        score = score_rtm(entries, acs)
        assert score == pytest.approx(100.0, abs=1.0)

    def test_zero_score(self):
        acs = [_ac("AC-1"), _ac("AC-2")]
        score = score_rtm([], acs)
        assert score == 0.0

    def test_clamped_to_range(self):
        # Even adversarial inputs shouldn't go out of bounds
        acs = [_ac("AC-1")]
        entries = [_entry("AC-1", "functional")]
        score = score_rtm(entries, acs)
        assert 0.0 <= score <= 100.0

    def test_partial_realistic(self):
        acs = [_ac("AC-1"), _ac("AC-2"), _ac("AC-3"), _ac("AC-4")]
        entries = [
            _entry("AC-1", "functional", "TC-1"),
            _entry("AC-1", "negative", "TC-2"),
            _entry("AC-2", "functional", "TC-3"),
            _entry("AC-3", "edge-case", "TC-4"),
        ]
        score = score_rtm(entries, acs)
        assert 20.0 < score < 80.0

    def test_all_orphan_entries(self):
        """All entries reference non-existent ACs — should score very low."""
        acs = [AcceptanceCriterion(id="AC-1", description="X"), AcceptanceCriterion(id="AC-2", description="Y")]
        entries = [_entry("AC-99", "functional"), _entry("AC-100", "negative"), _entry("AC-101", "edge-case")]
        score = score_rtm(entries, acs)
        assert score < 20.0

    def test_empty_ac_list_returns_zero(self):
        """Empty AC list should return 0.0, not a high score."""
        entries = [_entry("AC-1", "functional"), _entry("AC-1", "negative")]
        score = score_rtm(entries, [])
        assert score == 0.0


# ---------------------------------------------------------------------------
# TestScoreRTMDetailed
# ---------------------------------------------------------------------------


class TestScoreRTMDetailed:
    def test_returns_all_keys(self):
        from skuld.rtm_scorer import score_rtm_detailed

        acs = [AcceptanceCriterion(id="AC-1", description="X")]
        entries = [_entry("AC-1", "functional"), _entry("AC-1", "negative"), _entry("AC-1", "edge-case")]
        result = score_rtm_detailed(entries, acs)
        assert "ac_coverage" in result
        assert "negative_coverage" in result
        assert "edge_coverage" in result
        assert "type_distribution" in result
        assert "orphan_penalty" in result
        assert "composite" in result
        assert "tier" in result

    def test_composite_matches_score_rtm(self):
        from skuld.rtm_scorer import score_rtm_detailed

        acs = [AcceptanceCriterion(id="AC-1", description="X")]
        entries = [_entry("AC-1", "functional"), _entry("AC-1", "negative"), _entry("AC-1", "edge-case")]
        detailed = score_rtm_detailed(entries, acs)
        scalar = score_rtm(entries, acs)
        assert detailed["composite"] == round(scalar, 2)

    def test_empty_ac_list_all_zeros(self):
        from skuld.rtm_scorer import score_rtm_detailed

        result = score_rtm_detailed([_entry("AC-1", "functional")], [])
        assert result["composite"] == 0.0
        assert result["tier"] == "low"
        assert result["gaps"] == []


# ---------------------------------------------------------------------------
# TestAssignTier
# ---------------------------------------------------------------------------


class TestAssignTier:
    def test_high_tier(self):
        assert assign_tier(90.0) == "high"

    def test_medium_tier(self):
        assert assign_tier(65.0) == "medium"

    def test_low_tier(self):
        assert assign_tier(30.0) == "low"

    def test_boundary_79_99(self):
        assert assign_tier(79.99) == "medium"

    def test_boundary_49_99(self):
        assert assign_tier(49.99) == "low"


# ---------------------------------------------------------------------------
# TestAddingTestsNeverDecreasesScore
# ---------------------------------------------------------------------------


class TestAddingTestsNeverDecreasesScore:
    def test_adding_tests_never_decreases_score(self):
        """Adding more tests of any type should never decrease the composite score."""
        from skuld.models import AcceptanceCriterion
        acs = [AcceptanceCriterion(id="AC-1", description="X")]

        base_entries = [
            _entry("AC-1", "functional"),
            _entry("AC-1", "negative"),
            _entry("AC-1", "edge-case"),
        ]
        base_score = score_rtm(base_entries, acs)

        # Add 10 more functional tests
        more_entries = base_entries + [_entry("AC-1", "functional", f"TC-extra-{i}") for i in range(10)]
        new_score = score_rtm(more_entries, acs)

        assert new_score >= base_score


# ---------------------------------------------------------------------------
# TestDetailedIncludesGaps
# ---------------------------------------------------------------------------


class TestDetailedIncludesGaps:
    def test_detailed_includes_gaps(self):
        from skuld.rtm_scorer import score_rtm_detailed
        from skuld.models import AcceptanceCriterion
        acs = [AcceptanceCriterion(id="AC-1", description="X"), AcceptanceCriterion(id="AC-2", description="Y")]
        entries = [_entry("AC-1", "functional")]  # AC-2 has no coverage, AC-1 missing neg/edge
        result = score_rtm_detailed(entries, acs)
        assert "gaps" in result
        assert len(result["gaps"]) > 0
        assert any("AC-2" in g for g in result["gaps"])


# ---------------------------------------------------------------------------
# TestScorerStoreIntegration
# ---------------------------------------------------------------------------


class TestScorerStoreIntegration:
    """Verify scorer only processes active entries when used with RTMStore."""

    def test_superseded_entries_excluded_from_scoring(self):
        """Scoring store.active_entries excludes superseded entries."""
        from skuld.rtm_store import RTMStore
        from skuld.models import AcceptanceCriterion
        from skuld.rtm_scorer import score_rtm

        store = RTMStore()
        store.merge([
            RTMEntry(ac_id="AC-1", test_case_id="TC-1", test_type="functional"),
            RTMEntry(ac_id="AC-1", test_case_id="TC-2", test_type="negative"),
            RTMEntry(ac_id="AC-1", test_case_id="TC-3", test_type="edge-case"),
        ], story_id="S-1", run_id="run-1")

        # Re-merge with only functional — old entries become superseded
        store.merge([
            RTMEntry(ac_id="AC-1", test_case_id="TC-4", test_type="functional"),
        ], story_id="S-1", run_id="run-2")

        acs = [AcceptanceCriterion(id="AC-1", description="X")]

        # Score only active entries
        score_active = score_rtm(store.active_entries, acs)
        # Score ALL entries (including superseded) — should be different
        score_all = score_rtm(store.entries, acs)

        # Active only has functional → lower score (missing negative/edge)
        # All entries has functional+negative+edge → higher score
        assert score_active < score_all

    def test_deprecated_entries_excluded_from_scoring(self):
        """Deprecated entries don't affect scoring."""
        from skuld.rtm_store import RTMStore
        from skuld.models import AcceptanceCriterion
        from skuld.rtm_scorer import score_rtm

        store = RTMStore()
        store.merge([
            RTMEntry(ac_id="AC-1", test_case_id="TC-1", test_type="functional"),
            RTMEntry(ac_id="AC-1", test_case_id="TC-2", test_type="negative"),
            RTMEntry(ac_id="AC-1", test_case_id="TC-3", test_type="edge-case"),
        ], story_id="S-1", run_id="run-1")

        # Deprecate the negative and edge tests
        store.deprecate(["TC-2", "TC-3"])

        acs = [AcceptanceCriterion(id="AC-1", description="X")]
        score = score_rtm(store.active_entries, acs)

        # Only functional remains active — score should reflect missing types
        assert score < 100.0

    def test_zero(self):
        assert assign_tier(0.0) == "low"

    def test_hundred(self):
        assert assign_tier(100.0) == "high"

    def test_boundary_80(self):
        assert assign_tier(80.0) == "high"

    def test_boundary_50(self):
        assert assign_tier(50.0) == "medium"

    def test_boundary_49(self):
        assert assign_tier(49.9) == "low"
