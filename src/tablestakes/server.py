"""FastMCP server instance and tool registration."""

from fastmcp import FastMCP

mcp = FastMCP(
    "tablestakes",
    instructions="""\
tablestakes reads and edits tables in Markdown files (pipe tables and HTML tables).

Workflow:
1. list_tables(file_path) → discover tables, note table_index values
2. read_table(file_path, table_index) → full table + version hash
3. Any write tool → pass the version hash from step 2

Version hash: extract the 12-char hex string after "v:" in read_table output.
Example: if output starts with "v:a1b2c3d4e5f6", pass "a1b2c3d4e5f6" as version.

On STALE_READ error: table was modified since your read. Call read_table again, \
get fresh version, retry.
Write tools return only "v:{new_hash}" on success — call read_table to see \
updated content.
Columns: use letter (A), name (Priority), or composite (B:Priority).
Row indices are 0-based, header row excluded.
""",
)

# Tool imports trigger registration via @mcp.tool decorators.
from tablestakes.tools import column as _column  # noqa: F401, E402
from tablestakes.tools import read as _read  # noqa: F401, E402
from tablestakes.tools import write as _write  # noqa: F401, E402
