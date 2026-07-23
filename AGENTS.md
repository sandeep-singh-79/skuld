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
- **Design pattern gate:** introduce a pattern ONLY when (a) the code already exists and is getting complex, AND (b) you can name the specific problem the pattern solves. If you can't name the problem, you don't need the pattern.
- **Reusability:** before writing a new helper, check the reusability index in `docs/REUSE-INDEX.md`. If a utility already exists (in this repo or siblings), use it. After creating a reusable utility, add it to the index.
- **Extraction trigger:** when 3+ repos contain near-identical code for the same purpose, flag it for extraction to a shared base package. Track in top-level `claude-memory/notes.md`.
- **Commit discipline:** one commit per task/functionality (max 2). All workloop steps (TDD + adversarial + fixes + simplify) land in a single commit. Squash if intermediate commits were made.
- All code must be tested before it is marked complete.
- Always report test pass/fail results and coverage details for code that was tested.
- Follow TDD in the standard order: red → green → refactor.
  - Red: write the failing test first.
  - Green: write the simplest code that passes. No premature abstraction.
  - Refactor: remove duplication, improve clarity, introduce design patterns only when the existing code complexity warrants them. Patterns are a refactoring tool, not a starting point.
- **After green, before commit: perform the completion workflow using the model orchestration below.**

## Model Orchestration

| Role | Model | Responsibility |
|------|-------|----------------|
| **Orchestrator + Planner** | Opus | Plan each item, define test specs, triage findings, gate quality |
| **Implementor** | Sonnet (subagent) | Write tests (RED), write code (GREEN), refactor, fix findings |
| **Adversarial Reviewer** | GPT-5.4 (subagent) | Find bugs, contract violations, security issues, design gaps |

### Workflow per work item (Opus orchestrates):

1. **Plan** (Opus): Define scope, test specifications, acceptance criteria
2. **Implement** (Sonnet subagent): TDD — failing tests → implementation → refactor
3. **Adversarial Review** (GPT-5.4 subagent): Review the diff covering ALL of:
   - Bugs, contract violations, design gaps
   - Security/logic (OWASP, schema versioning, I/O safety, references)
   - User-perspective (workflow scenarios a real QE lead would trigger)
4. **Fix Loop**: If issues found →
   - Opus triages findings (accept / defer)
   - Sonnet fixes accepted findings
   - GPT-5.4 re-reviews until clean (full scope again, not just fixes)
5. **Simplify** (Opus): Flatten nesting, remove dead code, ask "can a junior read this in 30 seconds?"
6. **Deferred issues** (Opus): Unresolved/deferred findings → `claude-memory/notes.md` with source and rationale
7. **Present to user**: Summary of implementation, tests passing, review outcome, deferred items
8. **Manual adversarial review** (user): User reviews and may request further changes
9. **Commit**: Only after user approves — single commit per work item

### Rules:
- NO commit lands until the user completes their manual adversarial review
- Adversarial review loops until clean — never skip re-review after fixes
- The adversarial review prompt must explicitly request all three lenses (bugs, security, user-perspective)
- Simplification happens AFTER the review loop is clean, not before
- Deferred findings go to `claude-memory/notes.md` with source, severity, and rationale
- One commit per work item (all TDD + fixes + simplification in one commit)
- Each subagent call is separate — never combine planning, implementation, and review in one invocation

## Architecture Guardrails

### Deterministic / LLM Boundary
- `rtm_builder.py`, `rtm_scorer.py`, and `confidence_scorer.py` must NEVER import or call LLM code.
- Deterministic modules must be fully testable without mocks, network, or API keys.
- The deterministic layer must pass validation before the LLM layer is invoked during a pipeline run.

### LLM Response Handling
- All LLM responses must be parsed into structured `TestCase` / `ReviewFeedback` objects before use.
- Unparseable or truncated responses are generation failures — do not score partial output.
- Check `finish_reason` (or equivalent) on every LLM response; reject truncated completions.

### Cross-Model Communication
- Generator and Reviewer communicate via a structured intermediate format (`ReviewFeedback` schema), not free-form prose.
- Each LLM call has a single responsibility: Generator ONLY generates; Reviewer ONLY reviews. Never combine.

### Input Safety
- User-supplied story/AC content is fenced with clear delimiters when injected into prompts.
- Validate input structure before prompt injection — reject malformed YAML at the input_loader boundary.
- API keys via environment variables only (`SKULD_ANTHROPIC_KEY`, `SKULD_OPENAI_KEY`); never in code or config files.

### Cost Control
- Enforce `max_tokens_per_run` budget (default: 32K total across both LLM passes).
- Warn at >15 ACs in input; reject at >30 (configurable via `config.max_acceptance_criteria`).

### Scope Fence (MVP)
- MVP produces test case specifications in tabular format. No automation code generation.
- Coverage types: functional, negative, edge-case only. No NFR, no accessibility.
- Single refinement pass only. No iterative loop.
