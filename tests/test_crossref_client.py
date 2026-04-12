"""Tests for CrossRefClient."""

from __future__ import annotations

import httpx
import pytest
import respx

from scholar_mcp._crossref_client import CrossRefClient

CR_BASE = "https://api.crossref.org"


@pytest.fixture
def client() -> CrossRefClient:
    return CrossRefClient(http_client=httpx.AsyncClient(base_url=CR_BASE))


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
