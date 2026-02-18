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


class RemixResolveRequest(BaseModel):
    canvas_items: list[RemixCanvasItem]


class RemixTemplateItem(BaseModel):
    name: str
    type: str
    language: str
    parent: str | None = None


class RemixTemplateMatchRequest(BaseModel):
    items: list[RemixTemplateItem]


class RemixPreviewRequest(BaseModel):
    canvas_items: list[RemixCanvasItem]
    resolutions: list[RemixConflictResolution] = []
    project_name: str = "remix-package"


# ── GET /api/remix/palette ───────────────────────────────────

@router.get("/palette")
async def remix_palette():
    """Return all ready scans with their items for the remix palette."""
    palette = []
    for scan_id, scan in state.scans.items():
        if scan.status != "ready":
            continue
        blocks = state.get_blocks_for_scan(scan_id)
        items = []
        for item in scan.items:
            item_id = f"{item.file_path}:{item.line_number}"
            item_data = {
                "item_id": item_id,
                "name": item.name,
                "type": item.block_type.value,
                "language": item.language.value,
                "parent": item.parent,
            }
            # Enrich with type_references and imports from extracted blocks
            if blocks and item_id in blocks:
                item_data["type_references"] = blocks[item_id].type_references
                item_data["imports"] = blocks[item_id].imports
            else:
                item_data["type_references"] = []
                item_data["imports"] = []
            items.append(item_data)
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
        RemixSource, merge_blocks, validate_remix, compute_compatibility_score,
    )

    sources, filtered_stores = _resolve_canvas_items(req.canvas_items)
    merged, origin_map = merge_blocks(sources, filtered_stores)

    result = validate_remix(merged, origin_map, full=req.full)

    response = {
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

    # Include compatibility score on full validation
    if req.full and merged:
        score_data = compute_compatibility_score(merged, origin_map)
        response["score"] = score_data["score"]
        response["grade"] = score_data["grade"]
        response["score_breakdown"] = score_data["breakdown"]

    return response


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


# ── POST /api/remix/resolve-deps ────────────────────────────

@router.post("/resolve-deps")
async def resolve_deps(req: RemixResolveRequest):
    """Find unresolved deps that can be resolved from the palette."""
    from code_extract.analysis.remix import (
        RemixSource, merge_blocks, find_resolvable_deps,
    )

    sources, filtered_stores = _resolve_canvas_items(req.canvas_items)
    merged, _origin_map = merge_blocks(sources, filtered_stores)

    # Build flat palette from all scans
    all_palette_flat = _build_palette_flat()

    deps = find_resolvable_deps(merged, all_palette_flat)

    resolvable = [d for d in deps if len(d["candidates"]) > 0]
    unresolvable = [d for d in deps if len(d["candidates"]) == 0]

    return {
        "resolvable": resolvable,
        "unresolvable": [{"unresolved_ref": d["unresolved_ref"], "needed_by": d["needed_by"]} for d in unresolvable],
        "total_unresolved": len(deps),
    }


# ── POST /api/remix/template/match ──────────────────────────

@router.post("/template/match")
async def template_match(req: RemixTemplateMatchRequest):
    """Match template item descriptors to current palette items."""
    matches = []
    for tmpl_item in req.items:
        found = False
        for scan_id, scan in state.scans.items():
            if scan.status != "ready":
                continue
            for item in scan.items:
                item_id = f"{item.file_path}:{item.line_number}"
                if (item.name == tmpl_item.name
                        and item.block_type.value == tmpl_item.type
                        and item.language.value == tmpl_item.language):
                    project_name = basename(scan.source_dir) if scan.source_dir else scan_id
                    matches.append({
                        "template_name": tmpl_item.name,
                        "scan_id": scan_id,
                        "item_id": item_id,
                        "name": item.name,
                        "type": item.block_type.value,
                        "language": item.language.value,
                        "parent": item.parent,
                        "project_name": project_name,
                    })
                    found = True
                    break
            if found:
                break
        if not found:
            matches.append({
                "template_name": tmpl_item.name,
                "unmatched": True,
            })
    return {"matches": matches}


# ── POST /api/remix/preview ─────────────────────────────────

@router.post("/preview")
async def remix_preview(req: RemixPreviewRequest):
    """Generate a live preview of remix output without writing to disk."""
    from code_extract.analysis.remix import (
        RemixSource, merge_blocks, preview_remix,
    )

    sources, filtered_stores = _resolve_canvas_items(req.canvas_items)
    if not sources:
        raise HTTPException(400, "No valid items on canvas")

    merged, _origin = merge_blocks(sources, filtered_stores)
    if not merged:
        raise HTTPException(400, "No blocks found for selected items")

    resolutions_dict = {r.composite_key: r.new_name for r in req.resolutions}

    result = await asyncio.to_thread(
        preview_remix, merged, resolutions_dict or None, req.project_name,
    )

    return result


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


def _build_palette_flat() -> list[dict]:
    """Build a flat list of all palette items across all scans."""
    items: list[dict] = []
    for scan_id, scan in state.scans.items():
        if scan.status != "ready":
            continue
        project_name = basename(scan.source_dir) if scan.source_dir else scan_id
        blocks = state.get_blocks_for_scan(scan_id)
        for item in scan.items:
            item_id = f"{item.file_path}:{item.line_number}"
            items.append({
                "scan_id": scan_id,
                "item_id": item_id,
                "name": item.name,
                "type": item.block_type.value,
                "language": item.language.value,
                "parent": item.parent,
                "project_name": project_name,
            })
    return items
