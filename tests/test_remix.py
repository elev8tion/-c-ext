"""Tests for the Remix Board analysis functions."""

import pytest
from pathlib import Path

from code_extract.models import (
    Language, CodeBlockType, ScannedItem, ExtractedBlock,
)
from code_extract.analysis.remix import (
    RemixSource, merge_blocks, detect_naming_conflicts, apply_conflict_resolutions,
    validate_language_coherence, validate_orphaned_methods, validate_sql_isolation,
    validate_unresolved_refs, validate_circular_deps, validate_remix,
    ValidationIssue, ValidationResult,
)


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


# ── merge_blocks ─────────────────────────────────────────────

class TestMergeBlocks:
    def test_empty(self):
        merged, origin = merge_blocks([], {})
        assert merged == {}
        assert origin == {}

    def test_single_source(self):
        b = _make_block("helper", source="def helper(): pass")
        blocks = _blocks_dict(b)
        src = RemixSource(scan_id="s1", project_name="proj-a", source_dir="/a")

        merged, origin = merge_blocks([src], {"s1": blocks})

        assert len(merged) == 1
        key = list(merged.keys())[0]
        assert key.startswith("s1::")
        assert origin[key] == "proj-a"

    def test_two_sources(self):
        b1 = _make_block("alpha", source="def alpha(): pass")
        b2 = _make_block("beta", source="def beta(): pass")
        blocks_a = _blocks_dict(b1)
        blocks_b = _blocks_dict(b2)
        src_a = RemixSource(scan_id="s1", project_name="proj-a", source_dir="/a")
        src_b = RemixSource(scan_id="s2", project_name="proj-b", source_dir="/b")

        merged, origin = merge_blocks([src_a, src_b], {"s1": blocks_a, "s2": blocks_b})

        assert len(merged) == 2
        projects = set(origin.values())
        assert projects == {"proj-a", "proj-b"}
        # All keys should be unique composites
        assert all("::" in k for k in merged)


# ── detect_naming_conflicts ──────────────────────────────────

class TestDetectConflicts:
    def test_different_names_no_conflict(self):
        b1 = _make_block("foo", source="def foo(): pass")
        b2 = _make_block("bar", source="def bar(): pass")
        merged = {"s1::id1": b1, "s2::id2": b2}
        origin = {"s1::id1": "proj-a", "s2::id2": "proj-b"}

        conflicts = detect_naming_conflicts(merged, origin)
        assert len(conflicts) == 0

    def test_same_name_different_projects(self):
        b1 = _make_block("Config", source="class Config: pass")
        b2 = _make_block("Config", source="class Config: pass")
        merged = {"s1::id1": b1, "s2::id2": b2}
        origin = {"s1::id1": "proj-a", "s2::id2": "proj-b"}

        conflicts = detect_naming_conflicts(merged, origin)
        assert len(conflicts) == 1
        assert conflicts[0].name == "Config"
        assert len(conflicts[0].items) == 2

    def test_same_name_same_project_not_conflict(self):
        b1 = _make_block("util", source="def util(): pass", line=1)
        b2 = _make_block("util", source="def util(): pass", line=20)
        merged = {"s1::id1": b1, "s1::id2": b2}
        origin = {"s1::id1": "proj-a", "s1::id2": "proj-a"}

        conflicts = detect_naming_conflicts(merged, origin)
        assert len(conflicts) == 0


# ── apply_conflict_resolutions ───────────────────────────────

class TestApplyResolutions:
    def test_renames_source_code(self):
        b = _make_block("Config", source="class Config:\n    name = 'Config'")
        merged = {"s1::id1": b}

        result = apply_conflict_resolutions(merged, {"s1::id1": "AppConfig"})

        assert result["s1::id1"].item.name == "AppConfig"
        assert "class AppConfig:" in result["s1::id1"].source_code
        assert "name = 'AppConfig'" in result["s1::id1"].source_code

    def test_updates_cross_refs(self):
        b1 = _make_block("Config", source="class Config: pass")
        b2 = _make_block("App", source="def App(): pass", type_references=["Config"])
        merged = {"s1::id1": b1, "s2::id2": b2}

        result = apply_conflict_resolutions(merged, {"s1::id1": "AppConfig"})

        assert "AppConfig" in result["s2::id2"].type_references
        assert "Config" not in result["s2::id2"].type_references


# ── validate_language_coherence ──────────────────────────────

class TestLanguageCoherence:
    def test_single_language_ok(self):
        b1 = _make_block("foo", lang=Language.PYTHON)
        b2 = _make_block("bar", lang=Language.PYTHON)
        merged = {"s1::id1": b1, "s1::id2": b2}
        assert validate_language_coherence(merged) == []

    def test_js_ts_compatible(self):
        b1 = _make_block("foo", lang=Language.JAVASCRIPT)
        b2 = _make_block("bar", lang=Language.TYPESCRIPT)
        merged = {"s1::id1": b1, "s2::id2": b2}
        assert validate_language_coherence(merged) == []

    def test_java_kotlin_compatible(self):
        b1 = _make_block("Foo", lang=Language.JAVA, btype=CodeBlockType.CLASS)
        b2 = _make_block("Bar", lang=Language.KOTLIN, btype=CodeBlockType.CLASS)
        merged = {"s1::id1": b1, "s2::id2": b2}
        assert validate_language_coherence(merged) == []

    def test_python_dart_error(self):
        b1 = _make_block("foo", lang=Language.PYTHON)
        b2 = _make_block("bar", lang=Language.DART)
        merged = {"s1::id1": b1, "s2::id2": b2}
        issues = validate_language_coherence(merged)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].rule == "language_coherence"

    def test_python_plus_sql_no_language_error(self):
        """SQL items are excluded from language coherence (handled by sql_isolation)."""
        b1 = _make_block("foo", lang=Language.PYTHON)
        b2 = _make_block("users", lang=Language.SQL, btype=CodeBlockType.TABLE)
        merged = {"s1::id1": b1, "s2::id2": b2}
        assert validate_language_coherence(merged) == []


# ── validate_orphaned_methods ────────────────────────────────

class TestOrphanedMethods:
    def test_parent_present_ok(self):
        b_class = _make_block("MyClass", btype=CodeBlockType.CLASS)
        b_method = _make_block("do_stuff", btype=CodeBlockType.METHOD, parent="MyClass")
        merged = {"s1::id1": b_class, "s1::id2": b_method}
        assert validate_orphaned_methods(merged) == []

    def test_parent_missing_warns(self):
        b_method = _make_block("do_stuff", btype=CodeBlockType.METHOD, parent="MissingClass")
        merged = {"s1::id1": b_method}
        issues = validate_orphaned_methods(merged)
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert issues[0].rule == "orphaned_method"
        assert "MissingClass" in issues[0].message

    def test_function_no_parent_ok(self):
        """Functions don't have parents — no warning."""
        b = _make_block("helper", btype=CodeBlockType.FUNCTION)
        merged = {"s1::id1": b}
        assert validate_orphaned_methods(merged) == []


# ── validate_sql_isolation ───────────────────────────────────

class TestSQLIsolation:
    def test_all_sql_ok(self):
        b1 = _make_block("users", lang=Language.SQL, btype=CodeBlockType.TABLE)
        b2 = _make_block("orders", lang=Language.SQL, btype=CodeBlockType.VIEW)
        merged = {"s1::id1": b1, "s1::id2": b2}
        assert validate_sql_isolation(merged) == []

    def test_all_runtime_ok(self):
        b1 = _make_block("foo", lang=Language.PYTHON)
        b2 = _make_block("bar", lang=Language.PYTHON)
        merged = {"s1::id1": b1, "s1::id2": b2}
        assert validate_sql_isolation(merged) == []

    def test_mixed_error(self):
        b1 = _make_block("users", lang=Language.SQL, btype=CodeBlockType.TABLE)
        b2 = _make_block("foo", lang=Language.PYTHON)
        merged = {"s1::id1": b1, "s2::id2": b2}
        issues = validate_sql_isolation(merged)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].rule == "sql_isolation"


# ── validate_unresolved_refs ─────────────────────────────────

class TestUnresolvedRefs:
    def test_all_resolved(self):
        b1 = _make_block("Config", btype=CodeBlockType.CLASS)
        b2 = _make_block("App", type_references=["Config"])
        merged = {"s1::id1": b1, "s1::id2": b2}
        assert validate_unresolved_refs(merged) == []

    def test_unresolved_warning(self):
        b = _make_block("App", type_references=["MissingType"])
        merged = {"s1::id1": b}
        issues = validate_unresolved_refs(merged)
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert "MissingType" in issues[0].message

    def test_no_refs(self):
        b = _make_block("foo")
        merged = {"s1::id1": b}
        assert validate_unresolved_refs(merged) == []


# ── validate_circular_deps ───────────────────────────────────

class TestCircularDeps:
    def test_no_cycle(self):
        b1 = _make_block("A", type_references=["B"])
        b2 = _make_block("B")
        merged = {"s1::id1": b1, "s1::id2": b2}
        # B doesn't reference A → no cycle
        assert validate_circular_deps(merged) == []

    def test_cycle_detected(self):
        b1 = _make_block("A", type_references=["B"])
        b2 = _make_block("B", type_references=["A"])
        merged = {"s1::id1": b1, "s1::id2": b2}
        issues = validate_circular_deps(merged)
        assert len(issues) >= 1
        assert issues[0].severity == "warning"
        assert issues[0].rule == "circular_dependency"


# ── validate_remix (orchestrator) ────────────────────────────

class TestValidateRemix:
    def test_clean_canvas(self):
        b1 = _make_block("foo", lang=Language.PYTHON)
        b2 = _make_block("bar", lang=Language.PYTHON)
        merged = {"s1::id1": b1, "s1::id2": b2}
        origin = {"s1::id1": "proj-a", "s1::id2": "proj-a"}

        result = validate_remix(merged, origin)
        assert result.is_buildable is True
        assert result.errors == []

    def test_errors_block_build(self):
        b1 = _make_block("foo", lang=Language.PYTHON)
        b2 = _make_block("bar", lang=Language.DART)
        merged = {"s1::id1": b1, "s2::id2": b2}
        origin = {"s1::id1": "proj-a", "s2::id2": "proj-b"}

        result = validate_remix(merged, origin)
        assert result.is_buildable is False
        assert len(result.errors) >= 1

    def test_full_includes_conflicts(self):
        b1 = _make_block("Config", lang=Language.PYTHON)
        b2 = _make_block("Config", lang=Language.PYTHON)
        merged = {"s1::id1": b1, "s2::id2": b2}
        origin = {"s1::id1": "proj-a", "s2::id2": "proj-b"}

        result = validate_remix(merged, origin, full=True)
        assert result.is_buildable is True
        assert len(result.conflicts) == 1
        assert result.conflicts[0]["name"] == "Config"
