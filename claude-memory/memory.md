# Memory — Skuld

> **Update Policy:** Update when strategy, decisions, next actions, or blockers change.
> **Scope:** Repo-specific. Carries the active state for Skuld (test case generator with adversarial review).

---

## Purpose
- AI-powered test case generator with adversarial cross-model review and RTM-based deterministic scoring.
- Position in pipeline: Strategy + ACs → Skuld → Test Cases + RTM + Confidence Score.

## Key Architectural Decisions
- Two-pass adversarial review: Generator LLM → Reviewer LLM (different model) → Generator refines → Score.
- Single refinement pass in MVP (not open-ended loop). V2 adds configurable iteration depth.
- Scoring: 70% deterministic (RTM) + 30% qualitative (adversarial review).
- Structured ACs as input (YAML). No free-form PRD extraction in V1.
- Cross-model: e.g., Claude generates, GPT reviews (or vice-versa).
- Suite-level confidence score: YES. Per-test confidence score: NO (replaced by Review Flag ✓/⚠).

## Coverage Types
- Non-negotiable (MVP): functional, negative, edge-case.
- Deferred (V2): NFR (performance, security), accessibility.

## Active Next Work
- V2-1: AnthropicLLMClient — COMPLETE (34 tests)
- V2-2: OpenAILLMClient — COMPLETE (31 tests)
- V2-3: Provider resolution — COMPLETE (wired in end_to_end_flow.py)
- V2-4: SharedBudget across phases — COMPLETE
- Prompt-builder caching split + loader-boundary provider config hardening — COMPLETE
- Documentation updates for real providers — COMPLETE
- Docs/contract review — COMPLETE
- Next: resolve docs/contract review findings (release version contract, default model contract, minor doc clarity gaps)
- After valid API keys are available: real-provider smoke review, cost/cache review, parser/output-contract review

## Blockers
- Real-provider validation reviews blocked on valid SKULD_ANTHROPIC_KEY and SKULD_OPENAI_KEY.
