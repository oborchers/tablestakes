"""Tests for table detection and classification."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from tablestakes.models import TableComplexity, TableFormat
from tablestakes.parser import detect_tables


@pytest.fixture
def mixed_doc(fixtures_dir: Path) -> str:
    return (fixtures_dir / "mixed_document.md").read_text()


@pytest.fixture
def gitbook_small_html(fixtures_dir: Path) -> str:
    return (fixtures_dir / "gitbook_small.html").read_text()


class TestDetectTables:
    def test_mixed_document_table_count(self, mixed_doc: str) -> None:
        """Mixed document has 2 pipe tables + 2 HTML tables = 4 total."""
        tables = detect_tables(mixed_doc)
        assert len(tables) == 4

    def test_tables_in_document_order(self, mixed_doc: str) -> None:
        """Tables are returned sorted by position."""
        tables = detect_tables(mixed_doc)
        offsets = [t.start_offset for t in tables]
        assert offsets == sorted(offsets)

    def test_sequential_indices(self, mixed_doc: str) -> None:
        """Tables get 0-based sequential indices."""
        tables = detect_tables(mixed_doc)
        assert [t.index for t in tables] == [0, 1, 2, 3]

    def test_pipe_table_detected(self, mixed_doc: str) -> None:
        """First table is a pipe table."""
        tables = detect_tables(mixed_doc)
        assert tables[0].format == TableFormat.PIPE

    def test_html_gitbook_detected(self, mixed_doc: str) -> None:
        """Second table is GitBook HTML (has width attr)."""
        tables = detect_tables(mixed_doc)
        assert tables[1].format == TableFormat.HTML_GITBOOK
        assert tables[1].complexity == TableComplexity.GITBOOK

    def test_second_pipe_table(self, mixed_doc: str) -> None:
        """Third table is the Notifications pipe table."""
        tables = detect_tables(mixed_doc)
        assert tables[2].format == TableFormat.PIPE

    def test_simple_html_table(self, mixed_doc: str) -> None:
        """Fourth table is plain HTML (no GitBook attrs)."""
        tables = detect_tables(mixed_doc)
        assert tables[3].format == TableFormat.HTML_GENERAL
        assert tables[3].complexity == TableComplexity.SIMPLE


class TestCodeBlockExclusion:
    def test_html_table_in_code_block_not_detected(self, mixed_doc: str) -> None:
        """<table> inside fenced code block is not detected."""
        tables = detect_tables(mixed_doc)
        raw_contents = [t.raw_content for t in tables]
        assert not any("inside a code block" in r.lower() for r in raw_contents)

    def test_pipe_table_in_code_block_not_detected(self, mixed_doc: str) -> None:
        """Pipe table inside fenced code block is not detected."""
        tables = detect_tables(mixed_doc)
        raw_contents = [t.raw_content for t in tables]
        assert not any("Inside | Code | Block" in r for r in raw_contents)

    def test_only_code_blocks(self) -> None:
        """Document with only code-block tables yields nothing."""
        content = """# Test

```
| A | B |
| - | - |
| 1 | 2 |
```
"""
        assert detect_tables(content) == []


class TestClassification:
    def test_gitbook_width_attrs_cached(self, mixed_doc: str) -> None:
        """GitBook table caches width attributes."""
        tables = detect_tables(mixed_doc)
        gb = tables[1]
        assert gb.gitbook_attrs is not None
        assert "header_attrs" in gb.gitbook_attrs
        assert 0 in gb.gitbook_attrs["header_attrs"]
        assert "width" in gb.gitbook_attrs["header_attrs"][0]

    def test_simple_html_no_gitbook_attrs(self, mixed_doc: str) -> None:
        """Simple HTML table has no gitbook_attrs."""
        tables = detect_tables(mixed_doc)
        simple = tables[3]
        assert simple.gitbook_attrs is None

    def test_colspan_is_complex(self) -> None:
        content = '<table><tr><th colspan="2">Wide</th></tr><tr><td>A</td><td>B</td></tr></table>'
        tables = detect_tables(content)
        assert len(tables) == 1
        assert tables[0].complexity == TableComplexity.COMPLEX

    def test_nested_table_is_complex(self) -> None:
        content = "<table><tr><td><table><tr><td>Inner</td></tr></table></td></tr></table>"
        tables = detect_tables(content)
        # Outer table detected, classified as complex
        assert any(t.complexity == TableComplexity.COMPLEX for t in tables)

    def test_pipe_table_always_simple(self) -> None:
        content = "| A | B |\n| - | - |\n| 1 | 2 |\n"
        tables = detect_tables(content)
        assert len(tables) == 1
        assert tables[0].complexity == TableComplexity.SIMPLE


class TestSectionHeading:
    def test_heading_found(self, mixed_doc: str) -> None:
        """Tables have their nearest preceding heading."""
        tables = detect_tables(mixed_doc)
        assert tables[0].section_heading == "Cross-Domain Dependencies"
        assert tables[1].section_heading == "Attachments"
        assert tables[2].section_heading == "Notifications"

    def test_no_heading(self) -> None:
        content = "| A | B |\n| - | - |\n| 1 | 2 |\n"
        tables = detect_tables(content)
        assert tables[0].section_heading is None


class TestSourceLine:
    def test_source_lines(self, mixed_doc: str) -> None:
        """Tables report correct 1-based line numbers."""
        tables = detect_tables(mixed_doc)
        # First table starts at the pipe table line
        assert tables[0].source_line > 0
        # Each subsequent table is on a later line
        for i in range(1, len(tables)):
            assert tables[i].source_line > tables[i - 1].source_line


class TestSoupPresence:
    def test_html_table_has_soup(self, mixed_doc: str) -> None:
        """HTML tables carry a BeautifulSoup Tag."""
        tables = detect_tables(mixed_doc)
        html_tables = [t for t in tables if t.format != TableFormat.PIPE]
        for t in html_tables:
            assert t.soup is not None

    def test_pipe_table_no_soup(self, mixed_doc: str) -> None:
        """Pipe tables have soup=None."""
        tables = detect_tables(mixed_doc)
        pipe_tables = [t for t in tables if t.format == TableFormat.PIPE]
        for t in pipe_tables:
            assert t.soup is None


class TestEmptyAndEdgeCases:
    def test_empty_document(self) -> None:
        assert detect_tables("") == []

    def test_no_tables(self) -> None:
        assert detect_tables("# Just a heading\n\nSome text.\n") == []

    def test_html_comment_not_detected(self) -> None:
        content = "<!-- <table><tr><td>Hidden</td></tr></table> -->\n\nText."
        assert detect_tables(content) == []

    def test_gitbook_data_view_attr(self) -> None:
        """data-view attribute triggers GitBook classification."""
        content = '<table data-view="cards"><thead><tr><th>Name</th></tr></thead><tbody><tr><td>A</td></tr></tbody></table>'
        tables = detect_tables(content)
        assert len(tables) == 1
        assert tables[0].complexity == TableComplexity.GITBOOK
        assert tables[0].gitbook_attrs is not None
        assert tables[0].gitbook_attrs["table_attrs"]["data-view"] == "cards"

    def test_gitbook_data_hidden_attr(self) -> None:
        """data-hidden boolean attribute on th triggers GitBook classification."""
        content = "<table><thead><tr><th>Visible</th><th data-hidden>Hidden</th></tr></thead><tbody><tr><td>A</td><td>B</td></tr></tbody></table>"
        tables = detect_tables(content)
        assert len(tables) == 1
        assert tables[0].complexity == TableComplexity.GITBOOK

    def test_standalone_gitbook_html(self, gitbook_small_html: str) -> None:
        """Real GitBook fixture parses correctly."""
        tables = detect_tables(gitbook_small_html)
        assert len(tables) == 1
        t = tables[0]
        assert t.format == TableFormat.HTML_GITBOOK
        assert t.complexity == TableComplexity.GITBOOK
        assert t.soup is not None
        # Has 4 columns: Requirement, Priority, Dependency, Priority 1-2-3
        headers = t.soup.find("thead").find_all(["th", "td"])
        assert len(headers) == 4
