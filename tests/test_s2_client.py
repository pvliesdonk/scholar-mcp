import asyncio
import json
import logging

import httpx
import pytest

from scholar_mcp._s2_client import (
    FIELD_SETS,
    KEEPALIVE_DEGRADED_AFTER_FAILURES,
    KEEPALIVE_INTERVAL_SECONDS,
    KEEPALIVE_PAPER_ID,
    KEEPALIVE_RETRY_INTERVAL_SECONDS,
    KeepaliveStatus,
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
        await run_keepalive(client, status=KeepaliveStatus())

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
        await run_keepalive(client, status=KeepaliveStatus())

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
        await run_keepalive(client, status=KeepaliveStatus())

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
        await run_keepalive(client, status=KeepaliveStatus())

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
        await run_keepalive(client, status=KeepaliveStatus())

    assert route.call_count == 1
    assert "s2_keepalive_failed status=network_error" in caplog.text


# --- A refused ping costs a retry interval, not the whole cycle (#368) ---


@pytest.mark.respx(base_url=S2_BASE)
async def test_run_keepalive_retries_soon_after_a_refused_ping(
    respx_mock, client, caplog, monkeypatch
):
    """A 429 sleeps the short retry interval, not the full 7-day cycle."""
    respx_mock.get(f"/paper/{KEEPALIVE_PAPER_ID}").mock(
        return_value=httpx.Response(429, text="slow down")
    )
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr("scholar_mcp._s2_client.asyncio.sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await run_keepalive(client, status=KeepaliveStatus())

    assert sleep_calls == [
        KEEPALIVE_RETRY_INTERVAL_SECONDS,
        KEEPALIVE_RETRY_INTERVAL_SECONDS,
    ]


@pytest.mark.respx(base_url=S2_BASE)
async def test_run_keepalive_returns_to_full_interval_after_recovery(
    respx_mock, client, caplog, monkeypatch
):
    """Once a ping lands, the loop goes back to the full cycle."""
    respx_mock.get(f"/paper/{KEEPALIVE_PAPER_ID}").mock(
        side_effect=[
            httpx.Response(429, text="slow down"),
            httpx.Response(200, json={"paperId": "x"}),
        ]
    )
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr("scholar_mcp._s2_client.asyncio.sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await run_keepalive(client, status=KeepaliveStatus())

    assert sleep_calls == [
        KEEPALIVE_RETRY_INTERVAL_SECONDS,
        KEEPALIVE_INTERVAL_SECONDS,
    ]


@pytest.mark.respx(base_url=S2_BASE)
async def test_run_keepalive_escalates_once_when_failures_persist(
    respx_mock, client, caplog, monkeypatch
):
    """Sustained refusal is an operator-visible ERROR, logged once, not spam.

    The observed failure mode is an endless 429 that never becomes a 403,
    so the escalation keys on persistence rather than on a status code.
    """
    respx_mock.get(f"/paper/{KEEPALIVE_PAPER_ID}").mock(
        return_value=httpx.Response(429, text="slow down")
    )
    monkeypatch.setattr("scholar_mcp._s2_client.KEEPALIVE_DEGRADED_AFTER_FAILURES", 2)
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 4:
            raise asyncio.CancelledError

    monkeypatch.setattr("scholar_mcp._s2_client.asyncio.sleep", fake_sleep)
    with (
        caplog.at_level(logging.DEBUG, logger="scholar_mcp._s2_client"),
        pytest.raises(asyncio.CancelledError),
    ):
        await run_keepalive(client, status=KeepaliveStatus())

    degraded = [r for r in caplog.records if "s2_keepalive_degraded" in r.message]
    assert len(degraded) == 1, "escalation must not re-log on every retry"
    assert degraded[0].levelno == logging.ERROR
    assert "consecutive_failures=2" in degraded[0].message


@pytest.mark.respx(base_url=S2_BASE)
async def test_run_keepalive_reports_recovery_after_degrading(
    respx_mock, client, caplog, monkeypatch
):
    """The operator who saw the ERROR gets told when the key works again."""
    respx_mock.get(f"/paper/{KEEPALIVE_PAPER_ID}").mock(
        side_effect=[
            httpx.Response(429, text="slow down"),
            httpx.Response(429, text="slow down"),
            httpx.Response(200, json={"paperId": "x"}),
        ]
    )
    monkeypatch.setattr("scholar_mcp._s2_client.KEEPALIVE_DEGRADED_AFTER_FAILURES", 2)
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 3:
            raise asyncio.CancelledError

    monkeypatch.setattr("scholar_mcp._s2_client.asyncio.sleep", fake_sleep)
    with (
        caplog.at_level(logging.DEBUG, logger="scholar_mcp._s2_client"),
        pytest.raises(asyncio.CancelledError),
    ):
        await run_keepalive(client, status=KeepaliveStatus())

    assert "s2_keepalive_recovered after_failures=2" in caplog.text


@pytest.mark.respx(base_url=S2_BASE)
async def test_run_keepalive_stays_quiet_when_never_degraded(
    respx_mock, client, caplog, monkeypatch
):
    """A single failure that clears reports no recovery: nothing was announced."""
    respx_mock.get(f"/paper/{KEEPALIVE_PAPER_ID}").mock(
        side_effect=[
            httpx.Response(429, text="slow down"),
            httpx.Response(200, json={"paperId": "x"}),
        ]
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
        await run_keepalive(client, status=KeepaliveStatus())

    assert "s2_keepalive_degraded" not in caplog.text
    assert "s2_keepalive_recovered" not in caplog.text


# --- The keepalive's verdict is readable, not only loggable (#229) ---


def test_keepalive_status_is_unknown_before_the_first_ping() -> None:
    """A configured key with no result yet is unknown, never ok.

    The window matters: the loop pings on startup, so anything reading this
    in the first moments of a process must not be told the key is fine.
    """
    status = KeepaliveStatus()
    status.mark_configured()
    assert status.as_dict()["key_status"] == "unknown"


def test_keepalive_status_reports_not_configured_without_a_key() -> None:
    """No key is a deployment choice, not a fault: the anonymous tier works."""
    status = KeepaliveStatus()
    status.mark_not_configured()
    payload = status.as_dict()
    assert payload["key_status"] == "not_configured"
    assert payload["key_configured"] is False


def test_keepalive_status_reports_ok_after_a_successful_ping() -> None:
    status = KeepaliveStatus()
    status.mark_configured()
    status.record_success()
    payload = status.as_dict()
    assert payload["key_status"] == "ok"
    assert payload["consecutive_failures"] == 0
    assert payload["last_success"] is not None


def test_keepalive_status_distinguishes_failing_from_degraded() -> None:
    """One refusal is noise; a day of them is the signal #368 escalates on."""
    status = KeepaliveStatus()
    status.mark_configured()
    status.record_failure("rate_limited")
    assert status.as_dict()["key_status"] == "failing"

    for _ in range(KEEPALIVE_DEGRADED_AFTER_FAILURES - 1):
        status.record_failure("rate_limited")
    payload = status.as_dict()
    assert payload["key_status"] == "degraded"
    assert payload["consecutive_failures"] == KEEPALIVE_DEGRADED_AFTER_FAILURES
    assert payload["last_failure_kind"] == "rate_limited"


def test_keepalive_status_clears_on_recovery() -> None:
    """A recovered key must stop reporting degraded, and keep the history."""
    status = KeepaliveStatus()
    status.mark_configured()
    for _ in range(KEEPALIVE_DEGRADED_AFTER_FAILURES):
        status.record_failure("rate_limited")
    status.record_success()
    payload = status.as_dict()
    assert payload["key_status"] == "ok"
    assert payload["consecutive_failures"] == 0
    assert payload["last_failure"] is not None, "the failure history survives recovery"


@pytest.mark.respx(base_url=S2_BASE)
async def test_run_keepalive_publishes_its_verdict(
    respx_mock, client, monkeypatch
) -> None:
    """The loop updates the shared status, so a reader sees what the log says."""
    respx_mock.get(f"/paper/{KEEPALIVE_PAPER_ID}").mock(
        return_value=httpx.Response(429, text="slow down")
    )
    status = KeepaliveStatus()
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr("scholar_mcp._s2_client.asyncio.sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await run_keepalive(client, status=status)

    payload = status.as_dict()
    assert payload["consecutive_failures"] == 2
    assert payload["key_status"] == "failing"
    assert payload["last_failure_kind"] == "rate_limited"
