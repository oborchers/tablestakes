# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

tablestakes is an MCP server that reads and edits HTML/Markdown tables in GitBook-synced documents. LLMs see clean pipe tables; files on disk stay in their original format (collapsed single-line HTML for GitBook, pipe tables for native Markdown). Published on PyPI (`uvx tablestakes`) and the MCP Registry (`io.github.oborchers/tablestakes`).

## Commands

```bash
make init          # First-time setup: venv + deps + pre-commit hooks
make check         # Run all checks: format-check + lint + typecheck + test
make format        # Auto-format with ruff
make test          # Run tests
make test-cov      # Tests with coverage report
make typecheck     # mypy strict mode
make build         # Build wheel (runs clean first)
```

Single test: `uv run pytest tests/test_parser.py::TestDetectTables::test_mixed_document_table_count -v`

Dev server with hot-reload: `uv run fastmcp dev`

List registered tools: `uv run fastmcp list`

## Architecture

### Four Layers

1. **Parser** (`parser.py`) — `detect_tables(content)` scans Markdown, returns `list[RawTable]` with byte offsets, classification, and cached BeautifulSoup Tags. Detection precedence: fenced code blocks (excluded) → HTML comments (excluded) → `<table>` blocks → GFM pipe tables.

2. **Converter** (`converter.py`) — Bidirectional HTML↔pipe. Read path: `html_to_rows()` uses `markdownify` per-cell for inline tags (`<strong>`→`**`). Write path: `rows_to_html()` clones the original AST to preserve GitBook attributes (`width=`, `data-*`), falls back to fresh HTML build on structural changes.

3. **Hasher** (`hasher.py`) — `compute_hash()` returns SHA-256 truncated to 12 hex chars. Used for optimistic concurrency version tokens.

4. **Tools** (`tools/read.py`, `tools/write.py`, `tools/column.py`) — 9 MCP tools registered via `@mcp.tool(output_schema=None)` decorators.

### The Shifted-Lines Safety Model

Every write tool calls `_safe_write()` in `tools/write.py`. This is the single write path — no exceptions. The invariant:

1. Re-read entire file from disk (never cached content)
2. Re-detect all tables (fresh scan)
3. Compute current hash of table at requested index
4. Compare against client-provided version hash
5. Match → apply edit → write. Mismatch → `STALE_READ` error.

No byte offsets or table positions are cached between tool calls. This means shifted lines (text inserted above a table) don't break writes — the hash is per-table content, not per-position.

### Tool Registration

`server.py` creates the `FastMCP` instance, then imports tool modules as side effects to trigger `@mcp.tool` registration. This requires `# noqa: F401, E402` suppressions — it's the standard FastMCP pattern, not a smell.

### Output Format Conventions

- Read tools return plain text, not JSON. Metadata line: `v:{hash} {format} {rows}r {cols}c [{heading}]`
- Write tools return only `v:{new_hash}` (14 chars). No full table in output — the LLM calls `read_table` if it needs to see the result.
- Error responses are JSON: `{"error": "STALE_READ", "message": "...", ...}`
- `output_schema=None` on all tools suppresses FastMCP's `structuredContent` wrapper.

### Table Classification

HTML tables are classified as:
- **simple** — no colspan/rowspan/data-* → presented as pipe table
- **gitbook** — has `width=` or `data-view`/`data-hidden`/`data-type` → presented as pipe table, attributes cached in `RawTable.gitbook_attrs` for write-back
- **complex** — has colspan/rowspan/nested tables → presented as pretty HTML

### Test Helpers

Shared helpers live in `tests/conftest.py`: `text_of()`, `version_of()`, `read_version()`, `parse_html_table()`, `VERSION_RE`. Do not duplicate these in test files.

## Release Flow

Versioning is automatic via `hatch-vcs` (git tags → `_version.py`). To release:

1. Update `CHANGELOG.md` — move `[Unreleased]` items to `[X.Y.Z] - YYYY-MM-DD`
2. Update `server.json` — set `version` and `packages[0].version` to the new version
3. Commit and push
4. Tag: `git tag vX.Y.Z -m "vX.Y.Z: description"`
5. Push tag: `git push origin vX.Y.Z`
6. Create GitHub Release from the tag

The release workflow (`release.yml`) handles everything automatically:
- Runs full CI (lint, typecheck, test matrix)
- Builds wheel and publishes to PyPI (OIDC trusted publishing, no tokens)
- Publishes to MCP Registry (OIDC via `mcp-publisher login github-oidc`)

The `server.json` version must match the git tag version — both PyPI and the MCP Registry validate this.

## GitHub Account

The repo is owned by `oborchers`. If git push fails with 403, check: `gh auth status` — switch with `gh auth switch --user oborchers`.
