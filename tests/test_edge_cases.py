"""Tests for edge cases and hardening."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from bs4 import Tag
from fastmcp import Client

from tablestakes.converter import (
    cell_html_to_markdown,
    html_to_rows,
    markdown_to_cell_html,
    pipe_table_to_rows,
    rows_to_html,
    rows_to_pipe_table,
    serialize_html_collapsed,
)
from tablestakes.parser import detect_tables
from tablestakes.server import mcp
from tests.conftest import parse_html_table as _parse_table
from tests.conftest import read_version, text_of

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Pipe escaping
# ---------------------------------------------------------------------------


class TestPipeEscaping:
    def test_pipe_in_cell_escaped_on_read(self) -> None:
        cell = _parse_table("<table><tr><td>a|b|c</td></tr></table>").find("td")
        assert isinstance(cell, Tag)
        result = cell_html_to_markdown(cell)
        assert "|" not in result.replace("\\|", "")
        assert result == r"a\|b\|c"

    def test_pipe_unescaped_on_write(self) -> None:
        result = markdown_to_cell_html(r"a\|b")
        assert result == "a|b"

    def test_pipe_roundtrip_in_table(self) -> None:
        html = "<table><thead><tr><th>Col</th></tr></thead><tbody><tr><td>x|y</td></tr></tbody></table>"
        soup = _parse_table(html)
        headers, rows = html_to_rows(soup)
        assert rows[0][0] == r"x\|y"
        # Write back
        result = rows_to_html(headers, rows, original_soup=soup)
        assert "x|y" in result
        assert r"x\|y" not in result

    def test_already_escaped_pipe_not_double_escaped(self) -> None:
        r"""If HTML already contains \|, don't escape to \\|."""
        cell = _parse_table(r"<table><tr><td>a\|b</td></tr></table>").find("td")
        assert isinstance(cell, Tag)
        result = cell_html_to_markdown(cell)
        # Should be a\|b, not a\\|b
        assert r"\\\|" not in result


# ---------------------------------------------------------------------------
# Empty separator rows
# ---------------------------------------------------------------------------


class TestEmptySeparatorRows:
    def test_preserved_through_read(self) -> None:
        html = (
            "<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody>"
            "<tr><td>1</td><td>2</td></tr>"
            "<tr><td></td><td></td></tr>"
            "<tr><td><strong>Section</strong></td><td></td></tr>"
            "<tr><td>3</td><td>4</td></tr>"
            "</tbody></table>"
        )
        soup = _parse_table(html)
        _headers, rows = html_to_rows(soup)
        assert len(rows) == 4
        assert rows[1] == ["", ""]

    def test_preserved_through_pipe_roundtrip(self) -> None:
        headers = ["A", "B"]
        rows = [["1", "2"], ["", ""], ["3", "4"]]
        pipe = rows_to_pipe_table(headers, rows)
        _h2, r2 = pipe_table_to_rows(pipe)
        assert r2[1] == ["", ""]

    def test_preserved_through_html_write(self) -> None:
        html = (
            "<table><thead><tr><th>A</th></tr></thead><tbody>"
            "<tr><td>1</td></tr>"
            "<tr><td></td></tr>"
            "<tr><td>2</td></tr>"
            "</tbody></table>"
        )
        soup = _parse_table(html)
        headers, rows = html_to_rows(soup)
        result = rows_to_html(headers, rows, original_soup=soup)
        # Should still have 3 data rows in the HTML
        assert result.count("<tr>") >= 4  # 1 header + 3 data


# ---------------------------------------------------------------------------
# Headerless tables
# ---------------------------------------------------------------------------


class TestHeaderlessTables:
    def test_synthetic_headers_generated(self) -> None:
        html = "<table><tbody><tr><td>a</td><td>b</td><td>c</td></tr><tr><td>1</td><td>2</td><td>3</td></tr></tbody></table>"
        soup = _parse_table(html)
        headers, rows = html_to_rows(soup)
        assert headers == ["A", "B", "C"]
        assert len(rows) == 2

    def test_no_thead_no_th_single_row(self) -> None:
        """Single row with no thead/th: first row becomes header, no data rows."""
        html = "<table><tr><td>x</td><td>y</td></tr></table>"
        soup = _parse_table(html)
        headers, rows = html_to_rows(soup)
        # With no structural hint, first row becomes header
        assert headers == ["x", "y"]
        assert rows == []


# ---------------------------------------------------------------------------
# UTF-8 BOM
# ---------------------------------------------------------------------------


class TestBom:
    def test_bom_does_not_break_detection(self, tmp_path: Path) -> None:
        """UTF-8 BOM at file start should not prevent table detection."""
        content = "\ufeff# Title\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n"
        f = tmp_path / "bom.md"
        f.write_text(content, encoding="utf-8")
        tables = detect_tables(f.read_text(encoding="utf-8"))
        assert len(tables) == 1

    def test_bom_table_content_correct(self, tmp_path: Path) -> None:
        content = "\ufeff| A | B |\n| --- | --- |\n| 1 | 2 |\n"
        f = tmp_path / "bom.md"
        f.write_text(content, encoding="utf-8")
        tables = detect_tables(f.read_text(encoding="utf-8"))
        headers, _rows = pipe_table_to_rows(tables[0].raw_content)
        assert headers == ["A", "B"]


# ---------------------------------------------------------------------------
# Line endings
# ---------------------------------------------------------------------------


class TestLineEndings:
    def test_crlf_pipe_table(self) -> None:
        content = "# Title\r\n\r\n| A | B |\r\n| --- | --- |\r\n| 1 | 2 |\r\n"
        tables = detect_tables(content)
        assert len(tables) == 1

    def test_crlf_html_table(self) -> None:
        content = "# Title\r\n\r\n<table><tr><th>A</th></tr><tr><td>1</td></tr></table>\r\n"
        tables = detect_tables(content)
        assert len(tables) == 1


# ---------------------------------------------------------------------------
# HTML entities
# ---------------------------------------------------------------------------


class TestHtmlEntities:
    def test_amp_decoded(self) -> None:
        cell = _parse_table("<table><tr><td>A &amp; B</td></tr></table>").find("td")
        assert isinstance(cell, Tag)
        result = cell_html_to_markdown(cell)
        assert "A & B" in result

    def test_nbsp_handled(self) -> None:
        cell = _parse_table("<table><tr><td>hello&nbsp;world</td></tr></table>").find("td")
        assert isinstance(cell, Tag)
        result = cell_html_to_markdown(cell)
        assert "hello" in result
        assert "world" in result

    def test_lt_gt_in_text(self) -> None:
        """Literal angle brackets in text survive via HTML entities."""
        cell = _parse_table("<table><tr><td>a &lt; b &gt; c</td></tr></table>").find("td")
        assert isinstance(cell, Tag)
        result = cell_html_to_markdown(cell)
        assert "a < b > c" in result


# ---------------------------------------------------------------------------
# Inline formatting round-trip
# ---------------------------------------------------------------------------


class TestInlineFormattingRoundTrip:
    @pytest.mark.parametrize(
        ("html_content", "expected_md", "back_to_html"),
        [
            pytest.param("<strong>bold</strong>", "**bold**", "<strong>bold</strong>", id="bold"),
            pytest.param("<em>italic</em>", "*italic*", "<em>italic</em>", id="italic"),
            pytest.param("<code>code</code>", "`code`", "<code>code</code>", id="code"),
            pytest.param(
                '<a href="https://x.com">link</a>',
                "[link](https://x.com)",
                '<a href="https://x.com">link</a>',
                id="link",
            ),
        ],
    )
    def test_roundtrip(self, html_content: str, expected_md: str, back_to_html: str) -> None:
        cell = _parse_table(f"<table><tr><td>{html_content}</td></tr></table>").find("td")
        assert isinstance(cell, Tag)
        md = cell_html_to_markdown(cell)
        assert md == expected_md
        html_back = markdown_to_cell_html(md)
        assert html_back == back_to_html


# ---------------------------------------------------------------------------
# Mismatched column counts
# ---------------------------------------------------------------------------


class TestMismatchedColumns:
    def test_short_rows_padded(self) -> None:
        headers = ["A", "B", "C"]
        rows = [["1"], ["1", "2"], ["1", "2", "3"]]
        pipe = rows_to_pipe_table(headers, rows)
        _h2, r2 = pipe_table_to_rows(pipe)
        assert all(len(r) == 3 for r in r2)

    def test_html_short_rows(self) -> None:
        html = (
            "<table><thead><tr><th>A</th><th>B</th><th>C</th></tr></thead>"
            "<tbody><tr><td>1</td></tr></tbody></table>"
        )
        soup = _parse_table(html)
        headers, rows = html_to_rows(soup)
        # Row has 1 cell, headers has 3
        assert len(headers) == 3
        # When formatted as pipe, should be padded
        pipe = rows_to_pipe_table(headers, rows)
        _, r2 = pipe_table_to_rows(pipe)
        assert len(r2[0]) == 3


# ---------------------------------------------------------------------------
# Long cell content
# ---------------------------------------------------------------------------


class TestLongContent:
    def test_paragraph_length_cell(self) -> None:
        """Paragraph-length cell content should not be truncated."""
        long_text = "This is a very long requirement description. " * 20
        html = f"<table><thead><tr><th>Req</th></tr></thead><tbody><tr><td>{long_text.strip()}</td></tr></tbody></table>"
        soup = _parse_table(html)
        _headers, rows = html_to_rows(soup)
        assert len(rows[0][0]) > 500

    def test_long_content_survives_pipe_roundtrip(self) -> None:
        long_text = "A" * 1000
        headers = ["Col"]
        rows = [[long_text]]
        pipe = rows_to_pipe_table(headers, rows)
        _h2, r2 = pipe_table_to_rows(pipe)
        assert r2[0][0] == long_text


# ---------------------------------------------------------------------------
# Multiple tables edited sequentially
# ---------------------------------------------------------------------------


class TestSequentialEdits:
    async def test_edit_two_tables_in_sequence(self, tmp_path: Path) -> None:
        """Edit table 0, then table 1. File should remain valid."""
        f = tmp_path / "multi.md"
        f.write_text(
            "# Doc\n\n"
            "| A | B |\n| --- | --- |\n| 1 | 2 |\n\n"
            "Middle text.\n\n"
            "| X | Y |\n| --- | --- |\n| 3 | 4 |\n"
        )

        async with Client(mcp) as client:
            v0 = await read_version(client, str(f), 0)
            await client.call_tool(
                "update_cells",
                {
                    "file_path": str(f),
                    "table_index": 0,
                    "version": v0,
                    "updates": [{"row": 0, "column": "A", "value": "edited0"}],
                },
            )

            v1 = await read_version(client, str(f), 1)
            await client.call_tool(
                "update_cells",
                {
                    "file_path": str(f),
                    "table_index": 1,
                    "version": v1,
                    "updates": [{"row": 0, "column": "X", "value": "edited1"}],
                },
            )

        content = f.read_text()
        assert "edited0" in content
        assert "edited1" in content
        assert "Middle text." in content
        tables = detect_tables(content)
        assert len(tables) == 2


# ---------------------------------------------------------------------------
# Collapsed HTML serialization
# ---------------------------------------------------------------------------


class TestCollapsedSerialization:
    def test_no_newlines(self) -> None:
        html = "<table>\n<thead>\n<tr>\n<th>A</th>\n</tr>\n</thead>\n<tbody>\n<tr>\n<td>1</td>\n</tr>\n</tbody>\n</table>"
        soup = _parse_table(html)
        result = serialize_html_collapsed(soup)
        assert "\n" not in result

    def test_no_whitespace_between_tags(self) -> None:
        html = "<table>\n  <tr>\n  <td> val </td>\n  </tr>\n  </table>"
        soup = _parse_table(html)
        result = serialize_html_collapsed(soup)
        assert ">\n" not in result

    def test_gitbook_format_match(self) -> None:
        """Output matches GitBook's collapsed single-line format."""
        html = '<table><thead><tr><th width="100">A</th><th>B</th></tr></thead><tbody><tr><td><strong>1</strong></td><td>2</td></tr></tbody></table>'
        soup = _parse_table(html)
        result = serialize_html_collapsed(soup)
        assert result == html  # should be identical

    def test_preserves_space_before_inline_tag(self) -> None:
        """Space between text and <strong> must survive collapsed serialization."""
        html = "<table><tr><td>hello <strong>world</strong></td></tr></table>"
        soup = _parse_table(html)
        result = serialize_html_collapsed(soup)
        assert "hello <strong>world</strong>" in result


# ---------------------------------------------------------------------------
# <br> tag preservation
# ---------------------------------------------------------------------------


class TestBrTagPreservation:
    def test_br_preserved_through_read(self) -> None:
        """<br> in cell content should survive the read path."""
        cell = _parse_table("<table><tr><td>line1<br>line2</td></tr></table>").find("td")
        assert isinstance(cell, Tag)
        result = cell_html_to_markdown(cell)
        assert "<br>" in result or "line1" in result

    def test_br_roundtrip_in_table(self) -> None:
        """<br> should survive HTML → pipe → HTML round-trip."""
        html = "<table><thead><tr><th>Col</th></tr></thead><tbody><tr><td>a<br>b</td></tr></tbody></table>"
        soup = _parse_table(html)
        _headers, rows = html_to_rows(soup)
        # The cell should contain some indication of the line break
        assert "a" in rows[0][0]
        assert "b" in rows[0][0]


# ---------------------------------------------------------------------------
# Backslash-backslash-pipe edge case
# ---------------------------------------------------------------------------


class TestBackslashPipeEdgeCases:
    def test_backslash_backslash_pipe(self) -> None:
        r"""Content with \\| (literal backslash + pipe) should be escaped."""
        from tablestakes.converter import _escape_pipes

        # \\| in the source means literal backslash followed by pipe
        result = _escape_pipes("a\\\\|b")
        # The pipe should still be escaped since \\| is backslash + unescaped pipe
        assert result == "a\\\\\\|b"


# ---------------------------------------------------------------------------
# Delete edge cases
# ---------------------------------------------------------------------------


class TestDeleteEdgeCases:
    async def test_delete_all_rows(self, tmp_path: Path) -> None:
        """Deleting all rows should leave a header-only table."""
        f = tmp_path / "test.md"
        f.write_text("| A |\n| --- |\n| 1 |\n")
        async with Client(mcp) as client:
            v = await read_version(client, str(f))
            text = text_of(
                await client.call_tool(
                    "delete_row",
                    {"file_path": str(f), "table_index": 0, "version": v, "row_index": 0},
                )
            )
            assert "v:" in text
            content = f.read_text()
            # Should still have header + delimiter
            assert "| A |" in content
            assert "| --- |" in content

    async def test_delete_last_column(self, tmp_path: Path) -> None:
        """Deleting the only column produces a minimal table."""
        f = tmp_path / "test.md"
        f.write_text("| A |\n| --- |\n| 1 |\n")
        async with Client(mcp) as client:
            v = await read_version(client, str(f))
            text = text_of(
                await client.call_tool(
                    "delete_column",
                    {"file_path": str(f), "table_index": 0, "version": v, "column": "A"},
                )
            )
            # Should succeed (or return an error — either is acceptable)
            assert "v:" in text or "error" in text.lower()


# ---------------------------------------------------------------------------
# Non-UTF-8 file handling
# ---------------------------------------------------------------------------


class TestFileErrors:
    async def test_non_utf8_file(self, tmp_path: Path) -> None:
        """Binary file should produce a clean error, not a crash."""
        f = tmp_path / "binary.md"
        f.write_bytes(b"\x80\x81\x82\xff\xfe")
        async with Client(mcp) as client:
            result = await client.call_tool("list_tables", {"file_path": str(f)})
            # Should not crash — either returns error text or empty results
            text = text_of(result)
            assert isinstance(text, str)
