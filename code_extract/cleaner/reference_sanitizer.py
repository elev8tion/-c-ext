"""Convert relative imports to TODO comments with warnings."""

from __future__ import annotations

import re


def sanitize_references(
    imports: list[str],
    source_code: str,
) -> tuple[list[str], str, list[str]]:
    """Sanitize relative imports and internal references.

    Returns (cleaned_imports, cleaned_code, warnings).
    """
    cleaned_imports: list[str] = []
    warnings: list[str] = []

    for imp in imports:
        if _is_relative_import(imp):
            todo = _make_todo_comment(imp)
            cleaned_imports.append(todo)
            warnings.append(f"Relative import converted to TODO: {imp.strip()}")
        else:
            cleaned_imports.append(imp)

    return cleaned_imports, source_code, warnings


def _is_relative_import(import_line: str) -> bool:
    line = import_line.strip()

    # Python relative imports
    if re.match(r"from\s+\.+", line):
        return True

    # JS/TS relative imports
    if re.search(r"""(?:from|require\()\s*['"]\.\.?/""", line):
        return True

    # Dart relative imports (not package: or dart:)
    if re.match(r"import\s+'(?!package:|dart:)", line):
        return True

    return False


def _make_todo_comment(import_line: str) -> str:
    line = import_line.strip().rstrip(";")
    # Detect language by syntax
    if import_line.strip().startswith("from .") or import_line.strip().startswith("import ."):
        return f"# TODO: Resolve relative import — {line}"
    elif "'" in import_line:
        return f"// TODO: Resolve relative import — {line}"
    else:
        return f"// TODO: Resolve relative import — {line}"
