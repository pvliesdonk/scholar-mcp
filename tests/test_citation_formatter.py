"""Tests for citation formatters."""

from __future__ import annotations

from scholar_mcp._citation_formatter import (
    escape_bibtex,
    generate_bibtex_key,
    infer_entry_type,
)


class TestGenerateBibtexKey:
    def test_simple_key(self) -> None:
        paper = {
            "authors": [{"name": "Ashish Vaswani"}],
            "year": 2017,
        }
        assert generate_bibtex_key(paper, set()) == "vaswani2017"

    def test_deduplication(self) -> None:
        paper = {
            "authors": [{"name": "John Smith"}],
            "year": 2024,
        }
        seen: set[str] = set()
        k1 = generate_bibtex_key(paper, seen)
        k2 = generate_bibtex_key(paper, seen)
        k3 = generate_bibtex_key(paper, seen)
        assert k1 == "smith2024"
        assert k2 == "smith2024a"
        assert k3 == "smith2024b"

    def test_prefix_in_name(self) -> None:
        paper = {
            "authors": [{"name": "Jan van Houten"}],
            "year": 2020,
        }
        assert generate_bibtex_key(paper, set()) == "houten2020"

    def test_no_authors(self) -> None:
        paper: dict = {"authors": [], "year": 2024}
        assert generate_bibtex_key(paper, set()) == "anon2024"

    def test_no_year(self) -> None:
        paper = {"authors": [{"name": "Smith"}], "year": None}
        assert generate_bibtex_key(paper, set()) == "smith"

    def test_unicode_folding(self) -> None:
        paper = {
            "authors": [{"name": "José García"}],
            "year": 2023,
        }
        assert generate_bibtex_key(paper, set()) == "garcia2023"


class TestInferEntryType:
    def test_conference_venue(self) -> None:
        assert infer_entry_type({"venue": "NeurIPS Proceedings"}) == "inproceedings"

    def test_workshop_venue(self) -> None:
        assert infer_entry_type({"venue": "ICML Workshop"}) == "inproceedings"

    def test_symposium_venue(self) -> None:
        assert infer_entry_type({"venue": "IEEE Symposium"}) == "inproceedings"

    def test_arxiv_preprint(self) -> None:
        paper = {"venue": "", "externalIds": {"ArXiv": "2401.00001"}}
        assert infer_entry_type(paper) == "misc"

    def test_journal_fallback(self) -> None:
        assert infer_entry_type({"venue": "Nature"}) == "article"

    def test_empty_venue_no_arxiv(self) -> None:
        assert infer_entry_type({"venue": ""}) == "article"

    def test_none_venue(self) -> None:
        assert infer_entry_type({"venue": None}) == "article"


class TestEscapeBibtex:
    def test_special_chars(self) -> None:
        assert escape_bibtex("R&D") == r"R\&D"
        assert escape_bibtex("100%") == r"100\%"
        assert escape_bibtex("C#") == r"C\#"

    def test_unicode_accents(self) -> None:
        result = escape_bibtex("José")
        assert result == r"Jos{\'e}"

    def test_umlaut(self) -> None:
        result = escape_bibtex("Müller")
        assert result == r"M{\"u}ller"

    def test_plain_text_unchanged(self) -> None:
        assert escape_bibtex("Hello World") == "Hello World"
