"""Tests for batch_resolve and enrich_paper tools."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client

from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_utility import register_utility_tools

S2_BASE = "https://api.semanticscholar.org/graph/v1"
OA_BASE = "https://api.openalex.org"


@pytest.fixture
def mcp(bundle: ServiceBundle) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_utility_tools(app)
    return app


async def test_batch_resolve_all_found(mcp: FastMCP) -> None:
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"paperId": "p1", "title": "Paper 1"},
                    {"paperId": "p2", "title": "Paper 2"},
                ],
            )
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "batch_resolve", {"identifiers": ["p1", "p2"]}
            )
    data = json.loads(result.content[0].text)
    assert len(data) == 2
    assert data[0]["paper"]["paperId"] == "p1"


async def test_batch_resolve_openalex_fallback(mcp: FastMCP) -> None:
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[None])
        )
        respx.get(f"{OA_BASE}/works/https://doi.org/10.1/test").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "W1",
                    "doi": "https://doi.org/10.1/test",
                    "title": "Found via OpenAlex",
                },
            )
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "batch_resolve", {"identifiers": ["DOI:10.1/test"]}
            )
    data = json.loads(result.content[0].text)
    assert data[0].get("source") == "openalex"


async def test_enrich_paper(mcp: FastMCP) -> None:
    with respx.mock:
        respx.get(f"{S2_BASE}/paper/p1").mock(
            return_value=httpx.Response(
                200,
                json={"paperId": "p1", "externalIds": {"DOI": "10.1/test"}},
            )
        )
        respx.get(f"{OA_BASE}/works/https://doi.org/10.1/test").mock(
            return_value=httpx.Response(
                200,
                json={
                    "open_access": {"is_oa": True, "oa_status": "gold"},
                    "grants": [{"funder_display_name": "NSF"}],
                    "authorships": [],
                    "concepts": [],
                },
            )
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "enrich_paper",
                {"identifier": "p1", "fields": ["oa_status", "funders"]},
            )
    data = json.loads(result.content[0].text)
    assert data["oa_status"] == "gold"
    assert data["funders"][0] == "NSF"
