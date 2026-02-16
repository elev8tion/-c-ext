"""Dependency graph builder — builds graph from ExtractedBlocks, resolves transitive deps, detects cycles."""

from __future__ import annotations

import re
from collections import deque

from code_extract.models import ExtractedBlock
from code_extract.analysis.graph_models import (
    DependencyEdge,
    DependencyGraph,
    DependencyNode,
    TransitiveDeps,
)


class DependencyGraphBuilder:
    """Build a dependency graph from extracted code blocks."""

    def build(self, blocks: dict[str, ExtractedBlock]) -> DependencyGraph:
        graph = DependencyGraph()

        # Step 1: Build nodes and name index
        for item_id, block in blocks.items():
            node = DependencyNode(
                item_id=item_id,
                qualified_name=block.item.qualified_name,
                block_type=block.item.block_type.value,
                language=block.item.language.value,
                file_path=str(block.item.file_path),
                type_references=list(block.type_references),
                imports=list(block.imports),
            )
            graph.nodes[item_id] = node
            graph.forward[item_id] = []
            graph.reverse[item_id] = []

            # Index by simple name and qualified name
            for name in {block.item.name, block.item.qualified_name}:
                graph.name_index.setdefault(name, []).append(item_id)

        # Step 2: Build edges from type_references
        for item_id, node in graph.nodes.items():
            for ref in node.type_references:
                targets = graph.name_index.get(ref, [])
                for target_id in targets:
                    if target_id != item_id:
                        self._add_edge(graph, item_id, target_id, "type_reference", ref)

        # Step 3: Build edges from imports
        for item_id, node in graph.nodes.items():
            for imp in node.imports:
                imported_names = self._parse_import_names(imp)
                for name in imported_names:
                    targets = graph.name_index.get(name, [])
                    for target_id in targets:
                        if target_id != item_id:
                            self._add_edge(graph, item_id, target_id, "import", name)

        # Step 4: Build parent edges (method → class)
        for item_id, block in blocks.items():
            if block.item.parent:
                parent_targets = graph.name_index.get(block.item.parent, [])
                for parent_id in parent_targets:
                    if parent_id != item_id:
                        self._add_edge(graph, item_id, parent_id, "parent", block.item.parent)

        return graph

    def resolve_transitive(self, graph: DependencyGraph, root_id: str) -> TransitiveDeps:
        """BFS to find all transitive dependencies from root_id."""
        result = TransitiveDeps(root_id=root_id)

        if root_id not in graph.forward:
            return result

        # Direct deps
        result.direct = set(graph.forward.get(root_id, []))

        # BFS for all transitive
        visited = set()
        queue = deque([root_id])
        path: dict[str, list[str]] = {root_id: [root_id]}

        while queue:
            current = queue.popleft()
            if current in visited:
                # Cycle detected
                if current in path:
                    result.cycles.append(path[current] + [current])
                continue
            visited.add(current)

            for neighbor in graph.forward.get(current, []):
                if neighbor != root_id:
                    result.all_transitive.add(neighbor)
                if neighbor not in visited:
                    path[neighbor] = path.get(current, []) + [neighbor]
                    queue.append(neighbor)
                elif neighbor == root_id:
                    result.cycles.append(path.get(current, []) + [neighbor])

        result.all_transitive.discard(root_id)
        return result

    def detect_cycles(self, graph: DependencyGraph) -> list[list[str]]:
        """Detect all cycles in the graph using DFS."""
        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: set[str] = set()
        path: list[str] = []

        def dfs(node_id: str) -> None:
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)

            for neighbor in graph.forward.get(node_id, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    idx = path.index(neighbor) if neighbor in path else -1
                    if idx >= 0:
                        cycles.append(path[idx:] + [neighbor])

            path.pop()
            rec_stack.discard(node_id)

        for node_id in graph.nodes:
            if node_id not in visited:
                dfs(node_id)

        return cycles

    def _add_edge(
        self,
        graph: DependencyGraph,
        source_id: str,
        target_id: str,
        edge_type: str,
        reference_name: str,
    ) -> None:
        # Avoid duplicate edges
        if target_id in graph.forward.get(source_id, []):
            return
        edge = DependencyEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            reference_name=reference_name,
        )
        graph.edges.append(edge)
        graph.forward.setdefault(source_id, []).append(target_id)
        graph.reverse.setdefault(target_id, []).append(source_id)

    @staticmethod
    def _parse_import_names(import_statement: str) -> list[str]:
        """Extract imported names from an import statement."""
        names: list[str] = []

        # Python: from X import Y, Z or import X
        m = re.match(r'from\s+\S+\s+import\s+(.+)', import_statement)
        if m:
            for part in m.group(1).split(','):
                part = part.strip()
                if ' as ' in part:
                    part = part.split(' as ')[0].strip()
                if part and part != '*':
                    names.append(part)
            return names

        m = re.match(r'import\s+(.+)', import_statement)
        if m:
            for part in m.group(1).split(','):
                part = part.strip()
                if ' as ' in part:
                    part = part.split(' as ')[0].strip()
                # Use the last component
                if '.' in part:
                    names.append(part.split('.')[-1])
                elif part:
                    names.append(part)
            return names

        # JS/TS: import { X, Y } from '...' or import X from '...'
        m = re.match(r'import\s+\{([^}]+)\}\s+from', import_statement)
        if m:
            for part in m.group(1).split(','):
                part = part.strip()
                if ' as ' in part:
                    part = part.split(' as ')[0].strip()
                if part:
                    names.append(part)
            return names

        m = re.match(r"import\s+(\w+)\s+from", import_statement)
        if m:
            names.append(m.group(1))
            return names

        # Dart: import '...' or import '...' show X, Y
        m = re.search(r'show\s+(.+?)(?:;|$)', import_statement)
        if m:
            for part in m.group(1).split(','):
                part = part.strip()
                if part:
                    names.append(part)
            return names

        return names
