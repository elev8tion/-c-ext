"""Python scanner using the ast module."""

from __future__ import annotations

import ast
from pathlib import Path

from code_extract.models import CodeBlockType, Language, ScannedItem
from code_extract.scanner.base import BaseScanner


class PythonScanner(BaseScanner):
    language = Language.PYTHON
    extensions = (".py",)

    def scan_file(self, file_path: Path) -> list[ScannedItem]:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(file_path))
        items: list[ScannedItem] = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                items.append(ScannedItem(
                    name=node.name,
                    block_type=CodeBlockType.CLASS,
                    language=self.language,
                    file_path=file_path,
                    line_number=node.lineno,
                    end_line=node.end_lineno,
                ))
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        items.append(ScannedItem(
                            name=child.name,
                            block_type=CodeBlockType.METHOD,
                            language=self.language,
                            file_path=file_path,
                            line_number=child.lineno,
                            end_line=child.end_lineno,
                            parent=node.name,
                        ))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                items.append(ScannedItem(
                    name=node.name,
                    block_type=CodeBlockType.FUNCTION,
                    language=self.language,
                    file_path=file_path,
                    line_number=node.lineno,
                    end_line=node.end_lineno,
                ))

        return items
