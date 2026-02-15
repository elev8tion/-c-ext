"""SQL formatter — basic keyword uppercasing and indentation normalization."""

from __future__ import annotations

import re

from code_extract.formatter.base import BaseFormatter

_SQL_KEYWORDS = {
    "select", "from", "where", "insert", "into", "values", "update", "set",
    "delete", "create", "table", "view", "function", "trigger", "index",
    "alter", "drop", "primary", "key", "foreign", "references", "not",
    "null", "default", "unique", "check", "constraint", "on", "or",
    "replace", "if", "exists", "begin", "end", "return", "returns",
    "declare", "as", "and", "in", "is", "with", "cascade", "restrict",
    "grant", "revoke", "policy", "using", "for", "each", "row",
    "before", "after", "execute", "procedure", "language", "plpgsql",
    "volatile", "stable", "immutable", "security", "definer", "invoker",
    "materialized", "temporary", "temp", "type", "enum",
}

_KEYWORD_RE = re.compile(
    r"\b(" + "|".join(re.escape(kw) for kw in _SQL_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


class SqlFormatter(BaseFormatter):

    def format_code(self, code: str) -> str:
        lines = code.splitlines()
        result: list[str] = []
        in_dollar = False

        for line in lines:
            stripped = line.rstrip()
            if not stripped:
                if result and result[-1].strip():
                    result.append("")
                continue

            if "$$" in stripped:
                in_dollar = not in_dollar

            if not in_dollar:
                # Uppercase SQL keywords (outside $$ blocks)
                stripped = _KEYWORD_RE.sub(lambda m: m.group(0).upper(), stripped)

            result.append(stripped)

        return "\n".join(result).strip()

    def validate(self, code: str) -> tuple[bool, str | None]:
        # Basic validation: check matching parens
        depth = 0
        in_string = False
        string_char = ""
        in_dollar = False
        i = 0

        while i < len(code):
            ch = code[i]

            # Handle $$ delimiters
            if ch == "$" and i + 1 < len(code) and code[i + 1] == "$":
                in_dollar = not in_dollar
                i += 2
                continue

            if in_dollar:
                i += 1
                continue

            # Handle strings
            if in_string:
                if ch == string_char:
                    # Check for escaped quote
                    if i + 1 < len(code) and code[i + 1] == string_char:
                        i += 2
                        continue
                    in_string = False
            elif ch == "'":
                in_string = True
                string_char = "'"
            elif ch == "--":
                # Skip to end of line
                while i < len(code) and code[i] != "\n":
                    i += 1
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1

            i += 1

        if depth != 0:
            return False, f"Unbalanced parentheses (depth={depth})"
        return True, None
