"""In-memory state for the web UI — no database required."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from code_extract.models import ExportResult, ExtractedBlock, ScannedItem


@dataclass
class ScanSession:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    source_dir: str = ""
    items: list[ScannedItem] = field(default_factory=list)
    status: str = "ready"  # scanning → extracting → ready
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ExportSession:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    scan_id: str = ""
    result: ExportResult | None = None
    zip_path: Path | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class AppState:
    """Singleton in-memory state shared by all API routes."""

    def __init__(self):
        self.scans: dict[str, ScanSession] = {}
        self.exports: dict[str, ExportSession] = {}
        self._item_index: dict[str, ScannedItem] = {}
        self._block_index: dict[str, dict[str, ExtractedBlock]] = {}
        self._analyses: dict[str, dict[str, Any]] = {}

    def add_scan(self, session: ScanSession) -> None:
        self.scans[session.id] = session
        for item in session.items:
            key = f"{item.file_path}:{item.line_number}"
            self._item_index[key] = item

    def get_item(self, item_id: str) -> ScannedItem | None:
        return self._item_index.get(item_id)

    def add_export(self, session: ExportSession) -> None:
        self.exports[session.id] = session

    # ── Block storage (v0.3) ────────────────────────────────

    def store_blocks(self, scan_id: str, blocks: dict[str, ExtractedBlock]) -> None:
        self._block_index[scan_id] = blocks

    def get_blocks_for_scan(self, scan_id: str) -> dict[str, ExtractedBlock] | None:
        return self._block_index.get(scan_id)

    # ── Analysis cache (v0.3) ───────────────────────────────

    def store_analysis(self, scan_id: str, name: str, data: Any) -> None:
        if scan_id not in self._analyses:
            self._analyses[scan_id] = {}
        self._analyses[scan_id][name] = data

    def get_analysis(self, scan_id: str, name: str) -> Any | None:
        return self._analyses.get(scan_id, {}).get(name)


# Module-level singleton — all routers import this
state = AppState()
