"""Shared test fixtures for Scholar MCP Server tests."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
from fastmcp_pvl_core import Jobs, JobsConfig, ServerConfig, build_jobs

from scholar_mcp import _epo_client
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
from scholar_mcp.config import ProjectConfig

_JOBS_TEST_DEADLINE_S = 0.05
"""Soft deadline for tests: short enough that a slow tool promotes at once.

Tests shrink the deadline rather than sleeping for real, so both branches of
``run_with_deadline`` -- inline result and promoted handle -- are reachable in
milliseconds.
"""


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all SCHOLAR_MCP_* env vars, then pin the KV backend.

    Clearing prevents env var leakage between tests that call
    :func:`make_server`.  Pinning `memory://` afterwards keeps job records out
    of the filesystem: unset, pvl-core's `build_kv_store` resolves to
    `file:///data/state` wherever that directory happens to be writable, so a
    machine with a `/data` volume would have the suite writing real job
    records.  Any test needing a different backend overrides it locally.
    """
    for key in list(os.environ):
        if key.startswith("SCHOLAR_MCP_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SCHOLAR_MCP_KV_STORE_URL", "memory://")


@pytest.fixture
async def cache(tmp_path: Path) -> ScholarCache:
    """Provide an open ScholarCache backed by a temp SQLite file."""
    c = ScholarCache(tmp_path / "test.db")
    await c.open()
    yield c
    await c.close()


@pytest.fixture
def test_config(tmp_path: Path) -> ProjectConfig:
    """Provide a ProjectConfig pointing cache_dir at a temp directory."""
    return ProjectConfig(cache_dir=tmp_path, docling_url=None)


@pytest.fixture
async def bundle(cache: ScholarCache, test_config: ProjectConfig) -> ServiceBundle:
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


@pytest.fixture(autouse=True)
def _fast_epo_backoff(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shrink the EPO throttle backoff so no test sleeps for real minutes.

    The production delay deliberately exceeds the 60s throttle-cache lifetime
    (see `_epo_client._THROTTLE_RETRY_DELAY_S`); waiting that out would add
    minutes per throttled case.

    A test asserting on the real constant -- the relationship between the
    delay and the cache lifetime is load-bearing -- opts out with
    `@pytest.mark.real_epo_backoff`, or it would be reading this stand-in.
    """
    if request.node.get_closest_marker("real_epo_backoff"):
        return
    monkeypatch.setattr(_epo_client, "_THROTTLE_RETRY_DELAY_S", 0.01)


@pytest.fixture
def jobs() -> Jobs:
    """Provide a memory-backed :class:`Jobs` with a near-zero soft deadline.

    Each test gets its own store, so job ids never leak between tests.
    """
    return build_jobs(
        ServerConfig(kv_store_url="memory://"),
        JobsConfig(soft_deadline_s=_JOBS_TEST_DEADLINE_S, result_ttl_s=60.0),
    )


@pytest.fixture
def slow_jobs() -> Jobs:
    """Provide a :class:`Jobs` whose deadline is long enough to answer inline.

    The counterpart to :func:`jobs`: work completes within the window, so the
    tool returns its own result rather than a handle.
    """
    return build_jobs(
        ServerConfig(kv_store_url="memory://"),
        JobsConfig(soft_deadline_s=30.0, result_ttl_s=60.0),
    )
