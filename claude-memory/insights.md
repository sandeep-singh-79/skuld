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
