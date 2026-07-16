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

## Quick Start

```bash
pip install -e ".[dev]"
skuld generate story_input.yaml
skuld benchmark benchmarks/
```

## Scoring Model

```
Confidence = (70% × RTM Score) + (30% × Adversarial Review Score)
```

- **RTM Score** (deterministic): AC coverage, negative coverage, edge-case coverage, orphan tests, type distribution
- **Adversarial Score** (qualitative): assertion strength, scenario realism, edge-case quality

## License

MIT
