"""Tests for typed record definitions."""

from __future__ import annotations

from scholar_mcp._record_types import BookRecord


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
