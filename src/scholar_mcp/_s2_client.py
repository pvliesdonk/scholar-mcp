"""Semantic Scholar API client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ._rate_limiter import RateLimiter, with_s2_retry

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

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        async def _call() -> dict[str, Any]:
            r = await self._client.get(
                path, params={k: v for k, v in params.items() if v is not None}
            )
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]

        return await with_s2_retry(_call, self._limiter)  # type: ignore[no-any-return]

    async def get_paper(
        self, identifier: str, fields: str = FIELD_SETS["full"]
    ) -> dict[str, Any]:
        """Fetch full metadata for a single paper.

        Args:
            identifier: DOI, S2 paper ID, arXiv ID (prefix ``ARXIV:``), etc.
            fields: Comma-separated S2 field names or a preset from FIELD_SETS.

        Returns:
            Paper metadata dict.
        """
        return await self._get(f"/paper/{identifier}", fields=fields)

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

        Returns:
            Dict with ``data`` (list of paper dicts) and ``total``.
        """
        return await self._get(
            "/paper/search",
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
        minCitationCount: int | None = None,
    ) -> dict[str, Any]:
        """Fetch papers that cite the given paper.

        Args:
            paper_id: S2 paper ID.
            fields: Comma-separated field names for citing papers.
            limit: Max results.
            offset: Pagination offset.
            year: Year range filter.
            fieldsOfStudy: Fields of study filter.
            minCitationCount: Minimum citation count filter.

        Returns:
            Dict with ``data`` (list of ``{"citingPaper": {...}}`` dicts).
        """
        return await self._get(
            f"/paper/{paper_id}/citations",
            fields=f"citingPaper.{fields}",
            limit=limit,
            offset=offset,
            year=year,
            fieldsOfStudy=fieldsOfStudy,
            minCitationCount=minCitationCount,
        )

    async def get_references(
        self,
        paper_id: str,
        *,
        fields: str,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        """Fetch papers referenced by the given paper.

        Args:
            paper_id: S2 paper ID.
            fields: Comma-separated field names for cited papers.
            limit: Max results.
            offset: Pagination offset.

        Returns:
            Dict with ``data`` (list of ``{"citedPaper": {...}}`` dicts).
        """
        return await self._get(
            f"/paper/{paper_id}/references",
            fields=f"citedPaper.{fields}",
            limit=limit,
            offset=offset,
        )

    async def search_authors(self, name: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search for authors by name.

        Args:
            name: Author name query.
            limit: Maximum number of candidates to return.

        Returns:
            List of author dicts with name, affiliations, hIndex, paperCount.
        """
        result = await self._get(
            "/author/search",
            query=name,
            fields="name,affiliations,hIndex,paperCount",
            limit=limit,
        )
        return result.get("data", [])  # type: ignore[no-any-return]

    async def get_author(
        self, author_id: str, *, limit: int = 20, offset: int = 0
    ) -> dict[str, Any]:
        """Fetch author profile with paginated publications.

        Args:
            author_id: S2 author ID.
            limit: Publications per page.
            offset: Publication page offset.

        Returns:
            Author dict with ``papers`` list.
        """
        return await self._get(
            f"/author/{author_id}",
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
    ) -> list[dict[str, Any]]:
        """Fetch paper recommendations from S2 recommendations endpoint.

        Args:
            positive_ids: Paper IDs to use as positive examples.
            negative_ids: Optional paper IDs to steer away from.
            limit: Number of recommendations.
            fields: Comma-separated field names.

        Returns:
            List of recommended paper dicts.
        """

        async def _call() -> list[dict[str, Any]]:
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

        return await with_s2_retry(_call, self._limiter)  # type: ignore[no-any-return]

    async def batch_resolve(
        self, ids: list[str], *, fields: str
    ) -> list[dict[str, Any] | None]:
        """Resolve a batch of paper IDs using the S2 batch endpoint.

        Args:
            ids: List of S2 paper IDs or DOIs (prefixed with ``DOI:``).
            fields: Comma-separated field names.

        Returns:
            List of paper dicts (None for unresolved items, preserving order).
        """

        async def _call() -> list[dict[str, Any] | None]:
            r = await self._client.post(
                "/paper/batch",
                json={"ids": ids},
                params={"fields": fields},
            )
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]

        return await with_s2_retry(_call, self._limiter)  # type: ignore[no-any-return]
