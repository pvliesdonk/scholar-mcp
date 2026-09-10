"""Google Books API client for metadata enrichment."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class GoogleBooksClient:
    """Thin async client for the Google Books API.

    Args:
        http_client: Pre-configured httpx.AsyncClient pointed at
            ``https://www.googleapis.com/books/v1``.
        api_key: Optional API key for higher rate limits.
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        api_key: str | None = None,
    ) -> None:
        self._client = http_client
        self._api_key = api_key

    def _params(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Build query params, adding API key if configured.

        Args:
            extra: Additional query parameters to merge in.

        Returns:
            Merged parameter dict.
        """
        params: dict[str, str] = {}
        if self._api_key:
            params["key"] = self._api_key
        if extra:
            params.update(extra)
        return params

    async def search_by_isbn(self, isbn: str) -> dict[str, Any] | None:
        """Search for a volume by ISBN.

        ``None`` means Google Books answered and had no such volume. A
        refused or failed request raises instead of returning ``None``:
        collapsing the two leaves a caller unable to tell "no such book"
        from "ask again later", and the anonymous tier returns 429 often
        enough for that to matter.

        Args:
            isbn: ISBN-10 or ISBN-13 string.

        Returns:
            The first matching volume dict, or None when Google Books
            reports no match.

        Raises:
            httpx.HTTPStatusError: Google Books returned an error status.
            httpx.RequestError: the request never reached Google Books.
        """
        try:
            r = await self._client.get(
                "/volumes",
                params=self._params({"q": f"isbn:{isbn}"}),
            )
            r.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError):
            # Logged here, where the status is in hand, then re-raised so
            # each caller decides: a tool reports it, enrichment skips it.
            logger.warning(
                "google_books_search_error isbn=%s",
                isbn,
                exc_info=True,
            )
            raise
        items = r.json().get("items", [])
        if not items:
            return None
        return items[0]  # type: ignore[no-any-return]

    async def get_volume(self, volume_id: str) -> dict[str, Any] | None:
        """Fetch a specific volume by its Google Books ID.

        Args:
            volume_id: Google Books volume identifier.

        Returns:
            Volume dict, or None on 404 or error.
        """
        try:
            r = await self._client.get(
                f"/volumes/{volume_id}",
                params=self._params(),
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]
        except (httpx.HTTPStatusError, httpx.RequestError):
            logger.warning(
                "google_books_volume_error volume_id=%s",
                volume_id,
                exc_info=True,
            )
            return None
