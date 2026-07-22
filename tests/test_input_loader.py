"""Tests for skuld.input_loader — T3: Input loading and validation."""
from __future__ import annotations

import pathlib
import textwrap

import pytest
import yaml

from skuld.input_loader import (
    InputValidationError,
    _require_keys,
    load_input,
    validate_raw,
)
from skuld.models import InputPackage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_INPUT = {
    "story": {
        "id": "PROJ-1234",
        "title": "User login with MFA",
        "description": "As a user, I want to log in with MFA.",
    },
    "acceptance_criteria": [
        {"id": "AC-1", "description": "User can log in with valid credentials", "criticality": "high"},
        {"id": "AC-2", "description": "MFA code sent after password", "criticality": "high"},
        {"id": "AC-3", "description": "Login fails after 3 incorrect MFA attempts", "criticality": "medium"},
    ],
}


def _write_yaml(tmp_path: pathlib.Path, data: dict, filename: str = "input.yaml") -> pathlib.Path:
    p = tmp_path / filename
    p.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# _require_keys helper
# ---------------------------------------------------------------------------


class TestRequireKeys:
    def test_passes_when_all_present(self):
        _require_keys({"a": 1, "b": 2}, ["a", "b"], "test_context")

    def test_raises_on_missing_key(self):
        with pytest.raises(InputValidationError, match="Missing required field 'c'"):
            _require_keys({"a": 1}, ["a", "c"], "test_context")

    def test_context_in_error_message(self):
        with pytest.raises(InputValidationError, match="in story"):
            _require_keys({}, ["id"], "story")


# ---------------------------------------------------------------------------
# validate_raw — story validation
# ---------------------------------------------------------------------------


class TestValidateRawStory:
    def test_valid_input_passes(self):
        result = validate_raw(VALID_INPUT)
        assert result["story"]["id"] == "PROJ-1234"

    def test_missing_story_key_raises(self):
        data = {**VALID_INPUT}
        del data["story"]
        with pytest.raises(InputValidationError, match="Missing required field 'story'"):
            validate_raw(data)

    def test_missing_story_id_raises(self):
        data = {**VALID_INPUT, "story": {"title": "X", "description": "Y"}}
        with pytest.raises(InputValidationError, match="Missing required field 'id'"):
            validate_raw(data)

    def test_missing_story_title_raises(self):
        data = {**VALID_INPUT, "story": {"id": "X", "description": "Y"}}
        with pytest.raises(InputValidationError, match="Missing required field 'title'"):
            validate_raw(data)

    def test_missing_story_description_raises(self):
        data = {**VALID_INPUT, "story": {"id": "X", "title": "Y"}}
        with pytest.raises(InputValidationError, match="Missing required field 'description'"):
            validate_raw(data)

    def test_non_dict_top_level_raises(self):
        with pytest.raises(InputValidationError, match="must be a mapping"):
            validate_raw("not a dict")

    def test_story_is_list_raises(self):
        data = {**VALID_INPUT, "story": ["not", "a", "dict"]}
        with pytest.raises(InputValidationError, match="story must be a mapping"):
            validate_raw(data)

    def test_story_id_empty_string_raises(self):
        data = {**VALID_INPUT, "story": {"id": "", "title": "X", "description": "Y"}}
        with pytest.raises(InputValidationError, match="must not be empty"):
            validate_raw(data)

    def test_story_title_empty_string_raises(self):
        data = {**VALID_INPUT, "story": {"id": "X", "title": "", "description": "Y"}}
        with pytest.raises(InputValidationError, match="must not be empty"):
            validate_raw(data)


# ---------------------------------------------------------------------------
# validate_raw — acceptance criteria validation
# ---------------------------------------------------------------------------


class TestValidateRawAC:
    def test_missing_acceptance_criteria_raises(self):
        data = {"story": VALID_INPUT["story"]}
        with pytest.raises(InputValidationError, match="Missing required field 'acceptance_criteria'"):
            validate_raw(data)

    def test_empty_ac_list_raises(self):
        data = {**VALID_INPUT, "acceptance_criteria": []}
        with pytest.raises(InputValidationError, match="at least one acceptance criterion"):
            validate_raw(data)

    def test_ac_missing_id_raises(self):
        data = {**VALID_INPUT, "acceptance_criteria": [{"description": "X"}]}
        with pytest.raises(InputValidationError, match="Missing required field 'id'"):
            validate_raw(data)

    def test_ac_missing_description_raises(self):
        data = {**VALID_INPUT, "acceptance_criteria": [{"id": "AC-1"}]}
        with pytest.raises(InputValidationError, match="Missing required field 'description'"):
            validate_raw(data)

    def test_criticality_defaults_to_medium(self):
        data = {
            **VALID_INPUT,
            "acceptance_criteria": [{"id": "AC-1", "description": "Something"}],
        }
        result = validate_raw(data)
        assert result["acceptance_criteria"][0]["criticality"] == "medium"

    def test_invalid_criticality_raises(self):
        data = {
            **VALID_INPUT,
            "acceptance_criteria": [{"id": "AC-1", "description": "X", "criticality": "extreme"}],
        }
        with pytest.raises(InputValidationError, match="criticality.*must be one of"):
            validate_raw(data)

    def test_duplicate_ac_ids_raises(self):
        data = {
            **VALID_INPUT,
            "acceptance_criteria": [
                {"id": "AC-1", "description": "First"},
                {"id": "AC-1", "description": "Duplicate"},
            ],
        }
        with pytest.raises(InputValidationError, match="Duplicate.*AC-1"):
            validate_raw(data)

    def test_acceptance_criteria_not_a_list_raises(self):
        data = {**VALID_INPUT, "acceptance_criteria": {"id": "AC-1", "description": "X"}}
        with pytest.raises(InputValidationError, match="must be a list"):
            validate_raw(data)

    def test_single_ac_passes(self):
        data = {**VALID_INPUT, "acceptance_criteria": [{"id": "AC-1", "description": "Only one"}]}
        result = validate_raw(data)
        assert len(result["acceptance_criteria"]) == 1

    def test_explicit_null_criticality_defaults_to_medium(self):
        data = {
            **VALID_INPUT,
            "acceptance_criteria": [{"id": "AC-1", "description": "X", "criticality": None}],
        }
        result = validate_raw(data)
        assert result["acceptance_criteria"][0]["criticality"] == "medium"


# ---------------------------------------------------------------------------
# validate_raw — AC count guardrails
# ---------------------------------------------------------------------------


class TestACCountGuardrails:
    def _make_acs(self, count: int) -> list[dict]:
        return [{"id": f"AC-{i}", "description": f"Criterion {i}"} for i in range(1, count + 1)]

    def test_15_acs_passes_without_warning(self):
        data = {**VALID_INPUT, "acceptance_criteria": self._make_acs(15)}
        result = validate_raw(data)
        assert "_warnings" not in result or "AC count" not in str(result.get("_warnings", []))

    def test_16_acs_produces_warning(self):
        data = {**VALID_INPUT, "acceptance_criteria": self._make_acs(16)}
        result = validate_raw(data)
        assert any("AC count" in w for w in result.get("_warnings", []))

    def test_30_acs_passes(self):
        data = {**VALID_INPUT, "acceptance_criteria": self._make_acs(30)}
        result = validate_raw(data)
        assert len(result["acceptance_criteria"]) == 30

    def test_31_acs_raises(self):
        data = {**VALID_INPUT, "acceptance_criteria": self._make_acs(31)}
        with pytest.raises(InputValidationError, match="exceeds maximum.*30"):
            validate_raw(data)


# ---------------------------------------------------------------------------
# validate_raw — strategy_ref HITL gate
# ---------------------------------------------------------------------------


class TestStrategyRefValidation:
    def test_no_strategy_ref_passes(self):
        result = validate_raw(VALID_INPUT)
        assert "strategy_ref" not in result or result.get("strategy_ref") is None

    def test_strategy_ref_with_approved_passes(self):
        data = {
            **VALID_INPUT,
            "strategy_ref": {"path": "strategy.md", "approved": True, "reviewed_by": "sandeep"},
        }
        result = validate_raw(data)
        assert result["strategy_ref"]["approved"] is True

    def test_strategy_ref_without_approved_warns(self):
        data = {
            **VALID_INPUT,
            "strategy_ref": {"path": "strategy.md"},
        }
        result = validate_raw(data)
        assert any("strategy" in w.lower() for w in result.get("_warnings", []))

    def test_strategy_ref_with_reviewed_by_only_passes(self):
        data = {
            **VALID_INPUT,
            "strategy_ref": {"path": "strategy.md", "reviewed_by": "sandeep"},
        }
        result = validate_raw(data)
        # Should pass without warning since reviewed_by is present
        warnings = result.get("_warnings", [])
        assert not any("strategy" in w.lower() for w in warnings)

    def test_strategy_ref_approved_false_warns(self):
        data = {
            **VALID_INPUT,
            "strategy_ref": {"path": "strategy.md", "approved": False},
        }
        result = validate_raw(data)
        assert any("strategy" in w.lower() for w in result.get("_warnings", []))

    def test_strategy_ref_reviewed_by_empty_string_warns(self):
        data = {
            **VALID_INPUT,
            "strategy_ref": {"path": "strategy.md", "reviewed_by": ""},
        }
        result = validate_raw(data)
        assert any("strategy" in w.lower() for w in result.get("_warnings", []))


# ---------------------------------------------------------------------------
# validate_raw — config defaults
# ---------------------------------------------------------------------------


class TestConfigDefaults:
    def test_missing_config_gets_defaults(self):
        result = validate_raw(VALID_INPUT)
        config = result["config"]
        assert config["generator_model"] == "claude-sonnet-4-20250514"
        assert config["reviewer_model"] == "gpt-4o"
        assert config["min_negative_per_ac"] == 1
        assert config["min_edge_case_per_ac"] == 1
        assert config["output_format"] == "markdown"

    def test_provided_config_preserved(self):
        data = {
            **VALID_INPUT,
            "config": {"generator_model": "gpt", "reviewer_model": "claude", "output_format": "json"},
        }
        result = validate_raw(data)
        assert result["config"]["generator_model"] == "gpt"
        assert result["config"]["reviewer_model"] == "claude"
        assert result["config"]["output_format"] == "json"

    def test_partial_config_fills_missing(self):
        data = {**VALID_INPUT, "config": {"generator_model": "ollama"}}
        result = validate_raw(data)
        assert result["config"]["generator_model"] == "ollama"
        assert result["config"]["reviewer_model"] == "gpt-4o"  # default

    def test_explicit_null_config_gets_defaults(self):
        data = {**VALID_INPUT, "config": None}
        result = validate_raw(data)
        assert result["config"]["generator_model"] == "claude-sonnet-4-20250514"


class TestProviderConfigValidation:
    def test_top_level_provider_config_numeric_strings_are_coerced(self):
        data = {
            **VALID_INPUT,
            "config": {
                "generator_model": "claude-sonnet-4-20250514",
                "reviewer_model": "gpt-4o",
                "generator_temperature": "0.3",
                "reviewer_temperature": "0.2",
                "refinement_temperature": "0.5",
                "max_tokens": "8192",
                "max_tokens_per_run": "64000",
            },
        }
        result = validate_raw(data)
        config = result["config"]
        assert config["generator_temperature"] == 0.3
        assert config["reviewer_temperature"] == 0.2
        assert config["refinement_temperature"] == 0.5
        assert config["max_tokens"] == 8192
        assert config["max_tokens_per_run"] == 64000

    def test_invalid_top_level_temperature_raises(self):
        data = {
            **VALID_INPUT,
            "config": {
                "generator_model": "claude-sonnet-4-20250514",
                "reviewer_model": "gpt-4o",
                "generator_temperature": "hot",
            },
        }
        with pytest.raises(InputValidationError, match="generator_temperature"):
            validate_raw(data)

    def test_negative_max_tokens_raises(self):
        data = {
            **VALID_INPUT,
            "config": {
                "generator_model": "claude-sonnet-4-20250514",
                "reviewer_model": "gpt-4o",
                "max_tokens": -1,
            },
        }
        with pytest.raises(InputValidationError, match="max_tokens"):
            validate_raw(data)

    def test_model_routing_numeric_strings_are_coerced(self):
        data = {
            **VALID_INPUT,
            "config": {
                "model_routing": {
                    "generator": {
                        "model": "claude-sonnet-4-20250514",
                        "provider": "anthropic",
                        "temperature": "0.7",
                        "max_tokens": "4096",
                    },
                    "reviewer": {
                        "model": "gpt-4o",
                        "provider": "openai",
                        "temperature": "0.2",
                        "max_tokens": "2048",
                    },
                    "refinement": {
                        "model": "claude-sonnet-4-20250514",
                        "provider": "anthropic",
                        "temperature": "0.5",
                        "max_tokens": "4096",
                    },
                },
                "max_tokens_per_run": "32000",
            },
        }
        result = validate_raw(data)
        routing = result["config"]["model_routing"]
        assert routing["generator"]["temperature"] == 0.7
        assert routing["generator"]["max_tokens"] == 4096
        assert routing["reviewer"]["temperature"] == 0.2
        assert routing["reviewer"]["max_tokens"] == 2048
        assert result["config"]["max_tokens_per_run"] == 32000

    def test_model_routing_invalid_provider_raises(self):
        data = {
            **VALID_INPUT,
            "config": {
                "model_routing": {
                    "generator": {"model": "claude-sonnet-4-20250514", "provider": "anthropic"},
                    "reviewer": {"model": "gpt-4o", "provider": "azure-openai"},
                    "refinement": {"model": "claude-sonnet-4-20250514", "provider": "anthropic"},
                }
            },
        }
        with pytest.raises(InputValidationError, match="provider"):
            validate_raw(data)

    def test_model_routing_provider_model_mismatch_raises(self):
        data = {
            **VALID_INPUT,
            "config": {
                "model_routing": {
                    "generator": {"model": "gpt-4o", "provider": "anthropic"},
                    "reviewer": {"model": "gpt-4o", "provider": "openai"},
                    "refinement": {"model": "claude-sonnet-4-20250514", "provider": "anthropic"},
                }
            },
        }
        with pytest.raises(InputValidationError, match="generator.*provider"):
            validate_raw(data)

    def test_model_routing_explicit_provider_allows_unknown_alias(self):
        data = {
            **VALID_INPUT,
            "config": {
                "model_routing": {
                    "generator": {"model": "claude-enterprise-prod", "provider": "anthropic"},
                    "reviewer": {"model": "gpt-4o", "provider": "openai"},
                    "refinement": {"model": "claude-enterprise-prod", "provider": "anthropic"},
                }
            },
        }
        result = validate_raw(data)
        routing = result["config"]["model_routing"]
        assert routing["generator"]["provider"] == "anthropic"
        assert routing["refinement"]["provider"] == "anthropic"

    def test_model_routing_known_prefix_mismatch_still_raises(self):
        data = {
            **VALID_INPUT,
            "config": {
                "model_routing": {
                    "generator": {"model": "gpt-4o", "provider": "anthropic"},
                    "reviewer": {"model": "gpt-4o", "provider": "openai"},
                    "refinement": {"model": "claude-sonnet-4-20250514", "provider": "anthropic"},
                }
            },
        }
        with pytest.raises(InputValidationError, match="generator.*provider"):
            validate_raw(data)

    def test_bool_temperature_rejected(self):
        data = {
            **VALID_INPUT,
            "config": {
                "generator_model": "claude-sonnet-4-20250514",
                "reviewer_model": "gpt-4o",
                "generator_temperature": True,
            },
        }
        with pytest.raises(InputValidationError, match="generator_temperature"):
            validate_raw(data)

    def test_bool_max_tokens_rejected(self):
        data = {
            **VALID_INPUT,
            "config": {
                "generator_model": "claude-sonnet-4-20250514",
                "reviewer_model": "gpt-4o",
                "max_tokens": True,
            },
        }
        with pytest.raises(InputValidationError, match="max_tokens"):
            validate_raw(data)

    def test_float_max_tokens_rejected(self):
        data = {
            **VALID_INPUT,
            "config": {
                "generator_model": "claude-sonnet-4-20250514",
                "reviewer_model": "gpt-4o",
                "max_tokens": 1.9,
            },
        }
        with pytest.raises(InputValidationError, match="max_tokens"):
            validate_raw(data)

    def test_float_string_max_tokens_rejected(self):
        data = {
            **VALID_INPUT,
            "config": {
                "generator_model": "claude-sonnet-4-20250514",
                "reviewer_model": "gpt-4o",
                "max_tokens": "1.9",
            },
        }
        with pytest.raises(InputValidationError, match="max_tokens"):
            validate_raw(data)

    def test_model_routing_missing_phase_raises_at_loader_boundary(self):
        data = {
            **VALID_INPUT,
            "config": {
                "model_routing": {
                    "generator": {"model": "claude-sonnet-4-20250514", "provider": "anthropic"},
                    "reviewer": {"model": "gpt-4o", "provider": "openai"},
                }
            },
        }
        with pytest.raises(InputValidationError, match="refinement"):
            validate_raw(data)


# ---------------------------------------------------------------------------
# load_input — file-based entry point
# ---------------------------------------------------------------------------


class TestLoadInput:
    def test_valid_file_returns_input_package(self, tmp_path):
        p = _write_yaml(tmp_path, VALID_INPUT)
        pkg = load_input(str(p))
        assert isinstance(pkg, InputPackage)
        assert pkg.source_path == str(p)
        assert pkg.raw["story"]["id"] == "PROJ-1234"
        assert pkg.normalized["story"]["id"] == "PROJ-1234"

    def test_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            load_input("/nonexistent/path/file.yaml")

    def test_invalid_content_raises_validation_error(self, tmp_path):
        p = _write_yaml(tmp_path, {"story": {"id": "X", "title": "Y"}})
        with pytest.raises(InputValidationError):
            load_input(str(p))

    def test_empty_file_raises(self, tmp_path):
        p = tmp_path / "empty.yaml"
        p.write_text("", encoding="utf-8")
        with pytest.raises(InputValidationError):
            load_input(str(p))

    def test_malformed_yaml_raises(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text(":\n  - [unclosed", encoding="utf-8")
        with pytest.raises(Exception):  # yaml.YAMLError or InputValidationError
            load_input(str(p))

    def test_yaml_list_at_top_level_raises(self, tmp_path):
        p = tmp_path / "list.yaml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(InputValidationError, match="must be a mapping"):
            load_input(str(p))

    def test_directory_path_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="directory"):
            load_input(str(tmp_path))


# ---------------------------------------------------------------------------
# Real-world edge cases
# ---------------------------------------------------------------------------


class TestRealWorldEdgeCases:
    """Scenarios that happen in real teams but are easy to miss in TDD."""

    def test_unicode_in_story_and_acs(self):
        data = {
            "story": {"id": "PROJ-日本語", "title": "Ñoño señal", "description": "Ünïcödé description 🚀"},
            "acceptance_criteria": [
                {"id": "AC-1", "description": "Ação com acentuação", "criticality": "high"},
            ],
        }
        result = validate_raw(data)
        assert result["story"]["id"] == "PROJ-日本語"
        assert "🚀" in result["story"]["description"]

    def test_ac_description_whitespace_only_raises(self):
        data = {
            **VALID_INPUT,
            "acceptance_criteria": [{"id": "AC-1", "description": "   "}],
        }
        with pytest.raises(InputValidationError, match="must not be empty|whitespace"):
            validate_raw(data)

    def test_story_id_is_integer_coerced(self):
        """YAML parses bare `id: 1234` as int — should be coerced to string."""
        data = {
            "story": {"id": 1234, "title": "Numeric ID", "description": "Some desc"},
            "acceptance_criteria": [{"id": "AC-1", "description": "Criterion"}],
        }
        result = validate_raw(data)
        assert result["story"]["id"] == "1234"
        assert isinstance(result["story"]["id"], str)

    def test_extra_top_level_keys_ignored(self):
        """Teams paste from templates with extra fields — should not reject."""
        data = {
            **VALID_INPUT,
            "metadata": {"author": "sandeep", "created": "2026-07-16"},
            "notes": "This is a draft",
        }
        result = validate_raw(data)
        assert result["story"]["id"] == "PROJ-1234"

    def test_ac_ordering_preserved(self):
        acs = [
            {"id": "AC-3", "description": "Third"},
            {"id": "AC-1", "description": "First"},
            {"id": "AC-2", "description": "Second"},
        ]
        data = {**VALID_INPUT, "acceptance_criteria": acs}
        result = validate_raw(data)
        assert result["acceptance_criteria"][0]["id"] == "AC-3"
        assert result["acceptance_criteria"][1]["id"] == "AC-1"
        assert result["acceptance_criteria"][2]["id"] == "AC-2"

    def test_large_description_accepted(self):
        desc = "A" * 2000
        data = {
            "story": {"id": "S-1", "title": "Big story", "description": desc},
            "acceptance_criteria": [{"id": "AC-1", "description": "X"}],
        }
        result = validate_raw(data)
        assert len(result["story"]["description"]) == 2000

    def test_normalized_output_excludes_extra_raw_fields(self):
        """Normalized output should be clean — no unexpected keys leak through."""
        data = {
            **VALID_INPUT,
            "junk_field": "should not appear",
        }
        result = validate_raw(data)
        assert "junk_field" not in result

    def test_config_same_generator_and_reviewer_warns(self):
        """Using same model for both defeats adversarial purpose."""
        data = {
            **VALID_INPUT,
            "config": {"generator_model": "claude", "reviewer_model": "claude"},
        }
        result = validate_raw(data)
        assert any("same model" in w.lower() for w in result.get("_warnings", []))

    def test_file_with_bom_loads(self, tmp_path):
        """Windows-created files often have UTF-8 BOM."""
        p = tmp_path / "bom.yaml"
        content = yaml.dump(VALID_INPUT, default_flow_style=False)
        p.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
        pkg = load_input(str(p))
        assert pkg.normalized["story"]["id"] == "PROJ-1234"

    def test_yaml_bomb_file_rejected(self, tmp_path):
        """Files larger than 1MB are rejected."""
        p = tmp_path / "big.yaml"
        p.write_text("x" * 1_100_000, encoding="utf-8")
        with pytest.raises(InputValidationError, match="exceeds maximum size"):
            load_input(str(p))

    def test_story_description_whitespace_only_raises(self):
        data = {**VALID_INPUT, "story": {"id": "S-1", "title": "X", "description": "   \n  "}}
        with pytest.raises(InputValidationError, match="must not be empty"):
            validate_raw(data)

    def test_story_title_is_list_raises(self):
        data = {**VALID_INPUT, "story": {"id": "S-1", "title": ["a", "b"], "description": "X"}}
        with pytest.raises(InputValidationError, match="must be a string"):
            validate_raw(data)

    def test_story_description_is_dict_raises(self):
        data = {**VALID_INPUT, "story": {"id": "S-1", "title": "X", "description": {"nested": "bad"}}}
        with pytest.raises(InputValidationError, match="must be a string"):
            validate_raw(data)

    def test_ac_id_empty_string_raises(self):
        data = {**VALID_INPUT, "acceptance_criteria": [{"id": "", "description": "Valid desc"}]}
        with pytest.raises(InputValidationError, match="must not be empty"):
            validate_raw(data)

    def test_ac_id_whitespace_only_raises(self):
        data = {**VALID_INPUT, "acceptance_criteria": [{"id": "   ", "description": "Valid desc"}]}
        with pytest.raises(InputValidationError, match="must not be empty"):
            validate_raw(data)

    def test_story_id_coerced_to_string(self):
        data = {
            "story": {"id": 1234, "title": "Numeric", "description": "Desc"},
            "acceptance_criteria": [{"id": "AC-1", "description": "X"}],
        }
        result = validate_raw(data)
        assert result["story"]["id"] == "1234"
        assert isinstance(result["story"]["id"], str)

    def test_normalized_story_is_independent_copy(self):
        """Normalized output should not share references with raw."""
        data = {**VALID_INPUT}
        result = validate_raw(data)
        result["story"]["id"] = "MODIFIED"
        assert data["story"]["id"] == "PROJ-1234"  # original unchanged

