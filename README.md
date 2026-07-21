# Skuld

> *"In Norse myth, Skuld is the Norn who weaves what should become. In QE, acceptance criteria define what must be true — Skuld ensures every 'should' gets a test."*

AI-powered test case generator with adversarial cross-model review, RTM-based deterministic scoring, and confidence assessment.

## What It Does

Given a user story and structured acceptance criteria, Skuld:

1. **Generates** comprehensive test cases (functional, negative, edge-case)
2. **Reviews** them adversarially using a different LLM model
3. **Refines** the test suite based on review feedback
4. **Scores** coverage deterministically via a Requirements Traceability Matrix (RTM)
5. **Reports** a confidence score with full traceability

## Pipeline Position

```
PRD/Story → [QEStrategyForge] → Strategy
Strategy + ACs → [Skuld] → Test Cases + RTM + Confidence Score
Test results → [SuiteCompass] → Optimised Suite
Release context → [ReleaseRadar] → Risk Score
```

## Installation

```bash
git clone git@github.com:sandeep-singh-79/Skuld.git
cd Skuld
pip install -e ".[dev]"
```

Verify:

```bash
skuld --help
```

## Quick Start

```bash
# Generate test cases from a story YAML (dry-run — no API keys needed)
skuld generate benchmarks/login-mfa.input.yaml --dry-run

# Score an existing test case set
skuld score test_cases.json --format markdown

# View RTM coverage summary
skuld rtm report --rtm-file rtm.yaml

# Run a benchmark scenario
skuld benchmark benchmarks/login-mfa.input.yaml benchmarks/login-mfa.assertions.yaml --dry-run
```

For full command reference, worked examples, and input/output formats see:
- [docs/USAGE-GUIDE.md](docs/USAGE-GUIDE.md)
- [docs/V1-INPUT-TEMPLATE.md](docs/V1-INPUT-TEMPLATE.md)
- [docs/V1-OUTPUT-TEMPLATE.md](docs/V1-OUTPUT-TEMPLATE.md)
- [docs/LEARNING-GUIDE.md](docs/LEARNING-GUIDE.md)

## Release Status

- Current release line: 0.1.x
- Current version: 0.1.0
- Runtime behavior currently uses FakeLLM for dry-run style pipeline execution.
- Real provider integrations are planned for a 0.2.x milestone.

Release notes and version history: [CHANGELOG.md](CHANGELOG.md)

## Scoring Model

```
Confidence = (70% × RTM Score) + (30% × Adversarial Review Score)
```

| RTM Component | What it measures |
|---|---|
| AC coverage (0.30) | Every AC has ≥1 functional test |
| Negative coverage (0.25) | Every AC has ≥1 negative test |
| Edge-case coverage (0.20) | Every AC has ≥1 edge-case test |
| Type distribution (0.15) | Functional/negative/edge-case ratio |
| Orphan penalty (0.10) | Tests not mapped to any AC (proportional) |

**Confidence tiers:** ≥80 = high · ≥50 = medium · <50 = low

## License

MIT
