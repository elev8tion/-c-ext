"""Bridge between legacy tool handlers (tools.py) and the new ToolSystem.

Wraps each of the 22 legacy handlers for registry compatibility while
preserving the OpenAI function-calling schemas verbatim.  Unlike the
generic tool_migration discovery layer, this module knows exactly which
tools to register and avoids picking up helper functions.
"""

from __future__ import annotations

import logging
from typing import Any

from .tool_registry import ToolRegistry, ToolCategory, ToolMetadata

logger = logging.getLogger(__name__)

# ── Category mapping for all 22 legacy tools ──────────────────────────

_TOOL_CATEGORIES: dict[str, ToolCategory] = {
    # Data queries
    "search_items": ToolCategory.DATA_QUERIES,
    "get_item_code": ToolCategory.DATA_QUERIES,
    "get_health_summary": ToolCategory.DATA_QUERIES,
    "get_architecture_info": ToolCategory.DATA_QUERIES,
    "get_dead_code_list": ToolCategory.DATA_QUERIES,
    "get_dependencies": ToolCategory.DATA_QUERIES,
    "get_boilerplate_patterns": ToolCategory.DATA_QUERIES,
    "get_docs_summary": ToolCategory.DATA_QUERIES,
    "get_tour_steps": ToolCategory.DATA_QUERIES,
    "get_catalog": ToolCategory.DATA_QUERIES,
    # UI operations
    "navigate_to_tab": ToolCategory.UI_OPERATIONS,
    "select_items": ToolCategory.UI_OPERATIONS,
    # Workflows
    "start_clone": ToolCategory.WORKFLOW,
    "add_to_remix": ToolCategory.WORKFLOW,
    "remix_build": ToolCategory.WORKFLOW,
    "start_boilerplate": ToolCategory.WORKFLOW,
    "run_comparison": ToolCategory.WORKFLOW,
    "detect_migrations": ToolCategory.WORKFLOW,
    # Boilerplate
    "generate_boilerplate_code": ToolCategory.BOILERPLATE,
    # Migration
    "apply_migration_pattern": ToolCategory.MIGRATION,
    # Extraction
    "extract_code": ToolCategory.EXTRACTION,
    "smart_extract": ToolCategory.EXTRACTION,
}

# Cached OpenAI tool definitions after initialization
_openai_tool_defs: list[dict[str, Any]] | None = None


# ── Wrapper factory ───────────────────────────────────────────────────

def _make_legacy_wrapper(handler_func, tool_name: str):
    """Wrap a legacy handler ``(scan_id, args) -> (str, list)`` for registry.

    The registry calls ``func(**arguments)`` so the wrapper accepts
    ``scan_id`` as a keyword arg and forwards the remaining kwargs as
    the ``args`` dict expected by legacy handlers.
    """
    def wrapper(scan_id: str = "", **kwargs) -> tuple[str, list]:
        return handler_func(scan_id, kwargs)

    wrapper.__name__ = tool_name
    wrapper.__qualname__ = tool_name
    wrapper.__doc__ = handler_func.__doc__ or f"Legacy tool: {tool_name}"
    return wrapper


# ── Registration ──────────────────────────────────────────────────────

def register_legacy_tools(registry: ToolRegistry) -> dict[str, dict]:
    """Register all 22 legacy tool handlers into *registry*.

    Returns a ``{tool_name: openai_schema}`` mapping for the tools that
    were successfully registered.
    """
    from .tools import TOOL_DEFINITIONS, _TOOL_HANDLERS
    import code_extract.ai.tools as tools_module

    registered: dict[str, dict] = {}

    for tool_def in TOOL_DEFINITIONS:
        fn_def = tool_def["function"]
        name = fn_def["name"]
        description = fn_def["description"]

        handler_name = _TOOL_HANDLERS.get(name)
        if not handler_name:
            logger.warning("No handler mapping for tool '%s', skipping", name)
            continue

        handler = getattr(tools_module, handler_name, None)
        if not handler:
            logger.warning("Handler '%s' not found, skipping", handler_name)
            continue

        category = _TOOL_CATEGORIES.get(name, ToolCategory.GENERAL)
        wrapper = _make_legacy_wrapper(handler, name)

        # Register directly via ToolMetadata to avoid the decorator's
        # introspection treating **kwargs as a required parameter.
        metadata = ToolMetadata(
            name=name,
            function=wrapper,
            description=description,
            parameters={"scan_id": {"type": "str", "description": "Scan session ID", "default": ""}},
            required_params=[],
            returns={"type": "tuple", "description": "(result_text, actions)"},
            category=category.value,
        )
        registry._tools[name] = metadata
        registry._categories[category].append(name)

        registered[name] = tool_def
        logger.debug("Registered legacy tool: %s [%s]", name, category.value)

    logger.info("Registered %d legacy tools in registry", len(registered))
    return registered


# ── Public helpers ────────────────────────────────────────────────────

def get_openai_tool_definitions() -> list[dict[str, Any]]:
    """Return the OpenAI function-calling schema list.

    After ``create_integrated_tool_system()`` has been called the cached
    definitions are returned.  Before initialisation this falls back to
    the raw ``TOOL_DEFINITIONS`` from ``tools.py``.
    """
    if _openai_tool_defs is not None:
        return _openai_tool_defs
    from .tools import TOOL_DEFINITIONS
    return TOOL_DEFINITIONS


def create_integrated_tool_system():
    """Create a ToolSystem with all 22 legacy tools registered.

    Returns:
        ``(ToolSystem, IntelligenceLayer)`` tuple.
    """
    global _openai_tool_defs

    from .tool_system import ToolSystem, ToolSystemConfig
    from .tool_intelligence import IntelligenceLayer

    config = ToolSystemConfig(
        auto_discover_tools=False,
        auto_migrate_legacy=False,
        enable_health_monitoring=True,
        enable_execution_history=True,
    )

    system = ToolSystem(config)
    tool_defs = register_legacy_tools(system.registry)
    _openai_tool_defs = list(tool_defs.values())

    intelligence = IntelligenceLayer(system)

    logger.info(
        "Integrated tool system created: %d tools, intelligence enabled",
        len(tool_defs),
    )
    return system, intelligence
