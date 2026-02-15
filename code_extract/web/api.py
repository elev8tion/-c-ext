"""FastAPI routes for the code-extract web UI."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

from code_extract.models import PipelineConfig
from code_extract.pipeline import run_pipeline, run_scan
from code_extract.web.state import AppState, ExportSession, ScanSession

router = APIRouter(prefix="/api")
state = AppState()


# --- Request / Response models ---

class ScanRequest(BaseModel):
    path: str

class ExtractRequest(BaseModel):
    scan_id: str
    item_ids: list[str]  # "filepath:line" keys
    output_name: str = "extracted"


# --- Path safety ---

def _validate_path(p: str) -> Path:
    """Ensure path exists and is under home directory."""
    resolved = Path(p).expanduser().resolve()
    if not resolved.exists():
        raise HTTPException(404, f"Path not found: {resolved}")
    home = Path.home().resolve()
    if not str(resolved).startswith(str(home)):
        raise HTTPException(403, "Path must be under your home directory")
    return resolved


# --- Endpoints ---

@router.post("/scan")
async def scan_directory(req: ScanRequest):
    source = _validate_path(req.path)
    if not source.is_dir():
        raise HTTPException(400, "Path must be a directory")

    config = PipelineConfig(source_dir=source)
    items = await asyncio.to_thread(run_scan, config)

    session = ScanSession(source_dir=str(source), items=items)
    state.add_scan(session)

    return {
        "scan_id": session.id,
        "source_dir": str(source),
        "count": len(items),
        "items": [
            {
                "id": f"{item.file_path}:{item.line_number}",
                "name": item.name,
                "qualified_name": item.qualified_name,
                "type": item.block_type.value,
                "language": item.language.value,
                "file": str(item.file_path),
                "line": item.line_number,
                "end_line": item.end_line,
                "parent": item.parent,
            }
            for item in items
        ],
    }


@router.post("/extract")
async def extract_items(req: ExtractRequest):
    scan = state.scans.get(req.scan_id)
    if not scan:
        raise HTTPException(404, "Scan session not found")

    selected = [state.get_item(iid) for iid in req.item_ids]
    selected = [s for s in selected if s is not None]
    if not selected:
        raise HTTPException(400, "No valid items selected")

    # Run pipeline with selected items
    tmpdir = Path(tempfile.mkdtemp(prefix="code_extract_"))
    output_dir = tmpdir / req.output_name

    config = PipelineConfig(
        source_dir=Path(scan.source_dir),
        output_dir=output_dir,
        extract_all=True,
    )

    # Run pipeline in thread to avoid blocking
    def _run():
        # We override the scan to only include selected items
        from code_extract.scanner import scan_directory
        from code_extract.extractor import extract_item
        from code_extract.cleaner import clean_block
        from code_extract.formatter import format_block
        from code_extract.exporter import export_blocks, generate_manifest, generate_readme

        extracted = []
        for item in selected:
            try:
                extracted.append(extract_item(item))
            except Exception:
                continue

        cleaned = [clean_block(b) for b in extracted]
        formatted = [format_block(b) for b in cleaned]

        result = export_blocks(formatted, output_dir)
        result.readme_path = generate_readme(formatted, output_dir, Path(scan.source_dir))
        result.manifest_path = generate_manifest(formatted, result, Path(scan.source_dir))
        return result

    result = await asyncio.to_thread(_run)

    # Create zip
    zip_path = Path(shutil.make_archive(str(tmpdir / req.output_name), "zip", str(output_dir)))

    export = ExportSession(scan_id=req.scan_id, result=result, zip_path=zip_path)
    state.add_export(export)

    return {
        "export_id": export.id,
        "files_created": len(result.files_created),
        "download_url": f"/api/exports/{export.id}/download",
    }


@router.get("/preview/{item_id:path}")
async def preview_item(item_id: str):
    item = state.get_item(item_id)
    if not item:
        raise HTTPException(404, "Item not found")

    try:
        source = item.file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        raise HTTPException(500, "Could not read source file")

    lines = source.splitlines()
    start = max(0, item.line_number - 1)
    end = item.end_line if item.end_line else min(start + 100, len(lines))
    code = "\n".join(lines[start:end])

    return {
        "name": item.qualified_name,
        "type": item.block_type.value,
        "language": item.language.value,
        "file": str(item.file_path),
        "line": item.line_number,
        "end_line": item.end_line,
        "code": code,
    }


@router.get("/exports")
async def list_exports():
    return {
        "exports": [
            {
                "id": exp.id,
                "scan_id": exp.scan_id,
                "files": len(exp.result.files_created) if exp.result else 0,
                "timestamp": exp.timestamp,
                "download_url": f"/api/exports/{exp.id}/download",
            }
            for exp in state.exports.values()
        ]
    }


@router.get("/exports/{export_id}/download")
async def download_export(export_id: str):
    export = state.exports.get(export_id)
    if not export or not export.zip_path or not export.zip_path.exists():
        raise HTTPException(404, "Export not found")
    return FileResponse(
        export.zip_path,
        media_type="application/zip",
        filename=export.zip_path.name,
    )


@router.get("/autocomplete")
async def autocomplete(q: str = Query("")):
    """Directory path autocomplete."""
    if not q:
        return {"suggestions": [str(Path.home())]}

    p = Path(q).expanduser()
    if not str(p.resolve()).startswith(str(Path.home().resolve())):
        return {"suggestions": []}

    if p.is_dir():
        parent = p
        prefix = ""
    else:
        parent = p.parent
        prefix = p.name

    if not parent.exists():
        return {"suggestions": []}

    try:
        suggestions = []
        for child in sorted(parent.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                if not prefix or child.name.lower().startswith(prefix.lower()):
                    suggestions.append(str(child))
                    if len(suggestions) >= 10:
                        break
        return {"suggestions": suggestions}
    except PermissionError:
        return {"suggestions": []}


@router.websocket("/ws/progress")
async def progress_ws(websocket: WebSocket):
    """WebSocket for real-time extraction progress."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("action") == "extract":
                scan_id = msg.get("scan_id")
                item_ids = msg.get("item_ids", [])
                output_name = msg.get("output_name", "extracted")

                scan = state.scans.get(scan_id)
                if not scan:
                    await websocket.send_json({"error": "Scan not found"})
                    continue

                selected = [state.get_item(iid) for iid in item_ids]
                selected = [s for s in selected if s is not None]

                tmpdir = Path(tempfile.mkdtemp(prefix="code_extract_"))
                output_dir = tmpdir / output_name

                from code_extract.extractor import extract_item
                from code_extract.cleaner import clean_block
                from code_extract.formatter import format_block
                from code_extract.exporter import export_blocks, generate_manifest, generate_readme

                total = len(selected)
                await websocket.send_json({"stage": "extracting", "current": 0, "total": total})

                extracted = []
                for i, item in enumerate(selected):
                    try:
                        extracted.append(extract_item(item))
                    except Exception:
                        pass
                    await websocket.send_json({"stage": "extracting", "current": i + 1, "total": total})

                await websocket.send_json({"stage": "formatting", "current": 0, "total": len(extracted)})
                cleaned = [clean_block(b) for b in extracted]
                formatted = [format_block(b) for b in cleaned]
                await websocket.send_json({"stage": "formatting", "current": len(formatted), "total": len(formatted)})

                await websocket.send_json({"stage": "exporting", "current": 0, "total": 1})
                result = export_blocks(formatted, output_dir)
                result.readme_path = generate_readme(formatted, output_dir, Path(scan.source_dir))
                result.manifest_path = generate_manifest(formatted, result, Path(scan.source_dir))

                zip_path = Path(shutil.make_archive(str(tmpdir / output_name), "zip", str(output_dir)))
                export = ExportSession(scan_id=scan_id, result=result, zip_path=zip_path)
                state.add_export(export)

                await websocket.send_json({
                    "stage": "done",
                    "export_id": export.id,
                    "files_created": len(result.files_created),
                    "download_url": f"/api/exports/{export.id}/download",
                })

    except WebSocketDisconnect:
        pass
