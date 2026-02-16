"""Migration mapper — detect and apply known migration patterns."""

from __future__ import annotations

import re

from code_extract.models import ExtractedBlock


# Known migration patterns
_PATTERNS = [
    {
        "id": "react_class_to_hooks",
        "name": "React Class Component -> Hooks",
        "detect": r'class\s+\w+\s+extends\s+(?:React\.)?(?:Component|PureComponent)',
        "language": "javascript",
        "description": "Convert React class components to functional components with hooks",
    },
    {
        "id": "flutter_stateful_to_riverpod",
        "name": "Flutter StatefulWidget -> Riverpod ConsumerWidget",
        "detect": r'class\s+\w+\s+extends\s+StatefulWidget',
        "language": "dart",
        "description": "Convert Flutter StatefulWidget to Riverpod ConsumerWidget",
    },
    {
        "id": "python_class_to_dataclass",
        "name": "Python Class -> Dataclass",
        "detect": r'class\s+\w+:?\s*\n\s+def\s+__init__\(self',
        "language": "python",
        "description": "Convert plain Python classes with __init__ to dataclasses",
    },
    {
        "id": "js_promise_to_async",
        "name": "Promise Chain -> Async/Await",
        "detect": r'\.then\s*\(',
        "language": "javascript",
        "description": "Convert .then() promise chains to async/await syntax",
    },
]


def detect_migrations(blocks: dict[str, ExtractedBlock]) -> list[dict]:
    """Detect possible migration patterns in the codebase.

    Returns list of: {pattern_id, pattern_name, description, items: [{item_id, name, file}]}
    """
    results: list[dict] = []

    for pattern in _PATTERNS:
        regex = re.compile(pattern["detect"], re.MULTILINE)
        matching_items: list[dict] = []

        for item_id, block in blocks.items():
            if block.item.language.value != pattern["language"]:
                continue
            if regex.search(block.source_code):
                matching_items.append({
                    "item_id": item_id,
                    "name": block.item.qualified_name,
                    "file": str(block.item.file_path),
                })

        if matching_items:
            results.append({
                "pattern_id": pattern["id"],
                "pattern_name": pattern["name"],
                "description": pattern["description"],
                "items": matching_items,
            })

    return results


def apply_migration(block: ExtractedBlock, pattern_id: str) -> dict:
    """Apply a migration pattern to a block.

    Returns: {original, migrated, pattern_name}
    """
    pattern = next((p for p in _PATTERNS if p["id"] == pattern_id), None)
    if not pattern:
        return {"original": block.source_code, "migrated": block.source_code, "pattern_name": "unknown"}

    migrated = block.source_code

    if pattern_id == "react_class_to_hooks":
        migrated = _migrate_react_class_to_hooks(block)
    elif pattern_id == "flutter_stateful_to_riverpod":
        migrated = _migrate_flutter_stateful_to_riverpod(block)
    elif pattern_id == "python_class_to_dataclass":
        migrated = _migrate_python_to_dataclass(block)
    elif pattern_id == "js_promise_to_async":
        migrated = _migrate_promise_to_async(block)

    return {
        "original": block.source_code,
        "migrated": migrated,
        "pattern_name": pattern["name"],
    }


def _migrate_react_class_to_hooks(block: ExtractedBlock) -> str:
    """Convert React class component to functional component with hooks."""
    code = block.source_code
    name = block.item.name

    # Extract state from this.state = { ... }
    state_match = re.search(r'this\.state\s*=\s*\{([^}]+)\}', code)
    state_vars: list[str] = []
    if state_match:
        for item in state_match.group(1).split(","):
            item = item.strip()
            if ":" in item:
                var_name = item.split(":")[0].strip()
                default_val = item.split(":")[1].strip()
                state_vars.append(f"  const [{var_name}, set{var_name.capitalize()}] = useState({default_val});")

    hooks_code = "\n".join(state_vars) if state_vars else "  // Add state hooks here"

    return f"""import React, {{ useState, useEffect }} from 'react';

function {name}(props) {{
{hooks_code}

  useEffect(() => {{
    // componentDidMount logic here
  }}, []);

  return (
    // JSX from render() method
    <div>{name}</div>
  );
}}

export default {name};
"""


def _migrate_flutter_stateful_to_riverpod(block: ExtractedBlock) -> str:
    """Convert StatefulWidget to ConsumerWidget."""
    name = block.item.name

    return f"""import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class {name} extends ConsumerWidget {{
  const {name}({{super.key}});

  @override
  Widget build(BuildContext context, WidgetRef ref) {{
    // Access providers with ref.watch() and ref.read()
    return Container(
      // Migrated from StatefulWidget
    );
  }}
}}
"""


def _migrate_python_to_dataclass(block: ExtractedBlock) -> str:
    """Convert plain class to dataclass."""
    code = block.source_code
    name = block.item.name

    # Extract __init__ params
    m = re.search(r'def\s+__init__\(self\s*,?\s*([^)]*)\)', code)
    fields: list[str] = []
    if m:
        for param in m.group(1).split(","):
            param = param.strip()
            if not param:
                continue
            if ":" in param:
                fields.append(f"    {param}")
            else:
                fields.append(f"    {param}: Any = None")

    fields_str = "\n".join(fields) if fields else "    pass"

    return f"""from dataclasses import dataclass

@dataclass
class {name}:
{fields_str}
"""


def _migrate_promise_to_async(block: ExtractedBlock) -> str:
    """Convert .then() chains to async/await."""
    code = block.source_code

    # Simple transformation: replace .then(result => ...) patterns
    # This is a simplified heuristic
    result = re.sub(
        r'(\w+)\s*\.\s*then\s*\(\s*(?:(\w+)\s*=>|function\s*\((\w+)\))\s*\{',
        r'const \2\3 = await \1;\n{',
        code,
    )

    # Add async to function declaration if not present
    if "async" not in result.split("\n")[0]:
        result = re.sub(r'(function\s+\w+)', r'async \1', result, count=1)
        result = re.sub(r'(const\s+\w+\s*=\s*)\(', r'\1async (', result, count=1)

    return result
