"""Abstract base formatter with header generation."""

from __future__ import annotations

import abc
from datetime import datetime

from code_extract.models import CleanedBlock, FormattedBlock


class BaseFormatter(abc.ABC):
    """Base class for language-specific formatters."""

    @abc.abstractmethod
    def format_code(self, code: str) -> str:
        """Format source code."""

    @abc.abstractmethod
    def validate(self, code: str) -> tuple[bool, str | None]:
        """Validate that code is syntactically correct. Returns (is_valid, error)."""

    def format_block(self, block: CleanedBlock) -> FormattedBlock:
        """Format a cleaned block into a final output block."""
        header = self._generate_header(block)

        # Combine imports and code
        parts: list[str] = []
        if block.required_imports:
            parts.append("\n".join(block.required_imports))
            parts.append("")  # blank separator

        formatted_code = self.format_code(block.source_code)
        parts.append(formatted_code)

        full_code = "\n".join(parts)

        is_valid, error = self.validate(full_code)

        return FormattedBlock(
            item=block.item,
            source_code=full_code,
            header=header,
            is_valid=is_valid,
            validation_error=error,
        )

    def _generate_header(self, block: CleanedBlock) -> str:
        item = block.item
        lines = [
            f"Extracted: {item.qualified_name}",
            f"Type: {item.block_type.value}",
            f"Source: {item.file_path}:{item.line_number}",
            f"Date: {datetime.now().strftime('%Y-%m-%d')}",
        ]
        if block.warnings:
            lines.append(f"Warnings: {'; '.join(block.warnings)}")
        return "\n".join(lines)
