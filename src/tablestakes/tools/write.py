"""Write MCP tools: update_cells, insert_row, delete_row, replace_table, create_table.

All write operations use _safe_write which implements the shifted-lines
safety model: re-read file, re-detect tables, verify content hash, then apply.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal, TypeAlias

from pydantic import Field

from tablestakes.converter import (
    html_to_rows,
    parse_alignment,
    pipe_table_to_rows,
    resolve_column,
    rows_to_html,
    rows_to_pipe_table,
)
from tablestakes.hasher import compute_hash
from tablestakes.models import CellUpdate, ColumnDescriptor, RawTable, TableFormat
from tablestakes.parser import detect_tables
from tablestakes.server import mcp

EditFn: TypeAlias = Callable[
    [RawTable, list[str], list[list[str]], list[ColumnDescriptor]],
    tuple[list[str], list[list[str]]],
]


def _strip_bom(content: str) -> tuple[str, str]:
    """Strip UTF-8 BOM if present, returning (stripped_content, bom_prefix)."""
    if content.startswith("\ufeff"):
        return content[1:], "\ufeff"
    return content, ""


def _atomic_write(path: Path, content: str) -> None:
    """Write content to file atomically via temp file + rename."""
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(content)
        Path(tmp_path).replace(path)
    except BaseException:
        Path(tmp_path).unlink()
        raise


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
    6. If match: parse → edit → serialize → replace → atomic write
    7. If mismatch: return STALE_READ error

    Returns: `v:{new_hash}` on success, JSON error on failure.
    """
    path = Path(file_path)
    if not path.exists():
        return _error("FILE_NOT_FOUND", f"File not found: {file_path}")

    raw_content = path.read_text(encoding="utf-8")
    content, bom = _strip_bom(raw_content)
    tables = detect_tables(content)

    if table_index >= len(tables):
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
    original_headers = list(headers)

    # Build column descriptors for column resolution
    columns = [ColumnDescriptor.from_header(i, h) for i, h in enumerate(headers)]

    # Apply the edit
    try:
        new_headers, new_rows = edit_fn(table, headers, rows, columns)
    except ValueError as e:
        return _error("EDIT_ERROR", str(e))

    # Serialize back to original format
    new_raw = _serialize_table(table, new_headers, new_rows, original_headers)

    # Replace in file and write atomically (preserve BOM if present)
    new_content = bom + content[: table.start_offset] + new_raw + content[table.end_offset :]
    _atomic_write(path, new_content)

    return f"v:{compute_hash(new_raw)}"


def _parse_table(table: RawTable) -> tuple[list[str], list[list[str]]]:
    """Parse a RawTable into headers and rows."""
    if table.format == TableFormat.PIPE:
        return pipe_table_to_rows(table.raw_content)
    if table.soup is not None:
        return html_to_rows(table.soup)
    return [], []


def _serialize_table(
    table: RawTable,
    headers: list[str],
    rows: list[list[str]],
    original_headers: list[str] | None = None,
) -> str:
    """Serialize headers + rows back to the table's original format."""
    if table.format == TableFormat.PIPE:
        alignments = parse_alignment(table.raw_content)
        return rows_to_pipe_table(headers, rows, alignments=alignments)
    return rows_to_html(
        headers,
        rows,
        original_soup=table.soup,
        gitbook_attrs=table.gitbook_attrs,
        original_headers=original_headers,
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
    table_index: Annotated[int, Field(ge=0)],
    version: str,
    updates: list[CellUpdate],
) -> str:
    """Batch-update cells. Requires version hash from read_table.

    Each update is {row, column, value} where:
    - row: 0-based data row index (header row is NOT counted)
    - column: letter ("A"), name ("Priority"), or composite ("B:Priority")
    - value: new cell content (Markdown inline formatting supported)

    On success returns ONLY `v:{new_hash}`.
    On error returns JSON: {"error": "STALE_READ"|"EDIT_ERROR"|..., "message": "..."}.
    If STALE_READ: call read_table again for current version, then retry.

    Args:
        file_path: Absolute path to the Markdown file.
        table_index: 0-based table index from list_tables.
        version: 12-char hex hash from read_table (after "v:", e.g. "a1b2c3d4e5f6").
        updates: List of {row: int, column: str, value: str} objects.
    """

    def apply(
        table: RawTable,
        headers: list[str],
        rows: list[list[str]],
        columns: list[ColumnDescriptor],
    ) -> tuple[list[str], list[list[str]]]:
        for update in updates:
            if update.row >= len(rows):
                msg = f"Row {update.row} out of range (0-{max(0, len(rows) - 1)})"
                raise ValueError(msg)

            col_idx = resolve_column(update.column, columns)

            # Pad row if needed
            while len(rows[update.row]) <= col_idx:
                rows[update.row].append("")

            rows[update.row][col_idx] = update.value

        return headers, rows

    return _safe_write(file_path, table_index, version, apply)


@mcp.tool(output_schema=None)
def insert_row(
    file_path: str,
    table_index: Annotated[int, Field(ge=0)],
    version: str,
    position: Annotated[int, Field(ge=-1)],
    values: dict[str, str],
) -> str:
    """Insert a new row. Requires version hash from read_table.

    Provide values as a dict mapping column identifiers to cell content.
    Column identifiers: letter ("A"), name ("Priority"), or composite ("B:Priority").
    Omitted columns default to empty string.

    On success returns ONLY `v:{new_hash}`.
    On error returns JSON with "error" and "message" fields.

    Args:
        file_path: Absolute path to the Markdown file.
        table_index: 0-based table index from list_tables.
        version: 12-char hex hash from read_table (after "v:").
        position: 0-based row index for insertion. Use -1 to append at the end.
        values: Dict mapping column identifiers to cell values.
            Example: {"Name": "Alice", "B": "30", "C:City": "NYC"}
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
        else:
            rows.insert(position, new_row)

        return headers, rows

    return _safe_write(file_path, table_index, version, apply)


@mcp.tool(output_schema=None)
def delete_row(
    file_path: str,
    table_index: Annotated[int, Field(ge=0)],
    version: str,
    row_index: Annotated[int, Field(ge=0)],
) -> str:
    """Delete a row. Requires version hash from read_table.

    On success returns ONLY `v:{new_hash}`.
    On error returns JSON with "error" and "message" fields.

    Args:
        file_path: Absolute path to the Markdown file.
        table_index: 0-based table index from list_tables.
        version: 12-char hex hash from read_table (after "v:").
        row_index: 0-based data row index to delete (header row is NOT counted).
    """

    def apply(
        table: RawTable,
        headers: list[str],
        rows: list[list[str]],
        columns: list[ColumnDescriptor],
    ) -> tuple[list[str], list[list[str]]]:
        if row_index >= len(rows):
            msg = f"Row {row_index} out of range (0-{max(0, len(rows) - 1)})"
            raise ValueError(msg)
        rows.pop(row_index)
        return headers, rows

    return _safe_write(file_path, table_index, version, apply)


@mcp.tool(output_schema=None)
def replace_table(
    file_path: str,
    table_index: Annotated[int, Field(ge=0)],
    version: str,
    new_content: str,
) -> str:
    """Replace an entire table with new content. Requires version from read_table.

    Provide new_content as a pipe table string (header row + delimiter + data rows).
    The server writes back in the ORIGINAL file format: pipe stays pipe,
    GitBook HTML stays GitBook HTML (attributes preserved).

    On success returns ONLY `v:{new_hash}`.
    On error returns JSON with "error" and "message" fields.

    Args:
        file_path: Absolute path to the Markdown file.
        table_index: 0-based table index from list_tables.
        version: 12-char hex hash from read_table (after "v:").
        new_content: Full pipe table string including header and delimiter rows.
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
        # Carry alignment markers from new_content into the serialization path
        if table.format == TableFormat.PIPE:
            table.raw_content = new_content
        return new_headers, new_rows

    return _safe_write(file_path, table_index, version, apply)


@mcp.tool(output_schema=None)
def create_table(
    file_path: str,
    content: str,
    position: Annotated[int, Field(ge=-1)] = -1,
    format: Literal["html", "pipe"] = "html",
) -> str:
    """Create a new table in a Markdown file. Provide content as a pipe table.

    The table is written in the specified format: "html" (default, collapsed
    single-line HTML suitable for GitBook) or "pipe" (GFM pipe table).

    No version hash needed — this creates, not edits.

    On success returns `v:{hash}` of the new table. Use this hash with
    read_table and write tools to edit the table immediately.
    On error returns JSON with "error" and "message" fields.

    Args:
        file_path: Absolute path to the Markdown file. Created if it doesn't exist.
        content: Table in pipe format (header row + delimiter + data rows).
            Example: "| Name | Age |\\n| --- | --- |\\n| Alice | 30 |"
        position: 1-based line number to insert AFTER. -1 appends (default). 0 inserts at top.
        format: "html" (default) or "pipe". HTML produces collapsed single-line
            GitBook-compatible output. GitBook will auto-add width/data-* attributes on sync.
    """
    headers, rows = pipe_table_to_rows(content)
    if not headers:
        return _error("INVALID_CONTENT", "Could not parse content as a pipe table.")

    if format == "html":
        raw = rows_to_html(headers, rows, original_soup=None, gitbook_attrs=None)
    else:
        alignments = parse_alignment(content)
        raw = rows_to_pipe_table(headers, rows, alignments=alignments)

    path = Path(file_path)
    raw_existing = path.read_text(encoding="utf-8") if path.exists() else ""
    existing, bom = _strip_bom(raw_existing)

    if position == -1 or not existing:
        separator = (
            "\n\n"
            if existing and not existing.endswith("\n\n")
            else ("\n" if existing and not existing.endswith("\n") else "")
        )
        new_file = existing + separator + raw + "\n"
    elif position == 0:
        new_file = raw + "\n\n" + existing
    else:
        lines = existing.split("\n")
        if position > len(lines):
            position = len(lines)

        # Reject positions that fall inside an existing table
        insert_offset = sum(len(lines[i]) + 1 for i in range(position))
        for t in detect_tables(existing):
            if t.start_offset < insert_offset < t.end_offset:
                end_line = t.source_line + t.raw_content.count("\n")
                return _error(
                    "POSITION_INSIDE_TABLE",
                    f"Position {position} falls inside table T{t.index} "
                    f"(lines {t.source_line}-{end_line}). "
                    f"Use a position before or after the table.",
                )

        before = "\n".join(lines[:position])
        after = "\n".join(lines[position:])
        new_file = before + "\n\n" + raw + "\n\n" + after

    _atomic_write(path, bom + new_file)

    return f"v:{compute_hash(raw)}"
