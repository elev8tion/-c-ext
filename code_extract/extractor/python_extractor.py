"""Python extractor using AST."""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

from code_extract.models import CodeBlockType, ExtractedBlock, ScannedItem
from code_extract.extractor.base import BaseExtractor


class PythonExtractor(BaseExtractor):

    def extract(self, item: ScannedItem, *, source: str | None = None) -> ExtractedBlock:
        source = self._read_source(item.file_path, source)
        lines = source.splitlines(keepends=True)
        tree = ast.parse(source, filename=str(item.file_path))

        # Find the target node
        target_node = self._find_node(tree, item)
        if target_node is None:
            raise ValueError(f"Could not find {item.name} in {item.file_path}")

        # Extract the code lines
        start = target_node.lineno - 1
        end = target_node.end_lineno if target_node.end_lineno else start + 1

        # Include decorators
        decorators: list[str] = []
        if hasattr(target_node, "decorator_list") and target_node.decorator_list:
            first_dec = target_node.decorator_list[0]
            start = first_dec.lineno - 1
            for dec in target_node.decorator_list:
                decorators.append(ast.dump(dec))

        code = "".join(lines[start:end])

        # Collect file-level imports
        imports = self._collect_python_imports(tree, source)

        # Find type references in the extracted code
        type_refs = self._find_type_references(code)

        return ExtractedBlock(
            item=item,
            source_code=code,
            imports=imports,
            decorators=decorators,
            type_references=type_refs,
        )

    def _find_node(self, tree: ast.Module, item: ScannedItem) -> ast.AST | None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == item.name and node.lineno == item.line_number:
                    return node
                # Check for parent-qualified match
                if item.parent and node.name == item.name:
                    if hasattr(node, "lineno") and node.lineno == item.line_number:
                        return node
        # Fallback: match by name only
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == item.name:
                    return node
        return None

    def _collect_python_imports(self, tree: ast.Module, source: str) -> list[str]:
        lines = source.splitlines()
        imports: list[str] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                start = node.lineno - 1
                end = node.end_lineno if node.end_lineno else start + 1
                imports.append("\n".join(lines[start:end]))
        return imports

    def _find_type_references(self, code: str) -> list[str]:
        """Find type annotation references in extracted code."""
        refs: list[str] = []
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return refs

        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                if node.id[0].isupper() and node.id not in ("True", "False", "None"):
                    if node.id not in refs:
                        refs.append(node.id)
        return refs
