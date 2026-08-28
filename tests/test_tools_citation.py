"""Tests for generate_citations MCP tool."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp_pvl_core import Jobs, register_job_tools

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
def mcp(bundle: ServiceBundle, slow_jobs: Jobs) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_citation_tools(app, slow_jobs)
    return app


async def test_generate_bibtex_single(mcp: FastMCP) -> None:
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[SAMPLE_PAPER])
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "citation_format": "bibtex"},
            )
    text = json.loads(result.content[0].text)["output"]
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
                {"paper_ids": ["abc123"], "citation_format": "csl-json"},
            )
    data = json.loads(json.loads(result.content[0].text)["output"])
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
                {"paper_ids": ["abc123"], "citation_format": "ris"},
            )
    text = json.loads(result.content[0].text)["output"]
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
                {"paper_ids": ["abc123", "missing_id"], "citation_format": "bibtex"},
            )
    text = json.loads(result.content[0].text)["output"]
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
                {"paper_ids": ["abc123"], "citation_format": "bibtex", "enrich": True},
            )
    text = json.loads(result.content[0].text)["output"]
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
                {"paper_ids": ["abc123"], "citation_format": "bibtex", "enrich": False},
            )
    text = json.loads(result.content[0].text)["output"]
    assert "@" in text


async def test_empty_input_error(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        result = await client.call_tool(
            "generate_citations",
            {"paper_ids": [], "citation_format": "bibtex"},
        )
    data = json.loads(result.content[0].text)
    assert "error" in data


async def test_upstream_error(mcp: FastMCP) -> None:
    """generate_citations returns upstream_error when S2 fails."""
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "citation_format": "bibtex"},
            )
    data = json.loads(result.content[0].text)
    assert data["error"] == "upstream_error"
    assert data["status"] == 500


async def test_too_many_ids_error(mcp: FastMCP) -> None:
    """generate_citations rejects more than 100 paper IDs."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "generate_citations",
            {"paper_ids": [f"id{i}" for i in range(101)], "citation_format": "bibtex"},
        )
    data = json.loads(result.content[0].text)
    assert "error" in data


async def test_all_papers_unresolved(mcp: FastMCP) -> None:
    """generate_citations returns structured error when all papers fail."""
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[None, None])
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["bad1", "bad2"], "citation_format": "bibtex"},
            )
    data = json.loads(result.content[0].text)
    assert data["error"] == "no_papers_resolved"
    assert set(data["failed"]) == {"bad1", "bad2"}


async def test_retries_on_429(bundle: ServiceBundle, slow_jobs: Jobs) -> None:
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
        register_citation_tools(app, slow_jobs)

        async with Client(app) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "citation_format": "bibtex"},
            )
            data = json.loads(result.content[0].text)
    assert "@article" in data["output"] or "@inproceedings" in data["output"]


async def test_generate_citations_promotes_when_slow(
    bundle: ServiceBundle, jobs: Jobs
) -> None:
    """Slow resolution is promoted, and the formatted text survives polling.

    This tool is the one whose payload had to be wrapped, so it is worth
    confirming the wrapper still arrives intact through a job record rather
    than only on the inline path.
    """

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.2)
        return httpx.Response(
            200,
            json=[{"paperId": "c9", "title": "Slow Paper", "year": 2024}],
        )

    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(side_effect=slow)

        @asynccontextmanager
        async def lifespan(app: FastMCP):  # type: ignore[type-arg]
            yield {"bundle": bundle}

        app = FastMCP("test", lifespan=lifespan)
        register_citation_tools(app, jobs)
        register_job_tools(app, jobs)

        async with Client(app) as client:
            result = await client.call_tool(
                "generate_citations", {"paper_ids": ["c9"], "enrich": False}
            )
            handle = json.loads(result.content[0].text)
            assert handle["status"] == "working"
            assert handle["poll_with"] == "get_job_result"

            for _ in range(40):
                polled = await client.call_tool(
                    "get_job_result", {"job_id": handle["job_id"]}
                )
                settled = json.loads(polled.content[0].text)
                if settled["status"] != "working":
                    break
                await asyncio.sleep(0.05)

    assert settled["status"] == "completed"
    assert settled["result"]["format"] == "bibtex"
    assert "Slow Paper" in settled["result"]["output"]
