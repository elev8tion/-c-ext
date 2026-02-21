"""Tests for the tool bridge — legacy handler ↔ ToolSystem integration."""

import json
from unittest.mock import patch, MagicMock

import pytest

from code_extract.ai.tool_registry import ToolRegistry, ToolCategory
from code_extract.ai.tool_bridge import (
    _TOOL_CATEGORIES,
    _make_legacy_wrapper,
    register_legacy_tools,
    get_openai_tool_definitions,
    create_integrated_tool_system,
)
from code_extract.ai.tools import TOOL_DEFINITIONS, _TOOL_HANDLERS


# ── Category map tests ────────────────────────────────────────────────


class TestToolCategories:
    def test_all_22_tools_mapped(self):
        """Every handler in _TOOL_HANDLERS has a category mapping."""
        for name in _TOOL_HANDLERS:
            assert name in _TOOL_CATEGORIES, f"Missing category for '{name}'"

    def test_no_extra_mappings(self):
        """No stale category entries for tools that don't exist."""
        for name in _TOOL_CATEGORIES:
            assert name in _TOOL_HANDLERS, f"Stale category for '{name}'"

    def test_category_values(self):
        """Spot-check a few known categories."""
        assert _TOOL_CATEGORIES["search_items"] == ToolCategory.DATA_QUERIES
        assert _TOOL_CATEGORIES["navigate_to_tab"] == ToolCategory.UI_OPERATIONS
        assert _TOOL_CATEGORIES["start_clone"] == ToolCategory.WORKFLOW
        assert _TOOL_CATEGORIES["extract_code"] == ToolCategory.EXTRACTION
        assert _TOOL_CATEGORIES["generate_boilerplate_code"] == ToolCategory.BOILERPLATE
        assert _TOOL_CATEGORIES["apply_migration_pattern"] == ToolCategory.MIGRATION


# ── Wrapper tests ─────────────────────────────────────────────────────


class TestMakeLegacyWrapper:
    def test_wrapper_calls_handler_correctly(self):
        """Wrapper translates (scan_id=, **kwargs) → handler(scan_id, args)."""
        calls = []

        def mock_handler(scan_id, args):
            calls.append((scan_id, args))
            return "ok", [{"type": "test"}]

        wrapper = _make_legacy_wrapper(mock_handler, "test_tool")
        result = wrapper(scan_id="s1", query="hello", limit=5)

        assert result == ("ok", [{"type": "test"}])
        assert len(calls) == 1
        assert calls[0] == ("s1", {"query": "hello", "limit": 5})

    def test_wrapper_default_scan_id(self):
        """scan_id defaults to empty string."""
        def mock_handler(scan_id, args):
            return scan_id, []

        wrapper = _make_legacy_wrapper(mock_handler, "test")
        text, actions = wrapper(foo="bar")
        assert text == ""

    def test_wrapper_preserves_name(self):
        def handler(scan_id, args):
            return "", []

        wrapper = _make_legacy_wrapper(handler, "my_tool")
        assert wrapper.__name__ == "my_tool"

    def test_wrapper_preserves_docstring(self):
        def handler(scan_id, args):
            """Original doc."""
            return "", []

        wrapper = _make_legacy_wrapper(handler, "t")
        assert wrapper.__doc__ == "Original doc."


# ── Registration tests ────────────────────────────────────────────────


class TestRegisterLegacyTools:
    def test_registers_all_22_tools(self):
        registry = ToolRegistry()
        registered = register_legacy_tools(registry)
        assert len(registered) == 22

    def test_all_tool_names_present(self):
        registry = ToolRegistry()
        register_legacy_tools(registry)
        all_tools = registry.get_all_tools()
        for name in _TOOL_HANDLERS:
            assert name in all_tools, f"'{name}' not registered"

    def test_returns_openai_schemas(self):
        registry = ToolRegistry()
        registered = register_legacy_tools(registry)
        for name, schema in registered.items():
            assert "type" in schema
            assert schema["type"] == "function"
            assert "function" in schema
            assert schema["function"]["name"] == name

    def test_categories_assigned_correctly(self):
        registry = ToolRegistry()
        register_legacy_tools(registry)
        tool = registry.get_tool("navigate_to_tab")
        assert tool is not None
        assert tool.category == ToolCategory.UI_OPERATIONS.value

    def test_registered_tool_is_executable(self):
        """A registered tool can be executed through the registry."""
        registry = ToolRegistry()
        register_legacy_tools(registry)

        # navigate_to_tab doesn't need server state
        result, exec_info = registry.execute(
            "navigate_to_tab",
            {"scan_id": "", "tab_name": "health"},
        )
        text, actions = result
        assert "health" in text.lower()
        assert any(a.get("tab") == "health" for a in actions)

    def test_data_tool_without_state_returns_error(self):
        """Data tools gracefully return errors when no scan data exists."""
        registry = ToolRegistry()
        register_legacy_tools(registry)

        result, _info = registry.execute(
            "get_health_summary",
            {"scan_id": "nonexistent"},
        )
        text, actions = result
        parsed = json.loads(text)
        assert "error" in parsed


# ── get_openai_tool_definitions tests ─────────────────────────────────


class TestGetOpenaiToolDefinitions:
    def test_returns_list_before_init(self):
        """Before create_integrated_tool_system, returns raw TOOL_DEFINITIONS."""
        import code_extract.ai.tool_bridge as bridge
        old = bridge._openai_tool_defs
        try:
            bridge._openai_tool_defs = None
            defs = get_openai_tool_definitions()
            assert isinstance(defs, list)
            assert len(defs) == 22
        finally:
            bridge._openai_tool_defs = old

    def test_returns_cached_after_set(self):
        import code_extract.ai.tool_bridge as bridge
        old = bridge._openai_tool_defs
        try:
            bridge._openai_tool_defs = [{"test": True}]
            assert get_openai_tool_definitions() == [{"test": True}]
        finally:
            bridge._openai_tool_defs = old


# ── create_integrated_tool_system tests ───────────────────────────────


class TestCreateIntegratedToolSystem:
    def test_returns_system_and_intelligence(self):
        from code_extract.ai.tool_system import ToolSystem
        from code_extract.ai.tool_intelligence import IntelligenceLayer

        system, intelligence = create_integrated_tool_system()
        assert isinstance(system, ToolSystem)
        assert isinstance(intelligence, IntelligenceLayer)

    def test_system_has_22_legacy_tools(self):
        system, _ = create_integrated_tool_system()
        tools = system.registry.get_all_tools()
        for name in _TOOL_HANDLERS:
            assert name in tools, f"'{name}' missing from integrated system"

    def test_caches_openai_defs(self):
        import code_extract.ai.tool_bridge as bridge
        old = bridge._openai_tool_defs
        try:
            bridge._openai_tool_defs = None
            create_integrated_tool_system()
            assert bridge._openai_tool_defs is not None
            assert len(bridge._openai_tool_defs) == 22
        finally:
            bridge._openai_tool_defs = old

    def test_system_info_available(self):
        system, _ = create_integrated_tool_system()
        info = system.get_system_info()
        assert info["status"] == "running"
        assert info["tools"]["total"] >= 22

    def test_intelligence_get_insights(self):
        _, intelligence = create_integrated_tool_system()
        insights = intelligence.get_insights()
        assert "total_tool_executions" in insights
        assert "popular_tools" in insights
