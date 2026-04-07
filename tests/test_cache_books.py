"""Tests for book cache tables and ISBN normalization."""

from __future__ import annotations

from scholar_mcp._cache import ScholarCache, isbn10_to_isbn13, normalize_isbn


def test_isbn10_to_isbn13_design_patterns() -> None:
    assert isbn10_to_isbn13("0201633612") == "9780201633610"


def test_isbn10_to_isbn13_writing_secure_code() -> None:
    assert isbn10_to_isbn13("0735611319") == "9780735611313"


def test_normalize_isbn_already_13() -> None:
    assert normalize_isbn("9780201633610") == "9780201633610"


def test_normalize_isbn_strips_hyphens() -> None:
    assert normalize_isbn("978-0-201-63361-0") == "9780201633610"


def test_normalize_isbn_converts_10_to_13() -> None:
    assert normalize_isbn("0201633612") == "9780201633610"


def test_normalize_isbn_invalid_returns_as_is() -> None:
    assert normalize_isbn("notanisbn") == "notanisbn"


SAMPLE_BOOK = {
    "title": "Design Patterns",
    "authors": ["Erich Gamma", "Richard Helm", "Ralph Johnson", "John Vlissides"],
    "publisher": "Addison-Wesley",
    "year": 1994,
    "isbn_13": "9780201633610",
}


async def test_get_book_by_isbn_miss(cache: ScholarCache) -> None:
    result = await cache.get_book_by_isbn("9780201633610")
    assert result is None


async def test_set_and_get_book_by_isbn(cache: ScholarCache) -> None:
    await cache.set_book_by_isbn("9780201633610", SAMPLE_BOOK)
    result = await cache.get_book_by_isbn("9780201633610")
    assert result is not None
    assert result["title"] == "Design Patterns"


async def test_get_book_by_work_miss(cache: ScholarCache) -> None:
    result = await cache.get_book_by_work("OL1168083W")
    assert result is None


async def test_set_and_get_book_by_work(cache: ScholarCache) -> None:
    await cache.set_book_by_work("OL1168083W", SAMPLE_BOOK)
    result = await cache.get_book_by_work("OL1168083W")
    assert result is not None
    assert result["title"] == "Design Patterns"


async def test_get_book_search_miss(cache: ScholarCache) -> None:
    result = await cache.get_book_search("design patterns")
    assert result is None


async def test_set_and_get_book_search(cache: ScholarCache) -> None:
    await cache.set_book_search("design patterns", [SAMPLE_BOOK])
    result = await cache.get_book_search("design patterns")
    assert result is not None
    assert len(result) == 1
    assert result[0]["title"] == "Design Patterns"


async def test_book_subject_roundtrip(cache: ScholarCache) -> None:
    books = [
        {"title": "Book A", "authors": ["Author A"]},
        {"title": "Book B", "authors": ["Author B"]},
    ]
    await cache.set_book_subject("machine_learning", books)
    result = await cache.get_book_subject("machine_learning")
    assert result is not None
    assert len(result) == 2
    assert result[0]["title"] == "Book A"


async def test_book_subject_returns_none_when_missing(cache: ScholarCache) -> None:
    result = await cache.get_book_subject("nonexistent")
    assert result is None
