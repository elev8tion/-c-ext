"""Codebase tour generator — traces import chains from entry points."""

from __future__ import annotations

from collections import deque

from code_extract.models import ExtractedBlock
from code_extract.analysis.graph_models import DependencyGraph

# Common entry-point names
_ENTRY_NAMES = {
    "main", "app", "index", "setup", "run", "start", "serve",
    "__main__", "__init__", "Application", "App",
}


def generate_tour(
    blocks: dict[str, ExtractedBlock],
    graph: DependencyGraph,
) -> dict:
    """Generate a step-by-step codebase tour.

    Returns: {steps: [{name, type, language, description, code, file, dependencies}]}
    """
    # Find entry points
    entry_ids = _find_entry_points(blocks, graph)

    if not entry_ids:
        # Fall back to items with most outgoing deps
        entry_ids = _find_most_connected(graph)

    if not entry_ids:
        # Fall back to first items
        entry_ids = list(blocks.keys())[:5]

    # BFS from entry points to build tour order
    visited: set[str] = set()
    tour_order: list[str] = []
    queue = deque(entry_ids)

    while queue and len(tour_order) < 30:  # cap at 30 steps
        item_id = queue.popleft()
        if item_id in visited:
            continue
        visited.add(item_id)
        tour_order.append(item_id)

        # Add dependencies to queue
        for dep_id in graph.forward.get(item_id, []):
            if dep_id not in visited:
                queue.append(dep_id)

    # Build step objects
    steps: list[dict] = []
    for item_id in tour_order:
        block = blocks.get(item_id)
        if not block:
            continue

        deps = []
        for dep_id in graph.forward.get(item_id, []):
            dep_block = blocks.get(dep_id)
            if dep_block:
                deps.append(dep_block.item.qualified_name)

        description = _generate_description(block)

        steps.append({
            "item_id": item_id,
            "name": block.item.qualified_name,
            "type": block.item.block_type.value,
            "language": block.item.language.value,
            "description": description,
            "code": block.source_code[:2000],
            "file": str(block.item.file_path),
            "dependencies": deps[:10],
        })

    return {"steps": steps}


def _find_entry_points(
    blocks: dict[str, ExtractedBlock],
    graph: DependencyGraph,
) -> list[str]:
    """Find likely entry points — items named main/app/index with few incoming deps."""
    candidates: list[tuple[str, int]] = []

    for item_id, block in blocks.items():
        name = block.item.name.lower()
        if name in _ENTRY_NAMES or any(ep in name for ep in ("main", "app", "index")):
            # Score: fewer incoming deps = more likely entry point
            incoming = len(graph.reverse.get(item_id, []))
            candidates.append((item_id, incoming))

    candidates.sort(key=lambda x: x[1])
    return [c[0] for c in candidates[:5]]


def _find_most_connected(graph: DependencyGraph) -> list[str]:
    """Find items with the most outgoing connections (likely important)."""
    scores = [
        (item_id, len(graph.forward.get(item_id, [])))
        for item_id in graph.nodes
    ]
    scores.sort(key=lambda x: -x[1])
    return [s[0] for s in scores[:5]]


def _generate_description(block: ExtractedBlock) -> str:
    """Generate a template-based description from AST metadata."""
    bt = block.item.block_type.value
    name = block.item.qualified_name
    lang = block.item.language.value

    # Check for docstring
    code = block.source_code
    import re
    # Python docstring
    m = re.search(r'"""(.*?)"""', code, re.DOTALL)
    if m:
        first_line = m.group(1).strip().splitlines()[0]
        if first_line:
            return first_line

    # JSDoc
    m = re.search(r'/\*\*(.*?)\*/', code, re.DOTALL)
    if m:
        desc = m.group(1).strip()
        lines = [l.strip().lstrip("* ").strip() for l in desc.splitlines()]
        lines = [l for l in lines if l and not l.startswith("@")]
        if lines:
            return lines[0]

    # Template-based descriptions
    templates = {
        "class": f"The {name} class provides core functionality in the {lang} codebase.",
        "function": f"The {name} function handles a specific operation.",
        "method": f"The {name} method implements behavior for its parent class.",
        "widget": f"The {name} widget renders a UI component.",
        "component": f"The {name} component renders a UI element.",
        "struct": f"The {name} struct defines a data structure.",
        "interface": f"The {name} interface defines a contract for implementations.",
        "enum": f"The {name} enum defines a set of named constants.",
        "module": f"The {name} module organizes related functionality.",
        "mixin": f"The {name} mixin provides reusable behavior.",
    }

    return templates.get(bt, f"{name} ({bt}) in the {lang} codebase.")
