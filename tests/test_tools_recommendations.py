"""Tests for recommend_papers tool."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client

from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_recommendations import register_recommendation_tools

S2_REC = "https://api.semanticscholar.org/recommendations/v1"


@pytest.fixture
def mcp(bundle: ServiceBundle) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_recommendation_tools(app)
    return app


async def test_recommend_papers(mcp: FastMCP) -> None:
    with respx.mock:
        respx.post(f"{S2_REC}/papers").mock(
            return_value=httpx.Response(
                200,
                json={
                    "recommendedPapers": [
                        {
                            "paperId": "r1",
                            "title": "Recommended 1",
                            "year": 2023,
                            "citationCount": 10,
                        }
                    ]
                },
            )
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "recommend_papers", {"positive_ids": ["p1", "p2"]}
            )
    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["paperId"] == "r1"


async def test_recommend_papers_with_negatives(mcp: FastMCP) -> None:
    with respx.mock:
        respx.post(f"{S2_REC}/papers").mock(
            return_value=httpx.Response(200, json={"recommendedPapers": []})
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "recommend_papers",
                {"positive_ids": ["p1"], "negative_ids": ["n1"], "limit": 5},
            )
    data = json.loads(result.content[0].text)
    assert isinstance(data, list)


async def test_recommend_papers_caps_positive_ids(mcp: FastMCP) -> None:
    """Only first 5 positive IDs are sent (spec: 1–5)."""
    captured_body: dict = {}

    async def capture(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured_body.update(_json.loads(request.content))
        return httpx.Response(200, json={"recommendedPapers": []})

    with respx.mock:
        respx.post(f"{S2_REC}/papers").mock(side_effect=capture)
        async with Client(mcp) as client:
            await client.call_tool(
                "recommend_papers",
                {"positive_ids": ["p1", "p2", "p3", "p4", "p5", "p6"]},
            )
    assert len(captured_body.get("positivePaperIds", [])) <= 5


async def test_recommend_papers_upstream_error(mcp: FastMCP) -> None:
    with respx.mock:
        respx.post(f"{S2_REC}/papers").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "recommend_papers", {"positive_ids": ["p1"]}
            )
    data = json.loads(result.content[0].text)
    assert data["error"] == "upstream_error"
