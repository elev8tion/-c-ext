"""Extractor registry."""

from __future__ import annotations

from code_extract.models import ExtractedBlock, Language, ScannedItem
from code_extract.extractor.base import BaseExtractor
from code_extract.extractor.dart_extractor import DartExtractor
from code_extract.extractor.js_extractor import JsExtractor
from code_extract.extractor.python_extractor import PythonExtractor

# Try tree-sitter extractor
_ts_extractor = None
try:
    from code_extract.extractor.treesitter_extractor import TreeSitterExtractor
    _ts_extractor = TreeSitterExtractor()
except ImportError:
    pass

# Try SQL extractor
_sql_extractor = None
try:
    from code_extract.extractor.sql_extractor import SqlExtractor
    _sql_extractor = SqlExtractor()
except ImportError:
    pass

# Languages that always use their own extractor
_EXTRACTORS: dict[Language, BaseExtractor] = {
    Language.PYTHON: PythonExtractor(),
}

# Languages that fall back to regex extractors if tree-sitter unavailable
_FALLBACK_EXTRACTORS: dict[Language, BaseExtractor] = {
    Language.JAVASCRIPT: JsExtractor(),
    Language.TYPESCRIPT: JsExtractor(),
    Language.DART: DartExtractor(),
}

# Languages that only tree-sitter supports
_TREESITTER_ONLY: set[Language] = {
    Language.RUST, Language.GO, Language.JAVA, Language.CPP,
    Language.RUBY, Language.SWIFT, Language.KOTLIN, Language.CSHARP,
}


def extract_item(item: ScannedItem, *, source: str | None = None) -> ExtractedBlock:
    """Extract a code block for the given scanned item.

    Args:
        item: The scanned item to extract.
        source: Pre-read file source to avoid redundant disk reads.
    """
    # Python always uses AST extractor
    if item.language in _EXTRACTORS:
        return _EXTRACTORS[item.language].extract(item, source=source)

    # SQL has its own extractor
    if item.language == Language.SQL and _sql_extractor is not None:
        return _sql_extractor.extract(item, source=source)

    # Tree-sitter languages
    if _ts_extractor is not None and item.language in (_TREESITTER_ONLY | set(_FALLBACK_EXTRACTORS)):
        return _ts_extractor.extract(item, source=source)

    # Fallback to regex extractors
    extractor = _FALLBACK_EXTRACTORS.get(item.language)
    if extractor is not None:
        return extractor.extract(item, source=source)

    raise ValueError(f"No extractor for language: {item.language}")


def clear_extractor_caches():
    """Clear all extractor caches (call between scans)."""
    if _ts_extractor is not None:
        _ts_extractor.clear_cache()


__all__ = [
    "BaseExtractor",
    "PythonExtractor",
    "JsExtractor",
    "DartExtractor",
    "extract_item",
]
