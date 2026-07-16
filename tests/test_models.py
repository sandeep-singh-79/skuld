"""Tests for skuld.models — T2: Data models."""
from __future__ import annotations

import pytest

from skuld.models import (
    EXIT_INPUT_ERROR,
    EXIT_OK,
    EXIT_VALIDATION_ERROR,
    AcceptanceCriterion,
    ConfidenceScore,
    FlowResult,
    GenerationRequest,
    GenerationResponse,
    InputPackage,
    ReviewFeedback,
    RTMEntry,
    Story,
    TestCase,
    ValidationResult,
)


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


class TestExitCodes:
    def test_exit_ok_is_zero(self):
        assert EXIT_OK == 0

    def test_exit_validation_error_is_one(self):
        assert EXIT_VALIDATION_ERROR == 1

    def test_exit_input_error_is_two(self):
        assert EXIT_INPUT_ERROR == 2


# ---------------------------------------------------------------------------
# Reused models (from IRO)
# ---------------------------------------------------------------------------


class TestInputPackage:
    def test_instantiation(self):
        pkg = InputPackage(source_path="/tmp/input.yaml", raw={"a": 1}, normalized={"a": 1})
        assert pkg.source_path == "/tmp/input.yaml"
        assert pkg.raw == {"a": 1}
        assert pkg.normalized == {"a": 1}


class TestValidationResult:
    def test_valid_when_no_errors(self):
        vr = ValidationResult(errors=[], total_checks=5)
        assert vr.is_valid is True
        assert vr.total_checks == 5

    def test_invalid_when_errors_present(self):
        vr = ValidationResult(errors=["missing heading"], total_checks=5)
        assert vr.is_valid is False

    def test_multiple_errors(self):
        vr = ValidationResult(errors=["err1", "err2", "err3"], total_checks=10)
        assert not vr.is_valid
        assert len(vr.errors) == 3

    def test_zero_checks(self):
        vr = ValidationResult(errors=[], total_checks=0)
        assert vr.is_valid is True
        assert vr.total_checks == 0


class TestFlowResult:
    def test_success_result(self):
        fr = FlowResult(exit_code=EXIT_OK, message="done", output_path="/out.md")
        assert fr.exit_code == 0
        assert fr.output_path == "/out.md"
        assert fr.warnings == []

    def test_with_warnings(self):
        fr = FlowResult(exit_code=EXIT_OK, message="ok", output_path=None, warnings=["w1"])
        assert fr.warnings == ["w1"]

    def test_error_result(self):
        fr = FlowResult(exit_code=EXIT_INPUT_ERROR, message="bad input", output_path=None)
        assert fr.exit_code == 2

    def test_multiple_warnings_accumulated(self):
        fr = FlowResult(
            exit_code=EXIT_OK, message="done", output_path=None,
            warnings=["strategy not approved", "AC count high", "token budget at 80%"],
        )
        assert len(fr.warnings) == 3


class TestGenerationRequest:
    def test_instantiation(self):
        req = GenerationRequest(system_prompt="You are a tester", user_prompt="Generate tests")
        assert req.system_prompt == "You are a tester"
        assert req.user_prompt == "Generate tests"


class TestGenerationResponse:
    def test_instantiation_with_defaults(self):
        resp = GenerationResponse(content="output", model="claude", provider="anthropic")
        assert resp.content == "output"
        assert resp.prompt_tokens is None
        assert resp.completion_tokens is None

    def test_instantiation_with_tokens(self):
        resp = GenerationResponse(
            content="out", model="gpt-4", provider="openai",
            prompt_tokens=100, completion_tokens=200,
        )
        assert resp.prompt_tokens == 100
        assert resp.completion_tokens == 200


# ---------------------------------------------------------------------------
# Skuld-specific models
# ---------------------------------------------------------------------------


class TestStory:
    def test_instantiation(self):
        s = Story(id="PROJ-123", title="Login feature", description="As a user...")
        assert s.id == "PROJ-123"
        assert s.title == "Login feature"
        assert s.description == "As a user..."

    def test_multiline_description(self):
        desc = "As a registered user,\nI want to log in with MFA,\nso that my account is secure."
        s = Story(id="S-1", title="MFA Login", description=desc)
        assert "\n" in s.description
        assert s.description.count("\n") == 2

    def test_equality(self):
        s1 = Story(id="S-1", title="A", description="B")
        s2 = Story(id="S-1", title="A", description="B")
        assert s1 == s2


class TestAcceptanceCriterion:
    def test_instantiation_with_criticality(self):
        ac = AcceptanceCriterion(id="AC-1", description="User can login", criticality="high")
        assert ac.id == "AC-1"
        assert ac.criticality == "high"

    def test_default_criticality_is_medium(self):
        ac = AcceptanceCriterion(id="AC-2", description="Shows error message")
        assert ac.criticality == "medium"

    def test_all_criticality_values(self):
        for crit in ("high", "medium", "low"):
            ac = AcceptanceCriterion(id="AC-X", description="test", criticality=crit)
            assert ac.criticality == crit

    def test_equality(self):
        ac1 = AcceptanceCriterion(id="AC-1", description="X", criticality="high")
        ac2 = AcceptanceCriterion(id="AC-1", description="X", criticality="high")
        assert ac1 == ac2


class TestTestCase:
    def test_instantiation_full(self):
        tc = TestCase(
            id="TC-001",
            story_id="PROJ-123",
            ac_ids=["AC-1", "AC-2"],
            test_type="functional",
            priority="P1",
            preconditions="User is registered",
            steps=["Navigate to login", "Enter credentials", "Click submit"],
            expected_result="User is logged in",
            test_data="email=test@example.com, password=valid123",
        )
        assert tc.id == "TC-001"
        assert tc.ac_ids == ["AC-1", "AC-2"]
        assert tc.test_type == "functional"
        assert tc.priority == "P1"
        assert len(tc.steps) == 3

    def test_defaults(self):
        tc = TestCase(
            id="TC-002",
            story_id="PROJ-123",
            ac_ids=["AC-1"],
            test_type="negative",
            priority="P2",
            preconditions="",
            steps=["Do invalid action"],
            expected_result="Error shown",
        )
        assert tc.test_data is None
        assert tc.automatable is True
        assert tc.review_flag == "✓"

    def test_valid_test_types(self):
        for tt in ("functional", "negative", "edge-case"):
            tc = TestCase(
                id="TC-X", story_id="S-1", ac_ids=["AC-1"],
                test_type=tt, priority="P1",
                preconditions="", steps=["step"], expected_result="result",
            )
            assert tc.test_type == tt

    def test_multiple_acs_mapping(self):
        tc = TestCase(
            id="TC-010", story_id="S-1", ac_ids=["AC-1", "AC-2", "AC-3"],
            test_type="functional", priority="P1",
            preconditions="", steps=["step"], expected_result="result",
        )
        assert len(tc.ac_ids) == 3

    def test_empty_ac_ids_orphan_test(self):
        tc = TestCase(
            id="TC-011", story_id="S-1", ac_ids=[],
            test_type="functional", priority="P3",
            preconditions="", steps=["step"], expected_result="result",
        )
        assert tc.ac_ids == []

    def test_non_automatable(self):
        tc = TestCase(
            id="TC-012", story_id="S-1", ac_ids=["AC-1"],
            test_type="functional", priority="P2",
            preconditions="Physical device required",
            steps=["Plug in USB token", "Verify LED blinks"],
            expected_result="Token recognised",
            automatable=False,
        )
        assert tc.automatable is False

    def test_review_flag_warning(self):
        tc = TestCase(
            id="TC-013", story_id="S-1", ac_ids=["AC-1"],
            test_type="negative", priority="P2",
            preconditions="", steps=["step"], expected_result="result",
            review_flag="⚠",
        )
        assert tc.review_flag == "⚠"

    def test_multiline_steps_and_expected_result(self):
        tc = TestCase(
            id="TC-014", story_id="S-1", ac_ids=["AC-1"],
            test_type="edge-case", priority="P1",
            preconditions="User has expired session token",
            steps=[
                "Navigate to dashboard",
                "Wait for session timeout (30 min)",
                "Click any action button",
                "Observe redirect to login page",
            ],
            expected_result="User is redirected to login with message 'Session expired'",
        )
        assert len(tc.steps) == 4
        assert "Session expired" in tc.expected_result


class TestRTMEntry:
    def test_instantiation(self):
        entry = RTMEntry(ac_id="AC-1", test_case_id="TC-001", test_type="functional")
        assert entry.ac_id == "AC-1"
        assert entry.test_case_id == "TC-001"
        assert entry.test_type == "functional"

    def test_with_story_and_metadata(self):
        entry = RTMEntry(
            ac_id="AC-2", test_case_id="TC-003", test_type="negative",
            story_id="PROJ-123", added_date="2026-07-16", status="active",
        )
        assert entry.story_id == "PROJ-123"
        assert entry.status == "active"

    def test_default_status_is_active(self):
        entry = RTMEntry(ac_id="AC-1", test_case_id="TC-001", test_type="edge-case")
        assert entry.status == "active"

    def test_deprecated_status(self):
        entry = RTMEntry(ac_id="AC-1", test_case_id="TC-001", test_type="functional", status="deprecated")
        assert entry.status == "deprecated"

    def test_superseded_status(self):
        entry = RTMEntry(ac_id="AC-1", test_case_id="TC-001", test_type="functional", status="superseded")
        assert entry.status == "superseded"

    def test_added_by_run_populated(self):
        entry = RTMEntry(
            ac_id="AC-1", test_case_id="TC-001", test_type="negative",
            story_id="S-1", added_date="2026-07-16",
            added_by_run="run-20260716-143000",
        )
        assert entry.added_by_run == "run-20260716-143000"


class TestConfidenceScore:
    def test_instantiation(self):
        cs = ConfidenceScore(
            overall=82.3,
            rtm_score=87.5,
            adversarial_score=70.0,
            rtm_details={"ac_coverage": "4/4", "negative_coverage": "3/4"},
            gaps=["AC-3: no negative test"],
        )
        assert cs.overall == 82.3
        assert cs.rtm_score == 87.5
        assert cs.adversarial_score == 70.0
        assert len(cs.gaps) == 1

    def test_with_none_adversarial(self):
        cs = ConfidenceScore(
            overall=87.5,
            rtm_score=87.5,
            adversarial_score=None,
            rtm_details={},
            gaps=[],
        )
        assert cs.adversarial_score is None

    def test_boundary_zero_score(self):
        cs = ConfidenceScore(
            overall=0.0, rtm_score=0.0, adversarial_score=0.0,
            rtm_details={"ac_coverage": "0/5"}, gaps=["everything missing"],
        )
        assert cs.overall == 0.0

    def test_boundary_perfect_score(self):
        cs = ConfidenceScore(
            overall=100.0, rtm_score=100.0, adversarial_score=100.0,
            rtm_details={"ac_coverage": "5/5"}, gaps=[],
        )
        assert cs.overall == 100.0

    def test_many_gaps(self):
        gaps = [f"AC-{i}: missing negative test" for i in range(1, 20)]
        cs = ConfidenceScore(
            overall=30.0, rtm_score=35.0, adversarial_score=20.0,
            rtm_details={}, gaps=gaps,
        )
        assert len(cs.gaps) == 19


class TestReviewFeedback:
    def test_instantiation(self):
        rf = ReviewFeedback(
            flagged_tests=["TC-002", "TC-005"],
            missing_scenarios=["AC-3 needs negative test for partial failure"],
            quality_scores={"assertion_strength": 75.0, "realism": 80.0},
            suggestions=["Add boundary test for AC-1"],
        )
        assert len(rf.flagged_tests) == 2
        assert len(rf.missing_scenarios) == 1
        assert rf.quality_scores["assertion_strength"] == 75.0
        assert len(rf.suggestions) == 1

    def test_empty_feedback(self):
        rf = ReviewFeedback(
            flagged_tests=[],
            missing_scenarios=[],
            quality_scores={},
            suggestions=[],
        )
        assert rf.flagged_tests == []
