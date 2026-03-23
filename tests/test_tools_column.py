"""Tests for column MCP tools via FastMCP in-memory Client."""

from __future__ import annotations

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


class TestAddColumn:
    async def test_append_column(self, pipe_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(pipe_md))
            text = text_of(
                await client.call_tool(
                    "add_column",
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
                "add_column",
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
                "add_column",
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


class TestToolRegistration:
    async def test_column_tools_registered(self) -> None:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            names = [t.name for t in tools]
            assert "add_column" in names
            assert "delete_column" in names
            assert "rename_column" in names
