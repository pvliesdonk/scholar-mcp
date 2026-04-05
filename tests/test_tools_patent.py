"""Tests for search_patents and get_patent MCP tools."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client

from scholar_mcp._epo_client import EpoClient, EpoRateLimitedError
from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_patent import _build_cql, register_patent_tools

# ---------------------------------------------------------------------------
# Inline fixtures
# ---------------------------------------------------------------------------

_BIBLIO_RESULT = {
    "title": "Test Patent",
    "abstract": "Test abstract.",
    "applicants": ["TEST CORP"],
    "inventors": [],
    "publication_number": "EP.1234567.A1",
    "publication_date": "2020-01-15",
    "filing_date": "2019-06-01",
    "priority_date": "2019-01-15",
    "family_id": "12345678",
    "classifications": ["H04L29/06"],
    "url": "https://worldwide.espacenet.com/patent/search/family/12345678/publication/EP1234567A1",
}

_SEARCH_RESULT = {
    "total_count": 1,
    "references": [
        {"country": "EP", "number": "1234567", "kind": "A1"},
    ],
}


# ---------------------------------------------------------------------------
# _build_cql unit tests
# ---------------------------------------------------------------------------


def test_build_cql_basic_query() -> None:
    """Basic query maps to ta= CQL field."""
    cql = _build_cql("machine learning")
    assert cql == 'ta="machine learning"'


def test_build_cql_with_applicant() -> None:
    """Applicant name is appended as pa= field."""
    cql = _build_cql("neural networks", applicant="ACME Corp")
    assert 'ta="neural networks"' in cql
    assert 'pa="ACME Corp"' in cql
    assert " AND " in cql


def test_build_cql_with_inventor() -> None:
    """Inventor name is appended as in= field."""
    cql = _build_cql("polymer synthesis", inventor="Jane Doe")
    assert 'in="Jane Doe"' in cql


def test_build_cql_with_cpc() -> None:
    """CPC classification code is appended as cpc= field."""
    cql = _build_cql("battery", cpc_classification="H01M10/00")
    assert 'cpc="H01M10/00"' in cql


def test_build_cql_with_jurisdiction() -> None:
    """Jurisdiction code is appended as pn= field."""
    cql = _build_cql("fuel cell", jurisdiction="EP")
    assert "pn=EP" in cql


def test_build_cql_date_range_both() -> None:
    """Both date_from and date_to produce 'within' expression."""
    cql = _build_cql("solar panel", date_from="2020-01-01", date_to="2023-12-31")
    assert "pd within 20200101,20231231" in cql


def test_build_cql_date_range_from_only() -> None:
    """Only date_from produces >= expression."""
    cql = _build_cql("wind turbine", date_from="2021-06-01")
    assert "pd >= 20210601" in cql


def test_build_cql_date_range_to_only() -> None:
    """Only date_to produces <= expression."""
    cql = _build_cql("superconductor", date_to="2022-12-31")
    assert "pd <= 20221231" in cql


def test_build_cql_date_type_filing() -> None:
    """Filing date type uses ad= field."""
    cql = _build_cql("semiconductor", date_from="2020-01-01", date_type="filing")
    assert "ad >= 20200101" in cql


def test_build_cql_date_type_priority() -> None:
    """Priority date type uses prd= field."""
    cql = _build_cql("optical fiber", date_to="2021-12-31", date_type="priority")
    assert "prd <= 20211231" in cql


def test_build_cql_all_params() -> None:
    """All parameters produce a well-formed AND-joined CQL expression."""
    cql = _build_cql(
        "CRISPR",
        cpc_classification="C12N15/00",
        applicant="BioTech Inc",
        inventor="Alice Smith",
        date_from="2018-01-01",
        date_to="2023-12-31",
        date_type="publication",
        jurisdiction="WO",
    )
    parts = cql.split(" AND ")
    assert len(parts) == 6
    assert any('ta="CRISPR"' in p for p in parts)
    assert any('cpc="C12N15/00"' in p for p in parts)
    assert any('pa="BioTech Inc"' in p for p in parts)
    assert any('in="Alice Smith"' in p for p in parts)
    assert any("pd within" in p for p in parts)
    assert any("pn=WO" in p for p in parts)


def test_build_cql_strips_dashes_from_dates() -> None:
    """Date strings like '2020-01-01' are normalised to '20200101'."""
    cql = _build_cql("test", date_from="2020-01-01")
    assert "20200101" in cql
    assert "-" not in cql.split("pd")[1]


def test_build_cql_escapes_quotes() -> None:
    """User-supplied values containing double quotes are escaped in CQL."""
    result = _build_cql('solar "cell"')
    assert '\\"' in result or "'" in result


# ---------------------------------------------------------------------------
# FastMCP fixture helpers
# ---------------------------------------------------------------------------


def _make_epo_client(
    *,
    search_result: dict | None = None,
    biblio_result: dict | None = None,
    raise_on_search: Exception | None = None,
    raise_on_biblio: Exception | None = None,
) -> EpoClient:
    """Return a mock EpoClient with configurable responses."""
    mock_ops = MagicMock()
    client = EpoClient(consumer_key="k", consumer_secret="s", _client=mock_ops)
    if raise_on_search is not None:
        client.search = AsyncMock(side_effect=raise_on_search)
    else:
        client.search = AsyncMock(return_value=search_result or _SEARCH_RESULT)
    if raise_on_biblio is not None:
        client.get_biblio = AsyncMock(side_effect=raise_on_biblio)
    else:
        client.get_biblio = AsyncMock(return_value=biblio_result or _BIBLIO_RESULT)
    return client


@pytest.fixture
def epo_client() -> EpoClient:
    """Default mock EpoClient for tests."""
    return _make_epo_client()


@pytest.fixture
def mcp_with_epo(bundle: ServiceBundle, epo_client: EpoClient) -> FastMCP:
    """FastMCP instance with patent tools and a mock EpoClient wired in."""
    bundle.epo = epo_client

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)
    return app


# ---------------------------------------------------------------------------
# search_patents tool tests
# ---------------------------------------------------------------------------


async def test_search_patents_returns_results(
    mcp_with_epo: FastMCP,
) -> None:
    """search_patents returns EPO search results as JSON."""
    async with Client(mcp_with_epo) as client:
        result = await client.call_tool("search_patents", {"query": "machine learning"})
    data = json.loads(result.content[0].text)
    assert data["total_count"] == 1
    assert data["references"][0]["country"] == "EP"


async def test_search_patents_uses_cache(
    bundle: ServiceBundle, epo_client: EpoClient
) -> None:
    """search_patents returns cached result without calling EPO API."""
    cql = 'ta="cached query"'
    # Cache key includes CQL + range (default offset=0, limit=10 → range_begin=1, range_end=10)
    cache_key = f"{cql}|1-10"
    cached_data = {"total_count": 99, "references": []}
    await bundle.cache.set_patent_search(cache_key, cached_data)

    bundle.epo = epo_client

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async with Client(app) as client:
        result = await client.call_tool("search_patents", {"query": "cached query"})
    data = json.loads(result.content[0].text)
    assert data["total_count"] == 99
    # EPO API should not have been called
    epo_client.search.assert_not_called()  # type: ignore[union-attr]


async def test_search_patents_different_offsets_different_cache_entries(
    bundle: ServiceBundle,
) -> None:
    """Different offsets produce distinct cache entries so pages don't collide."""
    from scholar_mcp._tools_patent import _build_cql

    cql = _build_cql("battery")
    page1_key = f"{cql}|1-5"
    page2_key = f"{cql}|6-10"
    page1_data = {"total_count": 100, "references": [{"page": 1}]}
    page2_data = {"total_count": 100, "references": [{"page": 2}]}

    await bundle.cache.set_patent_search(page1_key, page1_data)
    await bundle.cache.set_patent_search(page2_key, page2_data)

    cached1 = await bundle.cache.get_patent_search(page1_key)
    cached2 = await bundle.cache.get_patent_search(page2_key)

    assert cached1 is not None
    assert cached2 is not None
    assert cached1["references"][0]["page"] == 1
    assert cached2["references"][0]["page"] == 2
    # They must be independent entries
    assert cached1 != cached2


async def test_search_patents_rate_limited_queues(
    bundle: ServiceBundle,
) -> None:
    """search_patents queues the task when EPO rate-limits the request."""
    call_count = 0

    async def _flaky_search(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise EpoRateLimitedError("yellow")
        return _SEARCH_RESULT

    epo = _make_epo_client()
    epo.search = _flaky_search  # type: ignore[method-assign]
    bundle.epo = epo

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)
    from scholar_mcp._tools_tasks import register_task_tools

    register_task_tools(app)

    async with Client(app) as client:
        result = await client.call_tool("search_patents", {"query": "throttled query"})
        data = json.loads(result.content[0].text)
        assert data["queued"] is True
        assert data["tool"] == "search_patents"

        # Poll for background result
        for _ in range(40):
            poll = await client.call_tool(
                "get_task_result", {"task_id": data["task_id"]}
            )
            poll_data = json.loads(poll.content[0].text)
            if poll_data["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(0.05)
        assert poll_data["status"] == "completed"
        inner = json.loads(poll_data["result"])
        assert inner["total_count"] == 1


async def test_search_patents_with_filters(
    bundle: ServiceBundle, epo_client: EpoClient
) -> None:
    """search_patents passes CQL filters to EPO client."""
    bundle.epo = epo_client

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async with Client(app) as client:
        await client.call_tool(
            "search_patents",
            {
                "query": "battery",
                "applicant": "Tesla Inc",
                "cpc_classification": "H01M10/00",
                "jurisdiction": "EP",
            },
        )
    # Verify that the CQL passed to the EPO client contains the expected clauses
    call_args = epo_client.search.call_args  # type: ignore[union-attr]
    cql_used = (
        call_args.args[0] if call_args.args else call_args.kwargs.get("cql_query", "")
    )
    assert 'ta="battery"' in cql_used
    assert 'pa="Tesla Inc"' in cql_used
    assert 'cpc="H01M10/00"' in cql_used
    assert "pn=EP" in cql_used


async def test_search_patents_range_from_limit_offset(
    bundle: ServiceBundle, epo_client: EpoClient
) -> None:
    """search_patents maps limit/offset to range_begin/range_end."""
    bundle.epo = epo_client

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async with Client(app) as client:
        await client.call_tool(
            "search_patents", {"query": "test", "limit": 5, "offset": 10}
        )
    call_args = epo_client.search.call_args  # type: ignore[union-attr]
    assert call_args.kwargs.get("range_begin") == 11  # offset+1 (1-based)
    assert call_args.kwargs.get("range_end") == 15  # offset+limit


# ---------------------------------------------------------------------------
# get_patent tool tests
# ---------------------------------------------------------------------------


async def test_get_patent_returns_biblio(
    mcp_with_epo: FastMCP,
) -> None:
    """get_patent returns bibliographic data as JSON."""
    async with Client(mcp_with_epo) as client:
        result = await client.call_tool("get_patent", {"patent_number": "EP1234567A1"})
    data = json.loads(result.content[0].text)
    assert data["patent_number"] == "EP.1234567.A1"
    assert data["biblio"]["title"] == "Test Patent"


async def test_get_patent_caches_result(
    bundle: ServiceBundle, epo_client: EpoClient
) -> None:
    """get_patent stores biblio result in cache after first fetch."""
    bundle.epo = epo_client

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async with Client(app) as client:
        await client.call_tool("get_patent", {"patent_number": "EP1234567A1"})

    cached = await bundle.cache.get_patent("EP.1234567.A1")
    assert cached is not None
    assert cached["title"] == "Test Patent"


async def test_get_patent_cache_hit_skips_api(
    bundle: ServiceBundle, epo_client: EpoClient
) -> None:
    """get_patent returns cached biblio without calling EPO API."""
    cached_biblio = {
        "title": "Cached Patent",
        "applicants": ["CACHED CORP"],
        "publication_number": "EP.9999999.B1",
    }
    await bundle.cache.set_patent("EP.9999999.B1", cached_biblio)

    bundle.epo = epo_client

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async with Client(app) as client:
        result = await client.call_tool("get_patent", {"patent_number": "EP9999999B1"})
    data = json.loads(result.content[0].text)
    assert data["biblio"]["title"] == "Cached Patent"
    epo_client.get_biblio.assert_not_called()  # type: ignore[union-attr]


async def test_get_patent_invalid_number_returns_error(
    mcp_with_epo: FastMCP,
) -> None:
    """get_patent returns error JSON for an unparseable patent number."""
    async with Client(mcp_with_epo) as client:
        result = await client.call_tool("get_patent", {"patent_number": "NOT_A_PATENT"})
    data = json.loads(result.content[0].text)
    assert data["error"] == "invalid_patent_number"
    assert "detail" in data


async def test_get_patent_default_sections_biblio_only(
    bundle: ServiceBundle, epo_client: EpoClient
) -> None:
    """get_patent defaults to sections=['biblio'] when none provided."""
    bundle.epo = epo_client

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async with Client(app) as client:
        result = await client.call_tool("get_patent", {"patent_number": "EP1234567A1"})
    data = json.loads(result.content[0].text)
    assert "biblio" in data
    # No other sections in Phase 1
    assert "claims" not in data
    assert "description" not in data


async def test_get_patent_unknown_sections_returns_notice(
    mcp_with_epo: FastMCP,
) -> None:
    """Phase 1: non-biblio sections produce a notice in the result."""
    async with Client(mcp_with_epo) as client:
        result = await client.call_tool(
            "get_patent",
            {"patent_number": "EP1234567A1", "sections": ["biblio", "claims"]},
        )
    data = json.loads(result.content[0].text)
    assert "biblio" in data
    assert "claims" not in data
    assert "notice" in data
    assert "claims" in data["notice"]


async def test_get_patent_only_unavailable_sections_returns_notice(
    mcp_with_epo: FastMCP,
) -> None:
    """Phase 1: requesting only non-biblio sections returns notice without biblio."""
    async with Client(mcp_with_epo) as client:
        result = await client.call_tool(
            "get_patent",
            {"patent_number": "EP1234567A1", "sections": ["claims", "description"]},
        )
    data = json.loads(result.content[0].text)
    assert "biblio" not in data
    assert "notice" in data
    assert "claims" in data["notice"]
    assert "description" in data["notice"]


async def test_get_patent_empty_biblio_returns_error(
    bundle: ServiceBundle,
) -> None:
    """get_patent returns error JSON when EPO returns empty/minimal biblio."""
    empty_biblio = {
        "title": "",
        "abstract": "",
        "applicants": [],
        "inventors": [],
        "publication_number": "",
        "publication_date": "",
        "filing_date": "",
        "priority_date": "",
        "family_id": "",
        "classifications": [],
        "url": "",
    }
    epo = _make_epo_client(biblio_result=empty_biblio)
    bundle.epo = epo

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async with Client(app) as client:
        result = await client.call_tool("get_patent", {"patent_number": "EP1234567A1"})
    data = json.loads(result.content[0].text)
    assert data["error"] == "patent_not_found"
    assert "detail" in data
    # Empty result should not be cached
    cached = await bundle.cache.get_patent("EP.1234567.A1")
    assert cached is None


async def test_get_patent_rate_limited_queues(
    bundle: ServiceBundle,
) -> None:
    """get_patent queues the task when EPO rate-limits the request."""
    call_count = 0

    async def _flaky_biblio(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise EpoRateLimitedError("red")
        return _BIBLIO_RESULT

    epo = _make_epo_client()
    epo.get_biblio = _flaky_biblio  # type: ignore[method-assign]
    bundle.epo = epo

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)
    from scholar_mcp._tools_tasks import register_task_tools

    register_task_tools(app)

    async with Client(app) as client:
        result = await client.call_tool("get_patent", {"patent_number": "EP1234567A1"})
        data = json.loads(result.content[0].text)
        assert data["queued"] is True
        assert data["tool"] == "get_patent"

        for _ in range(40):
            poll = await client.call_tool(
                "get_task_result", {"task_id": data["task_id"]}
            )
            poll_data = json.loads(poll.content[0].text)
            if poll_data["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(0.05)
        assert poll_data["status"] == "completed"
        inner = json.loads(poll_data["result"])
        assert inner["biblio"]["title"] == "Test Patent"


async def test_get_patent_no_epo_client_returns_error(
    bundle: ServiceBundle,
) -> None:
    """get_patent returns error JSON when EPO client is not configured."""
    bundle.epo = None

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async with Client(app) as client:
        result = await client.call_tool("get_patent", {"patent_number": "EP1234567A1"})
    data = json.loads(result.content[0].text)
    assert data["error"] == "epo_not_configured"


async def test_search_patents_no_epo_client_returns_error(
    bundle: ServiceBundle,
) -> None:
    """search_patents returns error JSON when EPO client is not configured."""
    bundle.epo = None

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async with Client(app) as client:
        result = await client.call_tool("search_patents", {"query": "test"})
    data = json.loads(result.content[0].text)
    assert data["error"] == "epo_not_configured"
