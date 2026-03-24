"""Tests for column MCP tools via FastMCP in-memory Client."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import pytest
from fastmcp import Client

from tablestakes.server import mcp
from tests.conftest import read_version, text_of

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def pipe_md(tmp_path: Path) -> Path:
    f = tmp_path / "test.md"
    f.write_text("# Test\n\n| Name | Age |\n| --- | --- |\n| Alice | 30 |\n| Bob | 25 |\n")
    return f


class TestInsertColumn:
    async def test_append_column(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            text = text_of(
                await client.call_tool(
                    "insert_column",
                    {
                        "file_path": str(pipe_md),
                        "table_index": 0,
                        "version": v,
                        "name": "City",
                        "default_value": "N/A",
                    },
                )
            )
            assert "v:" in text
            content = pipe_md.read_text()
            assert "City" in content
            assert "N/A" in content

    async def test_insert_at_position(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            await client.call_tool(
                "insert_column",
                {
                    "file_path": str(pipe_md),
                    "table_index": 0,
                    "version": v,
                    "name": "ID",
                    "position": 0,
                },
            )
            content = pipe_md.read_text()
            assert content.index("ID") < content.index("Name")

    async def test_default_empty(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            await client.call_tool(
                "insert_column",
                {
                    "file_path": str(pipe_md),
                    "table_index": 0,
                    "version": v,
                    "name": "Notes",
                },
            )
            assert "Notes" in pipe_md.read_text()


class TestDeleteColumn:
    async def test_delete_by_name(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            await client.call_tool(
                "delete_column",
                {
                    "file_path": str(pipe_md),
                    "table_index": 0,
                    "version": v,
                    "column": "Age",
                },
            )
            content = pipe_md.read_text()
            assert "Age" not in content
            assert "Name" in content

    async def test_delete_by_letter(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            await client.call_tool(
                "delete_column",
                {
                    "file_path": str(pipe_md),
                    "table_index": 0,
                    "version": v,
                    "column": "A",
                },
            )
            content = pipe_md.read_text()
            assert "Name" not in content
            assert "Age" in content

    async def test_delete_not_found(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            text = text_of(
                await client.call_tool(
                    "delete_column",
                    {
                        "file_path": str(pipe_md),
                        "table_index": 0,
                        "version": v,
                        "column": "Nonexistent",
                    },
                )
            )
            assert "EDIT_ERROR" in text


class TestRenameColumn:
    async def test_rename(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            text = text_of(
                await client.call_tool(
                    "rename_column",
                    {
                        "file_path": str(pipe_md),
                        "table_index": 0,
                        "version": v,
                        "old_name": "Name",
                        "new_name": "Full Name",
                    },
                )
            )
            assert "v:" in text
            content = pipe_md.read_text()
            assert "Full Name" in content
            assert "Alice" in content

    async def test_rename_by_letter(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            await client.call_tool(
                "rename_column",
                {
                    "file_path": str(pipe_md),
                    "table_index": 0,
                    "version": v,
                    "old_name": "B",
                    "new_name": "Years",
                },
            )
            content = pipe_md.read_text()
            assert "Years" in content
            assert "30" in content

    async def test_rename_preserves_gitbook_attrs(self, gitbook_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(gitbook_md))
            await client.call_tool(
                "rename_column",
                {
                    "file_path": str(gitbook_md),
                    "table_index": 0,
                    "version": v,
                    "old_name": "Requirement",
                    "new_name": "Req",
                },
            )
            content = gitbook_md.read_text()
            assert 'width="395.0811767578125"' in content
            assert "Req" in content


class TestDeleteLastColumn:
    """Bug B: deleting the only column must be rejected."""

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


class TestRenameColumnWithPipe:
    """Bug A: pipe characters in column names must be escaped."""

    async def test_rename_to_name_with_pipe(self, tmp_path: Path) -> None:
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
            assert "2c" in result


class TestInsertColumnGitBookAttrs:
    """Bug E: GitBook attributes must follow column content, not position."""

    async def test_insert_column_attrs_follow_content(self, gitbook_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(gitbook_md))
            original = gitbook_md.read_text()
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
            ths = re.findall(r"<th([^>]*)>([^<]*)</th>", content)
            if ths:
                new_col_attrs = ths[0][0]
                assert "width=" not in new_col_attrs or not first_width


class TestToolRegistration:
    async def test_column_tools_registered(self) -> None:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            names = [t.name for t in tools]
            assert "insert_column" in names
            assert "delete_column" in names
            assert "rename_column" in names
