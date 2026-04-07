"""Tests for Open Library API client."""

from __future__ import annotations

import httpx
import pytest
import respx

from scholar_mcp._openlibrary_client import (
    OpenLibraryClient,
    _filter_by_author,
    normalize_book,
    normalize_subject,
    normalize_subject_work,
)
from scholar_mcp._rate_limiter import RateLimiter

OL_BASE = "https://openlibrary.org"


@pytest.fixture
def limiter() -> RateLimiter:
    return RateLimiter(delay=0.0)


@pytest.fixture
def ol_client(limiter: RateLimiter) -> OpenLibraryClient:
    http = httpx.AsyncClient(base_url=OL_BASE, timeout=10.0, follow_redirects=True)
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
async def test_get_by_isbn_redirect(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    """ISBN endpoint returns 302 to the edition path; client must follow."""
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(302, headers={"Location": "/books/OL1429049M.json"})
    )
    respx_mock.get("/books/OL1429049M.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION)
    )
    result = await ol_client.get_by_isbn("9780201633610")
    assert result is not None
    assert result["title"] == "Design Patterns"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_by_isbn_server_error(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(return_value=httpx.Response(500))
    result = await ol_client.get_by_isbn("9780201633610")
    assert result is None


def test_normalize_book_from_search_doc() -> None:
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


def test_normalize_book_from_edition() -> None:
    book = normalize_book(SAMPLE_EDITION, source="edition")
    assert book["title"] == "Design Patterns"
    assert book["publisher"] == "Addison-Wesley"
    assert book["isbn_13"] == "9780201633610"
    assert book["isbn_10"] == "0201633612"
    assert book["openlibrary_edition_id"] == "OL1429049M"
    assert book["openlibrary_work_id"] == "OL1168083W"
    assert book["page_count"] == 395


@pytest.mark.respx(base_url=OL_BASE)
async def test_search_structured_fields(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    """Structured title/author params are forwarded to OL search."""
    route = respx_mock.get("/search.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_SEARCH)
    )
    results = await ol_client.search(title="Design Patterns", author="Gamma")
    assert len(results) == 1
    assert route.called
    req = route.calls[0].request
    query_str = str(req.url)
    assert "title=Design" in query_str
    assert "author=Gamma" in query_str


async def test_search_no_params(ol_client: OpenLibraryClient) -> None:
    """search() with no params returns empty list without hitting API."""
    results = await ol_client.search()
    assert results == []


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_author(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/authors/OL239963A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR)
    )
    result = await ol_client.get_author("OL239963A")
    assert result is not None
    assert result["name"] == "Erich Gamma"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_author_not_found(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/authors/OL0000000A.json").mock(return_value=httpx.Response(404))
    result = await ol_client.get_author("OL0000000A")
    assert result is None


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_work_editions(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/works/OL1168083W/editions.json").mock(
        return_value=httpx.Response(200, json={"entries": [SAMPLE_EDITION], "size": 1})
    )
    editions = await ol_client.get_work_editions("OL1168083W", limit=1)
    assert len(editions) == 1
    assert editions[0]["title"] == "Design Patterns"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_work_editions_empty(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/works/OL0000000W/editions.json").mock(
        return_value=httpx.Response(200, json={"entries": [], "size": 0})
    )
    editions = await ol_client.get_work_editions("OL0000000W")
    assert editions == []


def test_filter_by_author_ranks_by_token_hits() -> None:
    docs = [
        {"title": "Book A", "author_name": ["Francis Duffy"]},
        {"title": "Book B", "author_name": ["James Joyce"]},
        {"title": "Book C", "author_name": ["Frank Duffy", "John Smith"]},
        {"title": "Book D", "author_name": ["Karen Duffy", "Frank Wong"]},
    ]
    result = _filter_by_author(docs, "Frank Duffy")
    # "Frank Duffy" (2 tokens in one name) > "Francis Duffy" (1) = "Karen Duffy"/"Frank Wong" (1 each)
    # Joyce dropped (0 matches)
    assert result[0]["title"] == "Book C"
    assert "Book B" not in [d["title"] for d in result]
    assert len(result) == 3


def test_filter_by_author_case_insensitive() -> None:
    docs = [{"title": "Book A", "author_name": ["FRANK DUFFY"]}]
    result = _filter_by_author(docs, "frank duffy")
    assert len(result) == 1


def test_filter_by_author_rejects_no_surname_match() -> None:
    """Books where no author shares the surname are filtered out."""
    docs = [
        {"title": "Ghostly", "author_name": ["Audrey Niffenegger", "Neil Gaiman"]},
        {"title": "Office Landscaping", "author_name": ["Frank Duffy"]},
    ]
    result = _filter_by_author(docs, "Frank Duffy")
    assert [d["title"] for d in result] == ["Office Landscaping"]


def test_filter_by_author_empty_author_field() -> None:
    docs = [{"title": "No Author", "author_name": []}]
    result = _filter_by_author(docs, "Anyone")
    assert result == []


@pytest.mark.respx(base_url=OL_BASE)
async def test_search_filters_author_results(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    """search() with author= post-filters noise from OL token matching."""
    noisy_response = {
        "numFound": 4,
        "docs": [
            {"title": "Ghostly", "author_name": ["Audrey Niffenegger"]},
            {"title": "Office Landscaping", "author_name": ["Frank Duffy"]},
            {"title": "Planning Office Space", "author_name": ["Francis Duffy"]},
            {
                "title": "Community Psychology",
                "author_name": ["Karen Duffy", "Frank Wong"],
            },
        ],
    }
    respx_mock.get("/search.json").mock(
        return_value=httpx.Response(200, json=noisy_response)
    )
    results = await ol_client.search(author="Frank Duffy")
    # Keeps all with "Duffy" in an author; drops "Ghostly" (no Duffy)
    titles = [r["title"] for r in results]
    assert "Ghostly" not in titles
    assert "Office Landscaping" in titles
    assert "Planning Office Space" in titles
    assert "Community Psychology" in titles


SAMPLE_SUBJECT_RESPONSE = {
    "name": "Machine learning",
    "work_count": 1234,
    "works": [
        {
            "title": "Pattern Recognition and Machine Learning",
            "key": "/works/OL8173450W",
            "authors": [{"name": "Christopher M. Bishop", "key": "/authors/OL123A"}],
            "edition_count": 15,
            "cover_id": 12345,
        },
        {
            "title": "Deep Learning",
            "key": "/works/OL17930368W",
            "authors": [{"name": "Ian Goodfellow", "key": "/authors/OL456A"}],
            "edition_count": 8,
            "cover_id": 67890,
        },
    ],
}


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_subject(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/subjects/machine_learning.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_SUBJECT_RESPONSE)
    )
    result = await ol_client.get_subject("machine_learning", limit=10)
    assert result is not None
    assert result["name"] == "Machine learning"
    assert len(result["works"]) == 2


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_subject_empty_works(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/subjects/nonexistent_topic_xyz.json").mock(
        return_value=httpx.Response(
            200, json={"name": "nonexistent_topic_xyz", "work_count": 0, "works": []}
        )
    )
    result = await ol_client.get_subject("nonexistent_topic_xyz")
    assert result is not None
    assert result["works"] == []


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_subject_404(
    respx_mock: respx.MockRouter, ol_client: OpenLibraryClient
) -> None:
    respx_mock.get("/subjects/no_such_subject.json").mock(
        return_value=httpx.Response(404)
    )
    result = await ol_client.get_subject("no_such_subject")
    assert result is None


def test_normalize_subject() -> None:
    assert normalize_subject("Machine Learning") == "machine_learning"
    assert normalize_subject("  deep learning  ") == "deep_learning"
    assert normalize_subject("algorithms") == "algorithms"
    assert (
        normalize_subject("Natural Language Processing")
        == "natural_language_processing"
    )


def test_normalize_subject_work() -> None:
    work = {
        "title": "Deep Learning",
        "key": "/works/OL17930368W",
        "authors": [{"name": "Ian Goodfellow"}],
        "edition_count": 8,
        "cover_id": 67890,
    }
    book = normalize_subject_work(work)
    assert book["title"] == "Deep Learning"
    assert book["authors"] == ["Ian Goodfellow"]
    assert book["openlibrary_work_id"] == "OL17930368W"
    assert book["cover_url"] == "https://covers.openlibrary.org/b/id/67890-M.jpg"
    assert book["isbn_13"] is None
    assert book["publisher"] is None
