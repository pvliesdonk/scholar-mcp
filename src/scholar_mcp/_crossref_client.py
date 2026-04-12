"""CrossRef API client for metadata enrichment."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class CrossRefClient:
    """Thin async client for the CrossRef API.

    Args:
        http_client: Pre-configured httpx.AsyncClient pointed at CrossRef.
    """

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._client = http_client

    async def get_by_doi(self, doi: str) -> dict[str, Any] | None:
        """Fetch CrossRef work metadata by DOI.

        Args:
            doi: DOI string (without ``https://doi.org/`` prefix).

        Returns:
            CrossRef message dict or None if not found or on error.
        """
        url = f"/works/{doi}"
        try:
            r = await self._client.get(url)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            data = r.json()
            return data["message"]  # type: ignore[no-any-return]
        except (httpx.HTTPStatusError, httpx.RequestError, KeyError):
            logger.warning("crossref_error doi=%s", doi, exc_info=True)
            return None
