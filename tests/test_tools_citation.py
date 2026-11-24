"""Tests for generate_citations MCP tool."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp_pvl_core import Jobs, JobsConfig, register_job_tools

from scholar_mcp._epo_client import EpoClient, EpoRateLimitedError
from scholar_mcp._tools_citation import register_citation_tools
from scholar_mcp.domain import Service
from tests.conftest import PlainClient, tasks_server
from tests.fixtures.chapter_papers import springer_paper
from tests.fixtures.crossref_chapters import springer_chapter, springer_parent
from tests.fixtures.patent_records import ep3491801b1

S2_BASE = "https://api.semanticscholar.org/graph/v1"
OA_BASE = "https://api.openalex.org"

SAMPLE_PAPER = {
    "paperId": "abc123",
    "title": "Attention Is All You Need",
    "year": 2017,
    "venue": "Neural Information Processing Systems",
    "authors": [
        {"authorId": "1", "name": "Ashish Vaswani"},
        {"authorId": "2", "name": "Noam Shazeer"},
    ],
    "externalIds": {"DOI": "10.5555/3295222.3295349", "ArXiv": "1706.03762"},
    "abstract": "The dominant sequence transduction models...",
    "openAccessPdf": {"url": "https://example.com/paper.pdf"},
    "citationCount": 90000,
}


@pytest.fixture
def mcp(service: Service, slow_jobs: Jobs) -> FastMCP:
    @asynccontextmanager
    async def lifespan(app: FastMCP):  # noqa: ARG001
        yield {"service": service}

    app = tasks_server("test", lifespan=lifespan)
    register_citation_tools(app, slow_jobs)
    return app


async def test_generate_bibtex_single(mcp: FastMCP) -> None:
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[SAMPLE_PAPER])
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "citation_format": "bibtex"},
            )
    text = json.loads(result.content[0].text)["output"]
    assert "@article{vaswani2017," in text
    assert "Vaswani, Ashish and Shazeer, Noam" in text


async def test_generate_csl_json(mcp: FastMCP) -> None:
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[SAMPLE_PAPER])
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "citation_format": "csl-json"},
            )
    data = json.loads(json.loads(result.content[0].text)["output"])
    assert len(data["citations"]) == 1
    assert data["citations"][0]["title"] == "Attention Is All You Need"


async def test_generate_ris(mcp: FastMCP) -> None:
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[SAMPLE_PAPER])
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "citation_format": "ris"},
            )
    text = json.loads(result.content[0].text)["output"]
    assert "TY  - JOUR" in text
    assert "AU  - Vaswani, Ashish" in text


async def test_partial_resolution(mcp: FastMCP) -> None:
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[SAMPLE_PAPER, None])
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123", "missing_id"], "citation_format": "bibtex"},
            )
    text = json.loads(result.content[0].text)["output"]
    assert "@article{vaswani2017," in text
    assert "% Could not resolve: missing_id" in text


async def test_enrich_fills_venue(mcp: FastMCP) -> None:
    paper_no_venue = {
        **SAMPLE_PAPER,
        "venue": "",
        "externalIds": {"DOI": "10.1/enrich"},
    }
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[paper_no_venue])
        )
        respx.get(f"{OA_BASE}/works/https://doi.org/10.1/enrich").mock(
            return_value=httpx.Response(
                200,
                json={
                    "primary_location": {
                        "source": {"display_name": "Nature Machine Intelligence"}
                    }
                },
            )
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "citation_format": "bibtex", "enrich": True},
            )
    text = json.loads(result.content[0].text)["output"]
    assert "Nature Machine Intelligence" in text


async def test_enrich_disabled(mcp: FastMCP) -> None:
    paper_no_venue = {**SAMPLE_PAPER, "venue": ""}
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[paper_no_venue])
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "citation_format": "bibtex", "enrich": False},
            )
    text = json.loads(result.content[0].text)["output"]
    assert "@" in text


async def test_empty_input_error(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        result = await client.call_tool(
            "generate_citations",
            {"paper_ids": [], "citation_format": "bibtex"},
        )
    data = json.loads(result.content[0].text)
    assert "error" in data


async def test_upstream_error(mcp: FastMCP) -> None:
    """generate_citations returns upstream_error when S2 fails."""
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "citation_format": "bibtex"},
            )
    data = json.loads(result.content[0].text)
    assert data["error"] == "upstream_error"
    assert data["status"] == 500


async def test_too_many_ids_error(mcp: FastMCP) -> None:
    """generate_citations rejects more than 100 paper IDs."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "generate_citations",
            {"paper_ids": [f"id{i}" for i in range(101)], "citation_format": "bibtex"},
        )
    data = json.loads(result.content[0].text)
    assert "error" in data


async def test_all_papers_unresolved(mcp: FastMCP) -> None:
    """generate_citations returns structured error when all papers fail."""
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[None, None])
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["bad1", "bad2"], "citation_format": "bibtex"},
            )
    data = json.loads(result.content[0].text)
    assert data["error"] == "no_papers_resolved"
    assert set(data["failed"]) == {"bad1", "bad2"}


async def test_retries_on_429(service: Service, slow_jobs: Jobs) -> None:
    call_count = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429)
        return httpx.Response(200, json=[SAMPLE_PAPER])

    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(side_effect=_side_effect)

        @asynccontextmanager
        async def lifespan(app: FastMCP):  # noqa: ARG001
            yield {"service": service}

        app = tasks_server("test", lifespan=lifespan)
        register_citation_tools(app, slow_jobs)

        async with Client(app) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": ["abc123"], "citation_format": "bibtex"},
            )
            data = json.loads(result.content[0].text)
    assert "@article" in data["output"] or "@inproceedings" in data["output"]


async def test_generate_citations_promotes_when_slow(
    service: Service, jobs: Jobs
) -> None:
    """Slow resolution is promoted, and the formatted text survives polling.

    This tool is the one whose payload had to be wrapped, so it is worth
    confirming the wrapper still arrives intact through a job record rather
    than only on the inline path.
    """

    async def slow(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        await asyncio.sleep(0.2)
        return httpx.Response(
            200,
            json=[{"paperId": "c9", "title": "Slow Paper", "year": 2024}],
        )

    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(side_effect=slow)

        @asynccontextmanager
        async def lifespan(app: FastMCP):  # type: ignore[type-arg]  # noqa: ARG001
            yield {"service": service}

        app = tasks_server("test", lifespan=lifespan)
        register_citation_tools(
            app, jobs, JobsConfig(soft_deadline_s=0.05, result_ttl_s=60.0)
        )
        register_job_tools(app, jobs)

        async with PlainClient(app) as client:
            result = await client.call_tool(
                "generate_citations", {"paper_ids": ["c9"], "enrich": False}
            )
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
    assert settled["result"]["format"] == "bibtex"
    assert "Slow Paper" in settled["result"]["output"]


# --- Patents (#50) ---------------------------------------------------------


def _epo_returning(*outcomes: object) -> EpoClient:
    """Return an EpoClient whose get_biblio yields *outcomes* in call order."""
    stub = "k"
    client = EpoClient(consumer_key=stub, consumer_secret=stub, _client=MagicMock())
    client.get_biblio = AsyncMock(side_effect=list(outcomes))  # type: ignore[method-assign]
    return client


async def _call(mcp: FastMCP, paper_ids: list[str], fmt: str = "bibtex") -> Any:
    async with Client(mcp) as client:
        result = await client.call_tool(
            "generate_citations",
            {"paper_ids": paper_ids, "citation_format": fmt, "enrich": False},
        )
    return json.loads(result.content[0].text)


async def test_all_patents_make_no_s2_call(mcp: FastMCP, service: Service) -> None:
    service.epo = _epo_returning(ep3491801b1())
    with respx.mock(assert_all_called=False):
        route = respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[])
        )
        data = await _call(mcp, ["EP3491801B1"])
        assert not route.called
    assert data["output"].startswith("@patent{ep3491801b1,\n")


async def test_mixed_input_keeps_order(mcp: FastMCP, service: Service) -> None:
    service.epo = _epo_returning(ep3491801b1())
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[SAMPLE_PAPER])
        )
        data = await _call(mcp, ["EP3491801B1", "abc123"], "csl-json")
    citations = json.loads(data["output"])["citations"]
    assert [c["id"] for c in citations] == ["ep3491801b1", "vaswani2017"]
    assert citations[0]["type"] == "patent"


async def test_s2_hex_id_is_not_sent_to_epo(mcp: FastMCP, service: Service) -> None:
    hex_id = "ca1b2c3d4e5f60718293a4b5c6d7e8f901234567"
    epo = _epo_returning()
    service.epo = epo
    with respx.mock:
        route = respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[SAMPLE_PAPER])
        )
        data = await _call(mcp, [hex_id])
        assert json.loads(route.calls.last.request.content)["ids"] == [hex_id]
    assert "@article{vaswani2017," in data["output"]
    epo.get_biblio.assert_not_called()  # type: ignore[attr-defined]


async def test_epo_not_configured_is_a_comment(mcp: FastMCP, service: Service) -> None:
    service.epo = None
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[SAMPLE_PAPER])
        )
        data = await _call(mcp, ["EP3491801B1", "abc123"])
    output = data["output"]
    assert "% Could not resolve: EP3491801B1 (epo_not_configured)" in output
    assert "@article{vaswani2017," in output


async def test_patent_throttle_is_a_comment(mcp: FastMCP, service: Service) -> None:
    service.epo = _epo_returning(*[EpoRateLimitedError("red")] * 10)
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[SAMPLE_PAPER])
        )
        data = await _call(mcp, ["abc123", "EP3491801B1"], "ris")
    output = data["output"]
    assert "% Could not resolve: EP3491801B1 (rate_limited)" in output
    assert "TY  - JOUR" in output


async def test_all_fail_lists_reasons(mcp: FastMCP, service: Service) -> None:
    service.epo = None
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[None])
        )
        data = await _call(mcp, ["EP3491801B1", "bad1"])
    assert data["error"] == "no_papers_resolved"
    assert data["failed"] == ["EP3491801B1", "bad1"]
    assert data["errors"] == [
        {"identifier": "EP3491801B1", "reason": "epo_not_configured"},
        {"identifier": "bad1", "reason": "not found"},
    ]


async def test_unknown_doi_does_not_lose_the_patents(
    mcp: FastMCP, service: Service
) -> None:
    """#729: S2's all-unknown 400 no longer fails the patents beside it."""
    service.epo = _epo_returning(ep3491801b1())
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(400, json={"error": "No valid paper ids given"})
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {
                    "paper_ids": ["EP3491801B1", "DOI:10.1038/nature14539"],
                    "enrich": False,
                },
            )
    text = json.loads(result.content[0].text)["output"]
    assert "% Could not resolve: DOI:10.1038/nature14539 (not found)" in text
    assert "@patent{ep3491801b1," in text


async def test_nonexistent_patent_is_reported_not_found(
    mcp: FastMCP, service: Service
) -> None:
    """#728: a wrong patent number says not_found, not resolve_failed."""
    import requests

    response = requests.Response()
    response.status_code = 404
    service.epo = _epo_returning(
        ep3491801b1(), requests.HTTPError("404", response=response)
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "generate_citations",
            {"paper_ids": ["EP3491801B1", "EP99999999A1"], "citation_format": "ris"},
        )
    text = json.loads(result.content[0].text)["output"]
    assert text.startswith("% Could not resolve: EP99999999A1 (not_found)")
    assert "TY  - PAT" in text


# ---------------------------------------------------------------------------
# Book chapters (#593): CrossRef enrichment supplies chapter_info
# ---------------------------------------------------------------------------

_CR_BASE = "https://api.crossref.org/works"
_CHAPTER_DOI = "10.1007/978-3-031-93275-5_2"


def _mock_springer_chapter() -> None:
    """Mock S2, OpenAlex and CrossRef for the Springer series chapter."""
    respx.post(f"{S2_BASE}/paper/batch").mock(
        return_value=httpx.Response(200, json=[springer_paper()])
    )
    respx.get(url__startswith=f"{OA_BASE}/works/").mock(
        return_value=httpx.Response(404)
    )
    respx.get(f"{_CR_BASE}/{_CHAPTER_DOI}").mock(
        return_value=httpx.Response(200, json={"message": springer_chapter()})
    )
    respx.get(f"{_CR_BASE}/10.1007/978-3-031-93275-5").mock(
        return_value=httpx.Response(200, json={"message": springer_parent()})
    )


@pytest.mark.parametrize(
    ("citation_format", "expected"),
    [
        ("bibtex", "@incollection{silva2025,"),
        ("bibtex", "  editor = {Rossi, Maria and de Vries, Jan}"),
        ("csl-json", '"type": "chapter"'),
        ("csl-json", '"container-title": "Cultural Heritage-Based'),
        ("ris", "TY  - CHAP"),
        ("ris", "A2  - Rossi, Maria"),
    ],
)
async def test_enriched_chapter_is_a_chapter_entry(
    mcp: FastMCP, citation_format: str, expected: str
) -> None:
    """The default enrich=True path maps the CrossRef chapter end to end."""
    with respx.mock:
        _mock_springer_chapter()
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {
                    "paper_ids": [f"DOI:{_CHAPTER_DOI}"],
                    "citation_format": citation_format,
                },
            )
    assert expected in json.loads(result.content[0].text)["output"]


async def test_chapter_without_enrichment_is_an_article(mcp: FastMCP) -> None:
    """enrich=False runs no CrossRef lookup, so no chapter_info exists."""
    with respx.mock:
        respx.post(f"{S2_BASE}/paper/batch").mock(
            return_value=httpx.Response(200, json=[springer_paper()])
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "generate_citations",
                {"paper_ids": [f"DOI:{_CHAPTER_DOI}"], "enrich": False},
            )
    output = json.loads(result.content[0].text)["output"]
    assert output.startswith("@article{silva2025,")
    assert "booktitle" not in output
