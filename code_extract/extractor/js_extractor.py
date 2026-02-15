"""JavaScript/TypeScript extractor using brace matching."""

from __future__ import annotations

import re
from pathlib import Path

from code_extract.models import ExtractedBlock, Language, ScannedItem
from code_extract.extractor.base import BaseExtractor

_IMPORT_RE = re.compile(
    r"""^(?:import\s+.*?(?:from\s+)?['"].*?['"]|"""
    r"""(?:const|let|var)\s+.*?=\s*require\s*\(.*?\))\s*;?\s*$""",
    re.MULTILINE,
)


class JsExtractor(BaseExtractor):

    def extract(self, item: ScannedItem) -> ExtractedBlock:
        source = self._read_source(item.file_path)
        lines = source.splitlines(keepends=True)

        # Find the start of the declaration
        start_line = item.line_number - 1
        line_offset = sum(len(lines[i]) for i in range(start_line))

        # Extract using brace matching
        try:
            code = self._extract_brace_block(source, line_offset)
        except (ValueError, IndexError):
            # Fallback: grab lines until we see a closing at same indent
            end_line = min(start_line + 100, len(lines))
            code = "".join(lines[start_line:end_line])

        # Collect imports from the file
        imports: list[str] = []
        for m in _IMPORT_RE.finditer(source):
            imports.append(m.group(0).strip())

        return ExtractedBlock(
            item=item,
            source_code=code,
            imports=imports,
        )
