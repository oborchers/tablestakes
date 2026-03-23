"""Write MCP tools: update_cells, insert_row, delete_row, replace_table.

All write operations use _safe_write which implements the shifted-lines
safety model: re-read file, re-detect tables, verify content hash, then apply.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TypeAlias

from tablestakes.converter import (
    html_to_rows,
    pipe_table_to_rows,
    resolve_column,
    rows_to_html,
    rows_to_pipe_table,
)
from tablestakes.hasher import compute_hash
from tablestakes.models import ColumnDescriptor, RawTable, TableFormat
from tablestakes.parser import detect_tables
from tablestakes.server import mcp

EditFn: TypeAlias = Callable[
    [RawTable, list[str], list[list[str]], list[ColumnDescriptor]],
    tuple[list[str], list[list[str]]],
]


def _safe_write(
    file_path: str,
    table_index: int,
    version: str,
    edit_fn: EditFn,
) -> str:
    """Core write pattern implementing the shifted-lines safety model.

    1. Re-read entire file from disk
    2. Re-detect ALL tables (fresh scan)
    3. Find table at requested index
    4. Compute current content hash
    5. Compare against client-provided version
    6. If match: parse → edit → serialize → replace → write
    7. If mismatch: return STALE_READ error

    Returns: `v:{new_hash}` on success, JSON error on failure.
    """
    path = Path(file_path)
    if not path.exists():
        return _error("FILE_NOT_FOUND", f"File not found: {file_path}")

    content = path.read_text(encoding="utf-8")
    tables = detect_tables(content)

    if table_index < 0 or table_index >= len(tables):
        return _error(
            "TABLE_NOT_FOUND",
            f"Index {table_index} out of range. File has {len(tables)} table(s).",
        )

    table = tables[table_index]
    current_version = compute_hash(table.raw_content)

    if current_version != version:
        return _error(
            "STALE_READ",
            "Table modified since last read. Call read_table again.",
            your_version=version,
            current_version=current_version,
        )

    # Parse current table into headers + rows
    headers, rows = _parse_table(table)

    # Build column descriptors for column resolution
    columns = [ColumnDescriptor.from_header(i, h) for i, h in enumerate(headers)]

    # Apply the edit
    try:
        new_headers, new_rows = edit_fn(table, headers, rows, columns)
    except ValueError as e:
        return _error("EDIT_ERROR", str(e))

    # Serialize back to original format
    new_raw = _serialize_table(table, new_headers, new_rows)

    # Replace in file and write
    new_content = content[: table.start_offset] + new_raw + content[table.end_offset :]
    path.write_text(new_content, encoding="utf-8")

    return f"v:{compute_hash(new_raw)}"


def _parse_table(table: RawTable) -> tuple[list[str], list[list[str]]]:
    """Parse a RawTable into headers and rows."""
    if table.format == TableFormat.PIPE:
        return pipe_table_to_rows(table.raw_content)
    if table.soup is not None:
        return html_to_rows(table.soup)
    return [], []


def _serialize_table(table: RawTable, headers: list[str], rows: list[list[str]]) -> str:
    """Serialize headers + rows back to the table's original format."""
    if table.format == TableFormat.PIPE:
        return rows_to_pipe_table(headers, rows)
    return rows_to_html(
        headers,
        rows,
        original_soup=table.soup,
        gitbook_attrs=table.gitbook_attrs,
    )


def _error(error_type: str, message: str, **extra: str) -> str:
    """Format an error response."""
    data: dict[str, str] = {"error": error_type, "message": message, **extra}
    return json.dumps(data)


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool(output_schema=None)
def update_cells(
    file_path: str,
    table_index: int,
    version: str,
    updates: list[dict[str, str | int]],
) -> str:
    """Batch update cells in a table.

    Each update is {row, column, value} where:
    - row: 0-based data row index
    - column: column letter (A), name (Priority), or composite (B:Priority)
    - value: new cell content (Markdown formatting supported)

    Requires version hash from read_table. Returns new version hash.

    Args:
        file_path: Path to the Markdown file.
        table_index: 0-based table index.
        version: Version hash from read_table.
        updates: List of {row: int, column: str, value: str} dicts.
    """

    def apply(
        table: RawTable,
        headers: list[str],
        rows: list[list[str]],
        columns: list[ColumnDescriptor],
    ) -> tuple[list[str], list[list[str]]]:
        for update in updates:
            row_idx = int(update["row"])
            col_ref = str(update["column"])
            value = str(update["value"])

            if row_idx < 0 or row_idx >= len(rows):
                msg = f"Row {row_idx} out of range (0-{len(rows) - 1})"
                raise ValueError(msg)

            col_idx = resolve_column(col_ref, columns)

            # Pad row if needed
            while len(rows[row_idx]) <= col_idx:
                rows[row_idx].append("")

            rows[row_idx][col_idx] = value

        return headers, rows

    return _safe_write(file_path, table_index, version, apply)


@mcp.tool(output_schema=None)
def insert_row(
    file_path: str,
    table_index: int,
    version: str,
    position: int,
    values: dict[str, str],
) -> str:
    """Insert a new row into a table.

    Returns new version hash (v:{hash}).

    Args:
        file_path: Path to the Markdown file.
        table_index: 0-based table index.
        version: Version hash from read_table.
        position: 0-based index where row is inserted. Use -1 to append.
        values: Dict mapping column identifiers to cell values.
    """

    def apply(
        table: RawTable,
        headers: list[str],
        rows: list[list[str]],
        columns: list[ColumnDescriptor],
    ) -> tuple[list[str], list[list[str]]]:
        new_row = [""] * len(headers)
        for col_ref, value in values.items():
            col_idx = resolve_column(col_ref, columns)
            new_row[col_idx] = value

        if position == -1 or position >= len(rows):
            rows.append(new_row)
        elif position < 0:
            msg = f"Position {position} invalid. Use -1 to append."
            raise ValueError(msg)
        else:
            rows.insert(position, new_row)

        return headers, rows

    return _safe_write(file_path, table_index, version, apply)


@mcp.tool(output_schema=None)
def delete_row(
    file_path: str,
    table_index: int,
    version: str,
    row_index: int,
) -> str:
    """Delete a row from a table.

    Returns new version hash (v:{hash}).

    Args:
        file_path: Path to the Markdown file.
        table_index: 0-based table index.
        version: Version hash from read_table.
        row_index: 0-based data row index to delete.
    """

    def apply(
        table: RawTable,
        headers: list[str],
        rows: list[list[str]],
        columns: list[ColumnDescriptor],
    ) -> tuple[list[str], list[list[str]]]:
        if row_index < 0 or row_index >= len(rows):
            msg = f"Row {row_index} out of range (0-{len(rows) - 1})"
            raise ValueError(msg)
        rows.pop(row_index)
        return headers, rows

    return _safe_write(file_path, table_index, version, apply)


@mcp.tool(output_schema=None)
def replace_table(
    file_path: str,
    table_index: int,
    version: str,
    new_content: str,
) -> str:
    """Replace an entire table with new content.

    Accepts a pipe table string. Writes back in the ORIGINAL format:
    pipe stays pipe, GitBook HTML stays GitBook HTML (with cached attributes).

    Returns new version hash (v:{hash}).

    Args:
        file_path: Path to the Markdown file.
        table_index: 0-based table index.
        version: Version hash from read_table.
        new_content: New table content as a pipe table string.
    """

    def apply(
        table: RawTable,
        headers: list[str],
        rows: list[list[str]],
        columns: list[ColumnDescriptor],
    ) -> tuple[list[str], list[list[str]]]:
        new_headers, new_rows = pipe_table_to_rows(new_content)
        if not new_headers:
            msg = "Could not parse new_content as a pipe table."
            raise ValueError(msg)
        return new_headers, new_rows

    return _safe_write(file_path, table_index, version, apply)
