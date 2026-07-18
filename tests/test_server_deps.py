"""Tests for _server_deps module."""

import asyncio

import pytest

from scholar_mcp._enrichment import EnrichmentPipeline
from scholar_mcp._s2_client import S2Client
from scholar_mcp._server_deps import _build_enrichment_pipeline, _start_s2_keepalive


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
