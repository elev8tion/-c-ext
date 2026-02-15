"""Remove unused imports via word-boundary matching."""

from __future__ import annotations

import re


def clean_imports(imports: list[str], source_code: str) -> tuple[list[str], list[str]]:
    """Return (kept_imports, removed_imports)."""
    kept: list[str] = []
    removed: list[str] = []

    for imp in imports:
        names = _extract_imported_names(imp)
        if not names:
            # Can't determine what's imported — keep it
            kept.append(imp)
            continue

        if any(_name_used_in_code(name, source_code) for name in names):
            kept.append(imp)
        else:
            removed.append(imp)

    return kept, removed


def _extract_imported_names(import_line: str) -> list[str]:
    """Extract the names being imported from an import statement."""
    line = import_line.strip().rstrip(";")

    # Python: from X import a, b, c
    m = re.match(r"from\s+\S+\s+import\s+(.+)", line)
    if m:
        names_part = m.group(1)
        names = []
        for part in names_part.split(","):
            part = part.strip()
            if " as " in part:
                names.append(part.split(" as ")[-1].strip())
            else:
                names.append(part.strip("()").strip())
        return [n for n in names if n and n.isidentifier()]

    # Python: import X or import X as Y
    m = re.match(r"import\s+(.+)", line)
    if m and "from" not in line:
        names_part = m.group(1)
        # Dart: import 'package:...'
        if "'" in names_part or '"' in names_part:
            return []  # Can't easily determine usage for Dart package imports
        names = []
        for part in names_part.split(","):
            part = part.strip()
            if " as " in part:
                names.append(part.split(" as ")[-1].strip())
            else:
                name = part.split(".")[-1].strip()
                names.append(name)
        return [n for n in names if n and n.isidentifier()]

    # JS: const { a, b } = require(...)
    m = re.match(r"(?:const|let|var)\s+\{([^}]+)\}\s*=\s*require", line)
    if m:
        return [n.strip().split(" as ")[-1].strip() for n in m.group(1).split(",") if n.strip()]

    # JS: const X = require(...)
    m = re.match(r"(?:const|let|var)\s+(\w+)\s*=\s*require", line)
    if m:
        return [m.group(1)]

    # JS: import { a, b } from '...'
    m = re.match(r"import\s+\{([^}]+)\}\s+from", line)
    if m:
        return [n.strip().split(" as ")[-1].strip() for n in m.group(1).split(",") if n.strip()]

    # JS: import X from '...'
    m = re.match(r"import\s+(\w+)\s+from", line)
    if m:
        return [m.group(1)]

    return []


def _name_used_in_code(name: str, code: str) -> bool:
    """Check if a name is used in the code via word-boundary matching."""
    pattern = rf"\b{re.escape(name)}\b"
    return bool(re.search(pattern, code))
