"""Read-only MCP tools: list_tables and read_table."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field

from tablestakes.converter import (
    html_to_rows,
    pipe_table_to_rows,
    pretty_print_html,
    rows_to_pipe_table,
)
from tablestakes.hasher import compute_hash
from tablestakes.models import ColumnDescriptor, TableComplexity, TableFormat
from tablestakes.parser import detect_tables
from tablestakes.server import mcp


@mcp.tool(output_schema=None)
def list_tables(file_path: str, preview_rows: Annotated[int, Field(ge=0)] = 1) -> str:
    """List all tables in a Markdown file. Call this FIRST to discover tables.

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
    """Read a full table and get the version hash required for writes.

    Workflow: list_tables → read_table → write tool (update_cells, etc.)

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
