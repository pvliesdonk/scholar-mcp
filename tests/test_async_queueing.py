"""Tests for async fire-and-forget queueing on S2 429 responses."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp_pvl_core import register_job_tools

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


async def test_try_once_preserves_positive_retry_after() -> None:
    """with_s2_try_once exposes a numeric upstream retry interval."""
    limiter = RateLimiter(delay=0.0)

    async def _rate_limited() -> dict:
        request = httpx.Request("GET", "http://test")
        response = httpx.Response(429, headers={"Retry-After": "2.5"}, request=request)
        raise httpx.HTTPStatusError("", request=request, response=response)

    with pytest.raises(RateLimitedError) as exc_info:
        await with_s2_try_once(_rate_limited, limiter)
    assert exc_info.value.retry_after_s == 2.5


async def test_try_once_parses_http_date_retry_after() -> None:
    """with_s2_try_once converts a future HTTP-date into a retry delay."""
    limiter = RateLimiter(delay=0.0)
    retry_at = datetime.now(UTC) + timedelta(seconds=60)

    async def _rate_limited() -> dict:
        request = httpx.Request("GET", "http://test")
        response = httpx.Response(
            429,
            headers={"Retry-After": format_datetime(retry_at, usegmt=True)},
            request=request,
        )
        raise httpx.HTTPStatusError("", request=request, response=response)

    with pytest.raises(RateLimitedError) as exc_info:
        await with_s2_try_once(_rate_limited, limiter)
    assert exc_info.value.retry_after_s is not None
    assert 0 < exc_info.value.retry_after_s <= 60


@pytest.mark.parametrize("retry_after", ["NaN", "Infinity", "-Infinity"])
async def test_try_once_discards_non_finite_retry_after(retry_after: str) -> None:
    """with_s2_try_once ignores non-finite Retry-After values."""
    limiter = RateLimiter(delay=0.0)

    async def _rate_limited() -> dict:
        request = httpx.Request("GET", "http://test")
        response = httpx.Response(
            429, headers={"Retry-After": retry_after}, request=request
        )
        raise httpx.HTTPStatusError("", request=request, response=response)

    with pytest.raises(RateLimitedError) as exc_info:
        await with_s2_try_once(_rate_limited, limiter)
    assert exc_info.value.retry_after_s is None


async def test_try_once_propagates_other_errors() -> None:
    """with_s2_try_once re-raises non-429 errors."""
    limiter = RateLimiter(delay=0.0)

    async def _server_error() -> dict:
        resp = httpx.Response(500, request=httpx.Request("GET", "http://test"))
        raise httpx.HTTPStatusError("", request=resp.request, response=resp)

    with pytest.raises(httpx.HTTPStatusError):
        await with_s2_try_once(_server_error, limiter)


# --- Integration tests for S2 tool queueing ---


async def _poll_job(client: Client, job_id: str, max_attempts: int = 40) -> dict:
    for _ in range(max_attempts):
        result = await client.call_tool("get_job_result", {"job_id": job_id})
        data = json.loads(result.content[0].text)
        if data["status"] in ("completed", "failed"):
            return data
        await asyncio.sleep(0.05)
    raise TimeoutError(f"job {job_id} did not complete")


@pytest.mark.respx(base_url=S2_BASE)
async def test_search_papers_deferred_on_429(
    respx_mock: respx.MockRouter, bundle: ServiceBundle
) -> None:
    """search_papers defers 429 work and returns its native result when complete."""
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
    register_search_tools(app)
    register_job_tools(app, bundle.jobs)

    async with Client(app) as client:
        result = await client.call_tool(
            "search_papers", {"query": "test", "fields": "compact"}
        )
        data = json.loads(result.content[0].text)
        assert data["status"] == "working"
        assert data["poll_with"] == "get_job_result"
        assert data["reason"] == "Semantic Scholar asked this client to retry later."
        assert "job_id" in data
        assert data["retry_after_s"] > 0

        # Poll for background result
        job_data = await _poll_job(client, data["job_id"])
    assert job_data["status"] == "completed"
    assert job_data["result"]["data"][0]["title"] == "Paper1"


@pytest.mark.respx(base_url=S2_BASE)
async def test_search_papers_direct_on_success(
    respx_mock: respx.MockRouter, bundle: ServiceBundle
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
    register_search_tools(app)

    async with Client(app) as client:
        result = await client.call_tool(
            "search_papers", {"query": "test", "fields": "compact"}
        )
    data = json.loads(result.content[0].text)
    assert data["data"][0]["title"] == "Paper1"


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_paper_deferred_on_429(
    respx_mock: respx.MockRouter, bundle: ServiceBundle
) -> None:
    """get_paper defers rate-limited work and returns the completed paper."""
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
    register_search_tools(app)
    register_job_tools(app, bundle.jobs)

    async with Client(app) as client:
        result = await client.call_tool("get_paper", {"identifier": "x1"})
        data = json.loads(result.content[0].text)
        assert data["status"] == "working"
        assert data["reason"] == "Semantic Scholar asked this client to retry later."
        assert data["retry_after_s"] > 0

        job_data = await _poll_job(client, data["job_id"])
    assert job_data["status"] == "completed"
    assert job_data["result"]["title"] == "Delayed"


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_paper_cached_returns_direct(
    respx_mock: respx.MockRouter, bundle: ServiceBundle
) -> None:
    """get_paper returns cached result directly, no queueing."""
    await bundle.cache.set_paper("abc123", {"paperId": "abc123", "title": "Cached"})

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_search_tools(app)

    async with Client(app) as client:
        result = await client.call_tool("get_paper", {"identifier": "abc123"})
    data = json.loads(result.content[0].text)
    assert data["title"] == "Cached"
