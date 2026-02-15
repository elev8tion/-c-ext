"""In-memory state for the web UI — no database required."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from code_extract.models import ExportResult, ScannedItem


@dataclass
class ScanSession:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    source_dir: str = ""
    items: list[ScannedItem] = field(default_factory=list)
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

    def add_scan(self, session: ScanSession) -> None:
        self.scans[session.id] = session
        for item in session.items:
            key = f"{item.file_path}:{item.line_number}"
            self._item_index[key] = item

    def get_item(self, item_id: str) -> ScannedItem | None:
        return self._item_index.get(item_id)

    def add_export(self, session: ExportSession) -> None:
        self.exports[session.id] = session
