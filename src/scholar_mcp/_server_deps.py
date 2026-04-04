"""Service bundle lifespan and dependency injection for Scholar MCP Server."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from ._cache import ScholarCache
from ._s2_client import S2Client
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
    openalex: httpx.AsyncClient  # NOTE: refined to OpenAlexClient in Task 11
    docling: httpx.AsyncClient | None  # NOTE: refined to DoclingClient in Task 12
    cache: ScholarCache
    config: ServerConfig


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
    openalex = httpx.AsyncClient(
        base_url=_OPENALEX_BASE,
        headers={"User-Agent": "scholar-mcp/0.1 (mailto:scholar-mcp@pvliesdonk.nl)"},
        timeout=30.0,
    )
    docling: httpx.AsyncClient | None = None
    if config.docling_url:
        docling = httpx.AsyncClient(base_url=config.docling_url, timeout=300.0)
        logger.info("docling_configured url=%s", config.docling_url)
    else:
        logger.info("docling_not_configured pdf_tools_disabled")

    cache = ScholarCache(config.cache_dir / "cache.db")
    await cache.open()

    bundle = ServiceBundle(
        s2=s2, openalex=openalex, docling=docling, cache=cache, config=config
    )
    try:
        yield {"bundle": bundle}
    finally:
        await s2.aclose()
        await openalex.aclose()
        if docling:
            await docling.aclose()
        await cache.close()


def get_bundle(ctx: Context = Depends(Context)) -> ServiceBundle:
    """FastMCP dependency: extract ServiceBundle from lifespan context.

    Args:
        ctx: FastMCP request context (injected automatically).

    Returns:
        The :class:`ServiceBundle` created during lifespan.
    """
    return ctx.request_context.lifespan_context["bundle"]  # type: ignore[return-value]
