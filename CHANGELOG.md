# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added

- 9 MCP tools: `list_tables`, `read_table`, `update_cells`, `insert_row`, `delete_row`, `replace_table`, `add_column`, `delete_column`, `rename_column`
- Table detection for GFM pipe tables, GitBook collapsed HTML, and general HTML tables
- Bidirectional HTML-to-pipe conversion with inline formatting support
- Optimistic concurrency via per-table content hashing (shifted-lines safety model)
- Composite column addressing: letter (A), name (Priority), composite (B:Priority)
- GitBook attribute preservation (width, data-*) through read/write round-trips
- Edge case handling: pipe escaping, empty separator rows, BOM, CRLF, headerless tables
