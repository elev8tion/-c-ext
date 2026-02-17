# CLAUDE.md — code-extract

## Project Overview

CLI + Web UI tool for extracting, analyzing, and exporting code blocks from any codebase. Python backend (FastAPI), single-page frontend (vanilla JS + Tailwind + Cytoscape.js).

## Quick Start

```bash
# Activate venv
source .venv/bin/activate

# Run tests (65 tests, ~1s)
python -m pytest tests/ --tb=short -q

# Start web UI
python -m code_extract.cli serve
```

## Architecture

```
code_extract/
├── scanner/          # Language scanners (AST, tree-sitter, regex)
├── extractor/        # Source code extraction
├── cleaner/          # Import cleanup, sanitization
├── formatter/        # Code formatting + validation
├── exporter/         # File writing, README/manifest generation
├── analysis/         # Analysis modules (see below)
│   ├── architecture.py   # Cytoscape.js graph data (dir grouping, edges, stats)
│   ├── catalog.py        # Component catalog builder
│   ├── health.py         # Long functions, duplication, coupling scores
│   ├── dead_code.py      # Unused code detection
│   ├── docs.py           # Auto-generated documentation
│   ├── tour.py           # Codebase walkthrough generator
│   ├── diff.py           # Semantic diff between codebases
│   ├── graph_models.py   # DependencyGraph, GraphNode, GraphEdge models
│   └── dependency_graph.py
├── web/
│   ├── app.py            # FastAPI app factory
│   ├── state.py          # Server state (scan store)
│   ├── api.py            # Core scan/extract/preview endpoints
│   ├── api_analysis.py   # Architecture, health, dead-code, smart-extract
│   ├── api_catalog.py    # Catalog build endpoint
│   ├── api_docs.py       # Docs generation + WebSocket watch
│   ├── api_diff.py       # Semantic diff endpoint
│   ├── api_tools.py      # Package, pattern clone, boilerplate, migration
│   ├── api_tour.py       # Tour generation endpoint
│   └── static/
│       ├── app.js        # Single-file frontend (IIFE module)
│       ├── index.html    # SPA shell (Tailwind utility classes)
│       └── styles.css    # Liquid Glass Neon theme tokens + components
├── models.py             # Core data models (CodeBlock, ScanResult)
├── pipeline.py           # Scan → Extract → Clean → Format → Export pipeline
└── cli.py                # Click CLI (scan, extract, serve)
```

## Frontend (app.js) Key Patterns

- **Single IIFE** — all state and functions inside `const app = (() => { ... })()`, public API returned at bottom
- **Tab system** — `switchTab(name)` toggles `.tab-panel` visibility, lazy-loads data via `loadTabData()`
- **Architecture graph state:**
  - `archCy` — Cytoscape instance (null until architecture loads)
  - `currentArchLayout` — persists layout choice across tab switches (`'dagre'` | `'cose'` | `'circle'`)
  - `ARCH_LAYOUTS` — shared layout configs used by constructor, tab switch, and layout buttons
  - Constructor uses `layout: { name: 'preset' }` (no-op), single layout run happens in post-init `setTimeout`
- **Highlight system** — `archResetHighlight()` clears `highlighted/neighbor/dimmed` classes AND search input
- **Module sidebar** — single-click expands, double-click zooms graph to that module's compound node
- **Search** — `archSearchNodes(query)` dims non-matches, highlights matches + ancestors; ESC resets
- **Node sizing** — `width/height` as functions of `ele.data('connections')`, range 28–52px
- **Edge thickness** — cross-module edges sized by `ele.data('weight')`, range 1.5–5px

## Backend (architecture.py) Key Patterns

- `_safe_id(name)` — sanitizes directory names to valid Cytoscape node IDs (replaces non-alphanumeric with `_`)
- Frontend has matching `_safeId()` for module sidebar → graph zoom lookup
- `generate_architecture()` returns `{ elements: [...], modules: [...], stats: {...} }`
- Elements include compound (parent) nodes for directories + leaf nodes for items + edges
- Each leaf node carries `connections` count; cross-module edges carry `weight`
- Items per directory capped at `MAX_ITEMS_PER_DIR = 15` with overflow node

## CSS Theme

- Design tokens in `:root` (canvas, glass, accent, text tiers, neon colors)
- Glass effect: `background: var(--glass-bg)` + `backdrop-filter: blur(var(--glass-blur))`
- Accent color: `#00f0ff` (cyan) — used for active states, highlights, graph focus
- Architecture controls bar: glass-tinted, horizontally scrollable, `position: absolute` spanning full width

## Tests

```bash
python -m pytest tests/ -q              # all 65 tests
python -m pytest tests/test_analysis.py  # architecture, health, dead-code, catalog, tour
python -m pytest tests/test_web_analysis_api.py  # API integration tests
```

## Conventions

- Commit style: imperative subject, body explains why, `Co-Authored-By` trailer
- No external state management — all frontend state in IIFE closure variables
- Backend analysis functions are pure: take `DependencyGraph` + `source_dir`, return dicts
- API endpoints: POST for analysis (takes `scan_id`), GET for previews/exports
- HTML uses Tailwind utility classes inline; `styles.css` only for custom components and theme tokens
