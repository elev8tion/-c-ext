"""Strip shebangs, encoding declarations, copyright blocks, lint directives."""

from __future__ import annotations

import re

_SHEBANG_RE = re.compile(r"^#!.*\n?", re.MULTILINE)
_ENCODING_RE = re.compile(r"^#.*?coding[:=]\s*[\w.-]+.*\n?", re.MULTILINE)
_LINT_DIRECTIVE_RE = re.compile(
    r"^\s*(?://\s*(?:ignore|noinspection|eslint-disable|pylint:|type:\s*ignore|noqa)|"
    r"#\s*(?:pylint:|type:\s*ignore|noqa|pragma)|"
    r"/\*\s*eslint-disable.*?\*/)\s*\n?",
    re.MULTILINE,
)


def strip_metadata(code: str) -> tuple[str, list[str]]:
    """Strip metadata from code. Returns (cleaned_code, warnings)."""
    warnings: list[str] = []
    original = code

    # Remove shebang
    code = _SHEBANG_RE.sub("", code, count=1)

    # Remove encoding declarations
    code = _ENCODING_RE.sub("", code, count=1)

    # Remove copyright/license blocks at the top
    code = _strip_copyright_block(code)

    # Remove lint directives
    code = _LINT_DIRECTIVE_RE.sub("", code)

    if code != original:
        warnings.append("Stripped metadata (shebang/encoding/copyright/lint directives)")

    # Clean up excessive leading blank lines
    code = re.sub(r"^\n{3,}", "\n\n", code)

    return code, warnings


def _strip_copyright_block(code: str) -> str:
    """Remove leading block comment that looks like a copyright/license."""
    stripped = code.lstrip("\n")

    # Python-style block comment with triple quotes
    m = re.match(r'^("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')\s*\n', stripped)
    if m:
        content = m.group(1).lower()
        if any(kw in content for kw in ("copyright", "license", "all rights reserved")):
            return stripped[m.end():]

    # C-style block comment
    m = re.match(r"^/\*[\s\S]*?\*/\s*\n", stripped)
    if m:
        content = m.group(0).lower()
        if any(kw in content for kw in ("copyright", "license", "all rights reserved")):
            return stripped[m.end():]

    # Line comment block at top
    lines = stripped.splitlines(keepends=True)
    comment_lines: list[str] = []
    for line in lines:
        s = line.strip()
        if s.startswith("#") or s.startswith("//"):
            comment_lines.append(line)
        elif not s:
            if comment_lines:
                comment_lines.append(line)
        else:
            break

    if comment_lines:
        block = "".join(comment_lines).lower()
        if any(kw in block for kw in ("copyright", "license", "all rights reserved")):
            return stripped[len("".join(comment_lines)):]

    return code
