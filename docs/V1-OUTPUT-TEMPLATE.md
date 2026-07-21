# V1 Output Template

Annotated reference for Skuld report output. The output is a structured markdown (or JSON) document with five required sections.

---

## Output Principles

1. **Structured** — fixed section order with line-anchored headings
2. **Deterministic** — same input always produces structurally identical output
3. **Machine-checkable** — all headings and labels validated by `output_validator.py`
4. **Section-aware** — each label appears exactly once in its declared section

---

## Required Sections (5)

| # | Heading | Purpose |
|---|---------|---------|
| 1 | `## Story Context` | Story metadata and accepted ACs |
| 2 | `## Test Cases` | Full test case table with all columns |
| 3 | `## Requirements Traceability Matrix` | AC × test case coverage grid |
| 4 | `## Confidence Score` | Score breakdown and tier |
| 5 | `## Coverage Gaps` | Missing test types per AC |

---

## Required Labels

| Label | Section | Value Type | Description |
|-------|---------|------------|-------------|
| `AC Coverage:` | Confidence Score | percentage | Proportion of ACs with ≥1 functional test |
| `Negative Coverage:` | Confidence Score | percentage | Proportion of ACs with ≥1 negative test |
| `Edge-Case Coverage:` | Confidence Score | percentage | Proportion of ACs with ≥1 edge-case test |
| `Orphan Tests:` | Confidence Score | integer | Tests not mapped to any declared AC |
| `Overall Confidence:` | Confidence Score | float (tier) | e.g. `99.30 (high)` |

---

## Confidence Score Model

```
Overall = (0.70 × RTM Score) + (0.30 × Adversarial Review Score)
```

### RTM Score Components

| Component | Weight | Description |
|-----------|--------|-------------|
| AC coverage | 0.30 | Every AC has ≥1 test |
| Negative coverage | 0.25 | Every AC has ≥1 negative test |
| Edge-case coverage | 0.20 | Every AC has ≥1 edge-case test |
| Type distribution | 0.15 | Functional/negative/edge-case ratio |
| Orphan penalty | 0.10 | Proportional: `orphans / total_entries` × 0.10 |

### Tier Thresholds

| Tier | Score Range |
|------|-------------|
| `high` | ≥ 80.0 |
| `medium` | ≥ 50.0 |
| `low` | < 50.0 |

---

## Annotated Sample Output (Markdown)

Generated from `skuld generate benchmarks/login-mfa.input.yaml --dry-run`:

```markdown
## Story Context

**Story:** AUTH-101 — User login with MFA

As a registered user, I want to log in using multi-factor authentication
so that my account is protected from unauthorised access.

**Acceptance Criteria:**
- [high] AC-1: User can log in with valid email and password
- [high] AC-2: MFA code sent to registered phone after password validation
- [medium] AC-3: Login fails after 3 incorrect MFA attempts with account lock
- [low] AC-4: Meaningful error message for expired MFA code

## Test Cases

| Test Case ID | Story/Req ID | AC IDs | Test Type | Priority | ... | Review Flag |
|---|---|---|---|---|---|---|
| TC-AUTH-101-001 | AUTH-101 | AC-1 | functional | P1 | ... | ✓ |
| TC-AUTH-101-001-NEG | AUTH-101 | AC-1 | negative | P2 | ... | ✓ |
| TC-AUTH-101-001-EDGE | AUTH-101 | AC-1 | edge-case | P3 | ... | ✓ |
...

## Requirements Traceability Matrix

| AC ID | TC-001 | TC-001-NEG | TC-001-EDGE | ... |
|---|---|---|---|---|
| AC-1 | functional | negative | edge-case | ... |
| AC-2 | ... | ... | ... | ... |

AC Coverage: 100%
Negative Coverage: 100%
Edge-Case Coverage: 100%
Orphan Tests: 0

## Confidence Score

Overall Confidence: 99.30 (high)

- RTM Score: 100.00
- Adversarial Score: 97.67
- ac_coverage: 1.0
- negative_coverage: 1.0
- edge_coverage: 1.0
- type_distribution: 1.0
- orphan_penalty: 0.0
- rtm_tier: high

## Coverage Gaps

No coverage gaps identified.
```

---

## JSON Output Format

Produced by `--format json`:

```json
{
  "test_cases": [
    {
      "id": "TC-AUTH-101-001",
      "story_id": "AUTH-101",
      "ac_ids": ["AC-1"],
      "test_type": "functional",
      "priority": "P1",
      "preconditions": "System is running",
      "steps": ["Step 1: Perform action", "Step 2: Verify result"],
      "expected_result": "Expected outcome for AC-1",
      "test_data": null,
      "automatable": true,
      "review_flag": "ok"
    }
  ],
  "confidence_score": {
    "overall": 99.3,
    "tier": "high",
    "rtm_score": 100.0,
    "adversarial_score": 97.67,
    "rtm_details": {
      "ac_coverage": 1.0,
      "negative_coverage": 1.0,
      "edge_coverage": 1.0,
      "type_distribution": 1.0,
      "orphan_penalty": 0.0,
      "composite": 100.0,
      "tier": "high",
      "gaps": []
    }
  },
  "rtm_matrix": {
    "matrix": {
      "AC-1": {
        "TC-AUTH-101-001": "functional",
        "TC-AUTH-101-001-NEG": "negative",
        "TC-AUTH-101-001-EDGE": "edge-case"
      }
    },
    "orphan_test_ids": []
  }
}
```
