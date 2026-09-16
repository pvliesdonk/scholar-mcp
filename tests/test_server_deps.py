"""Tests for the service lifespan and the domain ``Service``."""

import asyncio
from pathlib import Path

import pytest

from scholar_mcp._cache import ScholarCache
from scholar_mcp._enrichment import EnrichmentPipeline
from scholar_mcp._s2_client import KeepaliveStatus, S2Client
from scholar_mcp._server_deps import server_lifespan
from scholar_mcp.config import ProjectConfig
from scholar_mcp.domain import (
    Service,
    _build_docling,
    _build_enrichment_pipeline,
    _start_s2_keepalive,
)
from tests.conftest import tasks_server


def test_build_enrichment_pipeline() -> None:
    """Pipeline builder returns an EnrichmentPipeline with registered enrichers."""
    pipeline = _build_enrichment_pipeline()
    assert isinstance(pipeline, EnrichmentPipeline)
    # Should have enrichers in at least two phases (0 and 1)
    assert len(pipeline._phases) >= 2


async def test_start_s2_keepalive_returns_none_without_key():
    """No keepalive task is created when no S2 API key is configured."""
    client = S2Client(api_key=None, delay=0.0)
    task = _start_s2_keepalive(client, api_key=None, status=KeepaliveStatus())
    assert task is None


async def test_start_s2_keepalive_creates_task_with_key():
    """A keepalive task is created and cancellable when an S2 API key is configured."""
    client = S2Client(api_key="fake-key", delay=0.0)
    task = _start_s2_keepalive(client, api_key="fake-key", status=KeepaliveStatus())
    assert task is not None
    assert isinstance(task, asyncio.Task)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_lifespan_starts_and_cancels_keepalive_with_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Entering/exiting the real lifespan starts and cleanly cancels the
    keepalive task end-to-end when an S2 API key is configured."""
    monkeypatch.setenv("SCHOLAR_MCP_S2_API_KEY", "fake-key")
    monkeypatch.setenv("SCHOLAR_MCP_CACHE_DIR", str(tmp_path))
    app = tasks_server(name="test")

    with caplog.at_level("INFO", logger="scholar_mcp.domain"):
        async with server_lifespan(app) as ctx:
            assert ctx["service"].s2 is not None
            tasks_while_open = {
                t
                for t in asyncio.all_tasks()
                if t.get_coro().__qualname__ == "run_keepalive"
            }
            assert len(tasks_while_open) == 1

    assert "s2_keepalive_started interval_days=7" in caplog.text
    tasks_after_close = {
        t for t in asyncio.all_tasks() if t.get_coro().__qualname__ == "run_keepalive"
    }
    assert not tasks_after_close


async def test_lifespan_does_not_start_keepalive_without_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Entering the real lifespan with no S2 API key configured starts no
    keepalive task."""
    monkeypatch.delenv("SCHOLAR_MCP_S2_API_KEY", raising=False)
    monkeypatch.setenv("SCHOLAR_MCP_CACHE_DIR", str(tmp_path))
    app = tasks_server(name="test")

    with caplog.at_level("INFO", logger="scholar_mcp.domain"):
        async with server_lifespan(app) as ctx:
            assert ctx["service"].s2 is not None
            tasks_while_open = {
                t
                for t in asyncio.all_tasks()
                if t.get_coro().__qualname__ == "run_keepalive"
            }
            assert not tasks_while_open

    assert "s2_keepalive_not_started reason=no_api_key" in caplog.text


async def test_lifespan_builds_and_closes_docling_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A configured docling URL reaches the service and its HTTP client is
    closed on teardown."""
    monkeypatch.setenv("SCHOLAR_MCP_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("SCHOLAR_MCP_DOCLING_URL", "http://docling.invalid")
    monkeypatch.setenv("SCHOLAR_MCP_VLM_API_URL", "http://vlm.invalid/v1")
    monkeypatch.setenv("SCHOLAR_MCP_VLM_API_KEY", "fake-key")
    monkeypatch.setenv("SCHOLAR_MCP_VLM_MODEL", "gpt-4o")
    app = tasks_server(name="test")

    with caplog.at_level("INFO", logger="scholar_mcp.domain"):
        async with server_lifespan(app) as ctx:
            docling = ctx["service"].docling
            assert docling is not None
            assert docling.vlm_available is True
            http = docling.http_client

    assert "docling_configured url=http://docling.invalid" in caplog.text
    assert "vlm_available=True" in caplog.text
    assert http.is_closed


async def test_build_docling_returns_none_pair_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """No docling URL yields no client pair and says so in the log."""
    monkeypatch.delenv("SCHOLAR_MCP_DOCLING_URL", raising=False)

    with caplog.at_level("INFO", logger="scholar_mcp.domain"):
        http, docling = _build_docling(ProjectConfig.from_env())

    assert (http, docling) == (None, None)
    assert "docling_not_configured pdf_tools_disabled" in caplog.text


async def test_start_failure_closes_what_was_already_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure part-way through startup unwinds the clients built before it.

    The cache opens after every HTTP client exists, so failing it proves the
    exit stack closes earlier resources instead of stranding them (#230).
    """
    monkeypatch.setenv("SCHOLAR_MCP_CACHE_DIR", str(tmp_path))
    service = Service()

    async def boom(self: object) -> None:
        raise RuntimeError("cache unavailable")

    monkeypatch.setattr("scholar_mcp.domain.ScholarCache.open", boom)

    with pytest.raises(RuntimeError, match="cache unavailable"):
        await service.start()

    assert service.openalex._client.is_closed
    assert service.crossref._client.is_closed


async def test_stop_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second ``stop`` after a clean shutdown is a no-op."""
    monkeypatch.setenv("SCHOLAR_MCP_CACHE_DIR", str(tmp_path))
    service = Service()
    await service.start()
    await service.stop()
    await service.stop()


async def test_start_failure_closes_a_partially_opened_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cache that fails after connecting is closed rather than stranded.

    ``ScholarCache.open`` assigns a live aiosqlite connection before applying
    the schema and the migrations, so the cleanup has to be registered before
    the await, not after it.
    """
    monkeypatch.setenv("SCHOLAR_MCP_CACHE_DIR", str(tmp_path))
    opened: list[ScholarCache] = []

    class RecordingCache(ScholarCache):
        def __init__(self, db_path: Path) -> None:
            super().__init__(db_path)
            opened.append(self)

    async def failing_migrations(_db: object) -> None:
        raise RuntimeError("migration failed")

    monkeypatch.setattr("scholar_mcp.domain.ScholarCache", RecordingCache)
    monkeypatch.setattr("scholar_mcp._cache._apply_migrations", failing_migrations)

    service = Service()
    with pytest.raises(RuntimeError, match="migration failed"):
        await service.start()

    assert opened, "the service never constructed a cache"
    assert opened[0]._db is None, "the partially opened cache was not closed"
