"""Tests for skuld.adversarial_reviewer — T12 Adversarial Reviewer."""
from __future__ import annotations

import copy
import json

import pytest

from skuld.adversarial_reviewer import (
    ReviewParseError,
    compute_adversarial_score,
    map_review_flags,
    review_tests,
)
from skuld.llm_client import FakeLLMClient
from skuld.models import AcceptanceCriterion, ReviewFeedback, TestCase

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

HAPPY_RESPONSE = json.dumps(
    {
        "flagged_tests": ["TC-002"],
        "missing_scenarios": ["AC-2: no edge-case for timeout"],
        "quality_scores": {
            "assertion_strength": 0.75,
            "realism": 0.80,
            "edge_case_quality": 0.70,
        },
        "suggestions": ["Add boundary test for AC-1"],
    }
)


def _make_test_case(tc_id: str = "TC-001") -> TestCase:
    return TestCase(
        id=tc_id,
        story_id="S-001",
        ac_ids=["AC-1"],
        test_type="functional",
        priority="P1",
        preconditions="User logged in",
        steps=["Step 1", "Step 2"],
        expected_result="Success",
    )


def _make_acs() -> list[AcceptanceCriterion]:
    return [
        AcceptanceCriterion(id="AC-1", description="User can log in", criticality="high"),
        AcceptanceCriterion(id="AC-2", description="Session timeout after 30m", criticality="medium"),
    ]


# ===========================================================================
# TestReviewTests
# ===========================================================================


class TestReviewTests:
    """Tests for review_tests()."""

    def test_happy_path_returns_review_feedback(self):
        llm = FakeLLMClient(response_content=HAPPY_RESPONSE)
        tc = [_make_test_case("TC-001"), _make_test_case("TC-002")]
        acs = _make_acs()

        result = review_tests(tc, acs, llm)

        assert isinstance(result, ReviewFeedback)
        assert result.flagged_tests == ["TC-002"]
        assert result.missing_scenarios == ["AC-2: no edge-case for timeout"]
        assert result.quality_scores["assertion_strength"] == 0.75
        assert result.suggestions == ["Add boundary test for AC-1"]

    def test_calls_llm_with_reviewer_prompt(self):
        llm = FakeLLMClient(response_content=HAPPY_RESPONSE)
        tc = [_make_test_case()]
        acs = _make_acs()

        review_tests(tc, acs, llm)

        assert llm.call_count == 1
        req = llm.last_request
        assert "adversarial" in req.system_prompt.lower()

    def test_malformed_json_raises_review_parse_error(self):
        llm = FakeLLMClient(response_content="not json at all {{{")
        tc = [_make_test_case()]
        acs = _make_acs()

        with pytest.raises(ReviewParseError):
            review_tests(tc, acs, llm)

    def test_empty_response_raises_review_parse_error(self):
        llm = FakeLLMClient(response_content="")
        tc = [_make_test_case()]
        acs = _make_acs()

        with pytest.raises(ReviewParseError):
            review_tests(tc, acs, llm)

    def test_missing_required_key_raises(self):
        # Missing 'suggestions' key
        partial = json.dumps(
            {
                "flagged_tests": [],
                "missing_scenarios": [],
                "quality_scores": {"completeness": 0.8},
            }
        )
        llm = FakeLLMClient(response_content=partial)
        tc = [_make_test_case()]
        acs = _make_acs()

        with pytest.raises(ReviewParseError):
            review_tests(tc, acs, llm)

    def test_code_fence_wrapped_response_parsed(self):
        fenced = f"```json\n{HAPPY_RESPONSE}\n```"
        llm = FakeLLMClient(response_content=fenced)
        tc = [_make_test_case()]
        acs = _make_acs()

        result = review_tests(tc, acs, llm)

        assert isinstance(result, ReviewFeedback)
        assert result.flagged_tests == ["TC-002"]


# ===========================================================================
# TestComputeAdversarialScore
# ===========================================================================


class TestComputeAdversarialScore:
    """Tests for compute_adversarial_score()."""

    def test_no_flags_no_missing_perfect_quality(self):
        fb = ReviewFeedback(
            flagged_tests=[],
            missing_scenarios=[],
            quality_scores={"assertion_strength": 1.0, "realism": 1.0},
            suggestions=[],
        )
        score = compute_adversarial_score(fb)
        assert score == 100.0

    def test_many_flags_reduces_score(self):
        fb = ReviewFeedback(
            flagged_tests=["TC-001", "TC-002", "TC-003", "TC-004", "TC-005"],
            missing_scenarios=[],
            quality_scores={"assertion_strength": 1.0, "realism": 1.0},
            suggestions=[],
        )
        score = compute_adversarial_score(fb)
        # 5 flags * -5 = -25 deduction from the flag portion
        assert score < 80.0

    def test_many_missing_scenarios_reduces_score(self):
        fb = ReviewFeedback(
            flagged_tests=[],
            missing_scenarios=["miss-1", "miss-2", "miss-3"],
            quality_scores={"assertion_strength": 1.0, "realism": 1.0},
            suggestions=[],
        )
        score = compute_adversarial_score(fb)
        # 3 missing * -10 = -30 deduction
        assert score < 75.0

    def test_low_quality_scores_reduce(self):
        fb = ReviewFeedback(
            flagged_tests=[],
            missing_scenarios=[],
            quality_scores={"assertion_strength": 0.2, "realism": 0.2},
            suggestions=[],
        )
        score = compute_adversarial_score(fb)
        # Quality portion is low → total < 90
        assert score < 90.0

    def test_clamp_to_zero(self):
        fb = ReviewFeedback(
            flagged_tests=[f"TC-{i:03d}" for i in range(20)],
            missing_scenarios=[f"miss-{i}" for i in range(10)],
            quality_scores={"assertion_strength": 0.0, "realism": 0.0},
            suggestions=[],
        )
        score = compute_adversarial_score(fb)
        assert score == 0.0

    def test_clamp_to_hundred(self):
        # Even with scores > 1, should not exceed 100
        fb = ReviewFeedback(
            flagged_tests=[],
            missing_scenarios=[],
            quality_scores={"assertion_strength": 2.0, "realism": 2.0},
            suggestions=[],
        )
        score = compute_adversarial_score(fb)
        assert score == 100.0

    def test_empty_feedback_returns_90(self):
        """Empty quality_scores gives neutral score (10), not full credit (20)."""
        fb = ReviewFeedback(
            flagged_tests=[],
            missing_scenarios=[],
            quality_scores={},
            suggestions=[],
        )
        score = compute_adversarial_score(fb)
        assert score == pytest.approx(90.0, abs=1.0)


# ===========================================================================
# TestMapReviewFlags
# ===========================================================================


class TestMapReviewFlags:
    """Tests for map_review_flags()."""

    def test_flagged_tests_get_warning(self):
        tcs = [_make_test_case("TC-001"), _make_test_case("TC-002")]
        fb = ReviewFeedback(
            flagged_tests=["TC-002"],
            missing_scenarios=[],
            quality_scores={},
            suggestions=[],
        )

        result = map_review_flags(tcs, fb)

        assert result[1].review_flag == "⚠"

    def test_unflagged_tests_get_checkmark(self):
        tcs = [_make_test_case("TC-001"), _make_test_case("TC-002")]
        fb = ReviewFeedback(
            flagged_tests=["TC-002"],
            missing_scenarios=[],
            quality_scores={},
            suggestions=[],
        )

        result = map_review_flags(tcs, fb)

        assert result[0].review_flag == "✓"

    def test_does_not_mutate_originals(self):
        tcs = [_make_test_case("TC-001")]
        original_flag = tcs[0].review_flag
        fb = ReviewFeedback(
            flagged_tests=["TC-001"],
            missing_scenarios=[],
            quality_scores={},
            suggestions=[],
        )

        result = map_review_flags(tcs, fb)

        # Original unchanged
        assert tcs[0].review_flag == original_flag
        # Result is different object
        assert result[0] is not tcs[0]
        assert result[0].review_flag == "⚠"

    def test_unknown_flag_id_ignored(self):
        tcs = [_make_test_case("TC-001")]
        fb = ReviewFeedback(
            flagged_tests=["TC-999"],  # not in test list
            missing_scenarios=[],
            quality_scores={},
            suggestions=[],
        )

        result = map_review_flags(tcs, fb)

        # All tests keep checkmark since TC-999 doesn't match any
        assert result[0].review_flag == "✓"


# ===========================================================================
# TestParsingEdgeCases
# ===========================================================================


class TestParsingEdgeCases:
    """Edge-case tests for parsing and scoring."""

    def test_quality_scores_01_scale_scored_correctly(self):
        """Quality scores on 0-1 scale (as prompt specifies) produce correct points."""
        fb = ReviewFeedback(
            flagged_tests=[],
            missing_scenarios=[],
            quality_scores={"assertion_strength": 0.8, "realism": 0.9, "edge_quality": 0.7},
            suggestions=[],
        )
        score = compute_adversarial_score(fb)
        # avg = 0.8, quality_points = 0.8 * 20 = 16, total = 80 + 16 = 96
        assert 90 < score <= 100

    def test_quality_scores_non_numeric_raises(self):
        """Non-numeric quality_scores values raise ReviewParseError during parsing."""
        bad_response = json.dumps({
            "flagged_tests": [],
            "missing_scenarios": [],
            "quality_scores": {"clarity": "high"},
            "suggestions": [],
        })
        client = FakeLLMClient(response_content=bad_response)
        tc = [_make_test_case()]
        acs = _make_acs()
        with pytest.raises(ReviewParseError, match="numeric"):
            review_tests(tc, acs, client)

    def test_quality_scores_negative_clamped_to_zero(self):
        """Negative quality scores don't produce negative quality_points."""
        fb = ReviewFeedback(
            flagged_tests=[],
            missing_scenarios=[],
            quality_scores={"metric": -1.0},
            suggestions=[],
        )
        score = compute_adversarial_score(fb)
        # quality_points should be 0 (clamped), so score = 80 + 0 = 80
        assert score == pytest.approx(80.0, abs=1.0)

    def test_empty_quality_scores_gives_neutral(self):
        """Empty quality_scores gives neutral score (10), not full credit (20)."""
        fb = ReviewFeedback(
            flagged_tests=[],
            missing_scenarios=[],
            quality_scores={},
            suggestions=[],
        )
        score = compute_adversarial_score(fb)
        # 80 (base - 0 flags - 0 missing) + 10 (neutral) = 90
        assert score == pytest.approx(90.0, abs=1.0)

    def test_flagged_tests_non_string_raises(self):
        """Non-string elements in flagged_tests raise ReviewParseError."""
        bad_response = json.dumps({
            "flagged_tests": [1, 2, 3],
            "missing_scenarios": [],
            "quality_scores": {},
            "suggestions": [],
        })
        client = FakeLLMClient(response_content=bad_response)
        tc = [_make_test_case()]
        acs = _make_acs()
        with pytest.raises(ReviewParseError, match="strings"):
            review_tests(tc, acs, client)

    def test_missing_scenarios_non_string_raises(self):
        """Non-string elements in missing_scenarios raise ReviewParseError."""
        bad_response = json.dumps({
            "flagged_tests": [],
            "missing_scenarios": [42],
            "quality_scores": {},
            "suggestions": [],
        })
        client = FakeLLMClient(response_content=bad_response)
        tc = [_make_test_case()]
        acs = _make_acs()
        with pytest.raises(ReviewParseError, match="strings"):
            review_tests(tc, acs, client)

    def test_suggestions_non_string_raises(self):
        """Non-string elements in suggestions raise ReviewParseError."""
        bad_response = json.dumps({
            "flagged_tests": [],
            "missing_scenarios": [],
            "quality_scores": {},
            "suggestions": [{"tip": "use mocks"}],
        })
        client = FakeLLMClient(response_content=bad_response)
        tc = [_make_test_case()]
        acs = _make_acs()
        with pytest.raises(ReviewParseError, match="strings"):
            review_tests(tc, acs, client)

    def test_map_review_flags_empty_test_cases(self):
        """Empty test case list returns empty list."""
        fb = ReviewFeedback(
            flagged_tests=["TC-1"],
            missing_scenarios=[],
            quality_scores={},
            suggestions=[],
        )
        result = map_review_flags([], fb)
        assert result == []
