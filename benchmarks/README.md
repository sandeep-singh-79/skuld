# Skuld Benchmarks

Benchmark scenarios for validating Skuld's test case generation pipeline.

Each scenario consists of:
- `{scenario-name}.input.yaml` — the story + ACs input payload
- `{scenario-name}.assertions.yaml` — the validation contract for expected output

## Running Benchmarks

Each benchmark is run as a file pair via the CLI:

```bash
skuld benchmark benchmarks/login-mfa.input.yaml benchmarks/login-mfa.assertions.yaml --dry-run
skuld benchmark benchmarks/ecommerce-checkout.input.yaml benchmarks/ecommerce-checkout.assertions.yaml --dry-run
skuld benchmark benchmarks/incomplete-story.input.yaml benchmarks/incomplete-story.assertions.yaml --dry-run
```

All benchmarks use `--dry-run` (FakeLLMClient) by default — deterministic, free, no API keys required.

## Benchmark Design

These benchmarks validate **deterministic pipeline wiring**, not generation quality. With `--dry-run`, the FakeLLMClient generates a fixed test suite per AC ID. The assertions verify that the full pipeline (input loading, comment filtering, generation, review, RTM scoring, rendering) executes without error and produces a correctly-shaped report.

Scenario-sensitive benchmarks that validate generation quality, reviewer behavior, or HITL contract enforcement require real provider responses or scenario-specific fake fixtures and are deferred to a later phase.

## Scenarios

| Scenario | ACs | Comments | Domain Context | Purpose |
|----------|-----|----------|----------------|---------|
| `login-mfa` | 4 | Yes | Yes (fintech/PCI-DSS) | Standard shape with comments and domain |
| `ecommerce-checkout` | 8 | Yes | Yes (retail) | Scale — large AC count |
| `incomplete-story` | 1 | No | No | Minimal input, graceful handling |
