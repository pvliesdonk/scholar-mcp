"""Tests for typed record definitions."""

from __future__ import annotations

from scholar_mcp._record_types import BookRecord, PaperRecord, PatentRecord


def test_book_record_accepts_valid_data() -> None:
    book: BookRecord = {
        "title": "Design Patterns",
        "authors": ["Erich Gamma"],
        "publisher": "Addison-Wesley",
        "year": 1994,
        "edition": None,
        "isbn_10": "0201633612",
        "isbn_13": "9780201633610",
        "openlibrary_work_id": "OL1168083W",
        "openlibrary_edition_id": "OL1429049M",
        "cover_url": "https://covers.openlibrary.org/b/isbn/9780201633610-M.jpg",
        "google_books_url": None,
        "subjects": ["Software patterns"],
        "page_count": 395,
        "description": None,
        "worldcat_url": "https://www.worldcat.org/isbn/9780201633610",
        "snippet": None,
        "cover_path": None,
    }
    assert book["title"] == "Design Patterns"
    assert book["authors"] == ["Erich Gamma"]


def test_book_record_allows_partial() -> None:
    book: BookRecord = {"title": "Minimal Book"}
    assert book["title"] == "Minimal Book"


def test_paper_record_accepts_s2_shape() -> None:
    paper: PaperRecord = {
        "paperId": "abc123",
        "title": "Attention Is All You Need",
        "year": 2017,
        "venue": "NeurIPS",
        "citationCount": 12345,
        "referenceCount": 42,
        "abstract": "The dominant sequence transduction models...",
        "authors": [
            {"authorId": "1", "name": "Ashish Vaswani"},
            {"authorId": "2", "name": "Noam Shazeer"},
        ],
        "externalIds": {"DOI": "10.48550/arXiv.1706.03762", "ArXiv": "1706.03762"},
        "fieldsOfStudy": ["Computer Science"],
        "tldr": {"model": "tldr@v2.0.0", "text": "A new architecture..."},
        "openAccessPdf": {
            "url": "https://arxiv.org/pdf/1706.03762",
            "status": "GREEN",
            "license": None,
        },
    }
    assert paper["paperId"] == "abc123"
    assert paper["externalIds"] is not None
    assert paper["externalIds"]["DOI"] == "10.48550/arXiv.1706.03762"


def test_paper_record_allows_partial_and_enrichment_fields() -> None:
    paper: PaperRecord = {"paperId": "x"}
    paper["book_metadata"] = {"publisher": "ACM"}
    paper["crossref_metadata"] = {"type": "journal-article"}
    assert paper["book_metadata"]["publisher"] == "ACM"


def test_paper_record_allows_none_optional_fields() -> None:
    # S2 returns None for unresolvable venue/year/etc.; the record must
    # accept those as-is rather than forcing callers to strip them.
    paper: PaperRecord = {
        "paperId": "x",
        "venue": None,
        "year": None,
        "externalIds": None,
        "openAccessPdf": None,
    }
    assert paper["venue"] is None


def test_patent_record_accepts_biblio_shape() -> None:
    patent: PatentRecord = {
        "title": "Method and apparatus for ...",
        "abstract": "A system that ...",
        "applicants": ["Acme Corp."],
        "inventors": ["Jane Doe", "John Smith"],
        "publication_number": "EP.1234567.A1",
        "publication_date": "2020-01-15",
        "filing_date": "2019-03-10",
        "priority_date": "2018-03-10",
        "family_id": "99999999",
        "classifications": ["H04L29/06"],
        "url": "https://worldwide.espacenet.com/patent/search/family/99999999/publication/EP1234567A1",
    }
    assert patent["publication_number"] == "EP.1234567.A1"
    assert patent["classifications"] == ["H04L29/06"]


def test_patent_record_allows_partial() -> None:
    patent: PatentRecord = {"publication_number": "EP.9.A1"}
    assert patent["publication_number"] == "EP.9.A1"
