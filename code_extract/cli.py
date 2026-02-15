"""Click CLI with scan, extract, and serve subcommands."""

from __future__ import annotations

from pathlib import Path

import click

from code_extract.models import CodeBlockType, Language, PipelineConfig
from code_extract.pipeline import run_pipeline, run_scan

_LANGUAGE_CHOICES = [lang.value for lang in Language]
_TYPE_CHOICES = [bt.value for bt in CodeBlockType]


@click.group()
@click.version_option(version="0.2.0")
def cli():
    """code-extract: Extract, clean, and export code from any codebase."""


@cli.command()
@click.argument("source_dir", type=click.Path(exists=True, file_okay=False, path_type=Path), default=".")
@click.option("--language", "-l", type=click.Choice(_LANGUAGE_CHOICES), help="Filter by language")
@click.option("--type", "-t", "block_type", type=click.Choice(_TYPE_CHOICES), help="Filter by type")
def scan(source_dir: Path, language: str | None, block_type: str | None):
    """Scan a directory and list extractable code items."""
    config = PipelineConfig(source_dir=source_dir)
    items = run_scan(config)

    # Apply filters
    if language:
        items = [i for i in items if i.language.value == language]
    if block_type:
        items = [i for i in items if i.block_type.value == block_type]

    if not items:
        click.echo("No extractable items found.")
        return

    click.echo(f"\nFound {len(items)} extractable item(s):\n")

    # Group by file
    by_file: dict[Path, list] = {}
    for item in items:
        by_file.setdefault(item.file_path, []).append(item)

    for file_path, file_items in by_file.items():
        click.echo(click.style(str(file_path), fg="cyan"))
        for item in file_items:
            type_color = {
                "class": "yellow",
                "function": "green",
                "component": "magenta",
                "widget": "magenta",
                "mixin": "blue",
                "method": "green",
                "struct": "yellow",
                "trait": "red",
                "interface": "cyan",
                "enum": "bright_green",
                "module": "bright_blue",
                "table": "bright_yellow",
                "view": "cyan",
                "sql_function": "magenta",
                "trigger": "red",
                "index": "white",
                "migration": "bright_magenta",
                "policy": "bright_red",
                "provider": "blue",
            }.get(item.block_type.value, "white")

            click.echo(
                f"  {click.style(item.block_type.value, fg=type_color):>20}  "
                f"{item.qualified_name}  "
                f"{click.style(f'L{item.line_number}', dim=True)}"
            )
        click.echo()

    # Summary
    by_type: dict[str, int] = {}
    by_lang: dict[str, int] = {}
    for item in items:
        by_type[item.block_type.value] = by_type.get(item.block_type.value, 0) + 1
        by_lang[item.language.value] = by_lang.get(item.language.value, 0) + 1

    click.echo("Summary:")
    for lang, count in sorted(by_lang.items()):
        click.echo(f"  {lang}: {count}")
    for btype, count in sorted(by_type.items()):
        click.echo(f"  {btype}: {count}")


@cli.command()
@click.argument("source_dir", type=click.Path(exists=True, file_okay=False, path_type=Path), default=".")
@click.argument("target", required=False)
@click.option("-o", "--output", "output_dir", type=click.Path(path_type=Path), default="extracted", help="Output directory")
@click.option("--pattern", "-p", help="Glob pattern to match item names")
@click.option("--all", "extract_all", is_flag=True, help="Extract all items")
def extract(
    source_dir: Path,
    target: str | None,
    output_dir: Path,
    pattern: str | None,
    extract_all: bool,
):
    """Extract code items from a source directory."""
    if not target and not pattern and not extract_all:
        raise click.UsageError(
            "Specify a target name, --pattern, or --all"
        )

    config = PipelineConfig(
        source_dir=source_dir,
        output_dir=output_dir,
        target=target,
        pattern=pattern,
        extract_all=extract_all,
    )

    def progress(stage: str, current: int, total: int):
        if total > 0:
            click.echo(f"  {stage}: {current}/{total}", nl=(current == total))
        else:
            click.echo(f"  {stage}...")

    click.echo(f"Extracting from {source_dir} -> {output_dir}\n")

    try:
        result = run_pipeline(config, progress=progress)
    except ValueError as e:
        raise click.ClickException(str(e))

    click.echo(f"\nDone! Created {len(result.files_created)} file(s) in {result.output_dir}")
    for f in result.files_created:
        click.echo(f"  {f}")


@cli.command()
@click.option("--port", "-p", default=8420, help="Port number")
@click.option("--host", default="127.0.0.1", help="Host address")
@click.option("--open/--no-open", default=True, help="Open browser automatically")
def serve(port: int, host: str, open: bool):
    """Start the web UI."""
    try:
        import uvicorn
    except ImportError:
        raise click.ClickException(
            "uvicorn is required for the web UI. "
            "Install with: pip install 'code-extract[web]' or pip install 'code-extract[all]'"
        )

    from code_extract.web import create_app

    click.echo(f"Starting code-extract web UI at http://{host}:{port}")

    if open:
        import webbrowser
        import threading
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()

    uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    cli()
