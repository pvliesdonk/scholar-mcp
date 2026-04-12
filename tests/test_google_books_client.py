"""Tests for GoogleBooksClient."""

from __future__ import annotations

import httpx
import pytest
import respx

from scholar_mcp._google_books_client import GoogleBooksClient

GB_BASE = "https://www.googleapis.com/books/v1"


@pytest.fixture
def client() -> GoogleBooksClient:
    return GoogleBooksClient(http_client=httpx.AsyncClient(base_url=GB_BASE))


@pytest.mark.respx(base_url=GB_BASE)
async def test_search_by_isbn_returns_volume(
    respx_mock: respx.MockRouter, client: GoogleBooksClient
) -> None:
    respx_mock.get("/volumes").mock(
        return_value=httpx.Response(
            200,
            json={
                "totalItems": 1,
                "items": [
                    {
                        "id": "vol1",
                        "volumeInfo": {
                            "title": "Test Book",
                            "industryIdentifiers": [
                                {"type": "ISBN_13", "identifier": "9780123456789"}
                            ],
                        },
                    }
                ],
            },
        )
    )
    result = await client.search_by_isbn("9780123456789")
    assert result is not None
    assert result["id"] == "vol1"
    assert result["volumeInfo"]["title"] == "Test Book"


@pytest.mark.respx(base_url=GB_BASE)
async def test_search_by_isbn_returns_none_when_empty(
    respx_mock: respx.MockRouter, client: GoogleBooksClient
) -> None:
    respx_mock.get("/volumes").mock(
        return_value=httpx.Response(
            200,
            json={"totalItems": 0, "items": []},
        )
    )
    result = await client.search_by_isbn("0000000000")
    assert result is None


@pytest.mark.respx(base_url=GB_BASE)
async def test_get_volume_returns_data(
    respx_mock: respx.MockRouter, client: GoogleBooksClient
) -> None:
    respx_mock.get("/volumes/vol123").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "vol123",
                "volumeInfo": {"title": "Deep Learning"},
            },
        )
    )
    result = await client.get_volume("vol123")
    assert result is not None
    assert result["id"] == "vol123"
    assert result["volumeInfo"]["title"] == "Deep Learning"


@pytest.mark.respx(base_url=GB_BASE)
async def test_get_volume_returns_none_on_404(
    respx_mock: respx.MockRouter, client: GoogleBooksClient
) -> None:
    respx_mock.get("/volumes/missing").mock(return_value=httpx.Response(404))
    result = await client.get_volume("missing")
    assert result is None


@pytest.mark.respx(base_url=GB_BASE)
async def test_search_by_isbn_returns_none_on_error(
    respx_mock: respx.MockRouter, client: GoogleBooksClient
) -> None:
    respx_mock.get("/volumes").mock(return_value=httpx.Response(500))
    result = await client.search_by_isbn("9780123456789")
    assert result is None


@pytest.mark.respx(base_url=GB_BASE)
async def test_get_volume_returns_none_on_server_error(
    respx_mock: respx.MockRouter, client: GoogleBooksClient
) -> None:
    respx_mock.get("/volumes/bad").mock(return_value=httpx.Response(500))
    result = await client.get_volume("bad")
    assert result is None


def test_params_includes_api_key() -> None:
    keyed = GoogleBooksClient(
        http_client=httpx.AsyncClient(base_url=GB_BASE),
        api_key="test-key",
    )
    params = keyed._params({"q": "isbn:123"})
    assert params["key"] == "test-key"
    assert params["q"] == "isbn:123"
