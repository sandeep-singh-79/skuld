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
- Phase 1, T1: Project scaffold — COMPLETE.
- Next: T2 — Models (Story, AcceptanceCriterion, TestCase, RTMEntry, ConfidenceScore).

## Blockers
- None.
