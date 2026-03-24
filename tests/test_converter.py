"""Tests for bidirectional HTML↔pipe conversion."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from bs4 import Tag

from tablestakes.converter import (
    _escape_pipe_cell,
    _unescape_pipe_cell,
    cell_html_to_markdown,
    html_to_rows,
    markdown_to_cell_html,
    parse_alignment,
    pipe_table_to_rows,
    resolve_column,
    rows_to_html,
    rows_to_pipe_table,
    serialize_html_collapsed,
)
from tablestakes.models import ColumnDescriptor
from tests.conftest import parse_html_table as _parse_table

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# cell_html_to_markdown
# ---------------------------------------------------------------------------


class TestCellHtmlToMarkdown:
    def test_strong(self) -> None:
        cell = _parse_table("<table><tr><td><strong>bold</strong></td></tr></table>").find("td")
        assert isinstance(cell, Tag)
        assert cell_html_to_markdown(cell) == "**bold**"

    def test_em(self) -> None:
        cell = _parse_table("<table><tr><td><em>italic</em></td></tr></table>").find("td")
        assert isinstance(cell, Tag)
        assert cell_html_to_markdown(cell) == "*italic*"

    def test_code(self) -> None:
        cell = _parse_table("<table><tr><td><code>Case.OwnerId</code></td></tr></table>").find("td")
        assert isinstance(cell, Tag)
        assert cell_html_to_markdown(cell) == "`Case.OwnerId`"

    def test_link(self) -> None:
        cell = _parse_table(
            '<table><tr><td><a href="https://example.com">link text</a></td></tr></table>'
        ).find("td")
        assert isinstance(cell, Tag)
        assert cell_html_to_markdown(cell) == "[link text](https://example.com)"

    def test_mixed_formatting(self) -> None:
        cell = _parse_table(
            "<table><tr><td><strong>1.1</strong> Some text with <code>code</code></td></tr></table>"
        ).find("td")
        assert isinstance(cell, Tag)
        result = cell_html_to_markdown(cell)
        assert "**1.1**" in result
        assert "`code`" in result

    def test_empty_cell(self) -> None:
        cell = _parse_table("<table><tr><td></td></tr></table>").find("td")
        assert isinstance(cell, Tag)
        assert cell_html_to_markdown(cell) == ""

    def test_pipe_escaped(self) -> None:
        cell = _parse_table("<table><tr><td>a|b</td></tr></table>").find("td")
        assert isinstance(cell, Tag)
        assert cell_html_to_markdown(cell) == r"a\|b"


# ---------------------------------------------------------------------------
# html_to_rows
# ---------------------------------------------------------------------------


class TestHtmlToRows:
    def test_basic_table(self) -> None:
        html = "<table><thead><tr><th>Name</th><th>Age</th></tr></thead><tbody><tr><td>Alice</td><td>30</td></tr></tbody></table>"
        soup = _parse_table(html)
        headers, rows = html_to_rows(soup)
        assert headers == ["Name", "Age"]
        assert rows == [["Alice", "30"]]

    def test_multiple_rows(self) -> None:
        html = "<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody><tr><td>1</td><td>2</td></tr><tr><td>3</td><td>4</td></tr></tbody></table>"
        soup = _parse_table(html)
        _headers, rows = html_to_rows(soup)
        assert len(rows) == 2
        assert rows[0] == ["1", "2"]
        assert rows[1] == ["3", "4"]

    def test_empty_separator_rows(self) -> None:
        html = "<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody><tr><td>1</td><td>2</td></tr><tr><td></td><td></td></tr><tr><td>3</td><td>4</td></tr></tbody></table>"
        soup = _parse_table(html)
        _headers, rows = html_to_rows(soup)
        assert len(rows) == 3
        assert rows[1] == ["", ""]

    def test_inline_formatting_preserved(self) -> None:
        html = "<table><thead><tr><th>Col</th></tr></thead><tbody><tr><td><strong>bold</strong> text</td></tr></tbody></table>"
        soup = _parse_table(html)
        _headers, rows = html_to_rows(soup)
        assert "**bold**" in rows[0][0]

    def test_headerless_table_gets_synthetic_headers(self) -> None:
        html = "<table><tbody><tr><td>1</td><td>2</td><td>3</td></tr></tbody></table>"
        soup = _parse_table(html)
        headers, rows = html_to_rows(soup)
        assert headers == ["A", "B", "C"]
        assert rows == [["1", "2", "3"]]

    def test_gitbook_fixture(self, fixtures_dir: Path) -> None:
        html = (fixtures_dir / "gitbook_small.html").read_text()
        soup = _parse_table(html)
        headers, rows = html_to_rows(soup)
        assert len(headers) == 4
        assert headers[0] == "Requirement"
        assert headers[1] == "Priority"
        assert len(rows) == 3
        assert "**5.1**" in rows[0][0]


# ---------------------------------------------------------------------------
# pipe_table_to_rows
# ---------------------------------------------------------------------------


class TestPipeTableToRows:
    def test_basic(self) -> None:
        text = "| A | B |\n| --- | --- |\n| 1 | 2 |"
        headers, rows = pipe_table_to_rows(text)
        assert headers == ["A", "B"]
        assert rows == [["1", "2"]]

    def test_escaped_pipes(self) -> None:
        text = r"| Col |" + "\n" + "| --- |\n" + r"| a\|b |"
        _headers, rows = pipe_table_to_rows(text)
        assert rows[0][0] == "a|b"

    def test_empty_cells(self) -> None:
        text = "| A | B |\n| --- | --- |\n|  |  |"
        _headers, rows = pipe_table_to_rows(text)
        assert rows[0] == ["", ""]


# ---------------------------------------------------------------------------
# rows_to_pipe_table
# ---------------------------------------------------------------------------


class TestRowsToPipeTable:
    def test_basic(self) -> None:
        result = rows_to_pipe_table(["A", "B"], [["1", "2"]])
        lines = result.split("\n")
        assert len(lines) == 3
        assert "A" in lines[0]
        assert "---" in lines[1]
        assert "1" in lines[2]

    def test_short_rows_padded(self) -> None:
        result = rows_to_pipe_table(["A", "B", "C"], [["1"]])
        lines = result.split("\n")
        # Data row should have 3 cells even though input had 1
        assert lines[2].count("|") == 4  # 3 cells + outer pipes

    def test_empty_headers_returns_empty(self) -> None:
        assert rows_to_pipe_table([], [["1", "2"]]) == ""

    def test_roundtrip(self) -> None:
        headers = ["Name", "Age", "City"]
        rows = [["Alice", "30", "NYC"], ["Bob", "25", "LA"]]
        pipe = rows_to_pipe_table(headers, rows)
        h2, r2 = pipe_table_to_rows(pipe)
        assert h2 == headers
        assert r2 == rows


# ---------------------------------------------------------------------------
# markdown_to_cell_html
# ---------------------------------------------------------------------------


class TestMarkdownToCellHtml:
    def test_bold(self) -> None:
        assert markdown_to_cell_html("**bold**") == "<strong>bold</strong>"

    def test_italic(self) -> None:
        assert markdown_to_cell_html("*italic*") == "<em>italic</em>"

    def test_code(self) -> None:
        assert markdown_to_cell_html("`code`") == "<code>code</code>"

    def test_link(self) -> None:
        result = markdown_to_cell_html("[text](https://example.com)")
        assert result == '<a href="https://example.com">text</a>'

    def test_mixed(self) -> None:
        result = markdown_to_cell_html("**1.1** Some `code` here")
        assert "<strong>1.1</strong>" in result
        assert "<code>code</code>" in result

    def test_pipe_unescaped(self) -> None:
        assert markdown_to_cell_html(r"a\|b") == "a|b"

    def test_plain_text(self) -> None:
        assert markdown_to_cell_html("hello world") == "hello world"


# ---------------------------------------------------------------------------
# rows_to_html (write-back)
# ---------------------------------------------------------------------------


class TestRowsToHtml:
    def test_fresh_build_simple(self) -> None:
        result = rows_to_html(["A", "B"], [["1", "2"]])
        assert "<table>" in result
        assert "<th>A</th>" in result
        assert "<td>1</td>" in result
        assert "\n" not in result  # collapsed

    def test_fresh_build_with_gitbook_attrs(self) -> None:
        attrs = {
            "table_attrs": {},
            "header_attrs": {0: {"width": "500.5"}},
        }
        result = rows_to_html(["Col"], [["val"]], gitbook_attrs=attrs)
        assert 'width="500.5"' in result

    def test_update_preserves_attrs(self) -> None:
        html = '<table><thead><tr><th width="100">A</th></tr></thead><tbody><tr><td>old</td></tr></tbody></table>'
        soup = _parse_table(html)
        result = rows_to_html(["A"], [["new"]], original_soup=soup)
        assert 'width="100"' in result
        assert "new" in result
        assert "old" not in result

    def test_structure_change_triggers_rebuild(self) -> None:
        html = "<table><thead><tr><th>A</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table>"
        soup = _parse_table(html)
        # Adding a row triggers rebuild
        result = rows_to_html(["A"], [["1"], ["2"]], original_soup=soup)
        assert "<td>2</td>" in result

    def test_markdown_converted_back_to_html(self) -> None:
        result = rows_to_html(["Header"], [["**bold** text"]])
        assert "<strong>bold</strong>" in result

    def test_collapsed_output(self) -> None:
        result = rows_to_html(["A", "B"], [["1", "2"], ["3", "4"]])
        assert "\n" not in result
        assert "> <" not in result


class TestSerializeHtmlCollapsed:
    def test_removes_whitespace(self) -> None:
        html = "<table>\n  <tr>\n    <td> A </td>\n  </tr>\n</table>"
        soup = _parse_table(html)
        result = serialize_html_collapsed(soup)
        assert "\n" not in result
        assert ">  <" not in result  # whitespace-only between tags removed

    def test_preserves_content_spaces(self) -> None:
        html = "<table><tr><td>hello world</td></tr></table>"
        soup = _parse_table(html)
        result = serialize_html_collapsed(soup)
        assert "hello world" in result


# ---------------------------------------------------------------------------
# resolve_column
# ---------------------------------------------------------------------------


class TestResolveColumn:
    @pytest.fixture
    def cols(self) -> list[ColumnDescriptor]:
        return [
            ColumnDescriptor.from_header(0, "Requirement"),
            ColumnDescriptor.from_header(1, "Priority"),
            ColumnDescriptor.from_header(2, "Priority 1-2-3"),
        ]

    def test_by_letter(self, cols: list[ColumnDescriptor]) -> None:
        assert resolve_column("A", cols) == 0
        assert resolve_column("B", cols) == 1
        assert resolve_column("C", cols) == 2

    def test_by_letter_lowercase(self, cols: list[ColumnDescriptor]) -> None:
        assert resolve_column("a", cols) == 0

    def test_by_name(self, cols: list[ColumnDescriptor]) -> None:
        assert resolve_column("Requirement", cols) == 0

    def test_by_composite(self, cols: list[ColumnDescriptor]) -> None:
        assert resolve_column("B:Priority", cols) == 1
        assert resolve_column("C:Priority 1-2-3", cols) == 2

    def test_by_index(self, cols: list[ColumnDescriptor]) -> None:
        assert resolve_column("0", cols) == 0
        assert resolve_column("2", cols) == 2

    def test_case_insensitive_name(self, cols: list[ColumnDescriptor]) -> None:
        assert resolve_column("requirement", cols) == 0

    def test_ambiguous_name(self) -> None:
        cols = [
            ColumnDescriptor.from_header(0, "Amount"),
            ColumnDescriptor.from_header(1, "Amount"),
        ]
        with pytest.raises(ValueError, match="ambiguous"):
            resolve_column("Amount", cols)

    def test_not_found(self, cols: list[ColumnDescriptor]) -> None:
        with pytest.raises(ValueError, match="not found"):
            resolve_column("Nonexistent", cols)

    def test_index_out_of_range(self, cols: list[ColumnDescriptor]) -> None:
        with pytest.raises(ValueError, match="out of range"):
            resolve_column("99", cols)


# ---------------------------------------------------------------------------
# Full round-trip: HTML → pipe → edit → HTML
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_gitbook_roundtrip(self, fixtures_dir: Path) -> None:
        """Read GitBook HTML → pipe → write back HTML, preserving structure."""
        html = (fixtures_dir / "gitbook_small.html").read_text()
        soup = _parse_table(html)

        # Read path
        headers, rows = html_to_rows(soup)
        pipe = rows_to_pipe_table(headers, rows)
        assert "**5.1**" in pipe

        # Simulate edit: change a cell
        rows[0][1] = "Should"  # was "Must"

        # Write path: back to HTML with original soup
        result = rows_to_html(headers, rows, original_soup=soup)
        assert "Should" in result
        assert "Must" not in result or result.count("Must") < html.count("Must")

    def test_pipe_roundtrip(self) -> None:
        """Pipe table survives parse → serialize → parse cycle."""
        original = "| A | B |\n| --- | --- |\n| hello | world |"
        h1, r1 = pipe_table_to_rows(original)
        regenerated = rows_to_pipe_table(h1, r1)
        h2, r2 = pipe_table_to_rows(regenerated)
        assert h1 == h2
        assert r1 == r2


# ---------------------------------------------------------------------------
# Pipe-table escaping (Bug A)
# ---------------------------------------------------------------------------


class TestPipeCellEscaping:
    def test_escape_pipe(self) -> None:
        assert _escape_pipe_cell("a|b") == "a\\|b"

    def test_escape_backslash(self) -> None:
        assert _escape_pipe_cell("a\\b") == "a\\\\b"

    def test_escape_newline(self) -> None:
        assert _escape_pipe_cell("line1\nline2") == "line1<br>line2"

    def test_escape_backslash_pipe(self) -> None:
        assert _escape_pipe_cell("a\\|b") == "a\\\\\\|b"

    def test_round_trip(self) -> None:
        original = "has|pipe and \\backslash"
        assert _unescape_pipe_cell(_escape_pipe_cell(original)) == original

    def test_pipe_in_cell_survives_table_round_trip(self) -> None:
        headers = ["Name", "Notes"]
        rows = [["Alice", "a|b|c"], ["Bob", "ok"]]
        parsed_h, parsed_r = pipe_table_to_rows(rows_to_pipe_table(headers, rows))
        assert parsed_h == headers
        assert parsed_r == rows

    def test_backslash_in_cell_survives_table_round_trip(self) -> None:
        headers = ["Path"]
        rows = [["C:\\Users\\test"], ["back\\slash"]]
        _, parsed_r = pipe_table_to_rows(rows_to_pipe_table(headers, rows))
        assert parsed_r[0] == ["C:\\Users\\test"]

    def test_newline_in_cell_becomes_br(self) -> None:
        headers = ["Content"]
        rows = [["line1\nline2"]]
        table_str = rows_to_pipe_table(headers, rows)
        assert "\\n" not in table_str
        assert "<br>" in table_str

    def test_pipe_in_header_survives_table_round_trip(self) -> None:
        headers = ["Col|A", "Col|B"]
        rows = [["1", "2"]]
        parsed_h, _ = pipe_table_to_rows(rows_to_pipe_table(headers, rows))
        assert parsed_h == headers


# ---------------------------------------------------------------------------
# Alignment markers (Bug C)
# ---------------------------------------------------------------------------


class TestAlignment:
    def test_parse_alignment(self) -> None:
        content = "| L | C | R | N |\n| :--- | :---: | ---: | --- |\n| 1 | 2 | 3 | 4 |"
        assert parse_alignment(content) == ["left", "center", "right", "none"]

    def test_alignment_preserved_in_round_trip(self) -> None:
        alignments = ["left", "center", "right", "none"]
        table_str = rows_to_pipe_table(
            ["L", "C", "R", "N"], [["a", "b", "c", "d"]], alignments=alignments
        )
        assert ":---" in table_str
        assert ":---:" in table_str
        assert "---:" in table_str


# ---------------------------------------------------------------------------
# Numeric column names (Bug J)
# ---------------------------------------------------------------------------


class TestNumericColumnNames:
    def test_numeric_name_resolved_by_name(self) -> None:
        columns = [
            ColumnDescriptor.from_header(0, "1"),
            ColumnDescriptor.from_header(1, "2"),
            ColumnDescriptor.from_header(2, "3"),
        ]
        assert resolve_column("1", columns) == 0
        assert resolve_column("2", columns) == 1
        assert resolve_column("3", columns) == 2

    def test_numeric_fallback_when_no_name_match(self) -> None:
        columns = [
            ColumnDescriptor.from_header(0, "Name"),
            ColumnDescriptor.from_header(1, "Age"),
            ColumnDescriptor.from_header(2, "City"),
        ]
        assert resolve_column("0", columns) == 0
        assert resolve_column("1", columns) == 1
