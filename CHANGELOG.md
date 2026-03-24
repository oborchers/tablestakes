# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [1.0.0] - 2026-03-24

### Added

- 10 MCP tools: `list_tables`, `read_table`, `update_cells`, `insert_row`, `delete_row`, `replace_table`, `create_table`, `insert_column`, `delete_column`, `rename_column`
- Table detection for GFM pipe tables, GitBook collapsed HTML, and general HTML tables
- Bidirectional HTML-to-pipe conversion with inline formatting support
- Optimistic concurrency via per-table content hashing (shifted-lines safety model)
- Composite column addressing: letter (A), name (Priority), composite (B:Priority)
- GitBook attribute preservation (width, data-*) through read/write round-trips
- Edge case handling: pipe escaping, empty separator rows, BOM, CRLF, headerless tables
- Pydantic validation on all tool inputs: `Field(ge=0)` on indices, `Literal` on format enum, `CellUpdate` model for batch updates, `Field(min_length=1)` on column names

### Fixed

- Pipe-table escape failures: `|`, `\`, and `\n` now escaped on all write operations
- GFM alignment markers (`:---`, `:---:`, `---:`) preserved through edits and replace/create
- Numeric column names (e.g. "2024") no longer shadowed by index interpretation
- `delete_column` on the last remaining column now returns an error instead of destroying the table
- UTF-8 BOM files no longer produce corrupted output on write
- `<table>` tags inside pipe table cells no longer create phantom table entries
- `create_table` at a position inside an existing table now returns an error instead of splitting it
- GitBook attributes (`width`, `data-type`, `data-hidden`) now follow column content on insert/delete/replace
- Editing header-less HTML tables no longer injects a synthetic `<thead>`
- `<img>`, `<del>`, `<sub>`, `<sup>` elements survive HTML table round-trips through edits

### Changed

- Renamed `add_column` to `insert_column` for symmetry with `insert_row`
- Token efficiency benchmarks measured against Claude Code Read+Edit baseline (not straw-man)
- Experiment scripts moved to `scripts/` directory
