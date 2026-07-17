# Skuld — Reusability Index

> **Purpose:** Quick-lookup of available utilities within this repo. Check here before writing new helpers.
> **Rule:** After creating a reusable utility, add it here. Before writing a new one, search here first.

---

## Models (`src/skuld/models.py`)

| Utility | Purpose | Used by |
|---------|---------|---------|
| `FlowResult` | Pipeline outcome (exit_code, message, output_path, warnings) | end_to_end_flow, CLI |
| `ValidationResult` | Validation pass result (errors, total_checks, is_valid) | output_validator, benchmark_runner |
| `InputPackage` | Loaded input (source_path, raw, normalized) | input_loader, end_to_end_flow |
| `ConfidenceScore` | Composite score with breakdown | confidence_scorer, renderer |
| `RTMEntry` | Single traceability mapping | rtm_builder, rtm_store, rtm_scorer |
| `MergeResult` | Merge outcome (added, superseded, retained, conflicts) | rtm_store |
| `GapInfo` | Coverage gap (ac_id, story_id, missing_types, gap_since) | rtm_store |
| `ReviewFeedback` | Adversarial review output (flagged, missing, scores, suggestions) | adversarial_reviewer (Phase 3) |

## Input Validation (`src/skuld/input_loader.py`)

| Utility | Purpose | Used by |
|---------|---------|---------|
| `InputValidationError` | Custom exception for validation failures | input_loader, end_to_end_flow |
| `_require_keys(obj, keys, context)` | Dict key presence validator | input_loader |
| `validate_raw(raw)` | Pure-logic validation (no I/O) | input_loader, tests |
| `load_input(path)` | File-based entry point | CLI, end_to_end_flow |

## Output Validation (`src/skuld/output_validator.py`)

| Utility | Purpose | Used by |
|---------|---------|---------|
| `parse_sections(markdown)` | Split markdown by headings → dict | output_validator, renderer (verification) |
| `validate_output(markdown)` | Contract check → ValidationResult | end_to_end_flow, benchmark_runner |
| `REQUIRED_HEADINGS` | List of required section headings | output_validator, renderer |
| `REQUIRED_LABELS` | List of required labels | output_validator, renderer |

## RTM (`src/skuld/rtm_builder.py`)

| Utility | Purpose | Used by |
|---------|---------|---------|
| `build_rtm(test_cases, acs)` | Create RTMEntry list from test cases | end_to_end_flow |
| `rtm_to_matrix(entries, acs, tcs)` | Build coverage matrix + detect orphans | renderer, rtm_scorer |
| `find_gaps(entries, acs)` | Human-readable gap list | rtm_scorer (detailed), renderer |

## RTM Store (`src/skuld/rtm_store.py`)

| Utility | Purpose | Used by |
|---------|---------|---------|
| `RTMStore.load(path)` | Load persistent RTM from YAML | CLI |
| `RTMStore.save(path)` | Atomic write to YAML | CLI |
| `RTMStore.merge(entries, story_id, run_id, force)` | AC-level merge with overlap warnings | end_to_end_flow, CLI |
| `RTMStore.active_entries` | Only active entries (for scoring) | end_to_end_flow, CLI |
| `RTMStore.query_gaps(ac_ids)` | Gap analysis with structured output | CLI (rtm report/gaps) |

## Scoring (`src/skuld/rtm_scorer.py`)

| Utility | Purpose | Used by |
|---------|---------|---------|
| `score_rtm(entries, acs)` | Scalar composite score (0–100) | confidence_scorer |
| `score_rtm_detailed(entries, acs)` | Dict with sub-scores + tier + gaps | confidence_scorer, renderer |
| `assign_tier(score)` | Threshold → "high"/"medium"/"low" | rtm_scorer, confidence_scorer |

## Confidence (`src/skuld/confidence_scorer.py`)

| Utility | Purpose | Used by |
|---------|---------|---------|
| `compute_confidence(rtm_score, adversarial_score, ...)` | Weighted combination → ConfidenceScore | end_to_end_flow |
| `compute_confidence_from_detailed(rtm_detailed, adversarial_score)` | Convenience: takes score_rtm_detailed output directly | end_to_end_flow |

## Rendering (`src/skuld/renderer.py`)

| Utility | Purpose | Used by |
|---------|---------|---------|
| `render_report(test_cases, rtm_matrix, confidence, gaps, format)` | Dispatch to markdown/json | end_to_end_flow, CLI |
| `render_markdown(...)` | Human-readable report | render_report |
| `render_json(...)` | Machine-readable output | render_report |
| `_escape_cell(text)` | Escape pipes/newlines for markdown tables | render_markdown |
