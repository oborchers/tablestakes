"""Read-only MCP tools: list_tables, read_table, search_tables."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from pydantic import Field

from tablestakes.converter import (
    html_to_rows,
    pipe_table_to_rows,
    pretty_print_html,
    resolve_column,
    rows_to_pipe_table,
)
from tablestakes.hasher import compute_hash
from tablestakes.models import ColumnDescriptor, RawTable, TableComplexity, TableFormat
from tablestakes.parser import detect_tables
from tablestakes.server import mcp


@mcp.tool(output_schema=None)
def list_tables(file_path: str, preview_rows: Annotated[int, Field(ge=0)] = 1) -> str:
    """List all tables in a Markdown file with column descriptors and row previews.

    Prefer this over grep for discovering table structure — returns column
    names, row counts, formats, and version hashes.  Use search_tables to
    find specific data across tables.

    Output format per table:
      T{index} {format} {rows}r {cols}c v:{hash} [{section heading}]
      {column descriptors as A:Name | B:Age | ...}
      row0: {first row cell values}

    Use table_index (the number after T) with read_table and write tools.

    Args:
        file_path: Absolute path to the Markdown file.
        preview_rows: Number of data rows to preview (default 1, 0 for none).
    """
    path = Path(file_path)
    if not path.exists():
        return f"File not found: {file_path}"

    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        return f"Cannot read file: {e}"

    tables = detect_tables(content)

    if not tables:
        return "No tables found."

    parts: list[str] = [f"{len(tables)} tables\n"]

    for table in tables:
        version = compute_hash(table.raw_content)

        if table.format == TableFormat.PIPE:
            headers, rows = pipe_table_to_rows(table.raw_content)
        elif table.soup is not None:
            headers, rows = html_to_rows(table.soup)
        else:
            headers, rows = [], []

        columns = [ColumnDescriptor.from_header(i, h) for i, h in enumerate(headers)]
        col_display = " | ".join(c.display_name for c in columns)

        fmt = table.format.value
        if table.complexity == TableComplexity.COMPLEX:
            fmt = "complex"
        sec = f" [{table.section_heading}]" if table.section_heading else ""

        parts.append(f"T{table.index} {fmt} {len(rows)}r {len(headers)}c v:{version}{sec}")
        parts.append(f"  {col_display}")

        # Preview rows as compact pipe-delimited lines
        for row_idx, row in enumerate(rows[:preview_rows]):
            cells = " | ".join(row[: len(headers)])
            parts.append(f"  row{row_idx}: {cells}")

        parts.append("")

    return "\n".join(parts)


@mcp.tool(output_schema=None)
def read_table(file_path: str, table_index: Annotated[int, Field(ge=0)]) -> str:
    """Read a full table as a clean pipe table with version hash.

    Prefer this over reading files directly — handles HTML tables, preserves
    inline formatting, and returns the version hash needed for any edit.

    First line of output is metadata: v:{hash} {format} {rows}r {cols}c [{section}]
    Extract the 12-char hex hash after "v:" (e.g. "a1b2c3d4e5f6") and pass it
    as the version argument to any write tool.

    If a write returns STALE_READ, call read_table again for a fresh version.

    Args:
        file_path: Absolute path to the Markdown file.
        table_index: 0-based table index from list_tables (the number after T).
    """
    path = Path(file_path)
    if not path.exists():
        return f"File not found: {file_path}"

    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        return f"Cannot read file: {e}"

    tables = detect_tables(content)

    if table_index >= len(tables):
        return f"TABLE_NOT_FOUND: index {table_index} out of range. {len(tables)} table(s) in file."

    table = tables[table_index]
    version = compute_hash(table.raw_content)
    sec = f" [{table.section_heading}]" if table.section_heading else ""

    # Complex tables: return pretty HTML
    if table.complexity == TableComplexity.COMPLEX and table.soup is not None:
        html = pretty_print_html(table.soup)
        return f"v:{version} complex{sec}\n{html}"

    # Simple/GitBook: return as pipe table
    if table.format == TableFormat.PIPE:
        headers, rows = pipe_table_to_rows(table.raw_content)
    elif table.soup is not None:
        headers, rows = html_to_rows(table.soup)
    else:
        return f"v:{version} {table.format.value}{sec}\n(empty)"

    columns = [ColumnDescriptor.from_header(i, h) for i, h in enumerate(headers)]
    col_display = " | ".join(c.display_name for c in columns)

    pipe = rows_to_pipe_table(headers, rows)

    return (
        f"v:{version} {table.format.value} {len(rows)}r {len(columns)}c{sec}\n{col_display}\n{pipe}"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_table_data(
    table: RawTable,
) -> tuple[list[str], list[list[str]]]:
    """Parse a RawTable into (headers, rows)."""
    if table.format == TableFormat.PIPE:
        return pipe_table_to_rows(table.raw_content)
    if table.soup is not None:
        return html_to_rows(table.soup)
    return [], []


def _error(error_type: str, message: str) -> str:
    return json.dumps({"error": error_type, "message": message})


Matcher = Callable[[str], bool]


def _read_tables(file_path: str) -> list[RawTable] | str:
    """Read and detect tables, returning the list or an error string."""
    path = Path(file_path)
    if not path.exists():
        return f"File not found: {file_path}"
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        return f"Cannot read file: {e}"
    tables = detect_tables(content)
    if not tables:
        return "No tables found."
    return tables


def _build_matcher(pattern: str, regex: str) -> Matcher | str:
    """Build a cell matcher.  Returns a callable or an error string."""
    if regex:
        try:
            compiled = re.compile(regex, re.IGNORECASE)
        except re.error as e:
            return _error("INVALID_REGEX", f"Bad regex: {e}")
        return lambda cell: compiled.search(cell) is not None

    if pattern:
        lower = pattern.lower()
        return lambda cell: lower in cell.lower()

    return lambda _cell: True  # match all


def _search_one_table(
    table: RawTable,
    matcher: Matcher,
    column: str,
    *,
    skip_missing_column: bool = False,
) -> tuple[list[str], int] | str:
    """Search a single table, returning (output_lines, match_count) or error str."""
    headers, rows = _parse_table_data(table)
    if not headers:
        return [], 0

    columns = [ColumnDescriptor.from_header(i, h) for i, h in enumerate(headers)]

    col_idx: int | None = None
    if column:
        try:
            col_idx = resolve_column(column, columns)
        except ValueError as e:
            if skip_missing_column:
                return [], 0
            return _error("COLUMN_NOT_FOUND", str(e))

    col_display = " | ".join(c.display_name for c in columns)
    version = compute_hash(table.raw_content)
    fmt = table.format.value
    if table.complexity == TableComplexity.COMPLEX:
        fmt = "complex"
    sec = f" [{table.section_heading}]" if table.section_heading else ""

    matched: list[str] = []
    for row_idx, row in enumerate(rows):
        cells_to_check = [row[col_idx]] if col_idx is not None and col_idx < len(row) else row
        if any(matcher(c) for c in cells_to_check):
            cells = " | ".join(row[: len(headers)])
            matched.append(f"  row{row_idx}: {cells}")

    if not matched:
        return [], 0

    lines = [f"T{table.index} v:{version} {fmt}{sec}", f"  {col_display}", *matched, ""]
    return lines, len(matched)


# ---------------------------------------------------------------------------
# search_tables
# ---------------------------------------------------------------------------


@mcp.tool(output_schema=None)
def search_tables(
    file_path: str,
    pattern: str = "",
    regex: str = "",
    table_index: Annotated[int, Field(ge=-1)] = -1,
    column: str = "",
) -> str:
    """Search for rows matching a value across one or all tables in a file.

    Returns matching rows with table index, row index, and version hash so
    you can immediately follow up with a write tool.  Prefer this over grep
    for table data — it understands column structure and handles HTML tables.

    Two search modes (regex overrides pattern if both given):
    - pattern: case-insensitive substring match (simple, no escaping needed)
    - regex: full regex via re.search (e.g. ``D 1\\.\\d+`` for sub-items)

    If neither pattern nor regex is provided, returns all rows.

    Args:
        file_path: Absolute path to the Markdown file.
        pattern: Case-insensitive substring to match in cell values.
        regex: Regular expression to match in cell values (overrides pattern).
        table_index: Search a specific table (0-based), or -1 for all tables.
        column: Restrict search to a column (letter, name, or composite).
            Empty string searches all columns.
    """
    result = _read_tables(file_path)
    if isinstance(result, str):
        return result
    tables = result

    # Determine which tables to search
    if table_index >= 0:
        if table_index >= len(tables):
            return _error(
                "TABLE_NOT_FOUND",
                f"Index {table_index} out of range. {len(tables)} table(s) in file.",
            )
        targets = [tables[table_index]]
    else:
        targets = tables

    matcher = _build_matcher(pattern, regex)
    if isinstance(matcher, str):
        return matcher  # error message

    total_matches = 0
    table_parts: list[str] = []

    for table in targets:
        table_result = _search_one_table(
            table, matcher, column, skip_missing_column=(table_index == -1)
        )
        if isinstance(table_result, str):
            return table_result  # error message
        lines, count = table_result
        if count:
            total_matches += count
            table_parts.extend(lines)

    if total_matches == 0:
        return "No matches found."

    table_count = sum(1 for line in table_parts if line.startswith("T"))
    header = f"{total_matches} match{'es' if total_matches != 1 else ''} in {table_count} table{'s' if table_count != 1 else ''}\n"
    return header + "\n".join(table_parts)
