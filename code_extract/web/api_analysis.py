"""Analysis API — dependency graph, transitive deps, smart extract, dead code, architecture, health."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from code_extract.web.state import state
from code_extract.analysis.dependency_graph import DependencyGraphBuilder
from code_extract.analysis.dead_code import detect_dead_code
from code_extract.analysis.architecture import generate_architecture
from code_extract.analysis.health import analyze_health
from code_extract.analysis.graph_models import DependencyGraph

router = APIRouter(prefix="/api/analysis")
_builder = DependencyGraphBuilder()


class ScanIdRequest(BaseModel):
    scan_id: str


class SmartExtractRequest(BaseModel):
    scan_id: str
    item_ids: list[str]


class DepsRequest(BaseModel):
    scan_id: str
    item_id: str


def _get_or_build_graph(scan_id: str) -> DependencyGraph:
    """Get cached graph or build one."""
    cached = state.get_analysis(scan_id, "graph")
    if cached:
        return cached

    blocks = state.get_blocks_for_scan(scan_id)
    if not blocks:
        raise HTTPException(400, "No extracted blocks found. Scan may still be processing.")

    graph = _builder.build(blocks)
    state.store_analysis(scan_id, "graph", graph)
    return graph


@router.post("/graph")
async def build_graph(req: ScanIdRequest):
    graph = await asyncio.to_thread(_get_or_build_graph, req.scan_id)
    return {
        "scan_id": req.scan_id,
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
    }


@router.post("/deps")
async def get_deps(req: DepsRequest):
    graph = await asyncio.to_thread(_get_or_build_graph, req.scan_id)

    result = _builder.resolve_transitive(graph, req.item_id)
    return {
        "root_id": req.item_id,
        "direct": list(result.direct),
        "all_transitive": list(result.all_transitive),
        "cycles": result.cycles,
    }


@router.get("/graph/{scan_id}")
async def get_cached_graph(scan_id: str):
    cached = state.get_analysis(scan_id, "graph")
    if not cached:
        raise HTTPException(404, "No cached graph for this scan")
    return {
        "scan_id": scan_id,
        "nodes": len(cached.nodes),
        "edges": len(cached.edges),
    }


@router.post("/smart-extract")
async def smart_extract(req: SmartExtractRequest):
    """Extract selected items plus all their transitive dependencies."""
    scan = state.scans.get(req.scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")

    blocks = state.get_blocks_for_scan(req.scan_id)
    if not blocks:
        raise HTTPException(400, "No extracted blocks available")

    graph = await asyncio.to_thread(_get_or_build_graph, req.scan_id)

    # Resolve all transitive deps for selected items
    all_item_ids = set(req.item_ids)
    for item_id in req.item_ids:
        result = _builder.resolve_transitive(graph, item_id)
        all_item_ids.update(result.all_transitive)

    # Collect blocks and run through extract/clean/format/export pipeline
    from code_extract.cleaner import clean_block
    from code_extract.formatter import format_block
    from code_extract.exporter import export_blocks, generate_manifest, generate_readme
    from code_extract.web.state import ExportSession

    selected_blocks = [blocks[iid] for iid in all_item_ids if iid in blocks]
    if not selected_blocks:
        raise HTTPException(400, "No matching blocks found")

    def _run():
        cleaned = [clean_block(b) for b in selected_blocks]
        formatted = [format_block(b) for b in cleaned]

        tmpdir = Path(tempfile.mkdtemp(prefix="code_extract_"))
        output_dir = tmpdir / "smart_extracted"

        result = export_blocks(formatted, output_dir)
        result.readme_path = generate_readme(formatted, output_dir, Path(scan.source_dir))
        result.manifest_path = generate_manifest(formatted, result, Path(scan.source_dir))

        zip_path = Path(shutil.make_archive(str(tmpdir / "smart_extracted"), "zip", str(output_dir)))

        export = ExportSession(scan_id=req.scan_id, result=result, zip_path=zip_path)
        state.add_export(export)
        return export, len(result.files_created), len(all_item_ids)

    export, files_count, total_items = await asyncio.to_thread(_run)

    return {
        "export_id": export.id,
        "files_created": files_count,
        "total_items": total_items,
        "download_url": f"/api/exports/{export.id}/download",
    }


@router.post("/dead-code")
async def dead_code(req: ScanIdRequest):
    cached = state.get_analysis(req.scan_id, "deadcode")
    if cached:
        return {"items": cached}
    graph = await asyncio.to_thread(_get_or_build_graph, req.scan_id)
    items = detect_dead_code(graph)
    state.store_analysis(req.scan_id, "deadcode", items)
    return {"items": items}


@router.post("/architecture")
async def architecture(req: ScanIdRequest):
    cached = state.get_analysis(req.scan_id, "architecture")
    if cached:
        return cached
    scan = state.scans.get(req.scan_id)
    source_dir = scan.source_dir if scan else ""
    graph = await asyncio.to_thread(_get_or_build_graph, req.scan_id)
    result = generate_architecture(graph, source_dir)
    state.store_analysis(req.scan_id, "architecture", result)
    return result


@router.post("/health")
async def health(req: ScanIdRequest):
    cached = state.get_analysis(req.scan_id, "health")
    if cached:
        return cached
    blocks = state.get_blocks_for_scan(req.scan_id)
    if not blocks:
        raise HTTPException(400, "No extracted blocks available")
    graph = await asyncio.to_thread(_get_or_build_graph, req.scan_id)
    result = analyze_health(blocks, graph)
    state.store_analysis(req.scan_id, "health", result)
    return result


@router.get("/item-stats/{scan_id}")
async def item_stats(scan_id: str):
    """Per-item stats: deps count, size in bytes, line count, health score."""
    cached = state.get_analysis(scan_id, "item_stats")
    if cached:
        return {"stats": cached}

    blocks = state.get_blocks_for_scan(scan_id)
    if not blocks:
        raise HTTPException(400, "No extracted blocks available")

    # Try to get graph for dep counts (non-fatal if missing)
    graph = None
    try:
        graph = await asyncio.to_thread(_get_or_build_graph, scan_id)
    except Exception:
        pass

    def _compute():
        stats = {}
        for item_id, block in blocks.items():
            code = getattr(block, "code", "") or ""
            line_count = len(code.splitlines()) if code else 0
            size_bytes = len(code.encode("utf-8")) if code else 0

            # Dependency count from graph
            deps = 0
            if graph:
                node = graph.nodes.get(item_id)
                if node:
                    deps = len(getattr(node, "edges_out", []) if hasattr(node, "edges_out") else [])
                # Fallback: count edges where source matches
                if deps == 0:
                    deps = sum(1 for e in graph.edges if getattr(e, "source", None) == item_id)

            # Simple health heuristic per item
            health_score = 100
            if line_count > 100:
                health_score -= min(30, (line_count - 100) // 5)
            if deps > 10:
                health_score -= min(20, (deps - 10) * 2)
            health_score = max(0, health_score)

            stats[item_id] = {
                "deps": deps,
                "size_bytes": size_bytes,
                "line_count": line_count,
                "health_score": health_score,
            }
        return stats

    result = await asyncio.to_thread(_compute)
    state.store_analysis(scan_id, "item_stats", result)
    return {"stats": result}
