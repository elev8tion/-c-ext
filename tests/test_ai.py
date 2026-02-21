"""Tests for AI chat integration — service layer and API endpoints."""

import time
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

try:
    from fastapi.testclient import TestClient
    from code_extract.web import create_app
    from code_extract.web.state import state
    from code_extract.ai import AIConfig, AIModel
    from code_extract.ai.service import DeepSeekService
    HAS_WEB = True
except ImportError:
    HAS_WEB = False

pytestmark = pytest.mark.skipif(not HAS_WEB, reason="web dependencies not installed")

FIXTURES = Path(__file__).parent / "fixtures"


# ── AI Config Tests ──────────────────────────────────────────

class TestAIConfig:
    def test_default_config(self):
        config = AIConfig()
        assert config.model == AIModel.DEEPSEEK_CODER
        assert config.temperature == 0.3
        assert config.max_tokens == 6000
        assert "deepseek.com" in config.base_url

    def test_custom_model(self):
        config = AIConfig(model=AIModel.DEEPSEEK_CHAT)
        assert config.model == AIModel.DEEPSEEK_CHAT

    def test_env_api_key(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-123")
        config = AIConfig()
        assert config.api_key == "test-key-123"


# ── AI Service Tests ─────────────────────────────────────────

class TestDeepSeekService:
    def test_build_system_prompt_empty(self):
        service = DeepSeekService(AIConfig(api_key="test"))
        prompt = service._build_system_prompt([], None)
        assert "expert software engineer" in prompt
        assert "Code Context" not in prompt

    def test_build_system_prompt_with_code(self):
        service = DeepSeekService(AIConfig(api_key="test"))
        code_context = [{
            "name": "my_func",
            "type": "function",
            "language": "python",
            "file": "test.py",
            "code": "def my_func(): pass",
        }]
        prompt = service._build_system_prompt(code_context, None)
        assert "my_func" in prompt
        assert "python" in prompt
        assert "def my_func" in prompt

    def test_build_system_prompt_with_analysis(self):
        service = DeepSeekService(AIConfig(api_key="test"))
        analysis = {
            "health": {"score": 85},
            "dependencies": {"a": {}, "b": {}, "c": {}},
            "dead_code": [{"name": "unused_fn", "type": "function", "confidence": 0.9, "reason": "unused"}],
        }
        prompt = service._build_system_prompt([], analysis)
        assert "85" in prompt
        assert "3 nodes" in prompt
        assert "1 items" in prompt

    def test_build_messages(self):
        service = DeepSeekService(AIConfig(api_key="test"))
        messages = service._build_messages("What does this do?", [], None)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "What does this do?"

    def test_code_context_limited(self):
        service = DeepSeekService(AIConfig(api_key="test"))
        # 15 blocks — should only include first 10
        blocks = [{"name": f"fn_{i}", "type": "function", "language": "python",
                    "file": "t.py", "code": "pass"} for i in range(15)]
        prompt = service._build_system_prompt(blocks, None)
        assert "fn_0" in prompt
        assert "fn_9" in prompt
        assert "fn_10" not in prompt


# ── API Endpoint Tests ───────────────────────────────────────

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def _scan_and_wait(client, path=None):
    """Scan and wait for background extraction to complete."""
    res = client.post("/api/scan", json={"path": str(path or FIXTURES)})
    assert res.status_code == 200
    scan_id = res.json()["scan_id"]
    for _ in range(30):
        status_res = client.get(f"/api/scan/{scan_id}/status")
        if status_res.json().get("status") == "ready":
            break
        time.sleep(0.2)
    return scan_id


class TestAIChatAPI:
    def test_chat_no_scan(self, client):
        res = client.post("/api/ai/chat", json={
            "scan_id": "nonexistent",
            "query": "hello",
        })
        assert res.status_code == 404

    def test_chat_no_api_key(self, client, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        scan_id = _scan_and_wait(client)
        res = client.post("/api/ai/chat", json={
            "scan_id": scan_id,
            "query": "hello",
        })
        assert res.status_code == 503
        assert "DEEPSEEK_API_KEY" in res.json()["detail"]

    @patch("code_extract.ai.service.DeepSeekService")
    def test_chat_success(self, MockService, client, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        scan_id = _scan_and_wait(client)

        # Mock the service
        mock_instance = MagicMock()
        mock_instance.chat_with_code = AsyncMock(return_value={
            "choices": [{"message": {"content": "This is a test function."}}],
            "model": "deepseek-coder",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        })
        mock_instance.close = AsyncMock()
        MockService.return_value = mock_instance

        res = client.post("/api/ai/chat", json={
            "scan_id": scan_id,
            "query": "What does this code do?",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["answer"] == "This is a test function."
        assert data["model"] == "deepseek-coder"
        assert "usage" in data

    def test_history_empty(self, client):
        scan_id = _scan_and_wait(client)
        res = client.get(f"/api/ai/history/{scan_id}")
        assert res.status_code == 200
        assert res.json()["history"] == []

    @patch("code_extract.ai.service.DeepSeekService")
    def test_history_after_chat(self, MockService, client, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        scan_id = _scan_and_wait(client)

        mock_instance = MagicMock()
        mock_instance.chat_with_code = AsyncMock(return_value={
            "choices": [{"message": {"content": "Answer here."}}],
            "model": "deepseek-coder",
            "usage": {},
        })
        mock_instance.close = AsyncMock()
        MockService.return_value = mock_instance

        client.post("/api/ai/chat", json={
            "scan_id": scan_id,
            "query": "test question",
        })

        res = client.get(f"/api/ai/history/{scan_id}")
        history = res.json()["history"]
        assert len(history) == 1
        assert history[0]["query"] == "test question"
        assert history[0]["answer"] == "Answer here."

    def test_clear_history(self, client):
        scan_id = _scan_and_wait(client)
        # Store some history manually
        state.store_analysis(scan_id, "chat_history", [{"query": "x", "answer": "y"}])

        res = client.delete(f"/api/ai/history/{scan_id}")
        assert res.status_code == 200
        assert res.json()["cleared"] is True

        # Verify it's cleared
        res = client.get(f"/api/ai/history/{scan_id}")
        assert res.json()["history"] == []
