"""Tests for Open Library API client."""

from __future__ import annotations

import httpx
import pytest
import respx

from scholar_mcp._openlibrary_client import (
    OpenLibraryClient,
    normalize_book,
)
from scholar_mcp._rate_limiter import RateLimiter

OL_BASE = "https://openlibrary.org"


@pytest.fixture
def limiter() -> RateLimiter:
    return RateLimiter(delay=0.0)


@pytest.fixture
def ol_client(limiter: RateLimiter) -> OpenLibraryClient:
    http = httpx.AsyncClient(base_url=OL_BASE, timeout=10.0)
    return OpenLibraryClient(http, limiter)


SAMPLE_EDITION = {
    "title": "Design Patterns",
    "publishers": ["Addison-Wesley"],
    "publish_date": "1994",
    "isbn_10": ["0201633612"],
    "isbn_13": ["9780201633610"],
    "number_of_pages": 395,
    "works": [{"key": "/works/OL1168083W"}],
    "key": "/books/OL1429049M",
    "subjects": ["Software patterns", "Object-oriented programming"],
}

SAMPLE_WORK = {
    "title": "Design Patterns",
    "key": "/works/OL1168083W",
    "description": "A foundational book on software design patterns.",
    "subjects": ["Software patterns", "Object-oriented programming"],
    "authors": [
        {"author": {"key": "/authors/OL239963A"}, "type": {"key": "/type/author_role"}}
    ],
}

SAMPLE_AUTHOR = {
    "name": "Erich Gamma",
    "key": "/authors/OL239963A",
}

SAMPLE_SEARCH = {
    "numFound": 1,
    "docs": [
        {
            "title": "Design Patterns",
            "author_name": ["Erich Gamma", "Richard Helm"],
            "publisher": ["Addison-Wesley"],
            "first_publish_year": 1994,
            "isbn": ["9780201633610", "0201633612"],
            "key": "/works/OL1168083W",
            "edition_key": ["OL1429049M"],
            "subject": ["Software patterns"],
            "number_of_pages_median": 395,
            "cover_i": 12345,
        }
    ],
}


@pytest.mark.respx(base_url=OL_BASE)
async def test_search(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/search.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_SEARCH)
    )
    results = await ol_client.search("design patterns", limit=5)
    assert len(results) == 1
    assert results[0]["title"] == "Design Patterns"


@pytest.mark.respx(base_url=OL_BASE)
async def test_search_empty(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/search.json").mock(
        return_value=httpx.Response(200, json={"numFound": 0, "docs": []})
    )
    results = await ol_client.search("nonexistent book xyz")
    assert results == []


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_by_isbn(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION)
    )
    result = await ol_client.get_by_isbn("9780201633610")
    assert result is not None
    assert result["title"] == "Design Patterns"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_by_isbn_not_found(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/isbn/0000000000000.json").mock(return_value=httpx.Response(404))
    result = await ol_client.get_by_isbn("0000000000000")
    assert result is None


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_work(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/works/OL1168083W.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_WORK)
    )
    result = await ol_client.get_work("OL1168083W")
    assert result is not None
    assert result["title"] == "Design Patterns"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_work_not_found(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/works/OL0000000W.json").mock(return_value=httpx.Response(404))
    result = await ol_client.get_work("OL0000000W")
    assert result is None


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_by_isbn_server_error(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(return_value=httpx.Response(500))
    result = await ol_client.get_by_isbn("9780201633610")
    assert result is None


def testnormalize_book_from_search_doc() -> None:
    doc = SAMPLE_SEARCH["docs"][0]
    book = normalize_book(doc, source="search")
    assert book["title"] == "Design Patterns"
    assert book["authors"] == ["Erich Gamma", "Richard Helm"]
    assert book["publisher"] == "Addison-Wesley"
    assert book["year"] == 1994
    assert book["isbn_13"] == "9780201633610"
    assert book["openlibrary_work_id"] == "OL1168083W"
    assert book["subjects"] == ["Software patterns"]
    assert book["page_count"] == 395
    assert book["google_books_url"] is None


def testnormalize_book_from_edition() -> None:
    book = normalize_book(SAMPLE_EDITION, source="edition")
    assert book["title"] == "Design Patterns"
    assert book["publisher"] == "Addison-Wesley"
    assert book["isbn_13"] == "9780201633610"
    assert book["isbn_10"] == "0201633612"
    assert book["openlibrary_edition_id"] == "OL1429049M"
    assert book["openlibrary_work_id"] == "OL1168083W"
    assert book["page_count"] == 395
