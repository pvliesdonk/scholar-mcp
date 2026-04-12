"""Service bundle lifespan and dependency injection for Scholar MCP Server."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

from ._cache import ScholarCache
from ._crossref_client import CrossRefClient
from ._docling_client import DoclingClient
from ._enricher_crossref import CrossRefEnricher
from ._enricher_openalex import OpenAlexEnricher
from ._enrichment import EnrichmentPipeline
from ._epo_client import EpoClient
from ._openalex_client import OpenAlexClient
from ._openlibrary_client import OpenLibraryClient
from ._rate_limiter import RateLimiter
from ._s2_client import S2Client
from ._standards_client import StandardsClient
from ._task_queue import TaskQueue
from .config import ServerConfig, load_config

if TYPE_CHECKING:
    from ._protocols import CacheProtocol

logger = logging.getLogger(__name__)

_CROSSREF_BASE = "https://api.crossref.org"
_OPENALEX_BASE = "https://api.openalex.org"
_OPENLIBRARY_BASE = "https://openlibrary.org"
_OPENLIBRARY_DELAY = 0.6  # ~100 req/min politeness


@dataclass
class ServiceBundle:
    """All shared services passed to tools via FastMCP dependency injection.

    Attributes:
        s2: Semantic Scholar API client.
        openalex: OpenAlex API client (httpx.AsyncClient pointed at OpenAlex).
        crossref: CrossRef API client for DOI metadata enrichment.
        docling: docling-serve httpx client, or None if not configured.
        epo: EPO OPS API client, or None if not configured.
        openlibrary: Open Library API client (keyless, always available).
        cache: SQLite cache.
        config: Server configuration.
    """

    s2: S2Client
    openalex: OpenAlexClient
    crossref: CrossRefClient
    docling: DoclingClient | None
    epo: EpoClient | None
    openlibrary: OpenLibraryClient
    cache: CacheProtocol
    config: ServerConfig
    tasks: TaskQueue
    standards: StandardsClient
    enrichment: EnrichmentPipeline


def _build_enrichment_pipeline() -> EnrichmentPipeline:
    """Build the enrichment pipeline with all registered enrichers.

    OpenLibraryEnricher is imported here (not at module level) to avoid
    a circular import: _enricher_openlibrary -> _book_enrichment -> _server_deps.

    Returns:
        Configured :class:`EnrichmentPipeline` instance.
    """
    from ._enricher_openlibrary import OpenLibraryEnricher

    return EnrichmentPipeline(
        [
            OpenAlexEnricher(),
            CrossRefEnricher(),
            OpenLibraryEnricher(),
        ]
    )


@asynccontextmanager
async def make_service_lifespan(
    app: FastMCP,
) -> AsyncGenerator[dict[str, ServiceBundle], None]:
    """FastMCP lifespan: create all clients, open cache, yield bundle.

    Args:
        app: The FastMCP application instance (unused but required by protocol).

    Yields:
        Dict mapping ``"bundle"`` to the :class:`ServiceBundle`.
    """
    config = load_config()
    config.cache_dir.mkdir(parents=True, exist_ok=True)

    s2 = S2Client(api_key=config.s2_api_key)
    ua = "scholar-mcp/0.1"
    if config.contact_email:
        ua = f"{ua} (mailto:{config.contact_email})"
    openalex_http = httpx.AsyncClient(
        base_url=_OPENALEX_BASE,
        headers={"User-Agent": ua},
        timeout=30.0,
    )
    openalex = OpenAlexClient(openalex_http)
    crossref_http = httpx.AsyncClient(
        base_url=_CROSSREF_BASE,
        headers={"User-Agent": ua},
        timeout=30.0,
    )
    crossref = CrossRefClient(crossref_http)
    openlibrary_http = httpx.AsyncClient(
        base_url=_OPENLIBRARY_BASE,
        headers={"User-Agent": ua},
        timeout=30.0,
        follow_redirects=True,
    )
    openlibrary_limiter = RateLimiter(delay=_OPENLIBRARY_DELAY)
    openlibrary = OpenLibraryClient(openlibrary_http, openlibrary_limiter)
    docling_http: httpx.AsyncClient | None = None
    docling: DoclingClient | None = None
    if config.docling_url:
        docling_http = httpx.AsyncClient(base_url=config.docling_url, timeout=300.0)
        docling = DoclingClient(
            http_client=docling_http,
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
    else:
        logger.info("docling_not_configured pdf_tools_disabled")

    # EPO OPS (optional — patent tools only available when configured)
    epo: EpoClient | None = None
    if config.epo_configured:
        epo = EpoClient(
            consumer_key=config.epo_consumer_key,  # type: ignore[arg-type]
            consumer_secret=config.epo_consumer_secret,  # type: ignore[arg-type]
        )
        logger.info("epo_ops status=configured")
    else:
        logger.info("epo_ops status=not_configured")

    cache = ScholarCache(config.cache_dir / "cache.db")
    await cache.open()

    tasks = TaskQueue()

    standards_http = httpx.AsyncClient(timeout=30.0)
    standards = StandardsClient(standards_http, cache_dir=config.cache_dir)

    enrichment = _build_enrichment_pipeline()

    bundle = ServiceBundle(
        s2=s2,
        openalex=openalex,
        crossref=crossref,
        docling=docling,
        epo=epo,
        openlibrary=openlibrary,
        cache=cache,
        config=config,
        tasks=tasks,
        standards=standards,
        enrichment=enrichment,
    )
    try:
        yield {"bundle": bundle}
    finally:
        await s2.aclose()
        await openalex_http.aclose()
        await crossref_http.aclose()
        await openlibrary.aclose()
        if docling_http:
            await docling_http.aclose()
        if epo is not None:
            await epo.aclose()
        await standards.aclose()
        await cache.close()


def get_bundle(ctx: Context = CurrentContext()) -> ServiceBundle:
    """FastMCP dependency: extract ServiceBundle from lifespan context.

    Args:
        ctx: FastMCP request context (injected automatically).

    Returns:
        The :class:`ServiceBundle` created during lifespan.
    """
    return ctx.lifespan_context["bundle"]  # type: ignore[no-any-return]
