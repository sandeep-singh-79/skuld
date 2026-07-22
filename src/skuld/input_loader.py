"""Input loader and validator for Skuld."""
from __future__ import annotations

import pathlib
import re
from typing import Any

import yaml

from skuld.models import InputPackage

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_INPUT_FILE_SIZE = 1_048_576  # 1MB
VALID_CRITICALITY_VALUES = {"high", "medium", "low"}
VALID_PROVIDER_VALUES = {"anthropic", "openai"}
VALID_OUTPUT_FORMATS = {"markdown", "json"}
VALID_ROUTING_PHASES = ("generator", "reviewer", "refinement")
DEFAULT_MAX_AC_COUNT = 30
AC_WARNING_THRESHOLD = 15
_INT_RE = re.compile(r"^[+-]?\d+$")

DEFAULT_CONFIG = {
    "generator_model": "claude-sonnet-4-20250514",
    "reviewer_model": "gpt-4o",
    "min_negative_per_ac": 1,
    "min_edge_case_per_ac": 1,
    "output_format": "markdown",
    "filter_comments": True,
}

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class InputValidationError(ValueError):
    """Raised when the input YAML fails structural or semantic validation."""


# ---------------------------------------------------------------------------
# Internal validators
# ---------------------------------------------------------------------------


def _require_keys(obj: dict, keys: list[str], context: str) -> None:
    """Validate that all required keys are present in a dict."""
    for key in keys:
        if key not in obj:
            raise InputValidationError(f"Missing required field {key!r} in {context}")


def _coerce_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise InputValidationError(f"{field_name} must be a number, got {value!r}")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise InputValidationError(f"{field_name} must be a number, got {value!r}")
    return result


def _coerce_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise InputValidationError(f"{field_name} must be an integer, got {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if _INT_RE.match(stripped):
            return int(stripped)
    raise InputValidationError(f"{field_name} must be an integer, got {value!r}")


def _known_provider_from_model(model_name: str) -> str | None:
    if model_name.startswith("claude-"):
        return "anthropic"
    if model_name.startswith(("gpt-", "o1-", "o3-", "o4-")):
        return "openai"
    return None


def _infer_provider_from_model(model_name: str) -> str:
    provider = _known_provider_from_model(model_name)
    if provider is not None:
        return provider
    raise InputValidationError(
        f"Cannot determine provider for model {model_name!r}. "
        "Use an explicit provider compatible with the model name."
    )


def _validate_story(story: dict) -> None:
    """Validate the story block."""
    _require_keys(story, ["id", "title", "description"], "story")
    for field in ("id", "title", "description"):
        if not story[field] or not str(story[field]).strip():
            raise InputValidationError(f"story.{field} must not be empty")
    if not isinstance(story["title"], str):
        raise InputValidationError(
            f"story.title must be a string, got {type(story['title']).__name__}"
        )
    if not isinstance(story["description"], str):
        raise InputValidationError(
            f"story.description must be a string, got {type(story['description']).__name__}"
        )
    # Coerce id to string for downstream consistency
    story["id"] = str(story["id"])


def _validate_ac(ac: dict, index: int) -> None:
    """Validate a single acceptance criterion."""
    ctx = f"acceptance_criteria[{index}]"
    _require_keys(ac, ["id", "description"], ctx)
    if not str(ac["id"]).strip():
        raise InputValidationError(f"id in {ctx} must not be empty")

    # Reject whitespace-only descriptions
    desc = ac.get("description", "")
    if isinstance(desc, str) and not desc.strip():
        raise InputValidationError(
            f"description in {ctx} must not be empty or whitespace-only"
        )

    criticality = ac.get("criticality")
    if criticality is not None and criticality not in VALID_CRITICALITY_VALUES:
        raise InputValidationError(
            f"criticality {criticality!r} in {ctx} must be one of {sorted(VALID_CRITICALITY_VALUES)}"
        )


def _validate_acceptance_criteria(acs: list[dict], warnings: list[str]) -> None:
    """Validate the acceptance_criteria list."""
    if not isinstance(acs, list):
        raise InputValidationError(
            f"acceptance_criteria must be a list, got {type(acs).__name__}"
        )

    if len(acs) == 0:
        raise InputValidationError("acceptance_criteria must contain at least one acceptance criterion")

    if len(acs) > DEFAULT_MAX_AC_COUNT:
        raise InputValidationError(
            f"AC count ({len(acs)}) exceeds maximum of {DEFAULT_MAX_AC_COUNT}"
        )

    if len(acs) > AC_WARNING_THRESHOLD:
        warnings.append(f"AC count ({len(acs)}) exceeds warning threshold of {AC_WARNING_THRESHOLD}")

    # Validate each AC and check for duplicates
    seen_ids: set[str] = set()
    for i, ac in enumerate(acs):
        _validate_ac(ac, i)
        ac_id = ac["id"]
        if ac_id in seen_ids:
            raise InputValidationError(f"Duplicate AC id {ac_id!r} in acceptance_criteria")
        seen_ids.add(ac_id)


def _validate_strategy_ref(strategy_ref: dict | None, warnings: list[str]) -> None:
    """Validate the optional strategy_ref block (HITL gate)."""
    if strategy_ref is None:
        return

    has_approved = strategy_ref.get("approved") is True
    has_reviewed_by = "reviewed_by" in strategy_ref and strategy_ref["reviewed_by"]

    if not has_approved and not has_reviewed_by:
        warnings.append(
            "strategy_ref provided but lacks 'approved: true' or 'reviewed_by' — "
            "strategy has not been human-reviewed"
        )


def _apply_config_defaults(raw: dict) -> dict:
    """Fill missing config fields with defaults."""
    config = raw.get("config", {}) or {}
    merged = {**DEFAULT_CONFIG, **config}
    return merged


def _validate_config(config: dict, warnings: list[str]) -> None:
    """Validate and normalize provider-related config."""
    temperature_fields = (
        "generator_temperature",
        "reviewer_temperature",
        "refinement_temperature",
    )
    for field_name in temperature_fields:
        if field_name in config and config[field_name] is not None:
            value = _coerce_float(config[field_name], field_name)
            if not 0.0 <= value <= 2.0:
                raise InputValidationError(f"{field_name} must be between 0.0 and 2.0")
            config[field_name] = value

    int_fields = ("max_tokens", "max_tokens_per_run")
    for field_name in int_fields:
        if field_name in config and config[field_name] is not None:
            value = _coerce_int(config[field_name], field_name)
            if value <= 0:
                raise InputValidationError(f"{field_name} must be greater than 0")
            config[field_name] = value

    output_format = config.get("output_format")
    if output_format is None:
        output_format = DEFAULT_CONFIG["output_format"]
        config["output_format"] = output_format
    if output_format not in VALID_OUTPUT_FORMATS:
        raise InputValidationError(
            f"output_format must be one of {sorted(VALID_OUTPUT_FORMATS)}, got {output_format!r}"
        )

    routing = config.get("model_routing")
    if routing is not None:
        if not isinstance(routing, dict):
            raise InputValidationError(
                f"model_routing must be a mapping, got {type(routing).__name__}"
            )

        for phase in VALID_ROUTING_PHASES:
            if phase not in routing:
                raise InputValidationError(
                    f"model_routing must contain phase {phase!r}"
                )

        for phase in VALID_ROUTING_PHASES:
            phase_config = routing[phase]
            if not isinstance(phase_config, dict):
                raise InputValidationError(
                    f"model_routing.{phase} must be a mapping, got {type(phase_config).__name__}"
                )

            model = phase_config.get("model")
            if not isinstance(model, str) or not model.strip():
                raise InputValidationError(
                    f"model_routing.{phase}.model must be a non-empty string"
                )
            phase_config["model"] = model.strip()

            provider = phase_config.get("provider")
            if provider is None:
                phase_config["provider"] = _infer_provider_from_model(phase_config["model"])
            else:
                if not isinstance(provider, str) or provider not in VALID_PROVIDER_VALUES:
                    raise InputValidationError(
                        f"model_routing.{phase}.provider must be one of {sorted(VALID_PROVIDER_VALUES)}"
                    )
                known_provider = _known_provider_from_model(phase_config["model"])
                if known_provider is not None and provider != known_provider:
                    raise InputValidationError(
                        f"model_routing.{phase}.provider {provider!r} does not match model "
                        f"{phase_config['model']!r}"
                    )

            if "temperature" in phase_config and phase_config["temperature"] is not None:
                value = _coerce_float(
                    phase_config["temperature"],
                    f"model_routing.{phase}.temperature",
                )
                if not 0.0 <= value <= 2.0:
                    raise InputValidationError(
                        f"model_routing.{phase}.temperature must be between 0.0 and 2.0"
                    )
                phase_config["temperature"] = value

            if "max_tokens" in phase_config and phase_config["max_tokens"] is not None:
                value = _coerce_int(
                    phase_config["max_tokens"],
                    f"model_routing.{phase}.max_tokens",
                )
                if value <= 0:
                    raise InputValidationError(
                        f"model_routing.{phase}.max_tokens must be greater than 0"
                    )
                phase_config["max_tokens"] = value

        gen_model = routing["generator"]["model"]
        rev_model = routing["reviewer"]["model"]
        if gen_model == rev_model:
            warnings.append(
                f"model_routing: generator and reviewer use the same model ('{gen_model}') "
                "— this defeats the adversarial review purpose"
            )

    if config.get("generator_model") == config.get("reviewer_model"):
        warnings.append(
            f"generator_model and reviewer_model are the same model "
            f"('{config['generator_model']}') — this defeats the adversarial review purpose"
        )


def _normalize_acs(acs: list[dict]) -> list[dict]:
    """Apply defaults to acceptance criteria (criticality)."""
    result = []
    for ac in acs:
        normalized = {**ac}
        if "criticality" not in normalized or normalized["criticality"] is None:
            normalized["criticality"] = "medium"
        result.append(normalized)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_raw(raw: Any) -> dict[str, Any]:
    """Validate a raw input dict and return normalised data.

    Args:
        raw: Top-level dict from parsed YAML.

    Returns:
        Normalised dict ready for the pipeline.

    Raises:
        InputValidationError: for structural or semantic errors.
    """
    if not isinstance(raw, dict):
        raise InputValidationError("Input YAML must be a mapping at the top level")

    warnings: list[str] = []

    # Required top-level keys
    _require_keys(raw, ["story", "acceptance_criteria"], "root")

    # Validate story
    story = raw["story"]
    if not isinstance(story, dict):
        raise InputValidationError(f"story must be a mapping, got {type(story).__name__}")
    _validate_story(story)

    # Validate acceptance criteria
    acs = raw["acceptance_criteria"]
    _validate_acceptance_criteria(acs, warnings)

    # Normalize ACs (apply defaults)
    normalized_acs = _normalize_acs(acs)

    # Validate strategy_ref (HITL gate)
    strategy_ref = raw.get("strategy_ref")
    _validate_strategy_ref(strategy_ref, warnings)

    # Apply config defaults
    config = _apply_config_defaults(raw)

    # Validate config combinations
    _validate_config(config, warnings)

    # Build normalised document
    normalized: dict[str, Any] = {
        "story": {**story},
        "acceptance_criteria": normalized_acs,
        "config": config,
    }

    if strategy_ref is not None:
        normalized["strategy_ref"] = strategy_ref

    # Pass through optional fields
    comments = raw.get("comments")
    if comments and isinstance(comments, list):
        normalized["comments"] = comments

    domain_context = raw.get("domain_context")
    if domain_context and isinstance(domain_context, dict):
        normalized["domain_context"] = domain_context

    if warnings:
        normalized["_warnings"] = warnings

    return normalized


def load_input(path: str) -> InputPackage:
    """Load, parse, and validate an input YAML file.

    Args:
        path: Absolute or relative path to the input YAML.

    Returns:
        InputPackage with raw and normalized data.

    Raises:
        InputValidationError: for structural or semantic errors.
        FileNotFoundError: if the file does not exist.
    """
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Input file not found: {path!r}")
    if p.is_dir():
        raise FileNotFoundError(f"Path is a directory, not a file: {path!r}")
    if p.stat().st_size > MAX_INPUT_FILE_SIZE:
        raise InputValidationError(
            f"Input file exceeds maximum size of 1MB ({p.stat().st_size} bytes)"
        )

    with p.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if raw is None:
        raise InputValidationError("Input YAML must be a mapping at the top level")

    normalized = validate_raw(raw)

    return InputPackage(source_path=path, raw=raw, normalized=normalized)
