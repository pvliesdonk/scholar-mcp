"""CrossRef API client for metadata enrichment.

Pacing follows the limits CrossRef's public pool advertises on single-work
requests; see ``docs/design/reference/crossref-book-chapter-fields.md``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from ._rate_limiter import RateLimitedError, RateLimiter

logger = logging.getLogger(__name__)


class CrossRefClient:
    """Thin async client for the CrossRef API.

    Requests are spaced by *limiter* and run one at a time, because the
    public pool allows a single request in flight.

    Args:
        http_client: Pre-configured httpx.AsyncClient pointed at CrossRef.
        limiter: Rate limiter spacing request starts.
    """

    def __init__(self, http_client: httpx.AsyncClient, limiter: RateLimiter) -> None:
        self._client = http_client
        self._limiter = limiter
        self._in_flight = asyncio.Lock()

    async def get_by_doi(self, doi: str) -> dict[str, Any] | None:
        """Fetch CrossRef work metadata by DOI.

        Args:
            doi: DOI string (without ``https://doi.org/`` prefix).

        Returns:
            CrossRef message dict, or None if CrossRef has no such work or
            the request failed.

        Raises:
            RateLimitedError: If CrossRef answered 429, so the caller can tell
                a throttled lookup from a missing record.
        """
        url = f"/works/{doi}"
        try:
            async with self._in_flight:
                await self._limiter.acquire()
                r = await self._client.get(url)
            if r.status_code == 404:
                logger.debug("crossref_not_found doi=%s", doi)
                return None
            if r.status_code == 429:
                logger.warning("crossref_rate_limited doi=%s", doi)
                raise RateLimitedError()
            r.raise_for_status()
            data = r.json()
            return data["message"]  # type: ignore[no-any-return]
        except (httpx.HTTPStatusError, httpx.RequestError, KeyError, ValueError):
            logger.warning("crossref_error doi=%s", doi, exc_info=True)
            return None
