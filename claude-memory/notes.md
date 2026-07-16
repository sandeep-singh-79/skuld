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

### From T5b Security Review

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
