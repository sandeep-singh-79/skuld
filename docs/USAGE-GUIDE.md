# Usage Guide

End-to-end usage instructions for Skuld — from installation to RTM management.

---

## Prerequisites

- Python ≥ 3.13
- pip (any recent version)

---

## Installation

```bash
git clone git@github.com:sandeep-singh-79/Skuld.git
cd Skuld
pip install -e ".[dev]"
```

Verify:

```bash
skuld --help
```

---

## Workflow 1: Generate Test Cases

Given a story YAML, Skuld runs a two-pass adversarial LLM pipeline and produces a test case report with RTM scoring.

### Step 1 — Write your story YAML

Create `story.yaml` with the required fields. See [V1-INPUT-TEMPLATE.md](V1-INPUT-TEMPLATE.md) for the full schema.

Minimum viable input:

```yaml
story:
  id: "PROJ-101"
  title: "User login with MFA"
  description: "As a registered user, I want to log in using MFA."

acceptance_criteria:
  - id: "AC-1"
    description: "User can log in with valid email and password"
    criticality: high
  - id: "AC-2"
    description: "Login fails after 3 incorrect MFA attempts"
    criticality: medium

config:
  generator_model: "claude-sonnet-4"
  reviewer_model: "gpt-5.5"
```

### Step 2 — Run generate

```bash
# Print to stdout (dry-run — no API keys needed)
skuld generate story.yaml --dry-run

# Write to file
skuld generate story.yaml --dry-run --output report.md

# JSON output format
skuld generate story.yaml --dry-run --format json

# Merge into persistent RTM
skuld generate story.yaml --dry-run --rtm-file rtm.yaml
```

### Step 3 — Read the report

See [V1-OUTPUT-TEMPLATE.md](V1-OUTPUT-TEMPLATE.md) for a full annotated example.

The report contains five sections:
1. **Story Context** — story metadata and ACs
2. **Test Cases** — full test case table
3. **Requirements Traceability Matrix** — AC × test case coverage grid
4. **Confidence Score** — overall score, tier, and breakdown
5. **Coverage Gaps** — ACs missing negative or edge-case tests

---

## Workflow 2: Score Without LLM

Score an existing set of test cases deterministically — no LLM call, no API keys.

### Input format (JSON)

```json
{
  "test_cases": [
    {
      "id": "TC-001",
      "story_id": "PROJ-101",
      "ac_ids": ["AC-1"],
      "test_type": "functional",
      "priority": "P1",
      "preconditions": "User is registered",
      "steps": ["Navigate to login", "Enter credentials", "Submit"],
      "expected_result": "User is authenticated"
    }
  ],
  "acceptance_criteria": [
    {"id": "AC-1", "description": "Valid login", "criticality": "high"}
  ]
}
```

### Run score

```bash
# JSON output (default — for downstream processing)
skuld score test_cases.json

# Markdown output (for human readability)
skuld score test_cases.json --format markdown
```

---

## Workflow 3: RTM Management

The RTM (`rtm.yaml`) is a persistent artifact that accumulates coverage across multiple stories and runs.

### View coverage summary

```bash
skuld rtm report --rtm-file rtm.yaml
```

### List coverage gaps

```bash
skuld rtm gaps --rtm-file rtm.yaml
```

### Merge test cases into RTM (without regeneration)

```bash
skuld rtm update test_cases.json --rtm-file rtm.yaml
```

All entries in `test_cases.json` must belong to the same `story_id`.

### View history for a specific AC

```bash
skuld rtm history --rtm-file rtm.yaml --ac AC-1
```

---

## Workflow 4: Benchmark

Run a full pipeline against a pre-defined scenario and validate the output against an assertions file.

```bash
skuld benchmark benchmarks/login-mfa.input.yaml benchmarks/login-mfa.assertions.yaml --dry-run
```

### Assertion file formats

**Simple format:**
```yaml
assertions:
  - type: contains
    value: "## Test Cases"
  - type: min_length
    value: "500"
```

**Spec format:**
```yaml
must_include_headings:
  - "## Test Cases"
  - "## Confidence Score"
must_include_substrings:
  - "functional"
  - "AC-1"
```

---

## CLI Reference

### `skuld generate`

```
skuld generate INPUT_FILE [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--output, -o` | path | stdout | Write output to file |
| `--format` | markdown\|json | markdown | Output format |
| `--rtm-file` | path | — | Merge results into persistent RTM |
| `--force` | flag | false | Force full RTM regeneration for this story |
| `--dry-run` | flag | false | Use FakeLLMClient (no API keys needed) |

### `skuld score`

```
skuld score TEST_CASES_FILE [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--format` | markdown\|json | json | Output format |

### `skuld rtm report`

```
skuld rtm report --rtm-file RTM_FILE
```

### `skuld rtm gaps`

```
skuld rtm gaps --rtm-file RTM_FILE
```

### `skuld rtm update`

```
skuld rtm update TEST_CASES_FILE --rtm-file RTM_FILE [--force]
```

Input JSON must have a `test_cases` array. All entries must share the same `story_id`.

### `skuld rtm history`

```
skuld rtm history --rtm-file RTM_FILE --ac AC_ID
```

### `skuld benchmark`

```
skuld benchmark INPUT_FILE ASSERTIONS_FILE [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--dry-run / --no-dry-run` | flag | dry-run | Use FakeLLMClient |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Benchmark assertions failed against output |
| 2 | Malformed input, validation error, or pipeline error |
