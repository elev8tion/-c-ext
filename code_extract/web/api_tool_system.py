"""Tool System monitoring API — exposes health, metrics, and insights."""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tools/system", tags=["tool-system"])

NOT_INITIALIZED = {"status": "not_initialized"}


def _get_instances():
    """Return ``(tool_system, intelligence)`` from the shared singleton."""
    from code_extract.web.api_ai import _get_tool_system
    return _get_tool_system()


@router.get("/info")
async def tool_system_info():
    """Comprehensive system information."""
    system, _intel = _get_instances()
    if system is None:
        return NOT_INITIALIZED
    return system.get_system_info()


@router.get("/health")
async def tool_system_health():
    """Health metrics summary."""
    system, _intel = _get_instances()
    if system is None:
        return NOT_INITIALIZED
    return system.health.get_metrics_summary()


@router.get("/tools")
async def tool_system_tools():
    """List registered tools with categories."""
    system, _intel = _get_instances()
    if system is None:
        return NOT_INITIALIZED
    tools = system.registry.get_all_tools()
    return {
        "total": len(tools),
        "tools": [
            {
                "name": meta.name,
                "description": meta.description,
                "category": meta.category,
            }
            for meta in tools.values()
        ],
    }


@router.get("/history")
async def tool_system_history():
    """Recent execution history."""
    system, _intel = _get_instances()
    if system is None:
        return NOT_INITIALIZED
    return {
        "history": system.registry.get_execution_history(limit=50),
    }


@router.get("/insights")
async def tool_system_insights():
    """Intelligence layer insights (patterns, popular tools, bottlenecks)."""
    _system, intelligence = _get_instances()
    if intelligence is None:
        return NOT_INITIALIZED
    return intelligence.get_insights()
