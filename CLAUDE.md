# CLAUDE.md — code-extract

## Project Overview

CLI + Web UI tool for extracting, analyzing, and exporting code blocks from any codebase. Python backend (FastAPI), single-page frontend (vanilla JS + Tailwind + Cytoscape.js).

## Quick Start

```bash
# Activate venv
source .venv/bin/activate

# Run tests (363 tests, ~3s)
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
│   ├── __init__.py           # Exports all phase modules + AIConfig/AIModel + temps
│   ├── service.py            # DeepSeek AI chat service (agent, reasoner, structured)
│   ├── tools.py              # Legacy tool definitions
│   ├── token_utils.py        # Token counting (tiktoken optional, heuristic fallback)
│   ├── rate_limiter.py       # Sliding-window rate limiter (per-key)
│   ├── tool_bridge.py        # Legacy ↔ ToolSystem integration bridge
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

## AI Chat Features (F1–F9)

Nine features enhancing AI chat response quality and system robustness:

### F1 — Token Counting (`token_utils.py`)
- `estimate_tokens(text)` / `truncate_to_tokens(text, max)` / `estimate_messages_tokens(msgs)` / `has_tiktoken()`
- Uses `cl100k_base` encoding via tiktoken (optional); falls back to `len(text) / 3.5` heuristic
- Lazy-loads encoder on first call; `tiktoken` is an optional dependency (`pip install code-extract[ai]`)

### F2 — Model-Specific Prompting
- **Coder** (`deepseek-coder`): File-path-emphasized code blocks (`### File: path — name (type)`), architecture focus line
- **Reasoner** (`deepseek-reasoner`): No system messages, no tools — single-shot via `_reasoner_chat()` / `_build_reasoner_message()`; pre-gathers health/arch/dead_code data via `_execute_tool()`
- `_build_messages()` folds system prompt into user message for Reasoner
- `agent_chat()` early-returns to `_reasoner_chat()` when model is Reasoner

### F3 — Per-Model Temperature
- `OPTIMAL_TEMPS` dict: chat=0.7, coder=0.7, reasoner=0.6 (module-level in `__init__.py`)
- `AIConfig.get_optimal_temperature()` — lookup by `self.model.value`, default 0.7
- `AIConfig.get_tool_temperature()` — `max(0.1, optimal - 0.2)` for precise tool selection
- Used in `agent_chat()` tool loop (tool temp), `_synthesize_answer()` and `chat_with_code()` (optimal temp)

### F4 — Structured JSON Analysis (`POST /api/ai/structured`)
- `DeepSeekService.structured_analyze()`: two-phase — data gathering via `_execute_tool()`, then JSON synthesis
- Request model: `StructuredAnalysisRequest(scan_id, focus?, item_ids?, model?, api_key?)`
- Focus filters: `"health"`, `"architecture"`, `"dead_code"` — gathers only that tool's data
- Response: `{analysis: {summary, issues: [{severity, file, line, type, description, fix}], recommendations}, model, usage, gathered_data_keys}`
- Uses `response_format: {"type": "json_object"}`; graceful fallback if JSON parse fails

### F5 — Sandwich Prompt Structure
- `_build_system_prompt()`: TOP (identity + "IMPORTANT: reference by name/path") → MIDDLE (code + analysis context) → BOTTOM (Response Guidelines)
- `_build_agent_system_prompt()`: TOP (identity + capabilities) → MIDDLE (history + code + analysis) → BOTTOM (Guidelines + Response Format)
- Exploits model attention pattern: strongest at start and end of prompt

### F6 — Health-Aware Item Scoring
- `_select_relevant_items()` accepts optional `analysis_context` parameter
- Extracts `problematic_names` set from `health.long_functions`, `health.high_coupling`, and `dead_code`
- Items matching problematic names get +3 bonus score
- Callers in `chat_with_scan()` and `agent_chat_endpoint()` pass analysis context

### F7 — Context Size in API Response
- `agent_chat()` returns `context_size` (int), `context_unit` ("tokens" | "chars_estimated"), `tool_calls_made` (int)
- Token budget check: `TOKEN_LIMITS = {chat: 64k, coder: 128k, reasoner: 128k}` × 0.80; breaks loop if exceeded
- `chat_with_scan()` estimates context from code+analysis+query
- `agent_chat_endpoint()` records `ai_context_size` metric in `ToolSystemHealth`
- Frontend footer: `"deepseek-chat · 12.4k tokens · 3 tool calls"`

### F8 — Server-Side Config Persistence
- Config file: `~/.code-extract/.chat_config.json`
- `_load_ai_config()` / `_save_ai_config()` helpers
- `GET /api/ai/config` → `{api_key_set: bool, selected_model: str}` (never exposes raw key)
- `POST /api/ai/config` → saves key + model; `"KEEP_EXISTING"` preserves key
- Fallback: `chat_with_scan()` and `agent_chat_endpoint()` try persisted config if no key in request/env

### F9 — Rate Limiting (`rate_limiter.py`)
- `RateLimiter(max_requests=30, window_seconds=60)` — sliding window, per-key (scan_id)
- `check(key) → (allowed, retry_after)` / `remaining(key) → int`
- Thread-safe (`threading.Lock`), auto-prunes expired timestamps
- `get_rate_limiter()` singleton; applied to `chat_with_scan()`, `agent_chat_endpoint()`, `structured_analysis()`
- Returns HTTP 429 with `Retry-After` header when exceeded

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
python -m pytest tests/ -q                        # all 363 tests
python -m pytest tests/test_analysis.py           # architecture, health, dead-code, catalog, tour
python -m pytest tests/test_web_analysis_api.py   # API integration tests
python -m pytest tests/test_tool_system.py        # tool system phases 1-6 (107 tests)
python -m pytest tests/test_ai.py                 # AI config, service, prompts, scoring (27 tests)
python -m pytest tests/test_ai_agent.py           # agent tools, service, API, reasoner (31 tests)
python -m pytest tests/test_token_utils.py        # token counting + truncation (14 tests)
python -m pytest tests/test_rate_limiter.py       # rate limiter sliding window (8 tests)
python -m pytest tests/test_ai_config_persistence.py  # config save/load/endpoints (6 tests)
python -m pytest tests/test_structured_analysis.py    # structured JSON endpoint (5 tests)
```

## Conventions

- Commit style: imperative subject, body explains why, `Co-Authored-By` trailer
- No external state management — all frontend state in IIFE closure variables
- Backend analysis functions are pure: take `DependencyGraph` + `source_dir`, return dicts
- API endpoints: POST for analysis (takes `scan_id`), GET for previews/exports
- HTML uses Tailwind utility classes inline; `styles.css` only for custom components and theme tokens
