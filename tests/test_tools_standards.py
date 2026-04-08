"""Tests for standards MCP tools."""

from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client

from scholar_mcp._docling_client import DoclingClient
from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_standards import register_standards_tools

IETF_BASE = "https://datatracker.ietf.org"

SAMPLE_RFC_DOC = {
    "objects": [
        {
            "name": "rfc9000",
            "title": "QUIC: A UDP-Based Multiplexed and Secure Transport",
            "abstract": "This document defines QUIC.",
            "std_level": "proposed_standard",
            "pub_date": "2021-05-01",
        }
    ],
    "meta": {"total_count": 1},
}


@pytest.fixture
def mcp(bundle: ServiceBundle) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_standards_tools(app)
    return app


@pytest.mark.respx(base_url=IETF_BASE)
async def test_resolve_unambiguous(respx_mock: respx.MockRouter, mcp: FastMCP) -> None:
    """resolve_standard_identifier returns canonical + record for known RFC."""
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC_DOC)
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "resolve_standard_identifier", {"raw": "rfc9000"}
        )
    data = json.loads(result.content[0].text)
    assert data["canonical"] == "RFC 9000"
    assert data["body"] == "IETF"
    assert data["record"] is not None
    assert (
        data["record"]["title"] == "QUIC: A UDP-Based Multiplexed and Secure Transport"
    )


async def test_resolve_unknown_returns_null(mcp: FastMCP) -> None:
    """resolve_standard_identifier returns nulls for unknown input."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "resolve_standard_identifier", {"raw": "totally unknown xyz"}
        )
    data = json.loads(result.content[0].text)
    assert data["canonical"] is None
    assert data["body"] is None
    assert data["record"] is None


async def test_resolve_uses_alias_cache(mcp: FastMCP, bundle: ServiceBundle) -> None:
    """resolve_standard_identifier uses alias cache on repeated calls."""
    await bundle.cache.set_standard_alias("rfc9000", "RFC 9000")
    await bundle.cache.set_standard(
        "RFC 9000",
        {
            "identifier": "RFC 9000",
            "title": "QUIC",
            "body": "IETF",
            "full_text_available": True,
            "url": "https://rfc-editor.org/info/rfc9000",
        },
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "resolve_standard_identifier", {"raw": "rfc9000"}
        )
    data = json.loads(result.content[0].text)
    assert data["canonical"] == "RFC 9000"
    assert data["record"]["title"] == "QUIC"


# ---------------------------------------------------------------------------
# search_standards tests
# ---------------------------------------------------------------------------


@pytest.mark.respx(base_url=IETF_BASE)
async def test_search_standards_returns_results(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC_DOC)
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_standards", {"query": "QUIC transport", "body": "IETF"}
        )
    data = json.loads(result.content[0].text)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["body"] == "IETF"


@pytest.mark.respx(base_url=IETF_BASE)
async def test_search_standards_caches_results(
    respx_mock: respx.MockRouter, mcp: FastMCP, bundle: ServiceBundle
) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC_DOC)
    )
    async with Client(mcp) as client:
        await client.call_tool(
            "search_standards", {"query": "cache test", "body": "IETF"}
        )

    cache_key = hashlib.sha256(b"cache test:IETF:10").hexdigest()
    cached = await bundle.cache.get_standards_search(cache_key)
    assert cached is not None


@pytest.mark.respx(base_url=IETF_BASE)
async def test_search_standards_cache_hit_skips_network(
    respx_mock: respx.MockRouter, mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """Second search for same query uses cache, not API."""
    call_count = 0

    def side_effect(request):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=SAMPLE_RFC_DOC)

    respx_mock.get("/api/v1/doc/document/").mock(side_effect=side_effect)
    async with Client(mcp) as client:
        await client.call_tool("search_standards", {"query": "QUIC", "body": "IETF"})
        await client.call_tool("search_standards", {"query": "QUIC", "body": "IETF"})
    assert call_count == 1


# ---------------------------------------------------------------------------
# get_standard tests
# ---------------------------------------------------------------------------


@pytest.mark.respx(base_url=IETF_BASE)
async def test_get_standard_by_fuzzy_id(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC_DOC)
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_standard", {"identifier": "rfc9000"})
    data = json.loads(result.content[0].text)
    assert data["identifier"] == "RFC 9000"
    assert data["body"] == "IETF"
    assert data["full_text_available"] is True


@pytest.mark.respx(base_url=IETF_BASE)
async def test_get_standard_caches_result(
    respx_mock: respx.MockRouter, mcp: FastMCP, bundle: ServiceBundle
) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC_DOC)
    )
    async with Client(mcp) as client:
        await client.call_tool("get_standard", {"identifier": "RFC 9000"})

    cached = await bundle.cache.get_standard("RFC 9000")
    assert cached is not None
    assert cached["title"] == "QUIC: A UDP-Based Multiplexed and Secure Transport"


@pytest.mark.respx(base_url=IETF_BASE)
async def test_get_standard_not_found(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(
            200, json={"objects": [], "meta": {"total_count": 0}}
        )
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_standard", {"identifier": "RFC 99999"})
    data = json.loads(result.content[0].text)
    assert "error" in data


async def test_get_standard_cache_hit_skips_network(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """get_standard returns cached record without a network call."""
    cached_record = {
        "identifier": "RFC 9000",
        "title": "QUIC",
        "body": "IETF",
        "full_text_available": True,
        "url": "https://www.rfc-editor.org/info/rfc9000",
    }
    await bundle.cache.set_standard("RFC 9000", cached_record)
    async with Client(mcp) as client:
        result = await client.call_tool("get_standard", {"identifier": "RFC 9000"})
    data = json.loads(result.content[0].text)
    assert data["title"] == "QUIC"


async def test_get_standard_alias_cache_hit(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """get_standard resolves via alias cache when alias was previously stored."""
    await bundle.cache.set_standard_alias("rfc9000", "RFC 9000")
    await bundle.cache.set_standard(
        "RFC 9000",
        {
            "identifier": "RFC 9000",
            "title": "QUIC cached",
            "body": "IETF",
            "full_text_available": False,
            "url": "https://www.rfc-editor.org/info/rfc9000",
        },
    )
    async with Client(mcp) as client:
        result = await client.call_tool("get_standard", {"identifier": "rfc9000"})
    data = json.loads(result.content[0].text)
    assert data["title"] == "QUIC cached"


@pytest.mark.respx(base_url=IETF_BASE)
async def test_get_standard_fetch_full_text_after_fresh_fetch(
    respx_mock: respx.MockRouter, mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """get_standard with fetch_full_text=True works when record is not yet cached."""
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC_DOC)
    )
    mock_docling = MagicMock(spec=DoclingClient)
    mock_docling.convert = AsyncMock(return_value="# RFC 9000\n...")
    bundle.docling = mock_docling  # type: ignore[assignment]

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://www.rfc-editor.org/rfc/rfc9000.html").mock(
            return_value=httpx.Response(200, content=b"<html>content</html>")
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_standard", {"identifier": "RFC 9000", "fetch_full_text": True}
            )
    data = json.loads(result.content[0].text)
    assert data.get("full_text") == "# RFC 9000\n..."


async def test_resolve_locally_resolved_but_not_found(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """resolve_standard_identifier: regex resolves but source fetch returns None."""
    with (
        patch(
            "scholar_mcp._tools_standards.resolve_identifier_local",
            return_value=("RFC 99998", "IETF"),
        ),
        patch.object(bundle.standards, "get", return_value=None),
    ):
        async with Client(mcp) as client:
            result = await client.call_tool(
                "resolve_standard_identifier", {"raw": "RFC 99998"}
            )
    data = json.loads(result.content[0].text)
    assert data["canonical"] == "RFC 99998"
    assert data["record"] is None


async def test_resolve_api_fallback_single_candidate(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """resolve_standard_identifier: API fallback returns a single unambiguous result."""
    candidate = {
        "identifier": "ETSI EN 303 645",
        "body": "ETSI",
        "title": "IoT Security",
        "full_text_available": False,
    }
    with patch.object(bundle.standards, "resolve", return_value=[candidate]):
        async with Client(mcp) as client:
            result = await client.call_tool(
                "resolve_standard_identifier", {"raw": "iot security etsi"}
            )
    data = json.loads(result.content[0].text)
    assert data["canonical"] == "ETSI EN 303 645"
    assert data["body"] == "ETSI"


async def test_resolve_api_fallback_ambiguous(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """resolve_standard_identifier: multiple API candidates returns ambiguous response."""
    candidates = [
        {
            "identifier": "RFC 1",
            "body": "IETF",
            "title": "A",
            "full_text_available": False,
        },
        {
            "identifier": "RFC 2",
            "body": "IETF",
            "title": "B",
            "full_text_available": False,
        },
    ]
    with patch.object(bundle.standards, "resolve", return_value=candidates):
        async with Client(mcp) as client:
            result = await client.call_tool(
                "resolve_standard_identifier", {"raw": "some ambiguous string"}
            )
    data = json.loads(result.content[0].text)
    assert data["ambiguous"] is True
    assert len(data["candidates"]) == 2


async def test_handle_full_text_already_present(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """_handle_full_text short-circuits when full_text is already in the record."""
    record = {
        "identifier": "RFC 9000",
        "title": "QUIC",
        "body": "IETF",
        "full_text_available": True,
        "full_text_url": "https://www.rfc-editor.org/rfc/rfc9000.html",
        "full_text": "# already converted",
        "url": "https://www.rfc-editor.org/info/rfc9000",
    }
    await bundle.cache.set_standard("RFC 9000", record)
    mock_docling = MagicMock(spec=DoclingClient)
    mock_docling.convert = AsyncMock(return_value="# should not be called")
    bundle.docling = mock_docling  # type: ignore[assignment]

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_standard", {"identifier": "RFC 9000", "fetch_full_text": True}
        )
    data = json.loads(result.content[0].text)
    assert data["full_text"] == "# already converted"
    mock_docling.convert.assert_not_called()


async def test_handle_full_text_download_error_returns_record(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """_handle_full_text returns the plain record when the download raises."""
    record = {
        "identifier": "RFC 9000",
        "title": "QUIC",
        "body": "IETF",
        "full_text_available": True,
        "full_text_url": "https://www.rfc-editor.org/rfc/rfc9000.html",
        "url": "https://www.rfc-editor.org/info/rfc9000",
    }
    await bundle.cache.set_standard("RFC 9000", record)
    mock_docling = MagicMock(spec=DoclingClient)
    mock_docling.convert = AsyncMock(side_effect=RuntimeError("timeout"))
    bundle.docling = mock_docling  # type: ignore[assignment]

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://www.rfc-editor.org/rfc/rfc9000.html").mock(
            side_effect=RuntimeError("connection failed")
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_standard", {"identifier": "RFC 9000", "fetch_full_text": True}
            )
    data = json.loads(result.content[0].text)
    assert data["identifier"] == "RFC 9000"
    assert "full_text" not in data


# ---------------------------------------------------------------------------
# Full-text via docling tests
# ---------------------------------------------------------------------------


async def test_get_standard_fetch_full_text_with_docling(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """get_standard with fetch_full_text=True and docling returns enriched record."""
    mock_docling = MagicMock(spec=DoclingClient)
    mock_docling.convert = AsyncMock(return_value="# RFC 9000\n...")

    record = {
        "identifier": "RFC 9000",
        "title": "QUIC",
        "body": "IETF",
        "full_text_available": True,
        "full_text_url": "https://www.rfc-editor.org/rfc/rfc9000.html",
        "url": "https://www.rfc-editor.org/info/rfc9000",
    }
    await bundle.cache.set_standard("RFC 9000", record)
    bundle.docling = mock_docling  # type: ignore[assignment]

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://www.rfc-editor.org/rfc/rfc9000.html").mock(
            return_value=httpx.Response(200, content=b"<html>RFC content</html>")
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_standard", {"identifier": "RFC 9000", "fetch_full_text": True}
            )
    data = json.loads(result.content[0].text)
    assert data.get("full_text") == "# RFC 9000\n..."
    assert data["identifier"] == "RFC 9000"


async def test_get_standard_fetch_full_text_no_docling(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """get_standard with fetch_full_text=True but no docling returns record only."""
    record = {
        "identifier": "RFC 9000",
        "title": "QUIC",
        "body": "IETF",
        "full_text_available": True,
        "full_text_url": "https://www.rfc-editor.org/rfc/rfc9000.html",
        "url": "https://www.rfc-editor.org/info/rfc9000",
    }
    await bundle.cache.set_standard("RFC 9000", record)
    # bundle.docling is None by default in test fixture

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_standard", {"identifier": "RFC 9000", "fetch_full_text": True}
        )
    data = json.loads(result.content[0].text)
    assert data["identifier"] == "RFC 9000"
    assert "full_text_url" in data


async def test_resolve_alias_cache_hit_but_record_cache_miss(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """resolve_standard_identifier: alias in cache but record expired — falls through to regex."""
    # Alias entry exists but the record was evicted from cache
    await bundle.cache.set_standard_alias("rfc9000", "RFC 9000")
    # No record stored — the alias-cache branch falls through at line 63

    with patch.object(bundle.standards, "get", return_value=None):
        async with Client(mcp) as client:
            result = await client.call_tool(
                "resolve_standard_identifier", {"raw": "rfc9000"}
            )
    data = json.loads(result.content[0].text)
    # Falls through to regex which also gets None from standards.get
    assert data["canonical"] == "RFC 9000"
    assert data["record"] is None


@pytest.mark.respx(base_url=IETF_BASE)
async def test_get_standard_alias_cache_hit_record_not_cached(
    respx_mock: respx.MockRouter, mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """get_standard: alias resolves but record not cached — fetches fresh from source."""
    respx_mock.get("/api/v1/doc/document/").mock(
        return_value=httpx.Response(200, json=SAMPLE_RFC_DOC)
    )
    await bundle.cache.set_standard_alias("rfc9000", "RFC 9000")
    # No record in cache — goes to step 3 (API fetch)

    async with Client(mcp) as client:
        result = await client.call_tool("get_standard", {"identifier": "rfc9000"})
    data = json.loads(result.content[0].text)
    assert data["identifier"] == "RFC 9000"


async def test_handle_full_text_rate_limited_queues_task(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
    """_handle_full_text queues a background task when docling is rate-limited."""
    from scholar_mcp._rate_limiter import RateLimitedError

    record = {
        "identifier": "RFC 9000",
        "title": "QUIC",
        "body": "IETF",
        "full_text_available": True,
        "full_text_url": "https://www.rfc-editor.org/rfc/rfc9000.html",
        "url": "https://www.rfc-editor.org/info/rfc9000",
    }
    await bundle.cache.set_standard("RFC 9000", record)
    mock_docling = MagicMock(spec=DoclingClient)
    mock_docling.convert = AsyncMock(side_effect=RateLimitedError("rate limited"))
    bundle.docling = mock_docling  # type: ignore[assignment]

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://www.rfc-editor.org/rfc/rfc9000.html").mock(
            return_value=httpx.Response(200, content=b"<html>content</html>")
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_standard", {"identifier": "RFC 9000", "fetch_full_text": True}
            )
    data = json.loads(result.content[0].text)
    assert data.get("queued") is True
    assert "task_id" in data
