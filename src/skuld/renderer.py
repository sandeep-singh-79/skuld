"""Renderer for Skuld reports — markdown and JSON output formats."""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from skuld.models import ConfidenceScore, TestCase


# ---------------------------------------------------------------------------
# Internal data assembly
# ---------------------------------------------------------------------------


def _build_report_data(
    test_cases: list[TestCase],
    rtm_matrix: dict,
    confidence: ConfidenceScore,
    gaps: list[str],
) -> dict:
    """Assemble all report data into a structured dict."""
    return {
        "test_cases": [asdict(tc) for tc in test_cases],
        "rtm_matrix": rtm_matrix,
        "confidence_score": {
            "overall": confidence.overall,
            "rtm_score": confidence.rtm_score,
            "adversarial_score": confidence.adversarial_score,
            "rtm_details": confidence.rtm_details,
            "gaps": confidence.gaps,
            "tier": confidence.tier,
        },
        "gaps": gaps,
    }


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def _escape_cell(value: str) -> str:
    """Escape characters that would break a markdown table cell."""
    # Pipes break column boundaries; newlines break rows
    return value.replace("|", "\\|").replace("\n", " ")


def _render_test_case_table(test_cases: list[TestCase]) -> str:
    """Render test cases as a markdown table."""
    headers = [
        "Test Case ID", "Story/Req ID", "AC IDs", "Test Type", "Priority",
        "Preconditions", "Steps", "Expected Result", "Test Data",
        "Automatable", "Review Flag",
    ]
    lines: list[str] = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")

    for tc in test_cases:
        steps_str = "; ".join(tc.steps)
        ac_str = ", ".join(tc.ac_ids)
        row = [
            _escape_cell(tc.id),
            _escape_cell(tc.story_id),
            _escape_cell(ac_str),
            _escape_cell(tc.test_type),
            _escape_cell(tc.priority),
            _escape_cell(tc.preconditions),
            _escape_cell(steps_str),
            _escape_cell(tc.expected_result),
            _escape_cell(tc.test_data or "—"),
            "Yes" if tc.automatable else "No",
            _escape_cell(tc.review_flag),
        ]
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def _render_rtm_section(rtm_matrix: dict) -> str:
    """Render the RTM matrix and coverage labels."""
    lines: list[str] = []

    matrix = rtm_matrix.get("matrix", {})
    orphans = rtm_matrix.get("orphan_test_ids", [])

    # Matrix table
    if matrix:
        all_tc_ids: list[str] = sorted(
            {tc_id for mapping in matrix.values() for tc_id in mapping}
        )
        headers = ["AC ID"] + all_tc_ids
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")

        for ac_id in sorted(matrix.keys()):
            row = [ac_id]
            for tc_id in all_tc_ids:
                row.append(matrix[ac_id].get(tc_id, "—"))
            lines.append("| " + " | ".join(row) + " |")
    else:
        lines.append("No traceability data available.")

    lines.append("")

    # Coverage labels — compute from matrix
    total_acs = len(matrix)
    covered_acs = sum(1 for mapping in matrix.values() if mapping)
    ac_coverage = covered_acs / total_acs if total_acs > 0 else 0.0

    negative_count = sum(
        1 for mapping in matrix.values()
        if any(t == "negative" for t in mapping.values())
    )
    negative_coverage = negative_count / total_acs if total_acs > 0 else 0.0

    edge_count = sum(
        1 for mapping in matrix.values()
        if any(t == "edge-case" for t in mapping.values())
    )
    edge_coverage = edge_count / total_acs if total_acs > 0 else 0.0

    lines.append(f"AC Coverage: {ac_coverage:.0%}")
    lines.append(f"Negative Coverage: {negative_coverage:.0%}")
    lines.append(f"Edge-Case Coverage: {edge_coverage:.0%}")
    lines.append(f"Orphan Tests: {len(orphans)}")

    return "\n".join(lines)


def _render_confidence_section(confidence: ConfidenceScore) -> str:
    """Render the confidence score section."""
    lines: list[str] = []
    lines.append(f"Overall Confidence: {confidence.overall:.2f} ({confidence.tier})")
    lines.append("")
    lines.append(f"- RTM Score: {confidence.rtm_score:.2f}")
    if confidence.adversarial_score is not None:
        lines.append(f"- Adversarial Score: {confidence.adversarial_score:.2f}")
    if confidence.rtm_details:
        for key, value in confidence.rtm_details.items():
            lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def _render_gaps_section(gaps: list[str]) -> str:
    """Render coverage gaps as a bullet list."""
    if not gaps:
        return "No coverage gaps identified."
    return "\n".join(f"- {gap}" for gap in gaps)


def render_markdown(
    test_cases: list[TestCase],
    rtm_matrix: dict,
    confidence: ConfidenceScore,
    gaps: list[str],
) -> str:
    """Render full report as markdown. MUST pass output_validator.validate_output()."""
    sections: list[str] = []

    # Test Cases
    sections.append("## Test Cases")
    sections.append("")
    sections.append(_render_test_case_table(test_cases))
    sections.append("")

    # Requirements Traceability Matrix
    sections.append("## Requirements Traceability Matrix")
    sections.append("")
    sections.append(_render_rtm_section(rtm_matrix))
    sections.append("")

    # Confidence Score
    sections.append("## Confidence Score")
    sections.append("")
    sections.append(_render_confidence_section(confidence))
    sections.append("")

    # Coverage Gaps
    sections.append("## Coverage Gaps")
    sections.append("")
    sections.append(_render_gaps_section(gaps))

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# JSON renderer
# ---------------------------------------------------------------------------


def render_json(
    test_cases: list[TestCase],
    rtm_matrix: dict,
    confidence: ConfidenceScore,
    gaps: list[str],
) -> str:
    """Render full report as JSON string (machine-readable)."""
    data = _build_report_data(test_cases, rtm_matrix, confidence, gaps)
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Convenience dispatcher
# ---------------------------------------------------------------------------


def render_report(
    test_cases: list[TestCase],
    rtm_matrix: dict,
    confidence: ConfidenceScore,
    gaps: list[str],
    output_format: str = "markdown",
) -> str:
    """Dispatch to the appropriate renderer."""
    if output_format == "markdown":
        return render_markdown(test_cases, rtm_matrix, confidence, gaps)
    elif output_format == "json":
        return render_json(test_cases, rtm_matrix, confidence, gaps)
    else:
        raise ValueError(f"Unsupported output format: {output_format!r}")
