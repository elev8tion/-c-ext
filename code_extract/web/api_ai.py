"""AI Chat API — DeepSeek integration for context-aware code analysis."""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from code_extract.web.state import state

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ── Config persistence (F8) ──────────────────────────────────────────

_CONFIG_DIR = Path.home() / ".code-extract"
_CONFIG_FILE = _CONFIG_DIR / ".chat_config.json"


def _load_ai_config() -> dict:
    """Load persisted AI config from disk."""
    try:
        if _CONFIG_FILE.exists():
            return json.loads(_CONFIG_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_ai_config(data: dict) -> None:
    """Write AI config to disk."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps(data, indent=2))


# ── Rate limiting (F9) ───────────────────────────────────────────────

def _check_rate_limit(scan_id: str) -> None:
    """Raise 429 if rate limit exceeded for this scan."""
    from code_extract.ai.rate_limiter import get_rate_limiter
    limiter = get_rate_limiter()
    allowed, retry_after = limiter.check(scan_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again later.",
            headers={"Retry-After": str(int(retry_after + 1))},
        )


# ── Health-aware item scoring (F6) ───────────────────────────────────

def _select_relevant_items(
    blocks: dict, query: str, limit: int = 20,
    analysis_context: dict | None = None,
) -> list[str]:
    """Score items by relevance to the query, return top *limit* IDs."""
    if not blocks or not query:
        return list(blocks.keys())[:limit] if blocks else []

    query_lower = query.lower()
    words = query_lower.split()
    scored: list[tuple[str, float]] = []

    # Build set of problematic names from analysis context (F6)
    problematic_names: set[str] = set()
    if analysis_context:
        health = analysis_context.get("health")
        if isinstance(health, dict):
            for fn in health.get("long_functions", []):
                if isinstance(fn, dict) and fn.get("name"):
                    problematic_names.add(fn["name"].lower())
            for c in health.get("high_coupling", []):
                if isinstance(c, dict) and c.get("name"):
                    problematic_names.add(c["name"].lower())
        dead = analysis_context.get("dead_code")
        if isinstance(dead, list):
            for item in dead:
                if isinstance(item, dict):
                    for key in ("qualified_name", "name"):
                        if item.get(key):
                            problematic_names.add(item[key].lower())

    for item_id, block in blocks.items():
        score = 0.1  # baseline
        name = (block.item.qualified_name or "").lower()
        btype = (block.item.block_type.value or "").lower()
        lang = (block.item.language.value or "").lower()
        fpath = str(block.item.file_path or "").lower()

        for w in words:
            if w in name:
                score += 10 if w == name or w == name.split(".")[-1] else 5
            if w in btype:
                score += 2
            if w in lang:
                score += 1
            if w in fpath:
                score += 3

        # Health-aware bonus (F6)
        if problematic_names:
            item_name = (block.item.qualified_name or block.item.name or "").lower()
            if item_name in problematic_names or block.item.name.lower() in problematic_names:
                score += 3

        scored.append((item_id, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [item_id for item_id, _ in scored[:limit]]


def _build_analysis_context(scan_id: str) -> dict:
    """Build enriched analysis context for a scan, fetching all available analyses."""
    ctx: dict = {}

    health = state.get_analysis(scan_id, "health")
    if health:
        ctx["health"] = health

    graph = state.get_analysis(scan_id, "graph")
    if graph:
        ctx["dependencies"] = graph

    dead = state.get_analysis(scan_id, "deadcode")
    if dead:
        ctx["dead_code"] = dead

    # Architecture summary (stats + module list only, not full elements)
    arch = state.get_analysis(scan_id, "architecture")
    if arch and isinstance(arch, dict):
        ctx["architecture"] = {
            "stats": arch.get("stats", {}),
            "modules": [m.get("name", m.get("id", "")) for m in arch.get("modules", [])],
        }

    # Catalog summary (type distribution)
    catalog = state.get_analysis(scan_id, "catalog")
    if catalog and isinstance(catalog, dict):
        items = catalog.get("items", [])
        type_dist: dict[str, int] = {}
        for item in items:
            t = item.get("type", "unknown") if isinstance(item, dict) else "unknown"
            type_dist[t] = type_dist.get(t, 0) + 1
        ctx["catalog"] = {"total": len(items), "types": type_dist}

    # Tour summary (step count + first entry points)
    tour = state.get_analysis(scan_id, "tour")
    if tour and isinstance(tour, dict):
        steps = tour.get("steps", [])
        entries = [
            s.get("title", s.get("name", ""))
            for s in steps[:3]
            if isinstance(s, dict)
        ]
        ctx["tour"] = {"step_count": len(steps), "entry_points": entries}

    return ctx


def _resolve_config_key(config) -> None:
    """If config has no API key, try loading from persisted config (F8 fallback)."""
    if not config.api_key:
        saved = _load_ai_config()
        if saved.get("api_key"):
            config.api_key = saved["api_key"]


# ── Lazy tool system singleton ──────────────────────────────────────

_tool_system_lock = threading.Lock()
_tool_system_instance = None
_intelligence_instance = None


def _get_tool_system():
    """Return ``(tool_system, intelligence)`` — created once, thread-safe.

    Returns ``(None, None)`` on failure so the service falls back to
    direct tool execution via ``tools.execute_tool()``.
    """
    global _tool_system_instance, _intelligence_instance
    if _tool_system_instance is not None:
        return _tool_system_instance, _intelligence_instance

    with _tool_system_lock:
        # Double-check after acquiring the lock
        if _tool_system_instance is not None:
            return _tool_system_instance, _intelligence_instance
        try:
            from code_extract.ai.tool_bridge import create_integrated_tool_system
            _tool_system_instance, _intelligence_instance = (
                create_integrated_tool_system()
            )
            logger.info("Tool system initialized for agent endpoint")
        except Exception:
            logger.exception("Failed to initialize tool system — falling back")
            return None, None

    return _tool_system_instance, _intelligence_instance


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


class AIConfigUpdate(BaseModel):
    api_key: Optional[str] = None
    model: Optional[str] = None


class StructuredAnalysisRequest(BaseModel):
    scan_id: str
    focus: Optional[str] = None  # "health", "architecture", "dead_code"
    item_ids: Optional[list[str]] = None
    model: Optional[str] = None
    api_key: Optional[str] = None


# ── Config endpoints (F8) ────────────────────────────────────────────

@router.get("/config")
async def get_ai_config():
    """Get saved AI config (never exposes raw API key)."""
    saved = _load_ai_config()
    return {
        "api_key_set": bool(saved.get("api_key")),
        "selected_model": saved.get("model", "deepseek-chat"),
    }


@router.post("/config")
async def update_ai_config(req: AIConfigUpdate):
    """Save AI config to disk."""
    from code_extract.ai import AIModel

    saved = _load_ai_config()

    if req.api_key and req.api_key != "KEEP_EXISTING":
        saved["api_key"] = req.api_key

    if req.model:
        # Validate model name
        try:
            AIModel(req.model)
            saved["model"] = req.model
        except ValueError:
            raise HTTPException(400, detail=f"Invalid model: {req.model}")

    _save_ai_config(saved)
    return {
        "api_key_set": bool(saved.get("api_key")),
        "selected_model": saved.get("model", "deepseek-chat"),
    }


# ── Chat endpoint ────────────────────────────────────────────────────

@router.post("/chat")
async def chat_with_scan(req: ChatRequest):
    """Chat about code from a specific scan."""
    from code_extract.ai import AIConfig, AIModel
    from code_extract.ai.service import DeepSeekService
    from code_extract.ai.token_utils import estimate_tokens

    _check_rate_limit(req.scan_id)

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

    _resolve_config_key(config)

    if not config.api_key:
        raise HTTPException(
            503,
            detail="DeepSeek API key not configured. Set the DEEPSEEK_API_KEY environment variable.",
        )

    # Build analysis context first (needed for health-aware scoring)
    analysis_context = {}
    if req.include_analysis:
        analysis_context = _build_analysis_context(req.scan_id)

    # Build code context from extracted blocks
    blocks = state.get_blocks_for_scan(req.scan_id)
    code_context = []

    if blocks:
        items_to_include = req.item_ids or _select_relevant_items(
            blocks, req.query, analysis_context=analysis_context,
        )
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

    # Estimate context size (F7)
    context_text = " ".join(b.get("code", "") for b in code_context)
    context_text += " " + req.query
    if analysis_context:
        context_text += " " + json.dumps(analysis_context, default=str)[:2000]
    context_size = estimate_tokens(context_text)
    from code_extract.ai.token_utils import has_tiktoken
    context_unit = "tokens" if has_tiktoken() else "chars_estimated"

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
        "context_size": context_size,
        "context_unit": context_unit,
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

MAX_AGENT_HISTORY_TURNS = 10


@router.post("/agent")
async def agent_chat_endpoint(req: AgentChatRequest):
    """Agentic copilot — tool-calling loop with UI actions."""
    from code_extract.ai import AIConfig, AIModel
    from code_extract.ai.service import DeepSeekService

    _check_rate_limit(req.scan_id)

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
        # Default to deepseek-chat for tool-calling support
        config.model = AIModel.DEEPSEEK_CHAT

    _resolve_config_key(config)

    if not config.api_key:
        raise HTTPException(
            503,
            detail="DeepSeek API key not configured. Set the DEEPSEEK_API_KEY environment variable.",
        )

    # Build analysis context first (for health-aware scoring)
    analysis_context = _build_analysis_context(req.scan_id)

    # Build code context
    blocks = state.get_blocks_for_scan(req.scan_id)
    code_context = []
    if blocks:
        items_to_include = req.item_ids or _select_relevant_items(
            blocks, req.query, analysis_context=analysis_context,
        )
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

    logger.info(
        "[agent-endpoint] model=%s, code_blocks=%d, analysis_keys=%s, query=%.80s",
        config.model.value, len(code_context),
        list(analysis_context.keys()) if analysis_context else "none",
        req.query,
    )

    # Load agent conversation history (last N turns)
    history = state.get_analysis(req.scan_id, "agent_history") or []

    tool_system, intelligence = _get_tool_system()
    service = DeepSeekService(
        config,
        tool_system=tool_system,
        intelligence=intelligence,
    )
    try:
        result = await service.agent_chat(
            query=req.query,
            scan_id=req.scan_id,
            history=history,
            code_context=code_context,
            analysis_context=analysis_context or None,
        )
    except Exception as e:
        logger.exception("[agent-endpoint] error: %s", e)
        raise HTTPException(500, detail=f"AI agent error: {e}")
    finally:
        await service.close()

    logger.info(
        "[agent-endpoint] result: answer=%d chars, actions=%d, model=%s",
        len(result.get("answer", "")), len(result.get("actions", [])),
        result.get("model", "?"),
    )

    # Track context size in tool system health (F7)
    if tool_system:
        try:
            tool_system.health.update_metric(
                "ai_context_size", result.get("context_size", 0),
                "tokens", warning_threshold=80000, critical_threshold=110000,
            )
        except Exception:
            pass

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
        "context_size": result.get("context_size"),
        "context_unit": result.get("context_unit"),
        "tool_calls_made": result.get("tool_calls_made"),
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


# ── Structured Analysis (F4) ─────────────────────────────────────────

@router.post("/structured")
async def structured_analysis(req: StructuredAnalysisRequest):
    """Structured JSON analysis — returns issues and recommendations."""
    from code_extract.ai import AIConfig, AIModel
    from code_extract.ai.service import DeepSeekService

    _check_rate_limit(req.scan_id)

    scan = state.scans.get(req.scan_id)
    if not scan:
        raise HTTPException(404, detail="Scan session not found")

    config = AIConfig(api_key=req.api_key or "")
    if req.model:
        try:
            config.model = AIModel(req.model)
        except ValueError:
            pass

    _resolve_config_key(config)

    if not config.api_key:
        raise HTTPException(
            503,
            detail="DeepSeek API key not configured. Set the DEEPSEEK_API_KEY environment variable.",
        )

    # Build code context (top 10 items relevant to focus)
    blocks = state.get_blocks_for_scan(req.scan_id)
    code_context = []
    if blocks:
        query_hint = req.focus or "health architecture quality"
        items_to_include = req.item_ids or _select_relevant_items(
            blocks, query_hint, limit=10,
        )
        for item_id in items_to_include:
            block = blocks.get(item_id)
            if not block:
                continue
            code_context.append({
                "name": block.item.qualified_name,
                "type": block.item.block_type.value,
                "language": block.item.language.value,
                "file": str(block.item.file_path),
                "code": block.source_code[:2000],
            })

    analysis_context = _build_analysis_context(req.scan_id)

    tool_system, intelligence = _get_tool_system()
    service = DeepSeekService(
        config,
        tool_system=tool_system,
        intelligence=intelligence,
    )
    try:
        result = await service.structured_analyze(
            scan_id=req.scan_id,
            code_context=code_context,
            analysis_context=analysis_context or None,
            focus=req.focus,
        )
    except Exception as e:
        logger.exception("[structured] error: %s", e)
        raise HTTPException(500, detail=f"Structured analysis error: {e}")
    finally:
        await service.close()

    # Record in intelligence layer
    if intelligence:
        try:
            intelligence.record_tool_usage(
                tool_name="structured_analyze",
                parameters={"focus": req.focus},
                execution_time=0,
                success=True,
            )
        except Exception:
            pass

    return result
