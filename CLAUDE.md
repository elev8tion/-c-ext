# CLAUDE.md — code-extract

## Project Overview

CLI + Web UI tool for extracting, analyzing, and exporting code blocks from any codebase. Python backend (FastAPI), single-page frontend (vanilla JS + Tailwind + Cytoscape.js).

## Quick Start

```bash
# Activate venv
source .venv/bin/activate

# Run tests (279 tests, ~2s)
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
├── ai/
│   ├── __init__.py           # Exports all phase modules + AIConfig/AIModel
│   ├── service.py            # DeepSeek AI chat service
│   ├── tools.py              # Legacy tool definitions
│   ├── tool_registry.py      # Phase 1: Centralized tool registry + execution engine
│   ├── tool_migration.py     # Phase 2: Legacy tool discovery + migration layer
│   ├── tool_enhancement.py   # Phase 3: Context, dependencies, chains, validation
│   ├── tool_system.py        # Phase 4: Unified ToolSystem + config + health monitoring
│   ├── tool_intelligence.py  # Phase 5: Pattern recognition, recommendations, analytics
│   └── tool_orchestration.py # Phase 6: Event bus, policies, resource mgmt, self-optimizer
├── models.py             # Core data models (CodeBlock, ScanResult)
├── pipeline.py           # Scan → Extract → Clean → Format → Export pipeline
└── cli.py                # Click CLI (scan, extract, serve)
```

## AI Tool System (Phases 1–6)

Six-layer tool infrastructure in `code_extract/ai/`:

### Phase 1 — Tool Registry (`tool_registry.py`)
- `ToolRegistry` — central registry with decorator-based `@registry.register()` for tool functions
- `ToolCategory` enum — GENERAL, CODE_ANALYSIS, UI_OPERATIONS, DATA_QUERIES, WORKFLOW, BOILERPLATE, MIGRATION, EXTRACTION
- `ToolMetadata` — rich metadata with parameter introspection, return types, category
- `registry.execute(name, args, context)` — validated execution with history tracking
- `registry.generate_openapi_schema()` — auto-generated OpenAPI spec for all tools
- Global `registry` instance with example tools (`search_items`, `get_item_code`)

### Phase 2 — Tool Migration (`tool_migration.py`)
- `ToolIntegrationLayer` — discovers tool-like functions in existing modules via `inspect`
- `_infer_category()` — maps tool names to categories by keyword matching
- `migrate_tool()` / `migrate_all_discovered()` — wraps legacy tools for registry compatibility
- `create_compatibility_shim()` — drop-in replacement for old `execute_tool` calls
- `generate_migration_report()` / `export_migration_config()` — migration status tracking

### Phase 3 — Tool Enhancement (`tool_enhancement.py`)
- `ExecutionContext` — session-scoped data, state, permissions, resource limits, execution history
- `DependencyGraph` — tool dependency tracking with prerequisite/output edges, execution path finding
- `ToolChain` — sequential tool execution with `{{ variable }}` template resolution between steps
- `ToolValidator` — pre-execution validation (required params, type checking, custom rules, resource limits)
- `create_safe_executor()` — wraps registry execution with validation gate

### Phase 4 — Tool System (`tool_system.py`)
- `ToolSystem` — unified entry point integrating registry, migration, dependencies, validation
- `ToolSystemConfig` — YAML/JSON-persisted configuration (discovery, performance, API, security settings)
- `ToolSystemHealth` — metric tracking with warning/critical thresholds, file-persisted metrics
- `execute_tool()` — thread-safe execution with context creation, validation, health metric updates
- `create_tool_chain()` / `get_system_info()` / `get_openapi_schema()` / `export_configuration()`
- `yaml` optional — falls back to JSON if PyYAML not installed

### Phase 5 — Intelligence Layer (`tool_intelligence.py`)
- `UsageHistory` — tool usage recording with per-user history, stats, sequence extraction, file persistence
- `PatternRecognizer` — sequential and co-occurrence pattern discovery with configurable support/confidence
- `ToolRecommender` — context-based, pattern-based, collaborative, and alternative recommendations
- `WorkflowGenerator` — named workflow creation, execution, optimization suggestions
- `PredictiveAnalytics` — demand forecasting, bottleneck detection, user need prediction
- `IntelligenceLayer` — main integration class with `get_recommendations()`, `generate_workflow_for_goal()`, `get_insights()`, `optimize_system()`
- `enhance_tool_system_with_intelligence()` — wraps ToolSystem to auto-record usage
- `numpy`, `sklearn`, `networkx` optional — graceful fallbacks when not installed

### Phase 6 — Orchestration Layer (`tool_orchestration.py`)
- `EventBus` — pub/sub system for `SystemEvent` types (tool execution, errors, health changes, etc.)
- `PolicyEngine` — rule-based orchestration mode selection with condition/and/or/not operators
- `OrchestrationPolicy` — mode + strategy + rules + priority; supports manual/assisted/automated/autonomous/adaptive
- `ResourceManager` — `ThreadPoolExecutor`-backed execution with resource usage tracking
- `SelfOptimizer` — event-driven performance monitoring, bottleneck detection, optimization suggestions
- `AutonomousOrchestrator` — operation lifecycle (start → execute → complete/fail), mode-specific execution paths
- `OrchestrationLayer` — top-level API with `orchestrate()`, `get_status()`, `add_policy()`, `optimize_system()`
- `create_complete_system()` — factory that wires all phases together

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
python -m pytest tests/ -q                    # all 279 tests
python -m pytest tests/test_analysis.py       # architecture, health, dead-code, catalog, tour
python -m pytest tests/test_web_analysis_api.py  # API integration tests
python -m pytest tests/test_tool_system.py    # tool system phases 1-6 (107 tests)
```

## Conventions

- Commit style: imperative subject, body explains why, `Co-Authored-By` trailer
- No external state management — all frontend state in IIFE closure variables
- Backend analysis functions are pure: take `DependencyGraph` + `source_dir`, return dicts
- API endpoints: POST for analysis (takes `scan_id`), GET for previews/exports
- HTML uses Tailwind utility classes inline; `styles.css` only for custom components and theme tokens
