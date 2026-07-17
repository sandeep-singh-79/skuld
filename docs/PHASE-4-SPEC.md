# Phase 4 Specification — Integration

> **Purpose:** Implementable spec driving T13–T16. Subagents reference this directly.
> **Status:** APPROVED
> **Last Updated:** 2026-07-17

---

## Decisions (Locked)

| Question | Answer |
|----------|--------|
| Real LLM providers in MVP? | YES — `ClaudeLLMClient` + `OpenAILLMClient` alongside `FakeLLMClient` |
| Benchmark LLM responses? | `FakeLLMClient` with pre-recorded responses. Config flag `use_fake_llm: true` for benchmarks/CI |
| `skuld score` input format? | Reuse `render_json` output schema (has `test_cases` + structured data) |

---

## T13: End-to-End Flow

### File: `src/skuld/end_to_end_flow.py`

### Pipeline Stages

```
1. load_input(path) → InputPackage
2. Extract: story, acs, config, comments, domain_context, strategy_ref
3. Comment filtering: if config.filter_comments AND comments → filter_comments(comments)
4. Model routing: resolve LLM clients from config (generator, reviewer, refinement)
5. Pass 1 — Generate: build_generator_prompt → llm.generate → parse → list[TestCase]
6. Pass 2a — Review: build_reviewer_prompt → llm.generate → parse → ReviewFeedback
7. Pass 2b — Refine: build_refinement_prompt → llm.generate → parse → list[TestCase]
8. Map flags: map_review_flags(refined_tests, feedback)
9. RTM: build_rtm(test_cases, acs) → entries
10. Matrix: rtm_to_matrix(entries, acs, test_cases)
11. Score: score_rtm_detailed(entries, acs) → detailed
12. Adversarial score: compute_adversarial_score(feedback)
13. Confidence: compute_confidence_from_detailed(detailed, adversarial_score)
14. Gaps: find_gaps(entries, acs)
15. Render: render_report(test_cases, matrix, confidence, gaps, format)
16. Self-validate: validate_output(rendered) — if format is markdown
17. RTM persist: if rtm_file → RTMStore.load → merge → save
18. Return FlowResult
```

### Public API

```python
def run_pipeline(
    input_path: str,
    rtm_file: str | None = None,
    force: bool = False,
    output_format: str = "markdown",
    use_fake_llm: bool = False,
) -> FlowResult:
    """File-based entry point."""

def run_pipeline_from_dict(
    data: dict,
    rtm_file: str | None = None,
    force: bool = False,
    output_format: str = "markdown",
    use_fake_llm: bool = False,
) -> FlowResult:
    """Dict-based entry point (for testing/programmatic use)."""
```

### LLM Client Resolution

```python
def _resolve_llm_clients(config: dict, use_fake: bool) -> dict:
    """Returns {"generator": LLMClient, "reviewer": LLMClient, "refinement": LLMClient}"""
    if use_fake:
        return {"generator": FakeLLMClient(...), "reviewer": FakeLLMClient(...), "refinement": FakeLLMClient(...)}
    
    routing = config.get("model_routing", {})
    # For each phase: check routing[phase], else fall back to top-level model names
    # Wrap each in BudgetedLLMClient(max_tokens=32000)
```

### Real LLM Providers

```python
# src/skuld/providers/anthropic_client.py
class AnthropicLLMClient:
    """Claude API client. Reads SKULD_ANTHROPIC_KEY from env."""
    def __init__(self, model: str, temperature: float, thinking_effort: str): ...
    def generate(self, request: GenerationRequest) -> GenerationResponse: ...

# src/skuld/providers/openai_client.py
class OpenAILLMClient:
    """OpenAI API client. Reads SKULD_OPENAI_KEY from env."""
    def __init__(self, model: str, temperature: float): ...
    def generate(self, request: GenerationRequest) -> GenerationResponse: ...
```

**API key handling:**
- Environment variables: `SKULD_ANTHROPIC_KEY`, `SKULD_OPENAI_KEY`
- No keys in code, config files, or logs
- Missing key → clear error: `"SKULD_ANTHROPIC_KEY not set. Use --dry-run for testing without API keys."`

### Error Handling

| Error | FlowResult |
|-------|------------|
| `FileNotFoundError` / `InputValidationError` | `EXIT_INPUT_ERROR` |
| `GenerationError` / `ReviewParseError` | `EXIT_VALIDATION_ERROR` + error message |
| `TokenBudgetExceeded` | `EXIT_VALIDATION_ERROR` + "Token budget exceeded" |
| Self-validation failure | `EXIT_VALIDATION_ERROR` + validation errors |
| Missing API key (and not `use_fake_llm`) | `EXIT_INPUT_ERROR` + "API key not configured" |
| Success | `EXIT_OK` + rendered output |

### Warnings (non-fatal, populated in FlowResult.warnings)

- Strategy ref lacks approval
- AC count > 15 (warning threshold)
- Same generator/reviewer model
- Cross-story RTM overlap (from merge)

### Tests (≥10)

| Test | What it validates |
|------|-------------------|
| `test_happy_path_fake_llm` | Full pipeline with FakeLLMClient → EXIT_OK + valid output |
| `test_input_error_bad_file` | Nonexistent file → EXIT_INPUT_ERROR |
| `test_generation_failure` | Malformed LLM response → EXIT_VALIDATION_ERROR |
| `test_review_parse_failure` | Reviewer returns garbage → EXIT_VALIDATION_ERROR |
| `test_token_budget_exceeded` | Low budget → EXIT_VALIDATION_ERROR |
| `test_self_validation_failure` | Renderer produces invalid output → EXIT_VALIDATION_ERROR |
| `test_strategy_warning_populated` | Strategy ref without approval → warnings |
| `test_rtm_merge_on_success` | RTM file created/updated after successful run |
| `test_dict_entry_point` | `run_pipeline_from_dict` works identically |
| `test_json_output_format` | `output_format="json"` produces valid JSON |
| `test_comments_filtered` | Pipeline filters comments before prompt |
| `test_use_fake_llm_flag` | `use_fake_llm=True` skips real providers |

---

## T14: CLI

### File: `src/skuld/cli.py` (replace existing stub)

### Commands

```
skuld generate <input.yaml> [OPTIONS]
    --output, -o FILE        Write output to file (default: stdout)
    --format [markdown|json]  Output format (default: markdown)
    --rtm-file PATH          Merge results into persistent RTM
    --force                  Force full RTM regeneration for this story
    --dry-run                Use FakeLLMClient (no API keys needed)

skuld score <test_cases.json> [OPTIONS]
    --format [markdown|json]  Output format (default: markdown)
    (Deterministic RTM scoring — no LLM needed)

skuld rtm update <test_cases.json> --rtm-file PATH
    (Merge existing test cases into RTM without generation)

skuld rtm report --rtm-file PATH
    (Coverage summary: totals, percentages, gaps count)

skuld rtm gaps --rtm-file PATH
    (Detailed gap list: which ACs missing which types)

skuld rtm history --rtm-file PATH --ac <AC-ID>
    (Coverage timeline for one AC)

skuld benchmark <input.yaml> <assertions.yaml>
    (Run pipeline + validate against assertions)
    --dry-run               Use FakeLLMClient for benchmarks
```

### Implementation Pattern

```python
@click.group()
@click.version_option()
def main(): ...

@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path())
@click.option("--format", "output_format", type=click.Choice(["markdown", "json"]), default="markdown")
@click.option("--rtm-file", type=click.Path())
@click.option("--force", is_flag=True)
@click.option("--dry-run", is_flag=True)
def generate(input_file, output, output_format, rtm_file, force, dry_run): ...

@main.group()
def rtm(): ...

@rtm.command()
def report(): ...

@rtm.command()
def gaps(): ...
```

### `skuld score` Input Format

Accepts the JSON produced by `render_json`:
```json
{
  "test_cases": [...],
  "rtm_matrix": {...},
  "confidence_score": {...},
  "gaps": [...]
}
```

Or a simpler YAML with just test cases + ACs:
```yaml
acceptance_criteria:
  - id: "AC-1"
    description: "..."
test_cases:
  - id: "TC-001"
    ac_ids: ["AC-1"]
    test_type: "functional"
    ...
```

The `score` command:
1. Loads test cases + ACs from file
2. Calls `build_rtm()` → `score_rtm_detailed()` → `compute_confidence_from_detailed()`
3. Renders score output

### Tests (≥12)

| Test | Validates |
|------|-----------|
| `test_generate_valid_input` | Exit 0, output on stdout |
| `test_generate_output_to_file` | `--output` writes file |
| `test_generate_invalid_input` | Exit 2, error on stderr |
| `test_generate_with_rtm_file` | RTM file created |
| `test_generate_dry_run` | Works without API keys |
| `test_generate_json_format` | `--format json` output is valid JSON |
| `test_score_command` | Deterministic scoring, no LLM |
| `test_rtm_report` | Prints coverage summary |
| `test_rtm_gaps` | Lists gap details |
| `test_benchmark_pass` | Exit 0 on valid assertions |
| `test_benchmark_fail` | Exit 1 on assertion failure |
| `test_help` | `--help` outputs usage |

---

## T15: Benchmarks

### File: `src/skuld/benchmark_runner.py` (copy from IRO, rename imports)

### Scenarios

#### 1. `benchmarks/login-mfa.input.yaml`

```yaml
story:
  id: "AUTH-101"
  title: "User login with MFA"
  description: "As a registered user, I want to log in using MFA so my account is secure."

acceptance_criteria:
  - id: "AC-1"
    description: "User can log in with valid email and password"
    criticality: high
  - id: "AC-2"
    description: "MFA code sent to registered phone after password validation"
    criticality: high
  - id: "AC-3"
    description: "Login fails after 3 incorrect MFA attempts with account lock"
    criticality: medium
  - id: "AC-4"
    description: "Meaningful error message for expired MFA code"
    criticality: low

comments:
  - "Dev: what about session timeout during MFA flow?"
  - "QA: handle SMS delivery failure gracefully"

domain_context:
  industry: "fintech"
  application_type: "banking portal"
  users: "retail banking customers"
  compliance: ["PCI-DSS", "SOX"]

config:
  filter_comments: true
  output_format: "markdown"
```

#### 2. `benchmarks/ecommerce-checkout.input.yaml`

8+ ACs covering: cart validation, payment processing, inventory check, shipping calculation, order confirmation, error handling, timeout, partial payment.

With `strategy_ref` (approved), domain_context (retail/ecommerce), comments.

#### 3. `benchmarks/incomplete-story.input.yaml`

```yaml
story:
  id: "MIN-001"
  title: "Minimal story"
  description: "As a user, I want to do something."

acceptance_criteria:
  - id: "AC-1"
    description: "The thing works"
    criticality: medium
```

No comments, no domain, no strategy ref. Tests graceful handling.

### Assertions Format

```yaml
# benchmarks/login-mfa.assertions.yaml
must_include_headings:
  - "## Test Cases"
  - "## Requirements Traceability Matrix"
  - "## Confidence Score"
  - "## Coverage Gaps"

must_include_labels:
  - "AC Coverage:"
  - "Negative Coverage:"
  - "Edge-Case Coverage:"
  - "Orphan Tests:"
  - "Overall Confidence:"

must_include_substrings:
  - "functional"
  - "negative"
  - "edge-case"
  - "AC-1"
  - "AC-2"
  - "AC-3"
  - "AC-4"
```

### `use_fake_llm` for Benchmarks

Benchmarks run with `use_fake_llm=True` by default (deterministic, free, fast). The `FakeLLMClient` is configured with pre-recorded responses matching each scenario. This ensures:
- CI runs without API keys
- Results are deterministic (same input → same output)
- No cost per test run

Config flag in benchmark command: `skuld benchmark --dry-run` (default for benchmark command).

### Tests (≥5)

| Test | Validates |
|------|-----------|
| `test_login_mfa_passes_assertions` | Full scenario + all assertions green |
| `test_ecommerce_passes_assertions` | Scale scenario + assertions green |
| `test_incomplete_passes_assertions` | Minimal input + graceful handling |
| `test_benchmark_runner_reports_failures` | Bad assertions → clear error report |
| `test_benchmark_runner_nonexistent_file` | Missing input → error |

---

## T16: Coverage Hardening

### Actions

1. **Coverage measurement:**
   ```bash
   pytest --cov=skuld --cov-report=term-missing --cov-fail-under=90
   ```

2. **Per-module check:** Every module ≥90% line coverage

3. **Guardrail verification tests** (add to `tests/test_guardrails.py`):

   ```python
   class TestArchitectureGuardrails:
       def test_deterministic_modules_dont_import_llm(self):
           """rtm_builder, rtm_scorer, confidence_scorer must not import LLM code."""
           import importlib
           for mod_name in ("skuld.rtm_builder", "skuld.rtm_scorer", "skuld.confidence_scorer"):
               mod = importlib.import_module(mod_name)
               source = inspect.getsource(mod)
               assert "llm_client" not in source
               assert "LLMClient" not in source

       def test_token_budget_enforcement(self):
           """Low budget → TokenBudgetExceeded."""
           ...

       def test_ac_count_limit(self):
           """31 ACs → InputValidationError."""
           ...

       def test_yaml_bomb_rejected(self):
           """File > 1MB → InputValidationError."""
           ...
   ```

4. **Fix gaps:** Add tests for any uncovered branches found by coverage report

---

## Provider Module Structure

```
src/skuld/
├── providers/
│   ├── __init__.py
│   ├── anthropic_client.py    # AnthropicLLMClient
│   └── openai_client.py       # OpenAILLMClient
```

Both providers:
- Read API key from environment variable
- Accept `model`, `temperature`, `thinking_effort` (where supported)
- Return `GenerationResponse` with token counts populated
- Handle HTTP errors gracefully → raise descriptive exceptions
- Never log or expose API keys

---

## Fake LLM Pre-Recorded Responses

Store in `tests/fixtures/`:
```
tests/fixtures/
├── fake_responses/
│   ├── login_mfa_generator.json       # Pass 1 output for login-mfa scenario
│   ├── login_mfa_reviewer.json        # Reviewer output
│   ├── login_mfa_refinement.json      # Pass 2 output
│   ├── ecommerce_generator.json
│   ├── ecommerce_reviewer.json
│   ├── ecommerce_refinement.json
│   ├── incomplete_generator.json
│   ├── incomplete_reviewer.json
│   └── incomplete_refinement.json
```

`FakeLLMClient` in benchmark mode loads from these files (sequential responses per scenario).

---

## Config-Driven LLM Flag

In `story_input.yaml`:
```yaml
config:
  use_fake_llm: false    # default: false (use real providers)
                         # set to true for benchmarks/CI/dry-run
```

CLI `--dry-run` overrides this to `true` regardless of config value.

---

## Acceptance Criteria for Phase 4 Complete

- [ ] `skuld generate sample.yaml --dry-run` produces valid markdown output
- [ ] `skuld generate sample.yaml --dry-run --format json` produces valid JSON
- [ ] `skuld benchmark benchmarks/login-mfa.input.yaml benchmarks/login-mfa.assertions.yaml --dry-run` exits 0
- [ ] All 3 benchmarks pass
- [ ] `pytest --cov-fail-under=90` passes
- [ ] All guardrail tests pass
- [ ] `skuld score` works without LLM
- [ ] `skuld rtm report` produces readable output
- [ ] Real provider classes exist (even if untested against live API in CI)
- [ ] Total test count ≥ 430
