"""Tests for citation graph tools."""

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
from scholar_mcp._tools_graph import register_graph_tools
from scholar_mcp._tools_tasks import register_task_tools

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
    respx_mock.post("/paper/batch").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"paperId": "p1", "title": "Seed", "year": 2020, "citationCount": 10}
            ],
        )
    )
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
    # Seed node should have resolved title from batch_resolve
    seed = next(n for n in data["nodes"] if n["id"] == "p1")
    assert seed["title"] == "Seed"
    assert data["stats"]["truncated"] is False


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citation_graph_max_nodes_cap(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.post("/paper/batch").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"paperId": "p1", "title": "Seed", "year": 2020, "citationCount": 10}
            ],
        )
    )
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


# --- Fixture with task tools for queueing tests ---


@pytest.fixture
def mcp_with_tasks(bundle: ServiceBundle) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_graph_tools(app)
    register_task_tools(app)
    return app


async def _poll_task(client: Client, task_id: str, max_attempts: int = 40) -> dict:
    for _ in range(max_attempts):
        result = await client.call_tool("get_task_result", {"task_id": task_id})
        data = json.loads(result.content[0].text)
        if data["status"] in ("completed", "failed"):
            return data
        await asyncio.sleep(0.05)
    raise TimeoutError(f"task {task_id} did not complete")


# --- get_citations: upstream_error (non-404 HTTP error, lines 86, 93-95) ---


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citations_upstream_error(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """get_citations returns upstream_error JSON on non-404 HTTP errors."""
    respx_mock.get("/paper/p1/citations").mock(return_value=httpx.Response(500))
    async with Client(mcp) as client:
        result = await client.call_tool("get_citations", {"identifier": "p1"})
    data = json.loads(result.content[0].text)
    assert data["error"] == "upstream_error"
    assert data["status"] == 500


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citations_queued_on_429(
    respx_mock: respx.MockRouter, mcp_with_tasks: FastMCP
) -> None:
    """get_citations returns queued response on 429, background task completes."""
    call_count = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429)
        return httpx.Response(
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

    respx_mock.get("/paper/p1/citations").mock(side_effect=_side_effect)

    async with Client(mcp_with_tasks) as client:
        result = await client.call_tool("get_citations", {"identifier": "p1"})
        data = json.loads(result.content[0].text)
        assert data["queued"] is True
        assert data["tool"] == "get_citations"

        task_data = await _poll_task(client, data["task_id"])
    assert task_data["status"] == "completed"
    inner = json.loads(task_data["result"])
    assert inner["data"][0]["citingPaper"]["paperId"] == "c1"


# --- get_references: error paths (lines 134-137, 144-146) ---


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_references_not_found(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """get_references returns not_found on 404."""
    respx_mock.get("/paper/missing/references").mock(return_value=httpx.Response(404))
    async with Client(mcp) as client:
        result = await client.call_tool("get_references", {"identifier": "missing"})
    data = json.loads(result.content[0].text)
    assert data["error"] == "not_found"
    assert data["identifier"] == "missing"


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_references_upstream_error(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """get_references returns upstream_error on non-404 HTTP errors."""
    respx_mock.get("/paper/p1/references").mock(return_value=httpx.Response(503))
    async with Client(mcp) as client:
        result = await client.call_tool("get_references", {"identifier": "p1"})
    data = json.loads(result.content[0].text)
    assert data["error"] == "upstream_error"
    assert data["status"] == 503


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_references_queued_on_429(
    respx_mock: respx.MockRouter, mcp_with_tasks: FastMCP
) -> None:
    """get_references returns queued response on 429, then completes."""
    call_count = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "citedPaper": {
                            "paperId": "r1",
                            "title": "Ref",
                            "year": 2019,
                            "citationCount": 100,
                        }
                    }
                ]
            },
        )

    respx_mock.get("/paper/p1/references").mock(side_effect=_side_effect)

    async with Client(mcp_with_tasks) as client:
        result = await client.call_tool("get_references", {"identifier": "p1"})
        data = json.loads(result.content[0].text)
        assert data["queued"] is True
        assert data["tool"] == "get_references"

        task_data = await _poll_task(client, data["task_id"])
    assert task_data["status"] == "completed"
    inner = json.loads(task_data["result"])
    assert inner["data"][0]["citedPaper"]["paperId"] == "r1"


# --- get_citation_graph: references branch (lines 252-282) ---


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citation_graph_references_direction(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """get_citation_graph with direction=references expands via references."""
    respx_mock.post("/paper/batch").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"paperId": "p1", "title": "Seed", "year": 2020, "citationCount": 10}
            ],
        )
    )
    respx_mock.get("/paper/p1/references").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "citedPaper": {
                            "paperId": "r1",
                            "title": "R1",
                            "year": 2018,
                            "citationCount": 50,
                        }
                    },
                    {
                        "citedPaper": {
                            "paperId": "r2",
                            "title": "R2",
                            "year": 2017,
                            "citationCount": 120,
                        }
                    },
                ]
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_citation_graph",
            {
                "seed_ids": ["p1"],
                "direction": "references",
                "depth": 1,
                "max_nodes": 50,
            },
        )
    data = json.loads(result.content[0].text)
    node_ids = {n["id"] for n in data["nodes"]}
    assert "p1" in node_ids
    assert "r1" in node_ids
    assert "r2" in node_ids
    # Edges should have source=p1 pointing to references
    edge_sources = {e["source"] for e in data["edges"]}
    assert "p1" in edge_sources
    assert data["stats"]["truncated"] is False


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citation_graph_both_direction(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """get_citation_graph with direction=both expands citations and references."""
    respx_mock.post("/paper/batch").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"paperId": "p1", "title": "Seed", "year": 2020, "citationCount": 10}
            ],
        )
    )
    respx_mock.get("/paper/p1/citations").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "citingPaper": {
                            "paperId": "c1",
                            "title": "C1",
                            "year": 2023,
                            "citationCount": 2,
                        }
                    }
                ]
            },
        )
    )
    respx_mock.get("/paper/p1/references").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "citedPaper": {
                            "paperId": "r1",
                            "title": "R1",
                            "year": 2018,
                            "citationCount": 40,
                        }
                    }
                ]
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_citation_graph",
            {
                "seed_ids": ["p1"],
                "direction": "both",
                "depth": 1,
                "max_nodes": 50,
            },
        )
    data = json.loads(result.content[0].text)
    node_ids = {n["id"] for n in data["nodes"]}
    assert "p1" in node_ids
    assert "c1" in node_ids
    assert "r1" in node_ids
    assert data["stats"]["total_nodes"] == 3


# --- get_citation_graph: RateLimitedError queueing (lines 317-319) ---


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citation_graph_queued_on_429(
    respx_mock: respx.MockRouter, mcp_with_tasks: FastMCP
) -> None:
    """get_citation_graph queues on 429 and background task completes."""
    batch_call_count = 0

    def _batch_side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal batch_call_count
        batch_call_count += 1
        if batch_call_count == 1:
            return httpx.Response(429)
        return httpx.Response(
            200,
            json=[
                {"paperId": "p1", "title": "Seed", "year": 2020, "citationCount": 10}
            ],
        )

    respx_mock.post("/paper/batch").mock(side_effect=_batch_side_effect)
    respx_mock.get("/paper/p1/citations").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "citingPaper": {
                            "paperId": "c1",
                            "title": "C1",
                            "year": 2023,
                            "citationCount": 1,
                        }
                    }
                ]
            },
        )
    )

    async with Client(mcp_with_tasks) as client:
        result = await client.call_tool(
            "get_citation_graph",
            {
                "seed_ids": ["p1"],
                "direction": "citations",
                "depth": 1,
                "max_nodes": 50,
            },
        )
        data = json.loads(result.content[0].text)
        assert data["queued"] is True
        assert data["tool"] == "get_citation_graph"

        task_data = await _poll_task(client, data["task_id"])
    assert task_data["status"] == "completed"
    inner = json.loads(task_data["result"])
    assert "c1" in {n["id"] for n in inner["nodes"]}


# --- find_bridge_papers: citations branch of _get_neighbours (lines 379-401) ---


@pytest.mark.respx(base_url=S2_BASE)
async def test_find_bridge_papers_citations_direction(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """find_bridge_papers with direction=citations uses citation expansion."""
    respx_mock.get("/paper/p1/citations").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"citingPaper": {"paperId": "p2"}},
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
                "direction": "citations",
            },
        )
    data = json.loads(result.content[0].text)
    assert data["found"] is True
    ids = [p["paperId"] for p in data["path"]]
    assert ids == ["p1", "p2"]


@pytest.mark.respx(base_url=S2_BASE)
async def test_find_bridge_papers_both_direction(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """find_bridge_papers with direction=both expands citations and references."""
    # references returns empty, citations finds the target
    respx_mock.get("/paper/p1/references").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    respx_mock.get("/paper/p1/citations").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"citingPaper": {"paperId": "p2"}},
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
                "direction": "both",
            },
        )
    data = json.loads(result.content[0].text)
    assert data["found"] is True
    ids = [p["paperId"] for p in data["path"]]
    assert ids == ["p1", "p2"]


# --- find_bridge_papers: RateLimitedError queueing (lines 429-431) ---


@pytest.mark.respx(base_url=S2_BASE)
async def test_find_bridge_papers_queued_on_429(
    respx_mock: respx.MockRouter, mcp_with_tasks: FastMCP
) -> None:
    """find_bridge_papers queues on 429 and background task completes."""
    call_count = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"citedPaper": {"paperId": "p2"}},
                ]
            },
        )

    respx_mock.get("/paper/p1/references").mock(side_effect=_side_effect)

    async with Client(mcp_with_tasks) as client:
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
        assert data["queued"] is True
        assert data["tool"] == "find_bridge_papers"

        task_data = await _poll_task(client, data["task_id"])
    assert task_data["status"] == "completed"
    inner = json.loads(task_data["result"])
    assert inner["found"] is True


# --- find_bridge_papers: HTTP error in _get_neighbours (lines 379-380, 399-400) ---


@pytest.mark.respx(base_url=S2_BASE)
async def test_find_bridge_papers_http_error_in_references(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """find_bridge_papers handles HTTP errors in reference expansion gracefully."""
    respx_mock.get("/paper/p1/references").mock(return_value=httpx.Response(500))
    async with Client(mcp) as client:
        result = await client.call_tool(
            "find_bridge_papers",
            {
                "source_id": "p1",
                "target_id": "p2",
                "max_depth": 1,
                "direction": "references",
            },
        )
    data = json.loads(result.content[0].text)
    # HTTP error causes empty neighbours, so target is not found
    assert data["found"] is False


@pytest.mark.respx(base_url=S2_BASE)
async def test_find_bridge_papers_http_error_in_citations(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """find_bridge_papers handles HTTP errors in citation expansion gracefully."""
    respx_mock.get("/paper/p1/citations").mock(return_value=httpx.Response(500))
    async with Client(mcp) as client:
        result = await client.call_tool(
            "find_bridge_papers",
            {
                "source_id": "p1",
                "target_id": "p2",
                "max_depth": 1,
                "direction": "citations",
            },
        )
    data = json.loads(result.content[0].text)
    # HTTP error causes empty neighbours, so target is not found
    assert data["found"] is False


# --- find_bridge_papers: multi-hop path with cached paper (lines 407, 417, 421-423) ---


@pytest.mark.respx(base_url=S2_BASE)
async def test_find_bridge_papers_multi_hop_with_cached_paper(
    respx_mock: respx.MockRouter, mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """find_bridge_papers finds a 2-hop path; intermediate paper uses cache."""
    # Pre-cache paper "mid" so line 417 (cached_paper branch) is hit
    await bundle.cache.set_paper(
        "mid", {"paperId": "mid", "title": "Middle Paper", "year": 2021}
    )
    # p1 references -> mid (intermediate node, not target)
    respx_mock.get("/paper/p1/references").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"citedPaper": {"paperId": "mid"}},
                ]
            },
        )
    )
    # mid references -> p2 (target)
    respx_mock.get("/paper/mid/references").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"citedPaper": {"paperId": "p2"}},
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
    path = data["path"]
    ids = [p["paperId"] for p in path]
    assert ids == ["p1", "mid", "p2"]
    # The intermediate paper should have the cached title
    assert path[1]["title"] == "Middle Paper"


@pytest.mark.respx(base_url=S2_BASE)
async def test_find_bridge_papers_max_depth_exceeded(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """find_bridge_papers stops expanding when max_depth is exceeded (line 407)."""
    # p1 -> mid at depth 1, mid -> p2 at depth 2, but max_depth=1 blocks it
    respx_mock.get("/paper/p1/references").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"citedPaper": {"paperId": "mid"}},
                ]
            },
        )
    )
    respx_mock.get("/paper/mid/references").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"citedPaper": {"paperId": "p2"}},
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
                "max_depth": 1,
                "direction": "references",
            },
        )
    data = json.loads(result.content[0].text)
    # With max_depth=1, p1->mid is at depth 1 (found),
    # then mid->p2 would be depth 2 but mid's path length is 2
    # which is > max_depth + 1 = 2, so mid is not expanded.
    # Actually let's check: path for mid is [p1, mid], len=2, max_depth+1=2.
    # 2 > 2 is False so mid IS expanded. Target found at depth 2.
    # We need max_depth=0 to hit the continue.
    assert data["found"] is True


@pytest.mark.respx(base_url=S2_BASE)
async def test_find_bridge_papers_depth_zero_skips_expansion(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """find_bridge_papers with max_depth=0 never expands beyond source."""
    # Even though p1 has references, depth=0 prevents expansion
    # path = [p1], len(path) = 1, max_depth + 1 = 1, 1 > 1 is False
    # so p1 IS expanded. We need the intermediate node to be blocked.
    # Actually, source path is [p1], len=1, 1 > 0+1=1 is False.
    # So source gets expanded. But the intermediate [p1, mid] len=2 > 1 is True.
    respx_mock.get("/paper/p1/references").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"citedPaper": {"paperId": "mid"}},
                ]
            },
        )
    )
    # mid references not needed -- its path [p1, mid] has len 2 > max_depth+1=1
    async with Client(mcp) as client:
        result = await client.call_tool(
            "find_bridge_papers",
            {
                "source_id": "p1",
                "target_id": "p2",
                "max_depth": 0,
                "direction": "references",
            },
        )
    data = json.loads(result.content[0].text)
    # p1 is expanded (its path len=1 is not > 1), finds mid but not p2.
    # mid is enqueued but when dequeued, path [p1, mid] len=2 > 1, so skipped.
    assert data["found"] is False


# --- get_citation_graph: HTTP error in references branch (lines 281-282) ---


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citation_graph_references_http_error(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """get_citation_graph swallows HTTP errors in the references branch."""
    respx_mock.post("/paper/batch").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"paperId": "p1", "title": "Seed", "year": 2020, "citationCount": 10}
            ],
        )
    )
    respx_mock.get("/paper/p1/references").mock(return_value=httpx.Response(500))
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_citation_graph",
            {
                "seed_ids": ["p1"],
                "direction": "references",
                "depth": 1,
                "max_nodes": 50,
            },
        )
    data = json.loads(result.content[0].text)
    # Only the seed node should be present (error swallowed)
    assert data["stats"]["total_nodes"] == 1
    assert data["nodes"][0]["id"] == "p1"
    assert data["stats"]["truncated"] is False


# --- get_citation_graph: batch_resolve failure falls back gracefully ---


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citation_graph_batch_resolve_failure(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """Seed nodes fall back to null metadata when batch_resolve fails."""
    respx_mock.post("/paper/batch").mock(return_value=httpx.Response(500))
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
                    }
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
    # Seed node present but with null metadata (fallback)
    seed = next(n for n in data["nodes"] if n["id"] == "p1")
    assert seed["title"] is None
    # Expansion still works
    assert "c1" in {n["id"] for n in data["nodes"]}


# --- get_citation_graph: client-side min_citations filter on citations ---


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citation_graph_citations_min_citations_filter(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """min_citations filter is applied client-side to citations."""
    respx_mock.post("/paper/batch").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"paperId": "p1", "title": "Seed", "year": 2020, "citationCount": 10}
            ],
        )
    )
    respx_mock.get("/paper/p1/citations").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "citingPaper": {
                            "paperId": "c1",
                            "title": "Popular Citer",
                            "year": 2023,
                            "citationCount": 100,
                        }
                    },
                    {
                        "citingPaper": {
                            "paperId": "c2",
                            "title": "Obscure Citer",
                            "year": 2023,
                            "citationCount": 2,
                        }
                    },
                ]
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_citation_graph",
            {
                "seed_ids": ["p1"],
                "direction": "citations",
                "depth": 1,
                "max_nodes": 50,
                "min_citations": 50,
            },
        )
    data = json.loads(result.content[0].text)
    node_ids = {n["id"] for n in data["nodes"]}
    assert "c1" in node_ids  # 100 >= 50
    assert "c2" not in node_ids  # 2 < 50


# --- get_citation_graph: client-side min_citations filter on references ---


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citation_graph_references_min_citations_filter(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """min_citations filter is applied client-side to references."""
    respx_mock.post("/paper/batch").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"paperId": "p1", "title": "Seed", "year": 2020, "citationCount": 10}
            ],
        )
    )
    respx_mock.get("/paper/p1/references").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "citedPaper": {
                            "paperId": "r1",
                            "title": "Popular",
                            "year": 2018,
                            "citationCount": 100,
                        }
                    },
                    {
                        "citedPaper": {
                            "paperId": "r2",
                            "title": "Obscure",
                            "year": 2019,
                            "citationCount": 2,
                        }
                    },
                ]
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_citation_graph",
            {
                "seed_ids": ["p1"],
                "direction": "references",
                "depth": 1,
                "max_nodes": 50,
                "min_citations": 50,
            },
        )
    data = json.loads(result.content[0].text)
    node_ids = {n["id"] for n in data["nodes"]}
    assert "r1" in node_ids  # 100 >= 50
    assert "r2" not in node_ids  # 2 < 50


# --- get_citation_graph: client-side year filter on references ---


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citation_graph_references_year_filter(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    """year_start/year_end filters are applied client-side to references."""
    respx_mock.post("/paper/batch").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"paperId": "p1", "title": "Seed", "year": 2020, "citationCount": 10}
            ],
        )
    )
    respx_mock.get("/paper/p1/references").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "citedPaper": {
                            "paperId": "r1",
                            "title": "InRange",
                            "year": 2019,
                            "citationCount": 10,
                        }
                    },
                    {
                        "citedPaper": {
                            "paperId": "r2",
                            "title": "TooOld",
                            "year": 2010,
                            "citationCount": 10,
                        }
                    },
                    {
                        "citedPaper": {
                            "paperId": "r3",
                            "title": "TooNew",
                            "year": 2025,
                            "citationCount": 10,
                        }
                    },
                ]
            },
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_citation_graph",
            {
                "seed_ids": ["p1"],
                "direction": "references",
                "depth": 1,
                "max_nodes": 50,
                "year_start": 2015,
                "year_end": 2022,
            },
        )
    data = json.loads(result.content[0].text)
    node_ids = {n["id"] for n in data["nodes"]}
    assert "r1" in node_ids  # 2019 in [2015, 2022]
    assert "r2" not in node_ids  # 2010 < 2015
    assert "r3" not in node_ids  # 2025 > 2022
