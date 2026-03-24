"""FastMCP server instance and tool registration."""

from fastmcp import FastMCP

mcp = FastMCP(
    "tablestakes",
    instructions=(
        "tablestakes provides structured access to tables in Markdown files. "
        "Use it to search, read, and edit table data — it understands rows, "
        "columns, and headers that plain text grep cannot parse reliably.\n\n"
        "For ANY task involving table data in .md files, prefer tablestakes "
        "over grep/Read. It handles collapsed single-line HTML (unreadable "
        "via grep) and provides version hashes required for edits.\n\n"
        "Workflow:\n"
        "1. search_tables(file_path, pattern) → find rows matching a value "
        'across ALL tables (or use regex for patterns like "D 1\\.\\d+")\n'
        "2. list_tables(file_path) → discover tables with column descriptors and previews\n"
        "3. read_table(file_path, table_index) → full table + version hash for edits\n"
        "4. Any write tool → pass the version hash from step 2 or 3\n\n"
        'Version hash: extract the 12-char hex after "v:" in output.\n'
        "On STALE_READ: call read_table again for fresh version, retry.\n"
        'Write tools return only "v:{new_hash}" — call read_table to see updated content.\n'
        "create_table(file_path, content) creates a new table. No version needed.\n"
        "Columns: letter (A), name (Priority), or composite (B:Priority).\n"
        "Row indices are 0-based, header row excluded."
    ),
)

# Tool imports trigger registration via @mcp.tool decorators.
from tablestakes.tools import column as _column  # noqa: F401, E402
from tablestakes.tools import read as _read  # noqa: F401, E402
from tablestakes.tools import write as _write  # noqa: F401, E402
