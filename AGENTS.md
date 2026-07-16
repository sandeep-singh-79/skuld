# AGENTS.md - Workspace Instructions

The authoritative working context for this repository is maintained in:

- `claude-memory/memory.md`
- `claude-memory/insights.md`
- `claude-memory/notes.md`
- `plan.md`

Read these files before proceeding.

## Session Start Checklist

### Step 1 — Load program-level memory (workspace root)
1. Read `../AGENTS.md` (workspace root)
2. Read `../claude-memory/memory.md`
3. Read `../claude-memory/insights.md`
4. Read `../claude-memory/notes.md`
5. Read `../plan.md`

### Step 2 — Load repo-level memory (this repo)
6. Read `AGENTS.md` (this file)
7. Read `claude-memory/memory.md`
8. Read `claude-memory/insights.md`
9. Read `claude-memory/notes.md`
10. Read `plan.md`

### Step 3 — Confirm state
11. Confirm the active milestone, next action, and any blockers from both layers

> Both layers must be loaded. The program layer carries portfolio strategy, cross-system decisions, and repositioning thesis. The repo layer carries active story, test generation pipeline, output contract, and implementation state.

## Working Rules

- This repo is the capability-specific workspace for `skuld` (AI-powered test case generator).
- Keep this repo's memory focused on this capability.
- Use the top-level `Agentic Upskilling` memory layer for cross-program strategy and portfolio decisions.
- Update memory continuously during the session, not only at the end.
- Follow KISS: keep code simple and direct.
- Follow DRY: remove duplication when it becomes real and recurring.
- Follow YAGNI: do not build speculative flexibility ahead of current validated need.
- Follow SOLID where it helps clarity, testability, and change safety; do not force abstraction for its own sake.
- Prefer reuse and extension of existing code before introducing new modules or abstractions.
- Write new code only when it is genuinely required by the current slice or validation need.
- All code must be tested before it is marked complete.
- Always report test pass/fail results and coverage details for code that was tested.
- Follow TDD in the standard order: red → green → refactor.
  - Red: write the failing test first.
  - Green: write the simplest code that passes. No premature abstraction.
  - Refactor: remove duplication, improve clarity, introduce design patterns only when the existing code complexity warrants them. Patterns are a refactoring tool, not a starting point.
