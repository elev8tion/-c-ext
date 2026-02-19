"""HTML extractor — extracts script/style blocks and inner JS constructs."""

from __future__ import annotations

import re
from pathlib import Path

from code_extract.models import CodeBlockType, ExtractedBlock, Language, ScannedItem
from code_extract.extractor.base import BaseExtractor
from code_extract.scanner.html_scanner import _HtmlBlockFinder

_IMPORT_RE = re.compile(
    r"""^(?:import\s+.*?(?:from\s+)?['"].*?['"]|"""
    r"""(?:const|let|var)\s+.*?=\s*require\s*\(.*?\))\s*;?\s*$""",
    re.MULTILINE,
)


class HtmlExtractor(BaseExtractor):

    def extract(self, item: ScannedItem, *, source: str | None = None) -> ExtractedBlock:
        source = self._read_source(item.file_path, source)

        if item.block_type in (CodeBlockType.SCRIPT_BLOCK, CodeBlockType.STYLE_BLOCK):
            return self._extract_block(item, source)
        else:
            return self._extract_inner_js(item, source)

    def _extract_block(self, item: ScannedItem, source: str) -> ExtractedBlock:
        """Extract a full <script> or <style> block's content."""
        finder = _HtmlBlockFinder()
        finder.feed(source)

        target_tag = "script" if item.block_type == CodeBlockType.SCRIPT_BLOCK else "style"
        for block in finder.blocks:
            if block.tag == target_tag and block.start_line == item.line_number:
                return ExtractedBlock(
                    item=item,
                    source_code=block.content.strip(),
                    imports=[],
                )

        # Fallback: return lines from start to end
        lines = source.splitlines(keepends=True)
        start = max(0, item.line_number - 1)
        end = item.end_line if item.end_line else min(start + 50, len(lines))
        return ExtractedBlock(
            item=item,
            source_code="".join(lines[start:end]).strip(),
            imports=[],
        )

    def _extract_inner_js(self, item: ScannedItem, source: str) -> ExtractedBlock:
        """Extract a JS construct (function, class) from within a <script> block."""
        finder = _HtmlBlockFinder()
        finder.feed(source)

        # Find the parent script block by matching the parent name
        parent_block = None
        if item.parent:
            for block in finder.blocks:
                if block.tag == "script" and f"script_block_{block.start_line}" == item.parent:
                    parent_block = block
                    break

        if parent_block is None:
            # Fallback: try to find any script block containing this line
            for block in finder.blocks:
                if block.tag == "script" and block.start_line <= item.line_number <= (block.end_line or block.start_line + 500):
                    parent_block = block
                    break

        if parent_block is None:
            # Last resort: return lines around the item
            lines = source.splitlines(keepends=True)
            start = max(0, item.line_number - 1)
            end = min(start + 50, len(lines))
            return ExtractedBlock(
                item=item,
                source_code="".join(lines[start:end]).strip(),
                imports=[],
            )

        # Find the item within the script content using line offset
        script_content = parent_block.content
        script_lines = script_content.splitlines(keepends=True)
        # item.line_number is relative to HTML file; content starts at content_start_line
        local_line = item.line_number - parent_block.content_start_line
        local_offset = sum(len(script_lines[i]) for i in range(max(0, local_line)))

        # Extract using brace matching on the script content
        try:
            code = self._extract_brace_block(script_content, local_offset)
        except (ValueError, IndexError):
            # Fallback: grab lines from item line to end of script
            end_line = min(local_line + 100, len(script_lines))
            code = "".join(script_lines[max(0, local_line):end_line])

        # Collect imports from within the script block
        imports: list[str] = []
        for m in _IMPORT_RE.finditer(script_content):
            imports.append(m.group(0).strip())

        return ExtractedBlock(
            item=item,
            source_code=code.strip(),
            imports=imports,
        )
