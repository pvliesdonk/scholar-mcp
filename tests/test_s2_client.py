import json
import logging

import httpx
import pytest

from scholar_mcp._s2_client import (
    FIELD_SETS,
    S2Client,
    format_s2_error,
    log_s2_error,
)

S2_BASE = "https://api.semanticscholar.org/graph/v1"


@pytest.fixture
def client():
    return S2Client(api_key=None, delay=0.0)


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_paper(respx_mock, client):
    respx_mock.get("/paper/abc123").mock(
        return_value=httpx.Response(
            200, json={"paperId": "abc123", "title": "Test Paper", "year": 2024}
        )
    )
    result = await client.get_paper("abc123")
    assert result["paperId"] == "abc123"
    assert result["title"] == "Test Paper"


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_paper_not_found(respx_mock, client):
    respx_mock.get("/paper/missing").mock(return_value=httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        await client.get_paper("missing")


@pytest.mark.respx(base_url=S2_BASE)
async def test_search_papers(respx_mock, client):
    respx_mock.get("/paper/search").mock(
        return_value=httpx.Response(
            200, json={"data": [{"paperId": "p1", "title": "Result 1"}], "total": 1}
        )
    )
    result = await client.search_papers(
        "machine learning", fields="compact", limit=10, offset=0
    )
    assert result["total"] == 1
    assert result["data"][0]["paperId"] == "p1"


@pytest.mark.respx(base_url=S2_BASE)
async def test_get_citations(respx_mock, client):
    respx_mock.get("/paper/p1/citations").mock(
        return_value=httpx.Response(
            200, json={"data": [{"citingPaper": {"paperId": "c1", "title": "Citer"}}]}
        )
    )
    result = await client.get_citations("p1", fields="compact", limit=10, offset=0)
    assert result["data"][0]["citingPaper"]["paperId"] == "c1"


@pytest.mark.respx(base_url=S2_BASE)
async def test_batch_resolve(respx_mock, client):
    respx_mock.post("/paper/batch").mock(
        return_value=httpx.Response(
            200, json=[{"paperId": "p1", "title": "Paper 1"}, None]
        )
    )
    result = await client.batch_resolve(["p1", "unknown"], fields="standard")
    assert result[0]["paperId"] == "p1"
    assert result[1] is None


def test_field_sets_exist():
    for preset in ("compact", "standard", "full"):
        assert preset in FIELD_SETS
        assert "title" in FIELD_SETS[preset]


def _make_error(status_code: int, text: str = "boom") -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.semanticscholar.org/graph/v1/paper/x")
    response = httpx.Response(status_code, text=text, request=request)
    return httpx.HTTPStatusError(
        f"{status_code} error", request=request, response=response
    )


def test_log_s2_error_403_logs_key_forbidden(caplog):
    exc = _make_error(403, text='{"message":"Forbidden"}')
    with caplog.at_level(logging.WARNING, logger="scholar_mcp._s2_client"):
        log_s2_error(exc)
    assert "s2_key_forbidden" in caplog.text
    assert '{"message":"Forbidden"}' in caplog.text


def test_log_s2_error_non_403_logs_upstream_error(caplog):
    exc = _make_error(500, text="Internal Server Error")
    with caplog.at_level(logging.WARNING, logger="scholar_mcp._s2_client"):
        log_s2_error(exc)
    assert "s2_upstream_error" in caplog.text
    assert "s2_key_forbidden" not in caplog.text
    assert "Internal Server Error" in caplog.text


def test_format_s2_error_returns_generic_detail_and_status():
    exc = _make_error(403, text='{"message":"Forbidden"}')
    result = json.loads(format_s2_error(exc))
    assert result["error"] == "upstream_error"
    assert result["status"] == 403
    assert "Forbidden" not in result["detail"]
    assert "message" not in result["detail"]


def test_format_s2_error_non_403_status_preserved():
    exc = _make_error(500, text="Internal Server Error")
    result = json.loads(format_s2_error(exc))
    assert result["error"] == "upstream_error"
    assert result["status"] == 500
    assert "Internal Server Error" not in result["detail"]
