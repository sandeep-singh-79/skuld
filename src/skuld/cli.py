"""Skuld CLI entry point."""

import click


@click.group()
@click.version_option()
def main():
    """Skuld — AI-powered test case generator with adversarial review."""


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def generate(input_file, output):
    """Generate test cases from a story input file."""
    click.echo(f"Generating test cases from: {input_file}")


@main.command()
@click.argument("benchmarks_dir", type=click.Path(exists=True))
def benchmark(benchmarks_dir):
    """Run benchmark scenarios against assertions."""
    click.echo(f"Running benchmarks from: {benchmarks_dir}")


if __name__ == "__main__":
    main()
