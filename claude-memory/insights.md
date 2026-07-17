# Insights — Skuld

Reusable lessons and decision rules for this repository.

---

## TDD Gap Review Practice (Established T2/T3)

After each task's initial TDD cycle (red → green → refactor), perform a **gap review** pass before moving to the next task:

### Checklist
1. **Real-world type coercion** — YAML parses bare numbers as int, booleans as bool. Test that the code handles these gracefully (coerce or reject clearly).
2. **Whitespace/empty string** — Fields that pass `_require_keys` can still be semantically empty (`""`, `"   "`). Validate content, not just presence.
3. **Unicode/i18n** — International teams use non-ASCII in stories, ACs, and identifiers. Ensure no encoding failures.
4. **Boundary values** — Test at exact thresholds (15/16 for warning, 30/31 for rejection, 0.0/100.0 for scores).
5. **Extra/unexpected input** — Real YAML files have extra keys from templates. Ensure they don't cause errors and don't leak into normalized output.
6. **Ordering preservation** — Lists (ACs, test cases) must maintain input order in output.
7. **Null/None** — YAML explicit `null` vs. absent key. Both must be handled.
8. **Adversarial config** — Same model for generator+reviewer defeats purpose. Warn.
9. **File encoding** — BOM markers from Windows editors. Handle gracefully.
10. **Lifecycle states** — Persistent artifacts (RTM entries) need all status values exercised.

### When to apply
- After every `T*` task passes its initial green phase
- Before committing the task
- Focus on scenarios that "happen in real teams" not just structural correctness

### Where to apply (scope rule)
Real-world gap tests belong at **system boundaries only**:
1. `input_loader.py` — user-supplied YAML ✓
2. `adversarial_reviewer.py` — LLM response parsing (Phase 3)
3. `cli.py` — command-line arguments (Phase 4)

Internal modules (rtm_builder, rtm_scorer, renderer, etc.) receive validated data from boundary layers. They get structural TDD tests only — no redundant unicode/encoding/type-coercion tests.

### Anti-pattern
- Don't add tests for impossible states (e.g., testing that a dataclass field doesn't accept `None` when the type annotation is `str` — Python doesn't enforce this at runtime anyway)
- Focus on user-facing inputs at system boundaries, not internal-only data flows

## Per-Task Completion Workflow (Established T5/T5b)

After TDD green + gap review, each task goes through this full cycle before commit:

### 1. TDD (red → green → refactor)
- Write failing tests, implement, clean up

### 2. Adversarial review (subagent)
- Different "perspective" reviews for correctness, contract alignment, missing tests, API design
- Plan fixes from findings, implement, validate

### 3. User-perspective review
- Think about how a real user would interact with this module through the pipeline/CLI
- Focus on **workflow scenarios**: multi-sprint accumulation, story rollover, re-runs, partial updates
- Ask: "What would a QE lead do with this over 3 months of sprints?"
- Internal modules: focus on data flow scenarios (what upstream sends, what downstream expects)
- Boundary modules: also add real-world edge cases (encoding, types, whitespace)

### 4. Security/logic review
- OWASP-relevant checks: injection, deserialization, path traversal, DoS
- Reference safety: mutable state exposure, shared references between raw/normalized
- Schema versioning: reject unknown versions on persistent file load
- Atomic I/O: temp file + replace pattern for writes
- Resource limits: file size caps, entry count caps

### 5. Simplify
- After all fixes are applied, do a simplification pass
- Ask: "Can a junior engineer read this function in 30 seconds?"
- Flatten unnecessary nesting (early returns over deep if/else)
- Remove dead code, unused imports, commented-out blocks
- Collapse one-use helpers back inline if they obscure flow
- Prefer plain data over clever abstractions
- If a function is >20 lines, consider whether it's doing two things

### 6. Deferred issues tracking
- Issues identified but not fixed go to `claude-memory/notes.md` with severity, reason, and target version
- Nothing gets silently ignored — every finding is recorded or fixed

### Commit only after all 6 steps complete for the task.
