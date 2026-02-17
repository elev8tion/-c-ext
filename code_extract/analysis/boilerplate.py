"""Boilerplate generator — detect repeated patterns and templatize."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import PurePosixPath

from code_extract.models import ExtractedBlock


def detect_patterns(blocks: dict[str, ExtractedBlock]) -> list[dict]:
    """Detect repeated structural patterns in the codebase.

    Returns list of patterns: {pattern_name, directory, block_type, count, example_names}
    """
    # Group by (directory, block_type)
    groups: dict[tuple[str, str], list[ExtractedBlock]] = {}
    for block in blocks.values():
        parts = PurePosixPath(str(block.item.file_path)).parts
        directory = "/".join(parts[-2:-1]) if len(parts) > 1 else "root"
        key = (directory, block.item.block_type.value)
        groups.setdefault(key, []).append(block)

    patterns: list[dict] = []
    for (directory, block_type), group_blocks in groups.items():
        if len(group_blocks) < 2:
            continue

        patterns.append({
            "pattern_name": f"{directory}/{block_type}",
            "directory": directory,
            "block_type": block_type,
            "count": len(group_blocks),
            "example_names": [b.item.qualified_name for b in group_blocks[:5]],
        })

    patterns.sort(key=lambda p: -p["count"])
    return patterns


def generate_template(blocks: list[ExtractedBlock], template_name: str = "template") -> dict:
    """Generate a boilerplate template from a list of similar blocks.

    Replaces specific names with {{placeholder}} variables.
    Returns: {template_code, variables, config}
    """
    if not blocks:
        return {"template_code": "", "variables": [], "config": {}}

    # Use the first block as the base template
    base = blocks[0]
    template_code = base.source_code

    # Find names that vary across blocks
    all_names = [b.item.name for b in blocks]
    common_prefix = _common_prefix(all_names)

    # Replace the specific name with placeholder
    name = base.item.name
    template_code = template_code.replace(name, "{{name}}")

    # If there's a common prefix, also create a suffix variable
    variables = [{"name": "name", "description": f"Name for the {base.item.block_type.value}", "example": name}]

    if common_prefix and len(common_prefix) > 2:
        template_code = template_code.replace(common_prefix, "{{prefix}}")
        variables.append({"name": "prefix", "description": "Common prefix", "example": common_prefix})

    config = {
        "template_name": template_name,
        "block_type": base.item.block_type.value,
        "language": base.item.language.value,
        "source_count": len(blocks),
    }

    return {
        "template_code": template_code,
        "variables": variables,
        "config": config,
    }


def filter_blocks_by_pattern(
    blocks: dict[str, ExtractedBlock], directory: str, block_type: str,
) -> list[ExtractedBlock]:
    """Filter blocks to only those matching a directory + block_type pair."""
    result: list[ExtractedBlock] = []
    for block in blocks.values():
        parts = PurePosixPath(str(block.item.file_path)).parts
        blk_dir = "/".join(parts[-2:-1]) if len(parts) > 1 else "root"
        if blk_dir == directory and block.item.block_type.value == block_type:
            result.append(block)
    return result


def batch_apply_template(
    template_code: str, variable_sets: list[dict[str, str]],
) -> list[str]:
    """Apply multiple variable sets to a template, returning a list of generated code strings."""
    return [apply_template(template_code, vs) for vs in variable_sets]


def apply_template(template_code: str, variables: dict[str, str]) -> str:
    """Apply variable values to a template."""
    result = template_code
    for key, value in variables.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


def _common_prefix(strings: list[str]) -> str:
    """Find the longest common prefix of a list of strings."""
    if not strings:
        return ""
    prefix = strings[0]
    for s in strings[1:]:
        while not s.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix
