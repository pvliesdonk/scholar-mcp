"""Tests for standards MCP tools."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client

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
async def test_resolve_unambiguous(
    respx_mock: respx.MockRouter, mcp: FastMCP
) -> None:
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
    assert data["record"]["title"] == "QUIC: A UDP-Based Multiplexed and Secure Transport"


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


async def test_resolve_uses_alias_cache(
    mcp: FastMCP, bundle: ServiceBundle
) -> None:
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
