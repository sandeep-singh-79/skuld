# Notes — Skuld

Temporary working notes, open questions, in-flight thinking.

---

## Review Findings After V2-1..V2-4 (2026-07-22)

### Current findings

- Docs/contract review completed against code and tests.
  - HIGH: release/version contract drift — README and CHANGELOG present 0.2.0 as current while package metadata and CLI version remain 0.1.0.
  - HIGH: default model contract drift — loader defaults still normalize to `claude-sonnet-4` / `gpt-5.5`, while newer docs and provider wiring point toward `claude-sonnet-4-20250514` / `gpt-4o`.
  - LOW: changelog coverage claim should be ~96% (95.83 current run), not ~97%.
  - LOW: usage docs should mention explicit `provider` for deployment-specific model aliases and consider a short note clarifying why V1 template docs contain V2 provider-routing fields.

- RESOLVED (2026-07-22): Anthropic cache-eligible prompt content now lives in `system_prompt`.
  - Stable requirements/schema blocks were moved out of `user_prompt` for generator, reviewer, and refinement prompts.
  - `_compose_system_prompt()` now acts as an explicit cache-safety guardrail: only stable, non-user-specific content belongs in cache-marked system prompts.

- RESOLVED (2026-07-22): Input-loader hardening now trusts explicit providers for deployment-specific aliases while still rejecting obvious known-prefix mismatches.
  - `model_routing` phases now infer providers only when `provider` is absent.
  - Explicit providers remain validated against known `claude-*` / `gpt-*` / `o1-*` / `o3-*` / `o4-*` prefixes, but unknown alias names are accepted when the provider is explicit.

- RESOLVED (2026-07-22): Numeric coercion at the loader boundary now rejects booleans and non-integral numerics for integer fields.
  - `True`/`False` no longer coerce into `temperature` or token limits.
  - Float values and float-like strings are rejected for integer token fields.

- RESOLVED (2026-07-22): Prompt-cache safety is now protected by regression tests.
  - Tests assert that story-specific content, comments, domain context, generated test payloads, and review feedback payloads stay out of cache-eligible `system_prompt` blocks.

- RESOLVED (2026-07-22): Provider config validation now happens at the input-loader boundary.
  - Top-level `temperature`, `max_tokens`, `max_tokens_per_run`, and `output_format` are validated/coerced before provider resolution.
  - `model_routing` now validates required phases, provider/model compatibility, and per-phase numeric fields; missing providers are inferred and written back.

- RESOLVED (2026-07-22): The prompt-caching footgun now has a concrete code-level safeguard.
  - The cache-safe composition helper documents the rule that user-specific content must not be moved into cacheable system prompt blocks.

### Review misses / pending reviews

- Real-provider smoke review is still pending.
  - Trigger: once valid `SKULD_ANTHROPIC_KEY` and `SKULD_OPENAI_KEY` are available.
  - Scope: one tiny real Anthropic call and one tiny real OpenAI call to confirm payload shape, finish_reason handling, and usage fields.

- Cost/latency/cache-behavior review is still pending.
  - Trigger: once real provider keys are available.
  - Scope: verify Anthropic cache counters move as expected and shared budgeting behaves correctly with cached reads.

- Parser/output-contract review with real provider output is still pending.
  - Trigger: once real provider keys are available.
  - Scope: confirm real model responses still satisfy JSON parsing and truncation assumptions across generate/review/refine paths.

### Ready-for-docs-and-commit checklist

- [x] V2-1 Anthropic provider implemented
- [x] V2-2 OpenAI provider implemented
- [x] V2-3 Provider resolution wired
- [x] V2-4 Shared per-run budget wired
- [x] Functional review completed
- [x] User-perspective review completed
- [x] Security review completed
- [x] Base-class refactor completed
- [x] Anthropic cache token accounting fixed
- [x] Prompt-builder cache split completed
- [x] Loader-boundary provider config validation completed
- [x] Cache-safety regression guards completed
- [x] Docs created/updated
- [x] Docs/contract review completed
- [ ] Real-provider smoke review completed with valid API keys
- [ ] Cost/latency/cache-behavior review completed with valid API keys
- [ ] Parser/output-contract review completed with real provider output
- [ ] Final adversarial-reviewer pass completed
- [ ] Commit

---

## V2 Prompt/Config Hardening (2026-07-22)

**Status:** Complete. 624 tests passing.

### What was fixed
- Stable requirements/schema content now lives in cache-eligible `system_prompt` blocks for generator, reviewer, and refinement prompts.
- Per-request minima (`min_negative_per_ac`, `min_edge_case_per_ac`) remain in `user_prompt` to avoid Anthropic cache fragmentation.
- Provider config is now validated and normalized at the input-loader boundary.
- Explicit providers now support deployment-specific alias model names while still rejecting obvious known-prefix mismatches.
- Numeric provider config rejects `bool` values and non-integer token limits for integer fields.

### Regression guards added
- Story, comments, and domain context stay out of generator `system_prompt`.
- Generated tests stay out of reviewer `system_prompt`.
- Original tests and review feedback stay out of refinement `system_prompt`.
- Custom per-run minima stay out of cache-eligible generator `system_prompt`.

### Deferred items
- **D-V2-PROMPT-1 (MEDIUM):** Real-world Anthropic cache effectiveness still needs validation with actual provider keys and usage counters.

---

## V2 Refactor: BaseLLMProvider + Prompt Caching (2026-07-22)

**Status:** Complete. 601 tests, 97% coverage. On branch `feature/v2-providers`.

### What was done:
- `src/skuld/providers/base.py` — Template Method base class (129 lines)
- Refactored both providers to ~70-80 lines each (down from ~115)
- Anthropic prompt caching: `cache_control: {"type": "ephemeral"}` on system prompt
- Token accounting: sums `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`
- `_DISPLAY_NAME` attribute for correct user-facing names ("OpenAI" not "Openai")

### Adding a new provider now requires:
- ~15 lines: class attrs + 4 method implementations
- No boilerplate for key resolution, SDK import, error wrapping, response building

### GPT-5.4 review findings:
- F1 (HIGH): Cache tokens undercounted → fixed, sum all input-side counters
- F2 (MEDIUM): Caching may be no-op for short system prompts → accepted, preparatory
- F3 (MEDIUM): Config validation at loader boundary → fixed in V2 Prompt/Config Hardening slice
- F4 (LOW): title() → _DISPLAY_NAME → fixed

---

## V2-2/V2-3/V2-4: OpenAI + Provider Resolution + Shared Budget (2026-07-22)

**Status:** Complete. 597 total tests, 96% coverage. On branch `feature/v2-providers`.

### V2-2: OpenAILLMClient
- `src/skuld/providers/openai_client.py` — mirrors anthropic pattern exactly
- 31 tests, covers protocol, init, generate, error handling, budgeted wrapping
- Default model: `gpt-4o`, env var: `SKULD_OPENAI_KEY`

### V2-3: Provider Resolution
- Replaced `_resolve_llm_clients()` stub with real wiring
- Two modes: simple (`generator_model`/`reviewer_model`) and advanced (`model_routing`)
- Provider inference: `claude-*` → anthropic, `gpt-*/o1-*/o3-*/o4-*` → openai
- `_infer_provider()` and `_create_provider_client()` helper functions

### V2-4: SharedBudget
- Added `SharedBudget` class to `llm_client.py`
- All three phases share a single token counter per run
- `BudgetedLLMClient` accepts optional `shared_budget` parameter

### GPT-5.4 review findings (all resolved):
- F1 (HIGH): model_routing schema not validated → added dict/model checks with ValueError
- F2 (HIGH): Three independent budgets → SharedBudget shared across all phases
- F3 (MEDIUM): Advanced mode ignored max_tokens_per_run → fixed in both paths
- F4 (MEDIUM): No same-model warning for model_routing → added check
- F5 (MEDIUM): No type/range validation on config values → deferred to V2-7+ (input_loader hardening)

### Awaiting:
- User's adversarial-reviewer agent pass

---

## V2-1: AnthropicLLMClient (2026-07-21)

**Status:** Complete. 30 tests, 100% coverage. On branch `feature/v2-providers`.

### What was done:
- `src/skuld/providers/__init__.py` — package init
- `src/skuld/providers/anthropic_client.py` — `AnthropicLLMClient` implementation (104 lines)
- `tests/test_anthropic_client.py` — 30 tests (protocol, init, generate, error handling, budgeted wrapping)
- `pyproject.toml` — optional dependency groups: `anthropic`, `openai`, `providers`

### Design decisions:
- API key resolution: explicit `api_key` param → `SKULD_ANTHROPIC_KEY` env var → `ValueError`
- No CLI `--api-key` flag (security: visible in shell history, process listings)
- Constructor `api_key` param kept for programmatic callers (vault integration, test harness)
- `anthropic` SDK imported lazily inside `__init__` (module importable without SDK installed)
- Content block filtering: only `text`-bearing blocks extracted; non-text blocks skipped
- `stop_reason` mapping: `end_turn`→`stop`, `max_tokens`→`length`, `None`→`stop`, others pass-through
- Specific exception catches: `AuthenticationError`, `RateLimitError`, `APITimeoutError`, `APIConnectionError` — all with actionable user-facing messages
- Generic `Exception` fallback wraps remaining errors with `from exc` for traceback chain
- Full try/except covers response processing too (AttributeError from malformed responses)

### Review rounds:
- R1 Adversarial: 4 findings (F1-F4) — all resolved
- R2 Adversarial: 6 findings — 5 resolved, 1 deferred (SDK exception granularity)
- R3 User-perspective + Security: 8 findings — 3 MEDIUM fixed (auth/rate-limit/timeout messages), 1 MEDIUM deferred (SEC-4)

### Deferred items:
- **D-V2-1-1 (MEDIUM):** SDK exception type granularity — callers can't distinguish retryable vs permanent errors. Original exception preserved via `__cause__`. Fix when adding retry logic in V2-3 provider resolver.
- **D-V2-1-2 (MEDIUM):** No JSON schema validation on LLM response content (SEC-4). Belongs in test_generator/adversarial_reviewer parsing layer. Fix in V2-5 integration tests.

### Awaiting:
- User's GPT-5.4 adversarial review before merge

---

## T17: Usage Documentation & Learning Guide (2026-07-21)

**Status:** Complete. README rewritten, 4 new docs created, adversarial findings fixed.

### Deferred MEDIUM items (accepted):
- **D17-1:** No API key setup instructions. `--dry-run` path is fully documented; real-provider onboarding deferred until providers are wired.
- **D17-2:** Scoring model explained in 4 places (README, V1-OUTPUT, LEARNING-GUIDE, USAGE-GUIDE). Acceptable duplication — each serves a different reading depth.
- **D17-3:** USAGE-GUIDE duplicates README installation section. Acceptable; keeps the guide self-contained.
- **D17-4:** `rtm update --force` not mentioned in USAGE-GUIDE prose (only in CLI ref table). Acceptable gap.
- **D17-5:** V1-OUTPUT-TEMPLATE sample uses `...` for truncated rows. Acceptable for a reference doc.

**Template source:** Follow the established structure from IRO/SuiteCompass and QEStrategyForge docs.

### Deliverables

| Artifact | Template from | Content |
|----------|---------------|---------|
| `README.md` (rewrite) | All 3 tools | Installation, quick start (correct CLI examples), feature overview, pipeline position, scoring model summary |
| `docs/USAGE-GUIDE.md` | `IRO/docs/USAGE-GUIDE.md` | Prerequisites, installation, workflow steps (generate → score → rtm → benchmark), CLI command reference with options/flags, exit codes, worked examples |
| `docs/V1-INPUT-TEMPLATE.md` | `IRO/docs/V1-INPUT-TEMPLATE.md` | Full YAML schema: `story`, `acceptance_criteria`, `comments`, `domain_context` (dict shape), `strategy_ref`, `config` — field tables with type/required/default/valid-values |
| `docs/V1-OUTPUT-TEMPLATE.md` | `IRO/docs/V1-OUTPUT-TEMPLATE.md` | Required sections (Story Context, Test Cases, RTM, Confidence Score, Coverage Gaps), required labels, annotated sample output from `--dry-run` |
| `docs/LEARNING-GUIDE.md` | `IRO/docs/LEARNING-GUIDE.md` | Domain teaching: why test case generation matters, how Skuld thinks (pipeline diagram), interpreting RTM coverage, confidence score breakdown, sprint workflow integration |

### Structure notes (from sibling tools)

- **USAGE-GUIDE**: Workflow 0 (quick start from template), Workflow 1 (YAML-first), Workflow 2 (benchmark), CLI reference table
- **V1-INPUT-TEMPLATE**: Top-level structure diagram, per-section field tables with types/defaults/validation rules
- **V1-OUTPUT-TEMPLATE**: Output principles (structured, deterministic, machine-checkable), section table, label table, annotated sample
- **LEARNING-GUIDE**: Opens with "How X Thinks" (pipeline diagram), then domain concepts, then interpretation guidance, then common pitfalls

### Scope rules
- Documents the implemented CLI only, not future/planned features
- Uses `--dry-run` path for all examples (no API keys needed)
- References benchmark scenarios as working examples
- Ships in the same commit as the stale README fix

### Dependencies
- T14 (CLI) ✅
- T15 (benchmarks) ✅
- No code changes expected — documentation only

---

## T15 Benchmarks (2026-07-20)

**Status:** Complete. 3 benchmark scenarios + domain_context fix. 503→516 tests.

### What was done:
- 3 benchmark input/assertion file pairs (login-mfa, ecommerce-checkout, incomplete-story)
- Fixed `prompt_builder._fence()` crash on dict `domain_context` (serializes to YAML string)
- Restored spec-compliant `domain_context` blocks in benchmark inputs
- `benchmarks/README.md` rewritten with correct CLI pattern and design limitations

### Still deferred:
- **D15-2:** Scenario-sensitive benchmarks (V2 — needs real provider responses or scenario fixtures)
- **D15-3:** `strategy_ref` / HITL contract (future T-slice when HITL gates are wired)
- **D15-5:** Structural assertion duplication across 3 files (revisit at 6+ scenarios)

---

## T16 Coverage Hardening (2026-07-20)

**Status:** Complete. 516 tests, 96% coverage, `--cov-fail-under=90` gate passes.

### What was done:
- `tests/test_guardrails.py`: 8 architecture/safety guardrail tests (deterministic boundary, token budget, AC limit, loader size, CLI size)
- Unified `generate` file-size contract: removed redundant 10MB CLI guard, loader's 1MB is the single authority
- 5 degraded-scenario integration tests proving the scoring/gap path can go red:
  - functional-only → medium tier (score 55–58)
  - mixed degradation → medium tier (score 56–59)
  - orphan-only → high tier with penalty (score 97–99)
  - severe degradation → low tier (score < 50)
  - stage wiring integrity (3 distinct clients, call_count + prompt-content assertions)

### Residual LOW (record-only):
- Wiring test prompt-content assertions depend on exact prompt wording; a harmless prompt rewrite could require test updates

---

## T14 CLI Adversarial Review Summary (2026-07-20)

**Status:** All HIGH/MEDIUM findings resolved across 6 review rounds. Residual LOW items recorded. Ready for final whole-change-set review and commit.

**Review process:** GPT-5.4 found issues → Opus planned fixes → Sonnet implemented → Opus verified → repeat until no HIGH/MEDIUM findings remained.

### Review Round Summary

| Round | Findings | Key changes |
|-------|----------|-------------|
| R1 | F1–F5 (2H, 2M, 1L) | Spec-format benchmark assertions, `rtm update` shape validation, malformed-entry handling, file-size cap |
| R2 | R2-1 to R2-3 (2H, 1M) | Spec-format keys validated as lists, `ac_ids` string→list coercion, benchmark value coercion to string |
| R3 | R3-1 to R3-2 (1H, 1M) | `ac_ids` list element types validated, simple `assertions` field validated as list |
| R4 | R4-1 to R4-3 (2H, 1M) | Blank AC IDs rejected, pre-evaluation assertion schema validation, malformed typed assertions exit 2 |
| R5 | R5-1 to R5-3 (2H, 1M) | Negative `min_length` rejected, whitespace-padded AC IDs normalized, allowed types gated, non-string values rejected |
| R6 | R6-1 to R6-3 (2H, 1M) | `story_id` batch consistency in `rtm update`, benchmark fail-fast ordering, explicit `type` required for simple assertions |

**Total: 18 findings fixed (11 HIGH, 7 MEDIUM). 1 LOW accepted (F5: symlink bypass).**

### Final State

- **Tests:** 496 passing (75 CLI-specific)
- **Coverage:** `cli.py` 91%, overall 96%
- **Exit-code contract:** exit 2 = malformed input, exit 1 = valid benchmark failing against output, exit 0 = pass

### Hardening Applied (by surface area)

- **`_coerce_ac_ids()`:** type validation, element type validation, blank rejection, whitespace normalization
- **`score`:** file-size cap, JSON dict validation, `_coerce_ac_ids()`
- **`rtm update`:** file-size cap, JSON dict validation, `story_id` required/consistent/normalized, `_coerce_ac_ids()`
- **`benchmark`:** assertions validated before `run_pipeline()`, explicit `type` required for simple format, allowed types gated, non-empty string values enforced, negative `min_length` rejected

---

## T14 Deferred Items (2026-07-20)

### Still open:
- **D14-1:** Symlink bypass of `_validate_path` — low risk for local CLI.
- **D14-4:** Exit code semantics: "no API key" exits 2 (input error), but it's really an environment error.
- **D14-5:** `skuld rtm update --help` doesn't document expected JSON schema.
- **D14-6:** `skuld score` gap messages could suggest remediation.
- **D14-7:** Truncation guard only in `BudgetedLLMClient` wrapper. Real providers must also be wrapped (T15+).
- **D14-8:** Add truncation integration tests for real-provider wiring path.

### Resolved by adversarial review rounds:
- ~~D14-2: Benchmark with 0 assertions passes vacuously~~ → resolved by R1 (empty assertions rejected)
- ~~D14-3: Empty `value` in `contains` always passes~~ → resolved by R4 (empty values rejected)
- ~~T5b-3: Path traversal on --rtm-file~~ → resolved by T14 `_validate_path`
- ~~T13-D3: RTM file path traversal~~ → resolved by T14 `_validate_path`

### Residual LOW items from post-Round-6 review (record-only):

| # | Description | Suggested future test |
|---|-------------|----------------------|
| L1 | Later-item `story_id` missing/blank not explicitly tested | `test_rtm_update_later_item_missing_story_id_rejected` |
| L2 | Fail-fast benchmark test only proves one malformed shape skips pipeline | `test_benchmark_schema_invalid_assertions_fail_before_pipeline` |
| L3 | Mixed simple assertion list with one missing `type` not covered | `test_benchmark_mixed_assertion_list_with_one_missing_type_rejected` |

**Deferred handling rule:** add these tests only when a future change touches `benchmark` or `rtm update`.

---

## Pre-Increment Branch Review Fix Plan (2026-07-20, completed)

These fixes from the GPT-5.4 pre-increment review of `feature/phase-1-3-mvp` vs `main` are **already implemented and merged**:

1. ~~**Fix 1 (HIGH):** Wire `finish_reason` through `GenerationResponse` and reject truncated completions~~ ✅
2. ~~**Fix 2 (MEDIUM):** Fail fast on non-fake path until real providers are wired~~ ✅
3. ~~**Fix 3 (MEDIUM):** Honour `config.output_format` from input YAML~~ ✅

**Residual risk:** truncation enforcement depends on `BudgetedLLMClient` wrapping. When T15+ wires real providers, they must either be wrapped or enforce `finish_reason == "stop"` at the provider boundary.

---

## Deferred Issues — Target V2+

### From Phase 1 Adversarial Review

| # | Severity | Issue | Deferred reason | Target |
|---|----------|-------|-----------------|--------|
| P1-6 | MEDIUM | `parse_sections` uses exact heading match — LLM output may vary case/whitespace | Our renderer controls exact output; only matters if third-party tools produce reports | V2 |
| P1-7 | MEDIUM | Label occurrence counting uses substring match — could false-match on longer strings | Our renderer produces exact labels; no ambiguity in practice | V2 |
| P1-8 | MEDIUM | Domain models accept arbitrary strings for `test_type`, `priority`, `status` — no runtime enforcement | Validation happens at system boundaries (input_loader, LLM response parser in Phase 3) | V2 |
| P1-11 | MEDIUM | No prompt injection test for malicious content in story/AC fields | Prompt fencing (`<story_context>` tags) is a Phase 3 concern (prompt_builder) | Phase 3 |
| P1-12 | LOW | Same-model family detection too naive (exact string match only) | MVP config uses simple model names; family-aware matching is over-engineering | V2 |
| P1-15 | LOW | `total_checks` in ValidationResult counts attempted checks, not executed | Semantics are clear enough; documenting "attempted" is sufficient | V2 |

### From T5 Adversarial Review

| # | Severity | Issue | Deferred reason | Target |
|---|----------|-------|-----------------|--------|
| T5-6 | MEDIUM | `find_gaps` returns `list[str]` — scorer needs structured data | Scorer computes from `rtm_entries` directly; `find_gaps` is for human display only | V2 if needed |

### From T6 Adversarial Review

| # | Severity | Issue | Deferred reason | Target |
|---|----------|-------|-----------------|--------|
| T6-4 | LOW-MED | Orphan penalty too weak (max -10 points) — 50% orphans only costs 5 points | Weight tuning is calibration; need real-world data to set properly | V2 calibration |
| T6-5 | LOW-MED | Duplicate `test_case_id` inflates orphan dilution — can game the score | Data comes from `build_rtm` which doesn't produce duplicates; only matters if manual entries bypass builder | V2 |

### From T6 User-Perspective Review

| # | Severity | Issue | Deferred reason | Target |
|---|----------|-------|-----------------|--------|
| T6-U3 | MEDIUM | Under-declaring ACs inflates score — scorer trusts ac_list blindly | Pipeline integrity is E2E flow's job (T13), not scorer's | T13 |
| T6-U4 | MEDIUM | Sprint-over-sprint comparison misleads on scope growth vs regression | Needs per-story scoring or delta tracking; design decision for V2 | V2 |
| T6-U5 | LOW | "Medium" tier too broad (50–79.9) for ship/no-ship decisions | Needs real-world calibration data; 4-tier model possible in V2 | V2 |
| T6-U1 | LOW | Presence-based distribution gives full credit easily (1 of each = 1.0) | Intentional trade-off: prevents "adding tests lowers score" bug; documenting as design choice | Accepted |

| # | Severity | Issue | Deferred reason | Target |
|---|----------|-------|-----------------|--------|
| T5b-3 | LOW | Path traversal via `--rtm-file` — `save()` creates parent dirs | Validate path at CLI boundary (T14), not in rtm_store | T14 (CLI) |
| T5b-4 | MEDIUM | Mutable state exposure — `entries` property returns references, not frozen copies | All callers are internal; no external consumers | V2 |
| T5b-5 | LOW | TOCTOU race between `exists()`/`stat()` and `open()` on load | Not a multi-user server; single-process CLI tool | Won't fix |
| T5b-7 | LOW | Unbounded entry growth — superseded/deprecated entries never purged from YAML | Add `compact()` method to prune dead entries | V2 |

### From Story Rollover / Overlap Discussion

| # | Issue | Deferred reason | Target |
|---|-------|-----------------|--------|
| OL-1 | Semantic overlap detection — two stories with similar (not identical) ACs | Requires embeddings or NLP; MVP uses exact AC ID match for warnings | V2 / Orchestrator |
| OL-2 | Cross-story AC registry — shared AC IDs managed at project level | Orchestrator concern, not individual tool | Orchestrator |

### From T8/T9/T9b Workloop (Steps 3-6)

| # | Severity | Issue | Deferred reason | Target |
|---|----------|-------|-----------------|--------|
| T8-D1 | LOW | Markdown summary header for 50+ test cases (count by type at top) | UX improvement — surface when real usage shows the need | V2 |
| T8-D2 | LOW | JSON schema version field for downstream stability | Decide when first external consumer exists | V2 |
| T8-D3 | LOW | HTML/markdown injection in `_escape_cell` (XSS via markdown preview) | Output consumed by QE leads in editors, not web-served | V2 (if web-published) |
| T8-D4 | LOW | Collapsible sections for large suites (`<details>` tags) | Markdown doesn't natively support; defer until 50+ test reports | V2 |
| T9-D1 | ~~LOW~~ | ~~`finish_reason` field in GenerationResponse~~ | **RESOLVED by Fix 1 (pre-increment review 2026-07-20)** | ~~T11~~ |

### From T10 Workloop

| # | Severity | Issue | Deferred reason | Target |
|---|----------|-------|-----------------|--------|
| T10-D1 | LOW | Prompt token estimation (budget-aware prompt construction) | Integrate during T11 LLM flow | T11 |
| T10-D2 | LOW | Config-driven model-specific prompt tuning (Claude vs GPT formatting) | Over-engineering for MVP; all models handle the current format | Post-MVP |

### From T12 Workloop

| # | Severity | Issue | Deferred reason | Target |
|---|----------|-------|-----------------|--------|
| T12-D1 | LOW | Rubber-stamp LLM detection (empty flags + uniform quality = suspicious) | Heuristic design needed; cross-model review reduces probability | V2 |
| T12-D2 | LOW | No size cap on parsed list fields (flagged_tests, missing_scenarios) | max_tokens at HTTP layer provides practical bound | V2 |

### From T13 Workloop

| # | Severity | Issue | Deferred reason | Target |
|---|----------|-------|-----------------|--------|
| T13-D1 | LOW-MED | RTM load→merge→save non-atomic (concurrent writers lose data) | Single-user CLI tool; file locking is V2 | V2 |
| T13-D2 | LOW | Ctrl+C loses partial output silently | Acceptable for MVP; KeyboardInterrupt handler is over-engineering | V2 |
| T13-D3 | LOW | RTM file path traversal (no restriction on --rtm-file target) | OS permissions mitigate; add guard when CLI is wired in T14 | T14 |
