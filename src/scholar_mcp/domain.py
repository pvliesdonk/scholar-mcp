"""Domain service for Scholar MCP.

:class:`Service` owns every upstream client, the SQLite cache and the
enrichment pipeline for the life of the server. The template's
``server_lifespan`` constructs it with no arguments and brackets the server
with :meth:`Service.start` / :meth:`Service.stop`; tools resolve it through
``Depends(get_service)``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING

import httpx

from ._cache import ScholarCache
from ._crossref_client import CrossRefClient
from ._docling_client import DoclingClient
from ._enricher_crossref import CrossRefEnricher
from ._enricher_openalex import OpenAlexEnricher
from ._enrichment import EnrichmentPipeline
from ._epo_client import EpoClient
from ._google_books_client import GoogleBooksClient
from ._openalex_client import OpenAlexClient
from ._openlibrary_client import OpenLibraryClient
from ._rate_limiter import RateLimiter
from ._s2_client import (
    KEEPALIVE_INTERVAL_SECONDS,
    S2_KEEPALIVE_STATUS,
    KeepaliveStatus,
    S2Client,
    run_keepalive,
)
from ._standards_client import StandardsClient
from .config import ProjectConfig

if TYPE_CHECKING:
    from ._protocols import CacheProtocol

logger = logging.getLogger(__name__)

_CROSSREF_BASE = "https://api.crossref.org"
_GOOGLE_BOOKS_BASE = "https://www.googleapis.com/books/v1"
_OPENALEX_BASE = "https://api.openalex.org"
_OPENLIBRARY_BASE = "https://openlibrary.org"
_OPENLIBRARY_DELAY = 0.6  # ~100 req/min politeness


class Service:
    """All shared services, resolved by tools through ``Depends(get_service)``.

    The client attributes exist once :meth:`start` has run. Tests that need a
    service without a lifespan construct one and assign the attributes
    directly.

    Attributes:
        config: Server configuration.
        s2: Semantic Scholar API client.
        openalex: OpenAlex API client.
        crossref: CrossRef API client for DOI metadata enrichment.
        google_books: Google Books API client for book excerpts and previews.
        docling: docling-serve client, or None if not configured.
        epo: EPO OPS API client, or None if not configured.
        openlibrary: Open Library API client (keyless, always available).
        cache: SQLite cache.
        standards: Standards resolution client.
        enrichment: Enrichment pipeline over every registered enricher.
    """

    s2: S2Client
    openalex: OpenAlexClient
    crossref: CrossRefClient
    google_books: GoogleBooksClient
    docling: DoclingClient | None
    epo: EpoClient | None
    openlibrary: OpenLibraryClient
    cache: CacheProtocol
    standards: StandardsClient
    enrichment: EnrichmentPipeline

    def __init__(self, config: ProjectConfig | None = None) -> None:
        """Bind the service to *config*, loading it from the environment if omitted.

        Args:
            config: Pre-loaded configuration; ``None`` reads the environment.
        """
        self.config = config or ProjectConfig.from_env()
        self._stack: AsyncExitStack | None = None

    async def start(self) -> None:
        """Build every client, open the cache and start the S2 keepalive.

        Each resource registers its cleanup as soon as it exists, so a failure
        part-way through startup closes what was already built instead of
        leaking it (#230).
        """
        config = self.config
        config.cache_dir.mkdir(parents=True, exist_ok=True)
        async with AsyncExitStack() as stack:
            self._open_clients(stack)

            cache = ScholarCache(config.cache_dir / "cache.db")
            await cache.open()
            stack.push_async_callback(cache.close)
            self.cache = cache

            self.standards = StandardsClient(
                httpx.AsyncClient(timeout=30.0), cache_dir=config.cache_dir, cache=cache
            )
            stack.push_async_callback(self.standards.aclose)
            self.enrichment = _build_enrichment_pipeline()

            keepalive = _start_s2_keepalive(
                self.s2, api_key=config.s2_api_key, status=S2_KEEPALIVE_STATUS
            )
            if keepalive is not None:
                stack.push_async_callback(_cancel_task, keepalive)
            self._stack = stack.pop_all()

    async def stop(self) -> None:
        """Close everything :meth:`start` built, in reverse order."""
        stack, self._stack = self._stack, None
        if stack is not None:
            await stack.aclose()

    def _open_clients(self, stack: AsyncExitStack) -> None:
        """Construct the upstream API clients, registering each one's cleanup.

        Args:
            stack: The exit stack that closes the clients on shutdown.
        """
        config = self.config
        ua = "scholar-mcp/0.1"
        if config.contact_email:
            ua = f"{ua} (mailto:{config.contact_email})"

        self.s2 = S2Client(api_key=config.s2_api_key)
        stack.push_async_callback(self.s2.aclose)
        self.openalex = OpenAlexClient(_http_client(stack, _OPENALEX_BASE, ua))
        self.crossref = CrossRefClient(_http_client(stack, _CROSSREF_BASE, ua))
        self.google_books = GoogleBooksClient(
            _http_client(stack, _GOOGLE_BOOKS_BASE, ua),
            api_key=config.google_books_api_key,
        )
        openlibrary_http = httpx.AsyncClient(
            base_url=_OPENLIBRARY_BASE,
            headers={"User-Agent": ua},
            timeout=30.0,
            follow_redirects=True,
        )
        self.openlibrary = OpenLibraryClient(
            openlibrary_http, RateLimiter(delay=_OPENLIBRARY_DELAY)
        )
        stack.push_async_callback(self.openlibrary.aclose)

        docling_http, self.docling = _build_docling(config)
        if docling_http is not None:
            stack.push_async_callback(docling_http.aclose)
        self.epo = _build_epo(config)
        if self.epo is not None:
            stack.push_async_callback(self.epo.aclose)


def _http_client(stack: AsyncExitStack, base_url: str, ua: str) -> httpx.AsyncClient:
    """Build a plain upstream HTTP client and register its cleanup.

    Args:
        stack: The exit stack that closes the client on shutdown.
        base_url: Upstream API base URL.
        ua: ``User-Agent`` header value.

    Returns:
        The constructed client.
    """
    http = httpx.AsyncClient(
        base_url=base_url, headers={"User-Agent": ua}, timeout=30.0
    )
    stack.push_async_callback(http.aclose)
    return http


async def _cancel_task(task: asyncio.Task[None]) -> None:
    """Cancel *task* and wait for it to finish unwinding.

    Args:
        task: The background task to stop.
    """
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def _build_enrichment_pipeline() -> EnrichmentPipeline:
    """Build the enrichment pipeline with all registered enrichers.

    OpenLibraryEnricher is imported here (not at module level) to avoid a
    circular import: _enricher_openlibrary -> _book_enrichment -> domain. The
    other late-bound enrichers are imported alongside it for symmetry.

    Returns:
        Configured :class:`EnrichmentPipeline` instance.
    """
    from ._enricher_google_books import GoogleBooksEnricher
    from ._enricher_openlibrary import OpenLibraryEnricher
    from ._enricher_standards import StandardsEnricher

    return EnrichmentPipeline(
        [
            OpenAlexEnricher(),
            CrossRefEnricher(),
            StandardsEnricher(),
            OpenLibraryEnricher(),
            GoogleBooksEnricher(),
        ]
    )


def _start_s2_keepalive(
    client: S2Client, *, api_key: str | None, status: KeepaliveStatus
) -> asyncio.Task[None] | None:
    """Start the S2 keepalive background task if an API key is configured.

    Args:
        client: The S2 client to keep alive.
        api_key: The configured S2 API key, or None.
        status: The shared record ``get_server_info`` reads. Marked
            not-configured when no key is set, so the absence reports itself
            rather than looking like a key that has never been pinged (#229).

    Returns:
        The created task, or None if no API key is configured.
    """
    if not api_key:
        logger.info("s2_keepalive_not_started reason=no_api_key")
        status.mark_not_configured()
        return None
    logger.info(
        "s2_keepalive_started interval_days=%s", KEEPALIVE_INTERVAL_SECONDS // 86400
    )
    return asyncio.create_task(run_keepalive(client, status=status))


def _build_docling(
    config: ProjectConfig,
) -> tuple[httpx.AsyncClient | None, DoclingClient | None]:
    """Build the optional docling-serve client pair.

    Args:
        config: Loaded project configuration.

    Returns:
        The ``(http_client, docling_client)`` pair, or ``(None, None)`` when
        ``SCHOLAR_MCP_DOCLING_URL`` is unset.  The raw HTTP client is
        returned alongside so the service can close it on shutdown.
    """
    if not config.docling_url:
        logger.info("docling_not_configured pdf_tools_disabled")
        return None, None

    http = httpx.AsyncClient(base_url=config.docling_url, timeout=300.0)
    docling = DoclingClient(
        http_client=http,
        vlm_api_url=config.vlm_api_url,
        vlm_api_key=config.vlm_api_key,
        vlm_model=config.vlm_model,
    )
    logger.info(
        "docling_configured url=%s vlm_available=%s vlm_model=%s",
        config.docling_url,
        docling.vlm_available,
        config.vlm_model if docling.vlm_available else "(n/a)",
    )
    return http, docling


def _build_epo(config: ProjectConfig) -> EpoClient | None:
    """Build the optional EPO OPS client.

    Patent tools are only registered when the OPS credentials are present, so
    an unconfigured deployment yields ``None`` rather than a client that fails
    at call time.

    Args:
        config: Loaded project configuration.

    Returns:
        The configured :class:`EpoClient`, or ``None``.
    """
    if not config.epo_configured:
        logger.info("epo_ops status=not_configured")
        return None

    epo = EpoClient(
        consumer_key=config.epo_consumer_key,  # type: ignore[arg-type]
        consumer_secret=config.epo_consumer_secret,  # type: ignore[arg-type]
    )
    logger.info("epo_ops status=configured")
    return epo
