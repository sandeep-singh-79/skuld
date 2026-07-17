"""Tests for skuld.test_generator — Pass 1 generation and Pass 2 refinement."""
from __future__ import annotations

import json

import pytest

from skuld.llm_client import FakeLLMClient
from skuld.models import ReviewFeedback, TestCase
from skuld.test_generator import (
    GenerationError,
    VALID_TEST_TYPES,
    _parse_test_cases,
    generate_tests,
    refine_tests,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_VALID_TC_JSON = json.dumps(
    {
        "test_cases": [
            {
                "id": "TC-001",
                "story_id": "S-1",
                "ac_ids": ["AC-1"],
                "test_type": "functional",
                "priority": "P1",
                "preconditions": "User exists",
                "steps": ["Navigate to login", "Enter creds"],
                "expected_result": "Login success",
                "test_data": None,
                "automatable": True,
            }
        ]
    }
)

_VALID_TC_TWO = json.dumps(
    {
        "test_cases": [
            {
                "id": "TC-001",
                "story_id": "S-1",
                "ac_ids": ["AC-1"],
                "test_type": "functional",
                "priority": "P1",
                "preconditions": "User exists",
                "steps": ["Step 1"],
                "expected_result": "OK",
                "test_data": None,
                "automatable": True,
            },
            {
                "id": "TC-002",
                "story_id": "S-1",
                "ac_ids": ["AC-1"],
                "test_type": "negative",
                "priority": "P2",
                "preconditions": "User does not exist",
                "steps": ["Attempt login"],
                "expected_result": "Error shown",
                "test_data": None,
                "automatable": True,
            },
        ]
    }
)


def _make_normalized(*, filter_comments: bool = False, comments: list[str] | None = None):
    """Build a minimal normalized input dict for testing."""
    return {
        "story": {"id": "S-1", "title": "Login", "description": "User can log in"},
        "acceptance_criteria": [
            {"id": "AC-1", "description": "Valid creds → dashboard", "criticality": "high"}
        ],
        "config": {"filter_comments": filter_comments, "min_negative_per_ac": 1, "min_edge_case_per_ac": 1},
        "comments": comments or [],
        "domain_context": None,
    }


# ---------------------------------------------------------------------------
# TestGenerateTests
# ---------------------------------------------------------------------------


class TestGenerateTests:
    """Tests for generate_tests() — Pass 1 generation."""

    def test_happy_path_returns_test_cases(self):
        llm = FakeLLMClient(response_content=_VALID_TC_JSON)
        normalized = _make_normalized()
        result = generate_tests(normalized, llm)
        assert len(result) == 1
        assert isinstance(result[0], TestCase)
        assert result[0].id == "TC-001"
        assert result[0].test_type == "functional"

    def test_calls_llm_client_with_generation_request(self):
        llm = FakeLLMClient(response_content=_VALID_TC_JSON)
        normalized = _make_normalized()
        generate_tests(normalized, llm)
        assert llm.call_count == 1
        assert llm.last_request is not None
        assert "test case writer" in llm.last_request.system_prompt.lower()

    def test_comments_filtered_when_config_enabled(self):
        """When filter_comments=True, noise comments are removed before prompting."""
        noise = "Moved to sprint 5"
        signal = "What if the user enters invalid email?"
        llm = FakeLLMClient(response_content=_VALID_TC_JSON)
        normalized = _make_normalized(filter_comments=True, comments=[noise, signal])
        generate_tests(normalized, llm)
        # The prompt should contain the signal but not the noise
        prompt = llm.last_request.user_prompt
        assert "invalid email" in prompt
        assert "Moved to sprint 5" not in prompt

    def test_comments_not_filtered_when_config_disabled(self):
        """When filter_comments=False, all comments pass through."""
        noise = "Moved to sprint 5"
        llm = FakeLLMClient(response_content=_VALID_TC_JSON)
        normalized = _make_normalized(filter_comments=False, comments=[noise])
        generate_tests(normalized, llm)
        prompt = llm.last_request.user_prompt
        assert "Moved to sprint 5" in prompt

    def test_malformed_json_raises_generation_error(self):
        llm = FakeLLMClient(response_content="not json at all {{{")
        normalized = _make_normalized()
        with pytest.raises(GenerationError):
            generate_tests(normalized, llm)

    def test_missing_required_field_raises_generation_error(self):
        bad_json = json.dumps({"test_cases": [{"id": "TC-001"}]})
        llm = FakeLLMClient(response_content=bad_json)
        normalized = _make_normalized()
        with pytest.raises(GenerationError, match="required field"):
            generate_tests(normalized, llm)

    def test_invalid_test_type_raises_generation_error(self):
        bad_json = json.dumps(
            {
                "test_cases": [
                    {
                        "id": "TC-001",
                        "story_id": "S-1",
                        "ac_ids": ["AC-1"],
                        "test_type": "invalid-type",
                        "priority": "P1",
                        "preconditions": "x",
                        "steps": ["s"],
                        "expected_result": "r",
                    }
                ]
            }
        )
        llm = FakeLLMClient(response_content=bad_json)
        normalized = _make_normalized()
        with pytest.raises(GenerationError, match="test_type"):
            generate_tests(normalized, llm)

    def test_empty_ac_ids_raises_generation_error(self):
        bad_json = json.dumps(
            {
                "test_cases": [
                    {
                        "id": "TC-001",
                        "story_id": "S-1",
                        "ac_ids": [],
                        "test_type": "functional",
                        "priority": "P1",
                        "preconditions": "x",
                        "steps": ["s"],
                        "expected_result": "r",
                    }
                ]
            }
        )
        llm = FakeLLMClient(response_content=bad_json)
        normalized = _make_normalized()
        with pytest.raises(GenerationError, match="ac_ids"):
            generate_tests(normalized, llm)

    def test_json_wrapped_in_code_fence_parsed_correctly(self):
        fenced = f"```json\n{_VALID_TC_JSON}\n```"
        llm = FakeLLMClient(response_content=fenced)
        normalized = _make_normalized()
        result = generate_tests(normalized, llm)
        assert len(result) == 1
        assert result[0].id == "TC-001"


# ---------------------------------------------------------------------------
# TestRefineTests
# ---------------------------------------------------------------------------


class TestRefineTests:
    """Tests for refine_tests() — Pass 2 refinement."""

    def test_happy_path_returns_refined_cases(self):
        original = [
            TestCase(
                id="TC-001",
                story_id="S-1",
                ac_ids=["AC-1"],
                test_type="functional",
                priority="P1",
                preconditions="x",
                steps=["s"],
                expected_result="r",
            )
        ]
        feedback = ReviewFeedback(
            flagged_tests=["TC-001"],
            missing_scenarios=["negative login"],
            quality_scores={"completeness": 0.6, "clarity": 0.8, "coverage": 0.5},
            suggestions=["Add negative case"],
        )
        llm = FakeLLMClient(response_content=_VALID_TC_TWO)
        normalized = _make_normalized()
        result = refine_tests(original, feedback, normalized, llm)
        assert len(result) == 2
        assert result[1].test_type == "negative"

    def test_calls_llm_with_refinement_prompt(self):
        original = [
            TestCase(
                id="TC-001",
                story_id="S-1",
                ac_ids=["AC-1"],
                test_type="functional",
                priority="P1",
                preconditions="x",
                steps=["s"],
                expected_result="r",
            )
        ]
        feedback = ReviewFeedback(
            flagged_tests=[],
            missing_scenarios=[],
            quality_scores={"completeness": 1.0, "clarity": 1.0, "coverage": 1.0},
            suggestions=[],
        )
        llm = FakeLLMClient(response_content=_VALID_TC_JSON)
        normalized = _make_normalized()
        refine_tests(original, feedback, normalized, llm)
        assert llm.call_count == 1
        assert "refine" in llm.last_request.system_prompt.lower()

    def test_malformed_response_raises_generation_error(self):
        original = [
            TestCase(
                id="TC-001",
                story_id="S-1",
                ac_ids=["AC-1"],
                test_type="functional",
                priority="P1",
                preconditions="x",
                steps=["s"],
                expected_result="r",
            )
        ]
        feedback = ReviewFeedback(
            flagged_tests=[],
            missing_scenarios=[],
            quality_scores={},
            suggestions=[],
        )
        llm = FakeLLMClient(response_content="garbage")
        normalized = _make_normalized()
        with pytest.raises(GenerationError):
            refine_tests(original, feedback, normalized, llm)

    def test_preserves_valid_structure(self):
        original = [
            TestCase(
                id="TC-001",
                story_id="S-1",
                ac_ids=["AC-1"],
                test_type="functional",
                priority="P1",
                preconditions="x",
                steps=["s"],
                expected_result="r",
            )
        ]
        feedback = ReviewFeedback(
            flagged_tests=[],
            missing_scenarios=[],
            quality_scores={"completeness": 1.0},
            suggestions=[],
        )
        llm = FakeLLMClient(response_content=_VALID_TC_JSON)
        normalized = _make_normalized()
        result = refine_tests(original, feedback, normalized, llm)
        tc = result[0]
        assert tc.story_id == "S-1"
        assert tc.ac_ids == ["AC-1"]
        assert tc.priority == "P1"


# ---------------------------------------------------------------------------
# TestParseTestCases
# ---------------------------------------------------------------------------


class TestParseTestCases:
    """Tests for _parse_test_cases() — low-level parser."""

    def test_valid_json_array_parsed(self):
        result = _parse_test_cases(_VALID_TC_JSON)
        assert len(result) == 1
        assert result[0].id == "TC-001"

    def test_json_with_extra_fields_accepted(self):
        """LLM may add unexpected keys — they should be ignored."""
        data = json.dumps(
            {
                "test_cases": [
                    {
                        "id": "TC-001",
                        "story_id": "S-1",
                        "ac_ids": ["AC-1"],
                        "test_type": "functional",
                        "priority": "P1",
                        "preconditions": "x",
                        "steps": ["s"],
                        "expected_result": "r",
                        "extra_field": "should be ignored",
                        "another_unknown": 42,
                    }
                ]
            }
        )
        result = _parse_test_cases(data)
        assert len(result) == 1
        assert result[0].id == "TC-001"

    def test_completely_invalid_json_raises(self):
        with pytest.raises(GenerationError):
            _parse_test_cases("this is not json")

    # -----------------------------------------------------------------------
    # Additional adversarial/robustness tests (Steps 2-4)
    # -----------------------------------------------------------------------

    def test_empty_response_raises(self):
        with pytest.raises(GenerationError):
            _parse_test_cases("")

    def test_whitespace_only_response_raises(self):
        with pytest.raises(GenerationError):
            _parse_test_cases("   \n\t  ")

    def test_partial_json_raises(self):
        with pytest.raises(GenerationError):
            _parse_test_cases('{"test_cases": [{"id": "TC-001"')

    def test_empty_test_cases_array_returns_empty_list(self):
        """If LLM returns fewer tests than expected, we don't crash."""
        result = _parse_test_cases(json.dumps({"test_cases": []}))
        assert result == []

    def test_invalid_priority_raises(self):
        data = json.dumps(
            {
                "test_cases": [
                    {
                        "id": "TC-001",
                        "story_id": "S-1",
                        "ac_ids": ["AC-1"],
                        "test_type": "functional",
                        "priority": "CRITICAL",  # invalid
                        "preconditions": "x",
                        "steps": ["s"],
                        "expected_result": "r",
                    }
                ]
            }
        )
        with pytest.raises(GenerationError, match="priority"):
            _parse_test_cases(data)

    def test_response_as_bare_array(self):
        """Some LLMs return a bare array without the wrapper object."""
        data = json.dumps(
            [
                {
                    "id": "TC-001",
                    "story_id": "S-1",
                    "ac_ids": ["AC-1"],
                    "test_type": "functional",
                    "priority": "P1",
                    "preconditions": "x",
                    "steps": ["s"],
                    "expected_result": "r",
                }
            ]
        )
        result = _parse_test_cases(data)
        assert len(result) == 1

    def test_nested_code_fence_stripped(self):
        """Multiple code fence wrappers handled."""
        inner = json.dumps({"test_cases": [
            {
                "id": "TC-001",
                "story_id": "S-1",
                "ac_ids": ["AC-1"],
                "test_type": "edge-case",
                "priority": "P3",
                "preconditions": "x",
                "steps": ["s"],
                "expected_result": "r",
            }
        ]})
        fenced = f"```json\n{inner}\n```"
        result = _parse_test_cases(fenced)
        assert result[0].test_type == "edge-case"

    def test_wrong_schema_no_test_cases_key_raises(self):
        """Valid JSON but wrong schema (dict without 'test_cases' key)."""
        data = json.dumps({"results": [{"id": "TC-001"}]})
        with pytest.raises(GenerationError, match="test_cases"):
            _parse_test_cases(data)

    def test_wrong_schema_scalar_value_raises(self):
        """Valid JSON scalar (string) is not an array or object with test_cases."""
        with pytest.raises(GenerationError, match="test_cases"):
            _parse_test_cases('"just a string"')

    def test_duplicate_test_ids_raises(self):
        """LLM returns duplicate test IDs — should raise GenerationError."""
        data = json.dumps(
            {
                "test_cases": [
                    {
                        "id": "TC-001",
                        "story_id": "S-1",
                        "ac_ids": ["AC-1"],
                        "test_type": "functional",
                        "priority": "P1",
                        "preconditions": "x",
                        "steps": ["s"],
                        "expected_result": "r",
                    },
                    {
                        "id": "TC-001",
                        "story_id": "S-1",
                        "ac_ids": ["AC-2"],
                        "test_type": "negative",
                        "priority": "P2",
                        "preconditions": "y",
                        "steps": ["s2"],
                        "expected_result": "r2",
                    },
                ]
            }
        )
        with pytest.raises(GenerationError, match="duplicate"):
            _parse_test_cases(data)


# ---------------------------------------------------------------------------
# TestDomainContext
# ---------------------------------------------------------------------------


class TestDomainContext:
    """Tests that domain_context is forwarded to the LLM prompt."""

    def test_domain_context_included_in_prompt(self):
        llm = FakeLLMClient(response_content=_VALID_TC_JSON)
        normalized = _make_normalized()
        normalized["domain_context"] = "This is a banking application with PCI-DSS compliance."
        generate_tests(normalized, llm)
        prompt = llm.last_request.user_prompt
        assert "banking application" in prompt
        assert "PCI-DSS" in prompt

    def test_domain_context_none_omitted_from_prompt(self):
        llm = FakeLLMClient(response_content=_VALID_TC_JSON)
        normalized = _make_normalized()
        normalized["domain_context"] = None
        generate_tests(normalized, llm)
        prompt = llm.last_request.user_prompt
        assert "domain_context" not in prompt
