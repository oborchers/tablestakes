"""Table detection and classification engine.

Detects both HTML <table> blocks and GFM pipe tables in Markdown documents.
Classifies HTML tables as simple, complex, or gitbook based on attributes.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from tablestakes.models import RawTable, TableComplexity, TableFormat

# --- Regex patterns ---

# Fenced code blocks: ```...``` or ~~~...~~~
_FENCED_CODE_RE = re.compile(
    r"^(`{3,})[^\n]*\n[\s\S]*?^\1\s*$|^(~{3,})[^\n]*\n[\s\S]*?^\2\s*$",
    re.MULTILINE,
)

# HTML comments
_HTML_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")

# HTML table blocks (non-greedy, case-insensitive)
_HTML_TABLE_RE = re.compile(r"<table[\s>][\s\S]*?</table>", re.IGNORECASE)

# GitBook-specific attributes that indicate a GitBook table
_GITBOOK_TABLE_ATTRS = {"data-view", "data-full-width"}
_GITBOOK_CELL_ATTRS = {
    "data-hidden",
    "data-card-target",
    "data-card-cover",
    "data-type",
}


def detect_tables(content: str) -> list[RawTable]:
    """Detect all tables in a Markdown document.

    Returns tables in document order with 0-based indices.

    Detection precedence:
    1. Fenced code blocks — excluded
    2. HTML comments — excluded
    3. HTML <table> blocks
    4. GFM pipe tables
    """
    # Strip UTF-8 BOM if present — it breaks regex matching at position 0
    content = content.lstrip("\ufeff")

    excluded = _detect_excluded_ranges(content)
    html_tables = _detect_html_tables(content, excluded)

    # Build set of HTML table ranges to avoid detecting pipe tables inside them
    html_ranges = [(t.start_offset, t.end_offset) for t in html_tables]
    pipe_tables = _detect_pipe_tables(content, excluded, html_ranges)

    # Merge, remove nested tables, and sort by position
    all_tables = _remove_nested_tables(html_tables + pipe_tables)
    all_tables.sort(key=lambda t: t.start_offset)

    # Assign sequential indices
    for i, table in enumerate(all_tables):
        table.index = i

    return all_tables


def _detect_excluded_ranges(content: str) -> list[tuple[int, int]]:
    """Find byte ranges to exclude: fenced code blocks, HTML comments."""
    ranges = [(m.start(), m.end()) for m in _FENCED_CODE_RE.finditer(content)]
    ranges.extend((m.start(), m.end()) for m in _HTML_COMMENT_RE.finditer(content))
    return ranges


def _is_in_ranges(pos: int, ranges: list[tuple[int, int]]) -> bool:
    """Check if a position falls inside any of the given ranges."""
    return any(start <= pos < end for start, end in ranges)


def _remove_nested_tables(tables: list[RawTable]) -> list[RawTable]:
    """Remove tables whose range falls entirely inside another table.

    Handles phantom ``<table>`` tags detected inside pipe table cells and
    pipe-like text detected inside HTML table cells.
    """
    return [
        t
        for t in tables
        if not any(
            o.start_offset <= t.start_offset and t.end_offset <= o.end_offset and o is not t
            for o in tables
        )
    ]


def _offset_to_line(content: str, offset: int) -> int:
    """Convert byte offset to 1-based line number."""
    return content[:offset].count("\n") + 1


def _detect_html_tables(content: str, excluded: list[tuple[int, int]]) -> list[RawTable]:
    """Find all <table>...</table> blocks not inside excluded ranges."""
    tables: list[RawTable] = []

    for match in _HTML_TABLE_RE.finditer(content):
        if _is_in_ranges(match.start(), excluded):
            continue

        raw = match.group(0)
        soup = BeautifulSoup(raw, "html.parser")
        table_tag = soup.find("table")

        if not isinstance(table_tag, Tag):
            continue

        complexity, gitbook_attrs = _classify_html_table(table_tag)

        if complexity == TableComplexity.GITBOOK:
            fmt = TableFormat.HTML_GITBOOK
        else:
            fmt = TableFormat.HTML_GENERAL

        tables.append(
            RawTable(
                index=-1,  # assigned later
                format=fmt,
                complexity=complexity,
                raw_content=raw,
                start_offset=match.start(),
                end_offset=match.end(),
                source_line=_offset_to_line(content, match.start()),
                section_heading=_find_section_heading(content, match.start()),
                soup=table_tag,
                gitbook_attrs=gitbook_attrs,
            )
        )

    return tables


def _classify_html_table(
    table_tag: Tag,
) -> tuple[TableComplexity, dict[str, Any] | None]:
    """Classify an HTML table by complexity.

    Returns (complexity, gitbook_attrs_or_None).
    """
    # Check for complex features
    if table_tag.find(attrs={"colspan": True}) or table_tag.find(attrs={"rowspan": True}):
        return TableComplexity.COMPLEX, None

    if table_tag.find("table"):  # nested table
        return TableComplexity.COMPLEX, None

    if table_tag.find(["select", "option"]):
        return TableComplexity.COMPLEX, None

    # Check for GitBook markers
    gitbook_attrs = _extract_gitbook_attrs(table_tag)
    if gitbook_attrs is not None:
        return TableComplexity.GITBOOK, gitbook_attrs

    return TableComplexity.SIMPLE, None


def _extract_gitbook_attrs(table_tag: Tag) -> dict[str, Any] | None:
    """Extract GitBook-specific attributes if present.

    Returns None if no GitBook markers found.
    """
    table_level = _extract_table_level_attrs(table_tag)
    header_level = _extract_header_level_attrs(table_tag)

    if not table_level and not header_level:
        return None

    return {
        "table_attrs": table_level,
        "header_attrs": header_level,
    }


def _extract_table_level_attrs(table_tag: Tag) -> dict[str, str]:
    """Extract GitBook table-level attributes (data-view, etc.)."""
    result: dict[str, str] = {}
    if not isinstance(table_tag.attrs, dict):
        return result
    for attr in _GITBOOK_TABLE_ATTRS:
        val = table_tag.get(attr)
        if val is not None:
            result[attr] = str(val)
    return result


def _extract_header_level_attrs(table_tag: Tag) -> dict[int, dict[str, str]]:
    """Extract GitBook header-level attributes (width, data-hidden, etc.)."""
    result: dict[int, dict[str, str]] = {}
    thead = table_tag.find("thead")
    if not thead or not isinstance(thead, Tag):
        return result
    for col_idx, th in enumerate(thead.find_all(["th", "td"])):
        if not isinstance(th, Tag):
            continue
        col_attrs = _extract_cell_gitbook_attrs(th)
        if col_attrs:
            result[col_idx] = col_attrs
    return result


def _extract_cell_gitbook_attrs(cell: Tag) -> dict[str, str]:
    """Extract GitBook attributes from a single th/td."""
    attrs: dict[str, str] = {}
    width = cell.get("width")
    if width is not None:
        attrs["width"] = str(width)
    for attr in _GITBOOK_CELL_ATTRS:
        if cell.has_attr(attr):
            val = cell.get(attr)
            # Boolean attributes (e.g. data-hidden) have no value
            attrs[attr] = str(val) if val and val is not True else ""  # type: ignore[comparison-overlap]
    return attrs


# Pipe table detection

# A pipe table line must start with optional 0-3 spaces then a pipe
_PIPE_LINE_RE = re.compile(r"^\s{0,3}\|")
# Delimiter row: | followed by dashes/colons/pipes
_DELIMITER_RE = re.compile(r"^\s{0,3}\|[\s:]*-{1,}[\s:]*(?:\|[\s:]*-{1,}[\s:]*)*\|?\s*$")


def _detect_pipe_tables(
    content: str,
    excluded: list[tuple[int, int]],
    html_ranges: list[tuple[int, int]],
) -> list[RawTable]:
    """Find GFM pipe tables not inside excluded or HTML ranges."""
    tables: list[RawTable] = []
    lines = content.split("\n")
    all_excluded = excluded + html_ranges

    i = 0
    offset = 0  # byte offset tracking
    while i < len(lines):
        line = lines[i]
        line_start = offset

        # Check if this could be a header line followed by a delimiter
        if (
            _PIPE_LINE_RE.match(line)
            and not _is_in_ranges(line_start, all_excluded)
            and "|" in line[line.index("|") + 1 :]  # at least 2 pipes
            and i + 1 < len(lines)
            and _DELIMITER_RE.match(lines[i + 1])
        ):
            # Found a pipe table — collect all contiguous pipe lines
            table_lines = [lines[i], lines[i + 1]]
            j = i + 2
            while j < len(lines) and _PIPE_LINE_RE.match(lines[j]):
                table_lines.append(lines[j])
                j += 1

            raw = "\n".join(table_lines)
            end_offset = line_start + len(raw)

            tables.append(
                RawTable(
                    index=-1,
                    format=TableFormat.PIPE,
                    complexity=TableComplexity.SIMPLE,
                    raw_content=raw,
                    start_offset=line_start,
                    end_offset=end_offset,
                    source_line=_offset_to_line(content, line_start),
                    section_heading=_find_section_heading(content, line_start),
                    soup=None,
                    gitbook_attrs=None,
                )
            )

            i = j
            offset = line_start + len(raw) + 1  # +1 for the \n
            continue

        offset += len(line) + 1  # +1 for the \n
        i += 1

    return tables


def _find_section_heading(content: str, offset: int) -> str | None:
    """Scan backward from offset to find the nearest Markdown heading."""
    before = content[:offset]
    last_match = None
    for m in re.finditer(r"^(#{1,6})\s+(.+)$", before, re.MULTILINE):
        last_match = m
    if last_match is None:
        return None

    return last_match.group(2).strip()
