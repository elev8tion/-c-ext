"""HTML scanner — finds inline <script> and <style> blocks, plus JS constructs within scripts."""

from __future__ import annotations

import bisect
import re
from html.parser import HTMLParser
from pathlib import Path

from code_extract.models import CodeBlockType, Language, ScannedItem
from code_extract.scanner.base import BaseScanner

# Script types that contain executable JS (absent type= also means JS)
_NON_JS_TYPES = {"application/json", "application/ld+json", "importmap"}

# JS regex patterns that allow leading whitespace (for indented code in <script> blocks)
_HTML_CLASS_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)",
    re.MULTILINE,
)
_HTML_FUNCTION_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)",
    re.MULTILINE,
)
_HTML_ARROW_CONST_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(",
    re.MULTILINE,
)


class _HtmlBlock:
    """A located <script> or <style> block in an HTML file."""

    __slots__ = ("tag", "attrs", "start_line", "end_line", "content", "content_start_line")

    def __init__(
        self,
        tag: str,
        attrs: dict[str, str | None],
        start_line: int,
        end_line: int,
        content: str,
        content_start_line: int,
    ):
        self.tag = tag
        self.attrs = attrs
        self.start_line = start_line
        self.end_line = end_line
        self.content = content
        self.content_start_line = content_start_line


class _HtmlBlockFinder(HTMLParser):
    """HTMLParser subclass that locates <script> and <style> blocks."""

    def __init__(self):
        super().__init__()
        self.blocks: list[_HtmlBlock] = []
        self._current_tag: str | None = None
        self._current_attrs: dict[str, str | None] = {}
        self._current_start_line: int = 0
        self._content_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag in ("script", "style"):
            self._current_tag = tag
            self._current_attrs = dict(attrs)
            self._current_start_line = self.getpos()[0]
            self._content_parts = []

    def handle_data(self, data: str):
        if self._current_tag is not None:
            self._content_parts.append(data)

    def handle_endtag(self, tag: str):
        if tag == self._current_tag and self._current_tag is not None:
            end_line = self.getpos()[0]
            content = "".join(self._content_parts)
            # Content starts on the line after the opening tag
            content_start_line = self._current_start_line + 1
            self.blocks.append(_HtmlBlock(
                tag=self._current_tag,
                attrs=self._current_attrs,
                start_line=self._current_start_line,
                end_line=end_line,
                content=content,
                content_start_line=content_start_line,
            ))
            self._current_tag = None
            self._current_attrs = {}
            self._content_parts = []


class HtmlScanner(BaseScanner):
    language = Language.HTML
    extensions = (".html", ".htm")

    def scan_file(self, file_path: Path) -> list[ScannedItem]:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        items: list[ScannedItem] = []

        # Parse HTML to find script/style blocks
        finder = _HtmlBlockFinder()
        finder.feed(source)

        script_index = 0
        for block in finder.blocks:
            if block.tag == "style":
                content_stripped = block.content.strip()
                if not content_stripped:
                    continue
                items.append(ScannedItem(
                    name=f"style_block_{block.start_line}",
                    block_type=CodeBlockType.STYLE_BLOCK,
                    language=Language.HTML,
                    file_path=file_path,
                    line_number=block.start_line,
                    end_line=block.end_line,
                ))

            elif block.tag == "script":
                # Skip external scripts (<script src="...">)
                if "src" in block.attrs:
                    continue

                content_stripped = block.content.strip()
                if not content_stripped:
                    continue

                script_index += 1
                block_name = f"script_block_{block.start_line}"

                # Emit the script block item
                items.append(ScannedItem(
                    name=block_name,
                    block_type=CodeBlockType.SCRIPT_BLOCK,
                    language=Language.HTML,
                    file_path=file_path,
                    line_number=block.start_line,
                    end_line=block.end_line,
                ))

                # Skip non-JS script types (JSON, importmap, etc.)
                script_type = block.attrs.get("type", "").lower()
                if script_type and script_type in _NON_JS_TYPES:
                    continue

                # Run JS regex patterns on script content to find inner constructs
                self._scan_js_in_script(
                    block.content, block.content_start_line,
                    block_name, file_path, items,
                )

        items.sort(key=lambda i: i.line_number)
        return items

    def _scan_js_in_script(
        self,
        script_content: str,
        content_start_line: int,
        parent_name: str,
        file_path: Path,
        items: list[ScannedItem],
    ) -> None:
        """Run JS regex patterns on script content, adjusting line numbers."""
        # Build newline offset index for the script content
        newline_offsets = [i for i, ch in enumerate(script_content) if ch == "\n"]

        def _line_at(offset: int) -> int:
            return bisect.bisect_left(newline_offsets, offset) + content_start_line

        seen: set[tuple[str, int]] = set()

        for m in _HTML_CLASS_RE.finditer(script_content):
            line_no = _line_at(m.start())
            name = m.group(1)
            if (name, line_no) not in seen:
                seen.add((name, line_no))
                items.append(ScannedItem(
                    name=name,
                    block_type=CodeBlockType.CLASS,
                    language=Language.HTML,
                    file_path=file_path,
                    line_number=line_no,
                    parent=parent_name,
                ))

        for m in _HTML_FUNCTION_RE.finditer(script_content):
            line_no = _line_at(m.start())
            name = m.group(1)
            if (name, line_no) not in seen:
                seen.add((name, line_no))
                items.append(ScannedItem(
                    name=name,
                    block_type=CodeBlockType.FUNCTION,
                    language=Language.HTML,
                    file_path=file_path,
                    line_number=line_no,
                    parent=parent_name,
                ))

        for m in _HTML_ARROW_CONST_RE.finditer(script_content):
            line_no = _line_at(m.start())
            name = m.group(1)
            if (name, line_no) not in seen:
                seen.add((name, line_no))
                block_type = CodeBlockType.COMPONENT if name[0].isupper() else CodeBlockType.FUNCTION
                items.append(ScannedItem(
                    name=name,
                    block_type=block_type,
                    language=Language.HTML,
                    file_path=file_path,
                    line_number=line_no,
                    parent=parent_name,
                ))
