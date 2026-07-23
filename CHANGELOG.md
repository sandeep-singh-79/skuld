# Changelog

All notable changes to this project will be documented in this file.

This project follows Semantic Versioning.

## [0.3.0] - 2026-07-23

Real-world hardening: retry resilience, prompt security, and exit-code formalization.

### Added
- `RetryingLLMClient` with exponential backoff, jitter, and injectable sleep for deterministic testing.
- `RetryPolicy` dataclass for configurable retry behaviour (max_retries, base_delay, max_delay, jitter).
- `ProviderAPIError.retryable` attribute for error classification (retryable vs permanent).
- `EXIT_PROVIDER_ERROR = 3` exit code for provider/environment failures (missing API key, missing SDK, provider errors).
- Server error handling: `InternalServerError` and Anthropic `OverloadedError` classified as retryable.
- 23 adversarial prompt injection tests against XML-fence guardrails (closing tag variations, case evasion, Unicode confusables, system override attempts, JSON breakout, cross-prompt coverage).
- Provider-specific missing-key error messages naming the exact required environment variable(s).
- Simple-mode model validation at input boundary (rejects non-string and unknown-provider models before env checks).

### Changed
- Provider failures now return controlled `FlowResult` with exit code 3 instead of uncaught tracebacks.
- Missing API key errors return exit code 3 (was 2) — environment errors distinguished from input errors.
- Config errors (unknown model name) consistently return exit code 2 regardless of environment state.
- Same-model warning deduplicated: `model_routing` check takes priority; simple-mode only fires via `elif`.
- Same-model warning logic consolidated in `input_loader._validate_config()` (removed from `end_to_end_flow`).
- Exit-code documentation updated in USAGE-GUIDE and PHASE-4-SPEC with per-command semantics.
- `SharedBudget` contract documented as successful-response-only budgeting.

### Fixed
- Provider API failures (auth, rate-limit, timeout, 5xx) no longer crash the CLI with tracebacks.
- Non-string simple-mode model values (e.g. `generator_model: 123`) now produce clear input validation errors.
- `_infer_provider()` and `_known_provider_from_model()` hardened against non-string inputs.

### Quality Gates
- 689 tests passing.
- Coverage gate enforced at 90 percent minimum.
- Multi-model adversarial review (GPT-5.4) applied to every work item.

## [0.2.0] - 2026-07-22

Real LLM provider integration milestone.

### Added
- Anthropic provider (`AnthropicLLMClient`) with prompt caching support.
- OpenAI provider (`OpenAILLMClient`) with Chat Completions API.
- `BaseLLMProvider` template method base class for easy provider extension.
- Provider resolution from config: simple mode (`generator_model`/`reviewer_model`) and advanced mode (`model_routing`).
- `SharedBudget` for per-run token budget enforcement across all pipeline phases.
- Anthropic prompt caching (`cache_control: ephemeral`) on system prompts for within-run cost savings.
- Input-loader boundary validation for all provider config fields (temperatures, token limits, model routing).
- Prompt-builder cache-safety guardrail (`_compose_system_prompt`) with regression tests.
- Optional dependency groups: `pip install skuld[anthropic]`, `pip install skuld[openai]`, `pip install skuld[providers]`.
- End-to-end walkthroughs for single-provider and cross-provider setups in USAGE-GUIDE.
- Model pairing examples table with budget, same-family, and reasoning-model strategies.
- Supported models reference table documenting all recognised prefixes and example models.

### Changed
- Stable instructions and output schemas moved into cache-eligible system prompts (from user prompts).
- Provider config is now validated and coerced at load time, not at provider construction time.
- Same-model adversarial warning now emitted for both simple and `model_routing` configurations.

### Fixed
- Quick-start docs now correctly state that the default mixed-provider config requires both API keys.
- Inline command examples in USAGE-GUIDE show both keys for cross-provider workflows.

### Quality Gates
- 624 tests passing.
- Coverage gate enforced at 90 percent minimum.
- Overall coverage approximately 96 percent.

### Environment Variables
- `SKULD_ANTHROPIC_KEY` — Anthropic API key (for Claude models)
- `SKULD_OPENAI_KEY` — OpenAI API key (for GPT/o-series models)

## [0.1.0] - 2026-07-21

Initial milestone release for the Skuld pipeline foundation.

### Added
- CLI commands for generation, scoring, RTM workflows, and benchmark validation.
- Deterministic benchmark scenarios and assertion contracts.
- Coverage hardening and degraded-scenario integration tests.
- Usage and learning documentation, including input/output templates.

### Quality Gates
- 516 tests passing.
- Coverage gate enforced at 90 percent minimum.
- Overall coverage approximately 96 percent at release time.

### Known Scope (Important)
- LLM behavior is currently simulated via FakeLLM in dry-run style workflows.
- Real provider integrations are intentionally deferred to the next milestone.

### Versioning Intent
- 1.0.0 will be reserved for a stable production-ready contract and provider path.
