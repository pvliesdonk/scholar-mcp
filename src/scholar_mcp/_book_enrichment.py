"""Centralized book enrichment for paper records."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ._cache import normalize_isbn
from ._openlibrary_client import normalize_book
from ._rate_limiter import RateLimitedError
from ._record_types import BookRecord
from ._server_deps import ServiceBundle

logger = logging.getLogger(__name__)


async def _resolve_author_keys(
    author_keys: list[str], bundle: ServiceBundle
) -> list[str]:
    """Resolve Open Library author keys to author names.

    Args:
        author_keys: List of Open Library author keys (e.g. ``/authors/OL239963A``).
        bundle: Service bundle with openlibrary client.

    Returns:
        List of resolved author name strings.
    """
    # Strip path prefix — get_author expects short IDs like "OL239963A"
    ids = [k.rsplit("/", 1)[-1] for k in author_keys]
    results = await asyncio.gather(*(bundle.openlibrary.get_author(aid) for aid in ids))
    return [a["name"] for a in results if a and a.get("name")]


def _extract_author_keys(work: dict[str, Any]) -> list[str]:
    """Extract author keys from a work record.

    Args:
        work: Open Library work dict.

    Returns:
        List of author key strings.
    """
    keys: list[str] = []
    for entry in work.get("authors") or []:
        if isinstance(entry, dict):
            author = entry.get("author")
            if isinstance(author, dict) and author.get("key"):
                keys.append(author["key"])
    return keys


async def enrich_authors_from_work(book: BookRecord, bundle: ServiceBundle) -> None:
    """Enrich book in-place with authors from its work record.

    Best-effort: failures are logged and silently skipped.

    Args:
        book: Book record to enrich in-place.
        bundle: Service bundle with openlibrary client.
    """
    if book.get("authors"):
        return
    work_id = book.get("openlibrary_work_id")
    if not work_id:
        return
    try:
        work = await bundle.openlibrary.get_work(work_id)
        if work is None:
            return
        author_keys = _extract_author_keys(work)
        if author_keys:
            names = await _resolve_author_keys(author_keys, bundle)
            if names:
                book["authors"] = names
    except Exception:
        logger.debug("author_enrichment_failed work_id=%s", work_id, exc_info=True)


def _needs_book_enrichment(paper: dict[str, Any]) -> bool:
    """Check whether a paper should be enriched with book metadata.

    Args:
        paper: S2 paper dict.

    Returns:
        True if the paper has an ISBN in externalIds.
    """
    ext = paper.get("externalIds") or {}
    return bool(ext.get("ISBN"))


def _extract_isbn(paper: dict[str, Any]) -> str | None:
    """Extract and normalize ISBN from a paper's externalIds.

    Args:
        paper: S2 paper dict.

    Returns:
        Normalized ISBN-13, or None.
    """
    ext = paper.get("externalIds") or {}
    isbn = ext.get("ISBN")
    if isbn:
        return normalize_isbn(isbn)
    return None


async def _enrich_one(paper: dict[str, Any], bundle: ServiceBundle) -> None:
    """Enrich a single paper dict in-place with book metadata.

    Args:
        paper: S2 paper dict (mutated in-place).
        bundle: Service bundle for API/cache access.
    """
    isbn = _extract_isbn(paper)
    if isbn is None:
        return

    try:
        cached = await bundle.cache.get_book_by_isbn(isbn)
        if cached is not None:
            paper["book_metadata"] = _to_enrichment_dict(cached)
            return

        edition = await bundle.openlibrary.get_by_isbn(isbn)
        if edition is None:
            return

        book: BookRecord = normalize_book(edition, source="edition")
        await enrich_authors_from_work(book, bundle)
        await bundle.cache.set_book_by_isbn(isbn, book)
        work_id = book.get("openlibrary_work_id")
        if work_id:
            await bundle.cache.set_book_by_work(work_id, book)
        paper["book_metadata"] = _to_enrichment_dict(book)
    except RateLimitedError:
        raise
    except Exception:
        logger.debug(
            "book_enrich_failed paper=%s isbn=%s",
            paper.get("paperId"),
            isbn,
            exc_info=True,
        )


def _to_enrichment_dict(book: BookRecord) -> dict[str, Any]:
    """Extract the enrichment-relevant subset from a full book record.

    Args:
        book: Normalized book record dict.

    Returns:
        Dict with book metadata fields for paper enrichment.
    """
    return {
        "publisher": book.get("publisher"),
        "edition": book.get("edition"),
        "isbn_13": book.get("isbn_13"),
        "cover_url": book.get("cover_url"),
        "openlibrary_work_id": book.get("openlibrary_work_id"),
        "description": book.get("description"),
        "subjects": book.get("subjects") or [],
        "page_count": book.get("page_count"),
        "authors": book.get("authors") or [],
    }


async def enrich_books(
    papers: list[dict[str, Any]],
    bundle: ServiceBundle,
    *,
    concurrency: int = 5,
) -> None:
    """Enrich paper dicts in-place with book metadata from Open Library.

    Only papers with an ISBN in ``externalIds`` are enriched. Failures
    are logged and silently skipped.

    Args:
        papers: List of S2 paper dicts (mutated in-place).
        bundle: Service bundle for API/cache access.
        concurrency: Max parallel Open Library requests.
    """
    candidates = [p for p in papers if _needs_book_enrichment(p)]
    if not candidates:
        return

    sem = asyncio.Semaphore(concurrency)

    async def _bounded(paper: dict[str, Any]) -> None:
        async with sem:
            await _enrich_one(paper, bundle)

    await asyncio.gather(*(_bounded(p) for p in candidates))
