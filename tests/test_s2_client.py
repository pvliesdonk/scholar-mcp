import asyncio
import json
import logging

import httpx
import pytest

from scholar_mcp._s2_client import (
    FIELD_SETS,
    KEEPALIVE_INTERVAL_SECONDS,
    KEEPALIVE_PAPER_ID,
    S2Client,
    format_s2_error,
    log_s2_error,
    run_keepalive,
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


@pytest.mark.respx(base_url=S2_BASE)
async def test_run_keepalive_calls_immediately_then_on_interval(
    respx_mock, client, caplog, monkeypatch
):
    """First call happens before any sleep; loop continues after success."""
    route = respx_mock.get(f"/paper/{KEEPALIVE_PAPER_ID}").mock(
        return_value=httpx.Response(200, json={"paperId": "x"})
    )
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr("scholar_mcp._s2_client.asyncio.sleep", fake_sleep)
    with (
        caplog.at_level(logging.DEBUG, logger="scholar_mcp._s2_client"),
        pytest.raises(asyncio.CancelledError),
    ):
        await run_keepalive(client)

    assert route.call_count == 2
    assert sleep_calls == [KEEPALIVE_INTERVAL_SECONDS, KEEPALIVE_INTERVAL_SECONDS]
    assert "s2_keepalive_ok" in caplog.text


@pytest.mark.respx(base_url=S2_BASE)
async def test_run_keepalive_403_logs_and_continues(
    respx_mock, client, caplog, monkeypatch
):
    """A 403 mid-loop logs s2_keepalive_key_forbidden but does not kill the loop."""
    route = respx_mock.get(f"/paper/{KEEPALIVE_PAPER_ID}").mock(
        side_effect=[
            httpx.Response(403, json={"message": "Forbidden"}),
            httpx.Response(200, json={"paperId": "x"}),
        ]
    )
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 1:
            raise asyncio.CancelledError

    monkeypatch.setattr("scholar_mcp._s2_client.asyncio.sleep", fake_sleep)
    with (
        caplog.at_level(logging.DEBUG, logger="scholar_mcp._s2_client"),
        pytest.raises(asyncio.CancelledError),
    ):
        await run_keepalive(client)

    assert route.call_count == 1
    assert "s2_keepalive_key_forbidden" in caplog.text


@pytest.mark.respx(base_url=S2_BASE)
async def test_run_keepalive_other_failure_logs_warning_and_continues(
    respx_mock, client, caplog, monkeypatch
):
    """A non-403 failure logs s2_keepalive_failed but does not kill the loop."""
    route = respx_mock.get(f"/paper/{KEEPALIVE_PAPER_ID}").mock(
        return_value=httpx.Response(500, text="boom")
    )
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 1:
            raise asyncio.CancelledError

    monkeypatch.setattr("scholar_mcp._s2_client.asyncio.sleep", fake_sleep)
    with (
        caplog.at_level(logging.DEBUG, logger="scholar_mcp._s2_client"),
        pytest.raises(asyncio.CancelledError),
    ):
        await run_keepalive(client)

    assert route.call_count == 1
    assert "s2_keepalive_failed" in caplog.text


@pytest.mark.respx(base_url=S2_BASE)
async def test_run_keepalive_rate_limited_logs_and_continues(
    respx_mock, client, caplog, monkeypatch
):
    """A 429 (RateLimitedError, since get_paper is called with retry=False)
    logs s2_keepalive_rate_limited but does not kill the loop."""
    route = respx_mock.get(f"/paper/{KEEPALIVE_PAPER_ID}").mock(
        return_value=httpx.Response(429, text="slow down")
    )
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 1:
            raise asyncio.CancelledError

    monkeypatch.setattr("scholar_mcp._s2_client.asyncio.sleep", fake_sleep)
    with (
        caplog.at_level(logging.DEBUG, logger="scholar_mcp._s2_client"),
        pytest.raises(asyncio.CancelledError),
    ):
        await run_keepalive(client)

    assert route.call_count == 1
    assert "s2_keepalive_rate_limited" in caplog.text


@pytest.mark.respx(base_url=S2_BASE)
async def test_run_keepalive_network_error_logs_and_continues(
    respx_mock, client, caplog, monkeypatch
):
    """A network-level failure (httpx.HTTPError, not HTTPStatusError) logs
    s2_keepalive_failed status=network_error but does not kill the loop."""
    route = respx_mock.get(f"/paper/{KEEPALIVE_PAPER_ID}").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 1:
            raise asyncio.CancelledError

    monkeypatch.setattr("scholar_mcp._s2_client.asyncio.sleep", fake_sleep)
    with (
        caplog.at_level(logging.DEBUG, logger="scholar_mcp._s2_client"),
        pytest.raises(asyncio.CancelledError),
    ):
        await run_keepalive(client)

    assert route.call_count == 1
    assert "s2_keepalive_failed status=network_error" in caplog.text
