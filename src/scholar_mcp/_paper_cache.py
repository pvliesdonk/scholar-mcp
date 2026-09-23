"""Shared read-through caching for Semantic Scholar paper records."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from ._record_types import PaperRecord

if TYPE_CHECKING:
    from ._protocols import CacheProtocol

logger = logging.getLogger(__name__)

PaperFetcher = Callable[[str], Awaitable[PaperRecord]]


async def resolve_paper(
    cache: CacheProtocol, fetch_paper: PaperFetcher, identifier: str
) -> PaperRecord:
    """Resolve a paper through its aliases, cache, and upstream fetcher.

    Fresh records are cached under their Semantic Scholar paper ID. When the
    caller used a different identifier, it is recorded as an alias. A record
    without a paper ID is returned but not cached because it has no canonical
    cache key.

    Args:
        cache: Paper and identifier-alias cache.
        fetch_paper: Async upstream lookup for a cache miss. It must return
            full metadata because its result is cached as a complete paper
            record.
        identifier: DOI, Semantic Scholar ID, arXiv ID, or another supported ID.

    Returns:
        The cached or freshly fetched paper record.
    """
    cached_id = await cache.get_alias(identifier) or identifier
    cached = await cache.get_paper(cached_id)
    if cached:
        logger.debug("paper_cache_hit identifier=%s", identifier)
        return cached

    paper = await fetch_paper(identifier)
    paper_id = paper.get("paperId") or ""
    if paper_id:
        await cache.set_paper(paper_id, paper)
        if identifier != paper_id:
            await cache.set_alias(identifier, paper_id)
    return paper
