"""OpenAlex API client for metadata enrichment."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class OpenAlexClient:
    """Thin async client for the OpenAlex API.

    Args:
        http_client: Pre-configured httpx.AsyncClient pointed at OpenAlex.
    """

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._client = http_client

    async def get_by_doi(self, doi: str) -> dict[str, Any] | None:
        """Fetch OpenAlex work metadata by DOI.

        Args:
            doi: DOI string (without ``https://doi.org/`` prefix).

        Returns:
            OpenAlex work dict or None if not found.
        """
        url = f"/works/https://doi.org/{doi}"
        try:
            r = await self._client.get(url)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]  # httpx returns Any
        except httpx.HTTPStatusError:
            logger.warning("openalex_error doi=%s status=%s", doi, r.status_code)
            return None
