"""Data models for the dependency graph."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DependencyNode:
    item_id: str
    qualified_name: str
    block_type: str
    language: str
    file_path: str
    type_references: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


@dataclass
class DependencyEdge:
    source_id: str
    target_id: str
    edge_type: str  # "type_reference" | "import" | "parent"
    reference_name: str = ""


@dataclass
class DependencyGraph:
    nodes: dict[str, DependencyNode] = field(default_factory=dict)
    edges: list[DependencyEdge] = field(default_factory=list)
    forward: dict[str, set[str]] = field(default_factory=dict)  # source -> {targets}
    reverse: dict[str, set[str]] = field(default_factory=dict)  # target -> {sources}
    name_index: dict[str, list[str]] = field(default_factory=dict)  # name -> [item_ids]


@dataclass
class TransitiveDeps:
    root_id: str
    direct: set[str] = field(default_factory=set)
    all_transitive: set[str] = field(default_factory=set)
    cycles: list[list[str]] = field(default_factory=list)
