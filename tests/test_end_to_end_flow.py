"""Tests for the end-to-end flow (T13)."""
from __future__ import annotations

import json
import os
import tempfile

import pytest
import yaml

from skuld.models import EXIT_INPUT_ERROR, EXIT_OK, EXIT_VALIDATION_ERROR


# ---------------------------------------------------------------------------
# Fixture: minimal valid normalised input dict
# ---------------------------------------------------------------------------

def _make_normalized_input() -> dict:
    """Return a valid normalized input dict as produced by validate_raw."""
    return {
        "story": {
            "id": "STORY-1",
            "title": "User login",
            "description": "As a user I want to log in so that I access my dashboard.",
        },
        "acceptance_criteria": [
            {"id": "AC-1", "description": "User can log in with valid credentials", "criticality": "high"},
            {"id": "AC-2", "description": "User sees error on invalid credentials", "criticality": "medium"},
        ],
        "config": {
            "generator_model": "claude-sonnet-4",
            "reviewer_model": "gpt-5.5",
            "min_negative_per_ac": 1,
            "min_edge_case_per_ac": 1,
            "output_format": "markdown",
            "filter_comments": True,
        },
        "comments": ["What if the user enters a SQL injection payload?"],
    }


def _make_raw_yaml_input() -> dict:
    """Return a raw YAML-level dict (pre-validate_raw)."""
    return {
        "story": {
            "id": "STORY-1",
            "title": "User login",
            "description": "As a user I want to log in so that I access my dashboard.",
        },
        "acceptance_criteria": [
            {"id": "AC-1", "description": "User can log in with valid credentials", "criticality": "high"},
            {"id": "AC-2", "description": "User sees error on invalid credentials", "criticality": "medium"},
        ],
        "config": {
            "generator_model": "claude-sonnet-4",
            "reviewer_model": "gpt-5.5",
        },
        "comments": ["What if the user enters a SQL injection payload?"],
    }


# ---------------------------------------------------------------------------
# Tests: TestRunPipeline
# ---------------------------------------------------------------------------

class TestRunPipeline:
    """Tests for run_pipeline and run_pipeline_from_dict happy paths."""

    def test_happy_path_fake_llm(self, tmp_path):
        """Pipeline completes with EXIT_OK and produces non-empty message."""
        from skuld.end_to_end_flow import run_pipeline_from_dict

        data = _make_raw_yaml_input()
        result = run_pipeline_from_dict(data, use_fake_llm=True)
        assert result.exit_code == EXIT_OK
        assert result.message  # non-empty rendered output
        assert "## Test Cases" in result.message

    def test_happy_path_has_numerical_confidence(self):
        """Pipeline produces a confidence score within valid range (0-100)."""
        from skuld.end_to_end_flow import run_pipeline_from_dict

        data = _make_raw_yaml_input()
        result = run_pipeline_from_dict(data, use_fake_llm=True)
        assert result.exit_code == EXIT_OK
        # Confidence score should appear as a number in the output
        assert "Overall Confidence:" in result.message
        # Extract and validate the score is a real number in range
        import re
        match = re.search(r"Overall Confidence:\s*([\d.]+)", result.message)
        assert match, "Overall Confidence value not found in output"
        score = float(match.group(1))
        assert 0.0 <= score <= 100.0, f"Score {score} outside valid range"
        assert score > 0.0, "Score should be > 0 for a valid input with test cases"

    def test_input_error_bad_file(self, tmp_path):
        """Non-existent file returns EXIT_INPUT_ERROR."""
        from skuld.end_to_end_flow import run_pipeline

        result = run_pipeline(str(tmp_path / "nonexistent.yaml"), use_fake_llm=True)
        assert result.exit_code == EXIT_INPUT_ERROR

    def test_dict_entry_point(self):
        """run_pipeline_from_dict works the same as file-based entry."""
        from skuld.end_to_end_flow import run_pipeline_from_dict

        data = _make_raw_yaml_input()
        result = run_pipeline_from_dict(data, use_fake_llm=True)
        assert result.exit_code == EXIT_OK
        assert result.message

    def test_file_entry_point(self, tmp_path):
        """run_pipeline with a valid file returns EXIT_OK."""
        from skuld.end_to_end_flow import run_pipeline

        input_file = tmp_path / "input.yaml"
        input_file.write_text(yaml.dump(_make_raw_yaml_input()), encoding="utf-8")
        result = run_pipeline(str(input_file), use_fake_llm=True)
        assert result.exit_code == EXIT_OK
        assert "## Test Cases" in result.message


# ---------------------------------------------------------------------------
# Tests: TestPipelineErrors
# ---------------------------------------------------------------------------

class TestPipelineErrors:
    """Tests for error paths in the pipeline."""

    def test_generation_failure(self):
        """When fake LLM returns garbage, pipeline returns EXIT_VALIDATION_ERROR."""
        from skuld.end_to_end_flow import _run_from_package
        from skuld.llm_client import FakeLLMClient
        from unittest.mock import patch

        normalized = _make_normalized_input()
        garbage_client = FakeLLMClient(response_content="not valid json at all {{{")
        with patch(
            "skuld.end_to_end_flow._prepare_fake_clients",
            return_value={
                "generator": garbage_client,
                "reviewer": garbage_client,
                "refinement": garbage_client,
            },
        ):
            result = _run_from_package(normalized, rtm_file=None, force=False, output_format="markdown", use_fake_llm=True)
        assert result.exit_code == EXIT_VALIDATION_ERROR
        assert "Failed to parse JSON" in result.message or "parse" in result.message.lower()

    def test_token_budget_exceeded(self):
        """When token budget is exceeded, pipeline returns EXIT_VALIDATION_ERROR."""
        from skuld.end_to_end_flow import _run_from_package
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient
        from unittest.mock import patch

        normalized = _make_normalized_input()
        # Create a budgeted client that will exceed on first call
        inner = FakeLLMClient(
            response_content="irrelevant",
            prompt_tokens=50000,
            completion_tokens=50000,
        )
        budget_client = BudgetedLLMClient(inner, max_tokens=100)

        with patch(
            "skuld.end_to_end_flow._prepare_fake_clients",
            return_value={
                "generator": budget_client,
                "reviewer": budget_client,
                "refinement": budget_client,
            },
        ):
            result = _run_from_package(normalized, rtm_file=None, force=False, output_format="markdown", use_fake_llm=True)
        assert result.exit_code == EXIT_VALIDATION_ERROR
        assert "budget" in result.message.lower() or "Token" in result.message

    def test_self_validation_failure(self):
        """If renderer produces invalid markdown, EXIT_VALIDATION_ERROR is returned."""
        from skuld.end_to_end_flow import _run_from_package
        from unittest.mock import patch

        normalized = _make_normalized_input()

        # Patch render_report to return invalid markdown (missing required headings)
        with patch("skuld.end_to_end_flow.render_report", return_value="# Bad output\nNo headings"):
            result = _run_from_package(normalized, rtm_file=None, force=False, output_format="markdown", use_fake_llm=True)
        assert result.exit_code == EXIT_VALIDATION_ERROR
        assert "Self-validation failed" in result.message


# ---------------------------------------------------------------------------
# Tests: TestPipelineFeatures
# ---------------------------------------------------------------------------

class TestPipelineFeatures:
    """Tests for pipeline features (RTM, formats, warnings, filtering)."""

    def test_rtm_merge_on_success(self, tmp_path):
        """When rtm_file is set, RTM entries are persisted."""
        from skuld.end_to_end_flow import run_pipeline_from_dict

        rtm_file = str(tmp_path / "rtm.yaml")
        data = _make_raw_yaml_input()
        result = run_pipeline_from_dict(data, rtm_file=rtm_file, use_fake_llm=True)
        assert result.exit_code == EXIT_OK
        assert os.path.exists(rtm_file)

        # Load and verify entries exist
        with open(rtm_file, "r") as f:
            rtm_data = yaml.safe_load(f)
        assert len(rtm_data["entries"]) > 0

    def test_json_output_format(self):
        """JSON output format produces valid JSON."""
        from skuld.end_to_end_flow import run_pipeline_from_dict

        data = _make_raw_yaml_input()
        result = run_pipeline_from_dict(data, output_format="json", use_fake_llm=True)
        assert result.exit_code == EXIT_OK
        # Verify it's valid JSON
        parsed = json.loads(result.message)
        assert "test_cases" in parsed
        assert "confidence_score" in parsed

    def test_warnings_populated_from_strategy(self):
        """Strategy warning appears in result.warnings when HITL not approved."""
        from skuld.end_to_end_flow import run_pipeline_from_dict

        data = _make_raw_yaml_input()
        # Add a strategy_ref without approval — triggers warning
        data["strategy_ref"] = {"name": "some-strategy"}
        result = run_pipeline_from_dict(data, use_fake_llm=True)
        assert result.exit_code == EXIT_OK
        assert any("strategy" in w.lower() or "reviewed" in w.lower() for w in result.warnings)

    def test_comments_filtered_in_pipeline(self):
        """When filter_comments is True, comment_filter is invoked."""
        from skuld.end_to_end_flow import run_pipeline_from_dict
        from unittest.mock import patch

        data = _make_raw_yaml_input()
        data["comments"] = [
            "Moved to sprint 5",  # noise — should be filtered
            "What if the token expires?",  # signal — should be kept
        ]

        with patch("skuld.end_to_end_flow.filter_comments", wraps=__import__("skuld.comment_filter", fromlist=["filter_comments"]).filter_comments) as mock_filter:
            result = run_pipeline_from_dict(data, use_fake_llm=True)
            assert result.exit_code == EXIT_OK
            assert mock_filter.called

    def test_same_model_warning(self):
        """Same generator/reviewer model emits a warning."""
        from skuld.end_to_end_flow import run_pipeline_from_dict

        data = _make_raw_yaml_input()
        data["config"]["generator_model"] = "gpt-5.5"
        data["config"]["reviewer_model"] = "gpt-5.5"
        result = run_pipeline_from_dict(data, use_fake_llm=True)
        assert result.exit_code == EXIT_OK
        assert any("same" in w.lower() and "adversarial" in w.lower() for w in result.warnings)

    def test_rtm_save_oserror_produces_warning(self, tmp_path):
        """When RTM save fails with OSError, pipeline still returns EXIT_OK with warning."""
        from skuld.end_to_end_flow import run_pipeline_from_dict
        from unittest.mock import patch

        data = _make_raw_yaml_input()
        rtm_file = str(tmp_path / "rtm.yaml")

        with patch("skuld.rtm_store.RTMStore.save", side_effect=OSError("disk full")):
            result = run_pipeline_from_dict(data, rtm_file=rtm_file, use_fake_llm=True)
        assert result.exit_code == EXIT_OK
        assert any("RTM persist failed" in w for w in result.warnings)

    def test_json_output_validates_keys(self):
        """JSON output format validates required keys."""
        from skuld.end_to_end_flow import run_pipeline_from_dict
        from unittest.mock import patch

        data = _make_raw_yaml_input()
        # Patch render_report to return valid JSON missing a required key
        bad_json = json.dumps({"test_cases": [], "confidence_score": 0.5})  # missing rtm_matrix
        with patch("skuld.end_to_end_flow.render_report", return_value=bad_json):
            result = run_pipeline_from_dict(data, output_format="json", use_fake_llm=True)
        assert result.exit_code == EXIT_VALIDATION_ERROR
        assert "missing keys" in result.message.lower() or "rtm_matrix" in result.message

    def test_json_output_validates_syntax(self):
        """JSON output format catches invalid JSON."""
        from skuld.end_to_end_flow import run_pipeline_from_dict
        from unittest.mock import patch

        data = _make_raw_yaml_input()
        with patch("skuld.end_to_end_flow.render_report", return_value="not json {{{"):
            result = run_pipeline_from_dict(data, output_format="json", use_fake_llm=True)
        assert result.exit_code == EXIT_VALIDATION_ERROR
        assert "JSON render invalid" in result.message


# ---------------------------------------------------------------------------
# Tests: TestPipelineApiKeyErrors
# ---------------------------------------------------------------------------

class TestPipelineApiKeyErrors:
    """Tests for API key validation."""

    def test_missing_api_key_raises(self, monkeypatch):
        """use_fake_llm=False with no env keys → EXIT_INPUT_ERROR."""
        from skuld.end_to_end_flow import run_pipeline_from_dict

        monkeypatch.delenv("SKULD_ANTHROPIC_KEY", raising=False)
        monkeypatch.delenv("SKULD_OPENAI_KEY", raising=False)

        data = _make_raw_yaml_input()
        result = run_pipeline_from_dict(data, use_fake_llm=False)
        assert result.exit_code == EXIT_INPUT_ERROR
        assert "API key not configured" in result.message

    def test_api_key_present_does_not_error(self, monkeypatch):
        """use_fake_llm=False with key set proceeds (uses fake under the hood for now)."""
        from skuld.end_to_end_flow import run_pipeline_from_dict

        monkeypatch.setenv("SKULD_ANTHROPIC_KEY", "sk-test-dummy")

        data = _make_raw_yaml_input()
        result = run_pipeline_from_dict(data, use_fake_llm=False)
        # Should not fail with API key error (may fail differently since real provider not wired)
        assert result.exit_code != EXIT_INPUT_ERROR or "API key" not in result.message


# ---------------------------------------------------------------------------
# Tests: TestReviewParseFailure
# ---------------------------------------------------------------------------

class TestReviewParseFailure:
    """Tests for reviewer parse failure paths."""

    def test_review_parse_failure(self):
        """Reviewer returns garbage → EXIT_VALIDATION_ERROR."""
        from skuld.end_to_end_flow import _run_from_package
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient

        from unittest.mock import patch

        normalized = _make_normalized_input()
        story_id = normalized["story"]["id"]
        ac_ids = [ac["id"] for ac in normalized["acceptance_criteria"]]

        # Generator succeeds, reviewer returns garbage, refinement irrelevant
        from skuld.end_to_end_flow import _fake_test_cases_json

        gen_json = _fake_test_cases_json(story_id, ac_ids)
        inner = FakeLLMClient(responses=[gen_json, "absolutely not json {{{", "irrelevant"])
        budgeted = BudgetedLLMClient(inner, max_tokens=32000)

        with patch(
            "skuld.end_to_end_flow._prepare_fake_clients",
            return_value={"generator": budgeted, "reviewer": budgeted, "refinement": budgeted},
        ):
            result = _run_from_package(
                normalized, rtm_file=None, force=False, output_format="markdown", use_fake_llm=True
            )
        assert result.exit_code == EXIT_VALIDATION_ERROR
        assert "parse" in result.message.lower() or "review" in result.message.lower()
