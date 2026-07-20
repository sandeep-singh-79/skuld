"""Skuld CLI entry point (T14)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click
import yaml

from skuld import __version__
from skuld.end_to_end_flow import run_pipeline
from skuld.models import EXIT_INPUT_ERROR, EXIT_OK, EXIT_VALIDATION_ERROR
from skuld.rtm_builder import build_rtm
from skuld.rtm_scorer import score_rtm_detailed
from skuld.rtm_store import RTMStore

MAX_FILE_SIZE = 10_485_760  # 10 MB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_path(ctx, param, value):
    """Reject paths with '..' traversal components (script injection defence)."""
    if value is None:
        return value
    if ".." in Path(value).parts:
        raise click.BadParameter(
            f"Path traversal detected: {value!r}. Use a direct path without '..' components."
        )
    return str(Path(value).resolve())


def _load_rtm(rtm_file):
    """Load RTMStore with error handling."""
    try:
        return RTMStore.load(rtm_file)
    except (ValueError, OSError) as exc:
        click.echo(f"Error loading RTM: {exc}", err=True)
        sys.exit(EXIT_INPUT_ERROR)


def _coerce_ac_ids(value: object) -> list:
    """Normalise ac_ids field: str → [str], list[str] → list, anything else → TypeError.

    Whitespace is stripped from each entry. Blank entries (empty after stripping) are rejected.
    """
    if isinstance(value, str):
        value = [value]
    elif not isinstance(value, list):
        raise TypeError(f"ac_ids must be a list or string, got {type(value).__name__}")
    else:
        bad = sorted({type(item).__name__ for item in value if not isinstance(item, str)})
        if bad:
            raise TypeError(f"ac_ids must contain only strings, got {', '.join(bad)}")
    normalized = [v.strip() for v in value]
    blanks = [repr(original) for original, cleaned in zip(value, normalized) if not cleaned]
    if blanks:
        raise TypeError(f"ac_ids must not contain blank entries: {', '.join(blanks)}")
    return normalized


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(version=__version__)
def main():
    """Skuld — AI-powered test case generator with adversarial review."""


# ---------------------------------------------------------------------------
# skuld generate
# ---------------------------------------------------------------------------

@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), callback=_validate_path, help="Write output to file (default: stdout)")
@click.option("--format", "output_format", type=click.Choice(["markdown", "json"]), default=None, help="Output format")
@click.option("--rtm-file", type=click.Path(), callback=_validate_path, help="Merge results into persistent RTM")
@click.option("--force", is_flag=True, help="Force full RTM regeneration for this story")
@click.option("--dry-run", is_flag=True, help="Use FakeLLMClient (no API keys needed)")
def generate(input_file, output, output_format, rtm_file, force, dry_run):
    """Generate test cases from a story input file."""
    result = run_pipeline(
        input_path=input_file,
        rtm_file=rtm_file,
        force=force,
        output_format=output_format,
        use_fake_llm=dry_run,
    )

    # Emit warnings to stderr
    for warning in result.warnings:
        click.echo(f"Warning: {warning}", err=True)

    if result.exit_code != EXIT_OK:
        click.echo(result.message, err=True)
        sys.exit(result.exit_code)

    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(result.message, encoding="utf-8")
        click.echo(f"Output written to {output}", err=True)
    else:
        click.echo(result.message)


# ---------------------------------------------------------------------------
# skuld score
# ---------------------------------------------------------------------------

@main.command()
@click.argument("test_cases_file", type=click.Path(exists=True))
@click.option("--format", "output_format", type=click.Choice(["markdown", "json"]), default="json", help="Output format")
def score(test_cases_file, output_format):
    """Score test cases deterministically using RTM analysis (no LLM needed)."""
    from skuld.models import AcceptanceCriterion, TestCase

    file_size = Path(test_cases_file).stat().st_size
    if file_size > MAX_FILE_SIZE:
        click.echo(f"Input file too large ({file_size} bytes, max 10MB).", err=True)
        sys.exit(EXIT_INPUT_ERROR)

    try:
        content = Path(test_cases_file).read_text(encoding="utf-8")
        data = json.loads(content)
    except (json.JSONDecodeError, OSError) as exc:
        click.echo(f"Error reading file: {exc}", err=True)
        sys.exit(EXIT_INPUT_ERROR)

    if not isinstance(data, dict):
        click.echo("Invalid file: expected a JSON object with 'test_cases' key.", err=True)
        sys.exit(EXIT_INPUT_ERROR)

    # Extract test cases and ACs
    raw_cases = data.get("test_cases", [])
    raw_acs = data.get("acceptance_criteria", [])

    if not raw_cases:
        click.echo("No test_cases found in input file.", err=True)
        sys.exit(EXIT_INPUT_ERROR)

    try:
        test_cases = [
            TestCase(
                id=tc["id"],
                story_id=tc.get("story_id", "unknown"),
                ac_ids=_coerce_ac_ids(tc.get("ac_ids", [])),
                test_type=tc.get("test_type", "functional"),
                priority=tc.get("priority", "P2"),
                preconditions=tc.get("preconditions", ""),
                steps=tc.get("steps", []),
                expected_result=tc.get("expected_result", ""),
            )
            for tc in raw_cases
        ]
    except (KeyError, TypeError) as exc:
        click.echo(f"Malformed test case data: {exc}", err=True)
        sys.exit(EXIT_INPUT_ERROR)

    # Build ACs from data or infer from test_cases
    if raw_acs:
        try:
            ac_list = [
                AcceptanceCriterion(
                    id=ac["id"],
                    description=ac.get("description", ""),
                    criticality=ac.get("criticality", "medium"),
                )
                for ac in raw_acs
            ]
        except (KeyError, TypeError) as exc:
            click.echo(f"Malformed acceptance criteria: {exc}", err=True)
            sys.exit(EXIT_INPUT_ERROR)
    else:
        # Infer ACs from test case ac_ids
        seen_ac_ids: set[str] = set()
        ac_list = []
        for tc in test_cases:
            for ac_id in tc.ac_ids:
                if ac_id not in seen_ac_ids:
                    seen_ac_ids.add(ac_id)
                    ac_list.append(AcceptanceCriterion(id=ac_id, description="(inferred)"))

    entries = build_rtm(test_cases, ac_list)
    detailed = score_rtm_detailed(entries, ac_list)

    if output_format == "json":
        click.echo(json.dumps(detailed, indent=2, default=str))
    else:
        click.echo(f"Composite Score: {detailed['composite']:.1f} / 100.0")
        click.echo(f"Tier: {detailed['tier']}")
        click.echo(f"AC Coverage: {detailed['ac_coverage']:.0%}")
        click.echo(f"Negative Coverage: {detailed['negative_coverage']:.0%}")
        click.echo(f"Edge Coverage: {detailed['edge_coverage']:.0%}")
        if detailed["gaps"]:
            click.echo(f"\nGaps ({len(detailed['gaps'])}):")
            for gap in detailed["gaps"]:
                click.echo(f"  {gap}")


# ---------------------------------------------------------------------------
# skuld rtm (subgroup)
# ---------------------------------------------------------------------------

@main.group()
def rtm():
    """RTM (Requirements Traceability Matrix) management commands."""


@rtm.command()
@click.option("--rtm-file", required=True, type=click.Path(), callback=_validate_path, help="Path to rtm.yaml")
def report(rtm_file):
    """Print RTM coverage summary."""
    store = _load_rtm(rtm_file)
    summary = store.coverage_summary()
    click.echo(f"Total entries: {summary['total_entries']}")
    click.echo(f"Total stories: {summary['total_stories']}")
    click.echo(f"Total test cases: {summary['total_test_cases']}")
    click.echo(f"Unique ACs: {summary['unique_acs']}")


@rtm.command()
@click.option("--rtm-file", required=True, type=click.Path(), callback=_validate_path, help="Path to rtm.yaml")
def gaps(rtm_file):
    """List coverage gaps in the RTM."""
    store = _load_rtm(rtm_file)
    gap_list = store.query_gaps()
    if not gap_list:
        click.echo("No coverage gaps found.")
        return
    click.echo(f"Coverage gaps ({len(gap_list)}):")
    for gap in gap_list:
        click.echo(f"  {gap.ac_id}: missing {gap.missing_types}")


@rtm.command()
@click.argument("test_cases_file", type=click.Path(exists=True))
@click.option("--rtm-file", required=True, type=click.Path(), callback=_validate_path, help="Path to rtm.yaml")
@click.option("--force", is_flag=True, help="Force full regeneration for the story")
def update(test_cases_file, rtm_file, force):
    """Merge test cases from a JSON file into the RTM."""
    from skuld.models import RTMEntry

    file_size = Path(test_cases_file).stat().st_size
    if file_size > MAX_FILE_SIZE:
        click.echo(f"Input file too large ({file_size} bytes, max 10MB).", err=True)
        sys.exit(EXIT_INPUT_ERROR)

    try:
        content = Path(test_cases_file).read_text(encoding="utf-8")
        data = json.loads(content)
    except (json.JSONDecodeError, OSError) as exc:
        click.echo(f"Error reading file: {exc}", err=True)
        sys.exit(EXIT_INPUT_ERROR)

    if not isinstance(data, dict):
        click.echo("Invalid file: expected a JSON object with 'test_cases' key.", err=True)
        sys.exit(EXIT_INPUT_ERROR)

    raw_cases = data.get("test_cases", [])
    if not raw_cases:
        click.echo("No test_cases found in input file.", err=True)
        sys.exit(EXIT_INPUT_ERROR)

    if not all(isinstance(tc, dict) for tc in raw_cases):
        click.echo("Malformed test_cases: each entry must be a JSON object.", err=True)
        sys.exit(EXIT_INPUT_ERROR)

    # Validate and normalize story_id — must be present and consistent across the batch
    story_ids = []
    for tc in raw_cases:
        raw_story_id = tc.get("story_id")
        if not isinstance(raw_story_id, str) or not raw_story_id.strip():
            click.echo(
                "Malformed test case data: every test_case in 'rtm update' must include a non-empty 'story_id'.",
                err=True,
            )
            sys.exit(EXIT_INPUT_ERROR)
        story_ids.append(raw_story_id.strip())

    unique_story_ids = set(story_ids)
    if len(unique_story_ids) != 1:
        click.echo(
            f"Malformed test case data: mixed 'story_id' values in batch: {sorted(unique_story_ids)}",
            err=True,
        )
        sys.exit(EXIT_INPUT_ERROR)

    story_id = story_ids[0]

    # Build RTM entries from test cases
    try:
        entries = []
        for tc in raw_cases:
            for ac_id in _coerce_ac_ids(tc.get("ac_ids", [])):
                entries.append(
                    RTMEntry(
                        ac_id=ac_id,
                        test_case_id=tc["id"],
                        test_type=tc.get("test_type", "functional"),
                        story_id=story_id,
                    )
                )
    except (KeyError, TypeError) as exc:
        click.echo(f"Malformed test case data: {exc}", err=True)
        sys.exit(EXIT_INPUT_ERROR)

    store = _load_rtm(rtm_file)
    merge_result = store.merge(entries, story_id=story_id, run_id="cli-update", force=force)
    store.save(rtm_file)

    click.echo(f"Added: {merge_result.added}, Superseded: {merge_result.superseded}, Retained: {merge_result.retained}")
    for conflict in merge_result.conflicts:
        click.echo(f"  Warning: {conflict}", err=True)


@rtm.command()
@click.option("--rtm-file", required=True, type=click.Path(), callback=_validate_path, help="Path to rtm.yaml")
@click.option("--ac", required=True, help="AC ID to filter history for")
def history(rtm_file, ac):
    """Show coverage history for a specific AC."""
    store = _load_rtm(rtm_file)
    matching = [e for e in store.entries if e.ac_id == ac]
    if not matching:
        click.echo(f"No entries found for {ac}.")
        return
    click.echo(f"History for {ac} ({len(matching)} entries):")
    for entry in matching:
        click.echo(f"  {entry.test_case_id} [{entry.test_type}] status={entry.status} added={entry.added_date}")


# ---------------------------------------------------------------------------
# skuld benchmark
# ---------------------------------------------------------------------------

@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.argument("assertions_file", type=click.Path(exists=True))
@click.option("--dry-run/--no-dry-run", default=True, help="Use FakeLLMClient (default for benchmarks)")
def benchmark(input_file, assertions_file, dry_run):
    """Run pipeline and validate output against assertions."""
    # --- Load and validate assertions FIRST — fail fast before any pipeline work ---
    assertions_size = Path(assertions_file).stat().st_size
    if assertions_size > MAX_FILE_SIZE:
        click.echo(f"Assertions file too large ({assertions_size} bytes, max 10MB).", err=True)
        sys.exit(EXIT_INPUT_ERROR)

    try:
        content = Path(assertions_file).read_text(encoding="utf-8")
        assertions_data = yaml.safe_load(content) or {}
    except (OSError, yaml.YAMLError) as exc:
        click.echo(f"Error reading assertions: {exc}", err=True)
        sys.exit(EXIT_INPUT_ERROR)

    # Build unified assertions list — support both formats:
    # Simple: {assertions: [{type, value}, ...]}  — 'type' is required
    # Spec:   {must_include_headings: [...], ...}  — 'type' is synthesized as 'contains'
    assertions: list = []
    if isinstance(assertions_data, dict):
        raw_assertions = assertions_data.get("assertions")
        if raw_assertions is not None:
            if not isinstance(raw_assertions, list):
                click.echo(
                    f"Invalid assertions file: 'assertions' must be a list,"
                    f" got {type(raw_assertions).__name__}.",
                    err=True,
                )
                sys.exit(EXIT_INPUT_ERROR)
            for i_item, item in enumerate(raw_assertions, 1):
                if isinstance(item, dict) and "type" not in item:
                    click.echo(
                        f"Invalid assertions file: assertion {i_item} is missing required field 'type'.",
                        err=True,
                    )
                    sys.exit(EXIT_INPUT_ERROR)
                assertions.append(item)
        for key in ("must_include_headings", "must_include_labels", "must_include_substrings"):
            field = assertions_data.get(key)
            if field is None:
                continue
            if not isinstance(field, list):
                click.echo(
                    f"Invalid assertions file: '{key}' must be a list, got {type(field).__name__}.",
                    err=True,
                )
                sys.exit(EXIT_INPUT_ERROR)
            for value in field:
                if not isinstance(value, str) or not value.strip():
                    click.echo(
                        f"Invalid assertions file: '{key}' entries must be non-empty strings.",
                        err=True,
                    )
                    sys.exit(EXIT_INPUT_ERROR)
                assertions.append({"type": "contains", "value": value.strip()})

    if not assertions:
        click.echo("No assertions found in file.", err=True)
        sys.exit(EXIT_INPUT_ERROR)

    # --- Validate assertion schema before running the pipeline ---
    _ALLOWED_TYPES = {"contains", "not_contains", "min_length"}
    schema_errors = []
    for i, assertion in enumerate(assertions, 1):
        if not isinstance(assertion, dict):
            schema_errors.append(f"Assertion {i}: expected a mapping, got {type(assertion).__name__}")
            continue
        a_type = assertion.get("type", "contains")
        if not isinstance(a_type, str) or a_type not in _ALLOWED_TYPES:
            schema_errors.append(
                f"Assertion {i}: unsupported assertion type {a_type!r}; "
                f"allowed: {', '.join(sorted(_ALLOWED_TYPES))}"
            )
            continue
        raw_value = assertion.get("value")
        if a_type in ("contains", "not_contains"):
            if not isinstance(raw_value, str) or raw_value.strip() == "":
                schema_errors.append(
                    f"Assertion {i}: '{a_type}' requires a non-empty string 'value' field"
                )
        elif a_type == "min_length":
            try:
                threshold = int(str(raw_value))
            except (ValueError, TypeError):
                schema_errors.append(
                    f"Assertion {i}: 'min_length' value must be an integer, got {raw_value!r}"
                )
            else:
                if threshold < 0:
                    schema_errors.append(
                        f"Assertion {i}: 'min_length' must be >= 0, got {threshold}"
                    )

    if schema_errors:
        click.echo("Invalid assertions file:", err=True)
        for err in schema_errors:
            click.echo(f"  {err}", err=True)
        sys.exit(EXIT_INPUT_ERROR)

    # --- Run pipeline (only after assertions are validated) ---
    result = run_pipeline(
        input_path=input_file,
        use_fake_llm=dry_run,
    )

    if result.exit_code != EXIT_OK:
        click.echo(f"Pipeline failed: {result.message}", err=True)
        sys.exit(result.exit_code)

    output = result.message

    # --- Evaluate validated assertions (exit 1 when valid benchmark fails against output) ---
    failures = []
    for i, assertion in enumerate(assertions, 1):
        a_type = assertion.get("type", "contains")
        value = str(assertion.get("value", ""))
        if a_type == "contains":
            if value not in output:
                failures.append(f"Assertion {i}: expected output to contain {value!r}")
        elif a_type == "not_contains":
            if value in output:
                failures.append(f"Assertion {i}: expected output NOT to contain {value!r}")
        elif a_type == "min_length":
            threshold = int(value)
            if len(output) < threshold:
                failures.append(f"Assertion {i}: output length {len(output)} < minimum {threshold}")
        else:
            failures.append(f"Assertion {i}: unknown assertion type {a_type!r}")

    if failures:
        click.echo("BENCHMARK FAILED:", err=True)
        for f in failures:
            click.echo(f"  {f}", err=True)
        sys.exit(EXIT_VALIDATION_ERROR)

    click.echo(f"BENCHMARK PASSED: {len(assertions)} assertions satisfied.")


if __name__ == "__main__":
    main()
