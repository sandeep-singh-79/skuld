"""Test generator for Skuld — Pass 1 generation and Pass 2 refinement."""
from __future__ import annotations

import json
import re
from dataclasses import asdict

from skuld.comment_filter import filter_comments
from skuld.llm_client import LLMClient
from skuld.models import ReviewFeedback, TestCase
from skuld.prompt_builder import build_generator_prompt, build_refinement_prompt

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_TEST_TYPES = frozenset({"functional", "negative", "edge-case"})
VALID_PRIORITIES = frozenset({"P1", "P2", "P3"})

_REQUIRED_FIELDS = ("id", "story_id", "ac_ids", "test_type", "priority", "preconditions", "steps", "expected_result")

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class GenerationError(RuntimeError):
    """Raised when LLM output cannot be parsed into valid test cases."""


# ---------------------------------------------------------------------------
# Internal parser
# ---------------------------------------------------------------------------


def _extract_json_block(text: str) -> str:
    """Extract JSON from response, stripping code fences if present."""
    text = text.strip()
    if not text:
        raise GenerationError("Empty response from LLM")
    match = _CODE_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return text


def _parse_test_cases(response_content: str) -> list[TestCase]:
    """Parse LLM JSON response into TestCase list. Raises GenerationError on failure."""
    try:
        raw_json = _extract_json_block(response_content)
        data = json.loads(raw_json)
    except (json.JSONDecodeError, GenerationError) as e:
        raise GenerationError(f"Failed to parse JSON: {e}") from e

    # Accept both {"test_cases": [...]} and bare [...]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and "test_cases" in data:
        items = data["test_cases"]
    else:
        raise GenerationError("Response must be a JSON object with 'test_cases' key or a bare array")

    if not isinstance(items, list):
        raise GenerationError("'test_cases' must be an array")

    result: list[TestCase] = []
    seen_ids: set[str] = set()
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise GenerationError(f"Item {i} is not an object")
        _validate_item(item, i)
        tc = _build_test_case(item)
        if tc.id in seen_ids:
            raise GenerationError(f"Item {i}: duplicate test ID '{tc.id}'")
        seen_ids.add(tc.id)
        result.append(tc)

    return result


def _validate_item(item: dict, index: int) -> None:
    """Validate a single test case dict has required fields with valid values."""
    for field in _REQUIRED_FIELDS:
        if field not in item:
            raise GenerationError(f"Item {index}: missing required field '{field}'")

    # Validate test_type
    if item["test_type"] not in VALID_TEST_TYPES:
        raise GenerationError(
            f"Item {index}: invalid test_type '{item['test_type']}' "
            f"(must be one of {sorted(VALID_TEST_TYPES)})"
        )

    # Validate priority
    if item["priority"] not in VALID_PRIORITIES:
        raise GenerationError(
            f"Item {index}: invalid priority '{item['priority']}' "
            f"(must be one of {sorted(VALID_PRIORITIES)})"
        )

    # Validate ac_ids non-empty
    if not item["ac_ids"]:
        raise GenerationError(f"Item {index}: ac_ids must be non-empty")


def _build_test_case(item: dict) -> TestCase:
    """Construct a TestCase from a validated dict, ignoring extra fields."""
    return TestCase(
        id=str(item["id"]),
        story_id=str(item["story_id"]),
        ac_ids=[str(a) for a in item["ac_ids"]],
        test_type=str(item["test_type"]),
        priority=str(item["priority"]),
        preconditions=str(item["preconditions"]),
        steps=[str(s) for s in item["steps"]],
        expected_result=str(item["expected_result"]),
        test_data=item.get("test_data"),
        automatable=bool(item.get("automatable", True)),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_tests(normalized: dict, llm_client: LLMClient) -> list[TestCase]:
    """Pass 1 — generate test cases from acceptance criteria.

    Args:
        normalized: Normalized input dict with keys: story, acceptance_criteria,
                    config, comments, domain_context.
        llm_client: LLM client implementing the generate() protocol.

    Returns:
        List of validated TestCase objects.

    Raises:
        GenerationError: If LLM output cannot be parsed or validated.
    """
    story = normalized["story"]
    acceptance_criteria = normalized["acceptance_criteria"]
    config = normalized["config"]
    comments = normalized.get("comments") or []
    domain_context = normalized.get("domain_context")

    # Filter comments if configured
    if config.get("filter_comments") and comments:
        comments = filter_comments(comments)

    # Build prompt and call LLM
    request = build_generator_prompt(
        story=story,
        acceptance_criteria=acceptance_criteria,
        config=config,
        comments=comments if comments else None,
        domain_context=domain_context,
    )
    response = llm_client.generate(request)

    # Parse and validate
    return _parse_test_cases(response.content)


def refine_tests(
    test_cases: list[TestCase],
    review_feedback: ReviewFeedback,
    normalized: dict,
    llm_client: LLMClient,
) -> list[TestCase]:
    """Pass 2 — refine test cases based on adversarial review feedback.

    Args:
        test_cases: Current test cases from Pass 1.
        review_feedback: Structured feedback from the adversarial reviewer.
        normalized: Normalized input dict (for ACs).
        llm_client: LLM client implementing the generate() protocol.

    Returns:
        Refined list of validated TestCase objects.

    Raises:
        GenerationError: If LLM output cannot be parsed or validated.
    """
    # Serialize current state
    tc_dicts = [asdict(tc) for tc in test_cases]
    test_cases_json = json.dumps({"test_cases": tc_dicts}, indent=2)

    feedback_dict = asdict(review_feedback)
    review_feedback_json = json.dumps(feedback_dict, indent=2)

    acceptance_criteria = normalized["acceptance_criteria"]

    # Build refinement prompt and call LLM
    request = build_refinement_prompt(
        test_cases_json=test_cases_json,
        review_feedback_json=review_feedback_json,
        acceptance_criteria=acceptance_criteria,
    )
    response = llm_client.generate(request)

    # Parse and validate
    return _parse_test_cases(response.content)
