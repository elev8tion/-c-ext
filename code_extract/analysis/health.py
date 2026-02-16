"""Refactoring radar — long functions, duplication detection, coupling scores."""

from __future__ import annotations

import re
from collections import Counter

from code_extract.models import ExtractedBlock
from code_extract.analysis.graph_models import DependencyGraph


def analyze_health(
    blocks: dict[str, ExtractedBlock],
    graph: DependencyGraph,
) -> dict:
    """Analyze codebase health.

    Returns: {score, long_functions, duplications, coupling}
    """
    long_functions = _find_long_functions(blocks)
    duplications = _find_duplications(blocks)
    coupling = _compute_coupling(graph)
    score = _compute_score(blocks, long_functions, duplications, coupling)

    return {
        "score": score,
        "long_functions": long_functions[:30],  # top 30
        "duplications": duplications[:20],       # top 20 pairs
        "coupling": coupling[:20],               # top 20
    }


def _find_long_functions(blocks: dict[str, ExtractedBlock]) -> list[dict]:
    """Find functions/methods sorted by line count."""
    results: list[dict] = []
    function_types = {"function", "method"}

    for item_id, block in blocks.items():
        if block.item.block_type.value not in function_types:
            continue

        start = block.item.line_number
        end = block.item.end_line or start
        line_count = max(end - start, len(block.source_code.splitlines()))

        if line_count < 10:
            continue

        results.append({
            "item_id": item_id,
            "name": block.item.qualified_name,
            "file": str(block.item.file_path),
            "line_count": line_count,
        })

    results.sort(key=lambda x: -x["line_count"])
    return results


def _find_duplications(blocks: dict[str, ExtractedBlock]) -> list[dict]:
    """Find similar code blocks using fuzzy token-bag Jaccard similarity."""
    # Build token bags
    token_bags: list[tuple[str, str, Counter]] = []
    for item_id, block in blocks.items():
        tokens = _tokenize(block.source_code)
        if len(tokens) < 5:  # skip trivial blocks
            continue
        token_bags.append((item_id, block.item.qualified_name, Counter(tokens)))

    results: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for i in range(len(token_bags)):
        for j in range(i + 1, len(token_bags)):
            id_a, name_a, bag_a = token_bags[i]
            id_b, name_b, bag_b = token_bags[j]

            pair_key = (min(id_a, id_b), max(id_a, id_b))
            if pair_key in seen:
                continue
            seen.add(pair_key)

            similarity = _jaccard_similarity(bag_a, bag_b)
            if similarity >= 0.75:
                results.append({
                    "item_a": name_a,
                    "item_b": name_b,
                    "item_a_id": id_a,
                    "item_b_id": id_b,
                    "similarity": round(similarity, 3),
                })

    results.sort(key=lambda x: -x["similarity"])
    return results


def _compute_coupling(graph: DependencyGraph) -> list[dict]:
    """Rank items by forward + reverse dependency count."""
    results: list[dict] = []

    for item_id, node in graph.nodes.items():
        fwd = len(graph.forward.get(item_id, []))
        rev = len(graph.reverse.get(item_id, []))
        total = fwd + rev
        if total == 0:
            continue

        results.append({
            "item_id": item_id,
            "name": node.qualified_name,
            "score": total,
            "forward": fwd,
            "reverse": rev,
        })

    results.sort(key=lambda x: -x["score"])
    return results


def _compute_score(
    blocks: dict[str, ExtractedBlock],
    long_functions: list[dict],
    duplications: list[dict],
    coupling: list[dict],
) -> int:
    """Compute overall health score 0-100."""
    total = len(blocks)
    if total == 0:
        return 100

    score = 100.0

    # Penalize for long functions
    long_ratio = len(long_functions) / max(total, 1)
    score -= min(30, long_ratio * 100)

    # Penalize for duplications
    dup_ratio = len(duplications) / max(total, 1)
    score -= min(30, dup_ratio * 100)

    # Penalize for high coupling (items with > 10 connections)
    high_coupling = sum(1 for c in coupling if c["score"] > 10)
    coupling_ratio = high_coupling / max(total, 1)
    score -= min(20, coupling_ratio * 100)

    return max(0, min(100, round(score)))


def _tokenize(code: str) -> list[str]:
    """Simple tokenizer — split on non-alphanumeric, lowercase."""
    return [t.lower() for t in re.findall(r'[a-zA-Z_]\w+', code) if len(t) > 1]


def _jaccard_similarity(a: Counter, b: Counter) -> float:
    """Compute Jaccard similarity between two token-bag Counters."""
    all_keys = set(a) | set(b)
    if not all_keys:
        return 0.0
    intersection = sum(min(a[k], b[k]) for k in all_keys)
    union = sum(max(a[k], b[k]) for k in all_keys)
    return intersection / union if union > 0 else 0.0
