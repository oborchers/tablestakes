"""Tests for the shifted-lines safety model and concurrency behavior."""

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
def two_tables_md(tmp_path: Path) -> Path:
    f = tmp_path / "two.md"
    f.write_text(
        "# Doc\n\n## First\n\n"
        "| A | B |\n| --- | --- |\n| 1 | 2 |\n\n"
        "Some text between.\n\n## Second\n\n"
        "| X | Y |\n| --- | --- |\n| 3 | 4 |\n"
    )
    return f


class TestStaleRead:
    async def test_stale_after_external_edit(self, two_tables_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(two_tables_md), 0)
            content = two_tables_md.read_text()
            two_tables_md.write_text(content.replace("| 1 | 2 |", "| 99 | 99 |"))
            text = text_of(
                await client.call_tool(
                    "update_cells",
                    {
                        "file_path": str(two_tables_md),
                        "table_index": 0,
                        "version": v,
                        "updates": [{"row": 0, "column": "A", "value": "X"}],
                    },
                )
            )
            assert json.loads(text)["error"] == "STALE_READ"

    async def test_version_changes_each_write(self, two_tables_md: Path) -> None:
        async with Client(mcp) as client:
            v1 = await read_version(client, str(two_tables_md), 0)
            v2 = version_of(
                text_of(
                    await client.call_tool(
                        "update_cells",
                        {
                            "file_path": str(two_tables_md),
                            "table_index": 0,
                            "version": v1,
                            "updates": [{"row": 0, "column": "A", "value": "X"}],
                        },
                    )
                )
            )
            v3 = version_of(
                text_of(
                    await client.call_tool(
                        "update_cells",
                        {
                            "file_path": str(two_tables_md),
                            "table_index": 0,
                            "version": v2,
                            "updates": [{"row": 0, "column": "A", "value": "Y"}],
                        },
                    )
                )
            )
            assert v1 != v2 != v3


class TestShiftedLines:
    async def test_text_inserted_above_succeeds(self, two_tables_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(two_tables_md), 0)
            content = two_tables_md.read_text()
            two_tables_md.write_text("New line at top.\n\n" + content)
            text = text_of(
                await client.call_tool(
                    "update_cells",
                    {
                        "file_path": str(two_tables_md),
                        "table_index": 0,
                        "version": v,
                        "updates": [{"row": 0, "column": "A", "value": "updated"}],
                    },
                )
            )
            assert "v:" in text
            assert "STALE_READ" not in text

    async def test_table_inserted_above_causes_stale(self, two_tables_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(two_tables_md), 0)
            content = two_tables_md.read_text()
            new_table = "| New | Table |\n| --- | --- |\n| x | y |\n\n"
            two_tables_md.write_text(content.replace("## First\n\n", f"## First\n\n{new_table}"))
            text = text_of(
                await client.call_tool(
                    "update_cells",
                    {
                        "file_path": str(two_tables_md),
                        "table_index": 0,
                        "version": v,
                        "updates": [{"row": 0, "column": "A", "value": "X"}],
                    },
                )
            )
            assert json.loads(text)["error"] == "STALE_READ"


class TestTwoAgentsSameTable:
    async def test_first_wins_second_stale(self, two_tables_md: Path) -> None:
        async with Client(mcp) as client:
            v = await read_version(client, str(two_tables_md), 0)
            text_a = text_of(
                await client.call_tool(
                    "update_cells",
                    {
                        "file_path": str(two_tables_md),
                        "table_index": 0,
                        "version": v,
                        "updates": [{"row": 0, "column": "A", "value": "AgentA"}],
                    },
                )
            )
            assert "v:" in text_a
            text_b = text_of(
                await client.call_tool(
                    "update_cells",
                    {
                        "file_path": str(two_tables_md),
                        "table_index": 0,
                        "version": v,
                        "updates": [{"row": 0, "column": "A", "value": "AgentB"}],
                    },
                )
            )
            assert json.loads(text_b)["error"] == "STALE_READ"


class TestTwoAgentsDifferentTables:
    async def test_both_succeed(self, two_tables_md: Path) -> None:
        async with Client(mcp) as client:
            v0 = await read_version(client, str(two_tables_md), 0)
            v1 = await read_version(client, str(two_tables_md), 1)
            assert "v:" in text_of(
                await client.call_tool(
                    "update_cells",
                    {
                        "file_path": str(two_tables_md),
                        "table_index": 0,
                        "version": v0,
                        "updates": [{"row": 0, "column": "A", "value": "edited0"}],
                    },
                )
            )
            assert "v:" in text_of(
                await client.call_tool(
                    "update_cells",
                    {
                        "file_path": str(two_tables_md),
                        "table_index": 1,
                        "version": v1,
                        "updates": [{"row": 0, "column": "X", "value": "edited1"}],
                    },
                )
            )
            content = two_tables_md.read_text()
            assert "edited0" in content
            assert "edited1" in content


class TestTextEditThenTableEdit:
    """Scenario: Agent A edits prose text, then Agent B edits a table.

    This is common when one agent works on documentation text while another
    edits requirement tables. The table write must preserve A's text changes.
    """

    async def test_text_edit_before_table_edit_preserved(self, two_tables_md: Path) -> None:
        """Agent A edits prose between tables, then Agent B edits table 0.

        Agent B's table write should preserve Agent A's text changes because
        _safe_write re-reads the file fresh before writing.
        """
        async with Client(mcp) as client:
            # Agent B reads the table (gets version)
            v0 = await read_version(client, str(two_tables_md), 0)

            # Agent A edits prose text between the tables (outside tablestakes)
            content = two_tables_md.read_text()
            two_tables_md.write_text(
                content.replace("Some text between.", "Agent A rewrote this paragraph.")
            )

            # Agent B writes to table 0 — should succeed AND preserve A's text
            text = text_of(
                await client.call_tool(
                    "update_cells",
                    {
                        "file_path": str(two_tables_md),
                        "table_index": 0,
                        "version": v0,
                        "updates": [{"row": 0, "column": "A", "value": "AgentB"}],
                    },
                )
            )
            assert "v:" in text  # write succeeded

            # Verify BOTH changes are in the file
            final = two_tables_md.read_text()
            assert "Agent A rewrote this paragraph." in final  # A's text preserved
            assert "AgentB" in final  # B's table edit applied

    async def test_text_edit_after_table_also_preserved(self, two_tables_md: Path) -> None:
        """Agent A edits prose AFTER the tables, then Agent B edits table 1."""
        async with Client(mcp) as client:
            v1 = await read_version(client, str(two_tables_md), 1)

            # Agent A appends text at the end
            content = two_tables_md.read_text()
            two_tables_md.write_text(content + "\nAgent A added this footer.\n")

            # Agent B edits table 1
            text = text_of(
                await client.call_tool(
                    "update_cells",
                    {
                        "file_path": str(two_tables_md),
                        "table_index": 1,
                        "version": v1,
                        "updates": [{"row": 0, "column": "X", "value": "AgentB"}],
                    },
                )
            )
            assert "v:" in text

            final = two_tables_md.read_text()
            assert "Agent A added this footer." in final
            assert "AgentB" in final
