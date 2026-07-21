# Learning Guide

A tutorial on AI-powered test case generation — how to think about coverage, what signals matter, and how to interpret Skuld's output.

This guide teaches the **domain**, not just the tool. After reading it, you should be able to make principled test coverage decisions even without Skuld.

---

## How Skuld Thinks

Every run follows the same five-stage pipeline:

```
Story YAML
     │
     ▼
1. Input Loading ── validates structure, normalises fields, rejects
     │               malformed input before any LLM work begins
     ▼
2. Generation ── Generator LLM (e.g. Claude) produces test cases for
     │             every AC: ≥1 functional, ≥1 negative, ≥1 edge-case
     ▼
3. Adversarial Review ── Reviewer LLM (e.g. GPT, different model)
     │                    critiques coverage gaps, flags weak tests,
     │                    scores assertion strength and scenario realism
     ▼
4. Refinement ── Generator LLM revises the suite based on review
     │             feedback: fixes flagged tests, adds missing scenarios
     ▼
5. Scoring + Rendering ── RTM is built, deterministic score computed,
                           confidence tier assigned, gaps listed, report rendered
```

**What this means in practice:**
- Two different LLM models are used deliberately. The generator produces; the reviewer challenges. Same-model review is ineffective — the model is unlikely to find its own blind spots.
- The RTM score is fully deterministic and formula-based. No LLM guesswork. The same test cases always produce the same score.
- Gaps are precise: `"AC-3: no negative test"` tells you exactly what coverage is missing.
- The confidence tier (`high` / `medium` / `low`) is a ship/no-ship signal, not a vanity metric.

---

## 1. Why Adversarial Review Matters

### The Rubber-Stamp Problem

When the same model generates and reviews its own output, it tends to score its own work highly. The same assumptions, the same blind spots, the same stylistic patterns. This is rubber-stamping — reviews that add no real value.

Skuld prevents this by using a *different* model family for the reviewer. Claude generates; GPT reviews (or vice-versa). The divergence in training data, reasoning patterns, and tendencies is the mechanism that creates genuine adversarial tension.

### What the Reviewer Actually Checks

- **Coverage gaps**: Does every AC have a negative test? An edge-case test?
- **Assertion strength**: Is the expected result specific enough to fail on a regression?
- **Scenario realism**: Would this test actually catch a real bug?
- **Traceability**: Does every test map to at least one AC?
- **Missing scenarios**: What inputs, states, or paths are not represented?

The reviewer's score contributes 30% of the final confidence score. A technically complete RTM can still produce a `medium` confidence if the reviewer flags multiple weak assertions or missing scenarios.

---

## 2. Understanding RTM Coverage

The Requirements Traceability Matrix is the backbone of Skuld's deterministic scoring. It answers one question per AC: **what types of tests exist for this requirement?**

### Three Coverage Types

| Type | What it catches |
|------|----------------|
| **Functional** | The happy path — does the feature work as specified? |
| **Negative** | Error paths — does the system fail gracefully on invalid input? |
| **Edge-case** | Boundary conditions — what happens at extremes, nulls, concurrency? |

All three are non-negotiable in MVP. A suite with 100% functional coverage but zero negative tests is dangerous — it only tests the path where everything goes right.

### Orphan Tests

An orphan test is one whose `ac_ids` don't match any declared AC. Orphan tests dilute the suite — they add execution time without contributing to AC coverage. Each orphan reduces the RTM score by a small penalty. A high orphan count is a signal that tests have drifted from requirements.

### Reading the Coverage Labels

```
AC Coverage: 100%        ← Every AC has at least 1 functional test
Negative Coverage: 75%   ← 3 of 4 ACs have a negative test (AC-3 is missing one)
Edge-Case Coverage: 50%  ← 2 of 4 ACs have an edge-case test
Orphan Tests: 2          ← 2 tests map to ACs not in the declared list
```

A **Coverage Gaps** section then lists exactly which ACs are missing which types:

```
- AC-3: no negative test
- AC-2: no edge-case test
- AC-4: no edge-case test
```

This is the actionable output. Each gap line tells a QE lead exactly what to write next.

---

## 3. Interpreting the Confidence Score

The confidence score is a composite of RTM accuracy (70%) and adversarial review quality (30%).

### What Each Tier Means

| Tier | Score | What it means in practice |
|------|-------|--------------------------|
| `high` | ≥ 80.0 | Strong coverage of all types, reviewer found no major gaps, assertions are specific. Safe to proceed to automation. |
| `medium` | 50–79.9 | Some coverage gaps remain or reviewer flagged weak assertions. Acceptable for initial sprint delivery if gaps are tracked and addressed. |
| `low` | < 50.0 | Significant coverage missing, or the test suite is too weak to catch regressions reliably. Address gaps before delivery. |

### Score Components

```
Overall = (0.70 × RTM Score) + (0.30 × Adversarial Score)
```

- The **RTM score** is entirely deterministic — you can calculate it from the test case list alone.
- The **adversarial score** is qualitative — it depends on what the reviewer LLM flagged.
- A perfect RTM (100%) with a mediocre review (60%) produces: `(0.70 × 100) + (0.30 × 60) = 88` — still `high`.
- A near-perfect review but incomplete RTM (70%) produces: `(0.70 × 70) + (0.30 × 95) = 77.5` — `medium`.

**Key insight:** You can't compensate for missing functional coverage with a good review score. The RTM weight is higher because completeness is a prerequisite for quality.

---

## 4. Sprint Workflow Integration

### One Run Per Story

Skuld is designed for story-level runs. Run it once per story or AC set, then accumulate results into the persistent RTM.

```bash
# Sprint 1: Story AUTH-101
skuld generate auth-101.yaml --dry-run --rtm-file project-rtm.yaml

# Sprint 2: Story SHOP-200
skuld generate shop-200.yaml --dry-run --rtm-file project-rtm.yaml

# Sprint 3: View cumulative gaps
skuld rtm gaps --rtm-file project-rtm.yaml
```

### Tracking Gaps Over Time

The RTM accumulates entries across runs. The `skuld rtm gaps` command shows which ACs still lack negative or edge-case coverage — not just for the latest story, but across the whole project.

```bash
skuld rtm gaps --rtm-file project-rtm.yaml
```

The `skuld rtm history --rtm-file project-rtm.yaml --ac AC-3` command shows when coverage for a specific AC was added or changed.

### When to Re-Run

- A story's ACs change significantly → re-run `generate` with `--force`
- Manual tests were written → use `rtm update` to merge without LLM cost
- Coverage report is needed mid-sprint → use `rtm report` or `rtm gaps` directly

---

## 5. Common Pitfalls

### Same Model for Generator and Reviewer

Skuld warns you, but it won't stop you. If `generator_model` and `reviewer_model` are the same, the adversarial review is weakened — the model is unlikely to catch its own blind spots. Use different model families (e.g. Claude + GPT).

### Too Many ACs

Skuld rejects inputs with more than 30 ACs. This is a design constraint, not a limitation — if a story has 30+ ACs, it should be split. Generating tests for 30+ ACs in one pass produces unfocused output and exceeds prompt budget.

### Missing Story Context

Vague descriptions produce vague test cases. The `description` field and `comments` array are fed directly to the generator. Specific business context ("users are field adjusters on tablets with intermittent connectivity") produces better tests than generic descriptions ("users interact with the system").

### Treating `--dry-run` Output as Final

`--dry-run` uses a fake LLM that produces deterministic, structurally valid output — useful for integration testing and CI, but not for production test case quality. Real model runs are required for meaningful test content. The `--dry-run` flag is for tool validation, not test case delivery.
