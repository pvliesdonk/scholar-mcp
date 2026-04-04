"""Tests for search_papers, get_paper, get_author tools."""

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


@pytest.fixture
def mcp(bundle: ServiceBundle) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_search_tools(app)
    return app


@pytest.mark.respx(base_url=S2_BASE)
async def test_search_papers_returns_results(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/paper/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "paperId": "p1",
                        "title": "Attention is All You Need",
                        "year": 2017,
                        "venue": "NeurIPS",
                        "citationCount": 50000,
                    }
                ],
                "total": 1,
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_papers", {"query": "attention transformer"}
        )
    data = json.loads(result.content[0].text)
    assert data["total"] == 1
    assert data["data"][0]["paperId"] == "p1"


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_paper_returns_full_metadata(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/paper/abc123").mock(
        return_value=httpx.Response(
            200,
            json={
                "paperId": "abc123",
                "title": "Test Paper",
                "year": 2024,
                "abstract": "An abstract.",
                "citationCount": 42,
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_paper", {"identifier": "abc123"})
    data = json.loads(result.content[0].text)
    assert data["paperId"] == "abc123"


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_paper_not_found(respx_mock: respx.MockRouter, mcp: FastMCP) -> None:
    respx_mock.get("/paper/missing").mock(return_value=httpx.Response(404))
    async with Client(mcp) as client:
        result = await client.call_tool("get_paper", {"identifier": "missing"})
    data = json.loads(result.content[0].text)
    assert data["error"] == "not_found"


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_author_by_id(respx_mock: respx.MockRouter, mcp: FastMCP) -> None:
    respx_mock.get("/author/12345").mock(
        return_value=httpx.Response(
            200,
            json={
                "authorId": "12345",
                "name": "Ada Lovelace",
                "hIndex": 42,
                "paperCount": 100,
                "papers": [
                    {
                        "paperId": "p1",
                        "title": "Paper 1",
                        "year": 2020,
                        "citationCount": 5,
                    }
                ],
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_author", {"identifier": "12345"})
    data = json.loads(result.content[0].text)
    assert data["name"] == "Ada Lovelace"


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_author_by_name_returns_candidates(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/author/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "authorId": "a1",
                        "name": "John Smith",
                        "hIndex": 10,
                        "paperCount": 50,
                    },
                    {
                        "authorId": "a2",
                        "name": "John Smith",
                        "hIndex": 5,
                        "paperCount": 20,
                    },
                ]
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_author", {"identifier": "John Smith"})
    data = json.loads(result.content[0].text)
    assert data["candidates"] is not None
    assert len(data["candidates"]) == 2


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_paper_alias_caching(
    respx_mock: respx.MockRouter, mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """get_paper stores alias when identifier differs from paperId."""
    respx_mock.get("/paper/ARXIV:2401.00001").mock(
        return_value=httpx.Response(
            200,
            json={"paperId": "abc123", "title": "Aliased Paper", "year": 2024},
        )
    )
    async with Client(mcp) as client:
        await client.call_tool("get_paper", {"identifier": "ARXIV:2401.00001"})
    resolved = await bundle.cache.get_alias("ARXIV:2401.00001")
    assert resolved == "abc123"


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_paper_cache_hit(
    respx_mock: respx.MockRouter, mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """get_paper returns cached data without a network call."""
    cached_data = {"paperId": "cached123", "title": "Cached Paper", "year": 2023}
    await bundle.cache.set_paper("cached123", cached_data)
    # No mock registered — if a network call is made, respx will raise
    async with Client(mcp) as client:
        result = await client.call_tool("get_paper", {"identifier": "cached123"})
    data = json.loads(result.content[0].text)
    assert data["paperId"] == "cached123"


@pytest.mark.respx(base_url=S2_BASE)
async def test_search_papers_upstream_error(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """search_papers returns error JSON on upstream HTTP error."""
    respx_mock.get("/paper/search").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )
    async with Client(mcp) as client:
        result = await client.call_tool("search_papers", {"query": "test"})
    data = json.loads(result.content[0].text)
    assert data["error"] == "upstream_error"
    assert data["status"] == 500
