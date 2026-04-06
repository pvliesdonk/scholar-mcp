"""Tests for _pdf_url_resolver — alternative PDF URL resolution."""

from __future__ import annotations

import httpx
import pytest
import respx

from scholar_mcp._pdf_url_resolver import (
    _UNPAYWALL_BASE,
    ResolvedPdf,
    _try_arxiv,
    _try_pmc,
    _try_unpaywall,
    resolve_alternative_pdf,
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
async def test_try_unpaywall_no_doi(respx_mock: respx.MockRouter) -> None:
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
# Integration tests for resolve_alternative_pdf
# ---------------------------------------------------------------------------


async def test_resolve_prefers_arxiv_over_unpaywall() -> None:
    """ArXiv is checked first, no network call to Unpaywall."""
    paper = {"externalIds": {"ArXiv": "2301.00001", "DOI": "10.1234/x"}}
    result = await resolve_alternative_pdf(paper, contact_email="test@example.com")
    assert result is not None
    assert result.source == "arxiv"


async def test_resolve_returns_none_when_nothing_available() -> None:
    paper = {"externalIds": {}}
    result = await resolve_alternative_pdf(paper, contact_email=None)
    assert result is None


async def test_resolve_skips_unpaywall_without_email() -> None:
    paper = {"externalIds": {"DOI": "10.1234/x"}}
    # No network mock — Unpaywall should be skipped entirely
    result = await resolve_alternative_pdf(paper, contact_email=None)
    assert result is None
