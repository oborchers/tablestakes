"""Tests for bug fixes from adversarial stress testing (BUG.md).

Each test class corresponds to a bug class (A through J).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastmcp import Client

from tablestakes.converter import (
    _escape_pipe_cell,
    _unescape_pipe_cell,
    parse_alignment,
    pipe_table_to_rows,
    resolve_column,
    rows_to_pipe_table,
)
from tablestakes.models import ColumnDescriptor
from tablestakes.parser import detect_tables
from tablestakes.server import mcp
from tests.conftest import read_version, text_of

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Bug A: Pipe-table escape failures
# ---------------------------------------------------------------------------


class TestBugA:
    """Pipe characters, backslashes, and newlines must be escaped on write."""

    def test_escape_pipe_cell(self) -> None:
        assert _escape_pipe_cell("a|b") == "a\\|b"

    def test_escape_backslash(self) -> None:
        assert _escape_pipe_cell("a\\b") == "a\\\\b"

    def test_escape_newline(self) -> None:
        assert _escape_pipe_cell("line1\nline2") == "line1<br>line2"

    def test_escape_backslash_pipe(self) -> None:
        assert _escape_pipe_cell("a\\|b") == "a\\\\\\|b"

    def test_unescape_round_trip(self) -> None:
        original = "has|pipe and \\backslash"
        assert _unescape_pipe_cell(_escape_pipe_cell(original)) == original

    def test_pipe_in_cell_round_trips_via_table(self) -> None:
        headers = ["Name", "Notes"]
        rows = [["Alice", "a|b|c"], ["Bob", "ok"]]
        table_str = rows_to_pipe_table(headers, rows)
        parsed_h, parsed_r = pipe_table_to_rows(table_str)
        assert parsed_h == headers
        assert parsed_r == rows

    def test_backslash_in_cell_round_trips(self) -> None:
        headers = ["Path"]
        rows = [["C:\\Users\\test"], ["back\\slash"]]
        table_str = rows_to_pipe_table(headers, rows)
        _, parsed_r = pipe_table_to_rows(table_str)
        assert parsed_r[0] == ["C:\\Users\\test"]
        assert parsed_r[1] == ["back\\slash"]

    def test_newline_in_cell_round_trips(self) -> None:
        headers = ["Content"]
        rows = [["line1\nline2"]]
        table_str = rows_to_pipe_table(headers, rows)
        # Newlines become <br> in pipe format
        assert "\\n" not in table_str
        assert "<br>" in table_str

    def test_pipe_in_header_round_trips(self) -> None:
        headers = ["Col|A", "Col|B"]
        rows = [["1", "2"]]
        table_str = rows_to_pipe_table(headers, rows)
        parsed_h, _ = pipe_table_to_rows(table_str)
        assert parsed_h == headers

    async def test_update_cells_with_pipe_value(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("| Name | Notes |\n| --- | --- |\n| Alice | ok |\n")
        async with Client(mcp) as client:
            v = await read_version(client, str(f))
            await client.call_tool(
                "update_cells",
                {
                    "file_path": str(f),
                    "table_index": 0,
                    "version": v,
                    "updates": [{"row": 0, "column": "Notes", "value": "has|pipe"}],
                },
            )
            result = text_of(
                await client.call_tool(
                    "read_table", {"file_path": str(f), "table_index": 0}
                )
            )
            # read_table shows raw pipe format — escaped as has\|pipe
            assert "has\\|pipe" in result
            # Verify no column corruption — still 2 columns
            assert "2c" in result

    async def test_rename_column_with_pipe(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("| X | Y |\n| --- | --- |\n| 1 | 2 |\n")
        async with Client(mcp) as client:
            v = await read_version(client, str(f))
            await client.call_tool(
                "rename_column",
                {
                    "file_path": str(f),
                    "table_index": 0,
                    "version": v,
                    "old_name": "X",
                    "new_name": "Col|X",
                },
            )
            result = text_of(
                await client.call_tool(
                    "read_table", {"file_path": str(f), "table_index": 0}
                )
            )
            # Should still be 2 columns, not 3
            assert "2c" in result

    async def test_existing_escaped_pipes_survive_edit(self, tmp_path: Path) -> None:
        """Pre-existing \\| in file must survive edits to other cells."""
        f = tmp_path / "test.md"
        f.write_text("| Name | Notes |\n| --- | --- |\n| Alice\\|Bob | ok |\n")
        async with Client(mcp) as client:
            v = await read_version(client, str(f))
            await client.call_tool(
                "update_cells",
                {
                    "file_path": str(f),
                    "table_index": 0,
                    "version": v,
                    "updates": [{"row": 0, "column": "Notes", "value": "edited"}],
                },
            )
            result = text_of(
                await client.call_tool(
                    "read_table", {"file_path": str(f), "table_index": 0}
                )
            )
            # Pipe should survive (shown escaped in raw pipe output)
            assert "Alice\\|Bob" in result
            assert "2c" in result


# ---------------------------------------------------------------------------
# Bug B: Delete last column destroys table
# ---------------------------------------------------------------------------


class TestBugB:
    async def test_delete_last_column_rejected(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("| Solo |\n| --- |\n| one |\n| two |\n")
        async with Client(mcp) as client:
            v = await read_version(client, str(f))
            text = text_of(
                await client.call_tool(
                    "delete_column",
                    {
                        "file_path": str(f),
                        "table_index": 0,
                        "version": v,
                        "column": "A",
                    },
                )
            )
            assert json.loads(text)["error"] == "EDIT_ERROR"
            assert "last remaining" in json.loads(text)["message"].lower()

    async def test_delete_second_to_last_succeeds(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("| A | B |\n| --- | --- |\n| 1 | 2 |\n")
        async with Client(mcp) as client:
            v = await read_version(client, str(f))
            text = text_of(
                await client.call_tool(
                    "delete_column",
                    {
                        "file_path": str(f),
                        "table_index": 0,
                        "version": v,
                        "column": "B",
                    },
                )
            )
            assert "v:" in text


# ---------------------------------------------------------------------------
# Bug C: Alignment markers stripped
# ---------------------------------------------------------------------------


class TestBugC:
    def test_alignment_parsing(self) -> None:
        content = "| L | C | R | N |\n| :--- | :---: | ---: | --- |\n| 1 | 2 | 3 | 4 |\n"
        alignments = parse_alignment(content)
        assert alignments == ["left", "center", "right", "none"]

    def test_alignment_preserved_in_round_trip(self) -> None:
        headers = ["Left", "Center", "Right", "Default"]
        rows = [["a", "b", "c", "d"]]
        alignments = ["left", "center", "right", "none"]
        table_str = rows_to_pipe_table(headers, rows, alignments=alignments)
        assert ":---" in table_str
        assert ":---:" in table_str
        assert "---:" in table_str

    async def test_alignment_preserved_through_update_cells(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("| Name | Age |\n| :--- | ---: |\n| Alice | 30 |\n")
        async with Client(mcp) as client:
            v = await read_version(client, str(f))
            await client.call_tool(
                "update_cells",
                {
                    "file_path": str(f),
                    "table_index": 0,
                    "version": v,
                    "updates": [{"row": 0, "column": "Age", "value": "31"}],
                },
            )
            content = f.read_text()
            assert ":---" in content  # left alignment preserved
            assert "---:" in content  # right alignment preserved

    async def test_alignment_from_replace_table(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("| X |\n| --- |\n| 1 |\n")
        async with Client(mcp) as client:
            v = await read_version(client, str(f))
            await client.call_tool(
                "replace_table",
                {
                    "file_path": str(f),
                    "table_index": 0,
                    "version": v,
                    "new_content": "| A | B |\n| :---: | ---: |\n| 1 | 2 |",
                },
            )
            content = f.read_text()
            assert ":---:" in content
            assert "---:" in content

    async def test_alignment_from_create_table(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("# Doc\n")
        async with Client(mcp) as client:
            await client.call_tool(
                "create_table",
                {
                    "file_path": str(f),
                    "content": "| L | R |\n| :--- | ---: |\n| a | b |",
                    "format": "pipe",
                },
            )
            content = f.read_text()
            assert ":---" in content
            assert "---:" in content


# ---------------------------------------------------------------------------
# Bug D: Phantom table from <table> inside pipe cell
# ---------------------------------------------------------------------------


class TestBugD:
    def test_html_inside_pipe_cell_not_detected(self) -> None:
        content = (
            "| Name | Data |\n"
            "| --- | --- |\n"
            "| Alice | <table><tr><td>nested</td></tr></table> |\n"
        )
        tables = detect_tables(content)
        assert len(tables) == 1  # Only the pipe table, no phantom

    def test_real_html_and_pipe_still_detected(self) -> None:
        content = (
            "| A | B |\n| --- | --- |\n| 1 | 2 |\n\n"
            "<table><tr><td>real</td></tr></table>\n"
        )
        tables = detect_tables(content)
        assert len(tables) == 2


# ---------------------------------------------------------------------------
# Bug E: GitBook attributes misassigned on structural changes
# ---------------------------------------------------------------------------


class TestBugE:
    async def test_insert_column_attrs_follow_content(
        self, gitbook_md: Path
    ) -> None:
        async with Client(mcp) as client:
            # Read original to get attrs
            v = await read_version(client, str(gitbook_md))
            original = gitbook_md.read_text()
            # Get first th's width attribute
            first_width = 'width="' in original

            await client.call_tool(
                "insert_column",
                {
                    "file_path": str(gitbook_md),
                    "table_index": 0,
                    "version": v,
                    "name": "NewCol",
                    "position": 0,
                },
            )
            content = gitbook_md.read_text()
            # NewCol at position 0 should NOT have stolen the first column's width
            # The first <th> (NewCol) should have no width attribute
            import re

            ths = re.findall(r"<th([^>]*)>([^<]*)</th>", content)
            if ths:
                new_col_attrs = ths[0][0]
                assert "width=" not in new_col_attrs or not first_width


# ---------------------------------------------------------------------------
# Bug F: create_table splits existing table
# ---------------------------------------------------------------------------


class TestBugF:
    async def test_create_table_inside_existing_rejected(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text(
            "# Test\n\n"
            "| A | B |\n"
            "| --- | --- |\n"
            "| 1 | 2 |\n"
            "| 3 | 4 |\n"
            "| 5 | 6 |\n"
            "\nEnd.\n"
        )
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "create_table",
                    {
                        "file_path": str(f),
                        "content": "| X |\n| --- |\n| new |",
                        "position": 4,  # Inside the pipe table
                    },
                )
            )
            assert json.loads(text)["error"] == "POSITION_INSIDE_TABLE"

    async def test_create_table_between_tables_ok(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text(
            "| A |\n| --- |\n| 1 |\n\nSeparator\n\n| B |\n| --- |\n| 2 |\n"
        )
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "create_table",
                    {
                        "file_path": str(f),
                        "content": "| X |\n| --- |\n| new |",
                        "format": "pipe",
                        "position": 4,  # On the separator line
                    },
                )
            )
            assert "v:" in text


# ---------------------------------------------------------------------------
# Bug G: Synthetic <thead> on header-less tables
# ---------------------------------------------------------------------------


class TestBugG:
    async def test_headerless_html_no_thead_injected(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text(
            "# Test\n\n"
            "<table><tbody>"
            "<tr><td>Alice</td><td>100</td></tr>"
            "<tr><td>Bob</td><td>200</td></tr>"
            "</tbody></table>\n"
        )
        async with Client(mcp) as client:
            v = await read_version(client, str(f))
            await client.call_tool(
                "update_cells",
                {
                    "file_path": str(f),
                    "table_index": 0,
                    "version": v,
                    "updates": [{"row": 0, "column": "B", "value": "999"}],
                },
            )
            content = f.read_text()
            assert "<thead>" not in content
            assert "999" in content


# ---------------------------------------------------------------------------
# Bug H: UTF-8 BOM causes write corruption
# ---------------------------------------------------------------------------


class TestBugH:
    async def test_bom_file_edit_correct(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_bytes(
            "\ufeff# Test\n\n| Name | Age |\n| --- | --- |\n| Alice | 30 |\n".encode()
        )
        async with Client(mcp) as client:
            v = await read_version(client, str(f))
            text = text_of(
                await client.call_tool(
                    "update_cells",
                    {
                        "file_path": str(f),
                        "table_index": 0,
                        "version": v,
                        "updates": [{"row": 0, "column": "Age", "value": "31"}],
                    },
                )
            )
            assert "v:" in text
            content = f.read_text(encoding="utf-8")
            assert "31" in content
            # BOM should be preserved
            raw = f.read_bytes()
            assert raw.startswith(b"\xef\xbb\xbf")
            # No stray pipe characters
            lines = content.split("\n")
            for line in lines:
                if line.startswith("|"):
                    # Each data line should have exactly 3 pipes (2 columns)
                    assert line.count("|") <= 4  # | Name | Age |


# ---------------------------------------------------------------------------
# Bug I: Lossy markdownify for <img>, <del>, <sub>, <sup>
# ---------------------------------------------------------------------------


class TestBugI:
    async def test_img_round_trip(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text(
            "<table><thead><tr><th>Name</th><th>Photo</th></tr></thead>"
            '<tbody><tr><td>Alice</td><td><img src="a.png" alt="pic"/></td></tr>'
            "</tbody></table>\n"
        )
        async with Client(mcp) as client:
            v = await read_version(client, str(f))
            await client.call_tool(
                "update_cells",
                {
                    "file_path": str(f),
                    "table_index": 0,
                    "version": v,
                    "updates": [{"row": 0, "column": "Name", "value": "Bob"}],
                },
            )
            content = f.read_text()
            # <img> should survive (not become !<a>)
            assert "<img" in content
            assert "a.png" in content

    async def test_del_round_trip(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text(
            "<table><thead><tr><th>A</th><th>B</th></tr></thead>"
            "<tbody><tr><td><del>removed</del></td><td>keep</td></tr>"
            "</tbody></table>\n"
        )
        async with Client(mcp) as client:
            v = await read_version(client, str(f))
            await client.call_tool(
                "update_cells",
                {
                    "file_path": str(f),
                    "table_index": 0,
                    "version": v,
                    "updates": [{"row": 0, "column": "B", "value": "edited"}],
                },
            )
            content = f.read_text()
            assert "<del>" in content
            assert "removed" in content

    async def test_sub_round_trip(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text(
            "<table><thead><tr><th>Formula</th><th>Name</th></tr></thead>"
            "<tbody><tr><td>H<sub>2</sub>O</td><td>Water</td></tr>"
            "</tbody></table>\n"
        )
        async with Client(mcp) as client:
            v = await read_version(client, str(f))
            await client.call_tool(
                "update_cells",
                {
                    "file_path": str(f),
                    "table_index": 0,
                    "version": v,
                    "updates": [{"row": 0, "column": "Name", "value": "Agua"}],
                },
            )
            content = f.read_text()
            assert "<sub>" in content
            assert "H<sub>2</sub>O" in content or "H<sub>2</sub>o" in content.lower()

    async def test_sup_round_trip(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text(
            "<table><thead><tr><th>Note</th><th>Val</th></tr></thead>"
            "<tbody><tr><td>x<sup>2</sup></td><td>4</td></tr>"
            "</tbody></table>\n"
        )
        async with Client(mcp) as client:
            v = await read_version(client, str(f))
            await client.call_tool(
                "update_cells",
                {
                    "file_path": str(f),
                    "table_index": 0,
                    "version": v,
                    "updates": [{"row": 0, "column": "Val", "value": "9"}],
                },
            )
            content = f.read_text()
            assert "<sup>" in content


# ---------------------------------------------------------------------------
# Bug J: Numeric column names shadowed by index interpretation
# ---------------------------------------------------------------------------


class TestBugJ:
    def test_numeric_column_name_resolved_by_name(self) -> None:
        columns = [
            ColumnDescriptor.from_header(0, "1"),
            ColumnDescriptor.from_header(1, "2"),
            ColumnDescriptor.from_header(2, "3"),
        ]
        # "1" should match column A (name "1"), not index 1 (column B)
        assert resolve_column("1", columns) == 0
        assert resolve_column("2", columns) == 1
        assert resolve_column("3", columns) == 2

    def test_numeric_fallback_when_no_name_match(self) -> None:
        columns = [
            ColumnDescriptor.from_header(0, "Name"),
            ColumnDescriptor.from_header(1, "Age"),
            ColumnDescriptor.from_header(2, "City"),
        ]
        # "0" is not a column name, so falls back to index 0
        assert resolve_column("0", columns) == 0
        assert resolve_column("1", columns) == 1

    async def test_numeric_column_name_via_update_cells(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("| 2024 | 2025 |\n| --- | --- |\n| 100 | 200 |\n")
        async with Client(mcp) as client:
            v = await read_version(client, str(f))
            text = text_of(
                await client.call_tool(
                    "update_cells",
                    {
                        "file_path": str(f),
                        "table_index": 0,
                        "version": v,
                        "updates": [{"row": 0, "column": "2024", "value": "150"}],
                    },
                )
            )
            assert "v:" in text
            result = text_of(
                await client.call_tool(
                    "read_table", {"file_path": str(f), "table_index": 0}
                )
            )
            # "2024" column should have 150, not the other column
            assert "150" in result
