"""JavaScript/TypeScript scanner using regex patterns."""

from __future__ import annotations

import re
from pathlib import Path

from code_extract.models import CodeBlockType, Language, ScannedItem
from code_extract.scanner.base import BaseScanner

# Patterns for JS/TS constructs
_CLASS_RE = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)",
    re.MULTILINE,
)
_FUNCTION_RE = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)",
    re.MULTILINE,
)
_ARROW_CONST_RE = re.compile(
    r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(",
    re.MULTILINE,
)
_REACT_COMPONENT_RE = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:const|function)\s+([A-Z]\w+)",
    re.MULTILINE,
)


class JsScanner(BaseScanner):
    language = Language.JAVASCRIPT
    extensions = (".js", ".jsx", ".ts", ".tsx", ".mjs")

    def scan_file(self, file_path: Path) -> list[ScannedItem]:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        lang = Language.TYPESCRIPT if file_path.suffix in (".ts", ".tsx") else Language.JAVASCRIPT
        items: list[ScannedItem] = []
        seen: set[tuple[str, int]] = set()
        lines = source.splitlines()

        for m in _CLASS_RE.finditer(source):
            line_no = source[:m.start()].count("\n") + 1
            name = m.group(1)
            if (name, line_no) not in seen:
                seen.add((name, line_no))
                items.append(ScannedItem(
                    name=name,
                    block_type=CodeBlockType.CLASS,
                    language=lang,
                    file_path=file_path,
                    line_number=line_no,
                ))

        for m in _FUNCTION_RE.finditer(source):
            line_no = source[:m.start()].count("\n") + 1
            name = m.group(1)
            if (name, line_no) not in seen:
                seen.add((name, line_no))
                items.append(ScannedItem(
                    name=name,
                    block_type=CodeBlockType.FUNCTION,
                    language=lang,
                    file_path=file_path,
                    line_number=line_no,
                ))

        for m in _ARROW_CONST_RE.finditer(source):
            line_no = source[:m.start()].count("\n") + 1
            name = m.group(1)
            if (name, line_no) not in seen:
                seen.add((name, line_no))
                block_type = CodeBlockType.COMPONENT if name[0].isupper() else CodeBlockType.FUNCTION
                items.append(ScannedItem(
                    name=name,
                    block_type=block_type,
                    language=lang,
                    file_path=file_path,
                    line_number=line_no,
                ))

        # Detect React components (function Xxx that returns JSX)
        for m in _REACT_COMPONENT_RE.finditer(source):
            line_no = source[:m.start()].count("\n") + 1
            name = m.group(1)
            if (name, line_no) not in seen:
                # Check for JSX-like return in nearby lines
                start_idx = max(0, line_no - 1)
                end_idx = min(len(lines), line_no + 50)
                chunk = "\n".join(lines[start_idx:end_idx])
                if "<" in chunk and ("return" in chunk or "=>" in chunk):
                    seen.add((name, line_no))
                    items.append(ScannedItem(
                        name=name,
                        block_type=CodeBlockType.COMPONENT,
                        language=lang,
                        file_path=file_path,
                        line_number=line_no,
                    ))

        items.sort(key=lambda i: i.line_number)
        return items
