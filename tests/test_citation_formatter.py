"""Tests for citation formatters."""

from __future__ import annotations

import json

from scholar_mcp._citation_formatter import (
    escape_bibtex,
    format_bibtex,
    format_csl_json,
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


class TestFormatBibtex:
    def test_single_article(self) -> None:
        papers = [
            {
                "paperId": "abc123",
                "title": "Attention Is All You Need",
                "year": 2017,
                "venue": "Neural Information Processing Systems",
                "authors": [
                    {"name": "Ashish Vaswani"},
                    {"name": "Noam Shazeer"},
                ],
                "externalIds": {"DOI": "10.5555/3295222.3295349"},
                "openAccessPdf": {"url": "https://example.com/paper.pdf"},
                "abstract": "The dominant sequence transduction models...",
            }
        ]
        result = format_bibtex(papers, [])
        assert "@article{vaswani2017," in result
        assert "author = {Vaswani, Ashish and Shazeer, Noam}" in result
        assert "title = {{Attention Is All You Need}}" in result
        assert "year = {2017}" in result
        assert "doi = {10.5555/3295222.3295349}" in result

    def test_conference_paper(self) -> None:
        papers = [
            {
                "title": "BERT",
                "year": 2019,
                "venue": "Conference on NLP",
                "authors": [{"name": "Jacob Devlin"}],
                "externalIds": {},
                "openAccessPdf": None,
                "abstract": None,
            }
        ]
        result = format_bibtex(papers, [])
        assert "@inproceedings{devlin2019," in result
        assert "booktitle = {Conference on NLP}" in result

    def test_arxiv_preprint(self) -> None:
        papers = [
            {
                "title": "Some Preprint",
                "year": 2024,
                "venue": "",
                "authors": [{"name": "Jane Doe"}],
                "externalIds": {"ArXiv": "2401.00001"},
                "openAccessPdf": None,
                "abstract": None,
            }
        ]
        result = format_bibtex(papers, [])
        assert "@misc{doe2024," in result
        assert "eprint = {2401.00001}" in result
        assert "archiveprefix = {arXiv}" in result

    def test_errors_as_comments(self) -> None:
        errors = [
            {"identifier": "DOI:10.1/missing", "reason": "not found"},
        ]
        result = format_bibtex([], errors)
        assert "% Could not resolve: DOI:10.1/missing (not found)" in result

    def test_prefix_author_formatting(self) -> None:
        papers = [
            {
                "title": "Test",
                "year": 2024,
                "venue": "",
                "authors": [{"name": "Jan van Houten"}],
                "externalIds": {},
                "openAccessPdf": None,
                "abstract": None,
            }
        ]
        result = format_bibtex(papers, [])
        assert "author = {van Houten, Jan}" in result

    def test_missing_fields_omitted(self) -> None:
        papers = [
            {
                "title": "Minimal Paper",
                "year": 2024,
                "venue": "",
                "authors": [{"name": "Smith"}],
                "externalIds": {},
                "openAccessPdf": None,
                "abstract": None,
            }
        ]
        result = format_bibtex(papers, [])
        # Should not contain doi or url fields
        lines = result.split("\n")
        field_lines = [line.strip() for line in lines if "=" in line]
        field_names = [line.split("=")[0].strip() for line in field_lines]
        assert "doi" not in field_names
        assert "url" not in field_names


class TestFormatCslJson:
    def test_single_paper(self) -> None:
        papers = [
            {
                "title": "Attention Is All You Need",
                "year": 2017,
                "venue": "Neural Information Processing Systems",
                "authors": [
                    {"name": "Ashish Vaswani"},
                    {"name": "Jan van Houten"},
                ],
                "externalIds": {"DOI": "10.5555/3295222.3295349"},
                "openAccessPdf": {"url": "https://example.com/paper.pdf"},
                "abstract": "The dominant sequence...",
            }
        ]
        result = json.loads(format_csl_json(papers, []))
        assert len(result["citations"]) == 1
        assert result["errors"] == []
        entry = result["citations"][0]
        assert entry["title"] == "Attention Is All You Need"
        assert entry["type"] == "article-journal"
        assert entry["issued"] == {"date-parts": [[2017]]}
        assert entry["author"][0] == {"family": "Vaswani", "given": "Ashish"}
        assert entry["author"][1] == {
            "family": "Houten",
            "given": "Jan",
            "non-dropping-particle": "van",
        }

    def test_errors_in_output(self) -> None:
        errors = [{"identifier": "bad_id", "reason": "not found"}]
        result = json.loads(format_csl_json([], errors))
        assert result["citations"] == []
        assert len(result["errors"]) == 1
        assert result["errors"][0]["identifier"] == "bad_id"

    def test_missing_year(self) -> None:
        papers = [
            {
                "title": "No Year",
                "year": None,
                "venue": "",
                "authors": [{"name": "Smith"}],
                "externalIds": {},
                "openAccessPdf": None,
                "abstract": None,
            }
        ]
        result = json.loads(format_csl_json(papers, []))
        assert "issued" not in result["citations"][0]
