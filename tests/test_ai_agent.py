"""Tests for AI agentic copilot — tools, service, and API endpoints."""

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

try:
    from fastapi.testclient import TestClient
    from code_extract.web import create_app
    from code_extract.web.state import state
    from code_extract.ai import AIConfig, AIModel
    from code_extract.ai.service import DeepSeekService
    from code_extract.ai.tools import (
        TOOL_DEFINITIONS,
        execute_tool,
        _resolve_items,
        _find_item,
        handle_search_items,
        handle_get_item_code,
        handle_get_health_summary,
        handle_get_architecture_info,
        handle_get_dead_code_list,
        handle_get_dependencies,
        handle_navigate_to_tab,
        handle_select_items,
        handle_start_clone,
        handle_add_to_remix,
    )
    from code_extract.models import (
        CodeBlockType,
        ExtractedBlock,
        Language,
        ScannedItem,
    )
    from code_extract.analysis.graph_models import DependencyGraph, DependencyNode
    HAS_WEB = True
except ImportError:
    HAS_WEB = False

pytestmark = pytest.mark.skipif(not HAS_WEB, reason="web dependencies not installed")

FIXTURES = Path(__file__).parent / "fixtures"


# ── Helpers ─────────────────────────────────────────────────────────

def _make_item(name, lang=Language.PYTHON, btype=CodeBlockType.FUNCTION,
               file_path=None, line=1, end_line=10, parent=None):
    return ScannedItem(
        name=name,
        block_type=btype,
        language=lang,
        file_path=Path(file_path or f"test/{name}.py"),
        line_number=line,
        end_line=end_line,
        parent=parent,
    )


def _make_block(name, source="def foo(): pass", lang=Language.PYTHON,
                btype=CodeBlockType.FUNCTION, file_path=None,
                line=1, end_line=10, parent=None):
    item = _make_item(name, lang, btype, file_path, line, end_line, parent)
    return ExtractedBlock(item=item, source_code=source)


def _blocks_dict(*blocks):
    return {f"{b.item.file_path}:{b.item.line_number}": b for b in blocks}


def _setup_scan_with_blocks(blocks_dict, scan_id="test-scan"):
    """Store blocks in state for a fake scan."""
    from code_extract.web.state import ScanSession
    session = ScanSession(id=scan_id, source_dir="/tmp/test")
    state.scans[scan_id] = session
    state.store_blocks(scan_id, blocks_dict)
    return scan_id


# ── Tool Definition Tests ──────────────────────────────────────────

class TestToolDefinitions:
    def test_tool_count(self):
        assert len(TOOL_DEFINITIONS) == 22

    def test_all_tools_have_function_schema(self):
        for tool in TOOL_DEFINITIONS:
            assert tool["type"] == "function"
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]

    def test_tool_names_unique(self):
        names = [t["function"]["name"] for t in TOOL_DEFINITIONS]
        assert len(names) == len(set(names))


# ── Item Resolution Tests ──────────────────────────────────────────

class TestItemResolution:
    def setup_method(self):
        self.blocks = _blocks_dict(
            _make_block("UserService", source="class UserService: pass",
                        btype=CodeBlockType.CLASS),
            _make_block("auth_login", source="def auth_login(): pass"),
            _make_block("AuthMiddleware", source="class AuthMiddleware: pass",
                        btype=CodeBlockType.CLASS),
        )
        self.scan_id = _setup_scan_with_blocks(self.blocks)

    def teardown_method(self):
        state.scans.pop("test-scan", None)
        state._block_index.pop("test-scan", None)

    def test_exact_match(self):
        match = _find_item(self.blocks, "UserService")
        assert match is not None
        assert match[1].item.name == "UserService"

    def test_case_insensitive_match(self):
        match = _find_item(self.blocks, "userservice")
        assert match is not None
        assert match[1].item.name == "UserService"

    def test_substring_match(self):
        match = _find_item(self.blocks, "auth")
        assert match is not None
        assert "auth" in match[1].item.name.lower()

    def test_no_match(self):
        match = _find_item(self.blocks, "NonExistentItem")
        assert match is None

    def test_resolve_items_multiple(self):
        resolved = _resolve_items(self.scan_id, ["UserService", "auth_login"])
        assert len(resolved) == 2

    def test_resolve_items_not_found(self):
        resolved = _resolve_items(self.scan_id, ["DoesNotExist"])
        assert len(resolved) == 0


# ── Data Tool Handler Tests ────────────────────────────────────────

class TestDataToolHandlers:
    def setup_method(self):
        self.blocks = _blocks_dict(
            _make_block("UserService", source="class UserService:\n    pass",
                        btype=CodeBlockType.CLASS),
            _make_block("create_user", source="def create_user(name): return User(name)"),
            _make_block("delete_user", source="def delete_user(uid): pass"),
        )
        self.scan_id = _setup_scan_with_blocks(self.blocks)

    def teardown_method(self):
        state.scans.pop("test-scan", None)
        state._block_index.pop("test-scan", None)
        state._analyses.pop("test-scan", None)

    def test_search_items_exact(self):
        result, actions = handle_search_items(self.scan_id, {"query": "UserService"})
        data = json.loads(result)
        assert data["count"] >= 1
        assert any(i["name"] == "UserService" for i in data["items"])
        assert actions == []

    def test_search_items_fuzzy(self):
        result, actions = handle_search_items(self.scan_id, {"query": "user"})
        data = json.loads(result)
        assert data["count"] >= 1

    def test_search_items_with_type_filter(self):
        result, _ = handle_search_items(self.scan_id, {"query": "user", "type": "class"})
        data = json.loads(result)
        for item in data["items"]:
            assert item["type"] == "class"

    def test_search_items_no_blocks(self):
        result, _ = handle_search_items("nonexistent", {"query": "test"})
        data = json.loads(result)
        assert data["items"] == []

    def test_get_item_code(self):
        result, actions = handle_get_item_code(self.scan_id, {"item_name": "create_user"})
        data = json.loads(result)
        assert "create_user" in data["code"]
        assert actions == []

    def test_get_item_code_not_found(self):
        result, _ = handle_get_item_code(self.scan_id, {"item_name": "nonexistent"})
        data = json.loads(result)
        assert "error" in data

    def test_get_health_summary(self):
        state.store_analysis(self.scan_id, "health", {
            "score": 72,
            "long_functions": [{"name": "big_fn", "line_count": 150}],
            "duplications": [],
            "coupling": [],
        })
        result, actions = handle_get_health_summary(self.scan_id, {})
        data = json.loads(result)
        assert data["score"] == 72
        assert data["long_functions"] == 1
        assert actions == []

    def test_get_health_summary_unavailable(self):
        result, _ = handle_get_health_summary(self.scan_id, {})
        data = json.loads(result)
        assert "error" in data

    def test_get_architecture_info(self):
        state.store_analysis(self.scan_id, "architecture", {
            "stats": {"total_items": 10, "total_edges": 5,
                      "total_modules": 3, "cross_module_edges": 2},
            "modules": [{"directory": "src", "item_count": 7}],
        })
        result, actions = handle_get_architecture_info(self.scan_id, {})
        data = json.loads(result)
        assert data["total_items"] == 10
        assert actions == []

    def test_get_dead_code_list(self):
        state.store_analysis(self.scan_id, "dead_code", [
            {"name": "unused_fn", "type": "function", "file": "test.py",
             "confidence": 0.9, "reason": "no references"},
        ])
        result, _ = handle_get_dead_code_list(self.scan_id, {})
        data = json.loads(result)
        assert data["count"] == 1
        assert data["items"][0]["name"] == "unused_fn"

    def test_get_dependencies(self):
        graph = DependencyGraph()
        # Add some nodes and edges
        item_ids = list(self.blocks.keys())
        graph.forward[item_ids[0]] = {item_ids[1]}
        graph.reverse[item_ids[1]] = {item_ids[0]}
        state.store_analysis(self.scan_id, "graph", graph)

        result, _ = handle_get_dependencies(self.scan_id, {"item_name": "UserService"})
        data = json.loads(result)
        assert "depends_on" in data
        assert "depended_by" in data


# ── UI Action Tool Handler Tests ───────────────────────────────────

class TestUIActionToolHandlers:
    def setup_method(self):
        self.blocks = _blocks_dict(
            _make_block("UserService", btype=CodeBlockType.CLASS),
            _make_block("auth_login"),
        )
        self.scan_id = _setup_scan_with_blocks(self.blocks)

    def teardown_method(self):
        state.scans.pop("test-scan", None)
        state._block_index.pop("test-scan", None)

    def test_navigate_generates_action(self):
        result, actions = handle_navigate_to_tab(self.scan_id, {"tab_name": "architecture"})
        assert len(actions) == 1
        assert actions[0]["type"] == "navigate"
        assert actions[0]["tab"] == "architecture"

    def test_select_items_generates_action(self):
        result, actions = handle_select_items(self.scan_id, {"item_names": ["UserService"]})
        assert len(actions) == 1
        assert actions[0]["type"] == "select"
        assert len(actions[0]["item_ids"]) == 1

    def test_start_clone_generates_multi_step(self):
        result, actions = handle_start_clone(self.scan_id, {
            "source_name": "UserService",
            "new_name": "AdminService",
        })
        assert len(actions) == 4  # navigate + fill select + fill name + preview
        assert actions[0]["type"] == "navigate"
        assert actions[0]["tab"] == "clone"
        assert actions[1]["type"] == "fill"
        assert actions[2]["type"] == "fill"
        assert actions[2]["value"] == "AdminService"
        assert actions[3]["type"] == "click"

    def test_add_to_remix_generates_actions(self):
        result, actions = handle_add_to_remix(self.scan_id, {
            "item_names": ["UserService", "auth_login"],
        })
        assert actions[0]["type"] == "navigate"
        assert actions[0]["tab"] == "remix"
        # One remix_add per resolved item
        remix_adds = [a for a in actions if a["type"] == "remix_add"]
        assert len(remix_adds) == 2

    def test_clone_not_found(self):
        result, actions = handle_start_clone(self.scan_id, {
            "source_name": "NonExistent",
            "new_name": "NewThing",
        })
        assert actions == []
        assert "not find" in result.lower()


# ── Execute Tool Dispatcher Tests ──────────────────────────────────

class TestExecuteTool:
    def test_unknown_tool(self):
        result, actions = execute_tool("nonexistent_tool", "scan-1", {})
        data = json.loads(result)
        assert "error" in data

    def test_dispatch_navigate(self):
        result, actions = execute_tool("navigate_to_tab", "scan-1", {"tab_name": "health"})
        assert len(actions) == 1
        assert actions[0]["tab"] == "health"


# ── Agent Service Tests (mocked DeepSeek) ──────────────────────────

class TestAgentChat:
    def test_agent_direct_answer(self):
        """Model responds without using any tools."""
        async def _test():
            service = DeepSeekService(AIConfig(api_key="test-key"))
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.json.return_value = {
                "choices": [{
                    "message": {"role": "assistant", "content": "The health score is 85."},
                    "finish_reason": "stop",
                }],
                "model": "deepseek-coder",
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            }
            service.client.post = AsyncMock(return_value=mock_response)
            result = await service.agent_chat("What's the health?", "scan-1", [])
            assert result["answer"] == "The health score is 85."
            assert result["actions"] == []
            assert result["usage"]["total_tokens"] == 120
            await service.close()
        asyncio.run(_test())

    def test_agent_data_tool_call(self):
        """Model calls a data tool, gets result, then answers."""
        async def _test():
            service = DeepSeekService(AIConfig(api_key="test-key"))
            tool_response = MagicMock()
            tool_response.status_code = 200
            tool_response.raise_for_status = MagicMock()
            tool_response.json.return_value = {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "search_items",
                                "arguments": json.dumps({"query": "User"}),
                            },
                        }],
                    },
                    "finish_reason": "tool_calls",
                }],
                "model": "deepseek-coder",
                "usage": {"prompt_tokens": 80, "completion_tokens": 10, "total_tokens": 90},
            }
            final_response = MagicMock()
            final_response.status_code = 200
            final_response.raise_for_status = MagicMock()
            final_response.json.return_value = {
                "choices": [{
                    "message": {"role": "assistant", "content": "I found UserService."},
                    "finish_reason": "stop",
                }],
                "model": "deepseek-coder",
                "usage": {"prompt_tokens": 120, "completion_tokens": 15, "total_tokens": 135},
            }
            service.client.post = AsyncMock(side_effect=[tool_response, final_response])
            with patch("code_extract.ai.tools.handle_search_items") as mock_search:
                mock_search.return_value = (
                    json.dumps({"items": [{"name": "UserService"}], "count": 1}),
                    [],
                )
                result = await service.agent_chat("Find User items", "scan-1", [])
            assert result["answer"] == "I found UserService."
            assert result["actions"] == []
            assert result["usage"]["total_tokens"] == 225
            await service.close()
        asyncio.run(_test())

    def test_agent_ui_action(self):
        """Model calls a UI action tool, response includes actions."""
        async def _test():
            service = DeepSeekService(AIConfig(api_key="test-key"))
            tool_response = MagicMock()
            tool_response.status_code = 200
            tool_response.raise_for_status = MagicMock()
            tool_response.json.return_value = {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_2",
                            "type": "function",
                            "function": {
                                "name": "navigate_to_tab",
                                "arguments": json.dumps({"tab_name": "architecture"}),
                            },
                        }],
                    },
                    "finish_reason": "tool_calls",
                }],
                "model": "deepseek-coder",
                "usage": {"prompt_tokens": 80, "completion_tokens": 10, "total_tokens": 90},
            }
            final_response = MagicMock()
            final_response.status_code = 200
            final_response.raise_for_status = MagicMock()
            final_response.json.return_value = {
                "choices": [{
                    "message": {"role": "assistant", "content": "Navigated to architecture."},
                    "finish_reason": "stop",
                }],
                "model": "deepseek-coder",
                "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
            }
            service.client.post = AsyncMock(side_effect=[tool_response, final_response])
            result = await service.agent_chat("Show architecture", "scan-1", [])
            assert result["answer"] == "Navigated to architecture."
            assert len(result["actions"]) == 1
            assert result["actions"][0]["type"] == "navigate"
            assert result["actions"][0]["tab"] == "architecture"
            await service.close()
        asyncio.run(_test())

    def test_agent_synthesis_after_loop(self):
        """After loop exhausts iterations, synthesis step produces answer."""
        async def _test():
            service = DeepSeekService(AIConfig(api_key="test-key"))

            # Tool-calling response returned for every loop iteration
            loop_response = MagicMock()
            loop_response.status_code = 200
            loop_response.raise_for_status = MagicMock()
            loop_response.json.return_value = {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_loop",
                            "type": "function",
                            "function": {
                                "name": "navigate_to_tab",
                                "arguments": json.dumps({"tab_name": "scan"}),
                            },
                        }],
                    },
                    "finish_reason": "tool_calls",
                }],
                "model": "deepseek-coder",
                "usage": {"prompt_tokens": 50, "completion_tokens": 5, "total_tokens": 55},
            }

            # Synthesis response (no tools)
            synth_response = MagicMock()
            synth_response.status_code = 200
            synth_response.raise_for_status = MagicMock()
            synth_response.json.return_value = {
                "choices": [{
                    "message": {"role": "assistant", "content": "Here is a synthesized answer."},
                    "finish_reason": "stop",
                }],
                "model": "deepseek-coder",
                "usage": {"prompt_tokens": 60, "completion_tokens": 20, "total_tokens": 80},
            }

            # 6 loop iterations + 1 synthesis call = 7 total
            service.client.post = AsyncMock(
                side_effect=[loop_response] * 6 + [synth_response],
            )
            result = await service.agent_chat("Loop forever", "scan-1", [])
            assert result["answer"] == "Here is a synthesized answer."
            assert "actions" in result
            assert service.client.post.call_count == 7  # 6 loop + 1 synthesis
            await service.close()
        asyncio.run(_test())

    def test_agent_synthesis_on_api_error(self):
        """Synthesis fires after early loop exit from API error."""
        async def _test():
            service = DeepSeekService(AIConfig(api_key="test-key"))

            # First call: tool call succeeds
            tool_response = MagicMock()
            tool_response.status_code = 200
            tool_response.raise_for_status = MagicMock()
            tool_response.json.return_value = {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "search_items",
                                "arguments": json.dumps({"query": "test"}),
                            },
                        }],
                    },
                    "finish_reason": "tool_calls",
                }],
                "model": "deepseek-coder",
                "usage": {"prompt_tokens": 50, "completion_tokens": 5, "total_tokens": 55},
            }

            # Second call: API error breaks loop
            error = httpx.HTTPStatusError(
                "Server Error", request=MagicMock(), response=MagicMock(),
            )

            # Third call: synthesis response
            synth_response = MagicMock()
            synth_response.status_code = 200
            synth_response.raise_for_status = MagicMock()
            synth_response.json.return_value = {
                "choices": [{
                    "message": {"role": "assistant", "content": "Recovered after error."},
                    "finish_reason": "stop",
                }],
                "model": "deepseek-coder",
                "usage": {"prompt_tokens": 40, "completion_tokens": 15, "total_tokens": 55},
            }

            service.client.post = AsyncMock(
                side_effect=[tool_response, error, synth_response],
            )
            with patch("code_extract.ai.tools.handle_search_items") as mock_search:
                mock_search.return_value = (
                    json.dumps({"items": [{"name": "Foo"}], "count": 1}),
                    [],
                )
                result = await service.agent_chat("Search test", "scan-1", [])

            assert result["answer"] == "Recovered after error."
            assert service.client.post.call_count == 3  # 1 tool + 1 error + 1 synth
            await service.close()
        asyncio.run(_test())


# ── API Endpoint Tests ─────────────────────────────────────────────

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


class TestAgentAPI:
    def test_agent_no_scan(self, client):
        res = client.post("/api/ai/agent", json={
            "scan_id": "nonexistent",
            "query": "hello",
        })
        assert res.status_code == 404

    def test_agent_no_key(self, client, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        scan_id = _scan_and_wait(client)
        res = client.post("/api/ai/agent", json={
            "scan_id": scan_id,
            "query": "hello",
        })
        assert res.status_code == 503

    @patch("code_extract.ai.service.DeepSeekService")
    def test_agent_success(self, MockService, client, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        scan_id = _scan_and_wait(client)

        mock_instance = MagicMock()
        mock_instance.agent_chat = AsyncMock(return_value={
            "answer": "Here is the health score.",
            "actions": [{"type": "navigate", "tab": "health"}],
            "model": "deepseek-coder",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            "history_update": [
                {"role": "user", "content": "Show health"},
                {"role": "assistant", "content": "Here is the health score."},
            ],
        })
        mock_instance.close = AsyncMock()
        MockService.return_value = mock_instance

        res = client.post("/api/ai/agent", json={
            "scan_id": scan_id,
            "query": "Show health",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["answer"] == "Here is the health score."
        assert len(data["actions"]) == 1
        assert data["actions"][0]["type"] == "navigate"

    def test_agent_history_empty(self, client):
        scan_id = _scan_and_wait(client)
        res = client.get(f"/api/ai/agent/history/{scan_id}")
        assert res.status_code == 200
        assert res.json()["history"] == []

    @patch("code_extract.ai.service.DeepSeekService")
    def test_agent_history_after_chat(self, MockService, client, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        scan_id = _scan_and_wait(client)

        mock_instance = MagicMock()
        mock_instance.agent_chat = AsyncMock(return_value={
            "answer": "Done.",
            "actions": [],
            "model": "deepseek-coder",
            "usage": {},
            "history_update": [
                {"role": "user", "content": "test"},
                {"role": "assistant", "content": "Done."},
            ],
        })
        mock_instance.close = AsyncMock()
        MockService.return_value = mock_instance

        client.post("/api/ai/agent", json={
            "scan_id": scan_id,
            "query": "test",
        })

        res = client.get(f"/api/ai/agent/history/{scan_id}")
        history = res.json()["history"]
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    def test_clear_agent_history(self, client):
        scan_id = _scan_and_wait(client)
        state.store_analysis(scan_id, "agent_history", [
            {"role": "user", "content": "x"},
            {"role": "assistant", "content": "y"},
        ])

        res = client.delete(f"/api/ai/agent/history/{scan_id}")
        assert res.status_code == 200
        assert res.json()["cleared"] is True

        res = client.get(f"/api/ai/agent/history/{scan_id}")
        assert res.json()["history"] == []
