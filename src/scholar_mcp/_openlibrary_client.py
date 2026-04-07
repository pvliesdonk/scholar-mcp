"""Open Library API client for book metadata."""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

import httpx

from ._rate_limiter import RateLimiter
from ._record_types import BookRecord

logger = logging.getLogger(__name__)

_COVER_BASE = "https://covers.openlibrary.org/b/isbn"

# Patterns for extracting OL identifiers from API keys.
_OL_WORK_RE = re.compile(r"OL\d+W")
_OL_EDITION_RE = re.compile(r"OL\d+M")


class OpenLibraryClient:
    """Thin async client for the Open Library API.

    Args:
        http_client: Pre-configured httpx.AsyncClient pointed at openlibrary.org.
        limiter: Rate limiter (~0.6s delay for ~100 req/min politeness).
    """

    def __init__(self, http_client: httpx.AsyncClient, limiter: RateLimiter) -> None:
        self._client = http_client
        self._limiter = limiter

    async def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Search Open Library for books.

        Args:
            query: Free-text search query.
            limit: Maximum number of results.

        Returns:
            List of raw Open Library search doc dicts.
        """
        await self._limiter.acquire()
        try:
            r = await self._client.get(
                "/search.json", params={"q": query, "limit": limit}
            )
            r.raise_for_status()
            return r.json().get("docs", [])  # type: ignore[no-any-return]
        except httpx.HTTPStatusError:
            logger.warning("openlibrary_search_error query=%s", query[:80])
            return []

    async def get_by_isbn(self, isbn: str) -> dict[str, Any] | None:
        """Fetch book edition by ISBN.

        Args:
            isbn: ISBN-10 or ISBN-13 (digits only).

        Returns:
            Open Library edition dict, or None if not found.
        """
        await self._limiter.acquire()
        try:
            r = await self._client.get(f"/isbn/{isbn}.json")
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError:
            logger.warning("openlibrary_isbn_error isbn=%s", isbn)
            return None

    async def get_work(self, work_id: str) -> dict[str, Any] | None:
        """Fetch work-level metadata.

        Args:
            work_id: Open Library work ID (e.g. ``OL1168083W``).

        Returns:
            Open Library work dict, or None if not found.
        """
        await self._limiter.acquire()
        try:
            r = await self._client.get(f"/works/{work_id}.json")
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError:
            logger.warning("openlibrary_work_error work_id=%s", work_id)
            return None

    async def get_edition(self, edition_id: str) -> dict[str, Any] | None:
        """Fetch edition-level metadata.

        Args:
            edition_id: Open Library edition ID (e.g. ``OL1429049M``).

        Returns:
            Open Library edition dict, or None if not found.
        """
        await self._limiter.acquire()
        try:
            r = await self._client.get(f"/books/{edition_id}.json")
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError:
            logger.warning("openlibrary_edition_error edition_id=%s", edition_id)
            return None

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


def normalize_book(
    data: dict[str, Any], *, source: Literal["search", "edition"] = "search"
) -> BookRecord:
    """Normalize an Open Library response to the standard book record shape.

    Args:
        data: Raw Open Library dict (search doc or edition).
        source: One of ``"search"`` or ``"edition"``.

    Returns:
        Normalized book record dict.
    """
    if source == "search":
        isbn_list = data.get("isbn") or []
        isbn_13 = next((i for i in isbn_list if len(i) == 13), None)
        isbn_10 = next((i for i in isbn_list if len(i) == 10), None)
        publishers = data.get("publisher") or []
        work_key = data.get("key") or ""
        work_match = _OL_WORK_RE.search(work_key)
        edition_keys = data.get("edition_key") or []
        cover_id = data.get("cover_i")
        return {
            "title": data.get("title", ""),
            "authors": data.get("author_name") or [],
            "publisher": publishers[0] if publishers else None,
            "year": data.get("first_publish_year"),
            "edition": None,
            "isbn_10": isbn_10,
            "isbn_13": isbn_13,
            "openlibrary_work_id": work_match.group(0) if work_match else None,
            "openlibrary_edition_id": edition_keys[0] if edition_keys else None,
            "cover_url": (
                f"{_COVER_BASE}/{isbn_13}-M.jpg"
                if isbn_13
                else (
                    f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
                    if cover_id
                    else None
                )
            ),
            "google_books_url": None,
            "subjects": data.get("subject") or [],
            "page_count": data.get("number_of_pages_median"),
            "description": None,
        }

    # source == "edition"
    isbn_13_list = data.get("isbn_13") or []
    isbn_10_list = data.get("isbn_10") or []
    isbn_13 = isbn_13_list[0] if isbn_13_list else None
    isbn_10 = isbn_10_list[0] if isbn_10_list else None
    publishers = data.get("publishers") or []
    works = data.get("works") or []
    work_key = works[0]["key"] if works else ""
    work_match = _OL_WORK_RE.search(work_key)
    edition_key = data.get("key") or ""
    edition_match = _OL_EDITION_RE.search(edition_key)
    publish_date = data.get("publish_date") or ""
    year = None
    year_match = re.search(r"\d{4}", publish_date)
    if year_match:
        year = int(year_match.group(0))
    return {
        "title": data.get("title", ""),
        "authors": [],  # edition records lack author names; enrich from work
        "publisher": publishers[0] if publishers else None,
        "year": year,
        "edition": data.get("edition_name"),
        "isbn_10": isbn_10,
        "isbn_13": isbn_13,
        "openlibrary_work_id": work_match.group(0) if work_match else None,
        "openlibrary_edition_id": (edition_match.group(0) if edition_match else None),
        "cover_url": (f"{_COVER_BASE}/{isbn_13}-M.jpg" if isbn_13 else None),
        "google_books_url": None,
        "subjects": data.get("subjects") or [],
        "page_count": data.get("number_of_pages"),
        "description": None,
    }
