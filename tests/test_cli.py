"""Tests for Skuld CLI (T14)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from skuld.cli import main


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def valid_input_file(tmp_path):
    """Create a minimal valid input YAML file."""
    data = {
        "story": {"id": "S-1", "title": "Login", "description": "User login flow"},
        "acceptance_criteria": [
            {"id": "AC-1", "description": "User can log in with email and password"},
        ],
        "config": {
            "generator_model": "claude-sonnet-4-20250514",
            "reviewer_model": "gpt-4o",
        },
    }
    path = tmp_path / "input.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return str(path)


@pytest.fixture
def multi_ac_input_file(tmp_path):
    """Input with multiple ACs for richer scoring."""
    data = {
        "story": {"id": "S-2", "title": "Checkout", "description": "E-commerce checkout"},
        "acceptance_criteria": [
            {"id": "AC-1", "description": "Cart total calculated", "criticality": "high"},
            {"id": "AC-2", "description": "Payment processed", "criticality": "high"},
            {"id": "AC-3", "description": "Error on invalid card", "criticality": "medium"},
        ],
        "config": {
            "generator_model": "claude-sonnet-4-20250514",
            "reviewer_model": "gpt-4o",
        },
    }
    path = tmp_path / "checkout.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# skuld generate
# ---------------------------------------------------------------------------

class TestGenerate:
    def test_generate_valid_input(self, runner, valid_input_file):
        result = runner.invoke(main, ["generate", valid_input_file, "--dry-run"])
        assert result.exit_code == 0
        assert "## Story Context" in result.output or "test_cases" in result.output

    def test_generate_output_to_file(self, runner, valid_input_file, tmp_path):
        out = str(tmp_path / "out.md")
        result = runner.invoke(main, ["generate", valid_input_file, "--dry-run", "--output", out])
        assert result.exit_code == 0
        assert Path(out).exists()
        content = Path(out).read_text(encoding="utf-8")
        assert "## Story Context" in content or "test_cases" in content

    def test_generate_invalid_input(self, runner, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("not_valid: true", encoding="utf-8")
        result = runner.invoke(main, ["generate", str(bad), "--dry-run"])
        assert result.exit_code == 2

    def test_generate_nonexistent_file(self, runner):
        result = runner.invoke(main, ["generate", "/no/such/file.yaml", "--dry-run"])
        assert result.exit_code == 2

    def test_generate_with_rtm_file(self, runner, valid_input_file, tmp_path):
        rtm = str(tmp_path / "rtm.yaml")
        result = runner.invoke(main, ["generate", valid_input_file, "--dry-run", "--rtm-file", rtm])
        assert result.exit_code == 0
        assert Path(rtm).exists()

    def test_generate_dry_run(self, runner, valid_input_file):
        """--dry-run works without API keys."""
        env = {k: v for k, v in os.environ.items() if "SKULD" not in k}
        result = runner.invoke(main, ["generate", valid_input_file, "--dry-run"], env=env)
        assert result.exit_code == 0

    def test_generate_json_format(self, runner, valid_input_file):
        result = runner.invoke(main, ["generate", valid_input_file, "--dry-run", "--format", "json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "test_cases" in parsed

    def test_generate_invalid_format(self, runner, valid_input_file):
        result = runner.invoke(main, ["generate", valid_input_file, "--dry-run", "--format", "xml"])
        assert result.exit_code == 2  # Click rejects invalid choice


# ---------------------------------------------------------------------------
# skuld score
# ---------------------------------------------------------------------------

class TestScore:
    def test_score_command(self, runner, valid_input_file):
        """Score runs deterministic scoring on pipeline output."""
        # First generate JSON to score
        gen_result = runner.invoke(main, ["generate", valid_input_file, "--dry-run", "--format", "json"])
        assert gen_result.exit_code == 0

        # Write to file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write(gen_result.output)
            score_file = f.name
        try:
            result = runner.invoke(main, ["score", score_file])
            assert result.exit_code == 0
            # Should show score/tier info
            assert "composite" in result.output.lower() or "tier" in result.output.lower()
        finally:
            os.unlink(score_file)


# ---------------------------------------------------------------------------
# skuld rtm
# ---------------------------------------------------------------------------

class TestRTM:
    def _create_rtm(self, runner, valid_input_file, tmp_path):
        """Helper: generate with --rtm-file to create an RTM."""
        rtm = str(tmp_path / "rtm.yaml")
        runner.invoke(main, ["generate", valid_input_file, "--dry-run", "--rtm-file", rtm])
        return rtm

    def test_rtm_report(self, runner, valid_input_file, tmp_path):
        rtm = self._create_rtm(runner, valid_input_file, tmp_path)
        result = runner.invoke(main, ["rtm", "report", "--rtm-file", rtm])
        assert result.exit_code == 0
        assert "total" in result.output.lower() or "entries" in result.output.lower()

    def test_rtm_gaps(self, runner, valid_input_file, tmp_path):
        rtm = self._create_rtm(runner, valid_input_file, tmp_path)
        result = runner.invoke(main, ["rtm", "gaps", "--rtm-file", rtm])
        assert result.exit_code == 0

    def test_rtm_update(self, runner, valid_input_file, tmp_path):
        """rtm update merges test cases into RTM."""
        gen_result = runner.invoke(main, ["generate", valid_input_file, "--dry-run", "--format", "json"])
        assert gen_result.exit_code == 0

        json_file = str(tmp_path / "cases.json")
        Path(json_file).write_text(gen_result.output, encoding="utf-8")

        rtm = str(tmp_path / "rtm.yaml")
        result = runner.invoke(main, ["rtm", "update", json_file, "--rtm-file", rtm])
        assert result.exit_code == 0
        assert Path(rtm).exists()

    def test_rtm_history(self, runner, valid_input_file, tmp_path):
        rtm = self._create_rtm(runner, valid_input_file, tmp_path)
        result = runner.invoke(main, ["rtm", "history", "--rtm-file", rtm, "--ac", "AC-1"])
        assert result.exit_code == 0

    def test_rtm_report_missing_file(self, runner, tmp_path):
        result = runner.invoke(main, ["rtm", "report", "--rtm-file", str(tmp_path / "none.yaml")])
        # Should handle gracefully (empty RTM)
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# skuld benchmark
# ---------------------------------------------------------------------------

class TestBenchmark:
    def _create_benchmark_files(self, tmp_path, should_pass=True):
        input_data = {
            "story": {"id": "S-1", "title": "Login", "description": "Login flow"},
            "acceptance_criteria": [
                {"id": "AC-1", "description": "Login works"},
            ],
            "config": {"generator_model": "a", "reviewer_model": "b"},
        }
        input_file = tmp_path / "input.yaml"
        input_file.write_text(yaml.dump(input_data), encoding="utf-8")

        if should_pass:
            assertions = {
                "assertions": [
                    {"type": "contains", "target": "output", "value": "TC-"},
                ]
            }
        else:
            assertions = {
                "assertions": [
                    {"type": "contains", "target": "output", "value": "IMPOSSIBLE_STRING_XYZZY"},
                ]
            }
        assertions_file = tmp_path / "assertions.yaml"
        assertions_file.write_text(yaml.dump(assertions), encoding="utf-8")
        return str(input_file), str(assertions_file)

    def test_benchmark_pass(self, runner, tmp_path):
        input_f, assert_f = self._create_benchmark_files(tmp_path, should_pass=True)
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 0

    def test_benchmark_fail(self, runner, tmp_path):
        input_f, assert_f = self._create_benchmark_files(tmp_path, should_pass=False)
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# General CLI
# ---------------------------------------------------------------------------

class TestCLIGeneral:
    def test_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "generate" in result.output
        assert "score" in result.output
        assert "rtm" in result.output

    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_rtm_path_traversal_rejected(self, runner, valid_input_file, tmp_path):
        """Path traversal in --rtm-file should be rejected."""
        malicious = str(tmp_path / ".." / ".." / "etc" / "evil.yaml")
        result = runner.invoke(main, ["generate", valid_input_file, "--dry-run", "--rtm-file", malicious])
        # Should fail with input error
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# Coverage gap tests — exercise remaining branches
# ---------------------------------------------------------------------------

class TestScoreMarkdown:
    def test_score_markdown_format(self, runner, valid_input_file, tmp_path):
        """Score with --format markdown shows textual summary."""
        gen_result = runner.invoke(main, ["generate", valid_input_file, "--dry-run", "--format", "json"])
        assert gen_result.exit_code == 0
        score_file = str(tmp_path / "cases.json")
        Path(score_file).write_text(gen_result.output, encoding="utf-8")
        result = runner.invoke(main, ["score", score_file, "--format", "markdown"])
        assert result.exit_code == 0
        assert "Composite Score" in result.output
        assert "Tier" in result.output

    def test_score_invalid_json(self, runner, tmp_path):
        """Score with invalid JSON shows error."""
        bad_file = str(tmp_path / "bad.json")
        Path(bad_file).write_text("not json!", encoding="utf-8")
        result = runner.invoke(main, ["score", bad_file])
        assert result.exit_code == 2

    def test_score_empty_test_cases(self, runner, tmp_path):
        """Score with no test_cases array."""
        empty_file = str(tmp_path / "empty.json")
        Path(empty_file).write_text(json.dumps({"test_cases": []}), encoding="utf-8")
        result = runner.invoke(main, ["score", empty_file])
        assert result.exit_code == 2


class TestRTMUpdateErrors:
    def test_rtm_update_invalid_json(self, runner, tmp_path):
        """rtm update with bad JSON shows error."""
        bad = str(tmp_path / "bad.json")
        Path(bad).write_text("nope", encoding="utf-8")
        rtm = str(tmp_path / "rtm.yaml")
        result = runner.invoke(main, ["rtm", "update", bad, "--rtm-file", rtm])
        assert result.exit_code == 2

    def test_rtm_update_empty_cases(self, runner, tmp_path):
        """rtm update with no test_cases."""
        empty = str(tmp_path / "e.json")
        Path(empty).write_text(json.dumps({"test_cases": []}), encoding="utf-8")
        rtm = str(tmp_path / "rtm.yaml")
        result = runner.invoke(main, ["rtm", "update", empty, "--rtm-file", rtm])
        assert result.exit_code == 2


class TestRTMHistoryFound:
    def test_rtm_history_no_entries(self, runner, valid_input_file, tmp_path):
        """History for non-existent AC returns no entries message."""
        rtm = str(tmp_path / "rtm.yaml")
        runner.invoke(main, ["generate", valid_input_file, "--dry-run", "--rtm-file", rtm])
        result = runner.invoke(main, ["rtm", "history", "--rtm-file", rtm, "--ac", "AC-999"])
        assert result.exit_code == 0
        assert "No entries found" in result.output

    def test_rtm_history_with_entries(self, runner, valid_input_file, tmp_path):
        """History for existing AC shows entry details."""
        rtm = str(tmp_path / "rtm.yaml")
        runner.invoke(main, ["generate", valid_input_file, "--dry-run", "--rtm-file", rtm])
        result = runner.invoke(main, ["rtm", "history", "--rtm-file", rtm, "--ac", "AC-1"])
        assert result.exit_code == 0
        assert "History for AC-1" in result.output


class TestBenchmarkAssertionTypes:
    def _make_files(self, tmp_path, assertions):
        input_data = {
            "story": {"id": "S-1", "title": "T", "description": "D"},
            "acceptance_criteria": [{"id": "AC-1", "description": "D"}],
            "config": {"generator_model": "a", "reviewer_model": "b"},
        }
        input_f = str(tmp_path / "in.yaml")
        Path(input_f).write_text(yaml.dump(input_data), encoding="utf-8")
        assert_f = str(tmp_path / "assert.yaml")
        Path(assert_f).write_text(yaml.dump({"assertions": assertions}), encoding="utf-8")
        return input_f, assert_f

    def test_not_contains_pass(self, runner, tmp_path):
        inf, af = self._make_files(tmp_path, [{"type": "not_contains", "value": "ZZZYYYXXX"}])
        result = runner.invoke(main, ["benchmark", inf, af, "--dry-run"])
        assert result.exit_code == 0

    def test_not_contains_fail(self, runner, tmp_path):
        inf, af = self._make_files(tmp_path, [{"type": "not_contains", "value": "TC-"}])
        result = runner.invoke(main, ["benchmark", inf, af, "--dry-run"])
        assert result.exit_code == 1

    def test_min_length_pass(self, runner, tmp_path):
        inf, af = self._make_files(tmp_path, [{"type": "min_length", "value": "10"}])
        result = runner.invoke(main, ["benchmark", inf, af, "--dry-run"])
        assert result.exit_code == 0

    def test_min_length_fail(self, runner, tmp_path):
        inf, af = self._make_files(tmp_path, [{"type": "min_length", "value": "999999"}])
        result = runner.invoke(main, ["benchmark", inf, af, "--dry-run"])
        assert result.exit_code == 1

    def test_unknown_assertion_type(self, runner, tmp_path):
        inf, af = self._make_files(tmp_path, [{"type": "regex_match", "value": ".*"}])
        result = runner.invoke(main, ["benchmark", inf, af, "--dry-run"])
        assert result.exit_code == 2
        assert "unsupported assertion type" in result.output


class TestGenerateWarnings:
    def test_same_model_warning(self, runner, tmp_path):
        """Same generator/reviewer model emits warning."""
        data = {
            "story": {"id": "S-1", "title": "T", "description": "D"},
            "acceptance_criteria": [{"id": "AC-1", "description": "D"}],
            "config": {"generator_model": "same", "reviewer_model": "same"},
        }
        f = str(tmp_path / "in.yaml")
        Path(f).write_text(yaml.dump(data), encoding="utf-8")
        result = runner.invoke(main, ["generate", f, "--dry-run"])
        assert result.exit_code == 0
        # Warning emitted via click.echo(err=True) or in output
        assert "same" in result.output.lower() or "warning" in result.output.lower()


class TestScoreWithExplicitACs:
    def test_score_with_acs_in_file(self, runner, tmp_path):
        """Score file that includes acceptance_criteria uses them."""
        data = {
            "test_cases": [
                {"id": "TC-1", "story_id": "S-1", "ac_ids": ["AC-1"],
                 "test_type": "functional", "priority": "P1",
                 "preconditions": "", "steps": ["s1"], "expected_result": "ok"},
            ],
            "acceptance_criteria": [
                {"id": "AC-1", "description": "Login works", "criticality": "high"},
            ],
        }
        f = str(tmp_path / "score.json")
        Path(f).write_text(json.dumps(data), encoding="utf-8")
        result = runner.invoke(main, ["score", f, "--format", "markdown"])
        assert result.exit_code == 0
        assert "Composite Score" in result.output

    def test_score_markdown_with_gaps(self, runner, tmp_path):
        """Score shows gaps section when types are missing."""
        data = {
            "test_cases": [
                {"id": "TC-1", "story_id": "S-1", "ac_ids": ["AC-1"],
                 "test_type": "functional", "priority": "P1",
                 "preconditions": "", "steps": ["s1"], "expected_result": "ok"},
            ],
            "acceptance_criteria": [
                {"id": "AC-1", "description": "D", "criticality": "high"},
            ],
        }
        f = str(tmp_path / "score.json")
        Path(f).write_text(json.dumps(data), encoding="utf-8")
        result = runner.invoke(main, ["score", f, "--format", "markdown"])
        assert result.exit_code == 0
        # AC-1 only has functional, missing negative + edge-case
        assert "Gaps" in result.output
        assert "AC-1" in result.output
        assert "negative" in result.output or "edge-case" in result.output


class TestBenchmarkPipelineFailure:
    def test_benchmark_bad_input(self, runner, tmp_path):
        """Benchmark with invalid input file fails gracefully."""
        input_f = str(tmp_path / "bad.yaml")
        Path(input_f).write_text("invalid: true", encoding="utf-8")
        assert_f = str(tmp_path / "assert.yaml")
        Path(assert_f).write_text(yaml.dump({"assertions": []}), encoding="utf-8")
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 2


class TestRTMGapsDetailed:
    def test_rtm_gaps_with_incomplete_coverage(self, runner, tmp_path):
        """Gaps command shows missing types when only functional tests exist."""
        # Manually build an RTM with only functional entries
        rtm_data = {
            "metadata": {"rtm_version": "1.0", "project_id": None},
            "entries": [
                {"ac_id": "AC-1", "test_case_id": "TC-1", "test_type": "functional",
                 "story_id": "S-1", "added_date": "2026-01-01", "added_by_run": "r1", "status": "active"},
            ],
        }
        rtm_f = str(tmp_path / "rtm.yaml")
        Path(rtm_f).write_text(yaml.dump(rtm_data), encoding="utf-8")
        result = runner.invoke(main, ["rtm", "gaps", "--rtm-file", rtm_f])
        assert result.exit_code == 0
        assert "AC-1" in result.output
        assert "negative" in result.output or "edge-case" in result.output


# ---------------------------------------------------------------------------
# Adversarial hardening tests — exercise new error guard paths
# ---------------------------------------------------------------------------

class TestAdversarialHardening:
    def test_score_non_dict_json(self, runner, tmp_path):
        """JSON array instead of object should give clear error."""
        f = str(tmp_path / "arr.json")
        Path(f).write_text('["not", "a", "dict"]', encoding="utf-8")
        result = runner.invoke(main, ["score", f])
        assert result.exit_code == 2
        assert "JSON object" in result.output or "Invalid" in result.output

    def test_score_missing_test_case_id(self, runner, tmp_path):
        """Test case without 'id' key reports malformed data."""
        data = {"test_cases": [{"story_id": "S-1", "ac_ids": ["AC-1"]}]}
        f = str(tmp_path / "noid.json")
        Path(f).write_text(json.dumps(data), encoding="utf-8")
        result = runner.invoke(main, ["score", f])
        assert result.exit_code == 2
        assert "Malformed" in result.output or "missing" in result.output.lower()

    def test_score_missing_ac_id(self, runner, tmp_path):
        """AC without 'id' key reports malformed data."""
        data = {
            "test_cases": [{"id": "TC-1", "ac_ids": ["AC-1"], "test_type": "functional",
                            "priority": "P1", "preconditions": "", "steps": [], "expected_result": "ok"}],
            "acceptance_criteria": [{"description": "no id"}],
        }
        f = str(tmp_path / "noac.json")
        Path(f).write_text(json.dumps(data), encoding="utf-8")
        result = runner.invoke(main, ["score", f])
        assert result.exit_code == 2

    def test_rtm_update_non_dict_json(self, runner, tmp_path):
        """rtm update with JSON array gives clear error."""
        f = str(tmp_path / "arr.json")
        Path(f).write_text("[1,2,3]", encoding="utf-8")
        rtm = str(tmp_path / "rtm.yaml")
        result = runner.invoke(main, ["rtm", "update", f, "--rtm-file", rtm])
        assert result.exit_code == 2

    def test_rtm_update_missing_test_case_id(self, runner, tmp_path):
        """rtm update with missing test case id."""
        data = {"test_cases": [{"story_id": "S-1", "ac_ids": ["AC-1"]}]}
        f = str(tmp_path / "noid.json")
        Path(f).write_text(json.dumps(data), encoding="utf-8")
        rtm = str(tmp_path / "rtm.yaml")
        result = runner.invoke(main, ["rtm", "update", f, "--rtm-file", rtm])
        assert result.exit_code == 2
        assert "Malformed" in result.output

    def test_rtm_load_corrupt_file(self, runner, tmp_path):
        """Corrupt RTM file gives error, not stack trace."""
        rtm = str(tmp_path / "rtm.yaml")
        Path(rtm).write_text("metadata:\n  rtm_version: '99.0'\nentries: []\n", encoding="utf-8")
        result = runner.invoke(main, ["rtm", "report", "--rtm-file", rtm])
        assert result.exit_code == 2
        assert "Error loading RTM" in result.output

    def test_benchmark_min_length_non_numeric(self, runner, tmp_path):
        """min_length with non-numeric value doesn't crash."""
        input_data = {
            "story": {"id": "S-1", "title": "T", "description": "D"},
            "acceptance_criteria": [{"id": "AC-1", "description": "D"}],
            "config": {"generator_model": "a", "reviewer_model": "b"},
        }
        input_f = str(tmp_path / "in.yaml")
        Path(input_f).write_text(yaml.dump(input_data), encoding="utf-8")
        assert_f = str(tmp_path / "assert.yaml")
        Path(assert_f).write_text(yaml.dump({"assertions": [{"type": "min_length", "value": "abc"}]}), encoding="utf-8")
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 2
        assert "must be an integer" in result.output

    def test_output_path_traversal_rejected(self, runner, valid_input_file):
        """--output with '..' is rejected."""
        result = runner.invoke(main, ["generate", valid_input_file, "--dry-run", "--output", "../../../evil.md"])
        assert result.exit_code == 2

    def test_benchmark_empty_assertions_file(self, runner, tmp_path):
        """Empty assertions file is rejected as input error."""
        input_data = {
            "story": {"id": "S-1", "title": "T", "description": "D"},
            "acceptance_criteria": [{"id": "AC-1", "description": "D"}],
            "config": {"generator_model": "a", "reviewer_model": "b"},
        }
        input_f = str(tmp_path / "in.yaml")
        Path(input_f).write_text(yaml.dump(input_data), encoding="utf-8")
        assert_f = str(tmp_path / "empty.yaml")
        Path(assert_f).write_text("", encoding="utf-8")
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 2
        assert "No assertions" in result.output or "No assertions" in (result.output + str(result.exception))


# ---------------------------------------------------------------------------
# Fix F1+F3+F2+F4 — GPT-5.4 adversarial findings
# ---------------------------------------------------------------------------

class TestBenchmarkSpecFormat:
    """Benchmark command supports PHASE-4-SPEC assertion format (F1 fix)."""

    def _make_input(self, tmp_path):
        data = {
            "story": {"id": "S-1", "title": "T", "description": "D"},
            "acceptance_criteria": [{"id": "AC-1", "description": "D"}],
            "config": {"generator_model": "a", "reviewer_model": "b"},
        }
        f = str(tmp_path / "in.yaml")
        Path(f).write_text(yaml.dump(data), encoding="utf-8")
        return f

    def test_benchmark_spec_format_headings_pass(self, runner, tmp_path):
        """Spec-format file with must_include_headings that match → passes."""
        input_f = self._make_input(tmp_path)
        assert_f = str(tmp_path / "assert.yaml")
        Path(assert_f).write_text(
            yaml.dump({"must_include_headings": ["## Story Context"]}), encoding="utf-8"
        )
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 0
        assert "BENCHMARK PASSED" in result.output

    def test_benchmark_spec_format_fail(self, runner, tmp_path):
        """Spec-format file with must_include_headings that don't match → fails."""
        input_f = self._make_input(tmp_path)
        assert_f = str(tmp_path / "assert.yaml")
        Path(assert_f).write_text(
            yaml.dump({"must_include_headings": ["## Completely Nonexistent Section XYZ"]}),
            encoding="utf-8",
        )
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 1

    def test_benchmark_mixed_format(self, runner, tmp_path):
        """Both assertions: and must_include_substrings: are evaluated together."""
        input_f = self._make_input(tmp_path)
        assert_f = str(tmp_path / "assert.yaml")
        # One from each format — both must pass
        Path(assert_f).write_text(
            yaml.dump({
                "assertions": [{"type": "contains", "value": "TC-"}],
                "must_include_substrings": ["Story Context"],
            }),
            encoding="utf-8",
        )
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 0
        assert "BENCHMARK PASSED" in result.output

    def test_benchmark_malformed_assertion_entry(self, runner, tmp_path):
        """Non-dict assertion entry is a malformed benchmark file — exits 2, not 1 (schema error)."""
        input_f = self._make_input(tmp_path)
        assert_f = str(tmp_path / "assert.yaml")
        Path(assert_f).write_text(
            yaml.dump({"assertions": ["not-a-dict"]}), encoding="utf-8"
        )
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 2
        assert "mapping" in result.output or "expected" in result.output.lower()


class TestRTMUpdateShapeValidation:
    """rtm update validates entry shapes before processing (F2 + F4 fix)."""

    def test_rtm_update_non_dict_entries(self, runner, tmp_path):
        """test_cases containing strings (not dicts) exits 2 with clear error."""
        f = str(tmp_path / "bad.json")
        Path(f).write_text(json.dumps({"test_cases": ["not-a-dict"]}), encoding="utf-8")
        rtm = str(tmp_path / "rtm.yaml")
        result = runner.invoke(main, ["rtm", "update", f, "--rtm-file", rtm])
        assert result.exit_code == 2
        assert "Malformed" in result.output


# ---------------------------------------------------------------------------
# Round-2 fixes — R2-1, R2-2, R2-3
# ---------------------------------------------------------------------------

class TestBenchmarkSpecFormatValidation:
    """R2-1: spec-format keys must be lists, not bare strings."""

    def _make_input(self, tmp_path):
        data = {
            "story": {"id": "S-1", "title": "T", "description": "D"},
            "acceptance_criteria": [{"id": "AC-1", "description": "D"}],
            "config": {"generator_model": "a", "reviewer_model": "b"},
        }
        f = str(tmp_path / "in.yaml")
        Path(f).write_text(yaml.dump(data), encoding="utf-8")
        return f

    def test_benchmark_spec_format_string_not_list(self, runner, tmp_path):
        """must_include_headings as a bare string is rejected (exit 2)."""
        input_f = self._make_input(tmp_path)
        assert_f = str(tmp_path / "assert.yaml")
        Path(assert_f).write_text(
            "must_include_headings: '## Test Cases'\n", encoding="utf-8"
        )
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 2
        assert "must be a list" in result.output


class TestACIdsCoercion:
    """R2-2: ac_ids as a bare string is coerced to a single-element list."""

    def test_score_string_ac_ids_coerced(self, runner, tmp_path):
        """score: ac_ids='AC-1' (string) maps to AC-1, not individual characters."""
        data = {
            "test_cases": [
                {
                    "id": "TC-1", "story_id": "S-1",
                    "ac_ids": "AC-1",
                    "test_type": "functional", "priority": "P1",
                    "preconditions": "", "steps": [], "expected_result": "ok",
                }
            ],
            "acceptance_criteria": [{"id": "AC-1", "description": "Login works"}],
        }
        f = str(tmp_path / "cases.json")
        Path(f).write_text(json.dumps(data), encoding="utf-8")
        result = runner.invoke(main, ["score", f, "--format", "markdown"])
        assert result.exit_code == 0
        assert "no test coverage" not in result.output

    def test_rtm_update_string_ac_ids_coerced(self, runner, tmp_path):
        """rtm update: ac_ids='AC-1' (string) writes one entry for AC-1, not 4 chars."""
        from skuld.rtm_store import RTMStore as _RTMStore
        data = {
            "test_cases": [
                {
                    "id": "TC-1", "story_id": "S-1",
                    "ac_ids": "AC-1",
                    "test_type": "functional",
                }
            ]
        }
        f = str(tmp_path / "cases.json")
        Path(f).write_text(json.dumps(data), encoding="utf-8")
        rtm = str(tmp_path / "rtm.yaml")
        result = runner.invoke(main, ["rtm", "update", f, "--rtm-file", rtm])
        assert result.exit_code == 0
        store = _RTMStore.load(rtm)
        ac_ids = [e.ac_id for e in store.entries]
        assert ac_ids == ["AC-1"], f"Expected ['AC-1'], got {ac_ids}"


class TestBenchmarkValueCoercion:
    """R2-3: non-string assertion value is coerced to str (no TypeError crash)."""

    def _make_input(self, tmp_path):
        data = {
            "story": {"id": "S-1", "title": "T", "description": "D"},
            "acceptance_criteria": [{"id": "AC-1", "description": "D"}],
            "config": {"generator_model": "a", "reviewer_model": "b"},
        }
        f = str(tmp_path / "in.yaml")
        Path(f).write_text(yaml.dump(data), encoding="utf-8")
        return f

    def test_benchmark_numeric_value_coerced(self, runner, tmp_path):
        """value: 123 (int from YAML) is now a schema error — 'contains' requires a string value (exit 2)."""
        input_f = self._make_input(tmp_path)
        assert_f = str(tmp_path / "assert.yaml")
        Path(assert_f).write_text(
            yaml.dump({"assertions": [{"type": "contains", "value": 123}]}),
            encoding="utf-8",
        )
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 2
        assert result.exception is None or isinstance(result.exception, SystemExit)
        assert "non-empty string" in result.output


class TestACIdsListElementValidation:
    """R3-1: ac_ids list with non-string elements is rejected, not silently corrupted."""

    def _make_score_file(self, tmp_path, ac_ids_value):
        data = {
            "test_cases": [
                {
                    "id": "TC-1", "story_id": "S-1",
                    "ac_ids": ac_ids_value,
                    "test_type": "functional", "priority": "P1",
                    "preconditions": "", "steps": [], "expected_result": "ok",
                }
            ],
            "acceptance_criteria": [{"id": "AC-1", "description": "D"}],
        }
        f = str(tmp_path / "cases.json")
        Path(f).write_text(json.dumps(data), encoding="utf-8")
        return f

    def test_score_ac_ids_list_with_non_string_rejected(self, runner, tmp_path):
        """score: ac_ids=[123] exits 2 with malformed-input error, not 0 with corrupt coverage."""
        f = self._make_score_file(tmp_path, [123])
        result = runner.invoke(main, ["score", f, "--format", "markdown"])
        assert result.exit_code == 2
        assert result.exception is None or isinstance(result.exception, SystemExit)

    def test_rtm_update_ac_ids_list_with_non_string_rejected(self, runner, tmp_path):
        """rtm update: ac_ids=[123] exits 2 and does not write a corrupted RTM file."""
        data = {"test_cases": [{"id": "TC-1", "story_id": "S-1", "ac_ids": [123], "test_type": "functional"}]}
        f = str(tmp_path / "cases.json")
        Path(f).write_text(json.dumps(data), encoding="utf-8")
        rtm = str(tmp_path / "rtm.yaml")
        result = runner.invoke(main, ["rtm", "update", f, "--rtm-file", rtm])
        assert result.exit_code == 2
        assert not Path(rtm).exists(), "RTM file must not be written on malformed input"


class TestBenchmarkAssertionsFieldNotList:
    """R3-2: simple benchmark assertions field that is a dict is rejected as input error (exit 2)."""

    def _make_input(self, tmp_path):
        data = {
            "story": {"id": "S-1", "title": "T", "description": "D"},
            "acceptance_criteria": [{"id": "AC-1", "description": "D"}],
            "config": {"generator_model": "a", "reviewer_model": "b"},
        }
        f = str(tmp_path / "in.yaml")
        Path(f).write_text(yaml.dump(data), encoding="utf-8")
        return f

    def test_benchmark_assertions_field_not_list(self, runner, tmp_path):
        """assertions: {type: contains, value: 'TC-'} is a dict, not a list — must exit 2."""
        input_f = self._make_input(tmp_path)
        assert_f = str(tmp_path / "assert.yaml")
        Path(assert_f).write_text(
            "assertions:\n  type: contains\n  value: 'TC-'\n", encoding="utf-8"
        )
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 2
        assert "must be a list" in result.output


class TestBlankACIds:
    """R4-2: blank or whitespace-only AC IDs are rejected at the CLI boundary."""

    def _make_score_file(self, tmp_path, ac_ids_value):
        data = {
            "test_cases": [
                {
                    "id": "TC-1", "story_id": "S-1",
                    "ac_ids": ac_ids_value,
                    "test_type": "functional", "priority": "P1",
                    "preconditions": "", "steps": [], "expected_result": "ok",
                }
            ],
            "acceptance_criteria": [{"id": "AC-1", "description": "D"}],
        }
        f = str(tmp_path / "cases.json")
        Path(f).write_text(json.dumps(data), encoding="utf-8")
        return f

    def test_score_blank_ac_id_rejected(self, runner, tmp_path):
        """score: ac_ids=[""] exits 2 — blank entry is not a valid AC ID."""
        f = self._make_score_file(tmp_path, [""])
        result = runner.invoke(main, ["score", f, "--format", "markdown"])
        assert result.exit_code == 2
        assert result.exception is None or isinstance(result.exception, SystemExit)

    def test_score_bare_blank_string_rejected(self, runner, tmp_path):
        """score: ac_ids="   " (bare whitespace string) is coerced to ["   "] then rejected."""
        f = self._make_score_file(tmp_path, "   ")
        result = runner.invoke(main, ["score", f, "--format", "markdown"])
        assert result.exit_code == 2
        assert result.exception is None or isinstance(result.exception, SystemExit)

    def test_rtm_update_whitespace_ac_id_rejected(self, runner, tmp_path):
        """rtm update: ac_ids=["   "] exits 2 and does not write an RTM file."""
        data = {"test_cases": [{"id": "TC-1", "story_id": "S-1", "ac_ids": ["   "], "test_type": "functional"}]}
        f = str(tmp_path / "cases.json")
        Path(f).write_text(json.dumps(data), encoding="utf-8")
        rtm = str(tmp_path / "rtm.yaml")
        result = runner.invoke(main, ["rtm", "update", f, "--rtm-file", rtm])
        assert result.exit_code == 2
        assert not Path(rtm).exists(), "RTM file must not be written on blank AC ID"


class TestBenchmarkAssertionSchemaValidation:
    """R4-1 / R4-3: malformed assertion schema exits 2, not 1."""

    def _make_input(self, tmp_path):
        data = {
            "story": {"id": "S-1", "title": "T", "description": "D"},
            "acceptance_criteria": [{"id": "AC-1", "description": "D"}],
            "config": {"generator_model": "a", "reviewer_model": "b"},
        }
        f = str(tmp_path / "in.yaml")
        Path(f).write_text(yaml.dump(data), encoding="utf-8")
        return f

    def test_benchmark_empty_value_rejected(self, runner, tmp_path):
        """contains assertion with value='' is malformed input — must exit 2, not pass vacuously."""
        input_f = self._make_input(tmp_path)
        assert_f = str(tmp_path / "assert.yaml")
        Path(assert_f).write_text(
            yaml.dump({"assertions": [{"type": "contains", "value": ""}]}), encoding="utf-8"
        )
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 2
        assert "non-empty" in result.output

    def test_benchmark_empty_dict_assertion_rejected(self, runner, tmp_path):
        """assertions: [{}] is missing required 'type' field — must exit 2."""
        input_f = self._make_input(tmp_path)
        assert_f = str(tmp_path / "assert.yaml")
        Path(assert_f).write_text(
            yaml.dump({"assertions": [{}]}), encoding="utf-8"
        )
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 2
        assert "missing required field 'type'" in result.output or "non-empty" in result.output

    def test_benchmark_spec_format_blank_member_rejected(self, runner, tmp_path):
        """must_include_headings: [""] contains a blank entry — must exit 2."""
        input_f = self._make_input(tmp_path)
        assert_f = str(tmp_path / "assert.yaml")
        Path(assert_f).write_text(
            "must_include_headings:\n  - ''\n", encoding="utf-8"
        )
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 2
        assert "blank entry" in result.output or "non-empty strings" in result.output

    def test_benchmark_min_length_non_integer_rejected(self, runner, tmp_path):
        """assertions: [{type: min_length, value: []}] is malformed — must exit 2."""
        input_f = self._make_input(tmp_path)
        assert_f = str(tmp_path / "assert.yaml")
        Path(assert_f).write_text(
            yaml.dump({"assertions": [{"type": "min_length", "value": []}]}), encoding="utf-8"
        )
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 2
        assert "must be an integer" in result.output


class TestRound5Fixes:
    """R5-1/R5-2/R5-3: final schema hardening — padded AC IDs, negative min_length, unsupported types, non-string values."""

    def _make_score_file(self, tmp_path, ac_ids_value):
        data = {
            "test_cases": [
                {
                    "id": "TC-1", "story_id": "S-1",
                    "ac_ids": ac_ids_value,
                    "test_type": "functional", "priority": "P1",
                    "preconditions": "", "steps": [], "expected_result": "ok",
                }
            ],
            "acceptance_criteria": [{"id": "AC-1", "description": "D"}],
        }
        f = str(tmp_path / "cases.json")
        Path(f).write_text(json.dumps(data), encoding="utf-8")
        return f

    def _make_input(self, tmp_path):
        data = {
            "story": {"id": "S-1", "title": "T", "description": "D"},
            "acceptance_criteria": [{"id": "AC-1", "description": "D"}],
            "config": {"generator_model": "a", "reviewer_model": "b"},
        }
        f = str(tmp_path / "in.yaml")
        Path(f).write_text(yaml.dump(data), encoding="utf-8")
        return f

    # R5-2: padded AC IDs are normalized

    def test_score_padded_ac_id_trimmed(self, runner, tmp_path):
        """score: ac_ids=[' AC-1 '] normalizes to AC-1 and covers the AC, not an orphan."""
        f = self._make_score_file(tmp_path, [" AC-1 "])
        result = runner.invoke(main, ["score", f, "--format", "markdown"])
        assert result.exit_code == 0
        assert "no test coverage" not in result.output

    def test_rtm_update_padded_ac_id_trimmed(self, runner, tmp_path):
        """rtm update: ac_ids=[' AC-1 '] stores 'AC-1', not the padded value."""
        from skuld.rtm_store import RTMStore as _RTMStore
        data = {"test_cases": [{"id": "TC-1", "story_id": "S-1", "ac_ids": [" AC-1 "], "test_type": "functional"}]}
        f = str(tmp_path / "cases.json")
        Path(f).write_text(json.dumps(data), encoding="utf-8")
        rtm = str(tmp_path / "rtm.yaml")
        result = runner.invoke(main, ["rtm", "update", f, "--rtm-file", rtm])
        assert result.exit_code == 0
        store = _RTMStore.load(rtm)
        assert [e.ac_id for e in store.entries] == ["AC-1"]

    # R5-1: negative min_length rejected as malformed input

    def test_benchmark_min_length_negative_rejected(self, runner, tmp_path):
        """min_length: -1 is nonsensical — must exit 2, not pass vacuously."""
        input_f = self._make_input(tmp_path)
        assert_f = str(tmp_path / "assert.yaml")
        Path(assert_f).write_text(
            yaml.dump({"assertions": [{"type": "min_length", "value": -1}]}), encoding="utf-8"
        )
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 2
        assert ">= 0" in result.output

    # R5-3: unsupported/non-string assertion values rejected

    def test_benchmark_unknown_assertion_type_rejected(self, runner, tmp_path):
        """type: regex is not in the allowed set — must exit 2, not benchmark-fail."""
        input_f = self._make_input(tmp_path)
        assert_f = str(tmp_path / "assert.yaml")
        Path(assert_f).write_text(
            yaml.dump({"assertions": [{"type": "regex", "value": "TC-1"}]}), encoding="utf-8"
        )
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 2
        assert "unsupported assertion type" in result.output

    def test_benchmark_contains_list_value_rejected(self, runner, tmp_path):
        """contains with value: [] (non-string) must exit 2, not evaluate against '[]'."""
        input_f = self._make_input(tmp_path)
        assert_f = str(tmp_path / "assert.yaml")
        Path(assert_f).write_text(
            yaml.dump({"assertions": [{"type": "contains", "value": []}]}), encoding="utf-8"
        )
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 2
        assert "non-empty string" in result.output

    def test_benchmark_spec_format_null_member_rejected(self, runner, tmp_path):
        """must_include_headings: [null] must exit 2, not evaluate against 'None'."""
        input_f = self._make_input(tmp_path)
        assert_f = str(tmp_path / "assert.yaml")
        Path(assert_f).write_text(
            "must_include_headings:\n  - null\n", encoding="utf-8"
        )
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 2
        assert "non-empty strings" in result.output


class TestRound6Fixes:
    """R6-1/R6-2/R6-3: story_id batch validation, fail-fast ordering, explicit type requirement."""

    def _make_input(self, tmp_path):
        data = {
            "story": {"id": "S-1", "title": "T", "description": "D"},
            "acceptance_criteria": [{"id": "AC-1", "description": "D"}],
            "config": {"generator_model": "a", "reviewer_model": "b"},
        }
        f = str(tmp_path / "in.yaml")
        Path(f).write_text(yaml.dump(data), encoding="utf-8")
        return f

    def _make_update_file(self, tmp_path, test_cases):
        f = str(tmp_path / "cases.json")
        Path(f).write_text(json.dumps({"test_cases": test_cases}), encoding="utf-8")
        return f

    # R6-1: story_id validation

    def test_rtm_update_missing_story_id_rejected(self, runner, tmp_path):
        """rtm update: test_case missing story_id exits 2 and writes nothing."""
        f = self._make_update_file(tmp_path, [{"id": "TC-1", "ac_ids": ["AC-1"], "test_type": "functional"}])
        rtm = str(tmp_path / "rtm.yaml")
        result = runner.invoke(main, ["rtm", "update", f, "--rtm-file", rtm])
        assert result.exit_code == 2
        assert not Path(rtm).exists()

    def test_rtm_update_mixed_story_ids_rejected(self, runner, tmp_path):
        """rtm update: batch with S-1 and S-2 exits 2 and writes nothing."""
        f = self._make_update_file(tmp_path, [
            {"id": "TC-1", "story_id": "S-1", "ac_ids": ["AC-1"], "test_type": "functional"},
            {"id": "TC-2", "story_id": "S-2", "ac_ids": ["AC-1"], "test_type": "negative"},
        ])
        rtm = str(tmp_path / "rtm.yaml")
        result = runner.invoke(main, ["rtm", "update", f, "--rtm-file", rtm])
        assert result.exit_code == 2
        assert "mixed" in result.output
        assert not Path(rtm).exists()

    def test_rtm_update_padded_story_id_normalized(self, runner, tmp_path):
        """rtm update: story_id '  S-1  ' is trimmed and merges under 'S-1'."""
        from skuld.rtm_store import RTMStore as _RTMStore
        f = self._make_update_file(tmp_path, [
            {"id": "TC-1", "story_id": "  S-1  ", "ac_ids": ["AC-1"], "test_type": "functional"},
        ])
        rtm = str(tmp_path / "rtm.yaml")
        result = runner.invoke(main, ["rtm", "update", f, "--rtm-file", rtm])
        assert result.exit_code == 0
        store = _RTMStore.load(rtm)
        assert all(e.story_id == "S-1" for e in store.entries)

    # R6-2: assertions validated before pipeline runs

    def test_benchmark_invalid_assertions_fail_before_pipeline(self, runner, tmp_path, monkeypatch):
        """Malformed assertions file exits 2 without invoking run_pipeline."""
        called = []
        import skuld.cli as cli_mod
        original = cli_mod.run_pipeline
        monkeypatch.setattr(cli_mod, "run_pipeline", lambda **kw: called.append(kw) or original(**kw))
        input_f = self._make_input(tmp_path)
        assert_f = str(tmp_path / "assert.yaml")
        Path(assert_f).write_text("assertions:\n  type: contains\n  value: 'TC-'\n", encoding="utf-8")
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 2
        assert called == [], "run_pipeline must not be called when assertions file is malformed"

    # R6-3: explicit type required for simple assertions

    def test_benchmark_simple_assertion_missing_type_rejected(self, runner, tmp_path):
        """assertions: [{value: 'TC-'}] is missing 'type' — must exit 2."""
        input_f = self._make_input(tmp_path)
        assert_f = str(tmp_path / "assert.yaml")
        Path(assert_f).write_text(
            yaml.dump({"assertions": [{"value": "TC-"}]}), encoding="utf-8"
        )
        result = runner.invoke(main, ["benchmark", input_f, assert_f, "--dry-run"])
        assert result.exit_code == 2
        assert "missing required field 'type'" in result.output
