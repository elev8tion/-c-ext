"""Tests for server-side AI config persistence (F8)."""

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

try:
    from fastapi.testclient import TestClient
    from code_extract.web import create_app
    from code_extract.web.state import state
    from code_extract.web.api_ai import _load_ai_config, _save_ai_config, _CONFIG_FILE
    HAS_WEB = True
except ImportError:
    HAS_WEB = False

pytestmark = pytest.mark.skipif(not HAS_WEB, reason="web dependencies not installed")


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_config(tmp_path):
    """Redirect config to a temp directory for test isolation."""
    config_file = tmp_path / ".chat_config.json"
    with patch("code_extract.web.api_ai._CONFIG_FILE", config_file), \
         patch("code_extract.web.api_ai._CONFIG_DIR", tmp_path):
        yield config_file


class TestConfigEndpoints:
    def test_get_empty_config(self, client):
        res = client.get("/api/ai/config")
        assert res.status_code == 200
        data = res.json()
        assert data["api_key_set"] is False
        assert data["selected_model"] == "deepseek-chat"

    def test_save_and_load_round_trip(self, client):
        # Save config
        res = client.post("/api/ai/config", json={
            "api_key": "sk-test-123",
            "model": "deepseek-coder",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["api_key_set"] is True
        assert data["selected_model"] == "deepseek-coder"

        # Load it back
        res = client.get("/api/ai/config")
        data = res.json()
        assert data["api_key_set"] is True
        assert data["selected_model"] == "deepseek-coder"

    def test_keep_existing_key(self, client):
        # Save initial key
        client.post("/api/ai/config", json={"api_key": "sk-original"})

        # Update model only, keep key
        res = client.post("/api/ai/config", json={
            "api_key": "KEEP_EXISTING",
            "model": "deepseek-reasoner",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["api_key_set"] is True
        assert data["selected_model"] == "deepseek-reasoner"

    def test_invalid_model(self, client):
        res = client.post("/api/ai/config", json={"model": "gpt-5-turbo"})
        assert res.status_code == 400
        assert "Invalid model" in res.json()["detail"]


class TestConfigHelpers:
    def test_load_missing_file(self, clean_config):
        assert _load_ai_config() == {}

    def test_save_creates_file(self, clean_config):
        _save_ai_config({"api_key": "test", "model": "deepseek-chat"})
        assert clean_config.exists()
        data = json.loads(clean_config.read_text())
        assert data["api_key"] == "test"
