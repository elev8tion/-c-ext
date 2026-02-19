"""Formatter registry."""

from __future__ import annotations

from code_extract.models import CleanedBlock, FormattedBlock, Language
from code_extract.formatter.base import BaseFormatter
from code_extract.formatter.dart_formatter import DartFormatter
from code_extract.formatter.js_formatter import JsFormatter
from code_extract.formatter.python_formatter import PythonFormatter
from code_extract.formatter.generic_formatter import GenericFormatter

# Try SQL formatter
try:
    from code_extract.formatter.sql_formatter import SqlFormatter
    _sql_formatter = SqlFormatter()
except ImportError:
    _sql_formatter = None

_generic = GenericFormatter()

_FORMATTERS: dict[Language, BaseFormatter] = {
    Language.PYTHON: PythonFormatter(),
    Language.JAVASCRIPT: JsFormatter(),
    Language.TYPESCRIPT: JsFormatter(),
    Language.DART: DartFormatter(),
    Language.RUST: _generic,
    Language.GO: _generic,
    Language.JAVA: _generic,
    Language.CPP: _generic,
    Language.RUBY: _generic,
    Language.SWIFT: _generic,
    Language.KOTLIN: _generic,
    Language.CSHARP: _generic,
    Language.HTML: _generic,
}

if _sql_formatter is not None:
    _FORMATTERS[Language.SQL] = _sql_formatter


def format_block(block: CleanedBlock) -> FormattedBlock:
    """Format a cleaned block."""
    formatter = _FORMATTERS.get(block.item.language)
    if formatter is None:
        raise ValueError(f"No formatter for language: {block.item.language}")
    return formatter.format_block(block)


__all__ = ["format_block"]
