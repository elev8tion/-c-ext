"""Dart/Flutter scanner using regex patterns."""

from __future__ import annotations

import re
from pathlib import Path

from code_extract.models import CodeBlockType, Language, ScannedItem
from code_extract.scanner.base import BaseScanner

_CLASS_RE = re.compile(
    r"^(?:abstract\s+)?class\s+(\w+)",
    re.MULTILINE,
)
_MIXIN_RE = re.compile(
    r"^mixin\s+(\w+)",
    re.MULTILINE,
)
_FUNCTION_RE = re.compile(
    r"^(?:\w+\s+)?(\w+)\s*\([^)]*\)\s*(?:async\s*)?{",
    re.MULTILINE,
)
_WIDGET_BASES = (
    "StatelessWidget", "StatefulWidget", "State<",
    "HookWidget", "ConsumerWidget",
)
_PROVIDER_RE = re.compile(
    r"final\s+\w+\s*=\s*(?:StateNotifier)?Provider",
    re.MULTILINE,
)


class DartScanner(BaseScanner):
    language = Language.DART
    extensions = (".dart",)

    def scan_file(self, file_path: Path) -> list[ScannedItem]:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        items: list[ScannedItem] = []
        seen: set[tuple[str, int]] = set()

        for m in _CLASS_RE.finditer(source):
            line_no = source[:m.start()].count("\n") + 1
            name = m.group(1)
            if (name, line_no) in seen:
                continue
            seen.add((name, line_no))

            # Check if it extends a widget base
            line = source[m.start():source.find("\n", m.start()) + 1] if "\n" in source[m.start():] else source[m.start():]
            rest = source[m.start():m.start() + 200]
            is_widget = any(base in rest for base in _WIDGET_BASES)

            items.append(ScannedItem(
                name=name,
                block_type=CodeBlockType.WIDGET if is_widget else CodeBlockType.CLASS,
                language=self.language,
                file_path=file_path,
                line_number=line_no,
            ))

        for m in _MIXIN_RE.finditer(source):
            line_no = source[:m.start()].count("\n") + 1
            name = m.group(1)
            if (name, line_no) not in seen:
                seen.add((name, line_no))
                items.append(ScannedItem(
                    name=name,
                    block_type=CodeBlockType.MIXIN,
                    language=self.language,
                    file_path=file_path,
                    line_number=line_no,
                ))

        items.sort(key=lambda i: i.line_number)
        return items
