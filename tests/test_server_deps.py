"""Tests for _server_deps module."""

import asyncio
from pathlib import Path

import pytest
from fastmcp import FastMCP

from scholar_mcp._enrichment import EnrichmentPipeline
from scholar_mcp._s2_client import S2Client
from scholar_mcp._server_deps import (
    _build_enrichment_pipeline,
    _start_s2_keepalive,
    make_service_lifespan,
)


def test_build_enrichment_pipeline() -> None:
    """Pipeline builder returns an EnrichmentPipeline with registered enrichers."""
    pipeline = _build_enrichment_pipeline()
    assert isinstance(pipeline, EnrichmentPipeline)
    # Should have enrichers in at least two phases (0 and 1)
    assert len(pipeline._phases) >= 2


async def test_start_s2_keepalive_returns_none_without_key():
    """No keepalive task is created when no S2 API key is configured."""
    client = S2Client(api_key=None, delay=0.0)
    task = _start_s2_keepalive(client, api_key=None)
    assert task is None


async def test_start_s2_keepalive_creates_task_with_key():
    """A keepalive task is created and cancellable when an S2 API key is configured."""
    client = S2Client(api_key="fake-key", delay=0.0)
    task = _start_s2_keepalive(client, api_key="fake-key")
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
    app = FastMCP(name="test")

    with caplog.at_level("INFO", logger="scholar_mcp._server_deps"):
        async with make_service_lifespan(app) as ctx:
            bundle = ctx["bundle"]
            assert bundle.s2 is not None
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
    app = FastMCP(name="test")

    with caplog.at_level("INFO", logger="scholar_mcp._server_deps"):
        async with make_service_lifespan(app) as ctx:
            assert ctx["bundle"].s2 is not None
            tasks_while_open = {
                t
                for t in asyncio.all_tasks()
                if t.get_coro().__qualname__ == "run_keepalive"
            }
            assert not tasks_while_open

    assert "s2_keepalive_not_started reason=no_api_key" in caplog.text
