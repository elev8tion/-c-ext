"""AI Chat API — DeepSeek integration for context-aware code analysis."""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from code_extract.web.state import state

router = APIRouter(prefix="/api/ai", tags=["ai"])


class ChatRequest(BaseModel):
    scan_id: str
    query: str
    item_ids: Optional[list[str]] = None
    include_analysis: bool = True
    model: Optional[str] = None
    api_key: Optional[str] = None


class AgentChatRequest(BaseModel):
    scan_id: str
    query: str
    item_ids: Optional[list[str]] = None
    model: Optional[str] = None
    api_key: Optional[str] = None


@router.post("/chat")
async def chat_with_scan(req: ChatRequest):
    """Chat about code from a specific scan."""
    from code_extract.ai import AIConfig, AIModel
    from code_extract.ai.service import DeepSeekService

    # Validate scan exists
    scan = state.scans.get(req.scan_id)
    if not scan:
        raise HTTPException(404, detail="Scan session not found")

    # Check API key — prefer request key, fall back to env var
    config = AIConfig(api_key=req.api_key or "")
    if req.model:
        try:
            config.model = AIModel(req.model)
        except ValueError:
            pass

    if not config.api_key:
        raise HTTPException(
            503,
            detail="DeepSeek API key not configured. Set the DEEPSEEK_API_KEY environment variable.",
        )

    # Build code context from extracted blocks
    blocks = state.get_blocks_for_scan(req.scan_id)
    code_context = []

    if blocks:
        items_to_include = req.item_ids or list(blocks.keys())[:20]
        for item_id in items_to_include:
            block = blocks.get(item_id)
            if not block:
                continue
            limit = 5000 if req.item_ids else 2000
            code_context.append({
                "item_id": item_id,
                "name": block.item.qualified_name,
                "type": block.item.block_type.value,
                "language": block.item.language.value,
                "file": str(block.item.file_path),
                "code": block.source_code[:limit],
            })

    # Build analysis context
    analysis_context = {}
    if req.include_analysis:
        health = state.get_analysis(req.scan_id, "health")
        if health:
            analysis_context["health"] = health
        graph = state.get_analysis(req.scan_id, "graph")
        if graph:
            analysis_context["dependencies"] = graph
        dead = state.get_analysis(req.scan_id, "dead_code")
        if dead:
            analysis_context["dead_code"] = dead

    # Call DeepSeek
    service = DeepSeekService(config)
    try:
        response = await service.chat_with_code(
            query=req.query,
            code_context=code_context,
            analysis_context=analysis_context,
        )
    except Exception as e:
        raise HTTPException(500, detail=f"AI service error: {e}")
    finally:
        await service.close()

    answer = (
        response.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )

    # Store in chat history
    history = state.get_analysis(req.scan_id, "chat_history") or []
    entry = {
        "query": req.query,
        "answer": answer,
        "model": response.get("model", config.model.value),
        "usage": response.get("usage", {}),
    }
    history.append(entry)
    state.store_analysis(req.scan_id, "chat_history", history)

    return {
        "answer": answer,
        "model": response.get("model", config.model.value),
        "usage": response.get("usage", {}),
    }


@router.get("/history/{scan_id}")
async def get_chat_history(scan_id: str):
    """Get chat history for a scan."""
    history = state.get_analysis(scan_id, "chat_history") or []
    return {"history": history}


@router.delete("/history/{scan_id}")
async def clear_chat_history(scan_id: str):
    """Clear chat history for a scan."""
    state.store_analysis(scan_id, "chat_history", [])
    return {"cleared": True}


# ── Agentic Copilot ────────────────────────────────────────────────

MAX_AGENT_HISTORY_TURNS = 5


@router.post("/agent")
async def agent_chat_endpoint(req: AgentChatRequest):
    """Agentic copilot — tool-calling loop with UI actions."""
    from code_extract.ai import AIConfig, AIModel
    from code_extract.ai.service import DeepSeekService

    scan = state.scans.get(req.scan_id)
    if not scan:
        raise HTTPException(404, detail="Scan session not found")

    config = AIConfig(api_key=req.api_key or "")
    if req.model:
        try:
            config.model = AIModel(req.model)
        except ValueError:
            pass
    else:
        # Agent needs deepseek-chat for tool-calling support;
        # deepseek-coder is a completion model that ignores tools.
        config.model = AIModel.DEEPSEEK_CHAT

    if not config.api_key:
        raise HTTPException(
            503,
            detail="DeepSeek API key not configured. Set the DEEPSEEK_API_KEY environment variable.",
        )

    # Build code context (same as /api/ai/chat)
    blocks = state.get_blocks_for_scan(req.scan_id)
    code_context = []
    if blocks:
        items_to_include = req.item_ids or list(blocks.keys())[:20]
        for item_id in items_to_include:
            block = blocks.get(item_id)
            if not block:
                continue
            limit = 5000 if req.item_ids else 2000
            code_context.append({
                "item_id": item_id,
                "name": block.item.qualified_name,
                "type": block.item.block_type.value,
                "language": block.item.language.value,
                "file": str(block.item.file_path),
                "code": block.source_code[:limit],
            })

    # Build analysis context (same as /api/ai/chat)
    analysis_context = {}
    health = state.get_analysis(req.scan_id, "health")
    if health:
        analysis_context["health"] = health
    graph = state.get_analysis(req.scan_id, "graph")
    if graph:
        analysis_context["dependencies"] = graph
    dead = state.get_analysis(req.scan_id, "dead_code")
    if dead:
        analysis_context["dead_code"] = dead

    # Load agent conversation history (last N turns)
    history = state.get_analysis(req.scan_id, "agent_history") or []

    service = DeepSeekService(config)
    try:
        result = await service.agent_chat(
            query=req.query,
            scan_id=req.scan_id,
            history=history,
            code_context=code_context,
            analysis_context=analysis_context or None,
        )
    except Exception as e:
        raise HTTPException(500, detail=f"AI agent error: {e}")
    finally:
        await service.close()

    # Update stored history (trim to last N turns)
    history_update = result.get("history_update", [])
    updated_history = history + history_update
    # Keep last MAX_AGENT_HISTORY_TURNS * 2 messages (user + assistant pairs)
    max_messages = MAX_AGENT_HISTORY_TURNS * 2
    if len(updated_history) > max_messages:
        updated_history = updated_history[-max_messages:]
    state.store_analysis(req.scan_id, "agent_history", updated_history)

    return {
        "answer": result["answer"],
        "actions": result["actions"],
        "model": result["model"],
        "usage": result["usage"],
    }


@router.get("/agent/history/{scan_id}")
async def get_agent_history(scan_id: str):
    """Get agent conversation history for a scan."""
    history = state.get_analysis(scan_id, "agent_history") or []
    return {"history": history}


@router.delete("/agent/history/{scan_id}")
async def clear_agent_history(scan_id: str):
    """Clear agent conversation history for a scan."""
    state.store_analysis(scan_id, "agent_history", [])
    return {"cleared": True}
