"""Bidirectional HTML↔pipe table conversion engine.

Read path: HTML → pipe table (for LLM consumption)
Write path: edited content → original format (for file write-back)
"""

from __future__ import annotations

import re
from copy import copy
from typing import Any

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString
from markdownify import markdownify as md

from tablestakes.models import ColumnDescriptor, index_to_letter

# ---------------------------------------------------------------------------
# Read path: HTML → rows
# ---------------------------------------------------------------------------


def html_to_rows(soup: Tag) -> tuple[list[str], list[list[str]]]:
    """Extract headers and data rows from an HTML table Tag.

    Returns (headers, rows) where each cell is Markdown text.
    Empty separator rows are preserved as rows of empty strings.
    """
    headers: list[str] = []
    rows: list[list[str]] = []

    thead = soup.find("thead")
    if thead and isinstance(thead, Tag):
        first_row = thead.find("tr")
        if first_row and isinstance(first_row, Tag):
            headers = [cell_html_to_markdown(cell) for cell in first_row.find_all(["th", "td"])]

    tbody = soup.find("tbody")
    container = tbody if tbody and isinstance(tbody, Tag) else soup

    for tr in container.find_all("tr", recursive=False):
        if not isinstance(tr, Tag):
            continue
        # Skip the header row if tbody wasn't present and we already extracted headers
        if not tbody and tr.parent == soup and not headers:
            headers = [cell_html_to_markdown(cell) for cell in tr.find_all(["th", "td"])]
            continue
        cells = [cell_html_to_markdown(cell) for cell in tr.find_all(["td", "th"])]
        rows.append(cells)

    # Generate synthetic headers if none found
    if not headers and rows:
        col_count = max(len(r) for r in rows)
        headers = [index_to_letter(i) for i in range(col_count)]

    return headers, rows


def cell_html_to_markdown(cell: Tag) -> str:
    """Convert a single cell's inner HTML to Markdown.

    Uses markdownify for inline tags, then escapes pipes for pipe tables.
    """
    inner_html = "".join(str(c) for c in cell.contents)
    if not inner_html.strip():
        return ""

    result = md(inner_html).strip()
    # Convert newlines (from <br> or markdownify output) to literal <br> for pipe tables
    result = result.replace("\n", "<br>")
    # Escape pipes for GFM pipe tables
    result = _escape_pipes(result)
    return result


def _escape_pipes(text: str) -> str:
    """Escape literal pipe characters for use in GFM pipe table cells."""
    # Match pipe NOT preceded by an odd number of backslashes
    return re.sub(r"(?<!\\)((?:\\\\)*)\|", r"\1\\|", text)


def _unescape_pipes(text: str) -> str:
    """Unescape pipe characters when converting back from pipe table."""
    return text.replace("\\|", "|")


# ---------------------------------------------------------------------------
# Read path: pipe table → rows
# ---------------------------------------------------------------------------


def pipe_table_to_rows(text: str) -> tuple[list[str], list[list[str]]]:
    """Parse a GFM pipe table string into headers and data rows."""
    lines = text.strip().split("\n")
    if len(lines) < 2:
        return [], []

    headers = _parse_pipe_line(lines[0])
    # Skip delimiter row (line 1)
    rows = [_parse_pipe_line(line) for line in lines[2:]]

    # Unescape pipes in cell content
    headers = [_unescape_pipes(h) for h in headers]
    rows = [[_unescape_pipes(c) for c in row] for row in rows]

    return headers, rows


def _parse_pipe_line(line: str) -> list[str]:
    """Parse a single pipe-delimited line into cell values."""
    # Strip leading/trailing whitespace and pipes
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    # Split on unescaped pipes
    cells = re.split(r"(?<!\\)\|", line)
    return [c.strip() for c in cells]


# ---------------------------------------------------------------------------
# Read path: rows → pipe table string
# ---------------------------------------------------------------------------


def rows_to_pipe_table(headers: list[str], rows: list[list[str]]) -> str:
    """Format headers + rows as a compact GFM pipe table string.

    Uses minimal formatting (no column padding) for token efficiency.
    LLMs don't need aligned columns — the pipe delimiters are sufficient.
    """
    if not headers:
        return ""

    col_count = len(headers)
    padded_rows = [_pad_row(row, col_count) for row in rows]

    header_line = "| " + " | ".join(headers) + " |"
    delim_line = "| " + " | ".join("---" for _ in headers) + " |"

    data_lines = []
    for row in padded_rows:
        cells = [row[i] if i < len(row) else "" for i in range(col_count)]
        data_lines.append("| " + " | ".join(cells) + " |")

    return "\n".join([header_line, delim_line, *data_lines])


def _pad_row(row: list[str], col_count: int) -> list[str]:
    """Pad a row with empty strings to match column count."""
    if len(row) >= col_count:
        return row[:col_count]
    return row + [""] * (col_count - len(row))


# ---------------------------------------------------------------------------
# Write path: Markdown cell → HTML cell content
# ---------------------------------------------------------------------------


def markdown_to_cell_html(text: str) -> str:
    """Convert inline Markdown back to HTML for write-back.

    Handles: **bold**, *italic*, `code`, [text](url)
    """
    text = _unescape_pipes(text)

    # Order matters: bold before italic to avoid ** → <em><em>
    # Bold: **text**
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Italic: *text* (but not inside already-converted <strong>)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    # Code: `text`
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    # Links: [text](url)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)

    return text


# ---------------------------------------------------------------------------
# Write path: rows → HTML
# ---------------------------------------------------------------------------


def rows_to_html(
    headers: list[str],
    rows: list[list[str]],
    original_soup: Tag | None = None,
    gitbook_attrs: dict[str, Any] | None = None,
) -> str:
    """Convert headers + rows back to HTML.

    If original_soup provided: clone AST, update cells in-place (preserves attrs).
    If structure changed (different row/col count): rebuild with cached attrs.
    Always serializes collapsed single-line for GitBook tables.
    """
    if original_soup is not None:
        return _update_existing_html(headers, rows, original_soup, gitbook_attrs)
    return _build_fresh_html(headers, rows, gitbook_attrs)


def _update_existing_html(
    headers: list[str],
    rows: list[list[str]],
    original_soup: Tag,
    gitbook_attrs: dict[str, Any] | None,
) -> str:
    """Update cell contents in a cloned AST, preserving all attributes."""
    soup = _clone_soup(original_soup)

    # Check if structure matches
    if len(headers) != _count_header_cells(soup) or len(rows) != _count_data_rows(soup):
        return _build_fresh_html(headers, rows, gitbook_attrs)

    _update_header_cells(soup, headers)
    _update_data_cells(soup, rows)

    return serialize_html_collapsed(soup)


def _update_header_cells(soup: Tag, headers: list[str]) -> None:
    """Update header cell contents in a parsed HTML table."""
    thead = soup.find("thead")
    if not thead or not isinstance(thead, Tag):
        return
    first_row = thead.find("tr")
    if not first_row or not isinstance(first_row, Tag):
        return
    for i, th in enumerate(first_row.find_all(["th", "td"])):
        if i < len(headers) and isinstance(th, Tag):
            _set_cell_content(th, markdown_to_cell_html(headers[i]))


def _update_data_cells(soup: Tag, rows: list[list[str]]) -> None:
    """Update data cell contents in a parsed HTML table."""
    tbody = soup.find("tbody")
    container = tbody if tbody and isinstance(tbody, Tag) else soup
    data_rows = [tr for tr in container.find_all("tr", recursive=False) if isinstance(tr, Tag)]

    # If no tbody and no thead, first row was used as header — skip it
    if not tbody and not soup.find("thead") and data_rows:
        data_rows = data_rows[1:]

    for row_idx, tr in enumerate(data_rows):
        if row_idx >= len(rows):
            break
        for col_idx, cell in enumerate(tr.find_all(["td", "th"])):
            if col_idx < len(rows[row_idx]) and isinstance(cell, Tag):
                _set_cell_content(cell, markdown_to_cell_html(rows[row_idx][col_idx]))


def _build_fresh_html(
    headers: list[str],
    rows: list[list[str]],
    gitbook_attrs: dict[str, Any] | None,
) -> str:
    """Build HTML table from scratch, applying cached GitBook attributes."""
    parts: list[str] = []

    # Table opening tag
    table_attrs_str = ""
    if gitbook_attrs and gitbook_attrs.get("table_attrs"):
        table_attrs_str = " " + " ".join(
            f'{k}="{v}"' for k, v in gitbook_attrs["table_attrs"].items()
        )
    parts.append(f"<table{table_attrs_str}>")

    # Thead
    parts.append("<thead><tr>")
    header_attrs = gitbook_attrs.get("header_attrs", {}) if gitbook_attrs else {}
    for col_idx, header in enumerate(headers):
        attrs_str = ""
        if col_idx in header_attrs:
            attrs_str = " " + " ".join(
                f'{k}="{v}"' if v else k for k, v in header_attrs[col_idx].items()
            )
        content = markdown_to_cell_html(header)
        parts.append(f"<th{attrs_str}>{content}</th>")
    parts.append("</tr></thead>")

    # Tbody
    parts.append("<tbody>")
    col_count = len(headers)
    for row in rows:
        parts.append("<tr>")
        for col_idx in range(col_count):
            val = row[col_idx] if col_idx < len(row) else ""
            content = markdown_to_cell_html(val)
            parts.append(f"<td>{content}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")

    return "".join(parts)


def _clone_soup(tag: Tag) -> Tag:
    """Create a deep copy of a BeautifulSoup Tag."""
    return copy(tag)


def _count_header_cells(soup: Tag) -> int:
    """Count header cells in a table."""
    thead = soup.find("thead")
    if thead and isinstance(thead, Tag):
        first_row = thead.find("tr")
        if first_row and isinstance(first_row, Tag):
            return len(first_row.find_all(["th", "td"]))
    return 0


def _count_data_rows(soup: Tag) -> int:
    """Count data rows (excluding header) in a table."""
    tbody = soup.find("tbody")
    container = tbody if tbody and isinstance(tbody, Tag) else soup
    return len([tr for tr in container.find_all("tr", recursive=False) if isinstance(tr, Tag)])


def _set_cell_content(cell: Tag, html_content: str) -> None:
    """Replace a cell's inner content with new HTML."""
    cell.clear()
    if not html_content:
        return
    fragment = BeautifulSoup(html_content, "html.parser")
    for child in list(fragment.children):
        cell.append(copy(child) if isinstance(child, Tag) else NavigableString(str(child)))


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def serialize_html_collapsed(soup: Tag) -> str:
    """Serialize a BeautifulSoup Tag to collapsed single-line HTML.

    Matches GitBook's format: no indentation, no extra whitespace between tags.
    """
    raw = str(soup)
    # Collapse formatting whitespace (contains newlines) between tags
    # Preserves single spaces in content like "hello <strong>world</strong>"
    raw = re.sub(r">\n\s*<", "><", raw)
    # Remove leading/trailing whitespace
    return raw.strip()


def pretty_print_html(soup: Tag) -> str:
    """Format HTML with indentation for complex tables shown to LLMs."""
    return soup.prettify()


# ---------------------------------------------------------------------------
# Column resolution
# ---------------------------------------------------------------------------


def resolve_column(ref: str, columns: list[ColumnDescriptor]) -> int:
    """Resolve a column reference to a 0-based index.

    Accepts: letter ("A"), name ("Priority"), composite ("B:Priority"),
    index as string ("1"), case-insensitive name match.

    Raises ValueError with suggestions on ambiguity or not-found.
    """
    ref = ref.strip()

    # Try composite "letter:name" format
    if ":" in ref:
        return _resolve_composite(ref, columns)

    # Try exact letter match
    ref_upper = ref.upper()
    letter_matches = [c for c in columns if c.letter == ref_upper]
    if len(letter_matches) == 1:
        return letter_matches[0].index

    # Try numeric index
    if ref.isdigit():
        return _resolve_numeric(ref, columns)

    # Try name match (exact, then case-insensitive)
    return _resolve_by_name(ref, columns)


def _resolve_composite(ref: str, columns: list[ColumnDescriptor]) -> int:
    """Resolve a composite 'letter:name' reference."""
    letter_part = ref.split(":")[0].upper()
    for col in columns:
        if col.letter == letter_part:
            return col.index
    _raise_not_found(ref, columns)
    return -1  # unreachable


def _resolve_numeric(ref: str, columns: list[ColumnDescriptor]) -> int:
    """Resolve a numeric index reference."""
    idx = int(ref)
    if 0 <= idx < len(columns):
        return idx
    msg = f"Column index {idx} out of range (0-{len(columns) - 1})"
    raise ValueError(msg)


def _resolve_by_name(ref: str, columns: list[ColumnDescriptor]) -> int:
    """Resolve by exact or case-insensitive name match."""
    # Exact match
    exact = [c for c in columns if c.name == ref]
    if len(exact) == 1:
        return exact[0].index
    if len(exact) > 1:
        _raise_ambiguous(ref, exact)

    # Case-insensitive match
    ci = [c for c in columns if c.name.lower() == ref.lower()]
    if len(ci) == 1:
        return ci[0].index
    if len(ci) > 1:
        _raise_ambiguous(ref, ci)

    _raise_not_found(ref, columns)
    return -1  # unreachable


def _raise_ambiguous(ref: str, matches: list[ColumnDescriptor]) -> None:
    """Raise ValueError for ambiguous column name."""
    options = [c.display_name for c in matches]
    msg = f"Column '{ref}' is ambiguous. Use one of: {', '.join(options)}"
    raise ValueError(msg)


def _raise_not_found(ref: str, columns: list[ColumnDescriptor]) -> None:
    """Raise ValueError with available column suggestions."""
    available = [c.display_name for c in columns]
    # Simple fuzzy: find names containing the ref as substring
    suggestions = [name for name in available if ref.lower() in name.lower()]
    if not suggestions:
        suggestions = available[:5]
    msg = f"Column '{ref}' not found. Available: {', '.join(suggestions)}"
    raise ValueError(msg)
