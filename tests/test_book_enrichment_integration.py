"""Integration tests for book enrichment in existing tools."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client

from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_search import register_search_tools

S2_BASE = "https://api.semanticscholar.org/graph/v1"
OL_BASE = "https://openlibrary.org"

BOOK_PAPER = {
    "paperId": "book1",
    "title": "Design Patterns",
    "year": 1994,
    "publicationTypes": ["Book"],
    "externalIds": {"ISBN": "9780201633610"},
}

OL_EDITION = {
    "title": "Design Patterns",
    "publishers": ["Addison-Wesley"],
    "publish_date": "1994",
    "isbn_13": ["9780201633610"],
    "isbn_10": ["0201633612"],
    "number_of_pages": 395,
    "works": [{"key": "/works/OL1168083W"}],
    "key": "/books/OL1429049M",
}


@pytest.fixture
def mcp(bundle: ServiceBundle) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_search_tools(app)
    return app


async def test_get_paper_enriches_book(mcp: FastMCP) -> None:
    with respx.mock:
        respx.get(f"{S2_BASE}/paper/book1").mock(
            return_value=httpx.Response(200, json=BOOK_PAPER)
        )
        respx.get(f"{OL_BASE}/isbn/9780201633610.json").mock(
            return_value=httpx.Response(200, json=OL_EDITION)
        )
        async with Client(mcp) as client:
            result = await client.call_tool("get_paper", {"identifier": "book1"})
    data = json.loads(result.content[0].text)
    assert "book_metadata" in data
    assert data["book_metadata"]["publisher"] == "Addison-Wesley"


async def test_get_paper_no_enrichment_for_regular_paper(mcp: FastMCP) -> None:
    regular_paper = {
        "paperId": "reg1",
        "title": "Regular Paper",
        "year": 2024,
    }
    with respx.mock:
        respx.get(f"{S2_BASE}/paper/reg1").mock(
            return_value=httpx.Response(200, json=regular_paper)
        )
        async with Client(mcp) as client:
            result = await client.call_tool("get_paper", {"identifier": "reg1"})
    data = json.loads(result.content[0].text)
    assert "book_metadata" not in data
