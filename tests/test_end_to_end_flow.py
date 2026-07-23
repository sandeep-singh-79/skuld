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
            "generator_model": "claude-sonnet-4-20250514",
            "reviewer_model": "gpt-4o",
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
            "generator_model": "claude-sonnet-4-20250514",
            "reviewer_model": "gpt-4o",
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
        data["config"]["generator_model"] = "gpt-4o"
        data["config"]["reviewer_model"] = "gpt-4o"
        result = run_pipeline_from_dict(data, use_fake_llm=True)
        assert result.exit_code == EXIT_OK
        assert any("same" in w.lower() and "adversarial" in w.lower() for w in result.warnings)

    def test_same_model_warning_model_routing(self):
        """Same generator/reviewer in model_routing emits a warning."""
        from skuld.end_to_end_flow import run_pipeline_from_dict

        data = _make_raw_yaml_input()
        data["config"]["model_routing"] = {
            "generator": {"model": "claude-sonnet-4-20250514", "provider": "anthropic"},
            "reviewer": {"model": "claude-sonnet-4-20250514", "provider": "anthropic"},
            "refinement": {"model": "claude-sonnet-4-20250514", "provider": "anthropic"},
        }
        result = run_pipeline_from_dict(data, use_fake_llm=True)
        assert result.exit_code == EXIT_OK
        assert any("same" in w.lower() and "adversarial" in w.lower() for w in result.warnings)

    def test_same_model_warning_not_duplicated_with_routing(self):
        """When model_routing is present, only one same-model warning fires."""
        from skuld.end_to_end_flow import run_pipeline_from_dict

        data = _make_raw_yaml_input()
        # Set both simple-mode AND model_routing to same model
        data["config"]["generator_model"] = "claude-sonnet-4-20250514"
        data["config"]["reviewer_model"] = "claude-sonnet-4-20250514"
        data["config"]["model_routing"] = {
            "generator": {"model": "claude-sonnet-4-20250514", "provider": "anthropic"},
            "reviewer": {"model": "claude-sonnet-4-20250514", "provider": "anthropic"},
            "refinement": {"model": "claude-sonnet-4-20250514", "provider": "anthropic"},
        }
        result = run_pipeline_from_dict(data, use_fake_llm=True)
        assert result.exit_code == EXIT_OK
        same_model_warnings = [w for w in result.warnings if "adversarial" in w.lower() and "same" in w.lower()]
        assert len(same_model_warnings) == 1, f"Expected 1 same-model warning, got {len(same_model_warnings)}: {same_model_warnings}"

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
        """use_fake_llm=False with no env keys → EXIT_PROVIDER_ERROR."""
        from skuld.end_to_end_flow import run_pipeline_from_dict
        from skuld.models import EXIT_PROVIDER_ERROR

        monkeypatch.delenv("SKULD_ANTHROPIC_KEY", raising=False)
        monkeypatch.delenv("SKULD_OPENAI_KEY", raising=False)

        data = _make_raw_yaml_input()
        result = run_pipeline_from_dict(data, use_fake_llm=False)
        assert result.exit_code == EXIT_PROVIDER_ERROR
        assert "API key not configured" in result.message
        assert "SKULD_ANTHROPIC_KEY" in result.message
        assert "SKULD_OPENAI_KEY" in result.message

    def test_unknown_model_returns_input_error(self, monkeypatch):
        """Unknown model in simple mode → EXIT_INPUT_ERROR (config error, not env)."""
        from skuld.end_to_end_flow import run_pipeline_from_dict

        monkeypatch.setenv("SKULD_ANTHROPIC_KEY", "sk-test")
        monkeypatch.setenv("SKULD_OPENAI_KEY", "sk-test")

        data = _make_raw_yaml_input()
        data["config"]["generator_model"] = "llama-3-unknown"
        result = run_pipeline_from_dict(data, use_fake_llm=False)
        assert result.exit_code == EXIT_INPUT_ERROR
        assert "Cannot determine provider" in result.message

    def test_unknown_model_returns_input_error_even_without_keys(self, monkeypatch):
        """Unknown model without keys → still EXIT_INPUT_ERROR (config before env)."""
        from skuld.end_to_end_flow import run_pipeline_from_dict

        monkeypatch.delenv("SKULD_ANTHROPIC_KEY", raising=False)
        monkeypatch.delenv("SKULD_OPENAI_KEY", raising=False)

        data = _make_raw_yaml_input()
        data["config"]["generator_model"] = "llama-3-unknown"
        result = run_pipeline_from_dict(data, use_fake_llm=False)
        assert result.exit_code == EXIT_INPUT_ERROR
        assert "Cannot determine provider" in result.message

    def test_non_string_model_returns_input_error(self, monkeypatch):
        """Non-string simple-mode model → EXIT_INPUT_ERROR, not traceback."""
        from skuld.end_to_end_flow import run_pipeline_from_dict

        monkeypatch.delenv("SKULD_ANTHROPIC_KEY", raising=False)
        monkeypatch.delenv("SKULD_OPENAI_KEY", raising=False)

        data = _make_raw_yaml_input()
        data["config"]["generator_model"] = 123
        result = run_pipeline_from_dict(data, use_fake_llm=False)
        assert result.exit_code == EXIT_INPUT_ERROR
        assert "generator_model must be a non-empty string" in result.message

    def test_real_provider_resolution_attempted(self, monkeypatch):
        """use_fake_llm=False with API key set → attempts real provider creation."""
        from skuld.end_to_end_flow import _resolve_llm_clients
        from skuld.llm_client import BudgetedLLMClient
        from unittest.mock import patch, MagicMock

        monkeypatch.setenv("SKULD_ANTHROPIC_KEY", "sk-test-dummy")

        with patch("skuld.providers.anthropic_client.AnthropicLLMClient") as mock_ac:
            config = {
                "generator_model": "claude-sonnet-4-20250514",
                "reviewer_model": "claude-haiku-4-20250514",
            }
            clients = _resolve_llm_clients(config)

        # Provider resolution succeeded and produced budgeted clients
        assert isinstance(clients["generator"], BudgetedLLMClient)
        assert isinstance(clients["reviewer"], BudgetedLLMClient)
        assert isinstance(clients["refinement"], BudgetedLLMClient)
        # AnthropicLLMClient was called for all three phases
        assert mock_ac.call_count == 3


# ---------------------------------------------------------------------------
# Tests: TestProviderErrorHandling (D-V2-1-1)
# ---------------------------------------------------------------------------

class TestProviderErrorHandling:
    """D-V2-1-1: Provider API errors produce controlled FlowResult, not tracebacks."""

    def test_generate_stage_provider_error_returns_exit_3(self):
        """ProviderAPIError during generation → EXIT_PROVIDER_ERROR."""
        from skuld.end_to_end_flow import run_pipeline_from_dict
        from skuld.models import EXIT_PROVIDER_ERROR
        from skuld.providers.base import ProviderAPIError
        from unittest.mock import patch

        from skuld.llm_client import FakeLLMClient

        data = _make_raw_yaml_input()
        mock_client = FakeLLMClient(error=ProviderAPIError("Anthropic rate limit exceeded", retryable=True))

        with patch("skuld.end_to_end_flow._prepare_fake_clients") as mock_prep:
            mock_prep.return_value = {"generator": mock_client, "reviewer": mock_client, "refinement": mock_client}
            result = run_pipeline_from_dict(data, use_fake_llm=True)

        assert result.exit_code == EXIT_PROVIDER_ERROR
        assert "rate limit" in result.message.lower()

    def test_review_stage_provider_error_returns_exit_3(self):
        """ProviderAPIError during review → EXIT_PROVIDER_ERROR."""
        from skuld.end_to_end_flow import _fake_test_cases_json, run_pipeline_from_dict
        from skuld.models import EXIT_PROVIDER_ERROR
        from skuld.providers.base import ProviderAPIError
        from unittest.mock import patch

        from skuld.llm_client import FakeLLMClient

        data = _make_raw_yaml_input()
        gen_client = FakeLLMClient(response_content=_fake_test_cases_json("STORY-1", ["AC-1", "AC-2"]))
        rev_client = FakeLLMClient(error=ProviderAPIError("OpenAI auth failed", retryable=False))
        ref_client = FakeLLMClient()

        with patch("skuld.end_to_end_flow._prepare_fake_clients") as mock_prep:
            mock_prep.return_value = {"generator": gen_client, "reviewer": rev_client, "refinement": ref_client}
            result = run_pipeline_from_dict(data, use_fake_llm=True)

        assert result.exit_code == EXIT_PROVIDER_ERROR
        assert "auth failed" in result.message.lower()

    def test_refine_stage_provider_error_returns_exit_3(self):
        """ProviderAPIError during refinement → EXIT_PROVIDER_ERROR."""
        from skuld.end_to_end_flow import _fake_review_feedback_json, _fake_test_cases_json, run_pipeline_from_dict
        from skuld.models import EXIT_PROVIDER_ERROR
        from skuld.providers.base import ProviderAPIError
        from unittest.mock import patch

        from skuld.llm_client import FakeLLMClient

        data = _make_raw_yaml_input()
        gen_client = FakeLLMClient(response_content=_fake_test_cases_json("STORY-1", ["AC-1", "AC-2"]))
        rev_client = FakeLLMClient(response_content=_fake_review_feedback_json())
        ref_client = FakeLLMClient(error=ProviderAPIError("Connection timeout", retryable=True))

        with patch("skuld.end_to_end_flow._prepare_fake_clients") as mock_prep:
            mock_prep.return_value = {"generator": gen_client, "reviewer": rev_client, "refinement": ref_client}
            result = run_pipeline_from_dict(data, use_fake_llm=True)

        assert result.exit_code == EXIT_PROVIDER_ERROR
        assert "timeout" in result.message.lower()

    def test_permanent_auth_error_returns_exit_3(self):
        """Non-retryable ProviderAPIError (auth) → EXIT_PROVIDER_ERROR with clear message."""
        from skuld.end_to_end_flow import run_pipeline_from_dict
        from skuld.models import EXIT_PROVIDER_ERROR
        from skuld.providers.base import ProviderAPIError
        from unittest.mock import patch

        from skuld.llm_client import FakeLLMClient

        data = _make_raw_yaml_input()
        mock_client = FakeLLMClient(error=ProviderAPIError(
            "Anthropic API key is invalid or expired. Verify SKULD_ANTHROPIC_KEY is correct.",
            retryable=False,
        ))

        with patch("skuld.end_to_end_flow._prepare_fake_clients") as mock_prep:
            mock_prep.return_value = {"generator": mock_client, "reviewer": mock_client, "refinement": mock_client}
            result = run_pipeline_from_dict(data, use_fake_llm=True)

        assert result.exit_code == EXIT_PROVIDER_ERROR
        assert "SKULD_ANTHROPIC_KEY" in result.message


# ---------------------------------------------------------------------------
# Tests: TestProviderResolution (V2-3, V2-4)
# ---------------------------------------------------------------------------

class TestProviderResolution:
    """Tests for _resolve_llm_clients and helper functions."""

    def test_infer_provider_claude(self):
        from skuld.end_to_end_flow import _infer_provider
        assert _infer_provider("claude-sonnet-4-20250514") == "anthropic"
        assert _infer_provider("claude-haiku-4-20250514") == "anthropic"

    def test_infer_provider_openai(self):
        from skuld.end_to_end_flow import _infer_provider
        assert _infer_provider("gpt-4o") == "openai"
        assert _infer_provider("gpt-5.5") == "openai"
        assert _infer_provider("o1-preview") == "openai"
        assert _infer_provider("o3-mini") == "openai"
        assert _infer_provider("o4-mini") == "openai"

    def test_infer_provider_unknown_raises(self):
        from skuld.end_to_end_flow import _infer_provider
        with pytest.raises(ValueError, match="Cannot determine provider"):
            _infer_provider("llama-3")

    def test_create_provider_unknown_raises(self):
        from skuld.end_to_end_flow import _create_provider_client
        with pytest.raises(ValueError, match="Unknown provider"):
            _create_provider_client("unknown", "model-x", 0.7, 4096)

    def test_simple_mode_resolution(self, monkeypatch):
        """Simple mode creates 3 budgeted clients from generator_model/reviewer_model."""
        from skuld.end_to_end_flow import _resolve_llm_clients
        from skuld.llm_client import BudgetedLLMClient
        from unittest.mock import patch, MagicMock

        monkeypatch.setenv("SKULD_ANTHROPIC_KEY", "sk-test")
        monkeypatch.setenv("SKULD_OPENAI_KEY", "sk-test")

        mock_anthropic = MagicMock()
        mock_openai = MagicMock()

        with patch("skuld.providers.anthropic_client.AnthropicLLMClient", return_value=mock_anthropic) as mock_ac, \
             patch("skuld.providers.openai_client.OpenAILLMClient", return_value=mock_openai) as mock_oc:
            config = {
                "generator_model": "claude-sonnet-4-20250514",
                "reviewer_model": "gpt-4o",
            }
            clients = _resolve_llm_clients(config)

        assert isinstance(clients["generator"], BudgetedLLMClient)
        assert isinstance(clients["reviewer"], BudgetedLLMClient)
        assert isinstance(clients["refinement"], BudgetedLLMClient)
        # Generator and refinement use anthropic, reviewer uses openai
        mock_ac.assert_called()  # at least once for generator (+ once for refinement)
        mock_oc.assert_called_once()  # once for reviewer

    def test_model_routing_mode_resolution(self, monkeypatch):
        """model_routing provides per-phase config."""
        from skuld.end_to_end_flow import _resolve_llm_clients
        from skuld.llm_client import BudgetedLLMClient
        from unittest.mock import patch, MagicMock

        monkeypatch.setenv("SKULD_ANTHROPIC_KEY", "sk-test")
        monkeypatch.setenv("SKULD_OPENAI_KEY", "sk-test")

        with patch("skuld.providers.anthropic_client.AnthropicLLMClient") as mock_ac, \
             patch("skuld.providers.openai_client.OpenAILLMClient") as mock_oc:
            config = {
                "model_routing": {
                    "generator": {"model": "claude-sonnet-4-20250514", "provider": "anthropic", "temperature": 0.7},
                    "reviewer": {"model": "gpt-4o", "provider": "openai", "temperature": 0.2},
                    "refinement": {"model": "claude-sonnet-4-20250514", "provider": "anthropic", "temperature": 0.5},
                }
            }
            clients = _resolve_llm_clients(config)

        assert isinstance(clients["generator"], BudgetedLLMClient)
        assert isinstance(clients["reviewer"], BudgetedLLMClient)
        assert isinstance(clients["refinement"], BudgetedLLMClient)

    def test_model_routing_missing_phase_raises(self, monkeypatch):
        """model_routing with missing phase raises ValueError."""
        from skuld.end_to_end_flow import _resolve_llm_clients

        monkeypatch.setenv("SKULD_ANTHROPIC_KEY", "sk-test")

        config = {
            "model_routing": {
                "generator": {"model": "claude-sonnet-4-20250514", "provider": "anthropic"},
                # missing reviewer and refinement
            }
        }
        with pytest.raises(ValueError, match="reviewer"):
            _resolve_llm_clients(config)

    def test_model_routing_infers_provider_from_model(self, monkeypatch):
        """model_routing without explicit provider infers from model name."""
        from skuld.end_to_end_flow import _resolve_llm_clients
        from unittest.mock import patch

        monkeypatch.setenv("SKULD_ANTHROPIC_KEY", "sk-test")
        monkeypatch.setenv("SKULD_OPENAI_KEY", "sk-test")

        with patch("skuld.providers.anthropic_client.AnthropicLLMClient") as mock_ac, \
             patch("skuld.providers.openai_client.OpenAILLMClient") as mock_oc:
            config = {
                "model_routing": {
                    "generator": {"model": "claude-sonnet-4-20250514", "temperature": 0.7},
                    "reviewer": {"model": "gpt-4o", "temperature": 0.2},
                    "refinement": {"model": "claude-sonnet-4-20250514", "temperature": 0.5},
                }
            }
            clients = _resolve_llm_clients(config)

        # Should have inferred anthropic for claude, openai for gpt
        assert mock_ac.call_count == 2  # generator + refinement
        assert mock_oc.call_count == 1  # reviewer

    def test_returns_budgeted_clients_v2_4(self, monkeypatch):
        """V2-4: All resolved clients are wrapped in BudgetedLLMClient."""
        from skuld.end_to_end_flow import _resolve_llm_clients
        from skuld.llm_client import BudgetedLLMClient
        from unittest.mock import patch

        monkeypatch.setenv("SKULD_ANTHROPIC_KEY", "sk-test")

        with patch("skuld.providers.anthropic_client.AnthropicLLMClient"):
            config = {"generator_model": "claude-sonnet-4-20250514", "reviewer_model": "claude-haiku-4-20250514"}
            clients = _resolve_llm_clients(config)

        for phase in ("generator", "reviewer", "refinement"):
            assert isinstance(clients[phase], BudgetedLLMClient), f"{phase} not wrapped in BudgetedLLMClient"

    def test_no_api_key_raises_clear_error(self, monkeypatch):
        """No API keys set at all → ValueError with actionable message."""
        from skuld.end_to_end_flow import _resolve_llm_clients

        monkeypatch.delenv("SKULD_ANTHROPIC_KEY", raising=False)
        monkeypatch.delenv("SKULD_OPENAI_KEY", raising=False)

        config = {"generator_model": "claude-sonnet-4-20250514", "reviewer_model": "gpt-4o"}
        with pytest.raises(ValueError):
            _resolve_llm_clients(config)

    def test_model_routing_missing_model_key_raises(self, monkeypatch):
        """model_routing phase without 'model' key raises ValueError."""
        from skuld.end_to_end_flow import _resolve_llm_clients

        monkeypatch.setenv("SKULD_ANTHROPIC_KEY", "sk-test")
        config = {
            "model_routing": {
                "generator": {"temperature": 0.7},  # no model key
                "reviewer": {"model": "gpt-4o"},
                "refinement": {"model": "claude-sonnet-4-20250514"},
            }
        }
        with pytest.raises(ValueError, match="model_routing.generator.model"):
            _resolve_llm_clients(config)

    def test_model_routing_non_dict_phase_raises(self, monkeypatch):
        """model_routing phase that is not a dict raises ValueError."""
        from skuld.end_to_end_flow import _resolve_llm_clients

        monkeypatch.setenv("SKULD_ANTHROPIC_KEY", "sk-test")
        config = {
            "model_routing": {
                "generator": "claude-sonnet-4",  # string instead of dict
                "reviewer": {"model": "gpt-4o"},
                "refinement": {"model": "claude-sonnet-4-20250514"},
            }
        }
        with pytest.raises(ValueError, match="must be a mapping"):
            _resolve_llm_clients(config)

    def test_model_routing_blank_model_raises(self, monkeypatch):
        """model_routing phase with blank model raises ValueError."""
        from skuld.end_to_end_flow import _resolve_llm_clients

        monkeypatch.setenv("SKULD_ANTHROPIC_KEY", "sk-test")
        config = {
            "model_routing": {
                "generator": {"model": "   "},
                "reviewer": {"model": "gpt-4o"},
                "refinement": {"model": "claude-sonnet-4-20250514"},
            }
        }
        with pytest.raises(ValueError, match="model_routing.generator.model"):
            _resolve_llm_clients(config)

    def test_shared_budget_across_phases(self, monkeypatch):
        """All three phases share a single token budget."""
        from skuld.end_to_end_flow import _resolve_llm_clients
        from skuld.llm_client import BudgetedLLMClient
        from unittest.mock import patch

        monkeypatch.setenv("SKULD_ANTHROPIC_KEY", "sk-test")

        with patch("skuld.providers.anthropic_client.AnthropicLLMClient"):
            config = {
                "generator_model": "claude-sonnet-4-20250514",
                "reviewer_model": "claude-haiku-4-20250514",
                "max_tokens_per_run": 10000,
            }
            clients = _resolve_llm_clients(config)

        # All three should share the same budget object
        assert clients["generator"]._budget is clients["reviewer"]._budget
        assert clients["reviewer"]._budget is clients["refinement"]._budget
        assert clients["generator"]._budget.max_tokens == 10000

    def test_shared_budget_model_routing(self, monkeypatch):
        """Advanced model_routing mode also shares budget."""
        from skuld.end_to_end_flow import _resolve_llm_clients
        from unittest.mock import patch

        monkeypatch.setenv("SKULD_ANTHROPIC_KEY", "sk-test")
        monkeypatch.setenv("SKULD_OPENAI_KEY", "sk-test")

        with patch("skuld.providers.anthropic_client.AnthropicLLMClient"), \
             patch("skuld.providers.openai_client.OpenAILLMClient"):
            config = {
                "max_tokens_per_run": 20000,
                "model_routing": {
                    "generator": {"model": "claude-sonnet-4-20250514", "provider": "anthropic"},
                    "reviewer": {"model": "gpt-4o", "provider": "openai"},
                    "refinement": {"model": "claude-sonnet-4-20250514", "provider": "anthropic"},
                }
            }
            clients = _resolve_llm_clients(config)

        assert clients["generator"]._budget is clients["reviewer"]._budget
        assert clients["reviewer"]._budget is clients["refinement"]._budget
        assert clients["generator"]._budget.max_tokens == 20000


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


# ---------------------------------------------------------------------------
# Tests: TestTruncatedResponse (Fix 1)
# ---------------------------------------------------------------------------

class TestTruncatedResponse:
    """Pipeline returns EXIT_VALIDATION_ERROR when LLM response is truncated."""

    def test_truncated_generation_returns_validation_error(self):
        """finish_reason='length' on generation → EXIT_VALIDATION_ERROR."""
        from skuld.end_to_end_flow import _run_from_package
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient
        from unittest.mock import patch

        normalized = _make_normalized_input()
        truncated_client = FakeLLMClient(
            response_content='{"test_cases": [',  # syntactically valid start, truncated
            finish_reason="length",
        )
        budgeted = BudgetedLLMClient(truncated_client, max_tokens=32000)

        with patch(
            "skuld.end_to_end_flow._prepare_fake_clients",
            return_value={"generator": budgeted, "reviewer": budgeted, "refinement": budgeted},
        ):
            result = _run_from_package(
                normalized, rtm_file=None, force=False, output_format=None, use_fake_llm=True
            )
        assert result.exit_code == EXIT_VALIDATION_ERROR
        assert "truncated" in result.message.lower() or "finish_reason" in result.message


# ---------------------------------------------------------------------------
# Tests: TestOutputFormatResolution (Fix 3)
# ---------------------------------------------------------------------------

class TestOutputFormatResolution:
    """config.output_format in YAML is honoured when no explicit param is passed."""

    def test_config_output_format_json_produces_json(self):
        """When config.output_format='json' and no explicit param → output is JSON."""
        from skuld.end_to_end_flow import run_pipeline_from_dict

        data = _make_raw_yaml_input()
        data["config"] = {**data.get("config", {}), "output_format": "json"}
        # No explicit output_format argument — must use config
        result = run_pipeline_from_dict(data, use_fake_llm=True)
        assert result.exit_code == EXIT_OK
        parsed = json.loads(result.message)
        assert "test_cases" in parsed
        assert "confidence_score" in parsed

    def test_explicit_output_format_overrides_config(self):
        """Explicit output_format='markdown' wins even when config says 'json'."""
        from skuld.end_to_end_flow import run_pipeline_from_dict

        data = _make_raw_yaml_input()
        data["config"] = {**data.get("config", {}), "output_format": "json"}
        result = run_pipeline_from_dict(data, output_format="markdown", use_fake_llm=True)
        assert result.exit_code == EXIT_OK
        assert "## Test Cases" in result.message
        # Must NOT be JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.message)

    def test_invalid_output_format_in_config_returns_input_error(self):
        """config.output_format='xml' (invalid) → EXIT_INPUT_ERROR with clear message."""
        from skuld.end_to_end_flow import run_pipeline_from_dict

        data = _make_raw_yaml_input()
        data["config"] = {**data.get("config", {}), "output_format": "xml"}
        result = run_pipeline_from_dict(data, use_fake_llm=True)
        assert result.exit_code == EXIT_INPUT_ERROR
        assert "output_format" in result.message
        assert "xml" in result.message

    def test_null_output_format_in_config_uses_default_markdown(self):
        """config.output_format=None (YAML null) → falls back to markdown."""
        from skuld.end_to_end_flow import run_pipeline_from_dict

        data = _make_raw_yaml_input()
        data["config"] = {**data.get("config", {}), "output_format": None}
        result = run_pipeline_from_dict(data, use_fake_llm=True)
        assert result.exit_code == EXIT_OK
        assert "## Test Cases" in result.message


# ---------------------------------------------------------------------------
# Tests: TestDegradedScenarios
# ---------------------------------------------------------------------------

class TestDegradedScenarios:
    """Prove the scoring/gap path can go meaningfully red.

    Each test patches _prepare_fake_clients with hand-crafted incomplete
    responses to verify that degraded inputs produce degraded scores and
    explicit gap reports — not just different shades of 'good'.
    """

    def _make_input(self) -> dict:
        return {
            "story": {"id": "S-1", "title": "T", "description": "D"},
            "acceptance_criteria": [
                {"id": f"AC-{i}", "description": f"AC {i}", "criticality": "medium"}
                for i in range(1, 4)
            ],
            "config": {"generator_model": "claude-sonnet-4-20250514", "reviewer_model": "gpt-4o"},
        }

    def _fake_review(self) -> str:
        return json.dumps({
            "flagged_tests": [],
            "missing_scenarios": [],
            "quality_scores": {"coverage": 0.9, "clarity": 0.85, "testability": 0.9},
            "suggestions": [],
        })

    def _patch_fake_clients(self, gen_response: str, review_response: str):
        """Return a patch context using sequential responses for the shared client."""
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient

        inner = FakeLLMClient(responses=[gen_response, review_response, gen_response])
        budgeted = BudgetedLLMClient(inner, max_tokens=32000)
        return {"generator": budgeted, "reviewer": budgeted, "refinement": budgeted}

    def test_functional_only_degradation(self):
        """All ACs get only functional tests → medium-tier confidence (50–65 range),
        with explicit no-negative and no-edge-case gap messages for every AC."""
        from unittest.mock import patch

        from skuld.end_to_end_flow import run_pipeline_from_dict

        gen_response = json.dumps({"test_cases": [
            {"id": f"TC-00{i}", "story_id": "S-1", "ac_ids": [f"AC-{i}"],
             "test_type": "functional", "priority": "P1", "preconditions": "Running",
             "steps": ["Step 1"], "expected_result": f"OK for AC-{i}",
             "test_data": None, "automatable": True}
            for i in range(1, 4)
        ]})

        with patch(
            "skuld.end_to_end_flow._prepare_fake_clients",
            return_value=self._patch_fake_clients(gen_response, self._fake_review()),
        ):
            result = run_pipeline_from_dict(self._make_input(), use_fake_llm=True)

        assert result.exit_code == EXIT_OK
        assert "Negative Coverage: 0%" in result.message
        assert "Edge-Case Coverage: 0%" in result.message
        for i in range(1, 4):
            assert f"AC-{i}: no negative test" in result.message
            assert f"AC-{i}: no edge-case test" in result.message
        import re
        match = re.search(r"Overall Confidence:\s*([\d.]+)", result.message)
        assert match, "Overall Confidence not found in output"
        score = float(match.group(1))
        assert 55.0 <= score < 58.0, f"Expected functional-only score 55–58, got {score}"
        assert "(medium)" in result.message

    def test_mixed_degradation_medium_tier(self):
        """AC-1 partial, AC-2 partial, AC-3 uncovered, orphan → medium-tier confidence (50–65 range)."""
        from unittest.mock import patch

        from skuld.end_to_end_flow import run_pipeline_from_dict

        gen_response = json.dumps({"test_cases": [
            {"id": "TC-001", "story_id": "S-1", "ac_ids": ["AC-1"],
             "test_type": "functional", "priority": "P1", "preconditions": "Running",
             "steps": ["Step 1"], "expected_result": "OK", "test_data": None, "automatable": True},
            {"id": "TC-002", "story_id": "S-1", "ac_ids": ["AC-2"],
             "test_type": "functional", "priority": "P1", "preconditions": "Running",
             "steps": ["Step 1"], "expected_result": "OK", "test_data": None, "automatable": True},
            {"id": "TC-003", "story_id": "S-1", "ac_ids": ["AC-2"],
             "test_type": "negative", "priority": "P2", "preconditions": "Running",
             "steps": ["Step 1"], "expected_result": "Error", "test_data": "bad", "automatable": True},
            {"id": "TC-ORPHAN", "story_id": "S-1", "ac_ids": ["AC-99"],
             "test_type": "functional", "priority": "P1", "preconditions": "Running",
             "steps": ["Step 1"], "expected_result": "OK", "test_data": None, "automatable": True},
        ]})

        with patch(
            "skuld.end_to_end_flow._prepare_fake_clients",
            return_value=self._patch_fake_clients(gen_response, self._fake_review()),
        ):
            result = run_pipeline_from_dict(self._make_input(), use_fake_llm=True)

        assert result.exit_code == EXIT_OK
        assert "AC-1: no negative test" in result.message
        assert "AC-1: no edge-case test" in result.message
        assert "AC-2: no edge-case test" in result.message
        assert "AC-3: no test coverage" in result.message
        assert "Orphan Tests: 1" in result.message
        import re
        match = re.search(r"Overall Confidence:\s*([\d.]+)", result.message)
        assert match, "Overall Confidence not found in output"
        score = float(match.group(1))
        assert 56.0 <= score < 59.0, f"Expected mixed-medium score 56–59, got {score}"
        assert "(medium)" in result.message

    def test_orphan_only_penalises_score(self):
        """Full coverage on all ACs + 2 orphan tests → score < perfect, no coverage gaps."""
        from unittest.mock import patch

        from skuld.end_to_end_flow import run_pipeline_from_dict

        cases = []
        for i in range(1, 4):
            for tt, sfx in [("functional", ""), ("negative", "-N"), ("edge-case", "-E")]:
                cases.append({
                    "id": f"TC-{i}{sfx}", "story_id": "S-1", "ac_ids": [f"AC-{i}"],
                    "test_type": tt, "priority": "P1", "preconditions": "Running",
                    "steps": ["Step 1"], "expected_result": f"OK", "test_data": None, "automatable": True,
                })
        # Two orphan tests mapping to non-existent ACs
        cases.append({"id": "TC-ORP-1", "story_id": "S-1", "ac_ids": ["AC-99"],
                      "test_type": "functional", "priority": "P1", "preconditions": "Running",
                      "steps": ["Step 1"], "expected_result": "OK", "test_data": None, "automatable": True})
        cases.append({"id": "TC-ORP-2", "story_id": "S-1", "ac_ids": ["AC-100"],
                      "test_type": "functional", "priority": "P1", "preconditions": "Running",
                      "steps": ["Step 1"], "expected_result": "OK", "test_data": None, "automatable": True})
        gen_response = json.dumps({"test_cases": cases})

        with patch(
            "skuld.end_to_end_flow._prepare_fake_clients",
            return_value=self._patch_fake_clients(gen_response, self._fake_review()),
        ):
            result = run_pipeline_from_dict(self._make_input(), use_fake_llm=True)

        assert result.exit_code == EXIT_OK
        assert "AC Coverage: 100%" in result.message
        assert "Negative Coverage: 100%" in result.message
        assert "Edge-Case Coverage: 100%" in result.message
        assert "No coverage gaps identified." in result.message
        assert "Orphan Tests: 2" in result.message
        import re
        match = re.search(r"Overall Confidence:\s*([\d.]+)", result.message)
        assert match, "Overall Confidence not found in output"
        score = float(match.group(1))
        assert 97.0 <= score < 99.0, f"Expected orphan-penalized score 97–99, got {score}"
        assert "(high)" in result.message

    def test_severe_degradation_low_tier(self):
        """4 ACs, only AC-1 has 1 functional test, 3 fully uncovered + 2 orphans → low tier
        from severe under-coverage. Orphan penalty contributes but coverage gaps dominate."""
        from unittest.mock import patch

        from skuld.end_to_end_flow import run_pipeline_from_dict

        input_data = {
            "story": {"id": "S-1", "title": "T", "description": "D"},
            "acceptance_criteria": [
                {"id": f"AC-{i}", "description": f"AC {i}", "criticality": "medium"}
                for i in range(1, 5)
            ],
            "config": {"generator_model": "claude-sonnet-4-20250514", "reviewer_model": "gpt-4o"},
        }

        def _tc(id_, ac, tt):
            return {"id": id_, "story_id": "S-1", "ac_ids": [ac], "test_type": tt,
                    "priority": "P1", "preconditions": "Running", "steps": ["Step 1"],
                    "expected_result": "OK", "test_data": None, "automatable": True}

        gen_response = json.dumps({"test_cases": [
            _tc("TC-001", "AC-1", "functional"),
            _tc("TC-ORP-1", "AC-99", "functional"),
            _tc("TC-ORP-2", "AC-100", "functional"),
        ]})

        with patch(
            "skuld.end_to_end_flow._prepare_fake_clients",
            return_value=self._patch_fake_clients(gen_response, self._fake_review()),
        ):
            result = run_pipeline_from_dict(input_data, use_fake_llm=True)

        assert result.exit_code == EXIT_OK
        assert "AC-1: no negative test" in result.message
        assert "AC-1: no edge-case test" in result.message
        assert "AC-2: no test coverage" in result.message
        assert "AC-3: no test coverage" in result.message
        assert "AC-4: no test coverage" in result.message
        assert "Orphan Tests: 2" in result.message
        import re
        match = re.search(r"Overall Confidence:\s*([\d.]+)", result.message)
        assert match, "Overall Confidence not found in output"
        score = float(match.group(1))
        assert score < 50.0, f"Expected low-tier score < 50, got {score}"
        assert "(low)" in result.message

    def test_stage_wiring_uses_refinement_output(self):
        """Pipeline uses the correct client for each stage: generator, reviewer, refinement."""
        from unittest.mock import patch

        from skuld.end_to_end_flow import run_pipeline_from_dict
        from skuld.llm_client import BudgetedLLMClient, FakeLLMClient

        def _tc(id_, ac, tt):
            return {"id": id_, "story_id": "S-1", "ac_ids": [ac], "test_type": tt,
                    "priority": "P1", "preconditions": "Running", "steps": ["Step 1"],
                    "expected_result": "OK", "test_data": None, "automatable": True}

        gen_cases = json.dumps({"test_cases": [
            _tc("TC-GEN-001", "AC-1", "functional"),
            _tc("TC-GEN-002", "AC-1", "negative"),
            _tc("TC-GEN-003", "AC-1", "edge-case"),
        ]})
        refined_cases = json.dumps({"test_cases": [
            _tc("TC-REFINED-001", "AC-1", "functional"),
            _tc("TC-REFINED-002", "AC-1", "negative"),
            _tc("TC-REFINED-003", "AC-1", "edge-case"),
        ]})

        gen_inner = FakeLLMClient(response_content=gen_cases)
        rev_inner = FakeLLMClient(response_content=self._fake_review())
        ref_inner = FakeLLMClient(response_content=refined_cases)

        gen_client = BudgetedLLMClient(gen_inner, max_tokens=32000)
        rev_client = BudgetedLLMClient(rev_inner, max_tokens=32000)
        ref_client = BudgetedLLMClient(ref_inner, max_tokens=32000)

        single_ac_input = {
            "story": {"id": "S-1", "title": "T", "description": "D"},
            "acceptance_criteria": [{"id": "AC-1", "description": "AC 1", "criticality": "medium"}],
            "config": {"generator_model": "claude-sonnet-4-20250514", "reviewer_model": "gpt-4o"},
        }

        with patch(
            "skuld.end_to_end_flow._prepare_fake_clients",
            return_value={"generator": gen_client, "reviewer": rev_client, "refinement": ref_client},
        ):
            result = run_pipeline_from_dict(single_ac_input, use_fake_llm=True)

        assert result.exit_code == EXIT_OK
        # Final report uses refinement output, not generator
        assert "TC-REFINED-001" in result.message, "Final report must contain refinement output"
        assert "TC-GEN-001" not in result.message, "Final report must NOT contain raw generator output"
        # Slot integrity: each inner client was called exactly once
        assert gen_inner.call_count == 1, f"Generator should be called once, got {gen_inner.call_count}"
        assert rev_inner.call_count == 1, f"Reviewer should be called once, got {rev_inner.call_count}"
        assert ref_inner.call_count == 1, f"Refinement should be called once, got {ref_inner.call_count}"
        # Request integrity: each stage receives the correct prompt type/content
        assert gen_inner.last_request is not None
        assert "expert test case writer specializing in comprehensive test" in gen_inner.last_request.system_prompt
        assert "## Output Format" in gen_inner.last_request.system_prompt
        assert "<story_context>" in gen_inner.last_request.user_prompt
        assert "<acceptance_criteria>" in gen_inner.last_request.user_prompt

        assert rev_inner.last_request is not None
        assert "adversarial test reviewer" in rev_inner.last_request.system_prompt
        assert "## Review Instructions" in rev_inner.last_request.system_prompt
        assert "## Generated Test Cases" in rev_inner.last_request.user_prompt
        assert "TC-GEN-001" in rev_inner.last_request.user_prompt

        assert ref_inner.last_request is not None
        assert "You are an expert test case writer. You will refine a set of test cases" in ref_inner.last_request.system_prompt
        assert "## Refinement Instructions" in ref_inner.last_request.system_prompt
        assert "## Original Test Cases" in ref_inner.last_request.user_prompt
        assert "TC-GEN-001" in ref_inner.last_request.user_prompt
        assert "## Review Feedback" in ref_inner.last_request.user_prompt
        assert "flagged_tests" in ref_inner.last_request.user_prompt
        assert "quality_scores" in ref_inner.last_request.user_prompt

