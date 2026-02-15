"""Create output directory with extracted files, index files, and dependency configs."""

from __future__ import annotations

import json
from pathlib import Path

from code_extract.models import ExportResult, FormattedBlock, Language


# File extensions per language
_EXTENSIONS: dict[Language, str] = {
    Language.PYTHON: ".py",
    Language.JAVASCRIPT: ".js",
    Language.TYPESCRIPT: ".ts",
    Language.DART: ".dart",
    Language.RUST: ".rs",
    Language.GO: ".go",
    Language.JAVA: ".java",
    Language.CPP: ".cpp",
    Language.RUBY: ".rb",
    Language.SWIFT: ".swift",
    Language.KOTLIN: ".kt",
    Language.CSHARP: ".cs",
    Language.SQL: ".sql",
}

# Subdirectory names per language
_SUBDIRS: dict[Language, str] = {
    Language.PYTHON: "python",
    Language.JAVASCRIPT: "javascript",
    Language.TYPESCRIPT: "typescript",
    Language.DART: "dart",
    Language.RUST: "rust",
    Language.GO: "go",
    Language.JAVA: "java",
    Language.CPP: "cpp",
    Language.RUBY: "ruby",
    Language.SWIFT: "swift",
    Language.KOTLIN: "kotlin",
    Language.CSHARP: "csharp",
    Language.SQL: "sql",
}


def export_blocks(blocks: list[FormattedBlock], output_dir: Path) -> ExportResult:
    """Export formatted blocks to an output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    result = ExportResult(output_dir=output_dir)

    # Group blocks by language
    by_language: dict[Language, list[FormattedBlock]] = {}
    for block in blocks:
        lang = block.item.language
        by_language.setdefault(lang, []).append(block)

    # Write files per language
    for lang, lang_blocks in by_language.items():
        subdir = output_dir / _SUBDIRS[lang]
        subdir.mkdir(exist_ok=True)

        for block in lang_blocks:
            filename = _safe_filename(block.item.name) + _EXTENSIONS[lang]
            file_path = subdir / filename

            # Build file content with header comment
            content = _build_file_content(block, lang)
            file_path.write_text(content, encoding="utf-8")
            result.files_created.append(file_path)

        # Generate index file
        index_path = _write_index_file(subdir, lang, lang_blocks)
        result.files_created.append(index_path)

        # Generate dependency config
        dep_path = _write_dependency_config(output_dir, lang)
        if dep_path:
            result.files_created.append(dep_path)

    return result


def _build_file_content(block: FormattedBlock, lang: Language) -> str:
    parts: list[str] = []

    # Add header as comment
    if block.header:
        if lang == Language.SQL:
            comment_prefix = "--"
        elif lang in (Language.PYTHON, Language.RUBY):
            comment_prefix = "#"
        else:
            comment_prefix = "//"
        for line in block.header.splitlines():
            parts.append(f"{comment_prefix} {line}")
        parts.append("")

    parts.append(block.source_code)

    # Ensure trailing newline
    content = "\n".join(parts)
    if not content.endswith("\n"):
        content += "\n"
    return content


def _safe_filename(name: str) -> str:
    """Convert a name to a safe snake_case filename."""
    result: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and name[i - 1].islower():
            result.append("_")
        result.append(ch.lower())
    # Replace any non-alphanumeric chars
    filename = "".join(result)
    filename = "".join(c if c.isalnum() or c == "_" else "_" for c in filename)
    return filename


def _write_index_file(
    subdir: Path,
    lang: Language,
    blocks: list[FormattedBlock],
) -> Path:
    if lang == Language.PYTHON:
        index_path = subdir / "__init__.py"
        lines = ['"""Extracted code modules."""', ""]
        for block in blocks:
            module = _safe_filename(block.item.name)
            lines.append(f"from .{module} import {block.item.name}")
        lines.append("")
        index_path.write_text("\n".join(lines), encoding="utf-8")

    elif lang in (Language.JAVASCRIPT, Language.TYPESCRIPT):
        ext = _EXTENSIONS[lang]
        index_path = subdir / f"index{ext}"
        lines: list[str] = []
        for block in blocks:
            module = _safe_filename(block.item.name)
            lines.append(f"export {{ {block.item.name} }} from './{module}';")
        lines.append("")
        index_path.write_text("\n".join(lines), encoding="utf-8")

    elif lang == Language.DART:
        index_path = subdir / "index.dart"
        lines = []
        for block in blocks:
            module = _safe_filename(block.item.name)
            lines.append(f"export '{module}.dart';")
        lines.append("")
        index_path.write_text("\n".join(lines), encoding="utf-8")

    elif lang == Language.RUST:
        index_path = subdir / "mod.rs"
        lines = []
        for block in blocks:
            module = _safe_filename(block.item.name)
            lines.append(f"pub mod {module};")
        lines.append("")
        index_path.write_text("\n".join(lines), encoding="utf-8")

    elif lang == Language.GO:
        index_path = subdir / "doc.go"
        lines = [
            "// Package extracted contains extracted code modules.",
            "package extracted",
            "",
        ]
        index_path.write_text("\n".join(lines), encoding="utf-8")

    elif lang == Language.JAVA:
        index_path = subdir / "package-info.java"
        lines = [
            "/** Extracted code modules. */",
            "package extracted;",
            "",
        ]
        index_path.write_text("\n".join(lines), encoding="utf-8")

    elif lang == Language.SQL:
        index_path = subdir / "index.sql"
        lines = ["-- Extracted SQL objects"]
        for block in blocks:
            module = _safe_filename(block.item.name)
            lines.append(f"\\i {module}.sql")
        lines.append("")
        index_path.write_text("\n".join(lines), encoding="utf-8")

    else:
        index_path = subdir / "index.txt"
        lines = [block.item.name for block in blocks]
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return index_path


def _write_dependency_config(output_dir: Path, lang: Language) -> Path | None:
    if lang == Language.PYTHON:
        path = output_dir / "requirements.txt"
        if not path.exists():
            path.write_text("# Add dependencies here\n", encoding="utf-8")
        return path

    elif lang in (Language.JAVASCRIPT, Language.TYPESCRIPT):
        path = output_dir / "package.json"
        if not path.exists():
            data = {
                "name": "extracted-modules",
                "version": "1.0.0",
                "description": "Extracted code modules",
                "dependencies": {},
            }
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return path

    elif lang == Language.DART:
        path = output_dir / "pubspec.yaml"
        if not path.exists():
            content = (
                "name: extracted_modules\n"
                "description: Extracted code modules\n"
                "version: 1.0.0\n"
                "\n"
                "environment:\n"
                "  sdk: '>=3.0.0 <4.0.0'\n"
                "\n"
                "dependencies:\n"
                "  flutter:\n"
                "    sdk: flutter\n"
            )
            path.write_text(content, encoding="utf-8")
        return path

    return None
