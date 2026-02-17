"""Remix Board — merge blocks from multiple scans, detect conflicts, apply renames."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from os.path import basename

from code_extract.models import ExtractedBlock


# ── Language / SQL constants ────────────────────────────────

LANGUAGE_GROUPS: dict[str, str] = {
    "javascript": "js_ts",
    "typescript": "js_ts",
    "java": "jvm",
    "kotlin": "jvm",
    "python": "python",
    "dart": "dart",
    "rust": "rust",
    "go": "go",
    "cpp": "cpp",
    "ruby": "ruby",
    "swift": "swift",
    "csharp": "csharp",
    "sql": "sql",
}

SQL_BLOCK_TYPES: set[str] = {
    "table", "view", "trigger", "policy", "migration", "index", "sql_function",
}


# ── Validation dataclasses ──────────────────────────────────

@dataclass
class ValidationIssue:
    """A single validation issue (error or warning)."""
    severity: str  # "error" | "warning"
    rule: str      # e.g. "language_coherence"
    message: str
    items: list[str] = field(default_factory=list)  # composite keys or names


@dataclass
class ValidationResult:
    """Aggregated result from all validation checks."""
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    is_buildable: bool = True


@dataclass
class RemixSource:
    """A single scan that contributes blocks to the remix."""
    scan_id: str
    project_name: str
    source_dir: str


@dataclass
class NamingConflict:
    """Two or more items from different projects share the same name."""
    name: str
    items: list[dict] = field(default_factory=list)
    # Each item: {composite_key, project_name, block_type, language}


def merge_blocks(
    sources: list[RemixSource],
    block_stores: dict[str, dict[str, ExtractedBlock]],
) -> tuple[dict[str, ExtractedBlock], dict[str, str]]:
    """Merge blocks from multiple scans into a unified dict.

    Keys are composite ``"{scan_id}::{item_id}"``.
    Returns ``(merged_blocks, origin_map)`` where *origin_map* maps
    composite key → project_name.
    """
    merged: dict[str, ExtractedBlock] = {}
    origin_map: dict[str, str] = {}

    for src in sources:
        blocks = block_stores.get(src.scan_id)
        if not blocks:
            continue
        for item_id, block in blocks.items():
            composite = f"{src.scan_id}::{item_id}"
            merged[composite] = block
            origin_map[composite] = src.project_name

    return merged, origin_map


def detect_naming_conflicts(
    merged_blocks: dict[str, ExtractedBlock],
    origin_map: dict[str, str],
) -> list[NamingConflict]:
    """Find items that share a name but come from different projects."""
    # Group by simple name
    by_name: dict[str, list[str]] = {}
    for composite_key, block in merged_blocks.items():
        name = block.item.name
        by_name.setdefault(name, []).append(composite_key)

    conflicts: list[NamingConflict] = []
    for name, keys in by_name.items():
        if len(keys) < 2:
            continue

        # Only a conflict if items come from different projects
        projects = {origin_map.get(k, "") for k in keys}
        if len(projects) < 2:
            continue

        items = []
        for k in keys:
            block = merged_blocks[k]
            items.append({
                "composite_key": k,
                "project_name": origin_map.get(k, ""),
                "block_type": block.item.block_type.value,
                "language": block.item.language.value,
            })
        conflicts.append(NamingConflict(name=name, items=items))

    return conflicts


def apply_conflict_resolutions(
    merged_blocks: dict[str, ExtractedBlock],
    resolutions: dict[str, str],
) -> dict[str, ExtractedBlock]:
    """Apply user-chosen renames to resolve naming conflicts.

    *resolutions* maps ``composite_key → new_name``.  For each renamed
    block we update ``item.name``, ``item.qualified_name`` (via the
    ``parent`` field), and do a word-boundary find/replace in
    ``source_code``.  We also update ``type_references`` in *other*
    blocks that referenced the old name.
    """
    # Build old→new mapping
    rename_map: dict[str, str] = {}
    for composite_key, new_name in resolutions.items():
        block = merged_blocks.get(composite_key)
        if not block:
            continue
        old_name = block.item.name
        if old_name == new_name:
            continue
        rename_map[old_name] = new_name

    # Apply renames to the target blocks themselves
    for composite_key, new_name in resolutions.items():
        block = merged_blocks.get(composite_key)
        if not block:
            continue
        old_name = block.item.name
        if old_name == new_name:
            continue

        # Rename in source code using word boundaries
        pattern = re.compile(r'\b' + re.escape(old_name) + r'\b')
        block.source_code = pattern.sub(new_name, block.source_code)
        block.item.name = new_name

    # Update type_references in ALL blocks that reference any renamed name
    for block in merged_blocks.values():
        updated_refs = []
        for ref in block.type_references:
            if ref in rename_map:
                updated_refs.append(rename_map[ref])
            else:
                updated_refs.append(ref)
        block.type_references = updated_refs

    return merged_blocks


# ── Validation functions ────────────────────────────────────

def validate_language_coherence(
    merged_blocks: dict[str, ExtractedBlock],
) -> list[ValidationIssue]:
    """Rule 1: All items must share a compatible language group.

    SQL items are excluded — they're handled by validate_sql_isolation.
    """
    groups: dict[str, list[str]] = {}  # group_key → [composite_keys]
    for key, block in merged_blocks.items():
        lang = block.item.language.value
        group = LANGUAGE_GROUPS.get(lang, lang)
        if group == "sql":
            continue  # SQL isolation is a separate rule
        groups.setdefault(group, []).append(key)

    if len(groups) <= 1:
        return []

    group_names = sorted(groups.keys())
    items_sample: list[str] = []
    for g in group_names:
        items_sample.extend(groups[g][:2])  # first 2 from each group

    return [ValidationIssue(
        severity="error",
        rule="language_coherence",
        message=f"Mixed language groups: {', '.join(group_names)}. "
                f"Items must share a compatible language (e.g. JS+TS or Java+Kotlin).",
        items=items_sample,
    )]


def validate_orphaned_methods(
    merged_blocks: dict[str, ExtractedBlock],
) -> list[ValidationIssue]:
    """Rule 2: Methods whose parent class isn't on canvas get a warning."""
    # Collect all item names on canvas
    names_on_canvas: set[str] = set()
    for block in merged_blocks.values():
        names_on_canvas.add(block.item.name)
        if block.item.parent:
            names_on_canvas.add(block.item.qualified_name)

    issues: list[ValidationIssue] = []
    for key, block in merged_blocks.items():
        if block.item.block_type.value != "method":
            continue
        if not block.item.parent:
            continue
        if block.item.parent not in names_on_canvas:
            issues.append(ValidationIssue(
                severity="warning",
                rule="orphaned_method",
                message=f"Method '{block.item.name}' needs parent class "
                        f"'{block.item.parent}' on canvas.",
                items=[key],
            ))

    return issues


def validate_sql_isolation(
    merged_blocks: dict[str, ExtractedBlock],
) -> list[ValidationIssue]:
    """Rule 4: SQL blocks can't mix with runtime code blocks."""
    sql_keys: list[str] = []
    runtime_keys: list[str] = []

    for key, block in merged_blocks.items():
        if block.item.block_type.value in SQL_BLOCK_TYPES:
            sql_keys.append(key)
        else:
            runtime_keys.append(key)

    if sql_keys and runtime_keys:
        return [ValidationIssue(
            severity="error",
            rule="sql_isolation",
            message=f"SQL blocks ({len(sql_keys)}) can't mix with "
                    f"runtime code blocks ({len(runtime_keys)}).",
            items=sql_keys[:2] + runtime_keys[:2],
        )]

    return []


def validate_unresolved_refs(
    merged_blocks: dict[str, ExtractedBlock],
) -> list[ValidationIssue]:
    """Rule 3: Warn about type references that don't resolve to anything on canvas."""
    # Build set of all names and qualified names available
    available: set[str] = set()
    for block in merged_blocks.values():
        available.add(block.item.name)
        if block.item.parent:
            available.add(block.item.qualified_name)

    issues: list[ValidationIssue] = []
    for key, block in merged_blocks.items():
        unresolved = [ref for ref in block.type_references if ref not in available]
        if unresolved:
            issues.append(ValidationIssue(
                severity="warning",
                rule="unresolved_refs",
                message=f"'{block.item.name}' references unresolved types: "
                        f"{', '.join(unresolved[:5])}",
                items=[key],
            ))

    return issues


def validate_circular_deps(
    merged_blocks: dict[str, ExtractedBlock],
) -> list[ValidationIssue]:
    """Rule 5: Warn about circular dependencies in the merged graph."""
    from code_extract.analysis.dependency_graph import DependencyGraphBuilder

    builder = DependencyGraphBuilder()
    graph = builder.build(merged_blocks)
    cycles = builder.detect_cycles(graph)

    issues: list[ValidationIssue] = []
    for cycle in cycles:
        issues.append(ValidationIssue(
            severity="warning",
            rule="circular_dependency",
            message=f"Circular dependency: {' → '.join(cycle)}",
            items=list(cycle),
        ))

    return issues


def validate_remix(
    merged_blocks: dict[str, ExtractedBlock],
    origin_map: dict[str, str],
    full: bool = False,
) -> ValidationResult:
    """Run all validation checks. Cheap checks always; expensive when full=True."""
    result = ValidationResult()

    # Always run cheap checks (rules 1, 2, 4)
    for issue in validate_language_coherence(merged_blocks):
        result.errors.append(issue)

    for issue in validate_orphaned_methods(merged_blocks):
        result.warnings.append(issue)

    for issue in validate_sql_isolation(merged_blocks):
        result.errors.append(issue)

    # Full validation adds expensive checks (rules 3, 5) + naming conflicts
    if full:
        for issue in validate_unresolved_refs(merged_blocks):
            result.warnings.append(issue)

        for issue in validate_circular_deps(merged_blocks):
            result.warnings.append(issue)

        conflicts = detect_naming_conflicts(merged_blocks, origin_map)
        result.conflicts = [
            {"name": c.name, "items": c.items}
            for c in conflicts
        ]

    result.is_buildable = len(result.errors) == 0
    return result
