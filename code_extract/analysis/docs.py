"""Living documentation generator — auto-docs from AST data."""

from __future__ import annotations

import re

from code_extract.models import ExtractedBlock


def generate_docs(blocks: dict[str, ExtractedBlock]) -> dict:
    """Generate documentation sections from extracted blocks.

    Returns: {sections: [{name, type, signature, description, members, file}]}
    """
    sections: list[dict] = []

    # Group methods under their parent classes
    classes: dict[str, list[ExtractedBlock]] = {}
    standalone: list[tuple[str, ExtractedBlock]] = []

    for item_id, block in blocks.items():
        if block.item.parent:
            classes.setdefault(block.item.parent, []).append(block)
        else:
            standalone.append((item_id, block))

    # Document standalone items
    for item_id, block in standalone:
        section = _build_section(item_id, block)

        # Add methods if this is a class
        if block.item.block_type.value in ("class", "widget", "component", "struct"):
            members = classes.get(block.item.name, [])
            section["members"] = [
                _format_member(m) for m in members
            ]

        sections.append(section)

    sections.sort(key=lambda s: (s["type"], s["name"]))
    return {"sections": sections}


def generate_markdown(blocks: dict[str, ExtractedBlock]) -> str:
    """Generate markdown documentation."""
    data = generate_docs(blocks)
    lines = ["# API Documentation\n"]

    current_type = ""
    for section in data["sections"]:
        if section["type"] != current_type:
            current_type = section["type"]
            lines.append(f"\n## {current_type.title()}s\n")

        lines.append(f"### {section['name']}\n")
        if section.get("signature"):
            lines.append(f"```\n{section['signature']}\n```\n")
        if section.get("description"):
            lines.append(f"{section['description']}\n")
        if section.get("members"):
            lines.append("**Members:**\n")
            for member in section["members"]:
                lines.append(f"- {member}")
            lines.append("")

    return "\n".join(lines)


def _build_section(item_id: str, block: ExtractedBlock) -> dict:
    """Build a documentation section for one item."""
    signature = _extract_signature(block)
    description = _extract_description(block)

    return {
        "item_id": item_id,
        "name": block.item.qualified_name,
        "type": block.item.block_type.value,
        "language": block.item.language.value,
        "signature": signature,
        "description": description,
        "file": str(block.item.file_path),
        "members": [],
    }


def _extract_signature(block: ExtractedBlock) -> str:
    """Extract function/class signature from first line(s)."""
    lines = block.source_code.strip().splitlines()
    if not lines:
        return ""

    first = lines[0].strip()

    # Python: def name(params): or class Name(bases):
    if block.item.language.value == "python":
        m = re.match(r'((?:async\s+)?(?:def|class)\s+\w+\s*\([^)]*\))', first)
        if m:
            return m.group(1)

    # JS/TS: function name(params) or const name = (params) =>
    if block.item.language.value in ("javascript", "typescript"):
        m = re.match(r'((?:export\s+)?(?:async\s+)?(?:function\s+)?\w+\s*\([^)]*\))', first)
        if m:
            return m.group(1)

    # Dart: ReturnType name(params)
    if block.item.language.value == "dart":
        m = re.match(r'([\w<>?\s]+\w+\s*\([^)]*\))', first)
        if m:
            return m.group(1)

    # Generic: return first line up to open brace
    return first.split("{")[0].strip()


def _extract_description(block: ExtractedBlock) -> str:
    """Extract docstring/comment description."""
    code = block.source_code.strip()

    # Python docstring
    m = re.search(r'"""(.*?)"""', code, re.DOTALL)
    if m:
        return m.group(1).strip().splitlines()[0]

    m = re.search(r"'''(.*?)'''", code, re.DOTALL)
    if m:
        return m.group(1).strip().splitlines()[0]

    # JSDoc or /** */ comment
    m = re.search(r'/\*\*(.*?)\*/', code, re.DOTALL)
    if m:
        desc = m.group(1).strip()
        # Clean up * prefixes
        lines = [l.strip().lstrip("* ").strip() for l in desc.splitlines()]
        lines = [l for l in lines if l and not l.startswith("@")]
        return lines[0] if lines else ""

    # Single-line // comment right before definition
    lines = code.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("//"):
            return line.strip().lstrip("/ ").strip()
        if not line.strip().startswith("//") and not line.strip().startswith("#"):
            break

    return ""


def _format_member(block: ExtractedBlock) -> str:
    """Format a method/member as a one-liner for docs."""
    sig = _extract_signature(block)
    if sig:
        return sig
    return f"{block.item.name}()"
