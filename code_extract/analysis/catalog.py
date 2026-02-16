"""Component catalog — extract function parameters and constructor params."""

from __future__ import annotations

import re

from code_extract.models import ExtractedBlock


def build_catalog(blocks: dict[str, ExtractedBlock]) -> list[dict]:
    """Build a component catalog from extracted blocks.

    Returns list of dicts with name, type, language, parameters, code, line_count.
    """
    items: list[dict] = []

    for item_id, block in blocks.items():
        params = _extract_parameters(block)
        start = block.item.line_number
        end = block.item.end_line or start
        line_count = max(end - start, len(block.source_code.splitlines()))

        items.append({
            "item_id": item_id,
            "name": block.item.qualified_name,
            "type": block.item.block_type.value,
            "language": block.item.language.value,
            "parameters": params,
            "code": block.source_code[:2000],  # truncate for safety
            "line_count": line_count,
            "file": str(block.item.file_path),
        })

    items.sort(key=lambda x: (x["type"], x["name"]))
    return items


def _extract_parameters(block: ExtractedBlock) -> list[dict]:
    """Extract function/constructor parameters from source code."""
    code = block.source_code
    lang = block.item.language.value

    if lang == "python":
        return _extract_python_params(code)
    elif lang in ("javascript", "typescript"):
        return _extract_js_params(code)
    elif lang == "dart":
        return _extract_dart_params(code)
    else:
        return _extract_generic_params(code)


def _extract_python_params(code: str) -> list[dict]:
    """Extract params from Python def/class __init__."""
    params: list[dict] = []
    # Match def name(params):
    m = re.search(r'def\s+\w+\s*\(([^)]*)\)', code)
    if not m:
        return params

    raw = m.group(1)
    for part in _split_params(raw):
        part = part.strip()
        if not part or part == "self" or part == "cls":
            continue

        name = part
        type_ann = None
        default = None

        if "=" in part:
            name_part, default = part.split("=", 1)
            name_part = name_part.strip()
            default = default.strip()
            part = name_part

        if ":" in part:
            name, type_ann = part.split(":", 1)
            name = name.strip()
            type_ann = type_ann.strip()

        params.append({
            "name": name,
            "type_annotation": type_ann,
            "default_value": default,
        })

    return params


def _extract_js_params(code: str) -> list[dict]:
    """Extract params from JS/TS functions."""
    params: list[dict] = []
    # Match function name(params) or (params) =>
    m = re.search(r'(?:function\s+\w+|(?:const|let|var)\s+\w+\s*=\s*(?:async\s+)?)\s*\(([^)]*)\)', code)
    if not m:
        m = re.search(r'\(([^)]*)\)\s*(?:=>|{)', code)
    if not m:
        return params

    raw = m.group(1)
    for part in _split_params(raw):
        part = part.strip()
        if not part:
            continue

        name = part
        type_ann = None
        default = None

        if "=" in part:
            name_part, default = part.split("=", 1)
            name_part = name_part.strip()
            default = default.strip()
            part = name_part

        if ":" in part:
            name, type_ann = part.split(":", 1)
            name = name.strip()
            type_ann = type_ann.strip()

        params.append({
            "name": name,
            "type_annotation": type_ann,
            "default_value": default,
        })

    return params


def _extract_dart_params(code: str) -> list[dict]:
    """Extract params from Dart functions/constructors."""
    params: list[dict] = []
    # Match name(params) or name({params})
    m = re.search(r'\w+\s*\(([^)]*)\)', code)
    if not m:
        return params

    raw = m.group(1)
    # Remove braces for named params
    raw = raw.replace("{", "").replace("}", "")

    for part in _split_params(raw):
        part = part.strip()
        if not part:
            continue

        # Remove 'required', 'this.'
        part = re.sub(r'^required\s+', '', part)
        part = re.sub(r'^this\.', '', part)

        name = part
        type_ann = None
        default = None

        if "=" in part:
            name_part, default = part.split("=", 1)
            name_part = name_part.strip()
            default = default.strip()
            part = name_part

        # Dart type comes before name: "String name"
        tokens = part.split()
        if len(tokens) >= 2:
            type_ann = " ".join(tokens[:-1])
            name = tokens[-1]
        elif len(tokens) == 1:
            name = tokens[0]

        params.append({
            "name": name,
            "type_annotation": type_ann,
            "default_value": default,
        })

    return params


def _extract_generic_params(code: str) -> list[dict]:
    """Generic parameter extraction."""
    params: list[dict] = []
    m = re.search(r'\w+\s*\(([^)]*)\)', code)
    if not m:
        return params

    raw = m.group(1)
    for part in _split_params(raw):
        part = part.strip()
        if part:
            params.append({"name": part, "type_annotation": None, "default_value": None})

    return params


def _split_params(raw: str) -> list[str]:
    """Split parameters respecting nested brackets/parens."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []

    for ch in raw:
        if ch in "([{<":
            depth += 1
            current.append(ch)
        elif ch in ")]}>":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)

    if current:
        parts.append("".join(current))

    return parts
