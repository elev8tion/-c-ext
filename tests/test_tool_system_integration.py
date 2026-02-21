"""Integration tests — tool system wired through service and API layers."""

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from code_extract.ai.service import DeepSeekService
from code_extract.ai import AIConfig


# ── DeepSeekService._execute_tool tests ───────────────────────────────


class TestServiceExecuteTool:
    def _make_service(self, tool_system=None, intelligence=None):
        config = AIConfig(api_key="test-key")
        return DeepSeekService(
            config,
            tool_system=tool_system,
            intelligence=intelligence,
        )

    def test_fallback_without_tool_system(self):
        """Without a tool_system, falls back to tools.execute_tool."""
        service = self._make_service()
        with patch("code_extract.ai.tools.execute_tool") as mock_exec:
            mock_exec.return_value = ("result", [{"type": "action"}])
            text, actions = service._execute_tool("search_items", "s1", {"query": "x"})

        assert text == "result"
        assert actions == [{"type": "action"}]
        mock_exec.assert_called_once_with("search_items", "s1", {"query": "x"})

    def test_routes_through_tool_system(self):
        """With a tool_system, routes through registry.execute."""
        mock_registry = MagicMock()
        mock_registry.execute.return_value = (
            ("registry result", [{"type": "reg_action"}]),
            {"success": True},
        )
        mock_system = MagicMock()
        mock_system.registry = mock_registry

        service = self._make_service(tool_system=mock_system)
        text, actions = service._execute_tool("search_items", "s1", {"query": "x"})

        assert text == "registry result"
        assert actions == [{"type": "reg_action"}]
        mock_registry.execute.assert_called_once_with(
            "search_items", {"scan_id": "s1", "query": "x"}
        )

    def test_records_usage_in_intelligence(self):
        """Intelligence layer records usage after execution."""
        mock_registry = MagicMock()
        mock_registry.execute.return_value = (("ok", []), {"success": True})
        mock_system = MagicMock()
        mock_system.registry = mock_registry

        mock_intelligence = MagicMock()

        service = self._make_service(
            tool_system=mock_system,
            intelligence=mock_intelligence,
        )
        service._execute_tool("get_health_summary", "s1", {})

        mock_intelligence.record_tool_usage.assert_called_once()
        call_kwargs = mock_intelligence.record_tool_usage.call_args[1]
        assert call_kwargs["tool_name"] == "get_health_summary"
        assert call_kwargs["success"] is True
        assert call_kwargs["execution_time"] >= 0

    def test_records_failure_in_intelligence(self):
        """Intelligence records success=False when execution fails."""
        mock_registry = MagicMock()
        mock_registry.execute.side_effect = RuntimeError("boom")
        mock_system = MagicMock()
        mock_system.registry = mock_registry

        mock_intelligence = MagicMock()

        service = self._make_service(
            tool_system=mock_system,
            intelligence=mock_intelligence,
        )
        text, actions = service._execute_tool("bad_tool", "s1", {})

        parsed = json.loads(text)
        assert "error" in parsed
        assert actions == []

        call_kwargs = mock_intelligence.record_tool_usage.call_args[1]
        assert call_kwargs["success"] is False

    def test_graceful_if_intelligence_fails(self):
        """If intelligence.record_tool_usage raises, tool result still returns."""
        mock_registry = MagicMock()
        mock_registry.execute.return_value = (("ok", []), {"success": True})
        mock_system = MagicMock()
        mock_system.registry = mock_registry

        mock_intelligence = MagicMock()
        mock_intelligence.record_tool_usage.side_effect = RuntimeError("intel fail")

        service = self._make_service(
            tool_system=mock_system,
            intelligence=mock_intelligence,
        )
        text, actions = service._execute_tool("search_items", "s1", {"query": "x"})
        assert text == "ok"


# ── Service constructor tests ─────────────────────────────────────────


class TestServiceConstructor:
    def test_default_no_tool_system(self):
        service = DeepSeekService(AIConfig(api_key="k"))
        assert service._tool_system is None
        assert service._intelligence is None

    def test_accepts_tool_system(self):
        mock_sys = MagicMock()
        mock_intel = MagicMock()
        service = DeepSeekService(
            AIConfig(api_key="k"),
            tool_system=mock_sys,
            intelligence=mock_intel,
        )
        assert service._tool_system is mock_sys
        assert service._intelligence is mock_intel


# ── API lazy initializer tests ────────────────────────────────────────


class TestApiToolSystemInit:
    def test_lazy_init_returns_tuple(self):
        """_get_tool_system returns a (system, intelligence) tuple."""
        import code_extract.web.api_ai as api_ai

        # Reset singleton
        old_sys = api_ai._tool_system_instance
        old_intel = api_ai._intelligence_instance
        try:
            api_ai._tool_system_instance = None
            api_ai._intelligence_instance = None

            system, intelligence = api_ai._get_tool_system()
            assert system is not None
            assert intelligence is not None

            # Second call returns cached
            system2, intelligence2 = api_ai._get_tool_system()
            assert system2 is system
            assert intelligence2 is intelligence
        finally:
            api_ai._tool_system_instance = old_sys
            api_ai._intelligence_instance = old_intel

    def test_returns_none_on_failure(self):
        """On import failure, returns (None, None)."""
        import code_extract.web.api_ai as api_ai

        old_sys = api_ai._tool_system_instance
        old_intel = api_ai._intelligence_instance
        try:
            api_ai._tool_system_instance = None
            api_ai._intelligence_instance = None

            with patch(
                "code_extract.ai.tool_bridge.create_integrated_tool_system",
                side_effect=ImportError("test"),
            ):
                system, intelligence = api_ai._get_tool_system()
                assert system is None
                assert intelligence is None
        finally:
            api_ai._tool_system_instance = old_sys
            api_ai._intelligence_instance = old_intel


# ── API router endpoint tests ─────────────────────────────────────────


class TestToolSystemEndpoints:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from code_extract.web.app import create_app
        app = create_app()
        return TestClient(app)

    def test_info_endpoint(self, client):
        resp = client.get("/api/tools/system/info")
        assert resp.status_code == 200
        data = resp.json()
        # Either initialized or not_initialized
        assert "status" in data

    def test_health_endpoint(self, client):
        resp = client.get("/api/tools/system/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data or "overall_status" in data

    def test_tools_endpoint(self, client):
        resp = client.get("/api/tools/system/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data or "tools" in data

    def test_history_endpoint(self, client):
        resp = client.get("/api/tools/system/history")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data or "history" in data

    def test_insights_endpoint(self, client):
        resp = client.get("/api/tools/system/insights")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data or "total_tool_executions" in data
