# Skuld — MVP Plan

> **Brand Name:** Skuld
> **Tagline:** *"Every 'should' gets a test."*
> **PyPI Name:** `skuld`
> **Import Name:** `skuld`
> **CLI Command:** `skuld`
> **GitHub Repo:** `Skuld`
> **One-liner:** AI-powered test case generator with adversarial cross-model review, RTM-based deterministic scoring, and confidence assessment.
> **Mythology:** In Norse myth, Skuld is the Norn who weaves what *should become*. Acceptance criteria define what must be true — Skuld ensures every "should" has a test proving it.
> **Last Updated:** 2026-07-16

---

## Position in Pipeline

```
PRD/Story → [QEStrategyForge] → Strategy
Strategy + ACs → [Skuld] → Test Cases + RTM + Confidence Score
Test results → [SuiteCompass] → Optimised Suite
Release context → [ReleaseRadar] → Risk Score
                        ↑
               [Orchestrator (future)] wires all four flagships
```

---

## Architecture — Two-Pass Adversarial Review

```
Structured ACs (YAML)
       ↓
┌─────────────────────┐
│  Generator LLM      │  Pass 1: produce test cases
│  (e.g. Claude)      │  (functional, negative, edge-case)
└────────┬────────────┘
         ↓
┌─────────────────────┐
│  Reviewer LLM       │  Adversarial review: score coverage gaps,
│  (e.g. GPT)         │  flag weak tests, identify missing scenarios
└────────┬────────────┘
         ↓
┌─────────────────────┐
│  Generator LLM      │  Pass 2: refine test suite using review feedback
│  (e.g. Claude)      │
└────────┬────────────┘
         ↓
┌─────────────────────┐
│  Deterministic       │  RTM build + scoring
│  Scorer              │
└────────┬────────────┘
         ↓
Final output: test cases + RTM + confidence score + coverage report
```

V2 extension: configurable iteration depth, threshold-based termination loop.

---

## Scoring Model — Hybrid Deterministic + Qualitative

```
Final Score = (0.70 × RTM_score) + (0.30 × adversarial_score)
```

### Deterministic Component (RTM + AC Matching) — 70%

| Check | Measurement | Type |
|-------|-------------|------|
| AC coverage | `covered_ACs / total_ACs` | Binary per AC |
| Negative coverage | Every AC has ≥1 negative test | Binary per AC |
| Edge-case coverage | Every AC has ≥1 edge-case test | Binary per AC |
| Orphan tests | Tests not mapped to any AC | Count |
| Type distribution | functional / negative / edge ratios meet minimums | Threshold |

### Qualitative Component (Adversarial Review) — 30%

| Check | Measured by |
|-------|-------------|
| Assertion strength | Reviewer LLM |
| Scenario realism | Reviewer LLM |
| Edge-case quality | Reviewer LLM |

---

## Coverage Types

| Type | MVP Status |
|------|------------|
| Functional (happy path) | **Non-negotiable** |
| Negative (error paths, invalid inputs) | **Non-negotiable** |
| Edge-case (boundaries, nulls, concurrency) | **Non-negotiable** |
| NFR (performance, security) | Deferred to V2 |
| Accessibility | Deferred to V2 |

---

## Input Contract

### Primary Input: `story_input.yaml`

```yaml
story:
  id: "PROJ-1234"
  title: "User login with MFA"
  description: |
    As a registered user, I want to log in using multi-factor authentication
    so that my account is protected from unauthorised access.

acceptance_criteria:
  - id: "AC-1"
    description: "User can log in with valid email and password"
    criticality: high          # high | medium | low — drives Priority
  - id: "AC-2"
    description: "MFA code is sent to registered phone number after password validation"
    criticality: high
  - id: "AC-3"
    description: "Login fails after 3 incorrect MFA attempts with account lock"
    criticality: medium
  - id: "AC-4"
    description: "User sees meaningful error message for expired MFA code"
    criticality: low

# Optional: user-supplied constraints
config:
  generator_model: "claude"       # default: claude
  reviewer_model: "gpt"          # default: gpt (must differ from generator)
  min_negative_per_ac: 1         # default: 1
  min_edge_case_per_ac: 1        # default: 1
  output_format: "markdown"      # markdown | yaml | json (default: markdown)
```

### Optional Input: QEStrategyForge Strategy Output

```yaml
# If provided, type distribution minimums are derived from strategy
strategy_ref:
  path: "path/to/strategy_output.md"
  # OR inline excerpt:
  testing_types_required:
    - functional
    - negative
    - edge_case
    - security          # would be deferred to V2 but noted in coverage report
```

### Optional Input: Custom Test Case Template

```yaml
# If provided, overrides the default column set
template:
  columns:
    - "Test Case ID"
    - "Story/Req ID"
    - "Acceptance Criteria"
    # ... user defines their own
```

If not provided, the default template (below) is used.

---

## Output Contract

### 1. Test Case Table (Markdown / YAML / JSON)

**Default columns:**

| # | Column | Filled by | Description |
|---|--------|-----------|-------------|
| 1 | Test Case ID | Agent | Auto-generated (TC-001, TC-002, ...) |
| 2 | Story/Req ID | Agent | From input story.id |
| 3 | Acceptance Criteria | Agent | AC-id(s) this test covers |
| 4 | Test Type | Agent | functional / negative / edge-case |
| 5 | Priority | Agent | P1 / P2 / P3 (derived from AC criticality) |
| 6 | Preconditions | Agent | Setup state required |
| 7 | Test Steps | Agent | Numbered action steps |
| 8 | Expected Result | Agent | Observable outcome |
| 9 | Test Data | Agent | Specific values / datasets |
| 10 | Automatable | Agent | Y / N (inferred from test nature) |
| 11 | Review Flag | Adversarial reviewer | ✓ (OK) or ⚠ (flagged concern) |
| 12 | Automated | Team (later) | Default "N" — lifecycle tracking |
| 13 | Script Group | Team (later) | Clusters tests automated under one script |

### 2. Requirements Traceability Matrix (RTM)

```
          TC-001  TC-002  TC-003  TC-004  TC-005  TC-006
AC-1        F       N       E       -       -       -
AC-2        -       -       -       F       N       -
AC-3        -       -       -       -       -       F
AC-4        -       N       -       -       -       -

Legend: F=functional, N=negative, E=edge-case, -=not covered
```

### 3. Confidence Score Report

```yaml
confidence_score:
  overall: 82.3
  breakdown:
    rtm_score: 87.5          # deterministic — 70% weight
    adversarial_score: 70.0  # qualitative — 30% weight
  rtm_details:
    ac_coverage: 4/4         # 100%
    negative_coverage: 3/4   # AC-3 missing negative test
    edge_case_coverage: 2/4  # AC-2, AC-4 missing edge tests
    orphan_tests: 0
    type_distribution:
      functional: 40%        # minimum 30% — PASS
      negative: 35%          # minimum 25% — PASS
      edge_case: 25%         # minimum 20% — PASS
  gaps:
    - "AC-3: no negative test — what happens with 2 incorrect attempts (below threshold)?"
    - "AC-2: no edge-case test — MFA delivery to invalid phone format?"
    - "AC-4: no edge-case test — expired code reused after refresh?"
```

### 4. Assertions File (for Benchmarking)

```yaml
must_include_headings:
  - "## Test Cases"
  - "## Requirements Traceability Matrix"
  - "## Confidence Score"
  - "## Coverage Gaps"

must_include_labels:
  - "Overall Confidence:"
  - "AC Coverage:"
  - "Orphan Tests:"

must_include_substrings:
  - "functional"
  - "negative"
  - "edge-case"
```

---

## Module Map (Planned)

```
src/skuld/
├── __init__.py
├── cli.py                  # Click CLI: skuld generate, skuld benchmark
├── models.py               # Story, AcceptanceCriterion, TestCase, RTMEntry, ConfidenceScore
├── input_loader.py         # Parse + validate story_input.yaml
├── output_validator.py     # Validate output against assertions
├── ac_extractor.py         # Extract/normalise ACs from input
├── test_generator.py       # LLM-based test case generation (Pass 1 + Pass 2)
├── adversarial_reviewer.py # LLM-based adversarial review (cross-model)
├── rtm_builder.py          # Build RTM from test cases + ACs
├── rtm_scorer.py           # Deterministic scoring from RTM
├── confidence_scorer.py    # Combine RTM score + adversarial score
├── renderer.py             # Render output (markdown / yaml / json)
├── end_to_end_flow.py      # Orchestrate full pipeline
├── benchmark_runner.py     # Run benchmark scenarios
├── llm_client.py           # LLM provider abstraction
└── prompt_builder.py       # Prompt templates for generator + reviewer
```

---

## Phased Build Plan

### Phase 1 — Scaffold + Core Data Model
- [ ] T1: Project scaffold (pyproject.toml, src/, tests/, benchmarks/, AGENTS.md, plan.md, claude-memory/)
- [ ] T2: Models (Story, AcceptanceCriterion, TestCase, RTMEntry, ConfidenceScore)
- [ ] T3: Input loader (parse story_input.yaml, validate ACs, reject invalid)
- [ ] T4: Output validator (validate generated output against assertions YAML)

### Phase 2 — Deterministic Engine (No LLM)
- [ ] T5: RTM builder (given test cases + ACs, build traceability matrix)
- [ ] T6: RTM scorer (deterministic scoring: AC coverage, type distribution, orphans)
- [ ] T7: Confidence scorer (combine RTM score + placeholder adversarial score)
- [ ] T8: Renderer (output markdown / yaml / json from test cases + RTM + score)

### Phase 3 — LLM Generation + Adversarial Review
- [ ] T9: LLM client abstraction (pluggable: Claude, GPT, Ollama)
- [ ] T10: Prompt builder (generator prompt + reviewer prompt templates)
- [ ] T11: Test generator (Pass 1 — generate from ACs; Pass 2 — refine from review)
- [ ] T12: Adversarial reviewer (cross-model review, produce review feedback + score)

### Phase 4 — Integration
- [ ] T13: End-to-end flow (wire: input → generate → review → refine → RTM → score → render)
- [ ] T14: CLI (tcforge generate <input.yaml>, tcforge benchmark <assertions.yaml>)
- [ ] T15: Benchmarks (≥3 scenarios with input + assertions files)
- [ ] T16: Coverage hardening (all modules ≥90%, all benchmarks green)

---

## Dependency Graph

```
T1 (scaffold) ─┬─► T2 (models) ─► T3 (input loader) ─► T5 (RTM builder)
               │                                              ↓
               │                  T4 (output validator) ──► T6 (RTM scorer) ─► T7 (confidence)
               │                                                                    ↓
               │                                                              T8 (renderer)
               │
               └─► T9 (LLM client) ─► T10 (prompt builder) ─► T11 (generator)
                                                                    ↓
                                                              T12 (reviewer)
                                                                    ↓
                                              T13 (E2E flow: deterministic + LLM layers)
                                                                    ↓
                                                              T14 (CLI) ─► T15 (benchmarks)
                                                                                ↓
                                                                          T16 (hardening)
```

Phase 2 (T5–T8) and Phase 3 (T9–T12) can run in parallel.
Phase 4 (T13–T16) requires both Phase 2 and Phase 3.

---

## Test Count Targets

| File | Min |
|---|---|
| test_models.py | 10 |
| test_input_loader.py | 15 |
| test_output_validator.py | 12 |
| test_rtm_builder.py | 15 |
| test_rtm_scorer.py | 20 |
| test_confidence_scorer.py | 8 |
| test_renderer.py | 12 |
| test_generator.py | 10 |
| test_adversarial_reviewer.py | 10 |
| test_end_to_end_flow.py | 5 |
| test_cli.py | 8 |
| test_pipeline_integration.py | 10 |
| test_contracts.py | 3 |
| **Total** | **≥138** |

---

## Naming Rationale

| Attribute | Value | Rationale |
|-----------|-------|-----------|
| Brand | **Skuld** | Norse Norn of "what should become" — ACs define what must be true |
| PyPI | `skuld` | Short, memorable, unique |
| CLI | `skuld` | One word, no ambiguity, consistent with short mnemonics (`iro`, `relrisk`) |
| GitHub | `Skuld` | Brand name for repository |

---

## Current Status

| Field | Value |
|---|---|
| Phase | Pre-build (planning) |
| Next Action | Create project scaffold (T1) |
| Blockers | None |
