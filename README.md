# code-extract

Extract, clean, and export code blocks from any codebase as standalone modules.

## Install

```bash
# Base install (CLI only, regex scanners for JS/Dart/Python)
pip install -e .

# With tree-sitter (12+ languages, AST-accurate parsing)
pip install -e ".[treesitter]"

# With web UI
pip install -e ".[web]"

# Everything
pip install -e ".[all]"
```

## Usage

### Scan a codebase

```bash
code-extract scan                         # scan current directory
code-extract scan ./my-project
code-extract scan ./my-project --language rust
code-extract scan ./my-project --type widget
code-extract scan ./my-project --type table   # find SQL tables
```

### Extract specific items

```bash
# Extract by name
code-extract extract ./my-project MyWidget -o ./extracted

# Extract by pattern
code-extract extract ./my-project --pattern "*.Widget" -o ./extracted

# Extract everything
code-extract extract ./my-project --all -o ./extracted
```

### Web UI

```bash
code-extract serve                  # opens http://localhost:8420
code-extract serve --port 9000      # custom port
code-extract serve --no-open        # don't auto-open browser
```

The web dashboard lets you:
- Scan any project directory with path autocomplete
- Browse results grouped by file, filterable by language/type
- Click any item to see syntax-highlighted source code
- Select items and extract them as a downloadable zip
- Real-time progress via WebSocket

### v0.3 Analysis Tabs

The web UI includes 8 tabs:

| Tab | What it does |
|-----|-------------|
| **Scan** | Scan projects, browse/filter/preview items, extract to zip |
| **Catalog** | Card grid of all components with parameters, language badges, code previews |
| **Architecture** | Interactive Cytoscape.js dependency graph with node sizing, edge weighting, search, module zoom |
| **Health** | Long functions, code duplication detection, coupling scores, overall health score |
| **Docs** | Auto-generated documentation from AST data, Watch Mode for live updates, markdown export |
| **Compare** | Semantic diff between two codebases — added/removed/modified items |
| **Dead Code** | Detect unused code with confidence scoring and entry-point heuristics |
| **Tour** | Step-by-step codebase walkthrough from entry points through dependency chains |

### Smart Tools

- **Smart Extract** — Extract items with all transitive dependencies resolved
- **Package Factory** — Generate ready-to-publish packages with language-appropriate manifests
- **Pattern Cloner** — Clone code patterns with intelligent case-variant name replacement
- **Boilerplate Generator** — Detect repeated patterns and generate reusable templates
- **Migration Mapper** — Detect and apply migration patterns (React class→hooks, Flutter StatefulWidget→Riverpod, etc.)

## Output Structure

```
extracted/
├── README.md
├── manifest.json
├── requirements.txt / package.json / pubspec.yaml
├── python/
│   ├── __init__.py
│   └── my_class.py
├── javascript/
│   ├── index.js
│   └── my_component.js
├── dart/
│   ├── index.dart
│   └── my_widget.dart
├── rust/
│   ├── mod.rs
│   └── my_struct.rs
├── sql/
│   ├── index.sql
│   └── users.sql
└── ...
```

## Supported Languages

| Language | Scanner | Extractor | Install |
|----------|---------|-----------|---------|
| Python | AST (`ast` stdlib) | AST-based | base |
| JavaScript/TypeScript | tree-sitter or regex | tree-sitter or brace-match | base (regex) / `[treesitter]` |
| Dart/Flutter | tree-sitter or regex | tree-sitter or brace-match | base (regex) / `[treesitter]` |
| Rust | tree-sitter | tree-sitter | `[treesitter]` |
| Go | tree-sitter | tree-sitter | `[treesitter]` |
| Java | tree-sitter | tree-sitter | `[treesitter]` |
| C/C++ | tree-sitter | tree-sitter | `[treesitter]` |
| Ruby | tree-sitter | tree-sitter | `[treesitter]` |
| Swift | tree-sitter | tree-sitter | `[treesitter]` |
| Kotlin | tree-sitter | tree-sitter | `[treesitter]` |
| C# | tree-sitter | tree-sitter | `[treesitter]` |
| SQL | regex | statement-based | base |

### SQL & Database Schema

code-extract scans `.sql` files for:
- `CREATE TABLE`, `CREATE VIEW`, `CREATE FUNCTION`
- PostgreSQL triggers, indexes, policies (Supabase RLS)
- Supabase migration files (auto-detected from path)

It also detects ORM models in code:
- SQLAlchemy / Django models (Python)
- TypeORM entities (TypeScript)
- Prisma models (`.prisma` files)

## Pipeline Stages

1. **Scanner** — Find extractable items (functions, classes, components, widgets, tables, etc.)
2. **Extractor** — Extract source code with imports and context
3. **Cleaner** — Remove unused imports, strip metadata, sanitize relative imports
4. **Formatter** — Format code and validate syntax
5. **Exporter** — Write files, generate README, manifest, and dependency configs
