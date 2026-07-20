"""T15: Benchmark scenario tests.

Validates that the skuld pipeline produces correct output for each benchmark
scenario using the CLI benchmark command with --dry-run (FakeLLMClient).
"""
from __future__ import annotations

import pathlib

import pytest
from click.testing import CliRunner

from skuld.cli import main

BENCHMARKS_DIR = pathlib.Path(__file__).resolve().parent.parent / "benchmarks"


@pytest.fixture
def runner():
    return CliRunner()


class TestBenchmarkScenarios:
    """Each benchmark scenario must pass its assertions via the CLI."""

    def test_login_mfa_passes_assertions(self, runner):
        """Full MFA login scenario — 4 ACs, comments, all assertion types."""
        result = runner.invoke(main, [
            "benchmark",
            str(BENCHMARKS_DIR / "login-mfa.input.yaml"),
            str(BENCHMARKS_DIR / "login-mfa.assertions.yaml"),
            "--dry-run",
        ])
        assert result.exit_code == 0, f"Expected pass, got:\n{result.output}"
        assert "BENCHMARK PASSED" in result.output

    def test_ecommerce_checkout_passes_assertions(self, runner):
        """Scale scenario — 8 ACs, comments, story ID in output."""
        result = runner.invoke(main, [
            "benchmark",
            str(BENCHMARKS_DIR / "ecommerce-checkout.input.yaml"),
            str(BENCHMARKS_DIR / "ecommerce-checkout.assertions.yaml"),
            "--dry-run",
        ])
        assert result.exit_code == 0, f"Expected pass, got:\n{result.output}"
        assert "BENCHMARK PASSED" in result.output

    def test_incomplete_story_passes_assertions(self, runner):
        """Minimal input — 1 AC, no comments/domain, graceful handling."""
        result = runner.invoke(main, [
            "benchmark",
            str(BENCHMARKS_DIR / "incomplete-story.input.yaml"),
            str(BENCHMARKS_DIR / "incomplete-story.assertions.yaml"),
            "--dry-run",
        ])
        assert result.exit_code == 0, f"Expected pass, got:\n{result.output}"
        assert "BENCHMARK PASSED" in result.output


class TestBenchmarkFailures:
    """Benchmark failure modes produce clear diagnostics."""

    def test_benchmark_reports_assertion_failures(self, runner, tmp_path):
        """Bad assertions against a valid scenario → exit 1 with failure report."""
        bad_assertions = tmp_path / "bad.yaml"
        bad_assertions.write_text(
            "must_include_substrings:\n"
            '  - "THIS HEADING DOES NOT EXIST"\n',
            encoding="utf-8",
        )
        result = runner.invoke(main, [
            "benchmark",
            str(BENCHMARKS_DIR / "login-mfa.input.yaml"),
            str(bad_assertions),
            "--dry-run",
        ])
        assert result.exit_code == 1
        assert "BENCHMARK FAILED" in result.output
        assert "THIS HEADING DOES NOT EXIST" in result.output

    def test_benchmark_nonexistent_input_file(self, runner):
        """Missing input file → Click error (exit 2)."""
        result = runner.invoke(main, [
            "benchmark",
            "nonexistent-input.yaml",
            str(BENCHMARKS_DIR / "login-mfa.assertions.yaml"),
            "--dry-run",
        ])
        assert result.exit_code == 2
