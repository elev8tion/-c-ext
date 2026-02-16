"""Architecture snapshot — groups items by directory, generates Mermaid diagrams."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from code_extract.analysis.graph_models import DependencyGraph


def generate_architecture(graph: DependencyGraph, source_dir: str = "") -> dict:
    """Generate architecture snapshot with Mermaid diagram and module list.

    Returns: {mermaid: str, modules: [{directory, item_count, items: [{name, type}]}]}
    """
    # Group nodes by directory
    dir_groups: dict[str, list[dict]] = {}
    for node in graph.nodes.values():
        rel_path = node.file_path.replace(source_dir, "").lstrip("/")
        parts = PurePosixPath(rel_path).parts
        directory = parts[0] if len(parts) > 1 else "root"

        dir_groups.setdefault(directory, []).append({
            "name": node.qualified_name,
            "type": node.block_type,
            "item_id": node.item_id,
        })

    # Build cross-directory import map
    dir_edges: dict[tuple[str, str], int] = {}
    for edge in graph.edges:
        src_node = graph.nodes.get(edge.source_id)
        tgt_node = graph.nodes.get(edge.target_id)
        if not src_node or not tgt_node:
            continue

        src_rel = src_node.file_path.replace(source_dir, "").lstrip("/")
        tgt_rel = tgt_node.file_path.replace(source_dir, "").lstrip("/")
        src_parts = PurePosixPath(src_rel).parts
        tgt_parts = PurePosixPath(tgt_rel).parts
        src_dir = src_parts[0] if len(src_parts) > 1 else "root"
        tgt_dir = tgt_parts[0] if len(tgt_parts) > 1 else "root"

        if src_dir != tgt_dir:
            key = (src_dir, tgt_dir)
            dir_edges[key] = dir_edges.get(key, 0) + 1

    # Generate Mermaid diagram
    mermaid_lines = ["graph LR"]

    # Sanitize names for mermaid
    def safe_id(name: str) -> str:
        return re.sub(r'[^a-zA-Z0-9_]', '_', name)

    for directory, items in sorted(dir_groups.items()):
        sid = safe_id(directory)
        mermaid_lines.append(f'    {sid}["{directory}<br/>{len(items)} items"]')

    for (src, tgt), count in sorted(dir_edges.items()):
        src_id = safe_id(src)
        tgt_id = safe_id(tgt)
        mermaid_lines.append(f'    {src_id} -->|{count}| {tgt_id}')

    mermaid = "\n".join(mermaid_lines)

    # Build module list
    modules = [
        {
            "directory": directory,
            "item_count": len(items),
            "items": sorted(items, key=lambda x: x["name"]),
        }
        for directory, items in sorted(dir_groups.items())
    ]

    return {"mermaid": mermaid, "modules": modules}
