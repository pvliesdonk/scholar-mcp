"""Semantic Scholar API client."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

import httpx

from ._rate_limiter import (
    RateLimitedError,
    RateLimiter,
    with_s2_retry,
    with_s2_try_once,
)

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

KEEPALIVE_PAPER_ID = (
    "ARXIV:1706.03762"  # "Attention Is All You Need" — stable, well-known
)
KEEPALIVE_INTERVAL_SECONDS = (
    7 * 24 * 60 * 60
)  # 7 days; well under S2's 60-day key-inactivity window


def log_s2_error(exc: httpx.HTTPStatusError) -> None:
    """Log an S2 upstream HTTP error at a level and event name operators can alert on.

    A 403 gets its own event name (``s2_key_forbidden``) distinct from the
    ordinary 429 retry-path logging in ``_rate_limiter.py`` — it is a
    non-retryable failure class, most commonly an S2 API key that has been
    revoked or removed for inactivity.

    Args:
        exc: The HTTP error raised by the S2 client.
    """
    status = exc.response.status_code
    detail = exc.response.text[:200]
    if status == 403:
        logger.warning("s2_key_forbidden status=403 detail=%s", detail)
    else:
        logger.warning("s2_upstream_error status=%s detail=%s", status, detail)


def format_s2_error(exc: httpx.HTTPStatusError) -> str:
    """Log and format an S2 upstream HTTP error as a caller-facing JSON string.

    Logs full detail server-side via :func:`log_s2_error`. The returned
    JSON intentionally omits the raw upstream response body — LLM callers
    get a generic, non-leaking message; operators get full detail from the
    log line.

    Args:
        exc: The HTTP error raised by the S2 client.

    Returns:
        JSON string: ``{"error": "upstream_error", "status": <code>,
        "detail": <generic message>}``.
    """
    log_s2_error(exc)
    return json.dumps(
        {
            "error": "upstream_error",
            "status": exc.response.status_code,
            "detail": "Semantic Scholar API request failed; see server logs for details",
        }
    )


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


async def run_keepalive(client: S2Client) -> None:
    """Ping S2 periodically to keep the API key from being removed for inactivity.

    Semantic Scholar may remove API keys that see no traffic for 60 days.
    This loop fires an immediate cheap call on startup, then repeats every
    :data:`KEEPALIVE_INTERVAL_SECONDS`. Each iteration's failure is caught
    and logged so one bad cycle never stops future ones; only
    ``asyncio.CancelledError`` (server shutdown) propagates out.

    Args:
        client: The S2 client to ping.
    """
    while True:
        try:
            await client.get_paper(KEEPALIVE_PAPER_ID, fields="paperId", retry=False)
        except RateLimitedError:
            # get_paper(retry=False) raises this (not HTTPStatusError) on a
            # 429 — transient, try again next cycle.
            logger.warning("s2_keepalive_rate_limited")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 403:
                logger.error("s2_keepalive_key_forbidden", exc_info=True)
            else:
                logger.warning(
                    "s2_keepalive_failed status=%s", exc.response.status_code
                )
        except httpx.HTTPError:
            logger.warning("s2_keepalive_failed status=network_error")
        else:
            logger.debug("s2_keepalive_ok")
        await asyncio.sleep(KEEPALIVE_INTERVAL_SECONDS)
