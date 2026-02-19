"""Scanner registry and dispatcher."""

from __future__ import annotations

from pathlib import Path

from code_extract.models import Language, ScannedItem
from code_extract.scanner.base import BaseScanner
from code_extract.scanner.python_scanner import PythonScanner
from code_extract.scanner.js_scanner import JsScanner
from code_extract.scanner.dart_scanner import DartScanner
from code_extract.scanner.html_scanner import HtmlScanner

# Try to import tree-sitter scanner; fall back to regex scanners
_HAS_TREESITTER = False
try:
    from code_extract.scanner.treesitter_scanner import TreeSitterScanner
    _HAS_TREESITTER = True
except ImportError:
    TreeSitterScanner = None  # type: ignore[misc,assignment]

# Try SQL scanner (always available, regex-based)
try:
    from code_extract.scanner.sql_scanner import SqlScanner
    _HAS_SQL = True
except ImportError:
    _HAS_SQL = False


def _get_scanners(skip_dirs: list[str] | None = None) -> list:
    scanners: list = []

    # Python always uses stdlib ast
    scanners.append(PythonScanner(skip_dirs=skip_dirs))

    if _HAS_TREESITTER:
        # Tree-sitter handles JS, TS, Dart, Rust, Go, Java, C++, Ruby, Swift, Kotlin, C#
        scanners.append(TreeSitterScanner(skip_dirs=skip_dirs))
    else:
        # Fallback to regex scanners for JS and Dart
        scanners.append(JsScanner(skip_dirs=skip_dirs))
        scanners.append(DartScanner(skip_dirs=skip_dirs))

    if _HAS_SQL:
        scanners.append(SqlScanner(skip_dirs=skip_dirs))

    # HTML scanner (stdlib only, always available)
    scanners.append(HtmlScanner(skip_dirs=skip_dirs))

    return scanners


def scan_directory(
    directory: Path,
    skip_dirs: list[str] | None = None,
) -> list[ScannedItem]:
    """Scan a directory with all available scanners."""
    items: list[ScannedItem] = []
    for scanner in _get_scanners(skip_dirs):
        items.extend(scanner.scan_directory(directory))
    items.sort(key=lambda i: (str(i.file_path), i.line_number))
    return items


__all__ = [
    "BaseScanner",
    "PythonScanner",
    "JsScanner",
    "DartScanner",
    "HtmlScanner",
    "scan_directory",
]
