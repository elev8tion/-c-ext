"""Remix Board API — palette, conflict detection, and build endpoints."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from os.path import basename
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from code_extract.web.state import state, ExportSession

router = APIRouter(prefix="/api/remix")


# ── Request / Response Models ────────────────────────────────

class RemixCanvasItem(BaseModel):
    scan_id: str
    item_id: str


class RemixConflictResolution(BaseModel):
    composite_key: str
    new_name: str


class RemixValidateRequest(BaseModel):
    canvas_items: list[RemixCanvasItem]
    full: bool = False


class RemixDetectRequest(BaseModel):
    canvas_items: list[RemixCanvasItem]


class RemixBuildRequest(BaseModel):
    canvas_items: list[RemixCanvasItem]
    resolutions: list[RemixConflictResolution] = []
    project_name: str = "remix-package"
    include_deps: bool = False


# ── GET /api/remix/palette ───────────────────────────────────

@router.get("/palette")
async def remix_palette():
    """Return all ready scans with their items for the remix palette."""
    palette = []
    for scan_id, scan in state.scans.items():
        if scan.status != "ready":
            continue
        items = []
        for item in scan.items:
            item_id = f"{item.file_path}:{item.line_number}"
            items.append({
                "item_id": item_id,
                "name": item.name,
                "type": item.block_type.value,
                "language": item.language.value,
                "parent": item.parent,
            })
        palette.append({
            "scan_id": scan_id,
            "project_name": basename(scan.source_dir) if scan.source_dir else scan_id,
            "source_dir": scan.source_dir,
            "items": items,
        })
    return {"palette": palette}


# ── POST /api/remix/validate ──────────────────────────────────

@router.post("/validate")
async def validate_remix_endpoint(req: RemixValidateRequest):
    """Run compatibility validation on the canvas items."""
    from code_extract.analysis.remix import (
        RemixSource, merge_blocks, validate_remix,
    )

    sources, filtered_stores = _resolve_canvas_items(req.canvas_items)
    merged, origin_map = merge_blocks(sources, filtered_stores)

    result = validate_remix(merged, origin_map, full=req.full)

    return {
        "errors": [
            {"severity": i.severity, "rule": i.rule, "message": i.message, "items": i.items}
            for i in result.errors
        ],
        "warnings": [
            {"severity": i.severity, "rule": i.rule, "message": i.message, "items": i.items}
            for i in result.warnings
        ],
        "conflicts": result.conflicts,
        "is_buildable": result.is_buildable,
        "total_items": len(merged),
    }


# ── POST /api/remix/detect-conflicts ─────────────────────────

@router.post("/detect-conflicts")
async def detect_conflicts(req: RemixDetectRequest):
    """Detect naming conflicts among selected canvas items."""
    from code_extract.analysis.remix import (
        RemixSource, merge_blocks, detect_naming_conflicts,
    )

    sources, filtered_stores = _resolve_canvas_items(req.canvas_items)
    merged, origin_map = merge_blocks(sources, filtered_stores)
    conflicts = detect_naming_conflicts(merged, origin_map)

    return {
        "conflicts": [
            {"name": c.name, "items": c.items}
            for c in conflicts
        ],
        "total_items": len(merged),
    }


# ── POST /api/remix/build ───────────────────────────────────

@router.post("/build")
async def remix_build(req: RemixBuildRequest):
    """Full remix build pipeline: validate → merge → resolve → deps → clean → format → export → zip."""
    from code_extract.analysis.remix import (
        RemixSource, merge_blocks, apply_conflict_resolutions, validate_remix,
    )
    from code_extract.analysis.dependency_graph import DependencyGraphBuilder
    from code_extract.cleaner import clean_block
    from code_extract.formatter import format_block
    from code_extract.exporter.package_exporter import export_package
    from code_extract.models import ExportResult

    sources, filtered_stores = _resolve_canvas_items(req.canvas_items)
    if not sources:
        raise HTTPException(400, "No valid items on canvas")

    def _run():
        # 0. Quick validation gate
        merged_check, origin_check = merge_blocks(sources, filtered_stores)
        validation = validate_remix(merged_check, origin_check, full=False)
        if not validation.is_buildable:
            msg = validation.errors[0].message if validation.errors else "Validation failed"
            raise HTTPException(400, msg)

        # 1. Merge
        merged, _origin = merge_blocks(sources, filtered_stores)
        if not merged:
            raise HTTPException(400, "No blocks found for selected items")

        # 2. Apply renames
        resolutions_dict = {r.composite_key: r.new_name for r in req.resolutions}
        if resolutions_dict:
            merged = apply_conflict_resolutions(merged, resolutions_dict)

        # 3. Optionally resolve transitive deps
        warnings: list[str] = []
        if req.include_deps:
            builder = DependencyGraphBuilder()
            graph = builder.build(merged)
            base_keys = set(merged.keys())
            expanded: set[str] = set()
            for key in base_keys:
                result = builder.resolve_transitive(graph, key)
                expanded.update(result.all_transitive)
            # Add any transitive blocks that are already in merged
            for dep_key in expanded:
                if dep_key not in merged:
                    warnings.append(f"Transitive dep {dep_key} not in remix canvas")

        # 4. Clean + format
        blocks_list = list(merged.values())
        cleaned = [clean_block(b) for b in blocks_list]
        formatted = [format_block(b) for b in cleaned]

        # 5. Export
        tmpdir = Path(tempfile.mkdtemp(prefix="code_extract_remix_"))
        output_dir = tmpdir / req.project_name
        pkg_result = export_package(formatted, output_dir, req.project_name)

        # 6. Zip
        zip_path = Path(shutil.make_archive(
            str(tmpdir / req.project_name), "zip", str(output_dir),
        ))

        export_result = ExportResult(
            output_dir=output_dir,
            files_created=[Path(f) for f in pkg_result["files_created"]],
        )
        export = ExportSession(scan_id="remix", result=export_result, zip_path=zip_path)
        state.add_export(export)

        return export, len(pkg_result["files_created"]), len(resolutions_dict), warnings

    export, file_count, resolved, warnings = await asyncio.to_thread(_run)

    return {
        "export_id": export.id,
        "files_created": file_count,
        "conflicts_resolved": resolved,
        "download_url": f"/api/exports/{export.id}/download",
        "warnings": warnings,
    }


# ── Internal helpers ─────────────────────────────────────────

def _resolve_canvas_items(
    canvas_items: list[RemixCanvasItem],
) -> tuple[list, dict[str, dict]]:
    """Build RemixSource list and filtered block stores from canvas items."""
    from code_extract.analysis.remix import RemixSource

    # Group item_ids by scan_id
    by_scan: dict[str, list[str]] = {}
    for ci in canvas_items:
        by_scan.setdefault(ci.scan_id, []).append(ci.item_id)

    sources = []
    filtered_stores: dict[str, dict] = {}

    for scan_id, item_ids in by_scan.items():
        scan = state.scans.get(scan_id)
        if not scan or scan.status != "ready":
            continue

        blocks = state.get_blocks_for_scan(scan_id)
        if not blocks:
            continue

        # Filter to only selected item_ids
        selected = {iid: blocks[iid] for iid in item_ids if iid in blocks}
        if not selected:
            continue

        project_name = basename(scan.source_dir) if scan.source_dir else scan_id
        sources.append(RemixSource(
            scan_id=scan_id,
            project_name=project_name,
            source_dir=scan.source_dir,
        ))
        filtered_stores[scan_id] = selected

    return sources, filtered_stores
