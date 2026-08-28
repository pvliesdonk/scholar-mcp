"""Tests for batch_resolve and enrich_paper tools."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp_pvl_core import Jobs, register_job_tools

from scholar_mcp._epo_client import EpoClient
from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._tools_utility import register_utility_tools

S2_BASE = "https://api.semanticscholar.org/graph/v1"
OA_BASE = "https://api.openalex.org"

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


def _make_epo_client(
    *,
    biblio_result: dict | None = None,
    raise_on_biblio: Exception | None = None,
) -> EpoClient:
    """Return a mock EpoClient with configurable responses."""
    mock_ops = MagicMock()
    client = EpoClient(consumer_key="k", consumer_secret="s", _client=mock_ops)
    if raise_on_biblio is not None:
        client.get_biblio = AsyncMock(side_effect=raise_on_biblio)
    else:
        client.get_biblio = AsyncMock(return_value=biblio_result or _BIBLIO_RESULT)
    return client


@pytest.fixture
def mcp(bundle: ServiceBundle, slow_jobs: Jobs) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_utility_tools(app, slow_jobs)
    return app


@pytest.fixture
def mcp_with_epo(bundle: ServiceBundle, slow_jobs: Jobs) -> FastMCP:
    """FastMCP instance with utility tools and a mock EpoClient wired in."""
    bundle.epo = _make_epo_client()

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_utility_tools(app, slow_jobs)
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
    data = json.loads(result.content[0].text)["results"]
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
    data = json.loads(result.content[0].text)["results"]
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
    data = json.loads(result.content[0].text)["results"]
    assert data[0]["error"] == "not_found"
    assert data[0]["identifier"] == "some_id"


async def test_batch_resolve_retries_on_429(
    bundle: ServiceBundle,
    slow_jobs: Jobs,
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
        register_utility_tools(app, slow_jobs)

        async with Client(app) as client:
            result = await client.call_tool("batch_resolve", {"identifiers": ["p1"]})

    data = json.loads(result.content[0].text)
    # Assert the retry actually happened and produced the record. Checking
    # only that "queued" is absent would pass just as well if the retry were
    # deleted and the 429 surfaced as an error payload.
    assert call_count == 2, "expected the 429 to be retried in-client"
    assert data["results"][0]["paper"]["paperId"] == "p1"


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


async def test_enrich_paper_retries_on_429(
    bundle: ServiceBundle,
    slow_jobs: Jobs,
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
        register_utility_tools(app, slow_jobs)

        async with Client(app) as client:
            result = await client.call_tool(
                "enrich_paper",
                {"identifier": "p1", "fields": ["oa_status"]},
            )

    data = json.loads(result.content[0].text)
    # Assert the enrichment landed. `"queued" not in data` alone would be
    # vacuous here: an exhausted 429 returns an error payload, which has no
    # "queued" key either.
    assert call_count == 2, "expected the 429 to be retried in-client"
    assert data["oa_status"] == "gold"


# ---------------------------------------------------------------------------
# batch_resolve patent support tests
# ---------------------------------------------------------------------------


async def test_batch_resolve_detects_patent(
    mcp_with_epo: FastMCP,
) -> None:
    """batch_resolve auto-detects patent numbers and routes to EPO."""
    async with Client(mcp_with_epo) as client:
        result = await client.call_tool(
            "batch_resolve",
            {"identifiers": ["EP1234567A1"]},
        )
    data = json.loads(result.content[0].text)["results"]
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["source_type"] == "patent"
    assert "patent" in data[0]
    assert data[0]["patent"]["title"] == "Test Patent"


async def test_batch_resolve_mixed_papers_and_patents(
    mcp_with_epo: FastMCP,
) -> None:
    """batch_resolve handles mixed paper and patent identifiers."""
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(
                200,
                json=[{"paperId": "p1", "title": "Paper 1"}],
            )
        )
        async with Client(mcp_with_epo) as client:
            result = await client.call_tool(
                "batch_resolve",
                {"identifiers": ["DOI:10.1234/test", "EP1234567A1"]},
            )
    data = json.loads(result.content[0].text)["results"]
    assert len(data) == 2
    # First is a paper (DOI)
    assert "paper" in data[0]
    assert data[0]["identifier"] == "DOI:10.1234/test"
    # Second is a patent
    assert data[1]["source_type"] == "patent"
    assert "patent" in data[1]
    assert data[1]["identifier"] == "EP1234567A1"


async def test_batch_resolve_patent_epo_not_configured(
    mcp: FastMCP,
) -> None:
    """batch_resolve returns epo_not_configured when EPO client is None."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "batch_resolve",
            {"identifiers": ["EP1234567A1"]},
        )
    data = json.loads(result.content[0].text)["results"]
    assert len(data) == 1
    assert data[0]["error"] == "epo_not_configured"
    assert data[0]["source_type"] == "patent"


async def test_batch_resolve_patent_resolve_failed(
    bundle: ServiceBundle,
    slow_jobs: Jobs,
) -> None:
    """batch_resolve returns resolve_failed when EPO raises an exception."""
    bundle.epo = _make_epo_client(raise_on_biblio=RuntimeError("EPO down"))

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_utility_tools(app, slow_jobs)

    async with Client(app) as client:
        result = await client.call_tool(
            "batch_resolve",
            {"identifiers": ["EP1234567A1"]},
        )
    data = json.loads(result.content[0].text)["results"]
    assert len(data) == 1
    assert data[0]["error"] == "resolve_failed"
    assert data[0]["source_type"] == "patent"


async def test_batch_resolve_patent_not_found_empty_biblio(
    bundle: ServiceBundle,
    slow_jobs: Jobs,
) -> None:
    """batch_resolve returns not_found when biblio has no title or applicants."""
    bundle.epo = _make_epo_client(biblio_result={"title": "", "applicants": []})

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_utility_tools(app, slow_jobs)

    async with Client(app) as client:
        result = await client.call_tool(
            "batch_resolve",
            {"identifiers": ["EP1234567A1"]},
        )
    data = json.loads(result.content[0].text)["results"]
    assert len(data) == 1
    assert data[0]["error"] == "not_found"
    assert data[0]["source_type"] == "patent"


async def test_batch_resolve_preserves_order_with_patents(
    mcp_with_epo: FastMCP,
) -> None:
    """batch_resolve preserves original order when mixing papers and patents."""
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
        async with Client(mcp_with_epo) as client:
            result = await client.call_tool(
                "batch_resolve",
                {
                    "identifiers": [
                        "p1",
                        "EP1234567A1",
                        "p2",
                    ]
                },
            )
    data = json.loads(result.content[0].text)["results"]
    assert len(data) == 3
    assert data[0]["identifier"] == "p1"
    assert "paper" in data[0]
    assert data[1]["identifier"] == "EP1234567A1"
    assert data[1]["source_type"] == "patent"
    assert data[2]["identifier"] == "p2"
    assert "paper" in data[2]


async def test_batch_resolve_patent_throttled_degrades_that_entry(
    bundle: ServiceBundle,
    slow_jobs: Jobs,
) -> None:
    """batch_resolve queues when EPO rate-limits during patent resolution."""
    from scholar_mcp._epo_client import EpoRateLimitedError

    bundle.epo = _make_epo_client(raise_on_biblio=EpoRateLimitedError("red"))

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_utility_tools(app, slow_jobs)
    from scholar_mcp._tools_tasks import register_task_tools

    register_task_tools(app)

    async with Client(app) as client:
        result = await client.call_tool(
            "batch_resolve",
            {"identifiers": ["EP1234567A1"]},
        )
    data = json.loads(result.content[0].text)["results"]
    assert data[0]["source_type"] == "patent"
    # A throttle that outlasts the backoff degrades this entry rather than
    # failing the batch, and names the state instead of the generic
    # "resolve_failed" every EPO failure used to collapse into.
    assert data[0]["error"] == "rate_limited"
    assert data[0]["retryable"] is True


OL_BASE = "https://openlibrary.org"

_OL_EDITION = {
    "title": "Design Patterns",
    "publishers": ["Addison-Wesley"],
    "publish_date": "1994",
    "isbn_10": ["0201633612"],
    "isbn_13": ["9780201633610"],
    "number_of_pages": 395,
    "works": [{"key": "/works/OL1168083W"}],
    "key": "/books/OL1429049M",
    "subjects": ["Software patterns"],
}


async def test_batch_resolve_isbn(mcp: FastMCP) -> None:
    """ISBN: prefixed identifiers are routed to Open Library, not S2."""
    with respx.mock:
        respx.get(f"{OL_BASE}/isbn/9780201633610.json").mock(
            return_value=httpx.Response(200, json=_OL_EDITION)
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "batch_resolve",
                {"identifiers": ["ISBN:9780201633610"]},
            )
    data = json.loads(result.content[0].text)["results"]
    assert len(data) == 1
    assert data[0]["source_type"] == "book"
    assert data[0]["book"]["title"] == "Design Patterns"
    assert data[0]["book"]["isbn_13"] == "9780201633610"


async def test_batch_resolve_isbn_not_found(mcp: FastMCP) -> None:
    """ISBN: identifier returns not_found when Open Library has no match."""
    with respx.mock:
        respx.get(f"{OL_BASE}/isbn/9780000000000.json").mock(
            return_value=httpx.Response(404)
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "batch_resolve",
                {"identifiers": ["ISBN:9780000000000"]},
            )
    data = json.loads(result.content[0].text)["results"]
    assert len(data) == 1
    assert data[0]["error"] == "not_found"
    assert data[0]["source_type"] == "book"


async def test_batch_resolve_mixed_papers_and_isbn(mcp: FastMCP) -> None:
    """batch_resolve handles a mix of paper IDs and ISBNs in correct order."""
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(
                200, json=[{"paperId": "abc", "title": "Paper A"}]
            )
        )
        respx.get(f"{OL_BASE}/isbn/9780201633610.json").mock(
            return_value=httpx.Response(200, json=_OL_EDITION)
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "batch_resolve",
                {"identifiers": ["abc", "ISBN:9780201633610"]},
            )
    data = json.loads(result.content[0].text)["results"]
    assert len(data) == 2
    assert data[0]["identifier"] == "abc"
    assert "paper" in data[0]
    assert data[1]["identifier"] == "ISBN:9780201633610"
    assert data[1]["source_type"] == "book"


# ---------------------------------------------------------------------------
# batch_resolve chapter integration tests
# ---------------------------------------------------------------------------


async def test_batch_resolve_chapter_hint_parsed(mcp: FastMCP) -> None:
    """batch_resolve attaches parsed chapter_info when chapter hints exist."""
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(
                200,
                json=[{"paperId": "p1", "title": "Deep Learning"}],
            )
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "batch_resolve",
                {"identifiers": ["DOI:10.1/ch3 Ch. 3, pp. 45-67"]},
            )
    data = json.loads(result.content[0].text)["results"]
    assert len(data) == 1
    assert "paper" in data[0]
    assert "chapter_info" in data[0]
    ci = data[0]["chapter_info"]
    assert ci["citation_source"] == "parsed"
    assert ci["chapter_number"] == 3
    assert ci["page_start"] == 45
    assert ci["page_end"] == 67


async def test_batch_resolve_chapter_parent_title_and_isbn(mcp: FastMCP) -> None:
    """parent_title and isbn from citation text flow into chapter_info."""
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(
                200,
                json=[{"paperId": "p1", "title": "Chapter Title"}],
            )
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "batch_resolve",
                {
                    "identifiers": [
                        "DOI:10.1/ch5 Ch. 5, pp. 100-120, "
                        "In: Deep Learning, ISBN: 978-0-262-03561-3"
                    ]
                },
            )
    data = json.loads(result.content[0].text)["results"]
    assert len(data) == 1
    ci = data[0]["chapter_info"]
    assert ci["citation_source"] == "parsed"
    assert ci["chapter_number"] == 5
    assert ci["page_start"] == 100
    assert ci["page_end"] == 120
    assert ci["parent_title"] == "Deep Learning"
    assert ci["isbn"] == "9780262035613"


async def test_batch_resolve_no_chapter_info(mcp: FastMCP) -> None:
    """batch_resolve does not attach chapter_info for plain identifiers."""
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(
                200,
                json=[{"paperId": "p1", "title": "Regular Paper"}],
            )
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "batch_resolve",
                {"identifiers": ["p1"]},
            )
    data = json.loads(result.content[0].text)["results"]
    assert len(data) == 1
    assert "paper" in data[0]
    assert "chapter_info" not in data[0]


@pytest.mark.respx(base_url=S2_BASE)
async def test_batch_resolve_promotes_when_slow(
    respx_mock: respx.MockRouter, bundle: ServiceBundle, jobs: Jobs
) -> None:
    """A slow batch is promoted and the ordered results arrive by polling."""

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.2)
        return httpx.Response(200, json=[{"paperId": "b1", "title": "Batched"}])

    respx_mock.post("/paper/batch").mock(side_effect=slow)

    @asynccontextmanager
    async def lifespan(app: FastMCP):  # type: ignore[type-arg]
        yield {"bundle": bundle}

    app = FastMCP("test", lifespan=lifespan)
    register_utility_tools(app, jobs)
    register_job_tools(app, jobs)

    async with Client(app) as client:
        result = await client.call_tool("batch_resolve", {"identifiers": ["b1"]})
        handle = json.loads(result.content[0].text)
        assert handle["status"] == "working"
        assert handle["poll_with"] == "get_job_result"

        for _ in range(40):
            polled = await client.call_tool(
                "get_job_result", {"job_id": handle["job_id"]}
            )
            settled = json.loads(polled.content[0].text)
            if settled["status"] != "working":
                break
            await asyncio.sleep(0.05)

    assert settled["status"] == "completed"
    assert settled["result"]["results"][0]["paper"]["paperId"] == "b1"


async def test_batch_resolve_reports_quota_exhaustion_per_entry(
    bundle: ServiceBundle, slow_jobs: Jobs
) -> None:
    """An exhausted EPO quota names itself in that entry, and only that entry.

    Two behaviours meet here. The condition must not be swallowed into the
    generic `"resolve_failed"` — the swallow fixed for the single-patent
    tools in #313, which this module still had. And it must not propagate
    either: this tool resolves identifiers independently, so failing the
    whole batch over one patent would lose the papers alongside it.
    """
    from scholar_mcp._epo_client import EpoQuotaExhaustedError

    epo = MagicMock(spec=EpoClient)
    epo.get_biblio = AsyncMock(side_effect=EpoQuotaExhaustedError)
    bundle.epo = epo

    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[{"paperId": "ok1"}])
        )

        @asynccontextmanager
        async def lifespan(app: FastMCP):  # type: ignore[type-arg]
            yield {"bundle": bundle}

        app = FastMCP("test", lifespan=lifespan)
        register_utility_tools(app, slow_jobs)

        async with Client(app) as client:
            result = await client.call_tool(
                "batch_resolve", {"identifiers": ["ok1", "EP1234567A1"]}
            )

    entries = json.loads(result.content[0].text)["results"]
    assert entries[0]["paper"]["paperId"] == "ok1", "the paper must survive"
    assert entries[1]["error"] == "epo_unavailable"
    assert entries[1]["retryable"] is False


async def test_enrich_paper_reports_a_sustained_rate_limit_as_retryable(
    bundle: ServiceBundle, slow_jobs: Jobs
) -> None:
    """An exhausted 429 says so, rather than claiming the paper is missing.

    Before the migration a 429 raised `RateLimitedError` and queued, so this
    handler never saw one. It does now, and answering "not_found" would tell
    the caller to give up on a paper that exists.
    """
    with respx.mock:
        respx.get(f"{S2_BASE}/paper/p1").mock(return_value=httpx.Response(429))

        @asynccontextmanager
        async def lifespan(app: FastMCP):  # type: ignore[type-arg]
            yield {"bundle": bundle}

        app = FastMCP("test", lifespan=lifespan)
        register_utility_tools(app, slow_jobs)

        async with Client(app) as client:
            result = await client.call_tool(
                "enrich_paper", {"identifier": "p1", "fields": ["oa_status"]}
            )

    data = json.loads(result.content[0].text)
    assert data["error"] == "rate_limited"
    assert data["retryable"] is True
