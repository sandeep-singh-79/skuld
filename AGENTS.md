# AGENTS.md - Skuld Repository Instructions

**Inherits from:** `../AGENTS.md` (workspace root) — universal workflow, design discipline, and review protocol.

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

**Universal rules** (design discipline, TDD, commit discipline) are defined in `../.vscode/prompts/design-discipline.instructions.md` and `../.vscode/prompts/tdd-implementation.prompt.md`. Do not duplicate here.

**Repo-specific rules:**
- This repo is the capability-specific workspace for `skuld` (AI-powered test case generator).
- Keep this repo's memory focused on this capability.
- Use the top-level `Agentic Upskilling` memory layer for cross-program strategy and portfolio decisions.
- **Reusability:** before writing a new helper, check the reusability index in `docs/REUSE-INDEX.md`. If a utility already exists (in this repo or siblings), use it. After creating a reusable utility, add it to the index.
- **Extraction trigger:** when 3+ repos contain near-identical code for the same purpose, flag it for extraction to a shared base package. Track in top-level `claude-memory/notes.md`.

## Model Orchestration

**Defined in:** `../.vscode/prompts/orchestrated-workflow.prompt.md` (workspace root — single source of truth).

Read that file for the full 9-step workflow. Summary:
1. Plan (Opus) → 2. Implement (Sonnet) → 3. Adversarial Review (GPT-5.4, 3 lenses) → 4. Fix Loop → 5. Simplify (Opus) → 6. Deferred Issues → 7. Present → 8. User Review → 9. Commit

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
