"""Tests for citation graph tools."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client

from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_graph import register_graph_tools

S2_BASE = "https://api.semanticscholar.org/graph/v1"


@pytest.fixture
def mcp(bundle: ServiceBundle) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_graph_tools(app)
    return app


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citations(respx_mock: respx.MockRouter, mcp: FastMCP) -> None:
    respx_mock.get("/paper/p1/citations").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "citingPaper": {
                            "paperId": "c1",
                            "title": "Citer",
                            "year": 2022,
                            "citationCount": 5,
                        }
                    }
                ]
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_citations", {"identifier": "p1"})
    data = json.loads(result.content[0].text)
    assert data["data"][0]["citingPaper"]["paperId"] == "c1"


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_references(respx_mock: respx.MockRouter, mcp: FastMCP) -> None:
    respx_mock.get("/paper/p1/references").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "citedPaper": {
                            "paperId": "r1",
                            "title": "Foundation",
                            "year": 2015,
                            "citationCount": 1000,
                        }
                    }
                ]
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_references", {"identifier": "p1"})
    data = json.loads(result.content[0].text)
    assert data["data"][0]["citedPaper"]["paperId"] == "r1"


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citations_not_found(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/paper/missing/citations").mock(return_value=httpx.Response(404))
    async with Client(mcp) as client:
        result = await client.call_tool("get_citations", {"identifier": "missing"})
    data = json.loads(result.content[0].text)
    assert data["error"] == "not_found"


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citation_graph_single_hop(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/paper/p1/citations").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "citingPaper": {
                            "paperId": "c1",
                            "title": "C1",
                            "year": 2022,
                            "citationCount": 3,
                        }
                    },
                    {
                        "citingPaper": {
                            "paperId": "c2",
                            "title": "C2",
                            "year": 2023,
                            "citationCount": 1,
                        }
                    },
                ]
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_citation_graph",
            {"seed_ids": ["p1"], "direction": "citations", "depth": 1, "max_nodes": 50},
        )
    data = json.loads(result.content[0].text)
    node_ids = {n["id"] for n in data["nodes"]}
    assert "p1" in node_ids
    assert "c1" in node_ids
    assert "c2" in node_ids
    assert data["stats"]["truncated"] is False


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citation_graph_max_nodes_cap(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/paper/p1/citations").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "citingPaper": {
                            "paperId": "c1",
                            "title": "C1",
                            "year": 2022,
                            "citationCount": 1,
                        }
                    },
                    {
                        "citingPaper": {
                            "paperId": "c2",
                            "title": "C2",
                            "year": 2022,
                            "citationCount": 1,
                        }
                    },
                    {
                        "citingPaper": {
                            "paperId": "c3",
                            "title": "C3",
                            "year": 2022,
                            "citationCount": 1,
                        }
                    },
                ]
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_citation_graph",
            {"seed_ids": ["p1"], "direction": "citations", "depth": 1, "max_nodes": 2},
        )
    data = json.loads(result.content[0].text)
    assert data["stats"]["truncated"] is True
    assert data["stats"]["total_nodes"] <= 2


@pytest.mark.respx(base_url=S2_BASE)
async def test_find_bridge_papers_direct(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/paper/p1/references").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "citedPaper": {
                            "paperId": "p2",
                            "title": "Target",
                            "year": 2020,
                            "citationCount": 5,
                        }
                    }
                ]
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "find_bridge_papers",
            {
                "source_id": "p1",
                "target_id": "p2",
                "max_depth": 3,
                "direction": "references",
            },
        )
    data = json.loads(result.content[0].text)
    assert data["found"] is True
    ids = [p["paperId"] for p in data["path"]]
    assert ids == ["p1", "p2"]


@pytest.mark.respx(base_url=S2_BASE)
async def test_find_bridge_papers_not_found(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/paper/p1/references").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "find_bridge_papers",
            {
                "source_id": "p1",
                "target_id": "nowhere",
                "max_depth": 1,
                "direction": "references",
            },
        )
    data = json.loads(result.content[0].text)
    assert data["found"] is False
