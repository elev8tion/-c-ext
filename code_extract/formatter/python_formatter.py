"""Python formatter — uses black if available, otherwise basic normalization."""

from __future__ import annotations

import ast
import re

from code_extract.formatter.base import BaseFormatter


class PythonFormatter(BaseFormatter):

    def __init__(self):
        self._has_black = False
        try:
            import black
            self._has_black = True
        except ImportError:
            pass

    def format_code(self, code: str) -> str:
        if self._has_black:
            return self._format_with_black(code)
        return self._basic_format(code)

    def validate(self, code: str) -> tuple[bool, str | None]:
        # Strip TODO/comment-only lines for validation
        code_lines = []
        for line in code.splitlines():
            stripped = line.strip()
            if stripped.startswith("# TODO:") or stripped.startswith("#"):
                continue
            code_lines.append(line)
        code_to_validate = "\n".join(code_lines)

        if not code_to_validate.strip():
            return True, None

        try:
            ast.parse(code_to_validate)
            return True, None
        except SyntaxError as e:
            return False, f"SyntaxError: {e.msg} (line {e.lineno})"

    def _format_with_black(self, code: str) -> str:
        try:
            import black
            mode = black.Mode(line_length=88)
            return black.format_str(code, mode=mode).rstrip()
        except Exception:
            return self._basic_format(code)

    def _basic_format(self, code: str) -> str:
        # Normalize trailing whitespace
        lines = [line.rstrip() for line in code.splitlines()]
        # Remove excessive blank lines (more than 2 consecutive)
        result: list[str] = []
        blank_count = 0
        for line in lines:
            if not line:
                blank_count += 1
                if blank_count <= 2:
                    result.append(line)
            else:
                blank_count = 0
                result.append(line)
        return "\n".join(result).strip()
