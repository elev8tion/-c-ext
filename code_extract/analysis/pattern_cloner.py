"""Pattern cloner — intelligent case-variant name replacement."""

from __future__ import annotations

import re


def clone_pattern(
    source_code: str,
    original_name: str,
    new_name: str,
) -> str:
    """Clone code by replacing all case variants of original_name with new_name.

    Handles: PascalCase, camelCase, snake_case, UPPER_SNAKE, kebab-case.
    """
    variants = _build_variants(original_name)
    new_variants = _build_variants(new_name)

    result = source_code

    # Replace each variant pair
    for old_var, new_var in zip(variants, new_variants):
        if old_var and new_var:
            result = result.replace(old_var, new_var)

    return result


def preview_clone(
    source_code: str,
    original_name: str,
    new_name: str,
) -> dict:
    """Preview what a clone would produce.

    Returns: {transformed_code, replacements: [{old, new, count}]}
    """
    variants = _build_variants(original_name)
    new_variants = _build_variants(new_name)

    replacements: list[dict] = []
    result = source_code

    for old_var, new_var in zip(variants, new_variants):
        if old_var and new_var and old_var in result:
            count = result.count(old_var)
            result = result.replace(old_var, new_var)
            replacements.append({"old": old_var, "new": new_var, "count": count})

    return {"transformed_code": result, "replacements": replacements}


def _build_variants(name: str) -> list[str]:
    """Build case variants from a name.

    Input can be PascalCase, camelCase, snake_case, etc.
    Returns: [PascalCase, camelCase, snake_case, UPPER_SNAKE, kebab-case]
    """
    words = _split_into_words(name)
    if not words:
        return [name, name, name, name, name]

    pascal = "".join(w.capitalize() for w in words)
    camel = words[0].lower() + "".join(w.capitalize() for w in words[1:])
    snake = "_".join(w.lower() for w in words)
    upper_snake = "_".join(w.upper() for w in words)
    kebab = "-".join(w.lower() for w in words)

    return [pascal, camel, snake, upper_snake, kebab]


def _split_into_words(name: str) -> list[str]:
    """Split a name into words regardless of case convention."""
    # Handle snake_case, kebab-case
    if "_" in name:
        return [w for w in name.split("_") if w]
    if "-" in name:
        return [w for w in name.split("-") if w]

    # Handle PascalCase / camelCase
    words: list[str] = []
    current: list[str] = []

    for i, ch in enumerate(name):
        if ch.isupper() and current:
            # Check for sequences like "XMLParser" -> ["XML", "Parser"]
            if i + 1 < len(name) and name[i + 1].islower() and len(current) > 1 and current[-1].isupper():
                words.append("".join(current[:-1]))
                current = [current[-1], ch]
            else:
                if not all(c.isupper() for c in current):
                    words.append("".join(current))
                    current = [ch]
                else:
                    current.append(ch)
        else:
            current.append(ch)

    if current:
        words.append("".join(current))

    return [w for w in words if w]
