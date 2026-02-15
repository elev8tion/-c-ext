"""Abstract base scanner."""

from __future__ import annotations

import abc
import fnmatch
from pathlib import Path

from code_extract.models import Language, ScannedItem


class BaseScanner(abc.ABC):
    """Base class for language-specific scanners."""

    language: Language
    extensions: tuple[str, ...]

    def __init__(self, skip_dirs: list[str] | None = None):
        self.skip_dirs = skip_dirs or [
            "node_modules", ".git", "__pycache__", ".dart_tool",
            "build", "dist", ".next", ".venv", "venv", "env",
        ]

    @abc.abstractmethod
    def scan_file(self, file_path: Path) -> list[ScannedItem]:
        """Scan a single file and return discovered items."""

    def scan_directory(self, directory: Path) -> list[ScannedItem]:
        """Recursively scan a directory for items."""
        items: list[ScannedItem] = []
        for path in sorted(directory.rglob("*")):
            if path.is_dir():
                continue
            if self._should_skip(path):
                continue
            if path.suffix in self.extensions:
                try:
                    items.extend(self.scan_file(path))
                except Exception:
                    continue
        return items

    def _should_skip(self, path: Path) -> bool:
        for part in path.parts:
            for pattern in self.skip_dirs:
                if fnmatch.fnmatch(part, pattern):
                    return True
        return False
