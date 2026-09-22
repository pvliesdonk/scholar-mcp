"""Tests for how the S2 client handles 429 responses.

Formerly `test_async_queueing.py`. There is no queue any more: a 429 inside
an MCP tool defers its current body to a job, where `with_s2_retry` keeps
waiting at the shared gate. `with_s2_try_once` remains for the keepalive's
single ping.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp_pvl_core import (
    JobLimitExceededError,
    Jobs,
    JobsConfig,
    ServerConfig,
    build_jobs,
)

from scholar_mcp._rate_limiter import (
    RateLimitedError,
    RateLimiter,
    with_s2_retry,
    with_s2_try_once,
)
from scholar_mcp._s2_jobs import _run_s2_body
from scholar_mcp._tools_search import register_search_tools
from scholar_mcp.domain import Service
from tests.conftest import PlainClient, tasks_server

S2_BASE = "https://api.semanticscholar.org/graph/v1"


# --- Unit tests for with_s2_try_once (still used by run_keepalive) ---


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


# --- Integration: a 429 is absorbed by the client's own backoff ---


@pytest.mark.respx(base_url=S2_BASE)
async def test_search_papers_defers_on_429(
    respx_mock: respx.MockRouter, service: Service, slow_jobs: Jobs
) -> None:
    """A 429 returns a reasoned handle and the same call finishes through it."""
    call_count = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"data": [{"title": "Paper1"}], "total": 1})

    respx_mock.get("/paper/search").mock(side_effect=_side_effect)

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]  # noqa: ARG001
        yield {"service": service}

    app = tasks_server("test", lifespan=lifespan)
    register_search_tools(app, slow_jobs)

    async with PlainClient(app) as client:
        result = await client.call_tool(
            "search_papers", {"query": "test", "fields": "compact"}
        )
        handle = json.loads(result.content[0].text)
        assert handle["status"] == "working"
        assert "Semantic Scholar" in handle["reason"]
        assert handle["retry_after_s"] > 0
        while True:
            record = await slow_jobs.poll(handle["job_id"])
            if record["status"] == "completed":
                break
            await asyncio.sleep(0.01)
    assert record["result"]["data"][0]["title"] == "Paper1"
    assert call_count == 2


@pytest.mark.respx(base_url=S2_BASE)
async def test_search_papers_direct_on_success(
    respx_mock: respx.MockRouter, service: Service, slow_jobs: Jobs
) -> None:
    """search_papers returns direct result when no rate limiting."""
    respx_mock.get("/paper/search").mock(
        return_value=httpx.Response(
            200, json={"data": [{"title": "Paper1"}], "total": 1}
        )
    )

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]  # noqa: ARG001
        yield {"service": service}

    app = tasks_server("test", lifespan=lifespan)
    register_search_tools(app, slow_jobs)

    async with Client(app) as client:
        result = await client.call_tool(
            "search_papers", {"query": "test", "fields": "compact"}
        )
    data = json.loads(result.content[0].text)
    assert "queued" not in data
    assert data["data"][0]["title"] == "Paper1"


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_paper_defers_on_429(
    respx_mock: respx.MockRouter, service: Service, slow_jobs: Jobs
) -> None:
    """A 429 defers the paper lookup and it eventually completes."""
    call_count = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"paperId": "x1", "title": "Delayed"})

    respx_mock.get("/paper/x1").mock(side_effect=_side_effect)

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]  # noqa: ARG001
        yield {"service": service}

    app = tasks_server("test", lifespan=lifespan)
    register_search_tools(app, slow_jobs)

    async with PlainClient(app) as client:
        result = await client.call_tool("get_paper", {"identifier": "x1"})
        handle = json.loads(result.content[0].text)
        while True:
            record = await slow_jobs.poll(handle["job_id"])
            if record["status"] == "completed":
                break
            await asyncio.sleep(0.01)
    assert record["result"]["title"] == "Delayed"


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_paper_cached_returns_direct(
    respx_mock: respx.MockRouter,  # noqa: ARG001
    service: Service,
    slow_jobs: Jobs,
) -> None:
    """A cached paper answers from cache without touching the network."""
    await service.cache.set_paper("abc123", {"paperId": "abc123", "title": "Cached"})

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]  # noqa: ARG001
        yield {"service": service}

    app = tasks_server("test", lifespan=lifespan)
    register_search_tools(app, slow_jobs)

    async with Client(app) as client:
        result = await client.call_tool("get_paper", {"identifier": "abc123"})
    data = json.loads(result.content[0].text)
    assert "queued" not in data
    assert data["title"] == "Cached"


async def test_throttle_continues_same_body_after_many_steps(slow_jobs: Jobs) -> None:
    """Deferral at a late graph-like step does not restart earlier work."""
    visited: list[int] = []
    attempts_at_last = 0
    limiter = RateLimiter(delay=0)

    async def work() -> dict[str, list[int]]:
        nonlocal attempts_at_last
        for node in range(40):

            async def request(current_node: int = node) -> int:
                nonlocal attempts_at_last
                if current_node == 39:
                    attempts_at_last += 1
                    if attempts_at_last == 1:
                        response = httpx.Response(
                            429, request=httpx.Request("GET", "https://example.test")
                        )
                        raise httpx.HTTPStatusError(
                            "throttled", request=response.request, response=response
                        )
                return current_node

            visited.append(await with_s2_retry(request, limiter, base_delay=0.01))
        return {"visited": visited}

    handle = await _run_s2_body(
        work(), jobs=slow_jobs, config=JobsConfig(), tool="graph_like_work"
    )
    assert "Semantic Scholar" in handle["reason"]
    while True:
        record = await slow_jobs.poll(handle["job_id"])
        if record["status"] == "completed":
            break
        await asyncio.sleep(0.01)
    assert record["result"] == {"visited": list(range(40))}
    assert attempts_at_last == 2


async def test_existing_shared_cooldown_defers_next_call(slow_jobs: Jobs) -> None:
    """A tool waiting on another call's 429 gets a reasoned handle."""
    limiter = RateLimiter(delay=0)
    limiter.cooldown(0.05)

    async def work() -> dict[str, bool]:
        async def request() -> dict[str, bool]:
            return {"answered": True}

        return await with_s2_retry(request, limiter)

    handle = await _run_s2_body(
        work(), jobs=slow_jobs, config=JobsConfig(), tool="waiting_call"
    )
    assert "Semantic Scholar" in handle["reason"]
    while True:
        record = await slow_jobs.poll(handle["job_id"])
        if record["status"] == "completed":
            break
        await asyncio.sleep(0.01)
    assert record["result"] == {"answered": True}


async def test_throttle_stops_before_job_record_expires() -> None:
    """A persistent 429 resolves to a retryable payload within the TTL."""
    config = JobsConfig(soft_deadline_s=1, result_ttl_s=0.18)
    jobs = build_jobs(ServerConfig(kv_store_url="memory://"), config)
    attempts = 0

    async def work() -> dict[str, str]:
        nonlocal attempts

        async def refused() -> dict[str, str]:
            nonlocal attempts
            attempts += 1
            response = httpx.Response(
                429, request=httpx.Request("GET", "https://example.test")
            )
            raise httpx.HTTPStatusError(
                "throttled", request=response.request, response=response
            )

        return await with_s2_retry(refused, RateLimiter(delay=0), base_delay=0.01)

    handle = await _run_s2_body(work(), jobs=jobs, config=config, tool="always_429")
    while True:
        record = await jobs.poll(handle["job_id"])
        if record["status"] == "completed":
            break
        await asyncio.sleep(0.01)
    assert record["result"] == {"error": "rate_limited", "retryable": True}
    assert attempts > 1


async def test_job_cap_cancels_throttled_body() -> None:
    """A rejected deferred handle leaves no untracked request running."""
    config = JobsConfig(soft_deadline_s=1, result_ttl_s=1, max_per_subject=1)
    jobs = build_jobs(ServerConfig(kv_store_url="memory://"), config)
    await jobs.start(asyncio.sleep(0.2, result={}), tool="occupy_slot")
    cancelled = asyncio.Event()

    async def work() -> dict[str, str]:
        try:

            async def refused() -> dict[str, str]:
                response = httpx.Response(
                    429, request=httpx.Request("GET", "https://example.test")
                )
                raise httpx.HTTPStatusError(
                    "throttled", request=response.request, response=response
                )

            return await with_s2_retry(refused, RateLimiter(delay=0), base_delay=0.01)
        finally:
            cancelled.set()

    with pytest.raises(JobLimitExceededError):
        await _run_s2_body(work(), jobs=jobs, config=config, tool="blocked")
    assert cancelled.is_set()
    await asyncio.sleep(0.2)
