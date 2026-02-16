"""Component catalog API."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from code_extract.web.state import state
from code_extract.analysis.catalog import build_catalog

router = APIRouter(prefix="/api/catalog")


class BuildRequest(BaseModel):
    scan_id: str


@router.post("/build")
async def build(req: BuildRequest):
    blocks = state.get_blocks_for_scan(req.scan_id)
    if not blocks:
        raise HTTPException(400, "No extracted blocks available. Scan may still be processing.")

    items = await asyncio.to_thread(build_catalog, blocks)
    return {"scan_id": req.scan_id, "items": items}


@router.get("/{scan_id}")
async def get_catalog(scan_id: str):
    cached = state.get_analysis(scan_id, "catalog")
    if cached:
        return {"scan_id": scan_id, "items": cached}

    blocks = state.get_blocks_for_scan(scan_id)
    if not blocks:
        raise HTTPException(404, "No catalog data available")

    items = await asyncio.to_thread(build_catalog, blocks)
    state.store_analysis(scan_id, "catalog", items)
    return {"scan_id": scan_id, "items": items}
