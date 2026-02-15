"""Universal tree-sitter scanner for all non-Python languages."""

from __future__ import annotations

import fnmatch
from pathlib import Path

from code_extract.models import CodeBlockType, Language, ScannedItem
from code_extract.scanner.language_map import EXT_TO_LANGUAGE, TREESITTER_EXTENSIONS

try:
    from tree_sitter_language_pack import get_parser
except ImportError as _err:
    raise ImportError(
        "tree-sitter-language-pack is required. Install with: "
        "pip install 'code-extract[treesitter]'"
    ) from _err

_WIDGET_BASES = {
    "StatelessWidget", "StatefulWidget", "State",
    "HookWidget", "ConsumerWidget",
}

# Node type → CodeBlockType mapping per grammar
_NODE_TYPE_MAP: dict[str, dict[str, CodeBlockType]] = {
    "javascript": {
        "class_declaration": CodeBlockType.CLASS,
        "function_declaration": CodeBlockType.FUNCTION,
        "method_definition": CodeBlockType.METHOD,
    },
    "typescript": {
        "class_declaration": CodeBlockType.CLASS,
        "function_declaration": CodeBlockType.FUNCTION,
        "method_definition": CodeBlockType.METHOD,
        "interface_declaration": CodeBlockType.INTERFACE,
        "enum_declaration": CodeBlockType.ENUM,
    },
    "tsx": {
        "class_declaration": CodeBlockType.CLASS,
        "function_declaration": CodeBlockType.FUNCTION,
        "method_definition": CodeBlockType.METHOD,
        "interface_declaration": CodeBlockType.INTERFACE,
        "enum_declaration": CodeBlockType.ENUM,
    },
    "dart": {
        "class_definition": CodeBlockType.CLASS,
        "mixin_declaration": CodeBlockType.MIXIN,
        "enum_declaration": CodeBlockType.ENUM,
    },
    "rust": {
        "struct_item": CodeBlockType.STRUCT,
        "enum_item": CodeBlockType.ENUM,
        "function_item": CodeBlockType.FUNCTION,
        "trait_item": CodeBlockType.TRAIT,
        "mod_item": CodeBlockType.MODULE,
    },
    "go": {
        "function_declaration": CodeBlockType.FUNCTION,
        "method_declaration": CodeBlockType.METHOD,
    },
    "java": {
        "class_declaration": CodeBlockType.CLASS,
        "interface_declaration": CodeBlockType.INTERFACE,
        "enum_declaration": CodeBlockType.ENUM,
        "method_declaration": CodeBlockType.METHOD,
    },
    "cpp": {
        "class_specifier": CodeBlockType.CLASS,
        "struct_specifier": CodeBlockType.STRUCT,
        "function_definition": CodeBlockType.FUNCTION,
        "enum_specifier": CodeBlockType.ENUM,
    },
    "ruby": {
        "class": CodeBlockType.CLASS,
        "module": CodeBlockType.MODULE,
        "method": CodeBlockType.FUNCTION,
        "singleton_method": CodeBlockType.FUNCTION,
    },
    "swift": {
        "class_declaration": None,  # Handled specially (class/struct/enum)
        "protocol_declaration": CodeBlockType.INTERFACE,
        "function_declaration": CodeBlockType.FUNCTION,
    },
    "kotlin": {
        "class_declaration": None,  # Could be class or interface
        "object_declaration": CodeBlockType.CLASS,
        "function_declaration": CodeBlockType.FUNCTION,
    },
    "csharp": {
        "class_declaration": CodeBlockType.CLASS,
        "struct_declaration": CodeBlockType.STRUCT,
        "interface_declaration": CodeBlockType.INTERFACE,
        "enum_declaration": CodeBlockType.ENUM,
        "method_declaration": CodeBlockType.METHOD,
    },
}

# Name node types per node type
_NAME_TYPES = {"identifier", "type_identifier", "property_identifier",
               "simple_identifier", "constant", "field_identifier",
               "package_identifier"}


class TreeSitterScanner:
    """Scans files using tree-sitter AST walking for all supported languages."""

    def __init__(self, skip_dirs: list[str] | None = None):
        self.skip_dirs = skip_dirs or [
            "node_modules", ".git", "__pycache__", ".dart_tool",
            "build", "dist", ".next", ".venv", "venv", "env",
        ]
        self._parser_cache: dict[str, object] = {}

    @property
    def extensions(self) -> set[str]:
        return TREESITTER_EXTENSIONS

    def scan_directory(self, directory: Path) -> list[ScannedItem]:
        items: list[ScannedItem] = []
        for path in sorted(directory.rglob("*")):
            if path.is_dir():
                continue
            if self._should_skip(path):
                continue
            if path.suffix in self.extensions:
                try:
                    items.extend(self.scan_file(path))
                except Exception:
                    continue
        items.sort(key=lambda i: (str(i.file_path), i.line_number))
        return items

    def scan_file(self, file_path: Path) -> list[ScannedItem]:
        ext = file_path.suffix
        if ext not in EXT_TO_LANGUAGE:
            return []

        language, grammar_name = EXT_TO_LANGUAGE[ext]
        if grammar_name not in _NODE_TYPE_MAP:
            return []

        source_bytes = file_path.read_bytes()
        parser = self._get_parser(grammar_name)
        tree = parser.parse(source_bytes)

        node_map = _NODE_TYPE_MAP[grammar_name]
        items: list[ScannedItem] = []
        seen: set[tuple[str, int]] = set()

        self._walk_tree(
            tree.root_node, source_bytes, language, grammar_name,
            node_map, file_path, items, seen,
        )

        # JS/TS: also detect arrow function components
        if grammar_name in ("javascript", "typescript", "tsx"):
            self._detect_arrow_functions(
                tree.root_node, source_bytes, language, file_path, items, seen,
            )

        # Go: detect struct/interface via type_declaration
        if grammar_name == "go":
            self._detect_go_types(
                tree.root_node, source_bytes, language, file_path, items, seen,
            )

        items.sort(key=lambda i: i.line_number)
        return items

    def _walk_tree(
        self, node, source_bytes: bytes, language: Language,
        grammar_name: str, node_map: dict, file_path: Path,
        items: list[ScannedItem], seen: set,
    ):
        """Walk the tree and collect items based on node types."""
        if node.type in node_map:
            block_type = node_map[node.type]
            name = self._get_name(node)
            if name:
                line_no = node.start_point[0] + 1
                end_line = node.end_point[0] + 1

                if (name, line_no) in seen:
                    pass
                else:
                    seen.add((name, line_no))

                    # Special handling per grammar
                    actual_type = block_type
                    parent = None

                    if block_type is None:
                        actual_type = self._resolve_special_type(
                            node, grammar_name, source_bytes,
                        )

                    if actual_type == CodeBlockType.METHOD:
                        parent = self._find_enclosing_class_name(node)

                    # Dart: widget detection
                    if language == Language.DART and actual_type == CodeBlockType.CLASS:
                        if self._is_dart_widget(node, source_bytes):
                            actual_type = CodeBlockType.WIDGET

                    # JS/TS: component detection for function declarations
                    if (language in (Language.JAVASCRIPT, Language.TYPESCRIPT)
                            and actual_type == CodeBlockType.FUNCTION
                            and name[0:1].isupper()):
                        text = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
                        if "<" in text and ("return" in text or "=>" in text):
                            actual_type = CodeBlockType.COMPONENT

                    if actual_type is not None:
                        items.append(ScannedItem(
                            name=name,
                            block_type=actual_type,
                            language=language,
                            file_path=file_path,
                            line_number=line_no,
                            end_line=end_line,
                            parent=parent,
                        ))

        # Recurse into children
        for child in node.children:
            self._walk_tree(
                child, source_bytes, language, grammar_name,
                node_map, file_path, items, seen,
            )

    def _get_name(self, node) -> str | None:
        """Extract the name from a definition node."""
        # Try 'name' field first
        name_node = node.child_by_field_name("name")
        if name_node and name_node.text:
            return name_node.text.decode("utf-8")

        # Fall back: first child that's a name-like type
        for child in node.children:
            if child.type in _NAME_TYPES and child.text:
                return child.text.decode("utf-8")

        return None

    def _resolve_special_type(
        self, node, grammar_name: str, source_bytes: bytes,
    ) -> CodeBlockType | None:
        """Resolve type for nodes that need special handling."""
        if grammar_name == "swift":
            # Swift: class_declaration is used for class, struct, and enum
            kind_node = node.child_by_field_name("declaration_kind")
            if kind_node:
                kind = kind_node.type
                if kind == "class":
                    return CodeBlockType.CLASS
                elif kind == "struct":
                    return CodeBlockType.STRUCT
                elif kind == "enum":
                    return CodeBlockType.ENUM
            # Fallback: check first child text
            for child in node.children:
                if child.type in ("class", "struct", "enum"):
                    return {"class": CodeBlockType.CLASS, "struct": CodeBlockType.STRUCT,
                            "enum": CodeBlockType.ENUM}.get(child.type)
            return CodeBlockType.CLASS

        if grammar_name == "kotlin":
            # Kotlin: class_declaration can be class or interface
            for child in node.children:
                if child.type == "interface":
                    return CodeBlockType.INTERFACE
                if child.type == "class":
                    return CodeBlockType.CLASS
            return CodeBlockType.CLASS

        return CodeBlockType.CLASS

    def _detect_arrow_functions(
        self, root, source_bytes: bytes, language: Language,
        file_path: Path, items: list[ScannedItem], seen: set,
    ):
        """Detect JS/TS const arrow functions."""
        for child in root.children:
            if child.type == "lexical_declaration":
                for decl in child.children:
                    if decl.type == "variable_declarator":
                        name_node = decl.child_by_field_name("name")
                        value_node = decl.child_by_field_name("value")
                        if (name_node and value_node
                                and value_node.type == "arrow_function"
                                and name_node.text):
                            name = name_node.text.decode("utf-8")
                            line_no = child.start_point[0] + 1
                            end_line = child.end_point[0] + 1
                            if (name, line_no) in seen:
                                continue
                            seen.add((name, line_no))

                            # Component if uppercase and has JSX
                            block_type = CodeBlockType.FUNCTION
                            if name[0:1].isupper():
                                text = source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                                if "<" in text:
                                    block_type = CodeBlockType.COMPONENT

                            items.append(ScannedItem(
                                name=name,
                                block_type=block_type,
                                language=language,
                                file_path=file_path,
                                line_number=line_no,
                                end_line=end_line,
                            ))

    def _detect_go_types(
        self, root, source_bytes: bytes, language: Language,
        file_path: Path, items: list[ScannedItem], seen: set,
    ):
        """Detect Go struct/interface types from type_declaration nodes."""
        for child in root.children:
            if child.type == "type_declaration":
                for spec in child.children:
                    if spec.type == "type_spec":
                        name_node = None
                        type_node = None
                        for sc in spec.children:
                            if sc.type == "type_identifier":
                                name_node = sc
                            elif sc.type in ("struct_type", "interface_type"):
                                type_node = sc
                        if name_node and type_node and name_node.text:
                            name = name_node.text.decode("utf-8")
                            line_no = child.start_point[0] + 1
                            end_line = child.end_point[0] + 1
                            if (name, line_no) in seen:
                                continue
                            seen.add((name, line_no))

                            bt = (CodeBlockType.STRUCT if type_node.type == "struct_type"
                                  else CodeBlockType.INTERFACE)
                            items.append(ScannedItem(
                                name=name,
                                block_type=bt,
                                language=language,
                                file_path=file_path,
                                line_number=line_no,
                                end_line=end_line,
                            ))

    def _find_enclosing_class_name(self, node) -> str | None:
        """Walk up the tree to find an enclosing class name."""
        current = node.parent
        while current:
            if current.type in (
                "class_declaration", "class_definition", "class_specifier",
                "struct_item", "impl_item", "struct_declaration",
                "struct_specifier", "object_declaration",
            ):
                name = self._get_name(current)
                if name:
                    return name
            current = current.parent
        return None

    def _is_dart_widget(self, node, source_bytes: bytes) -> bool:
        """Check if a Dart class extends a widget base class."""
        sc_node = node.child_by_field_name("superclass")
        if sc_node:
            text = source_bytes[sc_node.start_byte:sc_node.end_byte].decode("utf-8")
            return any(base in text for base in _WIDGET_BASES)
        # Fallback: check text near start
        end = min(node.start_byte + 300, node.end_byte)
        text = source_bytes[node.start_byte:end].decode("utf-8")
        return any(f"extends {base}" in text for base in _WIDGET_BASES)

    def _get_parser(self, grammar_name: str):
        if grammar_name not in self._parser_cache:
            self._parser_cache[grammar_name] = get_parser(grammar_name)
        return self._parser_cache[grammar_name]

    def _should_skip(self, path: Path) -> bool:
        for part in path.parts:
            for pattern in self.skip_dirs:
                if fnmatch.fnmatch(part, pattern):
                    return True
        return False
