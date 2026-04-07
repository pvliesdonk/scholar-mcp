"""Book search and lookup MCP tools."""

from __future__ import annotations

import asyncio
import json
import logging
import re

from fastmcp import FastMCP
from fastmcp.dependencies import Depends

from ._book_enrichment import enrich_authors_from_work
from ._cache import normalize_isbn
from ._openlibrary_client import (
    normalize_book,
    normalize_subject,
    normalize_subject_work,
)
from ._rate_limiter import RateLimitedError
from ._record_types import BookRecord
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
        query: str | None = None,
        title: str | None = None,
        author: str | None = None,
        limit: int = 10,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Search for books by title, author, or free text.

        Uses Open Library. Prefer ``title`` and ``author`` over ``query``
        — they use dedicated indexes and return far better results.

        Examples:
            search_books(title="Planning Office Space", author="Francis Duffy")
            search_books(title="Design Patterns")
            search_books(author="Knuth")
            search_books(query="machine learning textbook")  # fallback

        Args:
            query: Free-text fallback. Use ``title``/``author`` when known.
            title: Book title or partial title (recommended).
            author: Author name (recommended).
            limit: Maximum results to return (max 50).

        Returns:
            JSON list of book records with title, authors, publisher, year,
            ISBNs, Open Library IDs, cover URL, and subjects.
        """
        if not query and not title and not author:
            return json.dumps(
                {"error": "provide at least one of query, title, or author"}
            )

        limit = max(1, min(limit, 50))

        cache_key = f"q={query!r}:t={title!r}:a={author!r}:limit={limit}"
        cached = await bundle.cache.get_book_search(cache_key)
        if cached is not None:
            logger.debug("book_search_cache_hit key=%s", cache_key[:60])
            return json.dumps(cached)

        async def _execute(*, retry: bool = True) -> str:
            # When only query is given (no explicit title/author), try
            # it as a title search first — OL's title index is far more
            # relevant than the free-text q= parameter.  Fall back to
            # q= if the title search returns nothing.
            effective_title = title
            effective_query = query
            if query and not title and not author:
                effective_title = query
                effective_query = None

            docs = await bundle.openlibrary.search(
                effective_query,
                title=effective_title,
                author=author,
                limit=limit,
            )

            # When author has multiple tokens (e.g. "Frank Duffy") and
            # results are thin, retry with individual tokens concurrently
            # to catch name variants (Frank→Francis).  The "Duffy" token
            # search finds "Francis Duffy" even when "Frank Duffy" misses.
            author_tokens = author.split() if author else []
            if len(docs) < 3 and len(author_tokens) > 1:
                seen_keys = {d.get("key") for d in docs}
                extras = await asyncio.gather(
                    *(
                        bundle.openlibrary.search(
                            effective_query,
                            title=effective_title,
                            author=token,
                            limit=limit,
                        )
                        for token in author_tokens
                    )
                )
                for extra in extras:
                    for d in extra:
                        key = d.get("key")
                        if key not in seen_keys:
                            docs.append(d)
                            seen_keys.add(key)
                docs = docs[:limit]

            if not docs and effective_query != query:
                # Title search returned nothing; fall back to free-text.
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

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )
    async def recommend_books(
        subject: str,
        limit: int = 10,
        bundle: ServiceBundle = Depends(get_bundle),
    ) -> str:
        """Recommend books for a subject via Open Library.

        Uses the Open Library subject API to find popular books on a
        topic, sorted by edition count (a proxy for popularity).

        Args:
            subject: Subject or topic (e.g. "machine learning",
                "algorithms", "computer vision").
            limit: Maximum results to return (max 50).

        Returns:
            JSON list of book records sorted by popularity.
        """
        limit = max(1, min(limit, 50))
        slug = normalize_subject(subject)

        cached = await bundle.cache.get_book_subject(slug)
        if cached is not None:
            logger.debug("book_subject_cache_hit subject=%s", slug)
            return json.dumps(cached[:limit])

        async def _execute(*, retry: bool = True) -> str:
            subject_data = await bundle.openlibrary.get_subject(slug, limit=limit)
            if subject_data is None:
                return json.dumps([])
            works = subject_data.get("works") or []
            books = [normalize_subject_work(w) for w in works]
            await bundle.cache.set_book_subject(slug, books)
            return json.dumps(books)

        try:
            return await _execute(retry=False)
        except RateLimitedError:
            task_id = bundle.tasks.submit(_execute(retry=True), tool="recommend_books")
            return json.dumps(
                {"queued": True, "task_id": task_id, "tool": "recommend_books"}
            )


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
    await enrich_authors_from_work(book, bundle)
    await bundle.cache.set_book_by_isbn(isbn, book)
    work_id = book.get("openlibrary_work_id")
    if work_id:
        await bundle.cache.set_book_by_work(work_id, book)
    return json.dumps(book)


async def _resolve_work(work_id: str, bundle: ServiceBundle) -> str:
    """Resolve a book by Open Library work ID, checking cache first.

    Fetches the work, resolves author names from author references, and
    pulls year/publisher/ISBN from the first edition.

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

    # Resolve author names concurrently.
    author_refs = work.get("authors") or []
    author_keys: list[str] = []
    for ref in author_refs:
        key = (ref.get("author") or {}).get("key") or ""
        # key looks like "/authors/OL239963A"
        if key:
            author_keys.append(key.rsplit("/", 1)[-1])

    # Resolve authors and fetch first edition concurrently.
    author_names: list[str] = []
    if author_keys:
        author_results, editions = await asyncio.gather(
            asyncio.gather(
                *(bundle.openlibrary.get_author(aid) for aid in author_keys)
            ),
            bundle.openlibrary.get_work_editions(work_id, limit=1),
        )
        author_names = [a["name"] for a in author_results if a and a.get("name")]
    else:
        editions = await bundle.openlibrary.get_work_editions(work_id, limit=1)

    edition: BookRecord = (
        normalize_book(editions[0], source="edition") if editions else {}
    )

    isbn_13 = edition.get("isbn_13")
    isbn_10 = edition.get("isbn_10")
    cover_url = edition.get("cover_url")
    if not cover_url:
        covers = work.get("covers") or []
        if covers:
            cover_url = f"https://covers.openlibrary.org/b/id/{covers[0]}-M.jpg"

    book: BookRecord = {
        "title": work.get("title", ""),
        "authors": author_names,
        "publisher": edition.get("publisher"),
        "year": edition.get("year"),
        "edition": edition.get("edition"),
        "isbn_10": isbn_10,
        "isbn_13": isbn_13,
        "openlibrary_work_id": work_id,
        "openlibrary_edition_id": edition.get("openlibrary_edition_id"),
        "cover_url": cover_url,
        "google_books_url": None,
        "subjects": work.get("subjects") or [],
        "page_count": edition.get("page_count"),
        "description": description if isinstance(description, str) else None,
    }
    await bundle.cache.set_book_by_work(work_id, book)
    if isbn_13:
        await bundle.cache.set_book_by_isbn(isbn_13, book)
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

    book: BookRecord = normalize_book(edition, source="edition")
    await enrich_authors_from_work(book, bundle)
    isbn_13 = book.get("isbn_13")
    if isbn_13:
        await bundle.cache.set_book_by_isbn(isbn_13, book)
    work_id = book.get("openlibrary_work_id")
    if work_id:
        await bundle.cache.set_book_by_work(work_id, book)
    return json.dumps(book)
