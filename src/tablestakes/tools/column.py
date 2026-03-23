"""Column MCP tools: add_column, delete_column, rename_column.

All use _safe_write from write.py for the shifted-lines safety model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tablestakes.converter import resolve_column
from tablestakes.server import mcp
from tablestakes.tools.write import _safe_write

if TYPE_CHECKING:
    from tablestakes.models import ColumnDescriptor, RawTable


@mcp.tool(output_schema=None)
def add_column(
    file_path: str,
    table_index: int,
    version: str,
    name: str,
    default_value: str = "",
    position: int = -1,
) -> str:
    """Add a new column. Requires version hash from read_table.

    All existing rows are populated with default_value (empty string if omitted).

    On success returns ONLY `v:{new_hash}`.
    On error returns JSON with "error" and "message" fields.

    Args:
        file_path: Absolute path to the Markdown file.
        table_index: 0-based table index from list_tables.
        version: 12-char hex hash from read_table (after "v:").
        name: Header text for the new column.
        default_value: Value for all existing rows (default: empty string).
        position: 0-based column index for insertion. -1 appends to the right (default).
    """

    def apply(
        table: RawTable,
        headers: list[str],
        rows: list[list[str]],
        columns: list[ColumnDescriptor],
    ) -> tuple[list[str], list[list[str]]]:
        col_count = len(headers)

        if position == -1 or position >= col_count:
            insert_at = col_count
        elif position < 0:
            msg = f"Position {position} invalid. Use -1 to append."
            raise ValueError(msg)
        else:
            insert_at = position

        headers.insert(insert_at, name)
        for row in rows:
            # Pad row if shorter than current column count
            while len(row) < col_count:
                row.append("")
            row.insert(insert_at, default_value)

        return headers, rows

    return _safe_write(file_path, table_index, version, apply)


@mcp.tool(output_schema=None)
def delete_column(
    file_path: str,
    table_index: int,
    version: str,
    column: str,
) -> str:
    """Delete a column. Requires version hash from read_table.

    On success returns ONLY `v:{new_hash}`.
    On error returns JSON with "error" and "message" fields.

    Args:
        file_path: Absolute path to the Markdown file.
        table_index: 0-based table index from list_tables.
        version: 12-char hex hash from read_table (after "v:").
        column: Column letter ("A"), name ("Priority"), or composite ("B:Priority").
    """

    def apply(
        table: RawTable,
        headers: list[str],
        rows: list[list[str]],
        columns: list[ColumnDescriptor],
    ) -> tuple[list[str], list[list[str]]]:
        col_idx = resolve_column(column, columns)
        headers.pop(col_idx)
        for row in rows:
            if col_idx < len(row):
                row.pop(col_idx)
        return headers, rows

    return _safe_write(file_path, table_index, version, apply)


@mcp.tool(output_schema=None)
def rename_column(
    file_path: str,
    table_index: int,
    version: str,
    old_name: str,
    new_name: str,
) -> str:
    """Rename a column header. Row data is unchanged. Requires version from read_table.

    On success returns ONLY `v:{new_hash}`.
    On error returns JSON with "error" and "message" fields.

    Args:
        file_path: Absolute path to the Markdown file.
        table_index: 0-based table index from list_tables.
        version: 12-char hex hash from read_table (after "v:").
        old_name: Current column identifier: letter ("A"), name, or composite ("B:Priority").
        new_name: New header text for the column.
    """

    def apply(
        table: RawTable,
        headers: list[str],
        rows: list[list[str]],
        columns: list[ColumnDescriptor],
    ) -> tuple[list[str], list[list[str]]]:
        col_idx = resolve_column(old_name, columns)
        headers[col_idx] = new_name
        return headers, rows

    return _safe_write(file_path, table_index, version, apply)
