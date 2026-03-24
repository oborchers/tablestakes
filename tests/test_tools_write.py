"""Tests for write MCP tools via FastMCP in-memory Client."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastmcp import Client

from tablestakes.server import mcp
from tests.conftest import read_version, text_of, version_of

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def pipe_md(tmp_path: Path) -> Path:
    f = tmp_path / "test.md"
    f.write_text(
        "# Test\n\n"
        "| Name | Age | City |\n"
        "| --- | --- | --- |\n"
        "| Alice | 30 | NYC |\n"
        "| Bob | 25 | LA |\n"
        "| Carol | 35 | SF |\n"
        "\nEnd.\n"
    )
    return f


class TestUpdateCells:
    async def test_update_single_cell(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            text = text_of(
                await client.call_tool(
                    "update_cells",
                    {
                        "file_path": str(pipe_md),
                        "table_index": 0,
                        "version": v,
                        "updates": [{"row": 0, "column": "Age", "value": "31"}],
                    },
                )
            )
            assert "v:" in text
            assert "31" in pipe_md.read_text()

    async def test_update_batch(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            await client.call_tool(
                "update_cells",
                {
                    "file_path": str(pipe_md),
                    "table_index": 0,
                    "version": v,
                    "updates": [
                        {"row": 0, "column": "A", "value": "Alicia"},
                        {"row": 1, "column": "City", "value": "Boston"},
                    ],
                },
            )
            content = pipe_md.read_text()
            assert "Alicia" in content
            assert "Boston" in content

    async def test_update_by_composite(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            await client.call_tool(
                "update_cells",
                {
                    "file_path": str(pipe_md),
                    "table_index": 0,
                    "version": v,
                    "updates": [{"row": 2, "column": "C:City", "value": "Denver"}],
                },
            )
            assert "Denver" in pipe_md.read_text()

    async def test_stale_read(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "update_cells",
                    {
                        "file_path": str(pipe_md),
                        "table_index": 0,
                        "version": "wrong_version",
                        "updates": [{"row": 0, "column": "Name", "value": "X"}],
                    },
                )
            )
            assert json.loads(text)["error"] == "STALE_READ"

    async def test_row_out_of_range(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            text = text_of(
                await client.call_tool(
                    "update_cells",
                    {
                        "file_path": str(pipe_md),
                        "table_index": 0,
                        "version": v,
                        "updates": [{"row": 99, "column": "Name", "value": "X"}],
                    },
                )
            )
            assert json.loads(text)["error"] == "EDIT_ERROR"

    async def test_column_not_found(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            text = text_of(
                await client.call_tool(
                    "update_cells",
                    {
                        "file_path": str(pipe_md),
                        "table_index": 0,
                        "version": v,
                        "updates": [{"row": 0, "column": "Nonexistent", "value": "X"}],
                    },
                )
            )
            assert json.loads(text)["error"] == "EDIT_ERROR"

    async def test_version_changes(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v1 = await read_version(client, str(pipe_md))
            text = text_of(
                await client.call_tool(
                    "update_cells",
                    {
                        "file_path": str(pipe_md),
                        "table_index": 0,
                        "version": v1,
                        "updates": [{"row": 0, "column": "Name", "value": "NewName"}],
                    },
                )
            )
            assert version_of(text) != v1

    async def test_gitbook_attrs_preserved(self, gitbook_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(gitbook_md))
            await client.call_tool(
                "update_cells",
                {
                    "file_path": str(gitbook_md),
                    "table_index": 0,
                    "version": v,
                    "updates": [{"row": 0, "column": "B", "value": "Should"}],
                },
            )
            content = gitbook_md.read_text()
            assert 'width="395.0811767578125"' in content
            assert "Should" in content


class TestInsertRow:
    async def test_append_row(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            text = text_of(
                await client.call_tool(
                    "insert_row",
                    {
                        "file_path": str(pipe_md),
                        "table_index": 0,
                        "version": v,
                        "position": -1,
                        "values": {"Name": "Dave", "Age": "40", "City": "Chicago"},
                    },
                )
            )
            assert "v:" in text
            assert "Dave" in pipe_md.read_text()

    async def test_insert_at_position(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            await client.call_tool(
                "insert_row",
                {
                    "file_path": str(pipe_md),
                    "table_index": 0,
                    "version": v,
                    "position": 1,
                    "values": {"Name": "Eve"},
                },
            )
            content = pipe_md.read_text()
            assert content.index("Alice") < content.index("Eve") < content.index("Bob")

    async def test_returns_version_only(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            text = text_of(
                await client.call_tool(
                    "insert_row",
                    {
                        "file_path": str(pipe_md),
                        "table_index": 0,
                        "version": v,
                        "position": -1,
                        "values": {"Name": "X"},
                    },
                )
            )
            assert text.startswith("v:")
            assert "| ---" not in text


class TestDeleteRow:
    async def test_delete_row(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            await client.call_tool(
                "delete_row",
                {
                    "file_path": str(pipe_md),
                    "table_index": 0,
                    "version": v,
                    "row_index": 1,
                },
            )
            content = pipe_md.read_text()
            assert "Bob" not in content
            assert "Alice" in content
            assert "Carol" in content

    async def test_delete_out_of_range(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            text = text_of(
                await client.call_tool(
                    "delete_row",
                    {
                        "file_path": str(pipe_md),
                        "table_index": 0,
                        "version": v,
                        "row_index": 99,
                    },
                )
            )
            assert json.loads(text)["error"] == "EDIT_ERROR"


class TestReplaceTable:
    async def test_replace_pipe(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            text = text_of(
                await client.call_tool(
                    "replace_table",
                    {
                        "file_path": str(pipe_md),
                        "table_index": 0,
                        "version": v,
                        "new_content": "| X | Y |\n| --- | --- |\n| 1 | 2 |",
                    },
                )
            )
            assert "v:" in text
            content = pipe_md.read_text()
            assert "Alice" not in content
            assert "X" in content

    async def test_replace_gitbook_preserves_format(self, gitbook_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(gitbook_md))
            await client.call_tool(
                "replace_table",
                {
                    "file_path": str(gitbook_md),
                    "table_index": 0,
                    "version": v,
                    "new_content": "| Req | Pri | Dep | P123 |\n| --- | --- | --- | --- |\n| New | Must | None | 1 |",
                },
            )
            content = gitbook_md.read_text()
            assert "<table>" in content
            assert "New" in content


class TestCreateTable:
    async def test_create_html_table(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Doc\n\nSome text.\n")
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "create_table",
                    {
                        "file_path": str(f),
                        "content": "| Name | Age |\n| --- | --- |\n| Alice | 30 |",
                    },
                )
            )
            assert "v:" in text
            content = f.read_text()
            assert "<table>" in content
            assert "<td>Alice</td>" in content
            assert "Some text." in content

    async def test_create_pipe_table(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Doc\n")
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "create_table",
                    {
                        "file_path": str(f),
                        "content": "| X | Y |\n| --- | --- |\n| 1 | 2 |",
                        "format": "pipe",
                    },
                )
            )
            assert "v:" in text
            content = f.read_text()
            assert "| X | Y |" in content
            assert "<table>" not in content

    async def test_append_to_existing(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Doc\n\nParagraph one.\n\nParagraph two.\n")
        async with Client(mcp) as client:
            await client.call_tool(
                "create_table",
                {
                    "file_path": str(f),
                    "content": "| A | B |\n| --- | --- |\n| 1 | 2 |",
                },
            )
            content = f.read_text()
            assert "Paragraph one." in content
            assert "Paragraph two." in content
            assert content.index("Paragraph two.") < content.index("<table>")

    async def test_insert_at_position(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Doc\n\nBefore.\n\nAfter.\n")
        async with Client(mcp) as client:
            await client.call_tool(
                "create_table",
                {
                    "file_path": str(f),
                    "content": "| A | B |\n| --- | --- |\n| 1 | 2 |",
                    "position": 3,
                },
            )
            content = f.read_text()
            assert content.index("Before.") < content.index("<table>") < content.index("After.")

    async def test_created_table_discoverable(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Doc\n")
        async with Client(mcp) as client:
            await client.call_tool(
                "create_table",
                {
                    "file_path": str(f),
                    "content": "| Name | Age |\n| --- | --- |\n| Alice | 30 |",
                },
            )
            list_text = text_of(await client.call_tool("list_tables", {"file_path": str(f)}))
            assert "1 tables" in list_text
            assert "Name" in list_text

    async def test_create_in_new_file(self, tmp_path: Path) -> None:
        f = tmp_path / "new.md"
        assert not f.exists()
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "create_table",
                    {
                        "file_path": str(f),
                        "content": "| A | B |\n| --- | --- |\n| 1 | 2 |",
                    },
                )
            )
            assert "v:" in text
            assert f.exists()
            assert "<table>" in f.read_text()

    async def test_invalid_content(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Doc\n")
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "create_table",
                    {"file_path": str(f), "content": "not a table"},
                )
            )
            assert json.loads(text)["error"] == "INVALID_CONTENT"

    async def test_invalid_format(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Doc\n")
        async with Client(mcp) as client:
            with pytest.raises(Exception, match="'html' or 'pipe'"):
                await client.call_tool(
                    "create_table",
                    {
                        "file_path": str(f),
                        "content": "| A |\n| --- |\n| 1 |",
                        "format": "xml",
                    },
                )


class TestPipeEscapingViaTools:
    """Bug A: pipes, backslashes, and pre-existing escapes in cell values."""

    async def test_update_cells_with_pipe_value(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            await client.call_tool(
                "update_cells",
                {
                    "file_path": str(pipe_md),
                    "table_index": 0,
                    "version": v,
                    "updates": [{"row": 0, "column": "City", "value": "has|pipe"}],
                },
            )
            result = text_of(
                await client.call_tool(
                    "read_table", {"file_path": str(pipe_md), "table_index": 0}
                )
            )
            assert "has\\|pipe" in result
            assert "3c" in result

    async def test_existing_escaped_pipes_survive_edit(self, tmp_path: Path) -> None:
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
            assert "Alice\\|Bob" in result
            assert "2c" in result


class TestAlignmentViaTools:
    """Bug C: alignment markers must survive edits."""

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
            assert ":---" in content
            assert "---:" in content

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


class TestCreateTablePositionGuard:
    """Bug F: create_table must not split existing tables."""

    async def test_position_inside_table_rejected(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text(
            "# Test\n\n"
            "| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |\n"
            "\nEnd.\n"
        )
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "create_table",
                    {
                        "file_path": str(f),
                        "content": "| X |\n| --- |\n| new |",
                        "position": 4,
                    },
                )
            )
            assert json.loads(text)["error"] == "POSITION_INSIDE_TABLE"

    async def test_position_between_tables_ok(self, tmp_path: Path) -> None:
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
                        "position": 4,
                    },
                )
            )
            assert "v:" in text


class TestHeaderlessHtml:
    """Bug G: editing header-less HTML tables must not inject <thead>."""

    async def test_tbody_no_thead_preserved(self, tmp_path: Path) -> None:
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
            assert "Alice" in content

    async def test_no_tbody_no_thead_preserved(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text(
            "# Test\n\n"
            "<table>"
            "<tr><td>Alice</td><td>100</td></tr>"
            "<tr><td>Bob</td><td>200</td></tr>"
            "</table>\n"
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


class TestBomHandling:
    """Bug H: UTF-8 BOM must not corrupt write offsets."""

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
            raw = f.read_bytes()
            assert raw.startswith(b"\xef\xbb\xbf")


class TestHtmlElementRoundTrip:
    """Bug I: <img>, <del>, <sub>, <sup> must survive edits."""

    async def test_img_survives(self, tmp_path: Path) -> None:
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
            assert "<img" in content
            assert "a.png" in content

    async def test_del_survives(self, tmp_path: Path) -> None:
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

    async def test_sub_survives(self, tmp_path: Path) -> None:
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

    async def test_sup_survives(self, tmp_path: Path) -> None:
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


class TestNumericColumnNamesViaTool:
    """Bug J: columns named "2024" must be reachable by name."""

    async def test_update_cells_with_numeric_column_name(self, tmp_path: Path) -> None:
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
            assert "150" in result


class TestToolRegistration:
    async def test_write_tools_registered(self) -> None:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            names = [t.name for t in tools]
            assert "update_cells" in names
            assert "insert_row" in names
            assert "delete_row" in names
            assert "replace_table" in names
            assert "create_table" in names
