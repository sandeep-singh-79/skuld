"""Data models for Skuld — AI-powered test case generator."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

EXIT_OK: int = 0
EXIT_VALIDATION_ERROR: int = 1
EXIT_INPUT_ERROR: int = 2

# ---------------------------------------------------------------------------
# Core data structures (reused pattern from IRO)
# ---------------------------------------------------------------------------


@dataclass
class InputPackage:
    """Parsed and normalised input document."""

    source_path: str
    raw: dict[str, Any]
    normalized: dict[str, Any]


@dataclass
class ValidationResult:
    """Output of a structural validation pass."""

    errors: list[str]
    total_checks: int

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


@dataclass
class FlowResult:
    """Final result returned by the end-to-end pipeline."""

    exit_code: int
    message: str
    output_path: str | None
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LLM integration data structures
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class GenerationRequest:
    """Input to an LLM generate call."""

    system_prompt: str
    user_prompt: str


@dataclass(slots=True)
class GenerationResponse:
    """Output from an LLM generate call."""

    content: str
    model: str
    provider: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


# ---------------------------------------------------------------------------
# Skuld-specific domain models
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Story:
    """A user story parsed from input."""

    id: str
    title: str
    description: str


@dataclass(slots=True)
class AcceptanceCriterion:
    """A single acceptance criterion within a story."""

    id: str
    description: str
    criticality: str = "medium"  # high | medium | low


@dataclass(slots=True)
class TestCase:
    """A generated test case specification."""

    __test__ = False  # prevent pytest collection

    id: str
    story_id: str
    ac_ids: list[str]
    test_type: str  # functional | negative | edge-case
    priority: str  # P1 | P2 | P3
    preconditions: str
    steps: list[str]
    expected_result: str
    test_data: str | None = None
    automatable: bool = True
    review_flag: str = "✓"  # ✓ | ⚠


@dataclass(slots=True)
class RTMEntry:
    """One traceability mapping: test case → acceptance criterion."""

    ac_id: str
    test_case_id: str
    test_type: str  # functional | negative | edge-case
    story_id: str | None = None
    added_date: str | None = None
    added_by_run: str | None = None
    status: str = "active"  # active | deprecated | superseded


@dataclass
class ConfidenceScore:
    """Composite confidence score for a generation run."""

    overall: float
    rtm_score: float
    adversarial_score: float | None
    rtm_details: dict[str, Any]
    gaps: list[str]


@dataclass
class ReviewFeedback:
    """Structured feedback from the adversarial reviewer."""

    flagged_tests: list[str]
    missing_scenarios: list[str]
    quality_scores: dict[str, float]
    suggestions: list[str]
