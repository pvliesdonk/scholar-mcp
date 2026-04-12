"""Shared test fixtures for Scholar MCP Server tests."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

from scholar_mcp._cache import ScholarCache
from scholar_mcp._crossref_client import CrossRefClient
from scholar_mcp._enrichment import EnrichmentPipeline
from scholar_mcp._google_books_client import GoogleBooksClient
from scholar_mcp._openalex_client import OpenAlexClient
from scholar_mcp._openlibrary_client import OpenLibraryClient
from scholar_mcp._rate_limiter import RateLimiter
from scholar_mcp._s2_client import S2Client
from scholar_mcp._server_deps import ServiceBundle
from scholar_mcp._standards_client import StandardsClient
from scholar_mcp._task_queue import TaskQueue
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
async def bundle(cache: ScholarCache, test_config: ServerConfig) -> ServiceBundle:
    """Provide a ServiceBundle wired to in-memory/temp test services."""
    s2 = S2Client(api_key=None, delay=0.0)
    openalex_http = httpx.AsyncClient(base_url="https://api.openalex.org")
    openalex = OpenAlexClient(openalex_http)
    crossref_http = httpx.AsyncClient(base_url="https://api.crossref.org", timeout=10.0)
    crossref = CrossRefClient(crossref_http)
    google_books_http = httpx.AsyncClient(
        base_url="https://www.googleapis.com/books/v1", timeout=10.0
    )
    google_books = GoogleBooksClient(google_books_http)
    openlibrary_http = httpx.AsyncClient(
        base_url="https://openlibrary.org", timeout=10.0, follow_redirects=True
    )
    openlibrary = OpenLibraryClient(openlibrary_http, RateLimiter(delay=0.0))
    standards_http = httpx.AsyncClient(timeout=10.0)
    standards = StandardsClient(standards_http)
    # Import enrichers here to avoid circular import
    # (_enricher_openlibrary -> _book_enrichment -> _server_deps)
    from scholar_mcp._enricher_crossref import CrossRefEnricher
    from scholar_mcp._enricher_google_books import GoogleBooksEnricher
    from scholar_mcp._enricher_openalex import OpenAlexEnricher
    from scholar_mcp._enricher_openlibrary import OpenLibraryEnricher

    enrichment = EnrichmentPipeline(
        [
            OpenAlexEnricher(),
            CrossRefEnricher(),
            OpenLibraryEnricher(),
            GoogleBooksEnricher(),
        ]
    )
    yield ServiceBundle(
        s2=s2,
        openalex=openalex,
        crossref=crossref,
        google_books=google_books,
        docling=None,
        epo=None,
        openlibrary=openlibrary,
        cache=cache,
        config=test_config,
        tasks=TaskQueue(),
        standards=standards,
        enrichment=enrichment,
    )
    await crossref_http.aclose()
    await google_books_http.aclose()
    await openlibrary_http.aclose()
    await openalex_http.aclose()
    await s2.aclose()
    await standards.aclose()
