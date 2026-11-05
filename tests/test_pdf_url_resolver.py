"""Tests for _pdf_url_resolver — alternative PDF URL resolution."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from scholar_mcp._pdf_url_resolver import (
    _UNPAYWALL_BASE,
    ResolvedPdf,
    _try_arxiv,
    _try_pmc,
    _try_unpaywall,
    iter_alternative_pdfs,
)

# ---------------------------------------------------------------------------
# Unit tests for individual resolvers
# ---------------------------------------------------------------------------


def test_try_arxiv_with_id() -> None:
    paper = {"externalIds": {"ArXiv": "2301.12345"}}
    result = _try_arxiv(paper)
    assert result is not None
    assert result.source == "arxiv"
    assert result.url == "https://arxiv.org/pdf/2301.12345.pdf"


def test_try_arxiv_missing() -> None:
    assert _try_arxiv({"externalIds": {"DOI": "10.1234/foo"}}) is None
    assert _try_arxiv({"externalIds": None}) is None
    assert _try_arxiv({}) is None


def test_try_pmc_with_id() -> None:
    paper = {"externalIds": {"PubMedCentral": "9876543"}}
    result = _try_pmc(paper)
    assert result is not None
    assert result.source == "pmc"
    assert "PMC9876543" in result.url
    assert not result.url.endswith("/")  # no trailing slash — direct PDF endpoint


def test_try_pmc_missing() -> None:
    assert _try_pmc({"externalIds": {}}) is None


@pytest.mark.respx(base_url=_UNPAYWALL_BASE)
async def test_try_unpaywall_success(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/10.1234/test").mock(
        return_value=httpx.Response(
            200,
            json={"best_oa_location": {"url_for_pdf": "https://example.com/paper.pdf"}},
        )
    )
    paper = {"externalIds": {"DOI": "10.1234/test"}}
    result = await _try_unpaywall(paper, "test@example.com")
    assert result is not None
    assert result.source == "unpaywall"
    assert result.url == "https://example.com/paper.pdf"


@pytest.mark.respx(base_url=_UNPAYWALL_BASE)
async def test_try_unpaywall_no_doi(respx_mock: respx.MockRouter) -> None:  # noqa: ARG001
    result = await _try_unpaywall({"externalIds": {}}, "test@example.com")
    assert result is None


@pytest.mark.respx(base_url=_UNPAYWALL_BASE)
async def test_try_unpaywall_404(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/10.1234/missing").mock(return_value=httpx.Response(404))
    paper = {"externalIds": {"DOI": "10.1234/missing"}}
    result = await _try_unpaywall(paper, "test@example.com")
    assert result is None


@pytest.mark.respx(base_url=_UNPAYWALL_BASE)
async def test_try_unpaywall_no_pdf_url(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/10.1234/nopdf").mock(
        return_value=httpx.Response(
            200, json={"best_oa_location": {"url_for_pdf": None}}
        )
    )
    paper = {"externalIds": {"DOI": "10.1234/nopdf"}}
    result = await _try_unpaywall(paper, "test@example.com")
    assert result is None


# ---------------------------------------------------------------------------
# Integration tests for iter_alternative_pdfs
# ---------------------------------------------------------------------------


async def _collect(paper: dict[str, Any], email: str | None) -> list[ResolvedPdf]:
    return [c async for c in iter_alternative_pdfs(paper, contact_email=email)]


@pytest.mark.respx(base_url=_UNPAYWALL_BASE)
async def test_iter_yields_every_source_in_order(respx_mock: respx.MockRouter) -> None:
    """ArXiv, then PMC, then Unpaywall: every candidate, not only the first."""
    respx_mock.get("/10.1234/x").mock(
        return_value=httpx.Response(
            200, json={"best_oa_location": {"url_for_pdf": "https://u.example/x.pdf"}}
        )
    )
    paper = {
        "externalIds": {
            "ArXiv": "2301.00001",
            "PubMedCentral": "42",
            "DOI": "10.1234/x",
        }
    }
    result = await _collect(paper, "test@example.com")
    assert [c.source for c in result] == ["arxiv", "pmc", "unpaywall"]


@pytest.mark.respx(base_url=_UNPAYWALL_BASE, assert_all_called=False)
async def test_iter_queries_unpaywall_only_when_asked(
    respx_mock: respx.MockRouter,
) -> None:
    """A caller that stops at ArXiv makes no Unpaywall request."""
    route = respx_mock.get("/10.1234/x").mock(return_value=httpx.Response(404))
    paper = {"externalIds": {"ArXiv": "2301.00001", "DOI": "10.1234/x"}}
    first = await anext(iter_alternative_pdfs(paper, contact_email="test@example.com"))
    assert first.source == "arxiv"
    assert not route.called


async def test_iter_yields_nothing_when_nothing_available() -> None:
    assert await _collect({"externalIds": {}}, None) == []


async def test_iter_skips_unpaywall_without_email() -> None:
    # No network mock — Unpaywall should be skipped entirely
    assert await _collect({"externalIds": {"DOI": "10.1234/x"}}, None) == []


@pytest.mark.respx(base_url=_UNPAYWALL_BASE)
async def test_try_unpaywall_with_shared_client(
    respx_mock: respx.MockRouter,
) -> None:
    """_try_unpaywall accepts an optional shared httpx client."""
    respx_mock.get("/10.1234/shared").mock(
        return_value=httpx.Response(
            200,
            json={
                "best_oa_location": {"url_for_pdf": "https://example.com/shared.pdf"}
            },
        )
    )
    paper = {"externalIds": {"DOI": "10.1234/shared"}}
    async with httpx.AsyncClient(timeout=15.0) as shared:
        result = await _try_unpaywall(paper, "test@example.com", http_client=shared)
    assert result is not None
    assert result.url == "https://example.com/shared.pdf"
