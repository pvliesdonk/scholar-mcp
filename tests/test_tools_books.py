"""Tests for search_books and get_book tools."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client

from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_books import register_book_tools

OL_BASE = "https://openlibrary.org"

SAMPLE_SEARCH_RESPONSE = {
    "numFound": 1,
    "docs": [
        {
            "title": "Design Patterns",
            "author_name": ["Erich Gamma"],
            "publisher": ["Addison-Wesley"],
            "first_publish_year": 1994,
            "isbn": ["9780201633610"],
            "key": "/works/OL1168083W",
            "edition_key": ["OL1429049M"],
            "subject": ["Software patterns"],
            "number_of_pages_median": 395,
        }
    ],
}

SAMPLE_EDITION_RESPONSE = {
    "title": "Design Patterns",
    "publishers": ["Addison-Wesley"],
    "publish_date": "1994",
    "isbn_13": ["9780201633610"],
    "isbn_10": ["0201633612"],
    "number_of_pages": 395,
    "works": [{"key": "/works/OL1168083W"}],
    "key": "/books/OL1429049M",
    "subjects": ["Software patterns"],
}

SAMPLE_WORK_RESPONSE = {
    "title": "Design Patterns",
    "key": "/works/OL1168083W",
    "description": "A book about patterns.",
    "subjects": ["Software patterns"],
    "authors": [
        {"author": {"key": "/authors/OL239963A"}, "type": {"key": "/type/author_role"}},
        {"author": {"key": "/authors/OL239964A"}, "type": {"key": "/type/author_role"}},
    ],
    "covers": [12345],
}

SAMPLE_AUTHOR_GAMMA = {"name": "Erich Gamma", "key": "/authors/OL239963A"}
SAMPLE_AUTHOR_HELM = {"name": "Richard Helm", "key": "/authors/OL239964A"}

SAMPLE_SUBJECT_RESPONSE = {
    "name": "Machine learning",
    "work_count": 100,
    "works": [
        {
            "title": "Pattern Recognition",
            "key": "/works/OL8173450W",
            "authors": [{"name": "Christopher Bishop"}],
            "edition_count": 15,
            "cover_id": 12345,
        },
        {
            "title": "Deep Learning",
            "key": "/works/OL17930368W",
            "authors": [{"name": "Ian Goodfellow"}],
            "edition_count": 8,
            "cover_id": None,
        },
    ],
}


@pytest.fixture
def mcp(bundle: ServiceBundle) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_book_tools(app)
    return app


@pytest.mark.respx(base_url=OL_BASE)
async def test_search_books_returns_results(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/search.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_SEARCH_RESPONSE)
    )
    async with Client(mcp) as client:
        result = await client.call_tool("search_books", {"query": "design patterns"})
    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["title"] == "Design Patterns"
    assert data[0]["isbn_13"] == "9780201633610"


@pytest.mark.respx(base_url=OL_BASE)
async def test_search_books_caches_results(
    respx_mock: respx.MockRouter, mcp: FastMCP, bundle: ServiceBundle
) -> None:
    respx_mock.get("/search.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_SEARCH_RESPONSE)
    )
    async with Client(mcp) as client:
        await client.call_tool("search_books", {"query": "design patterns"})
    # Second call should hit cache, not API
    cached = await bundle.cache.get_book_search(
        "q='design patterns':t=None:a=None:limit=10"
    )
    assert cached is not None
    assert len(cached) == 1


@pytest.mark.respx(base_url=OL_BASE)
async def test_search_books_uses_cache(
    respx_mock: respx.MockRouter, mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """Second search_books call for same query returns cached results."""
    respx_mock.get("/search.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_SEARCH_RESPONSE)
    )
    async with Client(mcp) as client:
        await client.call_tool("search_books", {"query": "cached query"})
        # Second call — should come from cache
        result = await client.call_tool("search_books", {"query": "cached query"})
    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["title"] == "Design Patterns"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_isbn_cache_hit(
    respx_mock: respx.MockRouter, mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """get_book returns cached result on second call for same ISBN."""
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION_RESPONSE)
    )
    respx_mock.get("/works/OL1168083W.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_WORK_RESPONSE)
    )
    respx_mock.get("/authors/OL239963A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_GAMMA)
    )
    respx_mock.get("/authors/OL239964A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_HELM)
    )
    async with Client(mcp) as client:
        await client.call_tool("get_book", {"identifier": "9780201633610"})
        result = await client.call_tool("get_book", {"identifier": "9780201633610"})
    data = json.loads(result.content[0].text)
    assert data["title"] == "Design Patterns"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_by_edition_id(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """get_book resolves OL edition IDs (OL...M) via /books/ endpoint."""
    respx_mock.get("/books/OL1429049M.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION_RESPONSE)
    )
    respx_mock.get("/works/OL1168083W.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_WORK_RESPONSE)
    )
    respx_mock.get("/authors/OL239963A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_GAMMA)
    )
    respx_mock.get("/authors/OL239964A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_HELM)
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_book", {"identifier": "OL1429049M"})
    data = json.loads(result.content[0].text)
    assert data["title"] == "Design Patterns"
    assert data["isbn_13"] == "9780201633610"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_by_edition_id_not_found(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/books/OL0000000M.json").mock(return_value=httpx.Response(404))
    async with Client(mcp) as client:
        result = await client.call_tool("get_book", {"identifier": "OL0000000M"})
    data = json.loads(result.content[0].text)
    assert data["error"] == "not_found"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_edition_no_isbn_no_work(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """Edition without ISBN or work ID still returns a valid record."""
    edition = {
        "title": "Rare Book",
        "publishers": ["Obscure Press"],
        "publish_date": "1900",
        "key": "/books/OL9999999M",
    }
    respx_mock.get("/books/OL9999999M.json").mock(
        return_value=httpx.Response(200, json=edition)
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_book", {"identifier": "OL9999999M"})
    data = json.loads(result.content[0].text)
    assert data["title"] == "Rare Book"
    assert data["isbn_13"] is None
    assert data["openlibrary_work_id"] is None


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_by_work_id_not_found(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/works/OL0000000W.json").mock(return_value=httpx.Response(404))
    async with Client(mcp) as client:
        result = await client.call_tool("get_book", {"identifier": "OL0000000W"})
    data = json.loads(result.content[0].text)
    assert data["error"] == "not_found"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_by_isbn(respx_mock: respx.MockRouter, mcp: FastMCP) -> None:
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION_RESPONSE)
    )
    respx_mock.get("/works/OL1168083W.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_WORK_RESPONSE)
    )
    respx_mock.get("/authors/OL239963A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_GAMMA)
    )
    respx_mock.get("/authors/OL239964A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_HELM)
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_book", {"identifier": "9780201633610"})
    data = json.loads(result.content[0].text)
    assert data["title"] == "Design Patterns"
    assert data["isbn_13"] == "9780201633610"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_isbn_no_work_id(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """ISBN edition without a works key skips work cache write."""
    edition = {
        "title": "Standalone Edition",
        "publishers": ["Publisher"],
        "isbn_13": ["9781111111111"],
        "key": "/books/OL8888888M",
    }
    respx_mock.get("/isbn/9781111111111.json").mock(
        return_value=httpx.Response(200, json=edition)
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_book", {"identifier": "9781111111111"})
    data = json.loads(result.content[0].text)
    assert data["title"] == "Standalone Edition"
    assert data["openlibrary_work_id"] is None


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_by_isbn_not_found(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/isbn/0000000000000.json").mock(return_value=httpx.Response(404))
    async with Client(mcp) as client:
        result = await client.call_tool("get_book", {"identifier": "0000000000000"})
    data = json.loads(result.content[0].text)
    assert data["error"] == "not_found"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_by_work_id(respx_mock: respx.MockRouter, mcp: FastMCP) -> None:
    """Work-level lookup resolves authors and pulls edition data."""
    respx_mock.get("/works/OL1168083W.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_WORK_RESPONSE)
    )
    respx_mock.get("/authors/OL239963A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_GAMMA)
    )
    respx_mock.get("/authors/OL239964A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_HELM)
    )
    respx_mock.get("/works/OL1168083W/editions.json").mock(
        return_value=httpx.Response(
            200, json={"entries": [SAMPLE_EDITION_RESPONSE], "size": 1}
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_book", {"identifier": "OL1168083W"})
    data = json.loads(result.content[0].text)
    assert data["title"] == "Design Patterns"
    assert data["openlibrary_work_id"] == "OL1168083W"
    assert data["authors"] == ["Erich Gamma", "Richard Helm"]
    assert data["year"] == 1994
    assert data["publisher"] == "Addison-Wesley"
    assert data["isbn_13"] == "9780201633610"
    assert data["openlibrary_edition_id"] == "OL1429049M"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_by_work_id_no_editions(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """Work with no editions still returns title, authors, description."""
    respx_mock.get("/works/OL1168083W.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_WORK_RESPONSE)
    )
    respx_mock.get("/authors/OL239963A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_GAMMA)
    )
    respx_mock.get("/authors/OL239964A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_HELM)
    )
    respx_mock.get("/works/OL1168083W/editions.json").mock(
        return_value=httpx.Response(200, json={"entries": [], "size": 0})
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_book", {"identifier": "OL1168083W"})
    data = json.loads(result.content[0].text)
    assert data["title"] == "Design Patterns"
    assert data["authors"] == ["Erich Gamma", "Richard Helm"]
    assert data["isbn_13"] is None
    assert data["cover_url"] == "https://covers.openlibrary.org/b/id/12345-M.jpg"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_isbn_enriches_authors(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """get_book by ISBN should resolve authors from the work record."""
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION_RESPONSE)
    )
    respx_mock.get("/works/OL1168083W.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_WORK_RESPONSE)
    )
    respx_mock.get("/authors/OL239963A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_GAMMA)
    )
    respx_mock.get("/authors/OL239964A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_HELM)
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_book", {"identifier": "9780201633610"})
    data = json.loads(result.content[0].text)
    assert data["authors"] == ["Erich Gamma", "Richard Helm"]


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_edition_enriches_authors(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """get_book by edition ID should resolve authors from the work record."""
    respx_mock.get("/books/OL1429049M.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION_RESPONSE)
    )
    respx_mock.get("/works/OL1168083W.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_WORK_RESPONSE)
    )
    respx_mock.get("/authors/OL239963A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_GAMMA)
    )
    respx_mock.get("/authors/OL239964A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_HELM)
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_book", {"identifier": "OL1429049M"})
    data = json.loads(result.content[0].text)
    assert data["authors"] == ["Erich Gamma", "Richard Helm"]


@pytest.mark.respx(base_url=OL_BASE)
async def test_search_books_structured_params(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """search_books with title/author uses structured OL search fields."""
    respx_mock.get("/search.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_SEARCH_RESPONSE)
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_books", {"title": "Design Patterns", "author": "Gamma"}
        )
    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["title"] == "Design Patterns"


async def test_search_books_no_params(mcp: FastMCP) -> None:
    """search_books with no params returns error."""
    async with Client(mcp) as client:
        result = await client.call_tool("search_books", {})
    data = json.loads(result.content[0].text)
    assert "error" in data


@pytest.mark.respx(base_url=OL_BASE)
async def test_search_books_author_broadening(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """When author+title returns <3 results, retries with individual tokens."""
    # Initial search with full author returns nothing
    respx_mock.get("/search.json").mock(
        side_effect=[
            httpx.Response(200, json={"numFound": 0, "docs": []}),
            # Retry with token "Frank" — also nothing
            httpx.Response(200, json={"numFound": 0, "docs": []}),
            # Retry with token "Duffy" — finds the book under "Francis Duffy"
            httpx.Response(
                200,
                json={
                    "numFound": 1,
                    "docs": [
                        {
                            "title": "Planning Office Space",
                            "author_name": ["Francis Duffy"],
                            "publisher": ["Architectural Press"],
                            "first_publish_year": 1976,
                            "isbn": ["9780750612920"],
                            "key": "/works/OL9486737W",
                            "edition_key": ["OL10808057M"],
                            "subject": [],
                        }
                    ],
                },
            ),
        ]
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_books",
            {"title": "Planning Office Space", "author": "Frank Duffy"},
        )
    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["title"] == "Planning Office Space"


@pytest.mark.respx(base_url=OL_BASE)
async def test_search_books_query_falls_back_to_q(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """When query-as-title returns nothing, falls back to free-text q=."""
    respx_mock.get("/search.json").mock(
        side_effect=[
            # Title search returns nothing
            httpx.Response(200, json={"numFound": 0, "docs": []}),
            # Free-text fallback finds something
            httpx.Response(200, json=SAMPLE_SEARCH_RESPONSE),
        ]
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_books", {"query": "obscure keyword search"}
        )
    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["title"] == "Design Patterns"


@pytest.mark.respx(base_url=OL_BASE)
async def test_recommend_books_returns_results(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/subjects/machine_learning.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_SUBJECT_RESPONSE)
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "recommend_books", {"subject": "machine learning"}
        )
    data = json.loads(result.content[0].text)
    assert len(data) == 2
    assert data[0]["title"] == "Pattern Recognition"
    assert data[0]["authors"] == ["Christopher Bishop"]
    assert data[0]["openlibrary_work_id"] == "OL8173450W"


@pytest.mark.respx(base_url=OL_BASE)
async def test_recommend_books_caches_results(
    respx_mock: respx.MockRouter, mcp: FastMCP, bundle: ServiceBundle
) -> None:
    respx_mock.get("/subjects/algorithms.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_SUBJECT_RESPONSE)
    )
    async with Client(mcp) as client:
        await client.call_tool("recommend_books", {"subject": "algorithms"})
    cached = await bundle.cache.get_book_subject("algorithms")
    assert cached is not None
    assert len(cached) == 2


@pytest.mark.respx(base_url=OL_BASE)
async def test_recommend_books_empty_subject(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/subjects/nonexistent.json").mock(
        return_value=httpx.Response(
            200, json={"name": "nonexistent", "work_count": 0, "works": []}
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool("recommend_books", {"subject": "nonexistent"})
    data = json.loads(result.content[0].text)
    assert data == []


async def test_search_books_queued_on_rate_limit(
    bundle: ServiceBundle,
) -> None:
    """search_books returns queued response when rate-limited."""
    from unittest.mock import AsyncMock

    from scholar_mcp._rate_limiter import RateLimitedError

    bundle.openlibrary.search = AsyncMock(side_effect=RateLimitedError())

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_book_tools(app)

    async with Client(app) as client:
        result = await client.call_tool("search_books", {"query": "test"})
    data = json.loads(result.content[0].text)
    assert data["queued"] is True
    assert data["tool"] == "search_books"


async def test_get_book_queued_on_rate_limit(
    bundle: ServiceBundle,
) -> None:
    """get_book returns queued response when rate-limited."""
    from unittest.mock import AsyncMock

    from scholar_mcp._rate_limiter import RateLimitedError

    bundle.openlibrary.get_by_isbn = AsyncMock(side_effect=RateLimitedError())

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_book_tools(app)

    async with Client(app) as client:
        result = await client.call_tool("get_book", {"identifier": "9780201633610"})
    data = json.loads(result.content[0].text)
    assert data["queued"] is True
    assert data["tool"] == "get_book"


COVERS_BASE = "https://covers.openlibrary.org"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_download_cover_saves_file(
    respx_mock: respx.MockRouter,
    mcp: FastMCP,
    bundle: ServiceBundle,
) -> None:
    """download_cover=True downloads the cover image and returns cover_path."""
    from unittest.mock import AsyncMock, patch

    bundle.config.read_only = False
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION_RESPONSE)
    )
    respx_mock.get("/works/OL1168083W.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_WORK_RESPONSE)
    )
    respx_mock.get("/authors/OL239963A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_GAMMA)
    )
    respx_mock.get("/authors/OL239964A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_HELM)
    )
    mock_resp = AsyncMock()
    mock_resp.content = b"FAKE_JPEG_DATA"
    mock_resp.raise_for_status = lambda: None

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("scholar_mcp._tools_books.httpx.AsyncClient", return_value=mock_client):
        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_book",
                {"identifier": "9780201633610", "download_cover": True},
            )
    data = json.loads(result.content[0].text)
    assert "cover_path" in data
    mock_client.get.assert_called_once_with(
        "https://covers.openlibrary.org/b/isbn/9780201633610-M.jpg"
    )
    from pathlib import Path

    saved = Path(data["cover_path"])
    assert saved.exists()
    assert saved.read_bytes() == b"FAKE_JPEG_DATA"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_download_cover_uses_cache(
    respx_mock: respx.MockRouter,
    mcp: FastMCP,
    bundle: ServiceBundle,
) -> None:
    """When cover file already exists on disk, no HTTP download is made."""
    bundle.config.read_only = False
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION_RESPONSE)
    )
    respx_mock.get("/works/OL1168083W.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_WORK_RESPONSE)
    )
    respx_mock.get("/authors/OL239963A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_GAMMA)
    )
    respx_mock.get("/authors/OL239964A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_HELM)
    )
    # Pre-create the cover file
    covers_dir = bundle.config.cache_dir / "covers"
    covers_dir.mkdir(parents=True, exist_ok=True)
    cover_file = covers_dir / "9780201633610_M.jpg"
    cover_file.write_bytes(b"CACHED_IMAGE")

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_book",
            {"identifier": "9780201633610", "download_cover": True},
        )
    data = json.loads(result.content[0].text)
    assert data["cover_path"] == str(cover_file)
    # File content should be unchanged (no download happened)
    assert cover_file.read_bytes() == b"CACHED_IMAGE"


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_download_cover_read_only(
    respx_mock: respx.MockRouter,
    mcp: FastMCP,
    bundle: ServiceBundle,
) -> None:
    """In read-only mode, download_cover returns cover_error instead."""
    bundle.config.read_only = True
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION_RESPONSE)
    )
    respx_mock.get("/works/OL1168083W.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_WORK_RESPONSE)
    )
    respx_mock.get("/authors/OL239963A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_GAMMA)
    )
    respx_mock.get("/authors/OL239964A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_HELM)
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_book",
            {"identifier": "9780201633610", "download_cover": True},
        )
    data = json.loads(result.content[0].text)
    assert data["cover_error"] == "read_only_mode"
    assert "cover_path" not in data


@pytest.mark.respx(base_url=OL_BASE)
async def test_get_book_download_cover_false_by_default(
    respx_mock: respx.MockRouter,
    mcp: FastMCP,
) -> None:
    """Normal get_book call without download_cover has no cover_path."""
    respx_mock.get("/isbn/9780201633610.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_EDITION_RESPONSE)
    )
    respx_mock.get("/works/OL1168083W.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_WORK_RESPONSE)
    )
    respx_mock.get("/authors/OL239963A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_GAMMA)
    )
    respx_mock.get("/authors/OL239964A.json").mock(
        return_value=httpx.Response(200, json=SAMPLE_AUTHOR_HELM)
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_book", {"identifier": "9780201633610"})
    data = json.loads(result.content[0].text)
    assert "cover_path" not in data or data.get("cover_path") is None
    assert "cover_error" not in data


GB_BASE = "https://www.googleapis.com/books/v1"

SAMPLE_GB_VOLUME = {
    "volumeInfo": {
        "title": "Design Patterns",
        "description": "A classic software engineering book.",
        "previewLink": "https://books.google.com/books?id=abc123",
    },
    "accessInfo": {
        "viewability": "PARTIAL",
    },
    "searchInfo": {
        "textSnippet": "Gang of Four patterns explained.",
    },
}


@pytest.mark.respx(base_url=GB_BASE)
async def test_get_book_excerpt_returns_data(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """get_book_excerpt returns excerpt, description, and preview info."""
    respx_mock.get("/volumes").mock(
        return_value=httpx.Response(
            200, json={"totalItems": 1, "items": [SAMPLE_GB_VOLUME]}
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_book_excerpt", {"isbn": "9780201633610"})
    data = json.loads(result.content[0].text)
    assert data["source"] == "google_books"
    assert data["excerpt"] == "Gang of Four patterns explained."
    assert data["description"] == "A classic software engineering book."
    assert data["preview_available"] is True
    assert data["preview_link"] == "https://books.google.com/books?id=abc123"


@pytest.mark.respx(base_url=GB_BASE)
async def test_get_book_excerpt_not_found(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """get_book_excerpt returns error when ISBN not found."""
    respx_mock.get("/volumes").mock(
        return_value=httpx.Response(200, json={"totalItems": 0, "items": []})
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_book_excerpt", {"isbn": "0000000000000"})
    data = json.loads(result.content[0].text)
    assert data["error"] == "not_found"
    assert data["isbn"] == "0000000000000"
