"""End-to-end pipeline flow for Skuld (T13)."""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

from skuld.adversarial_reviewer import (
    ReviewParseError,
    compute_adversarial_score,
    map_review_flags,
    review_tests,
)
from skuld.comment_filter import filter_comments
from skuld.confidence_scorer import compute_confidence_from_detailed
from skuld.input_loader import InputValidationError, load_input, validate_raw
from skuld.llm_client import BudgetedLLMClient, FakeLLMClient, TokenBudgetExceeded
from skuld.models import (
    EXIT_INPUT_ERROR,
    EXIT_OK,
    EXIT_VALIDATION_ERROR,
    AcceptanceCriterion,
    FlowResult,
)
from skuld.output_validator import validate_output
from skuld.renderer import render_report
from skuld.rtm_builder import build_rtm, rtm_to_matrix
from skuld.rtm_scorer import score_rtm_detailed
from skuld.rtm_store import RTMStore
from skuld.test_generator import GenerationError, generate_tests, refine_tests


# ---------------------------------------------------------------------------
# Fake LLM response templates (realistic enough for parsing)
# ---------------------------------------------------------------------------

def _fake_test_cases_json(story_id: str, ac_ids: list[str]) -> str:
    """Produce a fake LLM response with valid test case JSON."""
    cases = []
    for i, ac_id in enumerate(ac_ids, 1):
        cases.append({
            "id": f"TC-{story_id}-{i:03d}",
            "story_id": story_id,
            "ac_ids": [ac_id],
            "test_type": "functional",
            "priority": "P1",
            "preconditions": "System is running",
            "steps": ["Step 1: Perform action", "Step 2: Verify result"],
            "expected_result": f"Expected outcome for {ac_id}",
            "test_data": None,
            "automatable": True,
        })
        # Add a negative test
        cases.append({
            "id": f"TC-{story_id}-{i:03d}-NEG",
            "story_id": story_id,
            "ac_ids": [ac_id],
            "test_type": "negative",
            "priority": "P2",
            "preconditions": "System is running",
            "steps": ["Step 1: Provide invalid input", "Step 2: Check error"],
            "expected_result": f"Error displayed for {ac_id}",
            "test_data": "invalid-data",
            "automatable": True,
        })
        # Add an edge-case test
        cases.append({
            "id": f"TC-{story_id}-{i:03d}-EDGE",
            "story_id": story_id,
            "ac_ids": [ac_id],
            "test_type": "edge-case",
            "priority": "P3",
            "preconditions": "System is in boundary state",
            "steps": ["Step 1: Trigger edge condition"],
            "expected_result": f"Graceful handling for {ac_id}",
            "test_data": "boundary-value",
            "automatable": True,
        })
    return json.dumps({"test_cases": cases}, indent=2)


def _fake_review_feedback_json() -> str:
    """Produce a fake LLM response with valid ReviewFeedback JSON."""
    return json.dumps({
        "flagged_tests": [],
        "missing_scenarios": [],
        "quality_scores": {
            "coverage": 0.9,
            "clarity": 0.85,
            "testability": 0.9,
        },
        "suggestions": ["Consider adding concurrency tests"],
    })


def _fake_refined_cases_json(story_id: str, ac_ids: list[str]) -> str:
    """Produce a fake refined test cases response (same structure, post-review)."""
    # Same as generation but with refined IDs
    cases = []
    for i, ac_id in enumerate(ac_ids, 1):
        cases.append({
            "id": f"TC-{story_id}-{i:03d}",
            "story_id": story_id,
            "ac_ids": [ac_id],
            "test_type": "functional",
            "priority": "P1",
            "preconditions": "System is running",
            "steps": ["Step 1: Perform action", "Step 2: Verify result"],
            "expected_result": f"Expected outcome for {ac_id}",
            "test_data": None,
            "automatable": True,
        })
        cases.append({
            "id": f"TC-{story_id}-{i:03d}-NEG",
            "story_id": story_id,
            "ac_ids": [ac_id],
            "test_type": "negative",
            "priority": "P2",
            "preconditions": "System is running",
            "steps": ["Step 1: Provide invalid input", "Step 2: Check error"],
            "expected_result": f"Error displayed for {ac_id}",
            "test_data": "invalid-data",
            "automatable": True,
        })
        cases.append({
            "id": f"TC-{story_id}-{i:03d}-EDGE",
            "story_id": story_id,
            "ac_ids": [ac_id],
            "test_type": "edge-case",
            "priority": "P3",
            "preconditions": "System is in boundary state",
            "steps": ["Step 1: Trigger edge condition"],
            "expected_result": f"Graceful handling for {ac_id}",
            "test_data": "boundary-value",
            "automatable": True,
        })
    return json.dumps({"test_cases": cases}, indent=2)


# ---------------------------------------------------------------------------
# LLM client resolution
# ---------------------------------------------------------------------------

def _resolve_llm_clients(config: dict, use_fake: bool) -> dict:
    """Returns {"generator": LLMClient, "reviewer": LLMClient, "refinement": LLMClient}.

    Raises ValueError if use_fake=False and no API key is configured.
    """
    if use_fake:
        # Placeholder; real callers use _prepare_fake_clients instead.
        inner = FakeLLMClient(responses=["placeholder", "placeholder", "placeholder"])
        budgeted = BudgetedLLMClient(inner, max_tokens=32000)
        return {"generator": budgeted, "reviewer": budgeted, "refinement": budgeted}

    # Check API keys
    anthropic_key = os.environ.get("SKULD_ANTHROPIC_KEY")
    openai_key = os.environ.get("SKULD_OPENAI_KEY")
    if not anthropic_key and not openai_key:
        raise ValueError(
            "API key not configured. Set SKULD_ANTHROPIC_KEY or SKULD_OPENAI_KEY, or use --dry-run."
        )

    # TODO: Wire real providers (AnthropicLLMClient, OpenAILLMClient) in T14.
    # For now, use Fake with budget enforcement.
    inner = FakeLLMClient(responses=["placeholder", "placeholder", "placeholder"])
    budgeted = BudgetedLLMClient(inner, max_tokens=32000)
    return {"generator": budgeted, "reviewer": budgeted, "refinement": budgeted}


def _prepare_fake_clients(normalized: dict) -> dict:
    """Build FakeLLMClients with story-aware responses, wrapped in BudgetedLLMClient."""
    story_id = normalized["story"]["id"]
    ac_ids = [ac["id"] for ac in normalized["acceptance_criteria"]]

    gen_response = _fake_test_cases_json(story_id, ac_ids)
    review_response = _fake_review_feedback_json()
    refine_response = _fake_refined_cases_json(story_id, ac_ids)

    inner = FakeLLMClient(responses=[gen_response, review_response, refine_response])
    budgeted = BudgetedLLMClient(inner, max_tokens=32000)
    return {"generator": budgeted, "reviewer": budgeted, "refinement": budgeted}


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def _run_from_package(
    normalized: dict,
    rtm_file: str | None,
    force: bool,
    output_format: str,
    use_fake_llm: bool,
) -> FlowResult:
    """Shared core pipeline logic."""
    # 1. Extract fields
    story = normalized["story"]
    acs = normalized["acceptance_criteria"]
    config = normalized["config"]
    comments = normalized.get("comments")

    logger.info("Pipeline started for story '%s' with %d ACs", story["id"], len(acs))

    # 2. Filter comments
    if config.get("filter_comments", True) and comments:
        comments = filter_comments(comments)
        # Update normalized so downstream (generate_tests) sees filtered
        normalized = {**normalized, "comments": comments}

    # 2b. Same-model warning
    warnings = list(normalized.get("_warnings", []))
    if config.get("generator_model") == config.get("reviewer_model"):
        warnings.append(
            f"generator_model and reviewer_model are the same ('{config['generator_model']}') "
            "— adversarial review effectiveness reduced"
        )

    # 3. Resolve LLM clients
    if use_fake_llm:
        clients = _prepare_fake_clients(normalized)
    else:
        try:
            clients = _resolve_llm_clients(config, use_fake_llm)
        except ValueError as exc:
            return FlowResult(exit_code=EXIT_INPUT_ERROR, message=str(exc), output_path=None)

    # 4. Generate (Pass 1)
    logger.info("Stage 1/3: Generating test cases...")
    try:
        test_cases = generate_tests(normalized, clients["generator"])
    except (GenerationError, TokenBudgetExceeded) as exc:
        return FlowResult(exit_code=EXIT_VALIDATION_ERROR, message=str(exc), output_path=None)

    # 5. Review
    logger.info("Stage 2/3: Adversarial review...")
    try:
        ac_objects = [
            AcceptanceCriterion(
                id=ac["id"],
                description=ac["description"],
                criticality=ac.get("criticality", "medium"),
            )
            for ac in acs
        ]
        feedback = review_tests(test_cases, ac_objects, clients["reviewer"])
    except (ReviewParseError, TokenBudgetExceeded) as exc:
        return FlowResult(exit_code=EXIT_VALIDATION_ERROR, message=str(exc), output_path=None)

    # 6. Refine (Pass 2)
    logger.info("Stage 3/3: Refining test cases...")
    try:
        refined = refine_tests(test_cases, feedback, normalized, clients["refinement"])
    except (GenerationError, TokenBudgetExceeded) as exc:
        return FlowResult(exit_code=EXIT_VALIDATION_ERROR, message=str(exc), output_path=None)

    # 7. Map review flags
    flagged_tests = map_review_flags(refined, feedback)

    # 8. RTM
    entries = build_rtm(flagged_tests, ac_objects)
    matrix = rtm_to_matrix(entries, ac_objects, flagged_tests)

    # 9. Score
    detailed = score_rtm_detailed(entries, ac_objects)
    adversarial_score = compute_adversarial_score(feedback)
    confidence = compute_confidence_from_detailed(detailed, adversarial_score)
    gaps = detailed["gaps"]

    logger.info("Scoring complete. Confidence: %.1f (%s)", confidence.overall, confidence.tier)

    # 10. Render
    rendered = render_report(
        flagged_tests, matrix, confidence, gaps, output_format,
        story=story, acceptance_criteria=acs,
    )

    logger.info("Report rendered (%s format)", output_format)

    # 11. Self-validate (markdown only)
    if output_format == "markdown":
        validation = validate_output(rendered)
        if not validation.is_valid:
            return FlowResult(
                exit_code=EXIT_VALIDATION_ERROR,
                message=f"Self-validation failed: {validation.errors}",
                output_path=None,
            )

    # 11b. JSON schema validation
    if output_format == "json":
        import json as json_mod

        try:
            parsed = json_mod.loads(rendered)
        except json_mod.JSONDecodeError as exc:
            return FlowResult(
                exit_code=EXIT_VALIDATION_ERROR,
                message=f"JSON render invalid: {exc}",
                output_path=None,
            )
        required_keys = {"test_cases", "confidence_score", "rtm_matrix"}
        missing = required_keys - set(parsed.keys())
        if missing:
            return FlowResult(
                exit_code=EXIT_VALIDATION_ERROR,
                message=f"JSON output missing keys: {missing}",
                output_path=None,
            )

    # 12. RTM persist
    if rtm_file:
        store = RTMStore.load(rtm_file)
        merge_result = store.merge(
            entries, story_id=story["id"], run_id=f"run-{story['id']}", force=force
        )
        try:
            store.save(rtm_file)
        except OSError as exc:
            warnings.append(f"RTM persist failed: {exc}. Output still valid.")
        if merge_result.conflicts:
            warnings.extend(merge_result.conflicts)

    return FlowResult(exit_code=EXIT_OK, message=rendered, output_path=None, warnings=warnings)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_pipeline(
    input_path: str,
    rtm_file: str | None = None,
    force: bool = False,
    output_format: str = "markdown",
    use_fake_llm: bool = False,
) -> FlowResult:
    """File-based entry point."""
    try:
        package = load_input(input_path)
    except FileNotFoundError as exc:
        return FlowResult(exit_code=EXIT_INPUT_ERROR, message=str(exc), output_path=None)
    except InputValidationError as exc:
        return FlowResult(exit_code=EXIT_INPUT_ERROR, message=str(exc), output_path=None)

    return _run_from_package(
        package.normalized,
        rtm_file=rtm_file,
        force=force,
        output_format=output_format,
        use_fake_llm=use_fake_llm,
    )


def run_pipeline_from_dict(
    data: dict,
    rtm_file: str | None = None,
    force: bool = False,
    output_format: str = "markdown",
    use_fake_llm: bool = False,
) -> FlowResult:
    """Dict-based entry point (for testing/programmatic use)."""
    try:
        normalized = validate_raw(data)
    except InputValidationError as exc:
        return FlowResult(exit_code=EXIT_INPUT_ERROR, message=str(exc), output_path=None)

    return _run_from_package(
        normalized,
        rtm_file=rtm_file,
        force=force,
        output_format=output_format,
        use_fake_llm=use_fake_llm,
    )
