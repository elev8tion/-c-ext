"""Dead code detector — finds items with zero reverse dependencies."""

from __future__ import annotations

from code_extract.analysis.graph_models import DependencyGraph

# Names that suggest entry points (not dead code)
_ENTRY_POINT_PATTERNS = {
    "main", "app", "index", "setup", "configure", "init",
    "__init__", "__main__", "run", "start", "serve",
}


def detect_dead_code(graph: DependencyGraph) -> list[dict]:
    """Detect potentially dead (unreferenced) code items.

    Returns list of dicts: {item_id, name, type, file, confidence, reason}
    """
    results: list[dict] = []

    for item_id, node in graph.nodes.items():
        referrers = graph.reverse.get(item_id, [])
        if len(referrers) > 0:
            continue

        # This item has zero incoming references — potentially dead
        confidence = 0.9
        reason = "No references found"

        name_lower = node.qualified_name.lower().split(".")[-1]

        # Lower confidence for entry-point-like names
        if name_lower in _ENTRY_POINT_PATTERNS:
            confidence = 0.2
            reason = "Likely entry point"

        # Lower confidence for public-looking items (no underscore prefix)
        if not name_lower.startswith("_"):
            confidence = min(confidence, 0.8)

        # Lower confidence for test-like items
        if "test" in name_lower:
            confidence = 0.3
            reason = "Appears to be a test"

        # HTML structural blocks are containers, not independently referenced
        if node.block_type in ("script_block", "style_block"):
            confidence = 0.2
            reason = "HTML structural block"

        # Methods are expected to be called externally
        if node.block_type == "method":
            confidence = min(confidence, 0.5)
            reason = "Method — may be called via instance"

        # Constructors / __init__
        if name_lower in ("__init__", "constructor", "build"):
            confidence = 0.1
            reason = "Constructor — called implicitly"

        results.append({
            "item_id": item_id,
            "name": node.qualified_name,
            "type": node.block_type,
            "file": node.file_path,
            "confidence": round(confidence, 2),
            "reason": reason,
        })

    # Sort by confidence descending
    results.sort(key=lambda x: -x["confidence"])
    return results
