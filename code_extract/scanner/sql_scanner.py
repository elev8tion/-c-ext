"""SQL scanner — regex-based detection of SQL DDL objects and ORM models."""

from __future__ import annotations

import re
import fnmatch
from pathlib import Path

from code_extract.models import CodeBlockType, Language, ScannedItem
from code_extract.scanner.base import BaseScanner

# SQL DDL patterns
_CREATE_TABLE_RE = re.compile(
    r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:\"?(\w+)\"?\.)?\"?(\w+)\"?",
    re.IGNORECASE | re.MULTILINE,
)
_CREATE_VIEW_RE = re.compile(
    r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:\"?(\w+)\"?\.)?\"?(\w+)\"?",
    re.IGNORECASE | re.MULTILINE,
)
_CREATE_FUNCTION_RE = re.compile(
    r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(?:\"?(\w+)\"?\.)?\"?(\w+)\"?",
    re.IGNORECASE | re.MULTILINE,
)
_CREATE_TRIGGER_RE = re.compile(
    r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+\"?(\w+)\"?",
    re.IGNORECASE | re.MULTILINE,
)
_CREATE_INDEX_RE = re.compile(
    r"^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?\"?(\w+)\"?",
    re.IGNORECASE | re.MULTILINE,
)
_CREATE_POLICY_RE = re.compile(
    r"^\s*CREATE\s+POLICY\s+\"?(\w+)\"?",
    re.IGNORECASE | re.MULTILINE,
)

# Supabase migration detection
_MIGRATION_RE = re.compile(r"supabase/migrations/(\d+)_\w+\.sql$")

# ORM model patterns (for Python/JS/TS files)
_SQLALCHEMY_RE = re.compile(
    r"^class\s+(\w+)\s*\(.*(?:Base|db\.Model).*\)\s*:",
    re.MULTILINE,
)
_DJANGO_MODEL_RE = re.compile(
    r"^class\s+(\w+)\s*\(.*models\.Model.*\)\s*:",
    re.MULTILINE,
)
_TYPEORM_RE = re.compile(
    r"@Entity\(\)\s*\n\s*(?:export\s+)?class\s+(\w+)",
    re.MULTILINE,
)
_PRISMA_MODEL_RE = re.compile(
    r"^model\s+(\w+)\s*\{",
    re.MULTILINE,
)


class SqlScanner(BaseScanner):
    language = Language.SQL
    extensions = (".sql", ".prisma")

    def __init__(self, skip_dirs: list[str] | None = None):
        super().__init__(skip_dirs=skip_dirs)

    def scan_directory(self, directory: Path) -> list[ScannedItem]:
        """Scan for SQL files and ORM models in code files."""
        items: list[ScannedItem] = []
        for path in sorted(directory.rglob("*")):
            if path.is_dir():
                continue
            if self._should_skip(path):
                continue
            try:
                if path.suffix == ".sql":
                    items.extend(self._scan_sql_file(path))
                elif path.suffix == ".prisma":
                    items.extend(self._scan_prisma_file(path))
                elif path.suffix == ".py":
                    items.extend(self._scan_python_orm(path))
                elif path.suffix in (".ts", ".js"):
                    items.extend(self._scan_typeorm(path))
            except Exception:
                continue
        items.sort(key=lambda i: (str(i.file_path), i.line_number))
        return items

    def scan_file(self, file_path: Path) -> list[ScannedItem]:
        if file_path.suffix == ".sql":
            return self._scan_sql_file(file_path)
        if file_path.suffix == ".prisma":
            return self._scan_prisma_file(file_path)
        return []

    def _scan_sql_file(self, file_path: Path) -> list[ScannedItem]:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        items: list[ScannedItem] = []

        # Check if this is a Supabase migration
        is_migration = bool(_MIGRATION_RE.search(str(file_path)))

        patterns: list[tuple[re.Pattern, CodeBlockType]] = [
            (_CREATE_TABLE_RE, CodeBlockType.TABLE),
            (_CREATE_VIEW_RE, CodeBlockType.VIEW),
            (_CREATE_FUNCTION_RE, CodeBlockType.FUNCTION_SQL),
            (_CREATE_TRIGGER_RE, CodeBlockType.TRIGGER),
            (_CREATE_INDEX_RE, CodeBlockType.INDEX),
            (_CREATE_POLICY_RE, CodeBlockType.POLICY),
        ]

        seen: set[tuple[str, int]] = set()
        for pattern, block_type in patterns:
            for m in pattern.finditer(source):
                line_no = source[:m.start()].count("\n") + 1
                # Get the name from the last group (handle schema.name patterns)
                groups = [g for g in m.groups() if g is not None]
                name = groups[-1] if groups else "unknown"

                if (name, line_no) in seen:
                    continue
                seen.add((name, line_no))

                actual_type = CodeBlockType.MIGRATION if is_migration else block_type
                items.append(ScannedItem(
                    name=name,
                    block_type=actual_type,
                    language=Language.SQL,
                    file_path=file_path,
                    line_number=line_no,
                ))

        items.sort(key=lambda i: i.line_number)
        return items

    def _scan_prisma_file(self, file_path: Path) -> list[ScannedItem]:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        items: list[ScannedItem] = []
        for m in _PRISMA_MODEL_RE.finditer(source):
            line_no = source[:m.start()].count("\n") + 1
            items.append(ScannedItem(
                name=m.group(1),
                block_type=CodeBlockType.TABLE,
                language=Language.SQL,
                file_path=file_path,
                line_number=line_no,
            ))
        return items

    def _scan_python_orm(self, file_path: Path) -> list[ScannedItem]:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        # Only scan if it looks like it has ORM imports
        if "Base" not in source and "db.Model" not in source and "models.Model" not in source:
            return []
        items: list[ScannedItem] = []
        for pattern in (_SQLALCHEMY_RE, _DJANGO_MODEL_RE):
            for m in pattern.finditer(source):
                line_no = source[:m.start()].count("\n") + 1
                items.append(ScannedItem(
                    name=m.group(1),
                    block_type=CodeBlockType.TABLE,
                    language=Language.SQL,
                    file_path=file_path,
                    line_number=line_no,
                ))
        return items

    def _scan_typeorm(self, file_path: Path) -> list[ScannedItem]:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        if "@Entity" not in source:
            return []
        items: list[ScannedItem] = []
        for m in _TYPEORM_RE.finditer(source):
            line_no = source[:m.start()].count("\n") + 1
            items.append(ScannedItem(
                name=m.group(1),
                block_type=CodeBlockType.TABLE,
                language=Language.SQL,
                file_path=file_path,
                line_number=line_no,
            ))
        return items
