# tablestakes

[![PyPI version](https://img.shields.io/pypi/v/tablestakes.svg)](https://pypi.org/project/tablestakes/)
[![Python versions](https://img.shields.io/pypi/pyversions/tablestakes.svg)](https://pypi.org/project/tablestakes/)
[![CI](https://github.com/oborchers/tablestakes/actions/workflows/ci.yml/badge.svg)](https://github.com/oborchers/tablestakes/actions/workflows/ci.yml)
[![License](https://img.shields.io/pypi/l/tablestakes.svg)](https://github.com/oborchers/tablestakes/blob/main/LICENSE)

An MCP server that gives LLMs clean, surgical access to tables trapped in messy HTML.

## The Problem

Tools like GitBook, Notion exports, and CMS platforms collapse tables into single-line HTML when syncing to Markdown files. The result looks like this in your editor:

```
<table><thead><tr><th width="520.11">Requirement</th><th width="122.07">Priority</th><th>Priority 1-2-3</th></tr></thead><tbody><tr><td><strong>1.1</strong> Agent sees only their Salesforce-assigned cases <strong>in the currently selected organization</strong> (case is "assigned" when SF <code>Case.OwnerId</code> matches the agent's linked SF user ID)...</td><td>Must</td><td>1</td></tr></tbody></table>
```

This is unreadable for humans and unreliable for LLMs. Models struggle to parse collapsed HTML tables, frequently hallucinate cell boundaries, and cannot edit them without corrupting the structure.

**tablestakes fixes this.** It sits between the LLM and the file, converting tables to clean pipe format on read and writing back in the original format on save — preserving GitBook compatibility, HTML attributes, and inline formatting.

## What the LLM Sees

**Discovery** — scan a 26-table document in one call:

```
26 tables

T0 pipe 5r 3c v:485f65f7b470 [Cross-Domain Dependencies]
  A:Integration | B:Source | C:Requirements

T2 gitbook 18r 3c v:77a9495fd328 [Case List]
  A:Requirement | B:Priority | C:Priority 1-2-3

T7 gitbook 3r 4c v:d9a9a45a370f [Attachments]
  A:Requirement | B:Priority | C:Dependency | D:Priority 1-2-3
```

**Read** — collapsed HTML becomes a clean pipe table:

```
v:d9a9a45a370f gitbook 3r 4c [Attachments]
A:Requirement | B:Priority | C:Dependency | D:Priority 1-2-3
| Requirement | Priority | Dependency | Priority 1-2-3 |
| --- | --- | --- | --- |
| **5.1** View inbound attachments in-app... | Must | — | 1 |
| **5.2** Send outbound attachments... | Must | Blocked on SF API | 1 |
| **5.3** Attachment file size limits... | Should | — |  |
```

**Write** — surgical cell edit, version-checked:

```
v:5749c94ffb1f
```

14 characters. The file is updated, GitBook HTML format preserved, `width` attributes intact.

## Token Efficiency

Output is optimized for LLM context windows. Measured against a real 26-table GitBook PRD:

| Operation | Output size |
|---|---|
| `list_tables` (26 tables) | ~2,600 tokens |
| `read_table` (18-row table) | ~1,500 tokens |
| Any write operation | ~4 tokens |
| **10-edit workflow** | **~1,550 tokens total** |

Write tools return only the new version hash (`v:{hash}`). No full table echo — the LLM already has the table from `read_table`. This cuts a 10-edit workflow from ~16,500 tokens (if tables were echoed) to ~1,550 tokens.

Pipe tables use compact formatting (no column padding). Per the [ImprovingAgents benchmark](https://improvingagents.com), GFM pipe tables achieve the best token-to-accuracy ratio: 1.24x CSV tokens at 51.9% QA accuracy, beating JSON (2.08x, 52.3%) and YAML (1.88x, 54.7%).

## Quick Start

**Claude Code:**

```bash
claude mcp add tablestakes -- uvx tablestakes
```

**Codex CLI:**

```bash
codex mcp add tablestakes -- uvx tablestakes
```

**Gemini CLI:**

```bash
gemini mcp add tablestakes -- uvx tablestakes
```

Or install from PyPI directly: `pip install tablestakes`

<details>
<summary><strong>Other clients (Cursor, Windsurf, Claude Desktop)</strong></summary>

Add the following JSON to your client's MCP config file:

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

| Client | Config file |
|---|---|
| Cursor | `.cursor/mcp.json` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` |
| Claude Desktop | `claude_desktop_config.json` |

</details>

## Tools

### Discovery & Read

| Tool | Purpose |
|---|---|
| `list_tables(file_path, preview_rows=1)` | Scan file, return all tables with metadata + preview |
| `read_table(file_path, table_index)` | Full table normalized to pipe format + version hash |

### Cell, Row & Column Operations

| Tool | Purpose |
|---|---|
| `update_cells(file_path, table_index, version, updates)` | Batch `{row, column, value}` patches |
| `insert_row(file_path, table_index, version, position, values)` | Insert row at position (-1 to append) |
| `delete_row(file_path, table_index, version, row_index)` | Remove row by index |
| `add_column(file_path, table_index, version, name, ...)` | Add column with default value |
| `delete_column(file_path, table_index, version, column)` | Remove column |
| `rename_column(file_path, table_index, version, old_name, new_name)` | Rename header |
| `replace_table(file_path, table_index, version, new_content)` | Full table replacement from pipe input |

All write tools require a `version` hash from `read_table` — optimistic concurrency that prevents stale overwrites without locks.

## Supported Table Formats

| Format | Read | Write | Round-trip |
|---|---|---|---|
| GFM pipe tables | Pass-through | In-place edit | Lossless |
| GitBook collapsed HTML | HTML → pipe | Pipe → collapsed HTML | Preserves `width`, `data-*`, inline formatting |
| General HTML tables | HTML → pipe or pretty HTML | Reconstructs HTML | Preserves structure |

While GitBook is the primary motivation, tablestakes works with any Markdown document containing HTML tables — CMS exports, Notion dumps, wiki migrations, or hand-written HTML in `.md` files.

## Column Addressing

Columns can be referenced by:
- **Letter**: `"A"`, `"B"`, `"AA"` (bijective base-26, like Excel)
- **Name**: `"Priority"` (must be unique)
- **Composite**: `"B:Priority"` (for disambiguation)
- **Index**: `"0"`, `"1"` (0-based)

## Development

```bash
make init      # First-time setup: venv + deps + pre-commit hooks
make check     # All checks: format + lint + typecheck + test
make test      # Run tests only
make test-cov  # Tests with coverage report
```

## License

Apache-2.0

---

mcp-name: io.github.oborchers/tablestakes
