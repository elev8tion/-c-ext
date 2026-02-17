"""Tree-sitter-based extractor for all non-Python languages."""

from __future__ import annotations

from pathlib import Path

from code_extract.models import ExtractedBlock, ScannedItem
from code_extract.scanner.language_map import EXT_TO_LANGUAGE

try:
    from tree_sitter_language_pack import get_parser  # noqa: F401
except ImportError as _err:
    raise ImportError(
        "tree-sitter-language-pack is required. Install with: "
        "pip install 'code-extract[treesitter]'"
    ) from _err

# Node types that represent definitions
_DEFINITION_TYPES = {
    "function_declaration", "function_definition", "function_item",
    "method_declaration", "method_definition", "method_signature",
    "class_declaration", "class_definition", "class_specifier",
    "struct_item", "struct_specifier", "struct_declaration",
    "enum_item", "enum_declaration", "enum_specifier",
    "interface_declaration", "trait_item", "protocol_declaration",
    "impl_item", "mod_item", "module",
    "mixin_declaration",
    "lexical_declaration", "variable_declaration",
    "object_declaration",
    "type_declaration",
}


class TreeSitterExtractor:
    """Extracts code blocks using tree-sitter AST node boundaries."""

    def __init__(self):
        self._parser_cache: dict[str, object] = {}
        self._tree_cache: dict[str, tuple[str, bytes, object]] = {}  # path -> (source, bytes, tree)

    def extract(self, item: ScannedItem, *, source: str | None = None) -> ExtractedBlock:
        file_key = str(item.file_path)
        if file_key in self._tree_cache:
            source, source_bytes, cached_tree = self._tree_cache[file_key]
        else:
            if source is None:
                source = item.file_path.read_text(encoding="utf-8", errors="replace")
            source_bytes = source.encode("utf-8")
            cached_tree = None

        ext = item.file_path.suffix
        entry = EXT_TO_LANGUAGE.get(ext)
        if entry is None:
            return self._fallback_extract(item, source)

        _, grammar_name = entry
        if cached_tree is not None:
            tree = cached_tree
        else:
            parser = self._get_parser(grammar_name)
            tree = parser.parse(source_bytes)
            self._tree_cache[file_key] = (source, source_bytes, tree)

        # Find the node at the item's line
        target_line = item.line_number - 1  # tree-sitter is 0-indexed
        node = self._find_node_at_line(tree.root_node, target_line, item.name, source_bytes)

        if node is not None:
            # Walk up to the definition node (function_declaration, class_declaration, etc.)
            def_node = self._find_definition_ancestor(node)
            if def_node:
                code = source_bytes[def_node.start_byte:def_node.end_byte].decode("utf-8")
                # Include decorators/annotations above the node
                decorators = self._collect_decorators(def_node, source_bytes)
                if decorators:
                    code = decorators + "\n" + code
            else:
                code = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
                decorators = ""
        else:
            # Fallback: use brace matching from the line
            return self._fallback_extract(item, source)

        imports = self._collect_imports(tree.root_node, source_bytes)
        type_refs = self._collect_type_refs(code)

        return ExtractedBlock(
            item=item,
            source_code=code,
            imports=imports,
            decorators=decorators.splitlines() if isinstance(decorators, str) and decorators else [],
            type_references=type_refs,
        )

    def clear_cache(self):
        """Clear tree cache between scans to free memory."""
        self._tree_cache.clear()

    def _get_parser(self, grammar_name: str):
        if grammar_name not in self._parser_cache:
            self._parser_cache[grammar_name] = get_parser(grammar_name)
        return self._parser_cache[grammar_name]

    def _find_node_at_line(self, root, target_line: int, name: str, source_bytes: bytes):
        """Find a named node at or near the target line."""
        best = None
        best_dist = float("inf")

        def _walk(node):
            nonlocal best, best_dist
            node_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            # Check if this node's text matches the name and it's near the target line
            if node.type in ("identifier", "type_identifier", "property_identifier",
                             "simple_identifier", "constant", "field_identifier"):
                if node.text and node.text.decode("utf-8") == name:
                    dist = abs(node.start_point[0] - target_line)
                    if dist < best_dist:
                        best_dist = dist
                        best = node

            for child in node.children:
                _walk(child)

        _walk(root)
        return best

    def _find_definition_ancestor(self, node):
        """Walk up tree to find the enclosing definition node."""
        current = node.parent
        while current:
            if current.type in _DEFINITION_TYPES:
                return current
            current = current.parent
        return node.parent

    def _collect_decorators(self, def_node, source_bytes: bytes) -> str:
        """Collect decorators/annotations above a definition node."""
        parts = []
        # Check previous siblings for decorator/annotation nodes
        prev = def_node.prev_named_sibling
        while prev:
            if prev.type in ("decorator", "annotation", "attribute_item", "attribute"):
                text = source_bytes[prev.start_byte:prev.end_byte].decode("utf-8")
                parts.insert(0, text)
                prev = prev.prev_named_sibling
            else:
                break
        return "\n".join(parts)

    def _collect_imports(self, root, source_bytes: bytes) -> list[str]:
        """Collect import statements from the top of the file."""
        imports = []
        for child in root.children:
            if child.type in (
                "import_declaration", "import_statement", "import_from_statement",
                "use_declaration", "use_item", "package_clause",
                "import_directive", "library_directive",
                "using_directive", "include_directive",
                "require_call",
            ):
                text = source_bytes[child.start_byte:child.end_byte].decode("utf-8").strip()
                imports.append(text)
            # Also catch JS/TS import via expression_statement wrapping
            elif child.type == "expression_statement":
                text = source_bytes[child.start_byte:child.end_byte].decode("utf-8").strip()
                if text.startswith("import ") or text.startswith("require("):
                    imports.append(text)
        return imports

    def _collect_type_refs(self, code: str) -> list[str]:
        """Find uppercase identifiers that look like type references."""
        import re
        refs = set()
        for m in re.finditer(r"\b([A-Z][a-zA-Z0-9]+)\b", code):
            refs.add(m.group(1))
        return sorted(refs)

    def _fallback_extract(self, item: ScannedItem, source: str) -> ExtractedBlock:
        """Fallback: extract using brace matching from the line number."""
        lines = source.splitlines()
        start_idx = max(0, item.line_number - 1)

        # Collect imports from top
        imports = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("//") or stripped.startswith("#"):
                continue
            if any(stripped.startswith(kw) for kw in ("import ", "from ", "use ", "require(", "#include", "using ")):
                imports.append(line)
            elif imports:
                break

        # Simple brace matching
        text = "\n".join(lines[start_idx:])
        depth = 0
        found_brace = False
        end_offset = len(text)
        for i, ch in enumerate(text):
            if ch == "{":
                depth += 1
                found_brace = True
            elif ch == "}":
                depth -= 1
                if depth == 0 and found_brace:
                    end_offset = i + 1
                    break

        code = text[:end_offset]

        return ExtractedBlock(
            item=item,
            source_code=code,
            imports=imports,
        )
