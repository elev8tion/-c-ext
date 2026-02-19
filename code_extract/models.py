"""Data models for the code-extract pipeline."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path


class Language(enum.Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    DART = "dart"
    RUST = "rust"
    GO = "go"
    JAVA = "java"
    CPP = "cpp"
    RUBY = "ruby"
    SWIFT = "swift"
    KOTLIN = "kotlin"
    CSHARP = "csharp"
    SQL = "sql"
    HTML = "html"


class CodeBlockType(enum.Enum):
    FUNCTION = "function"
    CLASS = "class"
    COMPONENT = "component"
    WIDGET = "widget"
    MIXIN = "mixin"
    PROVIDER = "provider"
    METHOD = "method"
    STRUCT = "struct"
    TRAIT = "trait"
    INTERFACE = "interface"
    ENUM = "enum"
    MODULE = "module"
    TABLE = "table"
    VIEW = "view"
    FUNCTION_SQL = "sql_function"
    TRIGGER = "trigger"
    INDEX = "index"
    MIGRATION = "migration"
    POLICY = "policy"
    SCRIPT_BLOCK = "script_block"
    STYLE_BLOCK = "style_block"


@dataclass
class ScannedItem:
    """Result from the scanner stage."""
    name: str
    block_type: CodeBlockType
    language: Language
    file_path: Path
    line_number: int
    end_line: int | None = None
    parent: str | None = None  # e.g. class name for methods

    @property
    def qualified_name(self) -> str:
        if self.parent:
            return f"{self.parent}.{self.name}"
        return self.name


@dataclass
class ExtractedBlock:
    """Result from the extractor stage."""
    item: ScannedItem
    source_code: str
    imports: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    type_references: list[str] = field(default_factory=list)


@dataclass
class CleanedBlock:
    """Result from the cleaner stage."""
    item: ScannedItem
    source_code: str
    required_imports: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class FormattedBlock:
    """Result from the formatter stage."""
    item: ScannedItem
    source_code: str
    header: str = ""
    is_valid: bool = True
    validation_error: str | None = None


@dataclass
class ExportResult:
    """Result from the exporter stage."""
    output_dir: Path
    files_created: list[Path] = field(default_factory=list)
    manifest_path: Path | None = None
    readme_path: Path | None = None


@dataclass
class PipelineConfig:
    """Configuration for the extraction pipeline."""
    source_dir: Path = field(default_factory=lambda: Path("."))
    output_dir: Path = field(default_factory=lambda: Path("extracted"))
    target: str | None = None
    pattern: str | None = None
    extract_all: bool = False
    include_tests: bool = False
    skip_dirs: list[str] = field(default_factory=lambda: [
        "node_modules", ".git", "__pycache__", ".dart_tool",
        "build", "dist", ".next", ".venv", "venv", "env",
        ".eggs", "*.egg-info",
    ])
