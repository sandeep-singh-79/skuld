# Skuld Benchmarks

Benchmark scenarios for validating Skuld's test case generation pipeline.

Each scenario consists of:
- `{scenario-name}.input.yaml` — the story + ACs input payload
- `{scenario-name}.assertions.yaml` — the validation contract for expected output

## Running Benchmarks

```bash
skuld benchmark benchmarks/
```
