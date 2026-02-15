"""Abstract base extractor with shared brace-matching."""

from __future__ import annotations

import abc
import re
from pathlib import Path

from code_extract.models import ExtractedBlock, ScannedItem


class BaseExtractor(abc.ABC):
    """Base class for language-specific extractors."""

    @abc.abstractmethod
    def extract(self, item: ScannedItem) -> ExtractedBlock:
        """Extract a code block for the given scanned item."""

    def _read_source(self, path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="replace")

    def _extract_brace_block(self, source: str, start_offset: int) -> str:
        """Extract a brace-delimited block, aware of strings and comments.

        Starts searching for the opening brace from start_offset, then
        finds the matching closing brace.
        """
        i = source.index("{", start_offset)
        depth = 0
        in_single_quote = False
        in_double_quote = False
        in_template = False
        in_line_comment = False
        in_block_comment = False
        length = len(source)
        result_start = start_offset

        pos = i
        while pos < length:
            ch = source[pos]
            next_ch = source[pos + 1] if pos + 1 < length else ""

            if in_line_comment:
                if ch == "\n":
                    in_line_comment = False
            elif in_block_comment:
                if ch == "*" and next_ch == "/":
                    in_block_comment = False
                    pos += 1
            elif in_single_quote:
                if ch == "\\" and next_ch:
                    pos += 1  # skip escaped char
                elif ch == "'":
                    in_single_quote = False
            elif in_double_quote:
                if ch == "\\" and next_ch:
                    pos += 1
                elif ch == '"':
                    in_double_quote = False
            elif in_template:
                if ch == "\\" and next_ch:
                    pos += 1
                elif ch == "`":
                    in_template = False
            else:
                if ch == "/" and next_ch == "/":
                    in_line_comment = True
                    pos += 1
                elif ch == "/" and next_ch == "*":
                    in_block_comment = True
                    pos += 1
                elif ch == "'":
                    in_single_quote = True
                elif ch == '"':
                    in_double_quote = True
                elif ch == "`":
                    in_template = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return source[result_start:pos + 1]

            pos += 1

        # If we didn't find matching brace, return what we have
        return source[result_start:pos]

    def _collect_imports(self, source: str) -> list[str]:
        """Collect import lines from the top of a file."""
        imports: list[str] = []
        for line in source.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue
            if self._is_import_line(stripped):
                imports.append(line)
            elif imports and not stripped:
                continue  # blank line between imports
            elif imports:
                break  # past the import section
        return imports

    def _is_import_line(self, line: str) -> bool:
        return (
            line.startswith("import ")
            or line.startswith("from ")
            or line.startswith("require(")
            or line.startswith("const ")
            and "require(" in line
        )
