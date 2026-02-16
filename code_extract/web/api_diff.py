"""Semantic diff API — compare two codebases."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from code_extract.analysis.diff import semantic_diff

router = APIRouter(prefix="/api/diff")

# Cache recent diffs
_diff_cache: dict[str, dict] = {}


class DiffRequest(BaseModel):
    path_a: str
    path_b: str


def _validate_path(p: str) -> Path:
    resolved = Path(p).expanduser().resolve()
    if not resolved.exists():
        raise HTTPException(404, f"Path not found: {resolved}")
    home = Path.home().resolve()
    if not str(resolved).startswith(str(home)):
        raise HTTPException(403, "Path must be under your home directory")
    return resolved


@router.post("")
async def run_diff(req: DiffRequest):
    path_a = _validate_path(req.path_a)
    path_b = _validate_path(req.path_b)

    if not path_a.is_dir():
        raise HTTPException(400, f"Not a directory: {path_a}")
    if not path_b.is_dir():
        raise HTTPException(400, f"Not a directory: {path_b}")

    result = await asyncio.to_thread(semantic_diff, path_a, path_b)

    diff_id = uuid.uuid4().hex[:12]
    result["diff_id"] = diff_id
    _diff_cache[diff_id] = result

    return result


@router.get("/{diff_id}")
async def get_diff(diff_id: str):
    cached = _diff_cache.get(diff_id)
    if not cached:
        raise HTTPException(404, "Diff not found")
    return cached


@router.get("/{diff_id}/detail/{item_name}")
async def get_diff_detail(diff_id: str, item_name: str):
    cached = _diff_cache.get(diff_id)
    if not cached:
        raise HTTPException(404, "Diff not found")

    for item in cached.get("modified", []):
        if item["name"] == item_name:
            return item

    for item in cached.get("added", []):
        if item["name"] == item_name:
            return item

    for item in cached.get("removed", []):
        if item["name"] == item_name:
            return item

    raise HTTPException(404, f"Item {item_name} not found in diff")
