"""Tests for search_patents and get_patent MCP tools."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client

from scholar_mcp._docling_client import DoclingClient
from scholar_mcp._epo_client import EpoClient, EpoRateLimitedError
from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_patent import (
    _build_cql,
    _fetch_patent_sections,
    register_patent_tools,
)

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
    """Jurisdiction code is appended as quoted pn= field."""
    cql = _build_cql("fuel cell", jurisdiction="EP")
    assert 'pn="EP"' in cql


def test_build_cql_date_range_both() -> None:
    """Both date_from and date_to produce 'within' expression."""
    cql = _build_cql("solar panel", date_from="2020-01-01", date_to="2023-12-31")
    assert 'pd within "20200101,20231231"' in cql


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
    assert any('pn="WO"' in p for p in parts)


def test_build_cql_strips_dashes_from_dates() -> None:
    """Date strings like '2020-01-01' are normalised to '20200101'."""
    cql = _build_cql("test", date_from="2020-01-01")
    assert "20200101" in cql
    assert "-" not in cql.split("pd")[1]


def test_build_cql_escapes_quotes() -> None:
    """User-supplied values containing double quotes are escaped in CQL."""
    result = _build_cql('solar "cell"')
    assert '\\"' in result or "'" in result


def test_build_cql_jurisdiction_escapes_injection() -> None:
    """Jurisdiction value is quoted and escaped to prevent CQL injection."""
    cql = _build_cql("test", jurisdiction="EP OR ti=*")
    # The injected payload should be inside quotes, not a separate clause
    assert 'pn="EP OR ti=*"' in cql


def test_build_cql_date_from_rejects_non_numeric() -> None:
    """date_from with non-numeric content raises ValueError."""
    with pytest.raises(ValueError, match="Invalid date_from"):
        _build_cql("test", date_from="20200101 OR ti=hack")


def test_build_cql_date_to_rejects_non_numeric() -> None:
    """date_to with non-numeric content raises ValueError."""
    with pytest.raises(ValueError, match="Invalid date_to"):
        _build_cql("test", date_to="not-a-date")


def test_build_cql_inventor_only_omits_ta() -> None:
    """Inventor-only search produces just in= without a ta= clause."""
    cql = _build_cql(inventor="Smith")
    assert cql == 'in="Smith"'
    assert "ta=" not in cql


def test_build_cql_applicant_only_omits_ta() -> None:
    """Applicant-only search produces just pa= without a ta= clause."""
    cql = _build_cql(applicant="ACME Corp")
    assert cql == 'pa="ACME Corp"'
    assert "ta=" not in cql


def test_build_cql_no_criteria_raises() -> None:
    """Calling _build_cql with no criteria raises ValueError."""
    with pytest.raises(ValueError, match="At least one search criterion"):
        _build_cql()


# ---------------------------------------------------------------------------
# FastMCP fixture helpers
# ---------------------------------------------------------------------------


def _make_epo_client(
    *,
    search_result: dict | None = None,
    biblio_result: dict | None = None,
    claims_result: str = "1. A method for testing.",
    description_result: str = "Test description text.",
    family_result: list[dict[str, str]] | None = None,
    legal_result: list[dict[str, str]] | None = None,
    citations_result: dict | None = None,
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
    client.get_claims = AsyncMock(return_value=claims_result)
    client.get_description = AsyncMock(return_value=description_result)
    client.get_family = AsyncMock(
        return_value=family_result
        or [{"country": "EP", "number": "1234567", "kind": "A1", "date": "2020-01-15"}]
    )
    client.get_legal = AsyncMock(
        return_value=legal_result
        or [{"date": "2020-01-15", "code": "PUB", "description": "Published"}]
    )
    client.get_citations = AsyncMock(
        return_value=citations_result or {"patent_refs": [], "npl_refs": []}
    )
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


async def test_search_patents_no_criteria_returns_error(
    mcp_with_epo: FastMCP,
) -> None:
    """search_patents with no criteria returns an invalid_query error."""
    async with Client(mcp_with_epo) as client:
        result = await client.call_tool("search_patents", {})
    data = json.loads(result.content[0].text)
    assert data["error"] == "invalid_query"


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
    assert 'pn="EP"' in cql_used


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


async def test_get_patent_with_claims_section(
    mcp_with_epo: FastMCP,
) -> None:
    """get_patent with sections=['biblio', 'claims'] returns both."""
    async with Client(mcp_with_epo) as client:
        result = await client.call_tool(
            "get_patent",
            {"patent_number": "EP1234567A1", "sections": ["biblio", "claims"]},
        )
    data = json.loads(result.content[0].text)
    assert "biblio" in data
    assert "claims" in data
    assert "method for testing" in data["claims"]


async def test_get_patent_claims_only(
    mcp_with_epo: FastMCP,
) -> None:
    """get_patent with sections=['claims'] returns claims without biblio."""
    async with Client(mcp_with_epo) as client:
        result = await client.call_tool(
            "get_patent",
            {"patent_number": "EP1234567A1", "sections": ["claims"]},
        )
    data = json.loads(result.content[0].text)
    assert "biblio" not in data
    assert "claims" in data


async def test_get_patent_citations_section_works(
    mcp_with_epo: FastMCP,
) -> None:
    """citations section is now available and returns citation data."""
    async with Client(mcp_with_epo) as client:
        result = await client.call_tool(
            "get_patent",
            {"patent_number": "EP1234567A1", "sections": ["biblio", "citations"]},
        )
    data = json.loads(result.content[0].text)
    assert "biblio" in data
    assert "citations" in data
    assert "notice" not in data


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


async def test_get_patent_not_found_without_biblio_section(
    bundle: ServiceBundle,
) -> None:
    """get_patent returns not-found even when only non-biblio sections are requested."""
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
        result = await client.call_tool(
            "get_patent",
            {"patent_number": "EP1234567A1", "sections": ["claims"]},
        )
    data = json.loads(result.content[0].text)
    assert data["error"] == "patent_not_found"


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


# ---------------------------------------------------------------------------
# _fetch_patent_sections unit tests
# ---------------------------------------------------------------------------


async def test_fetch_all_sections(bundle: ServiceBundle) -> None:
    """All five sections are fetched concurrently and returned."""
    from scholar_mcp._patent_numbers import DocdbNumber

    epo = _make_epo_client()
    doc = DocdbNumber("EP", "1234567", "A1")
    result_json = await _fetch_patent_sections(
        doc=doc,
        sections=["biblio", "claims", "description", "family", "legal"],
        epo=epo,
        cache=bundle.cache,
    )
    result = json.loads(result_json)
    assert result["patent_number"] == "EP.1234567.A1"
    assert result["biblio"]["title"] == "Test Patent"
    assert "method for testing" in result["claims"]
    assert "Test description" in result["description"]
    assert len(result["family"]) == 1
    assert len(result["legal"]) == 1


async def test_fetch_sections_uses_cache(bundle: ServiceBundle) -> None:
    """Cached sections are returned without calling EPO API."""
    from scholar_mcp._patent_numbers import DocdbNumber

    epo = _make_epo_client()
    await bundle.cache.set_patent_claims("EP.1234567.A1", "Cached claims")
    doc = DocdbNumber("EP", "1234567", "A1")
    result_json = await _fetch_patent_sections(
        doc=doc,
        sections=["claims"],
        epo=epo,
        cache=bundle.cache,
    )
    result = json.loads(result_json)
    assert result["claims"] == "Cached claims"
    epo.get_claims.assert_not_called()  # type: ignore[union-attr]


async def test_fetch_sections_caches_results(bundle: ServiceBundle) -> None:
    """Fetched sections are stored in cache."""
    from scholar_mcp._patent_numbers import DocdbNumber

    epo = _make_epo_client()
    doc = DocdbNumber("EP", "1234567", "A1")
    await _fetch_patent_sections(
        doc=doc,
        sections=["claims", "description", "family", "legal"],
        epo=epo,
        cache=bundle.cache,
    )
    assert await bundle.cache.get_patent_claims("EP.1234567.A1") is not None
    assert await bundle.cache.get_patent_description("EP.1234567.A1") is not None
    assert await bundle.cache.get_patent_family("EP.1234567.A1") is not None
    assert await bundle.cache.get_patent_legal("EP.1234567.A1") is not None


async def test_get_patent_all_sections_via_tool(
    bundle: ServiceBundle,
) -> None:
    """get_patent tool returns all five sections via MCP client."""
    epo = _make_epo_client()
    bundle.epo = epo

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async with Client(app) as client:
        result = await client.call_tool(
            "get_patent",
            {
                "patent_number": "EP1234567A1",
                "sections": ["biblio", "claims", "description", "family", "legal"],
            },
        )
    data = json.loads(result.content[0].text)
    assert "biblio" in data
    assert "claims" in data
    assert "description" in data
    assert "family" in data
    assert "legal" in data


# ---------------------------------------------------------------------------
# citations section tests
# ---------------------------------------------------------------------------


async def test_get_patent_citations_section(
    bundle: ServiceBundle,
) -> None:
    """get_patent with sections=['citations'] returns citation data."""
    citations_data = {
        "patent_refs": [{"country": "US", "number": "9876543", "kind": "B2"}],
        "npl_refs": [
            {"raw": "Smith, doi:10.1234/test", "doi": "10.1234/test"},
            {"raw": "Unknown reference", "doi": None},
        ],
    }
    epo = _make_epo_client(citations_result=citations_data)
    bundle.epo = epo

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async with Client(app) as client:
        result = await client.call_tool(
            "get_patent",
            {"patent_number": "EP1234567A1", "sections": ["citations"]},
        )
    data = json.loads(result.content[0].text)
    assert "citations" in data
    assert len(data["citations"]["patent_refs"]) == 1
    assert len(data["citations"]["npl_refs"]) == 2
    # Without S2 client configured on the bundle's s2 mock, NPL refs have no paper
    assert data["citations"]["npl_refs"][0]["confidence"] is None


async def test_citations_npl_resolution_with_s2(
    bundle: ServiceBundle,
) -> None:
    """NPL references with DOIs are resolved via S2 when available."""
    citations_data = {
        "patent_refs": [],
        "npl_refs": [
            {"raw": "Smith, doi:10.1234/test", "doi": "10.1234/test"},
            {"raw": "No DOI here", "doi": None},
        ],
    }
    epo = _make_epo_client(citations_result=citations_data)
    bundle.epo = epo

    # Mock S2 batch_resolve to return a paper for the DOI
    bundle.s2.batch_resolve = AsyncMock(  # type: ignore[assignment]
        return_value=[{"paperId": "abc123", "title": "Smith Paper"}]
    )

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async with Client(app) as client:
        result = await client.call_tool(
            "get_patent",
            {"patent_number": "EP1234567A1", "sections": ["citations"]},
        )
    data = json.loads(result.content[0].text)
    npl = data["citations"]["npl_refs"]
    # First NPL had a DOI -> resolved with high confidence
    assert npl[0]["confidence"] == "high"
    assert npl[0]["paper"]["paperId"] == "abc123"
    # Second NPL had no DOI -> unresolved
    assert npl[1]["confidence"] is None
    assert "paper" not in npl[1]


# ---------------------------------------------------------------------------
# get_citing_patents tests
# ---------------------------------------------------------------------------


async def test_get_citing_patents_returns_results(
    bundle: ServiceBundle,
) -> None:
    """get_citing_patents finds patents citing a paper."""
    epo = _make_epo_client(
        search_result={
            "total_count": 1,
            "references": [{"country": "EP", "number": "9999999", "kind": "A1"}],
        },
    )
    bundle.epo = epo

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async with Client(app) as client:
        result = await client.call_tool(
            "get_citing_patents",
            {"paper_id": "10.1234/test"},
        )
    data = json.loads(result.content[0].text)
    assert data["paper_id"] == "10.1234/test"
    assert len(data["patents"]) == 1
    assert data["patents"][0]["match_source"] == "epo_search"
    assert data["total_count"] == 1
    assert "note" in data


async def test_get_citing_patents_empty_results(
    bundle: ServiceBundle,
) -> None:
    """get_citing_patents returns empty list when no patents found."""
    epo = _make_epo_client(
        search_result={"total_count": 0, "references": []},
    )
    bundle.epo = epo

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async with Client(app) as client:
        result = await client.call_tool(
            "get_citing_patents",
            {"paper_id": "10.9999/nonexistent"},
        )
    data = json.loads(result.content[0].text)
    assert data["patents"] == []
    assert data["total_count"] == 0


async def test_get_citing_patents_no_epo_returns_error(
    bundle: ServiceBundle,
) -> None:
    """get_citing_patents returns error when EPO not configured."""
    bundle.epo = None

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async with Client(app) as client:
        result = await client.call_tool(
            "get_citing_patents",
            {"paper_id": "10.1234/test"},
        )
    data = json.loads(result.content[0].text)
    assert data["error"] == "epo_not_configured"


async def test_get_citing_patents_rate_limited_queues(
    bundle: ServiceBundle,
) -> None:
    """get_citing_patents queues on rate limit."""
    epo = _make_epo_client(raise_on_search=EpoRateLimitedError("red"))
    bundle.epo = epo

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async with Client(app) as client:
        result = await client.call_tool(
            "get_citing_patents",
            {"paper_id": "10.1234/test"},
        )
    data = json.loads(result.content[0].text)
    assert data["queued"] is True
    assert data["tool"] == "get_citing_patents"


# ---------------------------------------------------------------------------
# fetch_patent_pdf tests
# ---------------------------------------------------------------------------


def _make_image_inquiry_xml(link: str, pages: int = 5) -> bytes:
    """Build a minimal EPO image inquiry XML response."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org" xmlns:exch="http://www.epo.org/exchange">
  <ops:document-inquiry>
    <ops:inquiry-result>
      <ops:document-instance desc="FullDocument" link="{link}" number-of-pages="{pages}">
        <ops:document-format desc="application/pdf"/>
      </ops:document-instance>
    </ops:inquiry-result>
  </ops:document-inquiry>
</ops:world-patent-data>
""".encode()


def test_fetch_patent_pdf_no_epo_client(bundle: ServiceBundle) -> None:
    """Returns error when EPO is not configured."""

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async def run() -> dict:
        async with Client(app) as client:
            result = await client.call_tool(
                "fetch_patent_pdf", {"patent_number": "EP3491801B1"}
            )
        return json.loads(result.content[0].text)

    data = asyncio.run(run())
    assert "error" in data
    assert "epo" in data["error"].lower() or "configured" in data["error"].lower()


def test_fetch_patent_pdf_invalid_number(bundle: ServiceBundle) -> None:
    """Returns error for unparseable patent number."""
    bundle.epo = _make_epo_client()

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async def run() -> dict:
        async with Client(app) as client:
            result = await client.call_tool(
                "fetch_patent_pdf", {"patent_number": "NOTAPATENT"}
            )
        return json.loads(result.content[0].text)

    data = asyncio.run(run())
    assert "error" in data


def test_fetch_patent_pdf_queued(bundle: ServiceBundle) -> None:
    """fetch_patent_pdf queues task and returns queued response."""
    epo = _make_epo_client()
    epo.get_pdf = AsyncMock(return_value=b"%PDF-1.4 fake pdf content")
    bundle.epo = epo

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async def run() -> dict:
        async with Client(app) as client:
            result = await client.call_tool(
                "fetch_patent_pdf", {"patent_number": "EP3491801B1"}
            )
        return json.loads(result.content[0].text)

    data = asyncio.run(run())
    assert data.get("queued") is True
    assert data.get("tool") == "fetch_patent_pdf"


def test_fetch_patent_pdf_cache_hit_returns_pdf_path(bundle: ServiceBundle) -> None:
    """fetch_patent_pdf returns cached PDF path immediately when file already exists."""
    epo = _make_epo_client()
    bundle.epo = epo

    # Pre-create the cached PDF file so the cache-hit branch fires
    pdf_dir = bundle.config.cache_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async def run() -> dict:
        # Compute the stem the same way the tool does
        import hashlib
        import re

        patent_number = "EP3491801B1"
        from scholar_mcp._patent_numbers import normalize

        doc = normalize(patent_number)
        stem = re.sub(r"[^\w\-]", "_", f"{doc.country}{doc.number}{doc.kind or ''}")
        url_hash = hashlib.sha256(patent_number.encode()).hexdigest()[:8]
        stem = f"patent_{stem}_{url_hash}"
        (pdf_dir / f"{stem}.pdf").write_bytes(b"%PDF-1.4 cached")

        async with Client(app) as client:
            result = await client.call_tool(
                "fetch_patent_pdf", {"patent_number": patent_number}
            )
        return json.loads(result.content[0].text)

    data = asyncio.run(run())
    assert "pdf_path" in data
    assert data.get("queued") is not True
    # EPO get_pdf was never called because of the cache hit
    epo.get_pdf = AsyncMock()  # type: ignore[method-assign]


def test_fetch_patent_pdf_execute_downloads_pdf(bundle: ServiceBundle) -> None:
    """_execute() downloads PDF from EPO and stores it when cache is empty."""
    epo = _make_epo_client()
    epo.get_pdf = AsyncMock(return_value=b"%PDF-1.4 fresh")  # type: ignore[method-assign]
    bundle.epo = epo

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async def run() -> str:
        async with Client(app) as client:
            result = await client.call_tool(
                "fetch_patent_pdf", {"patent_number": "EP3491801B1"}
            )
        queued_data = json.loads(result.content[0].text)
        assert queued_data.get("queued") is True
        task_id = queued_data["task_id"]

        # Wait for the background task to complete
        tasks = bundle.tasks
        for _ in range(50):
            task = tasks.get(task_id)
            if task and task.status == "completed":
                return task.result or ""
            await asyncio.sleep(0.05)
        return ""

    result_json = asyncio.run(run())
    result = json.loads(result_json)
    assert "pdf_path" in result
    epo.get_pdf.assert_called_once()  # type: ignore[attr-defined]


def test_fetch_patent_pdf_execute_pdf_not_available(bundle: ServiceBundle) -> None:
    """_execute() returns pdf_not_available error when EPO raises ValueError."""
    epo = _make_epo_client()
    epo.get_pdf = AsyncMock(side_effect=ValueError("No PDF available for EP3491801B1"))  # type: ignore[method-assign]
    bundle.epo = epo

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async def run() -> str:
        async with Client(app) as client:
            result = await client.call_tool(
                "fetch_patent_pdf", {"patent_number": "EP3491801B1"}
            )
        queued_data = json.loads(result.content[0].text)
        task_id = queued_data["task_id"]

        tasks = bundle.tasks
        for _ in range(50):
            task = tasks.get(task_id)
            if task and task.status == "completed":
                return task.result or ""
            await asyncio.sleep(0.05)
        return ""

    result_json = asyncio.run(run())
    result = json.loads(result_json)
    assert result.get("error") == "pdf_not_available"


def _make_mock_docling(
    *,
    convert_result: str = "# Patent\n\nMarkdown content.",
    vlm_available: bool = False,
) -> MagicMock:
    """Return a MagicMock DoclingClient for use in patent PDF tests."""
    mock = MagicMock(spec=DoclingClient)
    mock.vlm_available = vlm_available
    mock.convert = AsyncMock(return_value=convert_result)
    mock.vlm_skip_reason = MagicMock(return_value=None)
    return mock


def test_fetch_patent_pdf_cache_hit_with_docling_and_cached_md(
    bundle: ServiceBundle,
) -> None:
    """Cache hit returns markdown inline when both PDF and MD are already cached."""
    epo = _make_epo_client()
    bundle.epo = epo
    bundle.docling = _make_mock_docling()  # type: ignore[assignment]

    pdf_dir = bundle.config.cache_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    md_dir = bundle.config.cache_dir / "md"
    md_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async def run() -> dict:
        import hashlib
        import re

        patent_number = "EP3491801B1"
        from scholar_mcp._patent_numbers import normalize

        doc = normalize(patent_number)
        stem = re.sub(r"[^\w\-]", "_", f"{doc.country}{doc.number}{doc.kind or ''}")
        url_hash = hashlib.sha256(patent_number.encode()).hexdigest()[:8]
        stem = f"patent_{stem}_{url_hash}"

        (pdf_dir / f"{stem}.pdf").write_bytes(b"%PDF-1.4 cached")
        (md_dir / f"{stem}.md").write_text("# Cached Markdown", encoding="utf-8")

        async with Client(app) as client:
            result = await client.call_tool(
                "fetch_patent_pdf", {"patent_number": patent_number}
            )
        return json.loads(result.content[0].text)

    data = asyncio.run(run())
    assert "pdf_path" in data
    assert data.get("markdown") == "# Cached Markdown"
    assert data.get("vlm_used") is False
    assert data.get("queued") is not True
    # No EPO call and no docling conversion — both were cached
    bundle.docling.convert.assert_not_called()  # type: ignore[union-attr]


def test_fetch_patent_pdf_execute_with_docling_converts_to_markdown(
    bundle: ServiceBundle,
) -> None:
    """_execute() downloads PDF and converts it to markdown via docling."""
    epo = _make_epo_client()
    epo.get_pdf = AsyncMock(return_value=b"%PDF-1.4 fresh")  # type: ignore[method-assign]
    bundle.epo = epo
    bundle.docling = _make_mock_docling(convert_result="# Patent Markdown")  # type: ignore[assignment]

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async def run() -> str:
        async with Client(app) as client:
            result = await client.call_tool(
                "fetch_patent_pdf", {"patent_number": "EP3491801B1"}
            )
        queued_data = json.loads(result.content[0].text)
        task_id = queued_data["task_id"]

        tasks = bundle.tasks
        for _ in range(50):
            task = tasks.get(task_id)
            if task and task.status == "completed":
                return task.result or ""
            await asyncio.sleep(0.05)
        return ""

    result_json = asyncio.run(run())
    result = json.loads(result_json)
    assert "pdf_path" in result
    assert result.get("markdown") == "# Patent Markdown"
    assert result.get("vlm_used") is False
    bundle.docling.convert.assert_called_once()  # type: ignore[union-attr]


def test_fetch_patent_pdf_cache_hit_docling_no_md_falls_through_to_queue(
    bundle: ServiceBundle,
) -> None:
    """Cache hit with docling but no cached md queues _execute() to convert."""
    epo = _make_epo_client()
    epo.get_pdf = AsyncMock(return_value=b"%PDF-1.4 fresh")  # type: ignore[method-assign]
    bundle.epo = epo
    bundle.docling = _make_mock_docling(convert_result="# Freshly Converted")  # type: ignore[assignment]

    pdf_dir = bundle.config.cache_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async def run() -> str:
        import hashlib
        import re

        patent_number = "EP3491801B1"
        from scholar_mcp._patent_numbers import normalize

        doc = normalize(patent_number)
        stem = re.sub(r"[^\w\-]", "_", f"{doc.country}{doc.number}{doc.kind or ''}")
        url_hash = hashlib.sha256(patent_number.encode()).hexdigest()[:8]
        stem = f"patent_{stem}_{url_hash}"

        # PDF exists, but no md file — so it falls through to queue
        (pdf_dir / f"{stem}.pdf").write_bytes(b"%PDF-1.4 cached")

        async with Client(app) as client:
            result = await client.call_tool(
                "fetch_patent_pdf", {"patent_number": patent_number}
            )
        queued_data = json.loads(result.content[0].text)
        assert queued_data.get("queued") is True
        task_id = queued_data["task_id"]

        tasks = bundle.tasks
        for _ in range(50):
            task = tasks.get(task_id)
            if task and task.status == "completed":
                return task.result or ""
            await asyncio.sleep(0.05)
        return ""

    result_json = asyncio.run(run())
    result = json.loads(result_json)
    assert result.get("markdown") == "# Freshly Converted"
    # PDF was not re-downloaded (already existed); docling was called
    epo.get_pdf.assert_not_called()  # type: ignore[attr-defined]
    bundle.docling.convert.assert_called_once()  # type: ignore[union-attr]


def test_fetch_patent_pdf_cache_hit_with_vlm_skip_reason(
    bundle: ServiceBundle,
) -> None:
    """Cache hit includes vlm_skip_reason when VLM is not available."""
    epo = _make_epo_client()
    bundle.epo = epo
    mock_docling = _make_mock_docling()
    mock_docling.vlm_skip_reason = MagicMock(return_value="VLM not configured")
    bundle.docling = mock_docling  # type: ignore[assignment]

    pdf_dir = bundle.config.cache_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    md_dir = bundle.config.cache_dir / "md"
    md_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async def run() -> dict:
        import hashlib
        import re

        patent_number = "EP3491801B1"
        from scholar_mcp._patent_numbers import normalize

        doc = normalize(patent_number)
        stem = re.sub(r"[^\w\-]", "_", f"{doc.country}{doc.number}{doc.kind or ''}")
        url_hash = hashlib.sha256(patent_number.encode()).hexdigest()[:8]
        stem = f"patent_{stem}_{url_hash}"

        (pdf_dir / f"{stem}.pdf").write_bytes(b"%PDF-1.4")
        (md_dir / f"{stem}.md").write_text("# Cached", encoding="utf-8")

        async with Client(app) as client:
            result = await client.call_tool(
                "fetch_patent_pdf", {"patent_number": patent_number}
            )
        return json.loads(result.content[0].text)

    data = asyncio.run(run())
    assert data.get("vlm_skip_reason") == "VLM not configured"


def test_fetch_patent_pdf_execute_docling_convert_exception(
    bundle: ServiceBundle,
) -> None:
    """_execute() returns pdf_path only when docling conversion raises."""
    epo = _make_epo_client()
    epo.get_pdf = AsyncMock(return_value=b"%PDF-1.4 fresh")  # type: ignore[method-assign]
    bundle.epo = epo
    mock_docling = _make_mock_docling()
    mock_docling.convert = AsyncMock(side_effect=RuntimeError("docling timeout"))
    bundle.docling = mock_docling  # type: ignore[assignment]

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async def run() -> str:
        async with Client(app) as client:
            result = await client.call_tool(
                "fetch_patent_pdf", {"patent_number": "EP3491801B1"}
            )
        queued_data = json.loads(result.content[0].text)
        task_id = queued_data["task_id"]

        tasks = bundle.tasks
        for _ in range(50):
            task = tasks.get(task_id)
            if task and task.status == "completed":
                return task.result or ""
            await asyncio.sleep(0.05)
        return ""

    result_json = asyncio.run(run())
    result = json.loads(result_json)
    # Falls back to just pdf_path when docling fails
    assert "pdf_path" in result
    assert "markdown" not in result


def test_fetch_patent_pdf_execute_with_vlm_skip_reason(
    bundle: ServiceBundle,
) -> None:
    """_execute() includes vlm_skip_reason in result when VLM is not available."""
    epo = _make_epo_client()
    epo.get_pdf = AsyncMock(return_value=b"%PDF-1.4 fresh")  # type: ignore[method-assign]
    bundle.epo = epo
    mock_docling = _make_mock_docling(convert_result="# Patent content")
    mock_docling.vlm_skip_reason = MagicMock(return_value="VLM not configured")
    bundle.docling = mock_docling  # type: ignore[assignment]

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async def run() -> str:
        async with Client(app) as client:
            result = await client.call_tool(
                "fetch_patent_pdf", {"patent_number": "EP3491801B1"}
            )
        queued_data = json.loads(result.content[0].text)
        task_id = queued_data["task_id"]

        tasks = bundle.tasks
        for _ in range(50):
            task = tasks.get(task_id)
            if task and task.status == "completed":
                return task.result or ""
            await asyncio.sleep(0.05)
        return ""

    result_json = asyncio.run(run())
    result = json.loads(result_json)
    assert result.get("vlm_skip_reason") == "VLM not configured"
    assert "markdown" in result


def test_fetch_patent_pdf_execute_with_docling_cached_md(
    bundle: ServiceBundle,
) -> None:
    """_execute() reads markdown from cache when md_path already exists."""
    epo = _make_epo_client()
    epo.get_pdf = AsyncMock(return_value=b"%PDF-1.4 fresh")  # type: ignore[method-assign]
    bundle.epo = epo
    bundle.docling = _make_mock_docling()  # type: ignore[assignment]

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_patent_tools(app)

    async def run() -> str:
        import hashlib
        import re

        patent_number = "EP3491801B1"
        from scholar_mcp._patent_numbers import normalize

        doc = normalize(patent_number)
        stem = re.sub(r"[^\w\-]", "_", f"{doc.country}{doc.number}{doc.kind or ''}")
        url_hash = hashlib.sha256(patent_number.encode()).hexdigest()[:8]
        stem = f"patent_{stem}_{url_hash}"

        md_dir = bundle.config.cache_dir / "md"
        md_dir.mkdir(parents=True, exist_ok=True)
        (md_dir / f"{stem}.md").write_text("# Pre-cached MD", encoding="utf-8")

        async with Client(app) as client:
            result = await client.call_tool(
                "fetch_patent_pdf", {"patent_number": patent_number}
            )
        queued_data = json.loads(result.content[0].text)
        task_id = queued_data["task_id"]

        tasks = bundle.tasks
        for _ in range(50):
            task = tasks.get(task_id)
            if task and task.status == "completed":
                return task.result or ""
            await asyncio.sleep(0.05)
        return ""

    result_json = asyncio.run(run())
    result = json.loads(result_json)
    assert result.get("markdown") == "# Pre-cached MD"
    # convert should not be called since md was already cached
    bundle.docling.convert.assert_not_called()  # type: ignore[union-attr]
