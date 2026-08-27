"""Tests for async fire-and-forget queueing on S2 429 responses."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp_pvl_core import Jobs

from scholar_mcp._rate_limiter import RateLimitedError, RateLimiter, with_s2_try_once
from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_search import register_search_tools

S2_BASE = "https://api.semanticscholar.org/graph/v1"


# --- Unit tests for with_s2_try_once ---


async def test_try_once_success() -> None:
    """with_s2_try_once returns result on success."""
    limiter = RateLimiter(delay=0.0)

    async def _ok() -> dict:
        return {"data": []}

    result = await with_s2_try_once(_ok, limiter)
    assert result == {"data": []}


async def test_try_once_raises_rate_limited() -> None:
    """with_s2_try_once raises RateLimitedError on 429."""
    limiter = RateLimiter(delay=0.0)

    async def _rate_limited() -> dict:
        resp = httpx.Response(429, request=httpx.Request("GET", "http://test"))
        raise httpx.HTTPStatusError("", request=resp.request, response=resp)

    with pytest.raises(RateLimitedError):
        await with_s2_try_once(_rate_limited, limiter)


async def test_try_once_propagates_other_errors() -> None:
    """with_s2_try_once re-raises non-429 errors."""
    limiter = RateLimiter(delay=0.0)

    async def _server_error() -> dict:
        resp = httpx.Response(500, request=httpx.Request("GET", "http://test"))
        raise httpx.HTTPStatusError("", request=resp.request, response=resp)

    with pytest.raises(httpx.HTTPStatusError):
        await with_s2_try_once(_server_error, limiter)


# --- Integration tests for S2 tool queueing ---


@pytest.mark.respx(base_url=S2_BASE)
async def test_search_papers_queued_on_429(
    respx_mock: respx.MockRouter, bundle: ServiceBundle, jobs: Jobs
) -> None:
    """search_papers returns queued response on 429, then background succeeds."""
    call_count = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"data": [{"title": "Paper1"}], "total": 1})

    respx_mock.get("/paper/search").mock(side_effect=_side_effect)

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_search_tools(app, jobs)

    async with Client(app) as client:
        result = await client.call_tool(
            "search_papers", {"query": "test", "fields": "compact"}
        )
        inner = json.loads(result.content[0].text)
    assert inner["data"][0]["title"] == "Paper1"


@pytest.mark.respx(base_url=S2_BASE)
async def test_search_papers_direct_on_success(
    respx_mock: respx.MockRouter, bundle: ServiceBundle, jobs: Jobs
) -> None:
    """search_papers returns direct result when no rate limiting."""
    respx_mock.get("/paper/search").mock(
        return_value=httpx.Response(
            200, json={"data": [{"title": "Paper1"}], "total": 1}
        )
    )

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_search_tools(app, jobs)

    async with Client(app) as client:
        result = await client.call_tool(
            "search_papers", {"query": "test", "fields": "compact"}
        )
    data = json.loads(result.content[0].text)
    assert "queued" not in data
    assert data["data"][0]["title"] == "Paper1"


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_paper_queued_on_429(
    respx_mock: respx.MockRouter, bundle: ServiceBundle, jobs: Jobs
) -> None:
    """get_paper returns queued response on 429, background task completes."""
    call_count = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"paperId": "x1", "title": "Delayed"})

    respx_mock.get("/paper/x1").mock(side_effect=_side_effect)

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_search_tools(app, jobs)

    async with Client(app) as client:
        result = await client.call_tool("get_paper", {"identifier": "x1"})
        inner = json.loads(result.content[0].text)
    assert inner["title"] == "Delayed"


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_paper_cached_returns_direct(
    respx_mock: respx.MockRouter, bundle: ServiceBundle, jobs: Jobs
) -> None:
    """get_paper returns cached result directly, no queueing."""
    await bundle.cache.set_paper("abc123", {"paperId": "abc123", "title": "Cached"})

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_search_tools(app, jobs)

    async with Client(app) as client:
        result = await client.call_tool("get_paper", {"identifier": "abc123"})
    data = json.loads(result.content[0].text)
    assert "queued" not in data
    assert data["title"] == "Cached"
