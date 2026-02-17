"""Dart extractor using brace matching."""

from __future__ import annotations

import re
from pathlib import Path

from code_extract.models import ExtractedBlock, ScannedItem
from code_extract.extractor.base import BaseExtractor

_DART_IMPORT_RE = re.compile(
    r"^import\s+'.*?';\s*$",
    re.MULTILINE,
)


class DartExtractor(BaseExtractor):

    def extract(self, item: ScannedItem, *, source: str | None = None) -> ExtractedBlock:
        source = self._read_source(item.file_path, source)
        lines = source.splitlines(keepends=True)

        start_line = item.line_number - 1
        line_offset = sum(len(lines[i]) for i in range(start_line))

        try:
            code = self._extract_brace_block(source, line_offset)
        except (ValueError, IndexError):
            end_line = min(start_line + 200, len(lines))
            code = "".join(lines[start_line:end_line])

        # Collect imports
        imports: list[str] = []
        for m in _DART_IMPORT_RE.finditer(source):
            imports.append(m.group(0).strip())

        return ExtractedBlock(
            item=item,
            source_code=code,
            imports=imports,
        )
