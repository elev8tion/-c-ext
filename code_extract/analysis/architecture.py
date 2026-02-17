"""Architecture snapshot — groups items by directory, generates Cytoscape.js graph data."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from code_extract.analysis.graph_models import DependencyGraph


def _safe_id(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_]', '_', name)


def generate_architecture(graph: DependencyGraph, source_dir: str = "") -> dict:
    """Generate architecture data for Cytoscape.js rendering.

    Returns: {elements: [...], modules: [...], stats: {...}}
    """
    # ── Group nodes by directory ──
    dir_groups: dict[str, list[dict]] = {}
    node_dir_map: dict[str, str] = {}  # item_id -> directory

    for node in graph.nodes.values():
        rel_path = node.file_path.replace(source_dir, "").lstrip("/")
        parts = PurePosixPath(rel_path).parts
        directory = parts[0] if len(parts) > 1 else "root"

        dir_groups.setdefault(directory, []).append({
            "name": node.qualified_name,
            "type": node.block_type,
            "item_id": node.item_id,
            "file_path": rel_path,
        })
        node_dir_map[node.item_id] = directory

    # ── Compute per-item connection counts for ranking ──
    conn_count: dict[str, int] = {}
    for edge in graph.edges:
        conn_count[edge.source_id] = conn_count.get(edge.source_id, 0) + 1
        conn_count[edge.target_id] = conn_count.get(edge.target_id, 0) + 1

    # ── Build cross-directory edge counts ──
    dir_edges: dict[tuple[str, str], int] = {}
    for edge in graph.edges:
        src_dir = node_dir_map.get(edge.source_id)
        tgt_dir = node_dir_map.get(edge.target_id)
        if src_dir and tgt_dir and src_dir != tgt_dir:
            key = (src_dir, tgt_dir)
            dir_edges[key] = dir_edges.get(key, 0) + 1

    # ── Build Cytoscape elements ──
    elements: list[dict] = []
    MAX_ITEMS_PER_DIR = 15

    for directory, items in sorted(dir_groups.items()):
        dir_id = f"dir-{_safe_id(directory)}"

        # Directory as compound (parent) node
        elements.append({
            "data": {
                "id": dir_id,
                "label": f"{directory}/",
                "type": "module",
                "itemCount": len(items),
            }
        })

        # Rank items by connectivity, take top N
        ranked = sorted(items, key=lambda x: conn_count.get(x["item_id"], 0), reverse=True)
        shown = ranked[:MAX_ITEMS_PER_DIR]

        for item in shown:
            elements.append({
                "data": {
                    "id": item["item_id"],
                    "label": item["name"],
                    "type": item["type"],
                    "parent": dir_id,
                    "file": item["file_path"],
                    "connections": conn_count.get(item["item_id"], 0),
                }
            })

        # If items were truncated, add a summary node
        remaining = len(items) - len(shown)
        if remaining > 0:
            elements.append({
                "data": {
                    "id": f"{dir_id}-more",
                    "label": f"+{remaining} more",
                    "type": "overflow",
                    "parent": dir_id,
                    "connections": 0,
                }
            })

    # ── Build edges (only between shown items) ──
    shown_ids = {e["data"]["id"] for e in elements if "parent" in e.get("data", {})}

    for edge in graph.edges:
        if edge.source_id in shown_ids and edge.target_id in shown_ids:
            elements.append({
                "data": {
                    "source": edge.source_id,
                    "target": edge.target_id,
                    "edgeType": edge.edge_type,
                    "label": edge.reference_name,
                }
            })

    # ── Also add cross-directory summary edges (between dir nodes) ──
    for (src_dir, tgt_dir), count in sorted(dir_edges.items()):
        src_id = f"dir-{_safe_id(src_dir)}"
        tgt_id = f"dir-{_safe_id(tgt_dir)}"
        elements.append({
            "data": {
                "source": src_id,
                "target": tgt_id,
                "edgeType": "cross_module",
                "label": str(count),
                "weight": count,
            }
        })

    # ── Build module list ──
    modules = [
        {
            "directory": directory,
            "item_count": len(items),
            "items": sorted(items, key=lambda x: x["name"]),
        }
        for directory, items in sorted(dir_groups.items())
    ]

    # ── Stats ──
    stats = {
        "total_items": len(graph.nodes),
        "total_edges": len(graph.edges),
        "total_modules": len(dir_groups),
        "cross_module_edges": sum(dir_edges.values()),
    }

    return {"elements": elements, "modules": modules, "stats": stats}
