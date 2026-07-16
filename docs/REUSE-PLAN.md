# Skuld — Reuse Plan

> **Purpose:** Tracks which components from existing repos are reused in Skuld, their source, adaptation needed, and target phase.
> **Last Updated:** 2026-07-16

---

## Direct Copy (verbatim or near-verbatim)

| # | Component | Source Repo | Source File | Target File in Skuld | Adaptation |
|---|-----------|-------------|-------------|---------------------|------------|
| R1 | `FlowResult` dataclass | IRO | `src/intelligent_regression_optimizer/models.py` | `src/skuld/models.py` | None — copy verbatim |
| R2 | `ValidationResult` dataclass | IRO | `src/intelligent_regression_optimizer/models.py` | `src/skuld/models.py` | None — copy verbatim |
| R3 | Exit code constants | IRO | `src/intelligent_regression_optimizer/models.py` | `src/skuld/models.py` | None — `EXIT_OK`, `EXIT_INPUT_ERROR`, `EXIT_VALIDATION_ERROR` |
| R4 | `InputPackage` dataclass | IRO | `src/intelligent_regression_optimizer/models.py` | `src/skuld/models.py` | None — `(source_path, raw, normalized)` |
| R5 | `InputValidationError` exception | IRO | `src/intelligent_regression_optimizer/input_loader.py` | `src/skuld/input_loader.py` | None |
| R6 | `_require_keys()` helper | IRO | `src/intelligent_regression_optimizer/input_loader.py` | `src/skuld/input_loader.py` | None |
| R7 | `benchmark_runner.py` (entire module) | IRO | `src/intelligent_regression_optimizer/benchmark_runner.py` | `src/skuld/benchmark_runner.py` | Rename imports only (`intelligent_regression_optimizer` → `skuld`) |
| R8 | `LLMClient` Protocol | QEStrategyForge | `src/ai_test_strategy_generator/llm_client.py` | `src/skuld/llm_client.py` | None — protocol interface is generic |
| R9 | `FakeLLMClient` test double | QEStrategyForge | `src/ai_test_strategy_generator/llm_client.py` | `src/skuld/llm_client.py` | Replace `_FAKE_STRATEGY` with Skuld-specific fake response |
| R10 | `GenerationRequest` / `GenerationResponse` | IRO | `src/intelligent_regression_optimizer/models.py` | `src/skuld/models.py` | None |
| R11 | `conftest.py` test fixtures | IRO | `tests/conftest.py` | `tests/conftest.py` | Update import paths |
| R12 | `_emit()` CLI helper | IRO | `src/intelligent_regression_optimizer/cli.py` | `src/skuld/cli.py` | None |

---

## Copy Structure (same skeleton, domain logic replaced)

| # | Component | Source Repo | Source File | Target File in Skuld | What to keep | What to replace |
|---|-----------|-------------|-------------|---------------------|--------------|-----------------|
| S1 | Two-level input loader | IRO | `input_loader.py` | `src/skuld/input_loader.py` | `validate_raw()` + `load_input()` pattern, file I/O wrapper, error handling | Validation rules → AC schema validation (id, description, criticality required per AC) |
| S2 | Output validator | IRO | `output_validator.py` | `src/skuld/output_validator.py` | `parse_sections()` markdown parser, `validate_output()` → `ValidationResult` pattern, heading/label/placement checks | `REQUIRED_HEADINGS`, `REQUIRED_LABELS`, `LABEL_SECTION_MAP` → Skuld's contract constants |
| S3 | CLI structure | IRO | `cli.py` | `src/skuld/cli.py` | `@click.group` + subcommands, `FlowResult` → `sys.exit()` mapping, `_emit()`, error output pattern | Remove IRO-specific options (`--history-dir`, `--area-map`, `--mode`); add Skuld-specific options |
| S4 | End-to-end flow | IRO | `end_to_end_flow.py` | `src/skuld/end_to_end_flow.py` | Dual-entry pattern (file + dict), `_run_from_package()` core, self-validation before returning `FlowResult` | Pipeline stages → `generate → review → refine → rtm_build → score → render` |
| S5 | Renderer | IRO | `renderer.py` | `src/skuld/renderer.py` | `lines: list[str]` accumulator, section-by-section rendering, `"\n".join(lines)` | Section names, labels, table formatting → Skuld's test case table + RTM + score |
| S6 | Prompt builder | QEStrategyForge | `prompt_builder.py` | `src/skuld/prompt_builder.py` | Base template + overlay composition, contract injection into prompt, template loading from files | Template content, field formatters, scenario names → generator prompt + reviewer prompt |
| S7 | Weighted scorer | ReleaseRadar | `quality_scorer.py` | `src/skuld/rtm_scorer.py` | Multi-factor `_compute_*` sub-score pattern, module-level tuning constants, `_assign_tier()` threshold logic | Factors → AC coverage, negative coverage, edge coverage, orphan penalty, type distribution |

---

## Phase Mapping

### Phase 1 — Scaffold + Core Data Model (T2–T4)

| Task | Reuse Items | Action |
|------|-------------|--------|
| T2: Models | R1, R2, R3, R4, R10 | Copy `FlowResult`, `ValidationResult`, `InputPackage`, exit codes, `GenerationRequest/Response` from IRO. Add Skuld-specific: `Story`, `AcceptanceCriterion`, `TestCase`, `RTMEntry`, `ConfidenceScore`, `ReviewFeedback`. |
| T3: Input loader | R5, R6, S1 | Copy `InputValidationError` + `_require_keys()`. Replicate two-level pattern. Write Skuld-specific AC validation rules. |
| T4: Output validator | S2 | Copy `parse_sections()`. Define Skuld's `REQUIRED_HEADINGS` and `REQUIRED_LABELS`. Write `validate_output()`. |
| (Support) conftest.py | R11 | Copy and update import paths. |

### Phase 2 — Deterministic Engine (T5–T8)

| Task | Reuse Items | Action |
|------|-------------|--------|
| T5: RTM builder | — | New module (no direct reuse — this is Skuld's unique logic). |
| T6: RTM scorer | S7 | Copy multi-factor scoring pattern from ReleaseRadar. Replace factors with RTM sub-scores. |
| T7: Confidence scorer | — | New module (combines RTM score + adversarial placeholder). Simple weighted average. |
| T8: Renderer | S5 | Copy line-accumulator pattern. Write Skuld-specific section rendering (test case table, RTM matrix, score breakdown). |

### Phase 3 — LLM Generation + Adversarial Review (T9–T12)

| Task | Reuse Items | Action |
|------|-------------|--------|
| T9: LLM client | R8, R9, R10 | Copy `LLMClient` Protocol, `FakeLLMClient`, `GenerationRequest/Response`. Add token tracking, `finish_reason` check, budget enforcement. |
| T10: Prompt builder | S6 | Copy template-composition pattern. Write generator prompt template + reviewer prompt template. Inject output contract into generator prompt. |
| T11: Test generator | — | New module (orchestrates Pass 1 + Pass 2 using LLM client + prompt builder). |
| T12: Adversarial reviewer | — | New module (calls reviewer LLM, parses into `ReviewFeedback` schema, produces qualitative score). |

### Phase 4 — Integration (T13–T16)

| Task | Reuse Items | Action |
|------|-------------|--------|
| T13: End-to-end flow | S4 | Copy dual-entry pattern + self-validation. Wire Skuld pipeline stages. |
| T14: CLI | S3, R12 | Copy Click group structure + `_emit()`. Define `skuld generate` + `skuld benchmark` commands. |
| T15: Benchmarks | R7 | Copy `benchmark_runner.py` verbatim (import rename only). Write ≥3 benchmark scenarios. |
| T16: Coverage hardening | — | Run pytest --cov; ensure ≥90% per module; all benchmarks green. |

---

## Execution Checklist

Before copying any component:
1. Read the source file in full
2. Identify domain-specific lines vs. generic structure
3. Copy generic structure into Skuld target file
4. Write failing tests FIRST (TDD red) for Skuld-specific behaviour
5. Implement Skuld-specific logic to pass tests (TDD green)
6. Refactor if duplication or complexity warrants it

**Rule:** Never copy domain logic from another repo. Only copy structural patterns and generic utilities. All Skuld-specific behaviour must be test-driven from scratch.

---

## Detailed Reuse Actions (3-Level)

### Phase 1 — Scaffold + Core Data Model

#### T2: Models — Reuse Steps
- **Copy from IRO `models.py`:**
  - `EXIT_OK = 0`, `EXIT_INPUT_ERROR = 1`, `EXIT_VALIDATION_ERROR = 2`
  - `FlowResult` dataclass (fields: `exit_code`, `message`, `output_path`, `warnings`)
  - `ValidationResult` dataclass (fields: `errors`, `total_checks`; property: `is_valid`)
  - `InputPackage` dataclass (fields: `source_path`, `raw`, `normalized`)
  - `GenerationRequest` dataclass (fields: `system_prompt`, `user_prompt`)
  - `GenerationResponse` dataclass (fields: `content`, `model`, `provider`, `prompt_tokens`, `completion_tokens`)
- **Adaptation:** None — copy verbatim, place at top of `src/skuld/models.py`
- **Verification:** Import in test file, instantiate each, assert field access works

#### T3: Input Loader — Reuse Steps
- **Copy from IRO `input_loader.py`:**
  - `InputValidationError(ValueError)` — custom exception class (no body needed)
  - `_require_keys(obj: dict, keys: list[str], context: str)` — raises `InputValidationError` if key missing
  - Two-level pattern skeleton:
    ```python
    def validate_raw(raw: dict) -> dict:
        # validate + normalize + return
    def load_input(path: str) -> InputPackage:
        # file I/O → yaml.safe_load → validate_raw → return InputPackage
    ```
- **Adaptation:** Replace validation body in `validate_raw()` with Skuld's AC schema rules
- **Verification:** Test that `_require_keys` raises on missing key; test that `load_input` returns `InputPackage`

#### T4: Output Validator — Reuse Steps
- **Copy from IRO `output_validator.py`:**
  - `parse_sections(markdown: str) -> dict[str, str]` — splits markdown by `## ` headings
  - `validate_output(markdown: str) -> ValidationResult` — structural pattern:
    ```python
    def validate_output(markdown):
        errors = []
        sections = parse_sections(markdown)
        # check headings present
        # check labels in correct sections
        return ValidationResult(errors=errors, total_checks=count)
    ```
- **Adaptation:** Replace `REQUIRED_HEADINGS`, `REQUIRED_LABELS`, `LABEL_SECTION_MAP` constants with Skuld's contract
- **Verification:** Test `parse_sections` splits correctly; test `validate_output` catches missing headings

#### Support: conftest.py — Reuse Steps
- **Copy from IRO `tests/conftest.py`:**
  - `FIXTURES_DIR`, `BENCHMARKS_DIR`, `REPO_TMP_DIR` path constants
  - `@pytest.fixture fixtures_dir()`, `benchmarks_dir()`, `repo_tmp(request)`
  - Cleanup logic in `repo_tmp` (mkdir + yield + shutil.rmtree)
- **Adaptation:** Update paths if directory structure differs (it doesn't — same convention)
- **Verification:** Run pytest, confirm fixtures resolve to correct paths

---

### Phase 2 — Deterministic Engine

#### T6: RTM Scorer — Reuse Steps
- **Copy from ReleaseRadar `quality_scorer.py`:**
  - Module-level constants pattern:
    ```python
    _WEIGHT_AC_COVERAGE = 0.30
    _WEIGHT_NEGATIVE = 0.25
    _WEIGHT_EDGE = 0.20
    _WEIGHT_DISTRIBUTION = 0.15
    _WEIGHT_ORPHAN_PENALTY = 0.10
    ```
  - Multi-factor sub-score pattern:
    ```python
    def _compute_ac_coverage(...) -> float: ...
    def _compute_negative_coverage(...) -> float: ...
    def _compute_edge_coverage(...) -> float: ...
    def _compute_orphan_penalty(...) -> float: ...
    def _compute_type_distribution(...) -> float: ...
    ```
  - Tier assignment pattern:
    ```python
    def _assign_tier(score: float) -> str:
        if score >= 80: return "high"
        if score >= 50: return "medium"
        return "low"
    ```
  - Composite scorer:
    ```python
    def score_rtm(rtm_entries, ac_list, config) -> float:
        sub_scores = [_compute_*(...) for each factor]
        return sum(weight * score for weight, score in zip(weights, sub_scores))
    ```
- **Adaptation:** Replace all factor formulas with RTM-specific logic; replace tier thresholds
- **Verification:** Test each `_compute_*` independently; test composite at boundary values

#### T8: Renderer — Reuse Steps
- **Copy from IRO `renderer.py`:**
  - Line-accumulator pattern:
    ```python
    def render_report(...) -> str:
        lines: list[str] = []
        lines.append("# Report Title")
        lines.append("")
        # ... section by section ...
        return "\n".join(lines)
    ```
  - Section helper pattern (one function per major section)
- **Adaptation:** Replace all section content with Skuld's: test case table, RTM matrix, confidence score, coverage gaps
- **Verification:** Rendered output passes `validate_output()`

---

### Phase 3 — LLM Generation + Adversarial Review

#### T9: LLM Client — Reuse Steps
- **Copy from QEStrategyForge `llm_client.py`:**
  - `LLMClient(Protocol)` with `@runtime_checkable`:
    ```python
    @runtime_checkable
    class LLMClient(Protocol):
        def generate(self, request: GenerationRequest) -> GenerationResponse: ...
    ```
  - `FakeLLMClient` test double:
    ```python
    class FakeLLMClient:
        def generate(self, request: GenerationRequest) -> GenerationResponse:
            return GenerationResponse(content=_FAKE_RESPONSE, model=request.model, ...)
    ```
- **Adaptation:**
  - Replace `_FAKE_RESPONSE` content with Skuld-specific fake test case output (valid JSON matching TestCase schema)
  - Add `_token_accumulator` field for budget tracking
  - Add `finish_reason` validation wrapper
- **Verification:** `isinstance(FakeLLMClient(), LLMClient)` is True; budget exceeded raises error

#### T10: Prompt Builder — Reuse Steps
- **Copy from QEStrategyForge `prompt_builder.py`:**
  - Template loading pattern:
    ```python
    def _load_template(name: str, prompt_dir: Path | None = None) -> str:
        base = prompt_dir or (Path(__file__).parent / "prompts")
        return (base / f"{name}.txt").read_text()
    ```
  - Contract injection pattern:
    ```python
    def _format_required_headings() -> str:
        return "\n".join(f"- {h}" for h in REQUIRED_HEADINGS)
    ```
  - Composition pattern:
    ```python
    def build_prompt(input_package, ...) -> str:
        base = _load_template("base")
        return base.format(context=..., contract=..., ...)
    ```
- **Adaptation:**
  - Create 3 templates: `generator.txt`, `reviewer.txt`, `refinement.txt`
  - Add user-content fencing (`<story_context>` / `</story_context>`)
  - Inject RTM contract (columns, expected structure) into generator prompt
  - Inject `ReviewFeedback` JSON schema into reviewer prompt
- **Verification:** Built prompt contains all ACs, fence delimiters present, contract injected

---

### Phase 4 — Integration

#### T13: End-to-End Flow — Reuse Steps
- **Copy from IRO `end_to_end_flow.py`:**
  - Dual-entry pattern:
    ```python
    def run_pipeline(input_path: str, ...) -> FlowResult:
        try:
            package = load_input(input_path)
        except (FileNotFoundError, InputValidationError) as exc:
            return FlowResult(exit_code=EXIT_INPUT_ERROR, message=str(exc), ...)
        return _run_from_package(package.normalized, ...)

    def run_pipeline_from_dict(data: dict, ...) -> FlowResult:
        normalized = validate_raw(data)
        return _run_from_package(normalized, ...)
    ```
  - Self-validation pattern:
    ```python
    def _run_from_package(normalized, ...) -> FlowResult:
        # ... pipeline stages ...
        validation = validate_output(rendered)
        if not validation.is_valid:
            return FlowResult(exit_code=EXIT_VALIDATION_ERROR, ...)
        return FlowResult(exit_code=EXIT_OK, message=rendered, ...)
    ```
- **Adaptation:** Wire Skuld pipeline stages (generate → review → refine → RTM → score → render)
- **Verification:** Happy path returns EXIT_OK; input error returns EXIT_INPUT_ERROR; validation failure returns EXIT_VALIDATION_ERROR

#### T14: CLI — Reuse Steps
- **Copy from IRO `cli.py`:**
  - `_emit()` helper:
    ```python
    def _emit(output: str | None, content: str):
        if output:
            Path(output).write_text(content)
        else:
            click.echo(content)
    ```
  - Click group + subcommand structure
  - Error mapping pattern: `FlowResult.exit_code` → `sys.exit()`
- **Adaptation:** Define `skuld generate`, `skuld benchmark`, `skuld score` commands with Skuld-specific options
- **Verification:** CLI tests with Click's `CliRunner`

#### T15: Benchmarks — Reuse Steps
- **Copy from IRO `benchmark_runner.py`:**
  - Entire module verbatim
  - Only change: `from intelligent_regression_optimizer.models import ValidationResult` → `from skuld.models import ValidationResult`
- **Adaptation:** None beyond import path
- **Verification:** `run_assertions(sample_markdown, sample_assertions_path)` returns `ValidationResult`

---

## Tracking

| Phase | Reuse Items Consumed | Status |
|-------|---------------------|--------|
| Phase 1 | R1–R6, R10, R11, S1, S2 | Not started |
| Phase 2 | S5, S7 | Not started |
| Phase 3 | R8, R9, S6 | Not started |
| Phase 4 | R7, R12, S3, S4 | Not started |
