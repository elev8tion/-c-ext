"""Smart tools API — package factory, pattern cloner, boilerplate, migration."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from code_extract.web.state import state, ExportSession

router = APIRouter(prefix="/api/tools")


# ── Package Factory ──────────────────────────────────────────

class PackageRequest(BaseModel):
    scan_id: str
    item_ids: list[str]
    package_name: str = "extracted-package"


@router.post("/package")
async def create_package(req: PackageRequest):
    scan = state.scans.get(req.scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")

    blocks = state.get_blocks_for_scan(req.scan_id)
    if not blocks:
        raise HTTPException(400, "No extracted blocks available")

    # Optionally resolve deps
    from code_extract.analysis.dependency_graph import DependencyGraphBuilder
    builder = DependencyGraphBuilder()
    graph = builder.build(blocks)

    all_ids = set(req.item_ids)
    for item_id in req.item_ids:
        result = builder.resolve_transitive(graph, item_id)
        all_ids.update(result.all_transitive)

    selected = [blocks[iid] for iid in all_ids if iid in blocks]
    if not selected:
        raise HTTPException(400, "No matching blocks")

    from code_extract.cleaner import clean_block
    from code_extract.formatter import format_block
    from code_extract.exporter.package_exporter import export_package

    def _run():
        cleaned = [clean_block(b) for b in selected]
        formatted = [format_block(b) for b in cleaned]

        tmpdir = Path(tempfile.mkdtemp(prefix="code_extract_pkg_"))
        output_dir = tmpdir / req.package_name

        pkg_result = export_package(formatted, output_dir, req.package_name)

        zip_path = Path(shutil.make_archive(str(tmpdir / req.package_name), "zip", str(output_dir)))

        from code_extract.models import ExportResult
        export_result = ExportResult(
            output_dir=output_dir,
            files_created=[Path(f) for f in pkg_result["files_created"]],
        )
        export = ExportSession(scan_id=req.scan_id, result=export_result, zip_path=zip_path)
        state.add_export(export)
        return export, len(pkg_result["files_created"])

    export, file_count = await asyncio.to_thread(_run)

    return {
        "export_id": export.id,
        "files_created": file_count,
        "download_url": f"/api/exports/{export.id}/download",
    }


# ── Pattern Cloner ────────────────────────────────────────────

class ClonePreviewRequest(BaseModel):
    scan_id: str
    item_ids: list[str]
    original_name: str
    new_name: str


class CloneRequest(BaseModel):
    scan_id: str
    item_ids: list[str]
    original_name: str
    new_name: str
    target_directory: str = ""


@router.post("/clone/preview")
async def clone_preview(req: ClonePreviewRequest):
    from code_extract.analysis.pattern_cloner import preview_clone

    blocks = state.get_blocks_for_scan(req.scan_id)
    if not blocks:
        raise HTTPException(400, "No extracted blocks available")

    results = []
    for item_id in req.item_ids:
        block = blocks.get(item_id)
        if not block:
            continue
        preview = preview_clone(block.source_code, req.original_name, req.new_name)
        results.append({
            "item_id": item_id,
            "name": block.item.qualified_name,
            **preview,
        })

    return {"items": results}


@router.post("/clone")
async def clone(req: CloneRequest):
    from code_extract.analysis.pattern_cloner import clone_pattern

    blocks = state.get_blocks_for_scan(req.scan_id)
    if not blocks:
        raise HTTPException(400, "No extracted blocks available")

    def _run():
        tmpdir = Path(tempfile.mkdtemp(prefix="code_extract_clone_"))
        output_dir = tmpdir / req.new_name
        output_dir.mkdir(parents=True, exist_ok=True)

        files: list[str] = []
        for item_id in req.item_ids:
            block = blocks.get(item_id)
            if not block:
                continue
            cloned = clone_pattern(block.source_code, req.original_name, req.new_name)
            filename = block.item.name.replace(req.original_name, req.new_name)
            ext = Path(str(block.item.file_path)).suffix or ".txt"
            fp = output_dir / f"{filename}{ext}"
            fp.write_text(cloned, encoding="utf-8")
            files.append(str(fp))

        zip_path = Path(shutil.make_archive(str(tmpdir / req.new_name), "zip", str(output_dir)))

        from code_extract.models import ExportResult
        export = ExportSession(
            scan_id=req.scan_id,
            result=ExportResult(output_dir=output_dir, files_created=[Path(f) for f in files]),
            zip_path=zip_path,
        )
        state.add_export(export)
        return export, len(files)

    export, file_count = await asyncio.to_thread(_run)

    return {
        "export_id": export.id,
        "files_created": file_count,
        "download_url": f"/api/exports/{export.id}/download",
    }


# ── Boilerplate Generator ────────────────────────────────────

class PatternFilter(BaseModel):
    directory: str
    block_type: str


class BoilerplateRequest(BaseModel):
    scan_id: str
    item_ids: list[str]
    template_name: str = "template"
    pattern_filter: PatternFilter | None = None


class BoilerplateGenerateRequest(BaseModel):
    template_code: str
    variables: dict[str, str]


class BoilerplateBatchRequest(BaseModel):
    template_code: str
    variable_sets: list[dict[str, str]]


@router.post("/boilerplate")
async def detect_boilerplate(req: BoilerplateRequest):
    from code_extract.analysis.boilerplate import (
        detect_patterns, generate_template, filter_blocks_by_pattern,
    )

    blocks = state.get_blocks_for_scan(req.scan_id)
    if not blocks:
        raise HTTPException(400, "No extracted blocks available")

    # If a pattern filter is provided, narrow to matching blocks
    if req.pattern_filter:
        filtered = filter_blocks_by_pattern(
            blocks, req.pattern_filter.directory, req.pattern_filter.block_type,
        )
        selected = filtered if filtered else [blocks[iid] for iid in req.item_ids if iid in blocks]
    else:
        selected = [blocks[iid] for iid in req.item_ids if iid in blocks]

    if not selected:
        raise HTTPException(400, "No matching blocks")

    template = generate_template(selected, req.template_name)

    # Also detect patterns in the full codebase
    patterns = detect_patterns(blocks)

    return {
        "template": template,
        "patterns": patterns[:10],
    }


@router.post("/boilerplate/generate")
async def generate_from_template(req: BoilerplateGenerateRequest):
    from code_extract.analysis.boilerplate import apply_template
    result = apply_template(req.template_code, req.variables)
    return {"generated_code": result}


@router.post("/boilerplate/generate-batch")
async def generate_batch(req: BoilerplateBatchRequest):
    from code_extract.analysis.boilerplate import batch_apply_template
    if len(req.variable_sets) > 50:
        raise HTTPException(400, "Maximum 50 variants allowed")
    results = batch_apply_template(req.template_code, req.variable_sets)
    return {"generated_codes": results}


# ── Migration Mapper ──────────────────────────────────────────

class MigrationDetectRequest(BaseModel):
    scan_id: str


class MigrationApplyRequest(BaseModel):
    scan_id: str
    item_id: str
    pattern_id: str


@router.post("/migration/detect")
async def detect_migration(req: MigrationDetectRequest):
    from code_extract.analysis.migration import detect_migrations

    blocks = state.get_blocks_for_scan(req.scan_id)
    if not blocks:
        raise HTTPException(400, "No extracted blocks available")

    results = await asyncio.to_thread(detect_migrations, blocks)
    return {"patterns": results}


@router.post("/migration/apply")
async def apply_migration_endpoint(req: MigrationApplyRequest):
    from code_extract.analysis.migration import apply_migration

    blocks = state.get_blocks_for_scan(req.scan_id)
    if not blocks:
        raise HTTPException(400, "No extracted blocks available")

    block = blocks.get(req.item_id)
    if not block:
        raise HTTPException(404, "Item not found")

    result = await asyncio.to_thread(apply_migration, block, req.pattern_id)
    return result
