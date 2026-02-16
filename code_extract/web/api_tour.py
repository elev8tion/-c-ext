"""Codebase tour API — generate step-by-step walkthroughs."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from code_extract.web.state import state
from code_extract.analysis.tour import generate_tour
from code_extract.analysis.dependency_graph import DependencyGraphBuilder

router = APIRouter(prefix="/api/tour")

_builder = DependencyGraphBuilder()

# Cache tours
_tour_cache: dict[str, dict] = {}


class GenerateRequest(BaseModel):
    scan_id: str


def _build_tour(scan_id: str) -> dict:
    blocks = state.get_blocks_for_scan(scan_id)
    if not blocks:
        raise HTTPException(400, "No extracted blocks available")

    # Build or get cached graph
    cached_graph = state.get_analysis(scan_id, "graph")
    if cached_graph:
        graph = cached_graph
    else:
        graph = _builder.build(blocks)
        state.store_analysis(scan_id, "graph", graph)

    return generate_tour(blocks, graph)


@router.post("/generate")
async def generate(req: GenerateRequest):
    cached = state.get_analysis(req.scan_id, "tour")
    if cached:
        cached["tour_id"] = req.scan_id
        _tour_cache[req.scan_id] = cached
        return cached

    result = await asyncio.to_thread(_build_tour, req.scan_id)
    _tour_cache[req.scan_id] = result
    state.store_analysis(req.scan_id, "tour", result)
    result["tour_id"] = req.scan_id
    return result


@router.get("/{tour_id}")
async def get_tour(tour_id: str):
    cached = _tour_cache.get(tour_id)
    if not cached:
        raise HTTPException(404, "Tour not found. Generate one first.")
    return cached
