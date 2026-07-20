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

### Execution Rule (Established T11)
Each step MUST be a separate subagent invocation — never combined into one call. This ensures:
- Each step's output is independently verifiable
- No self-reporting ("I did all 6 steps") — each is visible in the conversation
- Gaps caught by verification (T11 missed 5 items when steps were combined)

**Sequence per task:**
1. Subagent 1: TDD implementation (red → green)
2. Subagent 2: Adversarial review (finds bugs/gaps)
3. Opus plans fixes from adversarial findings
4. Subagent 3: Implement fixes
5. Subagent 4: User-perspective + Security review
6. Opus plans fixes from findings
7. Subagent 5: Implement fixes + simplify
8. Record deferred items → commit

## Inherited from Sibling Agents (Phase 4 onwards)

1. **Documentation ships with code.** If a task adds a CLI flag, workflow, or schema change — the affected doc (README, --help text) is updated in the same commit. Deferring docs creates knowledge debt. *(from IRO #18)*

2. **Help text, implementation, and tests form a contract triangle.** All three must agree. Stale help text that describes removed/changed behaviour misleads users. When adding a flag: write help string + implementation + test in the same commit. *(from IRO #21)*

3. **Pre-increment branch review is a mandatory gate.** Before starting the next phase/increment, review the current branch diff — implementation, tests, docs, governance. Produce written findings. Only start new work when findings are resolved or explicitly deferred. *(from IRO #25)*

4. **Repo-local temp paths, never OS temp dirs.** Use `tests/.tmp/` under project root (gitignored). `tempfile.gettempdir()` is fragile in sandboxed/CI environments. *(from IRO #9)*

5. **Integration tests must assert numerical outcomes, not just "exit 0 + heading present."** When a benchmark/test validates scoring, it must assert specific score ranges or values — "passes without error" is not a meaningful quality gate for scoring correctness. *(from ReleaseRadar)*

6. **Coverage ≥90% is a per-module gate, not an aggregate.** A 95% project average can hide an 0%-covered new module. Measure and enforce per-module after each task. *(from IRO #20)*

7. **Behaviour-change benchmarks must prove the recommendation shifts in both directions.** Include at least one benchmark that produces high confidence AND one that produces low confidence. All-passing scenarios don't prove the system can detect bad input. *(from IRO #24)*

## Learnings from Pre-Increment Review (2026-07-20, GPT-5.4 adversarial)

8. **Domain models must carry all metadata that downstream logic needs for correctness decisions.** When response metadata (like `finish_reason`) exists in the provider contract but is absent from the domain model, information is destroyed at the adapter boundary. A "lossy boundary" means downstream code cannot distinguish a complete response from a truncated one. Rule: if a correctness decision depends on a field, the domain model must propagate it.

9. **Placeholder implementations that don't fail fast create confusing errors downstream.** A TODO comment is not a safety net. If a code path isn't implemented, it must raise `NotImplementedError` at the boundary — not proceed with fake data that causes a different, misleading failure three layers deeper. Rule: every non-implemented branch must be guarded by an explicit runtime error with an actionable message.

10. **Config values that are loaded but never consumed are silent contract violations (dead config).** When the input schema documents a field and the loader preserves it, but the consuming function ignores it in favour of its own default, users will set the value and get no effect. Rule: trace data flow from input schema → loader → consumer during review. Every config field must either be consumed or explicitly documented as "not yet wired".

11. **When correctness checks live in a wrapper, provider wiring must preserve that wrapper.** The 2026-07-20 truncation fix is enforced by `BudgetedLLMClient`, not by raw provider clients. That is safe only if every real-provider path is wrapped before the pipeline consumes it. Rule for T14+: either keep all providers behind `BudgetedLLMClient` or duplicate the `finish_reason == "stop"` enforcement at each provider boundary, then test generator/reviewer/refinement truncation on the real wiring path.
