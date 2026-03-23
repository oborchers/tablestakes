# tablestakes

<!-- mcp-name: io.github.oborchers/tablestakes -->

MCP server for reading and editing HTML/Markdown tables in GitBook-synced documents.

## Overview

GitBook's bidirectional sync collapses complex tables into single-line HTML in Markdown files, making them unreadable for LLMs. tablestakes acts as a transparent intermediary: LLMs see clean pipe tables, files on disk stay in their original format.

Supports three table formats:
- **GFM pipe tables** (native Markdown)
- **GitBook collapsed HTML** (single-line `<table>` blocks with width/data-* attributes)
- **General HTML tables**

## Installation

```bash
uvx tablestakes
```

## Client Configuration

### Claude Code

Add to `.claude/settings.json`:

```json
{
  "mcpServers": {
    "tablestakes": {
      "command": "uvx",
      "args": ["tablestakes"]
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tablestakes": {
      "command": "uvx",
      "args": ["tablestakes"]
    }
  }
}
```

## Tools

### Discovery & Read

| Tool | Purpose |
|---|---|
| `list_tables(file_path, preview_rows=1)` | Scan file, return all tables with metadata + preview |
| `read_table(file_path, table_index)` | Full table in normalized format + version hash |

### Cell Operations

| Tool | Purpose |
|---|---|
| `update_cells(file_path, table_index, version, updates)` | Batch `{row, column, value}` patches |

### Row Operations

| Tool | Purpose |
|---|---|
| `insert_row(file_path, table_index, version, position, values)` | Insert row at position (-1 to append) |
| `delete_row(file_path, table_index, version, row_index)` | Remove row by index |

### Column Operations

| Tool | Purpose |
|---|---|
| `add_column(file_path, table_index, version, name, default_value, position)` | Add column |
| `delete_column(file_path, table_index, version, column)` | Remove column |
| `rename_column(file_path, table_index, version, old_name, new_name)` | Rename header |

### Full Table Operations

| Tool | Purpose |
|---|---|
| `replace_table(file_path, table_index, version, new_content)` | Full replacement from pipe table input |

## Column Addressing

Columns can be referenced by:
- **Letter**: `"A"`, `"B"`, `"AA"` (bijective base-26, like Excel)
- **Name**: `"Priority"` (must be unique)
- **Composite**: `"B:Priority"` (for disambiguation)
- **Index**: `"0"`, `"1"` (0-based)

## Concurrency Model

All write tools require a `version` hash from `read_table`. The server re-reads the file on every write, verifies the hash, and rejects stale writes with a `STALE_READ` error. No state is cached between calls.

## Development

```bash
uv sync --group dev
uv run pytest tests/ -x -v
uv run ruff check src tests
uv run mypy src
```

## License

Apache-2.0
