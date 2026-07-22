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
- v0.2.0 released and tagged (2026-07-22)
- V2-1 through V2-4 + V2-6 + docs: COMPLETE
- Next milestone: **v0.3.0 — Real-World Hardening**
  - V2-12: Prompt injection tests (can start immediately, no API keys needed)
  - D-V2-1-1: Retry logic with retryable/permanent error classification
  - V2-9: Exit code 3 for environment errors
  - LOW-fix: Deduplicate same-model warning
  - V2-5: Real-provider truncation/budget integration tests (needs keys)
  - D-V2-1-2: JSON schema validation on LLM responses (needs keys)
  - D-V2-PROMPT-1: Cache effectiveness validation (needs keys)
- Trigger for v0.3.0: after real-model testing with valid API keys

## Blockers
- Real-provider validation items blocked on valid SKULD_ANTHROPIC_KEY and SKULD_OPENAI_KEY.
