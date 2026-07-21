# Changelog

All notable changes to this project will be documented in this file.

This project follows Semantic Versioning.

## [0.1.0] - 2026-07-21

Initial milestone release for the Skuld pipeline foundation.

### Added
- CLI commands for generation, scoring, RTM workflows, and benchmark validation.
- Deterministic benchmark scenarios and assertion contracts.
- Coverage hardening and degraded-scenario integration tests.
- Usage and learning documentation, including input/output templates.

### Quality Gates
- 516 tests passing.
- Coverage gate enforced at 90 percent minimum.
- Overall coverage approximately 96 percent at release time.

### Known Scope (Important)
- LLM behavior is currently simulated via FakeLLM in dry-run style workflows.
- Real provider integrations are intentionally deferred to the next milestone.

### Versioning Intent
- Next planned minor release: 0.2.0 for real provider integration and related wiring.
- 1.0.0 will be reserved for a stable production-ready contract and provider path.
