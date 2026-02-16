"""Semantic diff — compare two codebases by matching items on name+type+language."""

from __future__ import annotations

from pathlib import Path

from code_extract.models import PipelineConfig, ScannedItem
from code_extract.pipeline import run_scan
from code_extract.extractor import extract_item


def semantic_diff(path_a: Path, path_b: Path) -> dict:
    """Compare two codebases and return semantic diff.

    Returns: {added, removed, modified, unchanged, diff_id}
    """
    config_a = PipelineConfig(source_dir=path_a)
    config_b = PipelineConfig(source_dir=path_b)

    items_a = run_scan(config_a)
    items_b = run_scan(config_b)

    # Index by (name, type, language)
    def item_key(item: ScannedItem) -> str:
        return f"{item.name}:{item.block_type.value}:{item.language.value}"

    index_a: dict[str, ScannedItem] = {}
    for item in items_a:
        key = item_key(item)
        index_a[key] = item

    index_b: dict[str, ScannedItem] = {}
    for item in items_b:
        key = item_key(item)
        index_b[key] = item

    keys_a = set(index_a.keys())
    keys_b = set(index_b.keys())

    added_keys = keys_b - keys_a
    removed_keys = keys_a - keys_b
    common_keys = keys_a & keys_b

    added = [
        {"name": index_b[k].qualified_name, "type": index_b[k].block_type.value, "language": index_b[k].language.value}
        for k in sorted(added_keys)
    ]

    removed = [
        {"name": index_a[k].qualified_name, "type": index_a[k].block_type.value, "language": index_a[k].language.value}
        for k in sorted(removed_keys)
    ]

    modified: list[dict] = []
    unchanged = 0

    for key in sorted(common_keys):
        item_a = index_a[key]
        item_b = index_b[key]

        try:
            block_a = extract_item(item_a)
            block_b = extract_item(item_b)
        except Exception:
            unchanged += 1
            continue

        if block_a.source_code.strip() != block_b.source_code.strip():
            modified.append({
                "name": item_a.qualified_name,
                "type": item_a.block_type.value,
                "language": item_a.language.value,
                "before": block_a.source_code[:1500],
                "after": block_b.source_code[:1500],
            })
        else:
            unchanged += 1

    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "unchanged": unchanged,
    }
