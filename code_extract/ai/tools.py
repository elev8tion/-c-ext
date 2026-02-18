"""Agentic AI tool definitions and handlers for the copilot."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Tool Definitions (OpenAI-compatible function calling schema) ────────

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    # --- Data tools (server-side execution) ---
    {
        "type": "function",
        "function": {
            "name": "search_items",
            "description": "Search for code items (functions, classes, components) in the scanned project by name. Supports fuzzy matching.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (name or partial name)"},
                    "type": {"type": "string", "description": "Filter by block type (function, class, component, etc.)"},
                    "language": {"type": "string", "description": "Filter by language (python, javascript, etc.)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_item_code",
            "description": "Get the source code of a specific code item by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {"type": "string", "description": "Name of the item to retrieve code for"},
                },
                "required": ["item_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_health_summary",
            "description": "Get the codebase health summary including score, long functions, duplications, and coupling issues.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_architecture_info",
            "description": "Get architecture information: module count, nodes, edges, and key statistics.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dead_code_list",
            "description": "Get list of potentially unused/dead code items with confidence scores.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dependencies",
            "description": "Get dependency information for a specific code item (what it depends on, what depends on it).",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {"type": "string", "description": "Name of the item to get dependencies for"},
                },
                "required": ["item_name"],
            },
        },
    },
    # --- UI action tools (generate frontend actions) ---
    {
        "type": "function",
        "function": {
            "name": "navigate_to_tab",
            "description": "Navigate the user interface to a specific tab (scan, catalog, architecture, health, docs, deadcode, tour, clone, boilerplate, migration, remix).",
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_name": {
                        "type": "string",
                        "description": "Tab to navigate to",
                        "enum": ["scan", "catalog", "architecture", "health", "docs",
                                 "deadcode", "tour", "clone", "boilerplate", "migration", "remix"],
                    },
                },
                "required": ["tab_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "select_items",
            "description": "Select specific code items in the scan results list by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Names of items to select",
                    },
                },
                "required": ["item_names"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_clone",
            "description": "Start the pattern clone workflow: navigate to clone tab, select source item, and fill in the new name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_name": {"type": "string", "description": "Name of the item to clone"},
                    "new_name": {"type": "string", "description": "Name for the cloned item"},
                },
                "required": ["source_name", "new_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_remix",
            "description": "Add code items to the Remix Board canvas by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Names of items to add to the remix canvas",
                    },
                },
                "required": ["item_names"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remix_build",
            "description": "Build the remix project from items currently on the canvas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string", "description": "Optional project name for the build"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_boilerplate",
            "description": "Start boilerplate detection for selected items: navigate to boilerplate tab and detect patterns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Names of items to detect boilerplate patterns for",
                    },
                },
                "required": ["item_names"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_comparison",
            "description": "Run a semantic diff comparison between two file paths.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path_a": {"type": "string", "description": "First path for comparison"},
                    "path_b": {"type": "string", "description": "Second path for comparison"},
                },
                "required": ["path_a", "path_b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_code",
            "description": "Extract or package selected code items.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Names of items to extract",
                    },
                    "package_name": {"type": "string", "description": "Optional package name for bundled export"},
                },
                "required": ["item_names"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_migrations",
            "description": "Navigate to migration tab and detect database migrations.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    # --- Data tools for tabs that were missing coverage ---
    {
        "type": "function",
        "function": {
            "name": "get_boilerplate_patterns",
            "description": "Detect boilerplate patterns in selected items and return the template code, detected variables, and pattern info. Use this before generate_boilerplate_code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Names of items to detect boilerplate patterns for. If empty, uses first 20 items.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_boilerplate_code",
            "description": "Generate code from a boilerplate template by substituting variable values. Call get_boilerplate_patterns first to get the template_code and variables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_code": {"type": "string", "description": "Template code with {{variable}} placeholders"},
                    "variables": {
                        "type": "object",
                        "description": "Variable name-value pairs to substitute into the template",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": ["template_code", "variables"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_docs_summary",
            "description": "Get auto-generated documentation for the scanned codebase. Returns module docs, sections, and summaries.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tour_steps",
            "description": "Get the codebase walkthrough tour — a guided sequence of steps explaining the project structure and key components.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_catalog",
            "description": "Get the component catalog — a categorized inventory of all classes, functions, and components in the scanned project.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_migration_pattern",
            "description": "Apply a detected migration pattern to a specific code item, transforming its code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {"type": "string", "description": "Name of the item to apply migration to"},
                    "pattern_id": {"type": "string", "description": "ID of the migration pattern to apply"},
                },
                "required": ["item_name", "pattern_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "smart_extract",
            "description": "Smart extract selected items along with all their transitive dependencies. Creates a downloadable package.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Names of items to extract with dependencies",
                    },
                },
                "required": ["item_names"],
            },
        },
    },
]

# Map tool names to handler functions
_TOOL_HANDLERS: dict[str, str] = {
    "search_items": "handle_search_items",
    "get_item_code": "handle_get_item_code",
    "get_health_summary": "handle_get_health_summary",
    "get_architecture_info": "handle_get_architecture_info",
    "get_dead_code_list": "handle_get_dead_code_list",
    "get_dependencies": "handle_get_dependencies",
    "navigate_to_tab": "handle_navigate_to_tab",
    "select_items": "handle_select_items",
    "start_clone": "handle_start_clone",
    "add_to_remix": "handle_add_to_remix",
    "remix_build": "handle_remix_build",
    "start_boilerplate": "handle_start_boilerplate",
    "run_comparison": "handle_run_comparison",
    "extract_code": "handle_extract_code",
    "detect_migrations": "handle_detect_migrations",
    "get_boilerplate_patterns": "handle_get_boilerplate_patterns",
    "generate_boilerplate_code": "handle_generate_boilerplate_code",
    "get_docs_summary": "handle_get_docs_summary",
    "get_tour_steps": "handle_get_tour_steps",
    "get_catalog": "handle_get_catalog",
    "apply_migration_pattern": "handle_apply_migration_pattern",
    "smart_extract": "handle_smart_extract",
}


# ── Shared helpers ──────────────────────────────────────────────────────

def _resolve_items(
    scan_id: str, names: list[str]
) -> list[dict[str, str]]:
    """Resolve item names to item_ids via exact → case-insensitive → substring.

    Returns list of {item_id, name, type, language, file} dicts.
    """
    from code_extract.web.state import state

    blocks = state.get_blocks_for_scan(scan_id)
    if not blocks:
        return []

    results = []
    for name in names:
        match = _find_item(blocks, name)
        if match:
            item_id, block = match
            results.append({
                "item_id": item_id,
                "name": block.item.qualified_name,
                "type": block.item.block_type.value,
                "language": block.item.language.value,
                "file": str(block.item.file_path),
            })
    return results


def _find_item(blocks: dict, name: str):
    """Find a single item by name: exact → case-insensitive → substring."""
    # Exact match on qualified_name or name
    for item_id, block in blocks.items():
        if block.item.qualified_name == name or block.item.name == name:
            return (item_id, block)

    # Case-insensitive
    lower = name.lower()
    for item_id, block in blocks.items():
        if block.item.qualified_name.lower() == lower or block.item.name.lower() == lower:
            return (item_id, block)

    # Substring
    for item_id, block in blocks.items():
        if lower in block.item.qualified_name.lower() or lower in block.item.name.lower():
            return (item_id, block)

    return None


# ── Data tool handlers ──────────────────────────────────────────────────

def handle_search_items(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Search for items by name, optionally filtered by type/language."""
    from code_extract.web.state import state

    query = args.get("query", "").lower()
    type_filter = args.get("type", "").lower()
    lang_filter = args.get("language", "").lower()
    blocks = state.get_blocks_for_scan(scan_id)
    if not blocks:
        return json.dumps({"items": [], "message": "No blocks extracted yet"}), []

    matches = []
    for item_id, block in blocks.items():
        name = block.item.qualified_name.lower()
        if query not in name and query not in block.item.name.lower():
            continue
        if type_filter and block.item.block_type.value.lower() != type_filter:
            continue
        if lang_filter and block.item.language.value.lower() != lang_filter:
            continue
        matches.append({
            "item_id": item_id,
            "name": block.item.qualified_name,
            "type": block.item.block_type.value,
            "language": block.item.language.value,
            "file": str(block.item.file_path),
        })
        if len(matches) >= 20:
            break

    return json.dumps({"items": matches, "count": len(matches)}), []


def handle_get_item_code(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Get source code for a named item."""
    from code_extract.web.state import state

    name = args.get("item_name", "")
    blocks = state.get_blocks_for_scan(scan_id)
    if not blocks:
        return json.dumps({"error": "No blocks extracted"}), []

    match = _find_item(blocks, name)
    if not match:
        return json.dumps({"error": f"Item '{name}' not found"}), []

    item_id, block = match
    code = block.source_code[:3000]
    return json.dumps({
        "item_id": item_id,
        "name": block.item.qualified_name,
        "type": block.item.block_type.value,
        "language": block.item.language.value,
        "file": str(block.item.file_path),
        "code": code,
    }), []


def handle_get_health_summary(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Get codebase health summary."""
    from code_extract.web.state import state

    health = state.get_analysis(scan_id, "health")
    if not health:
        return json.dumps({"error": "Health analysis not available. Run a scan first."}), []

    summary = {
        "score": health.get("score", "N/A"),
        "long_functions": len(health.get("long_functions", [])),
        "duplications": len(health.get("duplications", [])),
        "high_coupling": len(health.get("coupling", [])),
    }
    # Include top issues
    if health.get("long_functions"):
        summary["top_long_functions"] = [
            {"name": f["name"], "lines": f["line_count"]}
            for f in health["long_functions"][:5]
        ]
    if health.get("duplications"):
        summary["top_duplications"] = [
            {"item_a": d["item_a"], "item_b": d["item_b"],
             "similarity": round(d["similarity"], 2)}
            for d in health["duplications"][:5]
        ]
    return json.dumps(summary), []


def handle_get_architecture_info(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Get architecture/module information."""
    from code_extract.web.state import state

    arch = state.get_analysis(scan_id, "architecture")
    if not arch:
        return json.dumps({"error": "Architecture analysis not available."}), []

    stats = arch.get("stats", {})
    modules = arch.get("modules", [])
    summary = {
        "total_items": stats.get("total_items", 0),
        "total_edges": stats.get("total_edges", 0),
        "total_modules": stats.get("total_modules", 0),
        "cross_module_edges": stats.get("cross_module_edges", 0),
        "modules": [
            {"directory": m["directory"], "item_count": m["item_count"]}
            for m in modules[:10]
        ],
    }
    return json.dumps(summary), []


def handle_get_dead_code_list(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Get dead/unused code items."""
    from code_extract.web.state import state

    dead = state.get_analysis(scan_id, "dead_code")
    if not dead:
        return json.dumps({"error": "Dead code analysis not available."}), []

    items = [
        {"name": d["name"], "type": d["type"], "file": d["file"],
         "confidence": round(d["confidence"], 2)}
        for d in (dead if isinstance(dead, list) else [])[:15]
    ]
    return json.dumps({"items": items, "count": len(dead) if isinstance(dead, list) else 0}), []


def handle_get_dependencies(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Get dependencies for a specific item."""
    from code_extract.web.state import state

    name = args.get("item_name", "")
    blocks = state.get_blocks_for_scan(scan_id)
    graph = state.get_analysis(scan_id, "graph")
    if not blocks or not graph:
        return json.dumps({"error": "Dependency data not available."}), []

    match = _find_item(blocks, name)
    if not match:
        return json.dumps({"error": f"Item '{name}' not found"}), []

    item_id = match[0]
    forward = list(graph.forward.get(item_id, set()))[:20]
    reverse = list(graph.reverse.get(item_id, set()))[:20]

    def _name_for_id(iid):
        b = blocks.get(iid)
        return b.item.qualified_name if b else iid

    return json.dumps({
        "item": match[1].item.qualified_name,
        "depends_on": [_name_for_id(i) for i in forward],
        "depended_by": [_name_for_id(i) for i in reverse],
    }), []


# ── UI action tool handlers ────────────────────────────────────────────

def handle_navigate_to_tab(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Navigate to a UI tab."""
    tab = args.get("tab_name", "scan")
    return f"Navigating to {tab} tab.", [{"type": "navigate", "tab": tab}]


def handle_select_items(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Select items in the scan list."""
    names = args.get("item_names", [])
    resolved = _resolve_items(scan_id, names)
    if not resolved:
        return f"Could not find items: {', '.join(names)}", []
    item_ids = [r["item_id"] for r in resolved]
    item_names = [r["name"] for r in resolved]
    return (
        f"Selected {len(resolved)} item(s): {', '.join(item_names)}",
        [{"type": "select", "item_ids": item_ids, "item_names": item_names}],
    )


def handle_start_clone(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Start the clone workflow: navigate → fill source → fill name → preview."""
    source_name = args.get("source_name", "")
    new_name = args.get("new_name", "")
    resolved = _resolve_items(scan_id, [source_name])
    if not resolved:
        return f"Could not find item '{source_name}' to clone.", []

    source = resolved[0]
    actions = [
        {"type": "navigate", "tab": "clone"},
        {"type": "fill", "selector": "#clone-item-select", "value": source["item_id"]},
        {"type": "fill", "selector": "#clone-new-name", "value": new_name},
        {"type": "click", "function": "previewClone"},
    ]
    return (
        f"Starting clone of '{source['name']}' as '{new_name}'.",
        actions,
    )


def handle_add_to_remix(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Add items to the remix canvas."""
    names = args.get("item_names", [])
    resolved = _resolve_items(scan_id, names)
    if not resolved:
        return f"Could not find items: {', '.join(names)}", []

    actions: list[dict] = [{"type": "navigate", "tab": "remix"}]
    for item in resolved:
        actions.append({
            "type": "remix_add",
            "scan_id": scan_id,
            "item_id": item["item_id"],
            "name": item["name"],
            "item_type": item["type"],
            "language": item["language"],
        })

    item_names = [r["name"] for r in resolved]
    return (
        f"Adding {len(resolved)} item(s) to remix: {', '.join(item_names)}",
        actions,
    )


def handle_remix_build(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Build the remix project."""
    project_name = args.get("project_name", "")
    actions: list[dict] = [
        {"type": "click", "function": "remixCheckCompatibility"},
        {"type": "click", "function": "remixBuild"},
    ]
    if project_name:
        actions.insert(0, {"type": "fill", "selector": "#remix-project-name", "value": project_name})
    return "Building remix project.", actions


def handle_start_boilerplate(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Start boilerplate detection for items."""
    names = args.get("item_names", [])
    resolved = _resolve_items(scan_id, names)
    if not resolved:
        return f"Could not find items: {', '.join(names)}", []

    item_ids = [r["item_id"] for r in resolved]
    actions = [
        {"type": "select", "item_ids": item_ids, "item_names": [r["name"] for r in resolved]},
        {"type": "navigate", "tab": "boilerplate"},
        {"type": "click", "function": "detectBoilerplate"},
    ]
    return f"Detecting boilerplate patterns for {len(resolved)} item(s).", actions


def handle_run_comparison(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Run semantic diff comparison."""
    path_a = args.get("path_a", "")
    path_b = args.get("path_b", "")
    actions = [
        {"type": "navigate", "tab": "diff"},
        {"type": "fill", "selector": "#diff-path-a", "value": path_a},
        {"type": "fill", "selector": "#diff-path-b", "value": path_b},
        {"type": "click", "function": "runDiff"},
    ]
    return f"Running comparison between '{path_a}' and '{path_b}'.", actions


def handle_extract_code(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Extract/package selected code items."""
    names = args.get("item_names", [])
    package_name = args.get("package_name", "")
    resolved = _resolve_items(scan_id, names)
    if not resolved:
        return f"Could not find items: {', '.join(names)}", []

    item_ids = [r["item_id"] for r in resolved]
    actions: list[dict] = [
        {"type": "select", "item_ids": item_ids, "item_names": [r["name"] for r in resolved]},
    ]
    if package_name:
        actions.append({"type": "click", "function": "showPackagePopover"})
        actions.append({"type": "fill", "selector": "#package-name-input", "value": package_name})
        actions.append({"type": "click", "function": "confirmPackage"})
    else:
        actions.append({"type": "click", "function": "extract"})

    return f"Extracting {len(resolved)} item(s).", actions


def handle_detect_migrations(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Navigate to migration detection."""
    actions = [
        {"type": "navigate", "tab": "migration"},
        {"type": "click", "function": "detectMigrations"},
    ]
    return "Detecting database migrations.", actions


# ── Boilerplate data tools ────────────────────────────────────────────

def handle_get_boilerplate_patterns(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Detect boilerplate patterns and return template + pattern data."""
    from code_extract.web.state import state
    from code_extract.analysis.boilerplate import detect_patterns, generate_template

    blocks = state.get_blocks_for_scan(scan_id)
    if not blocks:
        return json.dumps({"error": "No blocks extracted"}), []

    names = args.get("item_names", [])
    if names:
        resolved = _resolve_items(scan_id, names)
        item_ids = [r["item_id"] for r in resolved]
    else:
        item_ids = list(blocks.keys())[:20]

    selected = [blocks[iid] for iid in item_ids if iid in blocks]
    if not selected:
        return json.dumps({"error": "No matching items found"}), []

    template_name = args.get("template_name", "template")
    template = generate_template(selected, template_name)
    patterns = detect_patterns(blocks)

    result = {
        "template_code": template.get("source_code", "")[:2000],
        "variables": template.get("variables", []),
        "language": template.get("config", {}).get("language", "text"),
        "patterns_found": len(patterns),
        "patterns": [
            {"directory": p.get("directory", ""),
             "block_type": p.get("block_type", ""),
             "count": p.get("count", 0)}
            for p in patterns[:5]
        ],
    }
    return json.dumps(result), [{"type": "navigate", "tab": "boilerplate"}]


def handle_generate_boilerplate_code(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Generate code from a boilerplate template with variable substitution."""
    from code_extract.analysis.boilerplate import apply_template

    template_code = args.get("template_code", "")
    variables = args.get("variables", {})

    if not template_code:
        return json.dumps({"error": "template_code is required"}), []

    generated = apply_template(template_code, variables)
    return json.dumps({"generated_code": generated[:3000]}), []


# ── Docs / Tour / Catalog data tools ──────────────────────────────────

def handle_get_docs_summary(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Get auto-generated documentation summary."""
    from code_extract.web.state import state

    docs = state.get_analysis(scan_id, "docs")
    if not docs:
        return json.dumps({
            "error": "Documentation not generated yet. Navigate to the docs tab to generate.",
        }), [{"type": "navigate", "tab": "docs"}]

    modules = docs.get("modules", [])
    summary = {
        "total_modules": len(modules),
        "modules": [
            {"name": m.get("name", ""), "item_count": len(m.get("items", []))}
            for m in modules[:10]
        ],
    }
    return json.dumps(summary), []


def handle_get_tour_steps(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Get codebase walkthrough tour steps."""
    from code_extract.web.state import state

    tour = state.get_analysis(scan_id, "tour")
    if not tour:
        return json.dumps({
            "error": "Tour not generated yet. Navigate to the tour tab to generate.",
        }), [{"type": "navigate", "tab": "tour"}]

    steps = tour.get("steps", [])
    summary = {
        "total_steps": len(steps),
        "steps": [
            {"title": s.get("title", ""),
             "description": s.get("description", "")[:200]}
            for s in steps[:10]
        ],
    }
    return json.dumps(summary), []


def handle_get_catalog(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Get component catalog."""
    from code_extract.web.state import state

    catalog = state.get_analysis(scan_id, "catalog")
    if not catalog:
        return json.dumps({
            "error": "Catalog not built yet. Navigate to the catalog tab to build.",
        }), [{"type": "navigate", "tab": "catalog"}]

    items = catalog if isinstance(catalog, list) else []
    summary = {
        "total_items": len(items),
        "items": [
            {"name": i.get("name", ""),
             "type": i.get("type", ""),
             "language": i.get("language", "")}
            for i in items[:15]
        ],
    }
    return json.dumps(summary), []


# ── Migration apply + smart extract ───────────────────────────────────

def handle_apply_migration_pattern(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Apply a migration pattern to a specific item."""
    from code_extract.web.state import state
    from code_extract.analysis.migration import apply_migration

    name = args.get("item_name", "")
    pattern_id = args.get("pattern_id", "")

    blocks = state.get_blocks_for_scan(scan_id)
    if not blocks:
        return json.dumps({"error": "No blocks extracted"}), []

    match = _find_item(blocks, name)
    if not match:
        return json.dumps({"error": f"Item '{name}' not found"}), []

    item_id, block = match
    try:
        result = apply_migration(block, pattern_id)
        return json.dumps({
            "item": block.item.qualified_name,
            "pattern_id": pattern_id,
            "result": result if isinstance(result, dict) else {"transformed": str(result)[:2000]},
        }), [{"type": "navigate", "tab": "migration"}]
    except Exception as e:
        return json.dumps({"error": f"Migration failed: {e}"}), []


def handle_smart_extract(scan_id: str, args: dict) -> tuple[str, list[dict]]:
    """Smart extract items with transitive dependencies."""
    names = args.get("item_names", [])
    resolved = _resolve_items(scan_id, names)
    if not resolved:
        return f"Could not find items: {', '.join(names)}", []

    item_ids = [r["item_id"] for r in resolved]
    item_names = [r["name"] for r in resolved]
    actions = [
        {"type": "select", "item_ids": item_ids, "item_names": item_names},
        {"type": "click", "function": "smartExtract"},
    ]
    return f"Smart extracting {len(resolved)} item(s) with dependencies: {', '.join(item_names)}", actions


# ── Dispatcher ──────────────────────────────────────────────────────────

def execute_tool(
    tool_name: str, scan_id: str, arguments: dict
) -> tuple[str, list[dict]]:
    """Execute a tool by name and return (result_text, actions)."""
    handler_name = _TOOL_HANDLERS.get(tool_name)
    if not handler_name:
        return json.dumps({"error": f"Unknown tool: {tool_name}"}), []

    handler = globals().get(handler_name)
    if not handler:
        return json.dumps({"error": f"Handler not found: {handler_name}"}), []

    try:
        return handler(scan_id, arguments)
    except Exception as e:
        logger.exception("Tool execution error: %s", tool_name)
        return json.dumps({"error": f"Tool error: {e}"}), []
