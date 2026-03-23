"""Shared test fixtures and helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from bs4 import BeautifulSoup, Tag

if TYPE_CHECKING:
    from fastmcp import Client

VERSION_RE = re.compile(r"v:([a-f0-9]{12})")


def text_of(result: object) -> str:
    """Extract text from a FastMCP CallToolResult."""
    return result.content[0].text  # type: ignore[attr-defined]


def version_of(text: str) -> str:
    """Extract version hash from tool output text."""
    m = VERSION_RE.search(text)
    if m:
        return m.group(1)
    msg = f"No version in: {text[:200]}"
    raise ValueError(msg)


async def read_version(client: Client, path: str, idx: int = 0) -> str:
    """Read a table and extract its version hash."""
    return version_of(
        text_of(await client.call_tool("read_table", {"file_path": path, "table_index": idx}))
    )


def parse_html_table(html: str) -> Tag:
    """Parse an HTML string and return the first <table> Tag."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    assert isinstance(table, Tag)
    return table


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_md(tmp_path: Path) -> Path:
    """Provide a temporary markdown file path for write tests."""
    p = tmp_path / "test.md"
    return p


@pytest.fixture
def gitbook_md(tmp_path: Path, fixtures_dir: Path) -> Path:
    """Temp file with a GitBook HTML table."""
    html = (fixtures_dir / "gitbook_small.html").read_text()
    f = tmp_path / "gitbook.md"
    f.write_text(f"# Test\n\n{html}\n\nEnd.\n")
    return f
