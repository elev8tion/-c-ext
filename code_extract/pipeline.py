"""5-stage pipeline orchestrator: scan -> filter -> extract -> clean -> format -> export."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Callable

from code_extract.models import (
    CleanedBlock,
    ExportResult,
    ExtractedBlock,
    FormattedBlock,
    PipelineConfig,
    ScannedItem,
)
from code_extract.scanner import scan_directory
from code_extract.extractor import extract_item
from code_extract.cleaner import clean_block
from code_extract.formatter import format_block
from code_extract.exporter import export_blocks, generate_manifest, generate_readme


ProgressCallback = Callable[[str, int, int], None]


def run_scan(config: PipelineConfig, progress: ProgressCallback | None = None) -> list[ScannedItem]:
    """Stage 1: Scan the source directory."""
    if progress:
        progress("Scanning", 0, 1)
    items = scan_directory(config.source_dir, skip_dirs=config.skip_dirs)
    if progress:
        progress("Scanning", 1, 1)
    return items


def run_pipeline(
    config: PipelineConfig,
    progress: ProgressCallback | None = None,
) -> ExportResult:
    """Run the full extraction pipeline."""
    # Stage 1: Scan
    if progress:
        progress("Scanning", 0, 1)
    all_items = scan_directory(config.source_dir, skip_dirs=config.skip_dirs)
    if progress:
        progress("Scanning", 1, 1)

    # Stage 2: Filter
    items = _filter_items(all_items, config)
    if not items:
        raise ValueError(
            f"No matching items found. "
            f"Scanned {len(all_items)} total items. "
            f"Target: {config.target!r}, Pattern: {config.pattern!r}"
        )

    # Stage 3: Extract
    extracted: list[ExtractedBlock] = []
    for i, item in enumerate(items):
        if progress:
            progress("Extracting", i, len(items))
        try:
            block = extract_item(item)
            extracted.append(block)
        except Exception as e:
            if progress:
                progress(f"Extract error ({item.name}): {e}", i, len(items))

    if progress:
        progress("Extracting", len(items), len(items))

    # Stage 4: Clean
    cleaned: list[CleanedBlock] = []
    for i, block in enumerate(extracted):
        if progress:
            progress("Cleaning", i, len(extracted))
        cleaned.append(clean_block(block))

    if progress:
        progress("Cleaning", len(extracted), len(extracted))

    # Stage 5: Format
    formatted: list[FormattedBlock] = []
    for i, block in enumerate(cleaned):
        if progress:
            progress("Formatting", i, len(cleaned))
        formatted.append(format_block(block))

    if progress:
        progress("Formatting", len(cleaned), len(cleaned))

    # Stage 6: Export
    if progress:
        progress("Exporting", 0, 1)

    result = export_blocks(formatted, config.output_dir)

    # Generate README and manifest
    result.readme_path = generate_readme(
        formatted, config.output_dir, config.source_dir,
    )
    result.files_created.append(result.readme_path)

    result.manifest_path = generate_manifest(
        formatted, result, config.source_dir,
    )
    result.files_created.append(result.manifest_path)

    if progress:
        progress("Exporting", 1, 1)

    return result


def _filter_items(items: list[ScannedItem], config: PipelineConfig) -> list[ScannedItem]:
    """Filter scanned items based on config."""
    if config.extract_all:
        return items

    if config.target:
        target = config.target
        matches = [
            item for item in items
            if item.name == target or item.qualified_name == target
        ]
        if not matches:
            # Try case-insensitive
            matches = [
                item for item in items
                if item.name.lower() == target.lower()
                or item.qualified_name.lower() == target.lower()
            ]
        return matches

    if config.pattern:
        pattern = config.pattern
        return [
            item for item in items
            if fnmatch.fnmatch(item.name, pattern)
            or fnmatch.fnmatch(item.qualified_name, pattern)
            or fnmatch.fnmatch(item.block_type.value, pattern)
        ]

    return items
