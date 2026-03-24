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
            with pytest.raises(Exception, match="greater than or equal to 0"):
                await client.call_tool(
                    "read_table", {"file_path": str(mixed_md), "table_index": -1}
                )

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


class TestSearchTables:
    async def test_search_all_tables(self, mixed_md: Path) -> None:
        """Search across all tables with table_index=-1."""
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "search_tables", {"file_path": str(mixed_md), "pattern": "Must"}
                )
            )
            assert "match" in text
            assert "Must" in text

    async def test_search_single_table(self, mixed_md: Path) -> None:
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "search_tables",
                    {"file_path": str(mixed_md), "pattern": "Alice", "table_index": 3},
                )
            )
            assert "1 match" in text
            assert "T3" in text

    async def test_search_with_column_filter(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("| Name | Status |\n| --- | --- |\n| Alice | Done |\n| Bob | Pending |\n")
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "search_tables",
                    {"file_path": str(f), "pattern": "Done", "column": "Status"},
                )
            )
            assert "1 match" in text
            assert "Alice" in text

    async def test_case_insensitive(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("| Name |\n| --- |\n| Alice |\n| BOB |\n")
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool("search_tables", {"file_path": str(f), "pattern": "bob"})
            )
            assert "1 match" in text
            assert "BOB" in text

    async def test_no_matches(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("| Name |\n| --- |\n| Alice |\n")
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "search_tables", {"file_path": str(f), "pattern": "Nonexistent"}
                )
            )
            assert "No matches" in text

    async def test_regex_match(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text(
            "| Req | Status |\n| --- | --- |\n"
            "| D 1.1 | Done |\n| D 1.2 | Pending |\n| D 2.1 | Done |\n"
        )
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "search_tables",
                    {"file_path": str(f), "regex": r"D 1\.\d+"},
                )
            )
            assert "2 match" in text
            assert "D 1.1" in text
            assert "D 1.2" in text
            assert "D 2.1" not in text

    async def test_invalid_regex(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("| A |\n| --- |\n| 1 |\n")
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool("search_tables", {"file_path": str(f), "regex": "[invalid"})
            )
            assert "INVALID_REGEX" in text

    async def test_empty_pattern_returns_all(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("| A |\n| --- |\n| 1 |\n| 2 |\n| 3 |\n")
        async with Client(mcp) as client:
            text = text_of(await client.call_tool("search_tables", {"file_path": str(f)}))
            assert "3 match" in text

    async def test_file_not_found(self) -> None:
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "search_tables", {"file_path": "/nonexistent.md", "pattern": "x"}
                )
            )
            assert "not found" in text.lower()

    async def test_invalid_table_index(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("| A |\n| --- |\n| 1 |\n")
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "search_tables",
                    {"file_path": str(f), "pattern": "1", "table_index": 99},
                )
            )
            assert "TABLE_NOT_FOUND" in text

    async def test_includes_version_hash(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("| A |\n| --- |\n| hello |\n")
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool("search_tables", {"file_path": str(f), "pattern": "hello"})
            )
            assert "v:" in text

    async def test_search_column_skips_tables_without_it(self, tmp_path: Path) -> None:
        """Bug K: searching all tables by column name must skip tables that lack it."""
        f = tmp_path / "test.md"
        f.write_text(
            "| Name | Age |\n| --- | --- |\n| Alice | 30 |\n\n"
            "| Title | Status |\n| --- | --- |\n| Report | Done |\n"
        )
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "search_tables",
                    {"file_path": str(f), "pattern": "30", "column": "Age"},
                )
            )
            assert "1 match" in text
            assert "Alice" in text
            assert "COLUMN_NOT_FOUND" not in text

    async def test_search_column_error_on_single_table(self, tmp_path: Path) -> None:
        """Explicit table_index with missing column should still error."""
        f = tmp_path / "test.md"
        f.write_text("| Name |\n| --- |\n| Alice |\n")
        async with Client(mcp) as client:
            text = text_of(
                await client.call_tool(
                    "search_tables",
                    {"file_path": str(f), "pattern": "x", "table_index": 0, "column": "Age"},
                )
            )
            assert "COLUMN_NOT_FOUND" in text


class TestToolRegistration:
    async def test_tools_are_registered(self) -> None:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            names = [t.name for t in tools]
            assert "list_tables" in names
            assert "read_table" in names
            assert "search_tables" in names
