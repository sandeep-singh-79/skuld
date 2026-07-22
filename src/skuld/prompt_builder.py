"""Prompt builder for Skuld — constructs LLM prompts for generation, review, and refinement."""
from __future__ import annotations

import json
import re

from skuld.models import GenerationRequest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CLOSING_TAG_RE = re.compile(r"</(\w+)>")

_TEST_CASE_SCHEMA = """{
  "test_cases": [
    {
      "id": "TC-001",
      "story_id": "<story_id>",
      "ac_ids": ["AC-1"],
      "test_type": "functional | negative | edge-case",
      "priority": "P1 | P2 | P3",
      "preconditions": "...",
      "steps": ["step 1", "step 2"],
      "expected_result": "...",
      "test_data": "... or null",
      "automatable": true
    }
  ]
}"""

_REVIEW_FEEDBACK_SCHEMA = """{
  "flagged_tests": ["TC-001"],
  "missing_scenarios": ["description of missing scenario"],
  "quality_scores": {"completeness": 0.0, "clarity": 0.0, "coverage": 0.0},
  "suggestions": ["actionable suggestion"]
}"""

_GENERATOR_SYSTEM = (
    "You are an expert test case writer specializing in comprehensive test "
    "design from user stories and acceptance criteria. You produce structured, "
    "actionable test cases covering functional, negative, and edge-case scenarios. "
    "You output ONLY valid JSON matching the provided schema."
)

_REVIEWER_SYSTEM = (
    "You are an adversarial test reviewer. Your role is to critically evaluate "
    "generated test cases against acceptance criteria, identify gaps in coverage, "
    "score quality, and flag weak or redundant tests. "
    "You output ONLY valid JSON matching the ReviewFeedback schema."
)

_REFINEMENT_SYSTEM = (
    "You are an expert test case writer. You will refine a set of test cases "
    "based on adversarial review feedback. Retain tests that passed review. "
    "Fix or replace flagged tests. Add new tests for missing scenarios. "
    "Address all suggestions. Output ONLY valid JSON matching the test case schema."
)


def _compose_system_prompt(*parts: str) -> str:
    """Join only stable, non-user-specific system instructions.

    This helper is the guardrail for provider-side prompt caching. Do not pass
    story text, acceptance criteria, comments, domain context, test case JSON,
    or review feedback into this helper.
    """
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _escape_closing_tags(text: str) -> str:
    """Escape XML-like closing tags in user content to prevent delimiter injection.

    Replaces `</tag>` with `<\\/tag>` so it cannot prematurely close a fence.
    """
    return _CLOSING_TAG_RE.sub(r"<\\/\1>", text)


def _fence(tag: str, content: str) -> str:
    """Wrap content in XML-like delimiter tags with injection-safe escaping."""
    safe_content = _escape_closing_tags(content)
    return f"<{tag}>\n{safe_content}\n</{tag}>"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_generator_prompt(
    story: dict,
    acceptance_criteria: list[dict],
    config: dict,
    comments: list[str] | None = None,
    domain_context: str | None = None,
) -> GenerationRequest:
    """Build the Pass 1 generator prompt.

    - System: role definition (expert test case writer)
    - User: story + ACs + config constraints + filtered comments (if any)
    - Contract injection: required output columns, expected test types
    - User content fenced with <story_context></story_context> delimiters
    """
    # Build story context
    story_text = (
        f"Story ID: {story['id']}\n"
        f"Title: {story['title']}\n"
        f"Description: {story['description']}"
    )

    # Build acceptance criteria block
    ac_lines: list[str] = []
    for ac in acceptance_criteria:
        crit = ac.get("criticality", "medium")
        ac_lines.append(f"- {ac['id']} [{crit}]: {ac['description']}")
    ac_text = "\n".join(ac_lines)

    # Assemble user prompt parts
    parts: list[str] = [
        _fence("story_context", story_text),
        "",
        _fence("acceptance_criteria", ac_text),
    ]

    # Optional comments
    if comments:
        comment_text = "\n".join(f"- {c}" for c in comments)
        parts.append("")
        parts.append(_fence("comments", comment_text))

    # Optional domain context — normalize dict to YAML string before fencing
    if domain_context:
        if isinstance(domain_context, dict):
            import yaml as _yaml
            domain_context = _yaml.dump(domain_context, default_flow_style=False).rstrip()
        parts.append("")
        parts.append(_fence("domain_context", domain_context))

    # Config constraints
    min_neg = config.get("min_negative_per_ac", 1)
    min_edge = config.get("min_edge_case_per_ac", 1)
    parts.append("")
    parts.append(
        "## Per-Run Constraints\n"
        f"- Generate at least {min_neg} negative test(s) per AC\n"
        f"- Generate at least {min_edge} edge-case test(s) per AC"
    )
    parts.append("")
    parts.append(
        "Generate functional, negative, and edge-case tests. "
        "Include test_cases entries with ac_ids and expected_result fields."
    )

    user_prompt = "\n".join(parts)
    system_prompt = _compose_system_prompt(
        _GENERATOR_SYSTEM,
        "## Requirements\n"
        "- Include functional, negative, and edge-case test types\n"
        "- Each test must trace to at least one AC via ac_ids",
        "## Output Format\n"
        "Respond with ONLY valid JSON matching this schema:\n"
        f"```json\n{_TEST_CASE_SCHEMA}\n```",
    )
    return GenerationRequest(system_prompt=system_prompt, user_prompt=user_prompt)


def build_reviewer_prompt(
    test_cases_json: str,
    acceptance_criteria: list[dict],
) -> GenerationRequest:
    """Build the adversarial reviewer prompt.

    - System: adversarial reviewer role (find gaps, score quality)
    - User: generated test cases + ACs + scoring rubric
    - Output contract: MUST produce JSON matching ReviewFeedback schema
    """
    ac_lines: list[str] = []
    for ac in acceptance_criteria:
        crit = ac.get("criticality", "medium")
        ac_lines.append(f"- {ac['id']} [{crit}]: {ac['description']}")
    ac_text = "\n".join(ac_lines)

    parts: list[str] = [
        "## Generated Test Cases\n"
        f"```json\n{test_cases_json}\n```",
        "",
        _fence("acceptance_criteria", ac_text),
        "",
        "Return feedback with flagged_tests, missing_scenarios, quality_scores, "
        "and suggestions.",
    ]

    user_prompt = "\n".join(parts)
    system_prompt = _compose_system_prompt(
        _REVIEWER_SYSTEM,
        "## Review Instructions\n"
        "1. Check each AC has at least one functional, one negative, and one edge-case test\n"
        "2. Flag tests that are vague, redundant, or untraceable\n"
        "3. Identify missing scenarios not covered by any test\n"
        "4. Score quality on completeness, clarity, and coverage (0.0 to 1.0)",
        "## Output Format\n"
        "Respond with ONLY valid JSON matching this schema:\n"
        f"```json\n{_REVIEW_FEEDBACK_SCHEMA}\n```",
    )
    return GenerationRequest(system_prompt=system_prompt, user_prompt=user_prompt)


def build_refinement_prompt(
    test_cases_json: str,
    review_feedback_json: str,
    acceptance_criteria: list[dict],
) -> GenerationRequest:
    """Build the Pass 2 refinement prompt.

    - System: same generator role with refinement instruction
    - User: original test cases + review feedback + instruction to address gaps
    - Must retain tests that passed review, fix/replace flagged ones, add missing ones
    """
    ac_lines: list[str] = []
    for ac in acceptance_criteria:
        crit = ac.get("criticality", "medium")
        ac_lines.append(f"- {ac['id']} [{crit}]: {ac['description']}")
    ac_text = "\n".join(ac_lines)

    parts: list[str] = [
        "## Original Test Cases\n"
        f"```json\n{test_cases_json}\n```",
        "",
        "## Review Feedback\n"
        f"```json\n{review_feedback_json}\n```",
        "",
        _fence("acceptance_criteria", ac_text),
        "",
        "Return a refined test_cases list that addresses the review feedback.",
    ]

    user_prompt = "\n".join(parts)
    system_prompt = _compose_system_prompt(
        _REFINEMENT_SYSTEM,
        "## Refinement Instructions\n"
        "1. Retain tests that were NOT flagged in the review\n"
        "2. Fix or replace all flagged tests addressing the reviewer's concerns\n"
        "3. Add new tests for each missing scenario identified\n"
        "4. Implement all actionable suggestions\n"
        "5. Ensure every AC has functional, negative, and edge-case coverage",
        "## Output Format\n"
        "Respond with ONLY valid JSON matching this schema:\n"
        f"```json\n{_TEST_CASE_SCHEMA}\n```",
    )
    return GenerationRequest(system_prompt=system_prompt, user_prompt=user_prompt)
