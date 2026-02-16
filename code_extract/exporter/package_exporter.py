"""Micro-Package Factory — generate publishable packages with manifests."""

from __future__ import annotations

import json
from pathlib import Path

from code_extract.models import FormattedBlock


def export_package(
    blocks: list[FormattedBlock],
    output_dir: Path,
    package_name: str = "extracted-package",
    version: str = "0.1.0",
) -> dict:
    """Export blocks as a self-contained, publishable package.

    Generates language-appropriate manifest (package.json, pubspec.yaml, etc.)
    and an index file that re-exports everything.

    Returns: {output_dir, files_created, manifest_type}
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    files_created: list[str] = []

    # Group blocks by language
    by_language: dict[str, list[FormattedBlock]] = {}
    for block in blocks:
        lang = block.item.language.value
        by_language.setdefault(lang, []).append(block)

    # Determine primary language
    primary_lang = max(by_language, key=lambda k: len(by_language[k])) if by_language else "python"

    # Write source files
    src_dir = output_dir / "src"
    src_dir.mkdir(exist_ok=True)

    for block in blocks:
        filename = _get_filename(block)
        file_path = src_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)

        content = ""
        if block.header:
            content += block.header + "\n\n"
        content += block.source_code

        file_path.write_text(content, encoding="utf-8")
        files_created.append(str(file_path))

    # Generate manifest
    manifest_type = _generate_manifest(output_dir, blocks, package_name, version, primary_lang)
    files_created.append(str(output_dir / manifest_type))

    # Generate index/entry file
    index_path = _generate_index(src_dir, blocks, primary_lang)
    if index_path:
        files_created.append(str(index_path))

    return {
        "output_dir": str(output_dir),
        "files_created": files_created,
        "manifest_type": manifest_type,
    }


def _get_filename(block: FormattedBlock) -> str:
    """Get appropriate filename for a block."""
    lang = block.item.language.value
    name = block.item.name

    extensions = {
        "python": ".py",
        "javascript": ".js",
        "typescript": ".ts",
        "dart": ".dart",
        "rust": ".rs",
        "go": ".go",
        "java": ".java",
        "cpp": ".cpp",
        "ruby": ".rb",
        "swift": ".swift",
        "kotlin": ".kt",
        "csharp": ".cs",
    }

    ext = extensions.get(lang, ".txt")

    # Convert PascalCase to snake_case for Python
    if lang == "python":
        import re
        name = re.sub(r'([A-Z])', r'_\1', name).lstrip('_').lower()

    return f"{name}{ext}"


def _generate_manifest(
    output_dir: Path,
    blocks: list[FormattedBlock],
    package_name: str,
    version: str,
    primary_lang: str,
) -> str:
    """Generate language-appropriate package manifest. Returns filename."""
    if primary_lang in ("javascript", "typescript"):
        manifest = {
            "name": package_name,
            "version": version,
            "main": "src/index.js",
            "types": "src/index.d.ts" if primary_lang == "typescript" else None,
            "keywords": ["extracted", "code-extract"],
        }
        manifest = {k: v for k, v in manifest.items() if v is not None}
        (output_dir / "package.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return "package.json"

    if primary_lang == "dart":
        pubspec = f"""name: {package_name.replace('-', '_')}
version: {version}
description: Extracted code package
environment:
  sdk: '>=3.0.0 <4.0.0'
"""
        (output_dir / "pubspec.yaml").write_text(pubspec, encoding="utf-8")
        return "pubspec.yaml"

    if primary_lang == "rust":
        cargo = f"""[package]
name = "{package_name}"
version = "{version}"
edition = "2021"

[dependencies]
"""
        (output_dir / "Cargo.toml").write_text(cargo, encoding="utf-8")
        return "Cargo.toml"

    # Default: Python pyproject.toml
    pyproject = f"""[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{package_name}"
version = "{version}"
description = "Extracted code package"
requires-python = ">=3.10"
"""
    (output_dir / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    return "pyproject.toml"


def _generate_index(
    src_dir: Path,
    blocks: list[FormattedBlock],
    primary_lang: str,
) -> Path | None:
    """Generate an index file that re-exports all items."""
    if not blocks:
        return None

    if primary_lang in ("javascript", "typescript"):
        ext = ".ts" if primary_lang == "typescript" else ".js"
        lines = []
        for block in blocks:
            name = block.item.name
            filename = _get_filename(block).replace(ext, "")
            lines.append(f"export {{ {name} }} from './{filename}';")
        index_path = src_dir / f"index{ext}"
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return index_path

    if primary_lang == "python":
        lines = []
        for block in blocks:
            filename = _get_filename(block).replace(".py", "")
            lines.append(f"from .{filename} import {block.item.name}")
        index_path = src_dir / "__init__.py"
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return index_path

    if primary_lang == "dart":
        lines = []
        for block in blocks:
            filename = _get_filename(block)
            lines.append(f"export '{filename}';")
        index_path = src_dir / "index.dart"
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return index_path

    return None
