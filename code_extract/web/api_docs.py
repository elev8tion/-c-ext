"""Living documentation API — auto-generate docs, watch mode via WebSocket."""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from code_extract.web.state import state
from code_extract.analysis.docs import generate_docs, generate_markdown

router = APIRouter(prefix="/api/docs")

# Cache generated docs
_docs_cache: dict[str, dict] = {}


class GenerateRequest(BaseModel):
    scan_id: str


@router.post("/generate")
async def generate(req: GenerateRequest):
    blocks = state.get_blocks_for_scan(req.scan_id)
    if not blocks:
        raise HTTPException(400, "No extracted blocks available. Scan may still be processing.")

    result = await asyncio.to_thread(generate_docs, blocks)

    doc_id = req.scan_id  # use scan_id as doc_id
    _docs_cache[doc_id] = result
    result["doc_id"] = doc_id
    return result


@router.get("/{doc_id}")
async def get_docs(doc_id: str):
    cached = _docs_cache.get(doc_id)
    if not cached:
        raise HTTPException(404, "Docs not found")
    return cached


@router.get("/{doc_id}/markdown")
async def get_docs_markdown(doc_id: str):
    blocks = state.get_blocks_for_scan(doc_id)
    if not blocks:
        raise HTTPException(404, "No blocks for this scan")

    md = await asyncio.to_thread(generate_markdown, blocks)
    return PlainTextResponse(md, media_type="text/markdown")


@router.websocket("/ws/docs-watch")
async def docs_watch(websocket: WebSocket):
    """WebSocket for live documentation updates (watch mode)."""
    await websocket.accept()

    try:
        data = await websocket.receive_text()
        msg = json.loads(data)
        scan_id = msg.get("scan_id")

        if not scan_id:
            await websocket.send_json({"error": "scan_id required"})
            return

        scan = state.scans.get(scan_id)
        if not scan:
            await websocket.send_json({"error": "Scan not found"})
            return

        # Try to use watchfiles for file watching
        try:
            from watchfiles import awatch
        except ImportError:
            await websocket.send_json({"error": "watchfiles not installed. Install with: pip install watchfiles"})
            return

        source_dir = scan.source_dir

        # Send initial docs
        blocks = state.get_blocks_for_scan(scan_id)
        if blocks:
            result = generate_docs(blocks)
            await websocket.send_json(result)

        # Watch for changes
        async for changes in awatch(source_dir):
            # Re-scan and regenerate docs
            from code_extract.models import PipelineConfig
            from code_extract.pipeline import run_scan
            from code_extract.extractor import extract_item
            from code_extract.web.state import ScanSession

            config = PipelineConfig(source_dir=__import__("pathlib").Path(source_dir))
            items = await asyncio.to_thread(run_scan, config)

            # Update scan
            session = ScanSession(id=scan_id, source_dir=source_dir, items=items)
            state.add_scan(session)

            # Re-extract and store blocks
            new_blocks = {}
            for item in items:
                try:
                    block = extract_item(item)
                    key = f"{item.file_path}:{item.line_number}"
                    new_blocks[key] = block
                except Exception:
                    pass

            state.store_blocks(scan_id, new_blocks)

            # Regenerate docs
            result = generate_docs(new_blocks)
            await websocket.send_json(result)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
