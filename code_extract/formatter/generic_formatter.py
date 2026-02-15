"""Generic formatter for brace-delimited languages (Rust, Go, Java, C++, Swift, Kotlin, C#)."""

from __future__ import annotations

from code_extract.formatter.base import BaseFormatter


class GenericFormatter(BaseFormatter):
    """Handles all brace-delimited languages not covered by specific formatters."""

    def format_code(self, code: str) -> str:
        lines = [line.rstrip() for line in code.splitlines()]
        result: list[str] = []
        blank_count = 0
        for line in lines:
            if not line.strip():
                blank_count += 1
                if blank_count <= 1:
                    result.append(line)
            else:
                blank_count = 0
                result.append(line)
        return "\n".join(result).strip()

    def validate(self, code: str) -> tuple[bool, str | None]:
        depth = 0
        in_string = False
        string_char = ""
        in_line_comment = False
        in_block_comment = False
        i = 0
        while i < len(code):
            ch = code[i]
            next_ch = code[i + 1] if i + 1 < len(code) else ""

            if in_line_comment:
                if ch == "\n":
                    in_line_comment = False
            elif in_block_comment:
                if ch == "*" and next_ch == "/":
                    in_block_comment = False
                    i += 1
            elif in_string:
                if ch == "\\" and next_ch:
                    i += 1
                elif ch == string_char:
                    in_string = False
            else:
                if ch == "/" and next_ch == "/":
                    in_line_comment = True
                    i += 1
                elif ch == "/" and next_ch == "*":
                    in_block_comment = True
                    i += 1
                elif ch == "#" and next_ch != "!":
                    # Ruby/Python line comments — skip rest of line
                    in_line_comment = True
                elif ch in ("'", '"', "`"):
                    in_string = True
                    string_char = ch
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1

            i += 1

        if depth != 0:
            return False, f"Unbalanced braces (depth={depth})"
        return True, None
