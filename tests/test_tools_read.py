"""Tests for read MCP tools via FastMCP in-memory Client."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastmcp import Client

from tablestakes.server import mcp
from tests.conftest import VERSION_RE, text_of

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def mixed_md(tmp_path: Path, fixtures_dir: Path) -> Path:
    src = fixtures_dir / "mixed_document.md"
    dest = tmp_path / "mixed.md"
    dest.write_text(src.read_text())
    return dest


class TestListTables:
    async def test_finds_all_tables(self, mixed_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(await client.call_tool("list_tables", {"file_path": str(mixed_md)}))
            assert "4 tables" in text

    async def test_shows_version_hash(self, mixed_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(await client.call_tool("list_tables", {"file_path": str(mixed_md)}))
            assert "v:" in text

    async def test_shows_column_descriptors(self, mixed_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(await client.call_tool("list_tables", {"file_path": str(mixed_md)}))
            assert "A:" in text

    async def test_shows_format_labels(self, mixed_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(await client.call_tool("list_tables", {"file_path": str(mixed_md)}))
            assert "pipe" in text
            assert "gitbook" in text

    async def test_shows_section_heading(self, mixed_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(await client.call_tool("list_tables", {"file_path": str(mixed_md)}))
            assert "Attachments" in text
            assert "Notifications" in text

    async def test_preview_rows(self, mixed_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "list_tables", {"file_path": str(mixed_md), "preview_rows": 2}
                )
            )
            assert "row0:" in text
            assert "row1:" in text

    async def test_no_preview_when_zero(self, mixed_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "list_tables", {"file_path": str(mixed_md), "preview_rows": 0}
                )
            )
            assert "row0:" not in text

    async def test_file_not_found(self) -> None:
        async with Client(mcp) as client:
            text = text_of(await client.call_tool("list_tables", {"file_path": "/nonexistent.md"}))
            assert "not found" in text.lower()

    async def test_no_tables(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.md"
        f.write_text("# Just a heading\n\nNo tables here.\n")
        async with Client(mcp) as client:
            text = text_of(await client.call_tool("list_tables", {"file_path": str(f)}))
            assert "No tables" in text


class TestReadTable:
    async def test_reads_pipe_table(self, mixed_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool("read_table", {"file_path": str(mixed_md), "table_index": 0})
            )
            assert "v:" in text
            assert "pipe" in text
            assert "Integration" in text

    async def test_reads_gitbook_table(self, mixed_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool("read_table", {"file_path": str(mixed_md), "table_index": 1})
            )
            assert "v:" in text
            assert "gitbook" in text
            assert "**5.1**" in text

    async def test_version_matches_list(self, mixed_md: Path) -> None:
        async with Client(mcp) as client:
            list_text = text_of(await client.call_tool("list_tables", {"file_path": str(mixed_md)}))
            read_text = text_of(
                await client.call_tool("read_table", {"file_path": str(mixed_md), "table_index": 0})
            )
            list_versions = VERSION_RE.findall(list_text)
            read_version = VERSION_RE.search(read_text)
            assert read_version
            assert list_versions[0] == read_version.group(1)

    async def test_table_not_found(self, mixed_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "read_table", {"file_path": str(mixed_md), "table_index": 99}
                )
            )
            assert "TABLE_NOT_FOUND" in text

    async def test_negative_index(self, mixed_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "read_table", {"file_path": str(mixed_md), "table_index": -1}
                )
            )
            assert "TABLE_NOT_FOUND" in text

    async def test_column_descriptors_in_output(self, mixed_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool("read_table", {"file_path": str(mixed_md), "table_index": 1})
            )
            assert "A:Requirement" in text

    async def test_inline_formatting_converted(self, mixed_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool("read_table", {"file_path": str(mixed_md), "table_index": 1})
            )
            assert "**5.1**" in text


class TestToolRegistration:
    async def test_tools_are_registered(self) -> None:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            names = [t.name for t in tools]
            assert "list_tables" in names
            assert "read_table" in names
