"""Tests for skuld.renderer — TDD RED phase."""
from __future__ import annotations

import json

import pytest

from skuld.models import AcceptanceCriterion, ConfidenceScore, TestCase
from skuld.output_validator import REQUIRED_HEADINGS, REQUIRED_LABELS, validate_output
from skuld.renderer import render_json, render_markdown, render_report


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_test_cases() -> list[TestCase]:
    return [
        TestCase(
            id="TC-001",
            story_id="STORY-1",
            ac_ids=["AC-1.1", "AC-1.2"],
            test_type="functional",
            priority="P1",
            preconditions="User is logged in",
            steps=["Navigate to dashboard", "Click submit"],
            expected_result="Dashboard loads",
            test_data="user=admin",
            automatable=True,
            review_flag="✓",
        ),
        TestCase(
            id="TC-002",
            story_id="STORY-1",
            ac_ids=["AC-1.1"],
            test_type="negative",
            priority="P2",
            preconditions="User is not logged in",
            steps=["Navigate to dashboard"],
            expected_result="Redirect to login",
            test_data=None,
            automatable=False,
            review_flag="⚠",
        ),
    ]


@pytest.fixture
def sample_rtm_matrix() -> dict:
    return {
        "matrix": {
            "AC-1.1": {"TC-001": "functional", "TC-002": "negative"},
            "AC-1.2": {"TC-001": "functional"},
        },
        "orphan_test_ids": [],
    }


@pytest.fixture
def sample_confidence() -> ConfidenceScore:
    return ConfidenceScore(
        overall=0.82,
        rtm_score=0.90,
        adversarial_score=0.75,
        rtm_details={"ac_coverage": 1.0, "negative_coverage": 0.5, "edge_case_coverage": 0.0},
        gaps=["AC-1.2: no negative test", "AC-1.2: no edge-case test"],
        tier="medium",
    )


@pytest.fixture
def sample_gaps() -> list[str]:
    return ["AC-1.2: no negative test", "AC-1.2: no edge-case test"]


# ---------------------------------------------------------------------------
# TestRenderMarkdown
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    def test_contains_all_required_headings(
        self, sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        md = render_markdown(sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps)
        for heading in REQUIRED_HEADINGS:
            assert heading in md, f"Missing heading: {heading}"

    def test_contains_all_required_labels(
        self, sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        md = render_markdown(sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps)
        for label in REQUIRED_LABELS:
            assert label in md, f"Missing label: {label}"

    def test_passes_output_validator(
        self, sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        """Critical round-trip test: rendered markdown must pass validate_output."""
        md = render_markdown(sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps)
        result = validate_output(md)
        assert result.is_valid, f"Validation errors: {result.errors}"

    def test_test_case_table_has_all_columns(
        self, sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        md = render_markdown(sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps)
        expected_columns = [
            "Test Case ID",
            "Story/Req ID",
            "AC IDs",
            "Test Type",
            "Priority",
            "Preconditions",
            "Steps",
            "Expected Result",
            "Test Data",
            "Automatable",
            "Review Flag",
        ]
        for col in expected_columns:
            assert col in md, f"Missing column header: {col}"

    def test_rtm_matrix_rendered(
        self, sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        md = render_markdown(sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps)
        # AC IDs from matrix should appear in the RTM section
        assert "AC-1.1" in md
        assert "AC-1.2" in md

    def test_confidence_score_rendered(
        self, sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        md = render_markdown(sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps)
        assert "0.82" in md or "82" in md
        assert "Overall Confidence:" in md

    def test_gaps_rendered_as_bullets(
        self, sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        md = render_markdown(sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps)
        for gap in sample_gaps:
            assert f"- {gap}" in md

    def test_empty_test_cases_still_valid(
        self, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        md = render_markdown([], sample_rtm_matrix, sample_confidence, sample_gaps)
        result = validate_output(md)
        assert result.is_valid, f"Validation errors: {result.errors}"

    def test_empty_gaps_section_present(
        self, sample_test_cases, sample_rtm_matrix, sample_confidence
    ):
        md = render_markdown(sample_test_cases, sample_rtm_matrix, sample_confidence, gaps=[])
        assert "## Coverage Gaps" in md
        result = validate_output(md)
        assert result.is_valid, f"Validation errors: {result.errors}"

    def test_pipe_in_cell_does_not_break_table(
        self, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        """Pipe characters in test data must be escaped to avoid column shift."""
        tc = TestCase(
            id="TC-PIPE",
            story_id="STORY-1",
            ac_ids=["AC-1.1"],
            test_type="functional",
            priority="P1",
            preconditions="Value is A | B",
            steps=["Select option A | B from dropdown"],
            expected_result="A|B is accepted",
            test_data="input=A|B",
            automatable=True,
            review_flag="✓",
        )
        md = render_markdown([tc], sample_rtm_matrix, sample_confidence, sample_gaps)
        result = validate_output(md)
        assert result.is_valid, f"Validation errors: {result.errors}"
        # Count pipe-separated columns in the data row (header + separator + 1 data row)
        table_lines = [l for l in md.splitlines() if l.startswith("|")]
        data_row = table_lines[2]  # first data row after header + separator
        # A correct 11-column row has 12 pipe delimiters (leading + trailing + 10 inner)
        assert data_row.count("|") - data_row.count("\\|") == 12

    def test_newline_in_cell_does_not_break_row(
        self, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        """Newlines in cell content must be flattened to spaces."""
        tc = TestCase(
            id="TC-NL",
            story_id="STORY-1",
            ac_ids=["AC-1.1"],
            test_type="functional",
            priority="P1",
            preconditions="Line1\nLine2",
            steps=["Step with\nnewline"],
            expected_result="Result\nhere",
            test_data=None,
            automatable=True,
            review_flag="✓",
        )
        md = render_markdown([tc], sample_rtm_matrix, sample_confidence, sample_gaps)
        result = validate_output(md)
        assert result.is_valid, f"Validation errors: {result.errors}"
        # No raw newlines inside the data row
        table_lines = [l for l in md.splitlines() if l.startswith("|")]
        data_row = table_lines[2]
        assert "\n" not in data_row

    def test_empty_rtm_matrix_still_valid(self, sample_test_cases, sample_confidence, sample_gaps):
        """An empty RTM matrix should still produce valid markdown with all labels."""
        empty_rtm = {"matrix": {}, "orphan_test_ids": []}
        md = render_markdown(sample_test_cases, empty_rtm, sample_confidence, sample_gaps)
        result = validate_output(md)
        assert result.is_valid, f"Validation errors: {result.errors}"
        assert "AC Coverage: 0%" in md


# ---------------------------------------------------------------------------
# TestRenderJSON
# ---------------------------------------------------------------------------


class TestRenderJSON:
    def test_valid_json_parseable(
        self, sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        output = render_json(sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_contains_all_keys(
        self, sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        output = render_json(sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps)
        parsed = json.loads(output)
        for key in ("test_cases", "rtm_matrix", "confidence_score", "gaps"):
            assert key in parsed, f"Missing key: {key}"

    def test_test_cases_serialized(
        self, sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        output = render_json(sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps)
        parsed = json.loads(output)
        assert len(parsed["test_cases"]) == 2
        assert parsed["test_cases"][0]["id"] == "TC-001"

    def test_confidence_score_serialized(
        self, sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        output = render_json(sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps)
        parsed = json.loads(output)
        cs = parsed["confidence_score"]
        assert cs["overall"] == 0.82
        assert cs["tier"] == "medium"

    def test_round_trip_json_load(
        self, sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        output = render_json(sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps)
        parsed = json.loads(output)
        # Round-trip: re-serialize and compare
        re_serialized = json.loads(json.dumps(parsed))
        assert re_serialized == parsed

    def test_steps_serialized_as_list(
        self, sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        output = render_json(sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps)
        parsed = json.loads(output)
        tc = parsed["test_cases"][0]
        assert isinstance(tc["steps"], list)
        assert tc["steps"] == ["Navigate to dashboard", "Click submit"]

    def test_ac_ids_serialized_as_list(
        self, sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        output = render_json(sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps)
        parsed = json.loads(output)
        tc = parsed["test_cases"][0]
        assert isinstance(tc["ac_ids"], list)
        assert tc["ac_ids"] == ["AC-1.1", "AC-1.2"]

    def test_null_test_data_serialized(
        self, sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        output = render_json(sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps)
        parsed = json.loads(output)
        # TC-002 has test_data=None
        tc2 = parsed["test_cases"][1]
        assert tc2["test_data"] is None


# ---------------------------------------------------------------------------
# TestRenderReport
# ---------------------------------------------------------------------------


class TestRenderReport:
    def test_dispatch_markdown(
        self, sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        result = render_report(
            sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps,
            output_format="markdown",
        )
        assert "## Test Cases" in result

    def test_dispatch_json(
        self, sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        result = render_report(
            sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps,
            output_format="json",
        )
        parsed = json.loads(result)
        assert "test_cases" in parsed

    def test_invalid_format_raises(
        self, sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps
    ):
        with pytest.raises(ValueError, match="Unsupported output format"):
            render_report(
                sample_test_cases, sample_rtm_matrix, sample_confidence, sample_gaps,
                output_format="xml",
            )
