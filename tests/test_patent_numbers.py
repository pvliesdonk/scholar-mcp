"""Tests for patent number normalization."""

from __future__ import annotations

import pytest

from scholar_mcp._patent_numbers import DocdbNumber, is_patent_number, normalize


class TestDocdbNumber:
    def test_docdb_property(self) -> None:
        d = DocdbNumber(country="EP", number="1234567", kind="A1")
        assert d.docdb == "EP.1234567.A1"

    def test_str(self) -> None:
        d = DocdbNumber(country="EP", number="1234567", kind="A1")
        assert str(d) == "EP.1234567.A1"

    def test_equality(self) -> None:
        a = DocdbNumber(country="EP", number="1234567", kind="A1")
        b = DocdbNumber(country="EP", number="1234567", kind="A1")
        assert a == b


class TestNormalize:
    def test_ep_no_spaces(self) -> None:
        assert normalize("EP1234567A1") == DocdbNumber("EP", "1234567", "A1")

    def test_ep_with_spaces(self) -> None:
        assert normalize("EP 1234567 A1") == DocdbNumber("EP", "1234567", "A1")

    def test_ep_no_kind(self) -> None:
        result = normalize("EP1234567")
        assert result.country == "EP"
        assert result.number == "1234567"
        assert result.kind == ""

    def test_wo_with_slash(self) -> None:
        assert normalize("WO2024/123456A1") == DocdbNumber("WO", "2024123456", "A1")

    def test_wo_without_slash(self) -> None:
        assert normalize("WO2024123456") == DocdbNumber("WO", "2024123456", "")

    def test_us_with_commas(self) -> None:
        assert normalize("US11,234,567B2") == DocdbNumber("US", "11234567", "B2")

    def test_us_no_commas(self) -> None:
        assert normalize("US11234567B2") == DocdbNumber("US", "11234567", "B2")

    def test_docdb_format_passthrough(self) -> None:
        assert normalize("EP.1234567.A1") == DocdbNumber("EP", "1234567", "A1")

    def test_lowercase_country(self) -> None:
        assert normalize("ep1234567A1") == DocdbNumber("EP", "1234567", "A1")

    def test_invalid_no_country(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse"):
            normalize("1234567")

    def test_invalid_empty(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse"):
            normalize("")

    def test_invalid_no_digits(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse"):
            normalize("EPABCDEF")

    def test_invalid_no_numeric_portion(self) -> None:
        with pytest.raises(ValueError, match="no numeric portion"):
            normalize("EP/A1")


class TestIsPatentNumber:
    def test_ep_patent(self) -> None:
        assert is_patent_number("EP1234567A1") is True

    def test_wo_patent(self) -> None:
        assert is_patent_number("WO2024123456") is True

    def test_us_patent(self) -> None:
        assert is_patent_number("US11234567B2") is True

    def test_doi(self) -> None:
        assert is_patent_number("10.1234/abc") is False

    def test_s2_id(self) -> None:
        assert is_patent_number("abc123def456") is False

    def test_arxiv_id(self) -> None:
        assert is_patent_number("2301.12345") is False

    def test_doi_prefix(self) -> None:
        assert is_patent_number("DOI:10.1234/abc") is False
