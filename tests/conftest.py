"""Shared test fixtures for Scholar MCP Server tests."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastmcp import Client, FastMCP
from fastmcp_pvl_core import (
    Jobs,
    JobsConfig,
    ServerConfig,
    build_jobs,
    configure_task_backend,
)

from scholar_mcp import _epo_client, _rate_limiter
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
from scholar_mcp.config import _ENV_PREFIX, ProjectConfig
from scholar_mcp.server import make_server

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


def tasks_server(*args: Any, **kwargs: Any) -> FastMCP:
    """A bare ``FastMCP`` carrying the SEP-2663 tasks extension.

    Every tool registered through ``register_long_running_tool`` is
    task-enabled, and from FastMCP 4 a server carrying one refuses to start
    unless the tasks extension is registered on it -- the client's connect
    fails with ``require the tasks extension``.  ``make_server`` gets that
    from ``configure_task_backend``; a test assembling its own server has to
    do the same, or it is testing a server production never builds.

    ``tasks_url`` is pinned to ``memory://`` rather than read from the
    environment, so no test can reach a real Redis even if one is configured
    on the machine running the suite.

    Args:
        *args: Positional arguments for ``FastMCP`` (typically the name).
        **kwargs: Keyword arguments for ``FastMCP`` (typically ``lifespan``).

    Returns:
        The constructed server, with the tasks extension already registered.
    """
    app = FastMCP(*args, **kwargs)
    configure_task_backend(app, _ENV_PREFIX, ServerConfig(tasks_url="memory://"))
    return app


class PlainClient(Client[Any]):
    """A ``Client`` that does not negotiate the SEP-2663 tasks extension.

    ``fastmcp.Client`` sets ``_auto_internal_extensions = True`` and folds the
    ``fastmcp-tasks`` client extension in at construction, so an ordinary
    client transparently drives a server's background tasks.  A tool
    registered by ``register_long_running_tool`` is ``TaskConfig(mode=
    "optional")``, and the server's ``intercept_tool_call`` runs an optional
    tool as a task *only when the client opted in* -- so under an ordinary
    client the native path always wins and pvl-core's soft-deadline promotion
    never happens.

    The promotion fallback is what a client that does not speak tasks gets,
    which is most MCP clients today, so it needs a client of that shape to be
    testable at all.  Overriding the class attribute is the only lever
    fastmcp offers; it is the same one ``ProxyClient`` uses, for the same
    reason -- a proxy must not advertise task support it cannot honour.
    """

    _auto_internal_extensions = False


@pytest.fixture
def server(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> FastMCP:
    """Construct a fresh server *synchronously*, outside any event loop.

    ``make_server()`` must not run inside a running loop. From pvl-core 6 the
    instruction finalizer enumerates the effective tool set through
    ``effective_tool_names``, which calls ``asyncio.get_running_loop()`` and
    raises rather than move loop-affine providers onto a worker loop
    (fastmcp-pvl-core ``_visibility.py``). A synchronous fixture is set up
    before pytest-asyncio enters the loop it runs an ``async def`` test in, so
    an async test takes its server from here instead of building one in the
    body. ``tests/test_server_construction.py`` enforces that.

    Environment the server reads is supplied by indirect parametrisation::

        @pytest.mark.parametrize("server", [_EPO_ENV], indirect=True, ids=["epo"])
        async def test_patent_tools_are_visible(server: FastMCP) -> None: ...

    ``cache_dir`` always points into ``tmp_path``, so entering the lifespan
    creates its state directory under the test's scratch space rather than in
    the real cache location.
    """
    monkeypatch.setenv("SCHOLAR_MCP_CACHE_DIR", str(tmp_path / "cache"))
    for key, value in getattr(request, "param", {}).items():
        monkeypatch.setenv(key, value)
    return make_server()


@pytest.fixture
async def client(server: FastMCP) -> AsyncIterator[Client[Any]]:
    """Provide an in-memory client connected to the :func:`server` fixture.

    The client is async because connecting enters the server's lifespan; the
    server it wraps was already built synchronously.
    """
    async with Client(server) as c:
        yield c


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
    # Same reasoning for the S2 429 backoff, which the migrated tools now
    # rely on instead of a queue hop: the real 1s/2s/4s ladder would add
    # seconds to every rate-limit test.
    monkeypatch.setattr(_rate_limiter, "_S2_BASE_DELAY_S", 0.01)


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
