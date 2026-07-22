# Changelog

All notable changes to this project will be documented in this file.

This project follows Semantic Versioning.

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
