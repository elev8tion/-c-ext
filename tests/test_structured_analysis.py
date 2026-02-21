"""Tests for structured JSON analysis endpoint (F4)."""

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

try:
    from fastapi.testclient import TestClient
    from code_extract.web import create_app
    from code_extract.web.state import state
    HAS_WEB = True
except ImportError:
    HAS_WEB = False

pytestmark = pytest.mark.skipif(not HAS_WEB, reason="web dependencies not installed")

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def _scan_and_wait(client, path=None):
    res = client.post("/api/scan", json={"path": str(path or FIXTURES)})
    assert res.status_code == 200
    scan_id = res.json()["scan_id"]
    for _ in range(30):
        status_res = client.get(f"/api/scan/{scan_id}/status")
        if status_res.json().get("status") == "ready":
            break
        time.sleep(0.2)
    return scan_id


class TestStructuredAnalysis:
    def test_no_scan_404(self, client):
        res = client.post("/api/ai/structured", json={
            "scan_id": "nonexistent",
        })
        assert res.status_code == 404

    def test_no_key_503(self, client, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        # Ensure no persisted config interferes
        with patch("code_extract.web.api_ai._load_ai_config", return_value={}):
            scan_id = _scan_and_wait(client)
            res = client.post("/api/ai/structured", json={
                "scan_id": scan_id,
            })
            assert res.status_code == 503

    @patch("code_extract.ai.service.DeepSeekService")
    def test_success_with_mock(self, MockService, client, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        scan_id = _scan_and_wait(client)

        mock_instance = MagicMock()
        mock_instance.structured_analyze = AsyncMock(return_value={
            "analysis": {
                "summary": "Code is healthy",
                "issues": [{"severity": "low", "file": "test.py", "line": 1,
                            "type": "style", "description": "Minor", "fix": "Refactor"}],
                "recommendations": ["Add tests"],
            },
            "model": "deepseek-chat",
            "usage": {"total_tokens": 200},
            "gathered_data_keys": ["health"],
        })
        mock_instance.close = AsyncMock()
        MockService.return_value = mock_instance

        res = client.post("/api/ai/structured", json={
            "scan_id": scan_id,
            "focus": "health",
        })
        assert res.status_code == 200
        data = res.json()
        assert "analysis" in data
        assert data["analysis"]["summary"] == "Code is healthy"
        assert len(data["analysis"]["issues"]) == 1

    @patch("code_extract.ai.service.DeepSeekService")
    def test_invalid_json_fallback(self, MockService, client, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        scan_id = _scan_and_wait(client)

        mock_instance = MagicMock()
        mock_instance.structured_analyze = AsyncMock(return_value={
            "analysis": {
                "summary": "Raw text fallback",
                "issues": [],
                "recommendations": [],
            },
            "model": "deepseek-chat",
            "usage": {},
            "gathered_data_keys": [],
        })
        mock_instance.close = AsyncMock()
        MockService.return_value = mock_instance

        res = client.post("/api/ai/structured", json={
            "scan_id": scan_id,
        })
        assert res.status_code == 200
        data = res.json()
        assert "analysis" in data
        assert isinstance(data["analysis"]["issues"], list)

    @patch("code_extract.ai.service.DeepSeekService")
    def test_focus_filter(self, MockService, client, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        scan_id = _scan_and_wait(client)

        mock_instance = MagicMock()
        mock_instance.structured_analyze = AsyncMock(return_value={
            "analysis": {"summary": "Focused", "issues": [], "recommendations": []},
            "model": "deepseek-chat",
            "usage": {},
            "gathered_data_keys": ["architecture"],
        })
        mock_instance.close = AsyncMock()
        MockService.return_value = mock_instance

        res = client.post("/api/ai/structured", json={
            "scan_id": scan_id,
            "focus": "architecture",
        })
        assert res.status_code == 200
