"""Cleaner orchestrator."""

from __future__ import annotations

from code_extract.models import CleanedBlock, ExtractedBlock
from code_extract.cleaner.import_cleaner import clean_imports
from code_extract.cleaner.metadata_stripper import strip_metadata
from code_extract.cleaner.reference_sanitizer import sanitize_references


def clean_block(block: ExtractedBlock) -> CleanedBlock:
    """Run all cleaning stages on an extracted block."""
    warnings: list[str] = []

    # 1. Strip metadata from source code
    code, meta_warnings = strip_metadata(block.source_code)
    warnings.extend(meta_warnings)

    # 2. Clean imports (remove unused)
    kept_imports, removed = clean_imports(block.imports, code)
    if removed:
        warnings.append(f"Removed {len(removed)} unused import(s)")

    # 3. Sanitize relative imports
    sanitized_imports, code, ref_warnings = sanitize_references(kept_imports, code)
    warnings.extend(ref_warnings)

    return CleanedBlock(
        item=block.item,
        source_code=code,
        required_imports=sanitized_imports,
        warnings=warnings,
    )


__all__ = ["clean_block"]
