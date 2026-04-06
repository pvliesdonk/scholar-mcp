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
    cached = await bundle.cache.get_book_search("design patterns:limit=10")
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
    async with Client(mcp) as client:
        result = await client.call_tool("get_book", {"identifier": "OL1429049M"})
    data = json.loads(result.content[0].text)
    assert data["title"] == "Design Patterns"
    assert data["isbn_13"] == "9780201633610"


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
    async with Client(mcp) as client:
        result = await client.call_tool("get_book", {"identifier": "9780201633610"})
    data = json.loads(result.content[0].text)
    assert data["title"] == "Design Patterns"
    assert data["isbn_13"] == "9780201633610"


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
    respx_mock.get("/works/OL1168083W.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "title": "Design Patterns",
                "key": "/works/OL1168083W",
                "description": "A book about patterns.",
                "subjects": ["Software patterns"],
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_book", {"identifier": "OL1168083W"})
    data = json.loads(result.content[0].text)
    assert data["title"] == "Design Patterns"
    assert data["openlibrary_work_id"] == "OL1168083W"
