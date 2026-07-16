"""Tests for skuld.output_validator — T4: Output contract validation."""
from __future__ import annotations

import pytest

from skuld.output_validator import (
    LABEL_SECTION_MAP,
    REQUIRED_HEADINGS,
    REQUIRED_LABELS,
    parse_sections,
    validate_output,
)
from skuld.models import ValidationResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_OUTPUT = """\
# Skuld Report

## Test Cases

| Test Case ID | Story/Req ID | Acceptance Criteria | Test Type | Priority |
|---|---|---|---|---|
| TC-001 | PROJ-1234 | AC-1 | functional | P1 |
| TC-002 | PROJ-1234 | AC-1 | negative | P2 |
| TC-003 | PROJ-1234 | AC-2 | edge-case | P2 |

## Requirements Traceability Matrix

AC Coverage: 2/2
Negative Coverage: 1/2
Edge-Case Coverage: 1/2
Orphan Tests: 0

## Confidence Score

Overall Confidence: 82.3
RTM Score: 87.5
Adversarial Score: 70.0

## Coverage Gaps

- AC-2: no negative test
- AC-2: no edge-case test for boundary input
"""


def _remove_section(text: str, heading: str) -> str:
    """Remove an entire section from the markdown."""
    lines = text.splitlines(keepends=True)
    result = []
    skip = False
    for line in lines:
        if line.rstrip() == heading:
            skip = True
            continue
        if skip and line.startswith("## "):
            skip = False
        if not skip:
            result.append(line)
    return "".join(result)


def _remove_label(text: str, label: str) -> str:
    """Remove a label line from the markdown."""
    return "\n".join(line for line in text.splitlines() if label not in line)


# ---------------------------------------------------------------------------
# parse_sections
# ---------------------------------------------------------------------------


class TestParseSections:
    def test_splits_by_headings(self):
        sections = parse_sections(VALID_OUTPUT)
        assert "## Test Cases" in sections
        assert "## Requirements Traceability Matrix" in sections
        assert "## Confidence Score" in sections
        assert "## Coverage Gaps" in sections

    def test_preamble_captured(self):
        sections = parse_sections(VALID_OUTPUT)
        assert "__preamble__" in sections
        assert "Skuld Report" in sections["__preamble__"]

    def test_section_body_correct(self):
        sections = parse_sections(VALID_OUTPUT)
        assert "TC-001" in sections["## Test Cases"]
        assert "Overall Confidence" in sections["## Confidence Score"]

    def test_empty_input(self):
        sections = parse_sections("")
        assert sections == {"__preamble__": ""}

    def test_no_recognized_headings(self):
        sections = parse_sections("Some text\n## Unknown Heading\nMore text")
        assert "__preamble__" in sections
        assert "## Unknown Heading" not in sections  # not in REQUIRED_HEADINGS


# ---------------------------------------------------------------------------
# validate_output — valid output passes
# ---------------------------------------------------------------------------


class TestValidateOutputValid:
    def test_valid_output_passes(self):
        vr = validate_output(VALID_OUTPUT)
        assert vr.is_valid, f"Expected valid but got errors: {vr.errors}"
        assert vr.total_checks > 0

    def test_returns_validation_result(self):
        vr = validate_output(VALID_OUTPUT)
        assert isinstance(vr, ValidationResult)


# ---------------------------------------------------------------------------
# validate_output — missing headings
# ---------------------------------------------------------------------------


class TestValidateOutputHeadings:
    def test_missing_one_heading(self):
        bad = _remove_section(VALID_OUTPUT, "## Coverage Gaps")
        vr = validate_output(bad)
        assert not vr.is_valid
        assert any("Coverage Gaps" in e for e in vr.errors)

    def test_missing_all_headings(self):
        bad = "Just some text without any headings"
        vr = validate_output(bad)
        assert not vr.is_valid
        assert len(vr.errors) >= len(REQUIRED_HEADINGS)

    def test_heading_not_line_anchored(self):
        """Heading embedded in text should not count."""
        bad = VALID_OUTPUT.replace("## Confidence Score", "text ## Confidence Score")
        vr = validate_output(bad)
        assert not vr.is_valid
        assert any("Confidence Score" in e for e in vr.errors)


# ---------------------------------------------------------------------------
# validate_output — missing labels
# ---------------------------------------------------------------------------


class TestValidateOutputLabels:
    def test_missing_one_label(self):
        bad = _remove_label(VALID_OUTPUT, "Overall Confidence:")
        vr = validate_output(bad)
        assert not vr.is_valid
        assert any("Overall Confidence" in e for e in vr.errors)

    def test_missing_multiple_labels(self):
        bad = _remove_label(VALID_OUTPUT, "AC Coverage:")
        bad = _remove_label(bad, "Orphan Tests:")
        vr = validate_output(bad)
        assert not vr.is_valid
        assert len([e for e in vr.errors if "label" in e.lower() or "Label" in e]) >= 2

    def test_duplicate_label_flagged(self):
        bad = VALID_OUTPUT + "\nOverall Confidence: 82.3\n"
        vr = validate_output(bad)
        assert not vr.is_valid
        assert any("Duplicate" in e or "duplicate" in e for e in vr.errors)


# ---------------------------------------------------------------------------
# validate_output — section placement
# ---------------------------------------------------------------------------


class TestValidateOutputPlacement:
    def test_label_in_wrong_section(self):
        """Move a Confidence Score label into the Test Cases section."""
        bad = VALID_OUTPUT.replace(
            "## Test Cases\n",
            "## Test Cases\nOverall Confidence: 82.3\n",
        )
        # Remove from correct section
        bad = bad.replace("Overall Confidence: 82.3\n\nRTM Score", "RTM Score")
        vr = validate_output(bad)
        # Should flag placement error (label not in declared section)
        assert not vr.is_valid


# ---------------------------------------------------------------------------
# validate_output — total_checks count
# ---------------------------------------------------------------------------


class TestValidateOutputCheckCount:
    def test_total_checks_reflects_all_validations(self):
        vr = validate_output(VALID_OUTPUT)
        # At minimum: len(REQUIRED_HEADINGS) + 2 * len(REQUIRED_LABELS)
        expected_min = len(REQUIRED_HEADINGS) + 2 * len(REQUIRED_LABELS)
        assert vr.total_checks >= expected_min
