"""SQL extractor — extracts full SQL statements from .sql files."""

from __future__ import annotations

import re
from pathlib import Path

from code_extract.models import ExtractedBlock, ScannedItem


class SqlExtractor:
    """Extracts SQL statements including multi-line bodies and $$ blocks."""

    def extract(self, item: ScannedItem, *, source: str | None = None) -> ExtractedBlock:
        if source is None:
            source = item.file_path.read_text(encoding="utf-8", errors="replace")
        lines = source.splitlines()
        start_idx = max(0, item.line_number - 1)

        code = self._extract_statement(lines, start_idx)

        return ExtractedBlock(
            item=item,
            source_code=code,
            imports=[],
            decorators=[],
            type_references=[],
        )

    def _extract_statement(self, lines: list[str], start_idx: int) -> str:
        """Extract a full SQL statement from start line to terminating semicolon.

        Handles:
        - Multi-line CREATE TABLE (...);
        - PostgreSQL $$ delimited function bodies
        - BEGIN...END blocks
        """
        result_lines: list[str] = []
        in_dollar_body = False
        paren_depth = 0
        i = start_idx

        while i < len(lines):
            line = lines[i]
            result_lines.append(line)

            if in_dollar_body:
                # Look for closing $$
                if "$$" in line and len(result_lines) > 1:
                    # Check if this line has the closing $$
                    text_so_far = "\n".join(result_lines)
                    # Count $$ occurrences — should be even when complete
                    count = text_so_far.count("$$")
                    if count >= 2 and count % 2 == 0:
                        in_dollar_body = False
                        # Still need the final semicolon
                        stripped = line.rstrip()
                        if stripped.endswith(";"):
                            break
            else:
                # Check for $$ to enter dollar-quoted body
                if "$$" in line:
                    in_dollar_body = True
                    i += 1
                    continue

                # Track parentheses for CREATE TABLE (...) etc.
                for ch in line:
                    if ch == "(":
                        paren_depth += 1
                    elif ch == ")":
                        paren_depth -= 1

                # Check for statement end: semicolon outside parens and $$ blocks
                stripped = line.rstrip()
                if stripped.endswith(";") and paren_depth <= 0:
                    break

            i += 1

        return "\n".join(result_lines)
