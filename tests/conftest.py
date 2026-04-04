"""Shared test fixtures for Scholar MCP Server tests."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

from scholar_mcp._cache import ScholarCache
from scholar_mcp._s2_client import S2Client
from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp.config import ServerConfig


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all SCHOLAR_MCP_* env vars before each test.

    Prevents env var leakage between tests that call :func:`create_server`.
    """
    for key in list(os.environ):
        if key.startswith("SCHOLAR_MCP_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
async def cache(tmp_path: Path) -> ScholarCache:
    """Provide an open ScholarCache backed by a temp SQLite file."""
    c = ScholarCache(tmp_path / "test.db")
    await c.open()
    yield c
    await c.close()


@pytest.fixture
def test_config(tmp_path: Path) -> ServerConfig:
    """Provide a ServerConfig pointing cache_dir at a temp directory."""
    return ServerConfig(cache_dir=tmp_path, docling_url=None)


@pytest.fixture
def bundle(cache: ScholarCache, test_config: ServerConfig) -> ServiceBundle:
    """Provide a ServiceBundle wired to in-memory/temp test services."""
    s2 = S2Client(api_key=None, delay=0.0)
    openalex = httpx.AsyncClient(base_url="https://api.openalex.org")
    return ServiceBundle(
        s2=s2,
        openalex=openalex,
        docling=None,
        cache=cache,
        config=test_config,
    )
