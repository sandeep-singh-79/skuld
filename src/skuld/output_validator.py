"""Output contract validator for Skuld reports."""
from __future__ import annotations

from skuld.models import ValidationResult

# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------

REQUIRED_HEADINGS: list[str] = [
    "## Test Cases",
    "## Requirements Traceability Matrix",
    "## Confidence Score",
    "## Coverage Gaps",
]

# Maps each required label to the heading of the section it must appear in.
LABEL_SECTION_MAP: dict[str, str] = {
    "AC Coverage:": "## Requirements Traceability Matrix",
    "Negative Coverage:": "## Requirements Traceability Matrix",
    "Edge-Case Coverage:": "## Requirements Traceability Matrix",
    "Orphan Tests:": "## Requirements Traceability Matrix",
    "Overall Confidence:": "## Confidence Score",
}

REQUIRED_LABELS: list[str] = list(LABEL_SECTION_MAP.keys())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def parse_sections(markdown: str) -> dict[str, str]:
    """Split markdown into sections keyed by heading (line-anchored).

    Returns a dict mapping each heading (e.g. "## Test Cases") to the body text
    that follows it. An implicit ``__preamble__`` key holds any text before the
    first recognized heading.
    """
    sections: dict[str, str] = {}
    current_heading = "__preamble__"
    current_lines: list[str] = []

    for line in markdown.splitlines():
        stripped = line.rstrip()
        if stripped in REQUIRED_HEADINGS:
            sections[current_heading] = "\n".join(current_lines)
            current_heading = stripped
            current_lines = []
        else:
            current_lines.append(line)

    sections[current_heading] = "\n".join(current_lines)
    return sections


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_output(markdown: str) -> ValidationResult:
    """Validate a rendered report against the Skuld output contract.

    Checks performed:
    1. All required headings present (line-anchored).
    2. All required labels present exactly once.
    3. No label appears more than once.
    4. Each label appears in its declared section.

    Returns a ValidationResult with is_valid True iff no errors.
    """
    errors: list[str] = []
    total_checks = 0

    # --- 1. Heading presence (line-anchored) --------------------------------
    present_headings: set[str] = set()
    for line in markdown.splitlines():
        if line.rstrip() in REQUIRED_HEADINGS:
            present_headings.add(line.rstrip())

    for heading in REQUIRED_HEADINGS:
        total_checks += 1
        if heading not in present_headings:
            errors.append(f"Missing required heading: {heading!r}")

    # --- 2 & 3. Label presence, uniqueness, and section placement -----------
    sections = parse_sections(markdown)

    for label, required_section in LABEL_SECTION_MAP.items():
        total_checks += 2  # one for presence, one for section placement

        # Count occurrences globally
        occurrences = sum(
            body.count(label)
            for body in sections.values()
        )

        if occurrences == 0:
            errors.append(f"Missing required label: {label!r}")
            continue  # can't check placement if absent

        if occurrences > 1:
            errors.append(f"Duplicate label (found {occurrences} times): {label!r}")

        # Section placement: label must appear in its declared section
        section_body = sections.get(required_section, "")
        if label not in section_body:
            errors.append(
                f"Label {label!r} must appear in section {required_section!r} "
                f"but was not found there"
            )

    return ValidationResult(errors=errors, total_checks=total_checks)
