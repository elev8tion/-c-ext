"""Shared extension-to-language mapping for scanner and extractor."""

from __future__ import annotations

from code_extract.models import Language

# Maps file extension -> (Language enum, tree-sitter grammar name)
EXT_TO_LANGUAGE: dict[str, tuple[Language, str]] = {
    ".js": (Language.JAVASCRIPT, "javascript"),
    ".jsx": (Language.JAVASCRIPT, "javascript"),
    ".mjs": (Language.JAVASCRIPT, "javascript"),
    ".ts": (Language.TYPESCRIPT, "typescript"),
    ".tsx": (Language.TYPESCRIPT, "tsx"),
    ".dart": (Language.DART, "dart"),
    ".py": (Language.PYTHON, "python"),
    ".rs": (Language.RUST, "rust"),
    ".go": (Language.GO, "go"),
    ".java": (Language.JAVA, "java"),
    ".cpp": (Language.CPP, "cpp"),
    ".cc": (Language.CPP, "cpp"),
    ".cxx": (Language.CPP, "cpp"),
    ".h": (Language.CPP, "cpp"),
    ".hpp": (Language.CPP, "cpp"),
    ".rb": (Language.RUBY, "ruby"),
    ".swift": (Language.SWIFT, "swift"),
    ".kt": (Language.KOTLIN, "kotlin"),
    ".kts": (Language.KOTLIN, "kotlin"),
    ".cs": (Language.CSHARP, "csharp"),
    ".sql": (Language.SQL, "sql"),
}

# Extensions handled by tree-sitter (excludes Python which uses stdlib ast)
TREESITTER_EXTENSIONS: set[str] = {
    ext for ext, (lang, _) in EXT_TO_LANGUAGE.items()
    if lang != Language.PYTHON and lang != Language.SQL
}
