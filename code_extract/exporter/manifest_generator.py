"""Generate manifest.json."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from code_extract.models import ExportResult, FormattedBlock


def generate_manifest(
    blocks: list[FormattedBlock],
    result: ExportResult,
    source_dir: Path,
) -> Path:
    """Generate a manifest.json summarizing the extraction."""
    items = []
    for block in blocks:
        item = block.item
        items.append({
            "name": item.name,
            "qualified_name": item.qualified_name,
            "type": item.block_type.value,
            "language": item.language.value,
            "source_file": str(item.file_path),
            "source_line": item.line_number,
            "is_valid": block.is_valid,
            "validation_error": block.validation_error,
        })

    manifest = {
        "version": "1.0",
        "generated": datetime.now().isoformat(),
        "source_directory": str(source_dir),
        "output_directory": str(result.output_dir),
        "total_items": len(blocks),
        "items": items,
        "files_created": [str(f) for f in result.files_created],
    }

    manifest_path = result.output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path
