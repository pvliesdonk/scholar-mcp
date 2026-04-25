"""Semantic Scholar API client."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx

from ._rate_limiter import RateLimiter, with_s2_retry, with_s2_try_once

if TYPE_CHECKING:
    from ._record_types import PaperRecord

logger = logging.getLogger(__name__)

_S2_BASE = "https://api.semanticscholar.org/graph/v1"

FIELD_SETS: dict[str, str] = {
    "compact": "title,year,venue,citationCount,paperId",
    "standard": "title,year,venue,citationCount,paperId,authors,externalIds,abstract",
    "full": (
        "title,year,venue,citationCount,paperId,authors,externalIds,"
        "abstract,tldr,openAccessPdf,fieldsOfStudy,referenceCount"
    ),
}


class S2Client:
    """Async client for the Semantic Scholar Graph API.

    Args:
        api_key: Optional S2 API key. Enables higher rate limits.
        delay: Inter-request delay in seconds. Defaults based on api_key
            presence: 1.1s without key, 0.1s with key.
    """

    def __init__(self, api_key: str | None, delay: float | None = None) -> None:
        self._api_key = api_key
        if delay is None:
            delay = 0.1 if api_key else 1.1
        self._limiter = RateLimiter(delay=delay)
        headers: dict[str, str] = {"User-Agent": "scholar-mcp/0.1"}
        if api_key:
            headers["x-api-key"] = api_key
        self._client = httpx.AsyncClient(
            base_url=_S2_BASE, headers=headers, timeout=30.0
        )

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    @property
    def limiter(self) -> RateLimiter:
        """Expose the rate limiter for external use (e.g. background tasks)."""
        return self._limiter

    async def _get(
        self, path: str, *, retry: bool = True, **params: Any
    ) -> dict[str, Any]:
        async def _call() -> dict[str, Any]:
            r = await self._client.get(
                path, params={k: v for k, v in params.items() if v is not None}
            )
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]

        if retry:
            return await with_s2_retry(_call, self._limiter)  # type: ignore[no-any-return]
        return await with_s2_try_once(_call, self._limiter)  # type: ignore[no-any-return]

    async def get_paper(
        self,
        identifier: str,
        fields: str = FIELD_SETS["full"],
        *,
        retry: bool = True,
    ) -> PaperRecord:
        """Fetch full metadata for a single paper.

        Args:
            identifier: DOI, S2 paper ID, arXiv ID (prefix ``ARXIV:``), etc.
            fields: Comma-separated S2 field names or a preset from FIELD_SETS.
            retry: If False, raise :class:`RateLimitedError` on 429 instead
                of retrying.

        Returns:
            Paper metadata record.
        """
        return await self._get(  # type: ignore[return-value]
            f"/paper/{identifier}", retry=retry, fields=fields
        )

    async def search_papers(
        self,
        query: str,
        *,
        fields: str,
        limit: int,
        offset: int,
        year: str | None = None,
        fieldsOfStudy: str | None = None,
        venue: str | None = None,
        minCitationCount: int | None = None,
        sort: str | None = None,
        retry: bool = True,
    ) -> dict[str, Any]:
        """Search the S2 corpus.

        Args:
            query: Search query string.
            fields: Comma-separated field names.
            limit: Max results per page.
            offset: Pagination offset.
            year: Year range string (e.g. ``"2010-2020"``).
            fieldsOfStudy: Comma-separated fields of study filter.
            venue: Venue filter string.
            minCitationCount: Minimum citation count filter.
            sort: Sort order string.
            retry: If False, raise :class:`RateLimitedError` on 429.

        Returns:
            Dict with ``data`` (list of paper dicts) and ``total``.
        """
        return await self._get(
            "/paper/search",
            retry=retry,
            query=query,
            fields=fields,
            limit=limit,
            offset=offset,
            year=year,
            fieldsOfStudy=fieldsOfStudy,
            venue=venue,
            minCitationCount=minCitationCount,
            sort=sort,
        )

    async def get_citations(
        self,
        paper_id: str,
        *,
        fields: str,
        limit: int,
        offset: int,
        year: str | None = None,
        fieldsOfStudy: str | None = None,
        retry: bool = True,
    ) -> dict[str, Any]:
        """Fetch papers that cite the given paper.

        Args:
            paper_id: S2 paper ID.
            fields: Comma-separated field names for citing papers.
            limit: Max results.
            offset: Pagination offset.
            year: Year range filter.
            fieldsOfStudy: Fields of study filter.
            retry: If False, raise :class:`RateLimitedError` on 429.

        Returns:
            Dict with ``data`` (list of ``{"citingPaper": {...}}`` dicts).
        """
        return await self._get(
            f"/paper/{paper_id}/citations",
            retry=retry,
            fields=fields,
            limit=limit,
            offset=offset,
            year=year,
            fieldsOfStudy=fieldsOfStudy,
        )

    async def get_references(
        self,
        paper_id: str,
        *,
        fields: str,
        limit: int,
        offset: int,
        retry: bool = True,
    ) -> dict[str, Any]:
        """Fetch papers referenced by the given paper.

        Args:
            paper_id: S2 paper ID.
            fields: Comma-separated field names for cited papers.
            limit: Max results.
            offset: Pagination offset.
            retry: If False, raise :class:`RateLimitedError` on 429.

        Returns:
            Dict with ``data`` (list of ``{"citedPaper": {...}}`` dicts).
        """
        return await self._get(
            f"/paper/{paper_id}/references",
            retry=retry,
            fields=fields,
            limit=limit,
            offset=offset,
        )

    async def search_authors(
        self, name: str, limit: int = 5, *, retry: bool = True
    ) -> list[dict[str, Any]]:
        """Search for authors by name.

        Args:
            name: Author name query.
            limit: Maximum number of candidates to return.
            retry: If False, raise :class:`RateLimitedError` on 429.

        Returns:
            List of author dicts with name, affiliations, hIndex, paperCount.
        """
        result = await self._get(
            "/author/search",
            retry=retry,
            query=name,
            fields="name,affiliations,hIndex,paperCount",
            limit=limit,
        )
        return result.get("data", [])  # type: ignore[no-any-return]

    async def get_author(
        self,
        author_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
        retry: bool = True,
    ) -> dict[str, Any]:
        """Fetch author profile with paginated publications.

        Args:
            author_id: S2 author ID.
            limit: Publications per page.
            offset: Publication page offset.
            retry: If False, raise :class:`RateLimitedError` on 429.

        Returns:
            Author dict with ``papers`` list.
        """
        return await self._get(
            f"/author/{author_id}",
            retry=retry,
            fields="name,affiliations,hIndex,paperCount,papers.paperId,papers.title,papers.year,papers.citationCount",
            limit=limit,
            offset=offset,
        )

    async def recommend(
        self,
        positive_ids: list[str],
        *,
        negative_ids: list[str] | None = None,
        limit: int = 10,
        fields: str,
        retry: bool = True,
    ) -> list[PaperRecord]:
        """Fetch paper recommendations from S2 recommendations endpoint.

        Args:
            positive_ids: Paper IDs to use as positive examples.
            negative_ids: Optional paper IDs to steer away from.
            limit: Number of recommendations.
            fields: Comma-separated field names.
            retry: If False, raise :class:`RateLimitedError` on 429.

        Returns:
            List of recommended paper records.
        """

        async def _call() -> list[PaperRecord]:
            body: dict[str, Any] = {
                "positivePaperIds": positive_ids,
                "negativePaperIds": negative_ids or [],
            }
            r = await self._client.post(
                "https://api.semanticscholar.org/recommendations/v1/papers",
                json=body,
                params={"fields": fields, "limit": limit},
            )
            r.raise_for_status()
            return r.json().get("recommendedPapers", [])  # type: ignore[no-any-return]

        if retry:
            return await with_s2_retry(_call, self._limiter)  # type: ignore[no-any-return]
        return await with_s2_try_once(_call, self._limiter)  # type: ignore[no-any-return]

    async def batch_resolve(
        self, ids: list[str], *, fields: str, retry: bool = True
    ) -> list[PaperRecord | None]:
        """Resolve a batch of paper IDs using the S2 batch endpoint.

        Args:
            ids: List of S2 paper IDs or DOIs (prefixed with ``DOI:``).
            fields: Comma-separated field names.
            retry: If False, raise :class:`RateLimitedError` on 429.

        Returns:
            List of paper records (None for unresolved items, preserving order).
        """

        async def _call() -> list[PaperRecord | None]:
            r = await self._client.post(
                "/paper/batch",
                json={"ids": ids},
                params={"fields": fields},
            )
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]

        if retry:
            return await with_s2_retry(_call, self._limiter)  # type: ignore[no-any-return]
        return await with_s2_try_once(_call, self._limiter)  # type: ignore[no-any-return]
