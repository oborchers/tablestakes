"""Tests for content hashing."""

from __future__ import annotations

from tablestakes.hasher import compute_hash


class TestComputeVersion:
    def test_deterministic(self) -> None:
        """Same input always produces same hash."""
        assert compute_hash("hello") == compute_hash("hello")

    def test_different_content(self) -> None:
        """Different input produces different hash."""
        assert compute_hash("hello") != compute_hash("world")

    def test_length(self) -> None:
        """Hash is exactly 12 hex characters."""
        result = compute_hash("test content")
        assert len(result) == 12
        assert all(c in "0123456789abcdef" for c in result)

    def test_empty_string(self) -> None:
        """Empty string is valid input."""
        result = compute_hash("")
        assert len(result) == 12

    def test_unicode(self) -> None:
        """Unicode content hashes correctly."""
        result = compute_hash("Erd\u00f6s P\u00e1l \u2014 \u00fcbersetzung")
        assert len(result) == 12

    def test_whitespace_sensitivity(self) -> None:
        """Whitespace differences produce different hashes."""
        assert compute_hash("<td>a</td>") != compute_hash("<td> a </td>")
