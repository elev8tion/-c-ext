"""Refactoring radar — long functions, duplication detection, coupling scores."""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict

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


# ── MinHash-based duplication detection (O(n) instead of O(n²)) ──

_NUM_HASHES = 64  # number of MinHash permutations
_BAND_SIZE = 4    # rows per band for LSH
_NUM_BANDS = _NUM_HASHES // _BAND_SIZE


def _minhash_signature(token_set: frozenset[str]) -> tuple[int, ...]:
    """Compute a MinHash signature for a set of tokens."""
    sig = []
    for i in range(_NUM_HASHES):
        min_hash = float("inf")
        for token in token_set:
            h = int(hashlib.md5(f"{i}:{token}".encode()).hexdigest()[:8], 16)
            if h < min_hash:
                min_hash = h
        sig.append(min_hash if min_hash != float("inf") else 0)
    return tuple(sig)


def _find_duplications(blocks: dict[str, ExtractedBlock]) -> list[dict]:
    """Find similar code blocks using MinHash LSH — O(n) average case."""
    # Build token sets and MinHash signatures
    entries: list[tuple[str, str, frozenset[str], Counter]] = []
    for item_id, block in blocks.items():
        tokens = _tokenize(block.source_code)
        if len(tokens) < 5:
            continue
        token_set = frozenset(tokens)
        token_bag = Counter(tokens)
        entries.append((item_id, block.item.qualified_name, token_set, token_bag))

    # For small sets, use direct comparison (fast enough)
    if len(entries) <= 500:
        return _find_duplications_direct(entries)

    # Build MinHash signatures
    sigs: dict[str, tuple[int, ...]] = {}
    for item_id, name, token_set, _ in entries:
        sigs[item_id] = _minhash_signature(token_set)

    # LSH: band items into buckets
    candidates: set[tuple[str, str]] = set()
    for band_idx in range(_NUM_BANDS):
        buckets: defaultdict[tuple, list[str]] = defaultdict(list)
        start = band_idx * _BAND_SIZE
        end = start + _BAND_SIZE
        for item_id, _, _, _ in entries:
            band = sigs[item_id][start:end]
            buckets[band].append(item_id)

        for bucket_items in buckets.values():
            if len(bucket_items) < 2:
                continue
            # Only compare within bucket (typically small)
            for i in range(len(bucket_items)):
                for j in range(i + 1, len(bucket_items)):
                    pair = (min(bucket_items[i], bucket_items[j]),
                            max(bucket_items[i], bucket_items[j]))
                    candidates.add(pair)

    # Verify candidates with exact Jaccard
    entry_map = {item_id: (name, bag) for item_id, name, _, bag in entries}
    results: list[dict] = []

    for id_a, id_b in candidates:
        if id_a not in entry_map or id_b not in entry_map:
            continue
        name_a, bag_a = entry_map[id_a]
        name_b, bag_b = entry_map[id_b]
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


def _find_duplications_direct(entries: list[tuple[str, str, frozenset, Counter]]) -> list[dict]:
    """Direct pairwise comparison for small sets (<= 500 items)."""
    results: list[dict] = []
    for i in range(len(entries)):
        id_a, name_a, _, bag_a = entries[i]
        for j in range(i + 1, len(entries)):
            id_b, name_b, _, bag_b = entries[j]
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
        fwd = len(graph.forward.get(item_id, set()))
        rev = len(graph.reverse.get(item_id, set()))
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
