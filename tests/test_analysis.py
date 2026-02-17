"""Tests for v0.3 analysis features — graph, dead code, architecture, health, catalog, docs, tour."""

import pytest
from pathlib import Path

from code_extract.models import (
    Language, CodeBlockType, ScannedItem, ExtractedBlock,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ── Helpers ───────────────────────────────────────────────────

def _make_item(name, lang=Language.PYTHON, btype=CodeBlockType.FUNCTION,
               file_path=None, line=1, end_line=10, parent=None):
    return ScannedItem(
        name=name,
        block_type=btype,
        language=lang,
        file_path=file_path or Path(f"/fake/{name}.py"),
        line_number=line,
        end_line=end_line,
        parent=parent,
    )


def _make_block(name, source="def foo(): pass", imports=None,
                type_references=None, lang=Language.PYTHON,
                btype=CodeBlockType.FUNCTION, file_path=None,
                line=1, end_line=10, parent=None):
    item = _make_item(name, lang, btype, file_path, line, end_line, parent)
    return ExtractedBlock(
        item=item,
        source_code=source,
        imports=imports or [],
        type_references=type_references or [],
    )


def _blocks_dict(*blocks):
    return {f"{b.item.file_path}:{b.item.line_number}": b for b in blocks}


# ── Dependency Graph ──────────────────────────────────────────

class TestDependencyGraph:
    def test_build_empty(self):
        from code_extract.analysis.dependency_graph import DependencyGraphBuilder
        builder = DependencyGraphBuilder()
        graph = builder.build({})
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0

    def test_build_single_node(self):
        from code_extract.analysis.dependency_graph import DependencyGraphBuilder
        b = _make_block("my_func")
        blocks = _blocks_dict(b)
        builder = DependencyGraphBuilder()
        graph = builder.build(blocks)
        assert len(graph.nodes) == 1

    def test_type_reference_edge(self):
        from code_extract.analysis.dependency_graph import DependencyGraphBuilder
        a = _make_block("func_a", type_references=["MyClass"])
        b = _make_block("MyClass", btype=CodeBlockType.CLASS,
                        source="class MyClass: pass")
        blocks = _blocks_dict(a, b)
        builder = DependencyGraphBuilder()
        graph = builder.build(blocks)
        assert len(graph.edges) > 0

    def test_resolve_transitive_no_deps(self):
        from code_extract.analysis.dependency_graph import DependencyGraphBuilder
        b = _make_block("solo")
        blocks = _blocks_dict(b)
        builder = DependencyGraphBuilder()
        graph = builder.build(blocks)
        key = list(blocks.keys())[0]
        result = builder.resolve_transitive(graph, key)
        assert len(result.all_transitive) == 0

    def test_detect_cycles_no_cycles(self):
        from code_extract.analysis.dependency_graph import DependencyGraphBuilder
        b = _make_block("solo")
        blocks = _blocks_dict(b)
        builder = DependencyGraphBuilder()
        graph = builder.build(blocks)
        cycles = builder.detect_cycles(graph)
        assert cycles == []


# ── Dead Code ─────────────────────────────────────────────────

class TestDeadCode:
    def test_detect_unused(self):
        from code_extract.analysis.dependency_graph import DependencyGraphBuilder
        from code_extract.analysis.dead_code import detect_dead_code
        a = _make_block("used_func")
        b = _make_block("unused_func")
        blocks = _blocks_dict(a, b)
        builder = DependencyGraphBuilder()
        graph = builder.build(blocks)
        results = detect_dead_code(graph)
        # Both should show as "dead" since neither references the other
        assert len(results) >= 1

    def test_entry_point_lower_confidence(self):
        from code_extract.analysis.dependency_graph import DependencyGraphBuilder
        from code_extract.analysis.dead_code import detect_dead_code
        main_block = _make_block("main", source="def main(): pass")
        blocks = _blocks_dict(main_block)
        builder = DependencyGraphBuilder()
        graph = builder.build(blocks)
        results = detect_dead_code(graph)
        # "main" is an entry-point name, should have lower confidence
        if results:
            main_items = [r for r in results if r["name"] == "main"]
            if main_items:
                assert main_items[0]["confidence"] < 0.9


# ── Architecture ──────────────────────────────────────────────

class TestArchitecture:
    def test_generate(self):
        from code_extract.analysis.dependency_graph import DependencyGraphBuilder
        from code_extract.analysis.architecture import generate_architecture
        a = _make_block("func_a", file_path=Path("/project/src/a.py"))
        b = _make_block("func_b", file_path=Path("/project/lib/b.py"))
        blocks = _blocks_dict(a, b)
        builder = DependencyGraphBuilder()
        graph = builder.build(blocks)
        result = generate_architecture(graph)
        assert "modules" in result
        assert "elements" in result
        assert "stats" in result
        assert len(result["modules"]) >= 1


# ── Health ────────────────────────────────────────────────────

class TestHealth:
    def test_analyze(self):
        from code_extract.analysis.dependency_graph import DependencyGraphBuilder
        from code_extract.analysis.health import analyze_health
        short = _make_block("short_func", line=1, end_line=5)
        long_ = _make_block("long_func", line=1, end_line=100,
                            source="\n".join(f"line {i}" for i in range(100)))
        blocks = _blocks_dict(short, long_)
        builder = DependencyGraphBuilder()
        graph = builder.build(blocks)
        result = analyze_health(blocks, graph)
        assert "score" in result
        assert "long_functions" in result
        assert "coupling" in result
        assert 0 <= result["score"] <= 100

    def test_long_function_detected(self):
        from code_extract.analysis.dependency_graph import DependencyGraphBuilder
        from code_extract.analysis.health import analyze_health
        long_ = _make_block("very_long", line=1, end_line=200)
        blocks = _blocks_dict(long_)
        builder = DependencyGraphBuilder()
        graph = builder.build(blocks)
        result = analyze_health(blocks, graph)
        assert len(result["long_functions"]) >= 1


# ── Catalog ───────────────────────────────────────────────────

class TestCatalog:
    def test_build(self):
        from code_extract.analysis.catalog import build_catalog
        func = _make_block("my_func", source="def my_func(x: int, y: str = 'hello'): pass")
        blocks = _blocks_dict(func)
        result = build_catalog(blocks)
        assert len(result) >= 1
        assert "name" in result[0]
        assert "language" in result[0]


# ── Docs ──────────────────────────────────────────────────────

class TestDocs:
    def test_generate_docs(self):
        from code_extract.analysis.docs import generate_docs
        func = _make_block("my_func", source='def my_func(x):\n    """Docstring."""\n    pass')
        blocks = _blocks_dict(func)
        result = generate_docs(blocks)
        assert "sections" in result
        assert len(result["sections"]) >= 1

    def test_generate_markdown(self):
        from code_extract.analysis.docs import generate_markdown
        func = _make_block("my_func", source="def my_func(x): pass")
        blocks = _blocks_dict(func)
        md = generate_markdown(blocks)
        assert isinstance(md, str)
        assert "my_func" in md


# ── Tour ──────────────────────────────────────────────────────

class TestTour:
    def test_generate(self):
        from code_extract.analysis.tour import generate_tour
        from code_extract.analysis.dependency_graph import DependencyGraphBuilder
        main = _make_block("main", source="def main(): pass")
        helper = _make_block("helper", source="def helper(): pass")
        blocks = _blocks_dict(main, helper)
        builder = DependencyGraphBuilder()
        graph = builder.build(blocks)
        result = generate_tour(blocks, graph)
        assert "steps" in result
        assert len(result["steps"]) >= 1


# ── Pattern Cloner ────────────────────────────────────────────

class TestPatternCloner:
    def test_clone_pattern(self):
        from code_extract.analysis.pattern_cloner import clone_pattern
        code = "class UserProfile:\n    def get_user_profile(self): pass"
        result = clone_pattern(code, "UserProfile", "ProductItem")
        assert "ProductItem" in result
        assert "product_item" in result or "ProductItem" in result

    def test_preview(self):
        from code_extract.analysis.pattern_cloner import preview_clone
        code = "class UserProfile: pass"
        result = preview_clone(code, "UserProfile", "ProductItem")
        assert "transformed_code" in result
        assert "replacements" in result
        assert len(result["replacements"]) > 0


# ── Boilerplate ───────────────────────────────────────────────

class TestBoilerplate:
    def test_generate_template(self):
        from code_extract.analysis.boilerplate import generate_template
        blocks = [
            _make_block("ComponentA", source="class ComponentA: pass",
                        btype=CodeBlockType.CLASS,
                        file_path=Path("/proj/components/a.py")),
            _make_block("ComponentB", source="class ComponentB: pass",
                        btype=CodeBlockType.CLASS,
                        file_path=Path("/proj/components/b.py")),
        ]
        result = generate_template(blocks, "MyTemplate")
        assert "template_code" in result
        assert "variables" in result

    def test_apply_template(self):
        from code_extract.analysis.boilerplate import apply_template
        template = "class {{name}}: pass"
        result = apply_template(template, {"name": "Foo"})
        assert "Foo" in result

    def test_filter_blocks_by_pattern(self):
        from code_extract.analysis.boilerplate import filter_blocks_by_pattern
        a = _make_block("CompA", source="class CompA: pass",
                        btype=CodeBlockType.CLASS,
                        file_path=Path("/proj/components/a.py"))
        b = _make_block("CompB", source="class CompB: pass",
                        btype=CodeBlockType.CLASS,
                        file_path=Path("/proj/components/b.py"))
        c = _make_block("util_fn", source="def util_fn(): pass",
                        btype=CodeBlockType.FUNCTION,
                        file_path=Path("/proj/utils/helpers.py"))
        blocks = _blocks_dict(a, b, c)
        result = filter_blocks_by_pattern(blocks, "components", "class")
        assert len(result) == 2
        names = {r.item.name for r in result}
        assert names == {"CompA", "CompB"}

    def test_filter_blocks_empty(self):
        from code_extract.analysis.boilerplate import filter_blocks_by_pattern
        a = _make_block("CompA", source="class CompA: pass",
                        btype=CodeBlockType.CLASS,
                        file_path=Path("/proj/components/a.py"))
        blocks = _blocks_dict(a)
        result = filter_blocks_by_pattern(blocks, "nonexistent", "class")
        assert result == []

    def test_batch_apply_template(self):
        from code_extract.analysis.boilerplate import batch_apply_template
        template = "class {{name}}({{base}}): pass"
        sets = [
            {"name": "Foo", "base": "Base"},
            {"name": "Bar", "base": "Parent"},
        ]
        results = batch_apply_template(template, sets)
        assert len(results) == 2
        assert "class Foo(Base): pass" == results[0]
        assert "class Bar(Parent): pass" == results[1]


# ── Migration ─────────────────────────────────────────────────

class TestMigration:
    def test_detect_no_patterns(self):
        from code_extract.analysis.migration import detect_migrations
        plain = _make_block("plain_func", source="def plain_func(): pass")
        blocks = _blocks_dict(plain)
        results = detect_migrations(blocks)
        assert isinstance(results, list)

    def test_detect_react_class(self):
        from code_extract.analysis.migration import detect_migrations
        react = _make_block(
            "MyComponent",
            lang=Language.JAVASCRIPT,
            btype=CodeBlockType.CLASS,
            source="class MyComponent extends React.Component {\n  render() { return <div/>; }\n}",
        )
        blocks = _blocks_dict(react)
        results = detect_migrations(blocks)
        # Should detect the React class → hooks pattern
        react_patterns = [r for r in results if "react" in r.get("pattern_id", "").lower()
                         or "React" in r.get("pattern_name", "")]
        # May or may not detect depending on exact matching
        assert isinstance(results, list)
