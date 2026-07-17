"""Adversarial reviewer for Skuld — T12.

Evaluates generated test cases against acceptance criteria using an LLM
adversarial review pass, then scores and flags results.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Callable

from skuld.llm_client import LLMClient
from skuld.models import (
    AcceptanceCriterion,
    ReviewFeedback,
    TestCase,
)
from skuld.prompt_builder import build_reviewer_prompt


class ReviewParseError(RuntimeError):
    """Raised when reviewer LLM output cannot be parsed into ReviewFeedback."""


_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)

_REQUIRED_KEYS = {"flagged_tests", "missing_scenarios", "quality_scores", "suggestions"}


def _validate_str_list(data: dict, key: str) -> None:
    """Raise ReviewParseError if data[key] is not a list of strings."""
    if not isinstance(data[key], list):
        raise ReviewParseError(f"{key} must be a list")
    if not all(isinstance(item, str) for item in data[key]):
        raise ReviewParseError(f"{key} must contain only strings")


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences wrapping JSON."""
    m = _CODE_FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def _parse_review_response(raw: str) -> ReviewFeedback:
    """Parse raw LLM text into ReviewFeedback, raising ReviewParseError on failure."""
    if not raw or not raw.strip():
        raise ReviewParseError("Empty response from reviewer LLM")

    cleaned = _strip_code_fences(raw)

    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        raise ReviewParseError(f"Invalid JSON from reviewer LLM: {e}") from e

    missing = _REQUIRED_KEYS - set(data.keys())
    if missing:
        raise ReviewParseError(f"Missing required keys in review response: {missing}")

    # Validate types
    _validate_str_list(data, "flagged_tests")
    _validate_str_list(data, "missing_scenarios")
    _validate_str_list(data, "suggestions")
    if not isinstance(data["quality_scores"], dict):
        raise ReviewParseError("quality_scores must be a dict")
    if not all(isinstance(v, (int, float)) for v in data["quality_scores"].values()):
        raise ReviewParseError("quality_scores values must be numeric")

    return ReviewFeedback(
        flagged_tests=data["flagged_tests"],
        missing_scenarios=data["missing_scenarios"],
        quality_scores=data["quality_scores"],
        suggestions=data["suggestions"],
    )


def review_tests(
    test_cases: list[TestCase],
    acceptance_criteria: list[AcceptanceCriterion],
    llm_client: LLMClient,
    prompt_builder_fn: Callable | None = None,
) -> ReviewFeedback:
    """Run adversarial review on generated test cases.

    1. Serialize test_cases to JSON
    2. Build reviewer prompt
    3. Call LLM
    4. Parse response into ReviewFeedback
    """
    # Serialize test cases
    tc_dicts = [
        {
            "id": tc.id,
            "story_id": tc.story_id,
            "ac_ids": tc.ac_ids,
            "test_type": tc.test_type,
            "priority": tc.priority,
            "preconditions": tc.preconditions,
            "steps": tc.steps,
            "expected_result": tc.expected_result,
            "test_data": tc.test_data,
            "automatable": tc.automatable,
        }
        for tc in test_cases
    ]
    test_cases_json = json.dumps(tc_dicts, indent=2)

    # Build AC dicts
    ac_dicts = [
        {"id": ac.id, "description": ac.description, "criticality": ac.criticality}
        for ac in acceptance_criteria
    ]

    # Build prompt
    builder = prompt_builder_fn or build_reviewer_prompt
    request = builder(test_cases_json, ac_dicts)

    # Call LLM
    response = llm_client.generate(request)

    # Parse
    return _parse_review_response(response.content)


def compute_adversarial_score(review_feedback: ReviewFeedback) -> float:
    """Compute a 0–100 adversarial quality score from review feedback.

    Scoring:
    - Base: 100
    - Deduct per flagged test: -5 (max deduction 50)
    - Deduct per missing scenario: -10 (max deduction 30)
    - Quality scores average contributes up to 20 points (replacing base 20)
    """
    # Flag deductions (max 50)
    flag_deduction = min(len(review_feedback.flagged_tests) * 5, 50)

    # Missing scenario deductions (max 30)
    missing_deduction = min(len(review_feedback.missing_scenarios) * 10, 30)

    # Quality contribution (20 points)
    scores = review_feedback.quality_scores
    if scores:
        # Scores are 0-1 scale per prompt schema
        avg = sum(scores.values()) / len(scores)
        quality_points = max(0.0, min(avg * 20.0, 20.0))
    else:
        # No quality scores → neutral (10 points)
        quality_points = 10.0

    # Base 80 (since 20 comes from quality) minus deductions + quality points
    score = 80.0 - flag_deduction - missing_deduction + quality_points

    # Clamp
    return max(0.0, min(100.0, score))


def map_review_flags(
    test_cases: list[TestCase],
    review_feedback: ReviewFeedback,
) -> list[TestCase]:
    """Map review flags onto test cases (non-mutating).

    Returns a new list of TestCase copies with review_flag set to:
    - "⚠" if the test ID is in flagged_tests
    - "✓" otherwise
    """
    flagged_ids = set(review_feedback.flagged_tests)
    result: list[TestCase] = []

    for tc in test_cases:
        new_tc = copy.copy(tc)
        # copy list fields to avoid shared references
        new_tc.ac_ids = list(tc.ac_ids)
        new_tc.steps = list(tc.steps)
        new_tc.review_flag = "⚠" if tc.id in flagged_ids else "✓"
        result.append(new_tc)

    return result
