"""Book search and lookup MCP tools."""

from __future__ import annotations

import json
import logging
import re

from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._cache import normalize_isbn
from ._openlibrary_client import normalize_book
from ._record_types import BookRecord
from ._rate_limiter import RateLimitedError
from ._server_deps import ServiceBundle, get_bundle

logger = logging.getLogger(__name__)

# Patterns for detecting identifier types.
_OL_WORK_RE = re.compile(r"^OL\d+W$")
_OL_EDITION_RE = re.compile(r"^OL\d+M$")


def register_book_tools(mcp: FastMCP) -> None:
    """Register book search and lookup tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
    """

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def search_books(
        query: str,
        limit: int = 10,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Search for books by title, author, ISBN, or free text.

        Uses Open Library as the data source. For academic paper search,
        use search_papers instead.

        Args:
            query: Search query — title, author name, ISBN, or keywords.
            limit: Maximum results to return (max 50).

        Returns:
            JSON list of book records with title, authors, publisher, year,
            ISBNs, Open Library IDs, cover URL, and subjects.
        """
        limit = max(1, min(limit, 50))

        cache_key = f"{query}:limit={limit}"
        cached = await bundle.cache.get_book_search(cache_key)
        if cached is not None:
            logger.debug("book_search_cache_hit query=%s", query[:60])
            return json.dumps(cached)

        async def _execute(*, retry: bool = True) -> str:
            docs = await bundle.openlibrary.search(query, limit=limit)
            books = [normalize_book(doc, source="search") for doc in docs]
            await bundle.cache.set_book_search(cache_key, books)
            return json.dumps(books)

        try:
            return await _execute(retry=False)
        except RateLimitedError:
            task_id = bundle.tasks.submit(_execute(retry=True), tool="search_books")
            return json.dumps(
                {"queued": True, "task_id": task_id, "tool": "search_books"}
            )

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def get_book(
        identifier: str,
        include_editions: bool = False,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Fetch book metadata by ISBN or Open Library ID.

        Args:
            identifier: ISBN-10, ISBN-13, Open Library work ID (e.g.
                OL1168083W), or edition ID (e.g. OL1429049M).
            include_editions: If true, fetch the work and list editions.

        Returns:
            JSON book record, or ``{"error": "not_found"}`` if not found.
        """
        cleaned = identifier.strip()

        async def _execute(*, retry: bool = True) -> str:
            # Detect identifier type
            if _OL_WORK_RE.match(cleaned):
                return await _resolve_work(cleaned, bundle)
            if _OL_EDITION_RE.match(cleaned):
                return await _resolve_edition(cleaned, bundle)
            # Assume ISBN
            isbn = normalize_isbn(cleaned)
            return await _resolve_isbn(isbn, bundle)

        try:
            return await _execute(retry=False)
        except RateLimitedError:
            task_id = bundle.tasks.submit(_execute(retry=True), tool="get_book")
            return json.dumps({"queued": True, "task_id": task_id, "tool": "get_book"})


async def _resolve_isbn(isbn: str, bundle: ServiceBundle) -> str:
    """Resolve a book by ISBN, checking cache first.

    Args:
        isbn: Normalized ISBN-13 string.
        bundle: Service bundle with cache and openlibrary client.

    Returns:
        JSON book record, or ``{"error": "not_found"}`` if not found.
    """
    cached = await bundle.cache.get_book_by_isbn(isbn)
    if cached is not None:
        return json.dumps(cached)

    edition = await bundle.openlibrary.get_by_isbn(isbn)
    if edition is None:
        return json.dumps({"error": "not_found", "identifier": isbn})

    book: BookRecord = normalize_book(edition, source="edition")
    await bundle.cache.set_book_by_isbn(isbn, book)
    if book.get("openlibrary_work_id"):
        await bundle.cache.set_book_by_work(book["openlibrary_work_id"], book)
    return json.dumps(book)


async def _resolve_work(work_id: str, bundle: ServiceBundle) -> str:
    """Resolve a book by Open Library work ID, checking cache first.

    Args:
        work_id: Open Library work ID (e.g. ``OL1168083W``).
        bundle: Service bundle with cache and openlibrary client.

    Returns:
        JSON book record, or ``{"error": "not_found"}`` if not found.
    """
    cached = await bundle.cache.get_book_by_work(work_id)
    if cached is not None:
        return json.dumps(cached)

    work = await bundle.openlibrary.get_work(work_id)
    if work is None:
        return json.dumps({"error": "not_found", "identifier": work_id})

    description = work.get("description")
    if isinstance(description, dict):
        description = description.get("value")
    book: BookRecord = {
        "title": work.get("title", ""),
        "authors": [],
        "publisher": None,
        "year": None,
        "edition": None,
        "isbn_10": None,
        "isbn_13": None,
        "openlibrary_work_id": work_id,
        "openlibrary_edition_id": None,
        "cover_url": None,
        "google_books_url": None,
        "subjects": work.get("subjects") or [],
        "page_count": None,
        "description": description if isinstance(description, str) else None,
    }
    await bundle.cache.set_book_by_work(work_id, book)
    return json.dumps(book)


async def _resolve_edition(edition_id: str, bundle: ServiceBundle) -> str:
    """Resolve a book by Open Library edition ID, checking cache first.

    Args:
        edition_id: Open Library edition ID (e.g. ``OL1429049M``).
        bundle: Service bundle with cache and openlibrary client.

    Returns:
        JSON book record, or ``{"error": "not_found"}`` if not found.
    """
    edition = await bundle.openlibrary.get_edition(edition_id)
    if edition is None:
        return json.dumps({"error": "not_found", "identifier": edition_id})

    book = normalize_book(edition, source="edition")
    if book.get("isbn_13"):
        await bundle.cache.set_book_by_isbn(book["isbn_13"], book)
    if book.get("openlibrary_work_id"):
        await bundle.cache.set_book_by_work(book["openlibrary_work_id"], book)
    return json.dumps(book)
