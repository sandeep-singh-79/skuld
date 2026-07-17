# Notes — Skuld

Temporary working notes, open questions, in-flight thinking.

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
| T9-D1 | LOW | `finish_reason` field in GenerationResponse | Wire when T11 (generator) uses it for truncation detection | T11 |

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
