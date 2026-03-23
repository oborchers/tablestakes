"""Tests for data models."""

from __future__ import annotations

import pytest

from tablestakes.models import ColumnDescriptor, index_to_letter


class TestIndexToLetter:
    @pytest.mark.parametrize(
        ("index", "expected"),
        [
            pytest.param(0, "A", id="first"),
            pytest.param(1, "B", id="second"),
            pytest.param(25, "Z", id="last-single"),
            pytest.param(26, "AA", id="first-double"),
            pytest.param(27, "AB", id="second-double"),
            pytest.param(51, "AZ", id="AZ"),
            pytest.param(52, "BA", id="BA"),
            pytest.param(701, "ZZ", id="last-double"),
            pytest.param(702, "AAA", id="first-triple"),
        ],
    )
    def test_bijective_base26(self, index: int, expected: str) -> None:
        assert index_to_letter(index) == expected

    def test_sequential_unique(self) -> None:
        """First 100 letters are all unique."""
        letters = [index_to_letter(i) for i in range(100)]
        assert len(set(letters)) == 100


class TestColumnDescriptor:
    def test_from_header_with_name(self) -> None:
        col = ColumnDescriptor.from_header(0, "Priority")
        assert col.index == 0
        assert col.letter == "A"
        assert col.name == "Priority"
        assert col.display_name == "A:Priority"

    def test_from_header_empty_name(self) -> None:
        col = ColumnDescriptor.from_header(2, "")
        assert col.letter == "C"
        assert col.display_name == "C"

    def test_from_header_high_index(self) -> None:
        col = ColumnDescriptor.from_header(26, "Data")
        assert col.letter == "AA"
        assert col.display_name == "AA:Data"
