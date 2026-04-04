"""Tests for batch_resolve and enrich_paper tools."""

from __future__ import annotations

import asyncio
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


async def test_batch_resolve_upstream_error(mcp: FastMCP) -> None:
    """batch_resolve returns upstream_error when S2 batch endpoint fails."""
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        async with Client(mcp) as client:
            result = await client.call_tool("batch_resolve", {"identifiers": ["p1"]})
    data = json.loads(result.content[0].text)
    assert data["error"] == "upstream_error"
    assert data["status"] == 500


async def test_batch_resolve_not_found_no_doi(mcp: FastMCP) -> None:
    """batch_resolve returns not_found when S2 returns None and no DOI prefix."""
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[None])
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "batch_resolve", {"identifiers": ["some_id"]}
            )
    data = json.loads(result.content[0].text)
    assert data[0]["error"] == "not_found"
    assert data[0]["identifier"] == "some_id"


async def test_batch_resolve_queued_on_429(
    bundle: ServiceBundle,
) -> None:
    """batch_resolve returns queued on 429, background completes."""
    call_count = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429)
        return httpx.Response(200, json=[{"paperId": "p1", "title": "Paper 1"}])

    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(side_effect=_side_effect)

        @asynccontextmanager
        async def lifespan(app: FastMCP):  # type: ignore[type-arg]
            yield {"bundle": bundle}

        app = FastMCP("test", lifespan=lifespan)
        register_utility_tools(app)
        from scholar_mcp._tools_tasks import register_task_tools

        register_task_tools(app)

        async with Client(app) as client:
            result = await client.call_tool("batch_resolve", {"identifiers": ["p1"]})
            data = json.loads(result.content[0].text)
            assert data["queued"] is True
            assert data["tool"] == "batch_resolve"

            for _ in range(40):
                poll = await client.call_tool(
                    "get_task_result", {"task_id": data["task_id"]}
                )
                poll_data = json.loads(poll.content[0].text)
                if poll_data["status"] in ("completed", "failed"):
                    break
                await asyncio.sleep(0.05)
            assert poll_data["status"] == "completed"


async def test_enrich_paper_doi_prefix(mcp: FastMCP) -> None:
    """enrich_paper handles DOI: prefix without calling S2."""
    with respx.mock:
        respx.get(f"{OA_BASE}/works/https://doi.org/10.1/test").mock(
            return_value=httpx.Response(
                200,
                json={
                    "open_access": {"is_oa": False, "oa_status": "closed"},
                    "grants": [],
                    "authorships": [],
                    "concepts": [],
                },
            )
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "enrich_paper",
                {"identifier": "DOI:10.1/test", "fields": ["oa_status"]},
            )
    data = json.loads(result.content[0].text)
    assert data["doi"] == "10.1/test"
    assert data["oa_status"] == "closed"


async def test_enrich_paper_s2_http_error(mcp: FastMCP) -> None:
    """enrich_paper returns not_found when S2 get_paper raises HTTPStatusError."""
    with respx.mock:
        respx.get(f"{S2_BASE}/paper/badid").mock(
            return_value=httpx.Response(500, text="Server Error")
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "enrich_paper",
                {"identifier": "badid", "fields": ["oa_status"]},
            )
    data = json.loads(result.content[0].text)
    assert data["error"] == "not_found"
    assert data["identifier"] == "badid"


async def test_enrich_paper_no_doi(mcp: FastMCP) -> None:
    """enrich_paper returns no_doi when S2 paper has no DOI."""
    with respx.mock:
        respx.get(f"{S2_BASE}/paper/nodoi").mock(
            return_value=httpx.Response(
                200,
                json={"paperId": "nodoi", "externalIds": {}},
            )
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "enrich_paper",
                {"identifier": "nodoi", "fields": ["oa_status"]},
            )
    data = json.loads(result.content[0].text)
    assert data["error"] == "no_doi"
    assert data["identifier"] == "nodoi"


async def test_enrich_paper_not_found_in_openalex(mcp: FastMCP) -> None:
    """enrich_paper returns not_found_in_openalex when OA has no data."""
    with respx.mock:
        respx.get(f"{S2_BASE}/paper/p1").mock(
            return_value=httpx.Response(
                200,
                json={"paperId": "p1", "externalIds": {"DOI": "10.1/missing"}},
            )
        )
        respx.get(f"{OA_BASE}/works/https://doi.org/10.1/missing").mock(
            return_value=httpx.Response(404)
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "enrich_paper",
                {"identifier": "p1", "fields": ["oa_status"]},
            )
    data = json.loads(result.content[0].text)
    assert data["error"] == "not_found_in_openalex"
    assert data["doi"] == "10.1/missing"


async def test_enrich_paper_affiliations_and_concepts(mcp: FastMCP) -> None:
    """enrich_paper returns affiliations and concepts fields."""
    with respx.mock:
        respx.get(f"{S2_BASE}/paper/p2").mock(
            return_value=httpx.Response(
                200,
                json={"paperId": "p2", "externalIds": {"DOI": "10.1/aff"}},
            )
        )
        respx.get(f"{OA_BASE}/works/https://doi.org/10.1/aff").mock(
            return_value=httpx.Response(
                200,
                json={
                    "authorships": [
                        {
                            "institutions": [
                                {"display_name": "MIT"},
                                {"display_name": "Stanford"},
                            ]
                        }
                    ],
                    "concepts": [
                        {"display_name": "AI", "score": 0.95},
                        {"display_name": "NLP", "score": 0.85},
                    ],
                    "grants": [],
                    "open_access": {},
                },
            )
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "enrich_paper",
                {"identifier": "p2", "fields": ["affiliations", "concepts"]},
            )
    data = json.loads(result.content[0].text)
    assert "MIT" in data["affiliations"]
    assert "Stanford" in data["affiliations"]
    assert data["concepts"][0]["name"] == "AI"
    assert data["concepts"][0]["score"] == 0.95
    assert data["concepts"][1]["name"] == "NLP"


async def test_enrich_paper_queued_on_429(
    bundle: ServiceBundle,
) -> None:
    """enrich_paper returns queued on 429, background completes."""
    call_count = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429)
        return httpx.Response(
            200,
            json={"paperId": "p1", "externalIds": {"DOI": "10.1/q"}},
        )

    with respx.mock:
        respx.get(f"{S2_BASE}/paper/p1").mock(side_effect=_side_effect)
        respx.get(f"{OA_BASE}/works/https://doi.org/10.1/q").mock(
            return_value=httpx.Response(
                200,
                json={
                    "open_access": {"is_oa": True, "oa_status": "gold"},
                    "grants": [],
                    "authorships": [],
                    "concepts": [],
                },
            )
        )

        @asynccontextmanager
        async def lifespan(app: FastMCP):  # type: ignore[type-arg]
            yield {"bundle": bundle}

        app = FastMCP("test", lifespan=lifespan)
        register_utility_tools(app)
        from scholar_mcp._tools_tasks import register_task_tools

        register_task_tools(app)

        async with Client(app) as client:
            result = await client.call_tool(
                "enrich_paper",
                {"identifier": "p1", "fields": ["oa_status"]},
            )
            data = json.loads(result.content[0].text)
            assert data["queued"] is True
            assert data["tool"] == "enrich_paper"

            for _ in range(40):
                poll = await client.call_tool(
                    "get_task_result", {"task_id": data["task_id"]}
                )
                poll_data = json.loads(poll.content[0].text)
                if poll_data["status"] in ("completed", "failed"):
                    break
                await asyncio.sleep(0.05)
            assert poll_data["status"] == "completed"
