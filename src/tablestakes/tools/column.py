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
    """Add a new column to a table.

    Returns new version hash (v:{hash}).

    Args:
        file_path: Path to the Markdown file.
        table_index: 0-based table index.
        version: Version hash from read_table.
        name: Header text for the new column.
        default_value: Value for all existing rows (default empty).
        position: 0-based column index. -1 appends to the right.
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
    """Delete a column from a table.

    Returns new version hash (v:{hash}).

    Args:
        file_path: Path to the Markdown file.
        table_index: 0-based table index.
        version: Version hash from read_table.
        column: Column letter (A), name (Priority), or composite (B:Priority).
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
    """Rename a column header. Data in the column is unchanged.

    Returns updated column descriptors and new version.

    Args:
        file_path: Path to the Markdown file.
        table_index: 0-based table index.
        version: Version hash from read_table.
        old_name: Current column name (letter, name, or composite).
        new_name: New header text.
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
