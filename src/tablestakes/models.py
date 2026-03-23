"""Data models for tablestakes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel


class TableFormat(str, Enum):
    """The original format of a detected table."""

    PIPE = "pipe"
    HTML_GITBOOK = "gitbook"
    HTML_GENERAL = "html"


class TableComplexity(str, Enum):
    """Complexity classification for HTML tables."""

    SIMPLE = "simple"
    COMPLEX = "complex"
    GITBOOK = "gitbook"


def index_to_letter(index: int) -> str:
    """Convert 0-based column index to bijective base-26 letter.

    0=A, 1=B, ..., 25=Z, 26=AA, 27=AB, ..., 701=ZZ, 702=AAA
    """
    result = ""
    n = index + 1
    while n > 0:
        n -= 1
        result = chr(n % 26 + ord("A")) + result
        n //= 26
    return result


class ColumnDescriptor(BaseModel):
    """Describes a table column with multiple addressing modes."""

    index: int
    letter: str
    name: str
    display_name: str

    @classmethod
    def from_header(cls, index: int, name: str) -> ColumnDescriptor:
        letter = index_to_letter(index)
        display_name = f"{letter}:{name}" if name else letter
        return cls(index=index, letter=letter, name=name, display_name=display_name)


class CellUpdate(BaseModel):
    """A single cell update in a batch."""

    row: int
    column: str
    value: str


@dataclass
class RawTable:
    """Internal representation of a detected table before conversion.

    This is NOT a Pydantic model — it carries BeautifulSoup Tag objects
    which are not serializable. Used only inside the parser/converter.
    """

    index: int
    format: TableFormat
    complexity: TableComplexity
    raw_content: str
    start_offset: int
    end_offset: int
    source_line: int
    section_heading: str | None
    soup: Any | None = None  # bs4.Tag — not typed to avoid import at module level
    gitbook_attrs: dict[str, Any] | None = field(default=None)
