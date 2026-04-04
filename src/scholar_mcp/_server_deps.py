"""Service bundle lifespan and dependency injection for Scholar MCP Server."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context

from ._cache import ScholarCache
from ._docling_client import DoclingClient
from ._openalex_client import OpenAlexClient
from ._s2_client import S2Client
from ._task_queue import TaskQueue
from .config import ServerConfig, load_config

logger = logging.getLogger(__name__)

_OPENALEX_BASE = "https://api.openalex.org"


@dataclass
class ServiceBundle:
    """All shared services passed to tools via FastMCP dependency injection.

    Attributes:
        s2: Semantic Scholar API client.
        openalex: OpenAlex API client (httpx.AsyncClient pointed at OpenAlex).
        docling: docling-serve httpx client, or None if not configured.
        cache: SQLite cache.
        config: Server configuration.
    """

    s2: S2Client
    openalex: OpenAlexClient
    docling: DoclingClient | None
    cache: ScholarCache
    config: ServerConfig
    tasks: TaskQueue


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
        logger.info("docling_configured url=%s", config.docling_url)
    else:
        logger.info("docling_not_configured pdf_tools_disabled")

    cache = ScholarCache(config.cache_dir / "cache.db")
    await cache.open()

    tasks = TaskQueue()

    bundle = ServiceBundle(
        s2=s2,
        openalex=openalex,
        docling=docling,
        cache=cache,
        config=config,
        tasks=tasks,
    )
    try:
        yield {"bundle": bundle}
    finally:
        await s2.aclose()
        await openalex_http.aclose()
        if docling_http:
            await docling_http.aclose()
        await cache.close()


def get_bundle(ctx: Context = CurrentContext()) -> ServiceBundle:
    """FastMCP dependency: extract ServiceBundle from lifespan context.

    Args:
        ctx: FastMCP request context (injected automatically).

    Returns:
        The :class:`ServiceBundle` created during lifespan.
    """
    return ctx.lifespan_context["bundle"]  # type: ignore[no-any-return]
