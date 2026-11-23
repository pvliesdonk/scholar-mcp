"""Tests for CrossRefClient."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

from scholar_mcp._crossref_client import CrossRefClient
from scholar_mcp._rate_limiter import RateLimitedError, RateLimiter

CR_BASE = "https://api.crossref.org"


@pytest.fixture
def client() -> CrossRefClient:
    return CrossRefClient(
        http_client=httpx.AsyncClient(base_url=CR_BASE),
        limiter=RateLimiter(delay=0.0),
    )


@pytest.mark.respx(base_url=CR_BASE)
async def test_get_by_doi_returns_data(
    respx_mock: respx.MockRouter, client: CrossRefClient
) -> None:
    doi = "10.1234/test"
    respx_mock.get(f"/works/{doi}").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "ok",
                "message": {
                    "DOI": doi,
                    "title": ["Test Paper"],
                    "type": "journal-article",
                },
            },
        )
    )
    result = await client.get_by_doi(doi)
    assert result is not None
    assert result["DOI"] == doi
    assert result["title"] == ["Test Paper"]


@pytest.mark.respx(base_url=CR_BASE)
async def test_get_by_doi_returns_none_on_404(
    respx_mock: respx.MockRouter, client: CrossRefClient
) -> None:
    respx_mock.get("/works/10.0/missing").mock(return_value=httpx.Response(404))
    result = await client.get_by_doi("10.0/missing")
    assert result is None


@pytest.mark.respx(base_url=CR_BASE)
async def test_get_by_doi_returns_none_on_error(
    respx_mock: respx.MockRouter, client: CrossRefClient
) -> None:
    respx_mock.get("/works/10.0/fail").mock(return_value=httpx.Response(500))
    result = await client.get_by_doi("10.0/fail")
    assert result is None


@pytest.mark.respx(base_url=CR_BASE)
async def test_get_by_doi_logs_not_found_at_debug(
    respx_mock: respx.MockRouter,
    client: CrossRefClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 404 is a missing record: DEBUG, distinct from a throttle."""
    respx_mock.get("/works/10.0/missing").mock(return_value=httpx.Response(404))
    with caplog.at_level(logging.DEBUG, logger="scholar_mcp._crossref_client"):
        assert await client.get_by_doi("10.0/missing") is None
    [rec] = caplog.records
    assert rec.msg.startswith("crossref_not_found")
    assert rec.levelno == logging.DEBUG


@pytest.mark.respx(base_url=CR_BASE)
async def test_get_by_doi_raises_rate_limited_on_429(
    respx_mock: respx.MockRouter,
    client: CrossRefClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 429 raises RateLimitedError and logs one line without a traceback."""
    respx_mock.get("/works/10.0/busy").mock(return_value=httpx.Response(429))
    with (
        caplog.at_level(logging.DEBUG, logger="scholar_mcp._crossref_client"),
        pytest.raises(RateLimitedError),
    ):
        await client.get_by_doi("10.0/busy")
    [rec] = caplog.records
    assert rec.msg.startswith("crossref_rate_limited")
    assert rec.levelno == logging.WARNING
    assert rec.exc_info is None


@pytest.mark.respx(base_url=CR_BASE)
async def test_get_by_doi_returns_none_on_malformed_body(
    respx_mock: respx.MockRouter, client: CrossRefClient
) -> None:
    """A body that is not JSON is an upstream error, not an exception."""
    respx_mock.get("/works/10.0/garbled").mock(
        return_value=httpx.Response(200, content=b"<html>oops</html>")
    )
    assert await client.get_by_doi("10.0/garbled") is None


async def test_get_by_doi_acquires_limiter_per_request() -> None:
    """Every request waits on the shared limiter first."""
    limiter = MagicMock()
    limiter.acquire = AsyncMock()
    transport = httpx.MockTransport(
        lambda _req: httpx.Response(200, json={"message": {"DOI": "x"}})
    )
    async with httpx.AsyncClient(base_url=CR_BASE, transport=transport) as http:
        cr = CrossRefClient(http, limiter=limiter)
        await cr.get_by_doi("10.0/a")
        await cr.get_by_doi("10.0/b")
    assert limiter.acquire.await_count == 2


async def test_get_by_doi_keeps_one_request_in_flight() -> None:
    """Concurrent lookups are serialised: the pool allows one in flight."""
    in_flight = 0
    peak = 0

    async def handler(_req: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        in_flight -= 1
        return httpx.Response(200, json={"message": {"DOI": "x"}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url=CR_BASE, transport=transport) as http:
        cr = CrossRefClient(http, limiter=RateLimiter(delay=0.0))
        results = await asyncio.gather(*(cr.get_by_doi(f"10.0/{i}") for i in range(5)))
    assert all(r == {"DOI": "x"} for r in results)
    assert peak == 1
