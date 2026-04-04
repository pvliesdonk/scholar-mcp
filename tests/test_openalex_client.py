"""Tests for OpenAlexClient."""

from __future__ import annotations

import httpx
import pytest
import respx

from scholar_mcp._openalex_client import OpenAlexClient

OA_BASE = "https://api.openalex.org"


@pytest.fixture
def client() -> OpenAlexClient:
    return OpenAlexClient(http_client=httpx.AsyncClient(base_url=OA_BASE))


@pytest.mark.respx(base_url=OA_BASE)
async def test_get_by_doi(respx_mock: respx.MockRouter, client: OpenAlexClient) -> None:
    doi = "10.1234/test"
    respx_mock.get(f"/works/https://doi.org/{doi}").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "https://openalex.org/W1",
                "doi": f"https://doi.org/{doi}",
                "authorships": [
                    {
                        "author": {"display_name": "Ada"},
                        "institutions": [{"display_name": "MIT"}],
                    }
                ],
                "grants": [],
                "open_access": {"is_oa": True, "oa_status": "gold"},
                "concepts": [{"display_name": "Machine Learning", "score": 0.9}],
            },
        )
    )
    result = await client.get_by_doi(doi)
    assert result is not None
    assert result["open_access"]["is_oa"] is True


@pytest.mark.respx(base_url=OA_BASE)
async def test_get_by_doi_not_found(
    respx_mock: respx.MockRouter, client: OpenAlexClient
) -> None:
    respx_mock.get("/works/https://doi.org/10.0/missing").mock(
        return_value=httpx.Response(404)
    )
    result = await client.get_by_doi("10.0/missing")
    assert result is None
