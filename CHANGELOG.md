# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added

- 10 MCP tools: `list_tables`, `read_table`, `update_cells`, `insert_row`, `delete_row`, `replace_table`, `create_table`, `insert_column`, `delete_column`, `rename_column`
- Table detection for GFM pipe tables, GitBook collapsed HTML, and general HTML tables
- Bidirectional HTML-to-pipe conversion with inline formatting support
- Optimistic concurrency via per-table content hashing (shifted-lines safety model)
- Composite column addressing: letter (A), name (Priority), composite (B:Priority)
- GitBook attribute preservation (width, data-*) through read/write round-trips
- Edge case handling: pipe escaping, empty separator rows, BOM, CRLF, headerless tables
- Pydantic validation on all tool inputs: `Field(ge=0)` on indices, `Literal` on format enum, `CellUpdate` model for batch updates, `Field(min_length=1)` on column names

### Changed

- Renamed `add_column` to `insert_column` for symmetry with `insert_row`
- Token efficiency benchmarks measured against Claude Code Read+Edit baseline (not straw-man)
- Experiment scripts moved to `scripts/` directory
