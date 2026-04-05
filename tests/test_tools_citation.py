"""Tests for generate_citations MCP tool."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client

from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_citation import register_citation_tools

S2_BASE = "https://api.semanticscholar.org/graph/v1"
OA_BASE = "https://api.openalex.org"

SAMPLE_PAPER = {
    "paperId": "abc123",
    "title": "Attention Is All You Need",
    "year": 2017,
    "venue": "Neural Information Processing Systems",
    "authors": [
        {"authorId": "1", "name": "Ashish Vaswani"},
        {"authorId": "2", "name": "Noam Shazeer"},
    ],
    "externalIds": {"DOI": "10.5555/3295222.3295349", "ArXiv": "1706.03762"},
    "abstract": "The dominant sequence transduction models...",
    "openAccessPdf": {"url": "https://example.com/paper.pdf"},
    "citationCount": 90000,
}


@pytest.fixture
def mcp(bundle: ServiceBundle) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_citation_tools(app)
    return app


async def test_generate_bibtex_single(mcp: FastMCP) -> None:
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[SAMPLE_PAPER])
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "format": "bibtex"},
            )
    text = result.content[0].text
    assert "@article{vaswani2017," in text
    assert "Vaswani, Ashish and Shazeer, Noam" in text


async def test_generate_csl_json(mcp: FastMCP) -> None:
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[SAMPLE_PAPER])
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "format": "csl-json"},
            )
    data = json.loads(result.content[0].text)
    assert len(data["citations"]) == 1
    assert data["citations"][0]["title"] == "Attention Is All You Need"


async def test_generate_ris(mcp: FastMCP) -> None:
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[SAMPLE_PAPER])
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "format": "ris"},
            )
    text = result.content[0].text
    assert "TY  - JOUR" in text
    assert "AU  - Vaswani, Ashish" in text


async def test_partial_resolution(mcp: FastMCP) -> None:
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[SAMPLE_PAPER, None])
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123", "missing_id"], "format": "bibtex"},
            )
    text = result.content[0].text
    assert "@article{vaswani2017," in text
    assert "% Could not resolve: missing_id" in text


async def test_enrich_fills_venue(mcp: FastMCP) -> None:
    paper_no_venue = {
        **SAMPLE_PAPER,
        "venue": "",
        "externalIds": {"DOI": "10.1/enrich"},
    }
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[paper_no_venue])
        )
        respx.get(f"{OA_BASE}/works/https://doi.org/10.1/enrich").mock(
            return_value=httpx.Response(
                200,
                json={
                    "primary_location": {
                        "source": {"display_name": "Nature Machine Intelligence"}
                    }
                },
            )
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "format": "bibtex", "enrich": True},
            )
    text = result.content[0].text
    assert "Nature Machine Intelligence" in text


async def test_enrich_disabled(mcp: FastMCP) -> None:
    paper_no_venue = {**SAMPLE_PAPER, "venue": ""}
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[paper_no_venue])
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "format": "bibtex", "enrich": False},
            )
    text = result.content[0].text
    assert "@" in text


async def test_empty_input_error(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        result = await client.call_tool(
            "generate_citations",
            {"paper_ids": [], "format": "bibtex"},
        )
    data = json.loads(result.content[0].text)
    assert "error" in data


async def test_queued_on_429(bundle: ServiceBundle) -> None:
    call_count = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429)
        return httpx.Response(200, json=[SAMPLE_PAPER])

    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(side_effect=_side_effect)

        @asynccontextmanager
        async def lifespan(app: FastMCP):
            yield {"bundle": bundle}

        app = FastMCP("test", lifespan=lifespan)
        register_citation_tools(app)

        async with Client(app) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "format": "bibtex"},
            )
            data = json.loads(result.content[0].text)
            assert data["queued"] is True
            assert data["tool"] == "generate_citations"
