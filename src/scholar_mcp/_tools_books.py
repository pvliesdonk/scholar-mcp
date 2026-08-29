"""Book search and lookup MCP tools."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING, Any

import httpx
from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp_pvl_core import register_long_running_tool

from ._book_enrichment import enrich_authors_from_work
from ._cache import normalize_isbn
from ._openlibrary_client import (
    normalize_book,
    normalize_subject,
    normalize_subject_work,
)
from ._record_types import BookRecord
from ._server_deps import ServiceBundle, get_bundle

if TYPE_CHECKING:
    from fastmcp_pvl_core import Jobs

logger = logging.getLogger(__name__)

# Patterns for detecting identifier types.
_OL_WORK_RE = re.compile(r"^OL\d+W$")
_OL_EDITION_RE = re.compile(r"^OL\d+M$")


async def search_books(
    query: str | None = None,
    title: str | None = None,
    author: str | None = None,
    limit: int = 10,
    bundle: ServiceBundle = Depends(get_bundle),
) -> dict[str, Any]:
    """Search for books by title, author, or free text.

    Uses Open Library. Prefer ``title`` and ``author`` over ``query``
    — they use dedicated indexes and return far better results.

    Open Library is politeness-rate-limited, so a busy moment may answer
    with a job handle to poll using ``get_job_result`` instead of the
    results themselves.

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
        ``{"books": [...]}`` — records with title, authors, publisher,
        year, ISBNs, Open Library IDs, cover URL, and subjects.
    """
    if not query and not title and not author:
        return {"error": "provide at least one of query, title, or author"}

    limit = max(1, min(limit, 50))

    cache_key = f"q={query!r}:t={title!r}:a={author!r}:limit={limit}"
    cached = await bundle.cache.get_book_search(cache_key)
    if cached is not None:
        logger.debug("book_search_cache_hit key=%s", cache_key[:60])
        return {"books": cached}

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
    return {"books": books}


async def get_book(
    identifier: str,
    download_cover: bool = False,
    cover_size: str = "M",
    bundle: ServiceBundle = Depends(get_bundle),
) -> dict[str, Any]:
    """Fetch book metadata by ISBN or Open Library ID.

    Open Library is politeness-rate-limited, so a busy moment may answer
    with a job handle to poll using ``get_job_result`` instead of the
    record itself.

    Args:
        identifier: ISBN-10, ISBN-13, Open Library work ID (e.g.
            OL1168083W), or edition ID (e.g. OL1429049M).
        download_cover: If True, download and cache the cover image
            locally. Returns ``cover_path`` in the response. In
            read-only mode, returns ``cover_error`` instead.
        cover_size: Cover size variant: ``"S"`` (small), ``"M"``
            (medium), ``"L"`` (large). Defaults to ``"M"``.

    Returns:
        The book record, or ``{"error": "not_found"}`` if not found.
    """
    cleaned = identifier.strip()

    async def _execute() -> dict[str, Any]:
        # Detect identifier type
        if _OL_WORK_RE.match(cleaned):
            return await _resolve_work(cleaned, bundle)
        if _OL_EDITION_RE.match(cleaned):
            return await _resolve_edition(cleaned, bundle)
        # Assume ISBN
        isbn = normalize_isbn(cleaned)
        return await _resolve_isbn(isbn, bundle)

    result = await _execute()

    if download_cover and result.get("cover_url") and result.get("isbn_13"):
        if bundle.config.read_only:
            result["cover_error"] = "read_only_mode"
        else:
            isbn = result["isbn_13"]
            size = cover_size.upper() if cover_size.upper() in ("S", "M", "L") else "M"
            covers_dir = bundle.config.cache_dir / "covers"
            covers_dir.mkdir(parents=True, exist_ok=True)
            local_path = covers_dir / f"{isbn}_{size}.jpg"
            if local_path.exists():
                result["cover_path"] = str(local_path)
            else:
                url = f"https://covers.openlibrary.org/b/isbn/{isbn}-{size}.jpg"
                try:
                    async with httpx.AsyncClient(timeout=30.0) as http:
                        resp = await http.get(url)
                        resp.raise_for_status()
                        await asyncio.to_thread(local_path.write_bytes, resp.content)
                        result["cover_path"] = str(local_path)
                except Exception:
                    logger.debug(
                        "cover_download_failed isbn=%s",
                        isbn,
                        exc_info=True,
                    )

    return result


async def get_book_excerpt(
    isbn: str,
    bundle: ServiceBundle = Depends(get_bundle),
) -> str:
    """Get a book excerpt and preview info from Google Books.

    Returns the publisher description, text snippet, and a link to
    the Google Books preview page. Google Books does not expose full
    chapter text via API -- the excerpt is a publisher-provided summary
    and/or search snippet.

    Args:
        isbn: ISBN-10 or ISBN-13.

    Returns:
        JSON with excerpt, description, preview availability, and link.

    Example return::

        {"excerpt": "...", "description": "...", "source": "google_books",
         "preview_available": true, "preview_link": "https://..."}
    """
    volume = await bundle.cache.get_google_books(isbn)
    if volume is None:
        volume = await bundle.google_books.search_by_isbn(isbn)
        if volume is None:
            return json.dumps({"error": "not_found", "isbn": isbn})
        await bundle.cache.set_google_books(isbn, volume)

    vol_info = volume.get("volumeInfo") or {}
    access_info = volume.get("accessInfo") or {}
    search_info = volume.get("searchInfo") or {}
    viewability = access_info.get("viewability", "NO_PAGES")
    preview_available = viewability in ("PARTIAL", "ALL_PAGES")

    return json.dumps(
        {
            "excerpt": search_info.get("textSnippet"),
            "description": vol_info.get("description"),
            "source": "google_books",
            "preview_available": preview_available,
            "preview_link": vol_info.get("previewLink"),
        }
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

    # Fetch a fixed pool of 50 so the popularity sort covers more candidates
    # than the caller's limit, and any future request for this subject is
    # served from cache with just a slice.
    subject_data = await bundle.openlibrary.get_subject(slug, limit=50)
    if subject_data is None:
        return json.dumps([])
    works = subject_data.get("works") or []
    works.sort(key=lambda w: w.get("edition_count", 0), reverse=True)
    books = [normalize_subject_work(w) for w in works]
    await bundle.cache.set_book_subject(slug, books)
    return json.dumps(books[:limit])


def register_book_tools(mcp: FastMCP, jobs: Jobs) -> None:
    """Register book search and lookup tools on *mcp*.

    Args:
        mcp: FastMCP application instance.
        jobs: Shared jobs mechanics. ``search_books`` and ``get_book`` reach
            Open Library, which is politeness-rate-limited, so a busy moment
            can outrun the soft deadline and is then promoted.
    """
    register_long_running_tool(
        mcp,
        jobs,
        annotations={
            "title": "Search Books",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(search_books)
    register_long_running_tool(
        mcp,
        jobs,
        annotations={
            "title": "Get Book",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(get_book)
    mcp.tool(
        annotations={
            "title": "Get Book Excerpt",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(get_book_excerpt)
    mcp.tool(
        annotations={
            "title": "Recommend Books",
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
        },
    )(recommend_books)


async def _resolve_isbn(isbn: str, bundle: ServiceBundle) -> dict[str, Any]:
    """Resolve a book by ISBN, checking cache first.

    Args:
        isbn: Normalized ISBN-13 string.
        bundle: Service bundle with cache and openlibrary client.

    Returns:
        The book record, or ``{"error": "not_found"}`` if not found.
    """
    cached = await bundle.cache.get_book_by_isbn(isbn)
    if cached is not None:
        return dict(cached)

    edition = await bundle.openlibrary.get_by_isbn(isbn)
    if edition is None:
        return {"error": "not_found", "identifier": isbn}

    book: BookRecord = normalize_book(edition, source="edition")
    await enrich_authors_from_work(book, bundle)
    await bundle.enrichment.enrich([book], bundle, tags=frozenset({"books"}))
    await bundle.cache.set_book_by_isbn(isbn, book)
    work_id = book.get("openlibrary_work_id")
    if work_id:
        await bundle.cache.set_book_by_work(work_id, book)
    return dict(book)


async def _resolve_work(work_id: str, bundle: ServiceBundle) -> dict[str, Any]:
    """Resolve a book by Open Library work ID, checking cache first.

    Fetches the work, resolves author names from author references, and
    pulls year/publisher/ISBN from the first edition.

    Args:
        work_id: Open Library work ID (e.g. ``OL1168083W``).
        bundle: Service bundle with cache and openlibrary client.

    Returns:
        The book record, or ``{"error": "not_found"}`` if not found.
    """
    cached = await bundle.cache.get_book_by_work(work_id)
    if cached is not None:
        return dict(cached)

    work = await bundle.openlibrary.get_work(work_id)
    if work is None:
        return {"error": "not_found", "identifier": work_id}

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
        "worldcat_url": (
            f"https://www.worldcat.org/isbn/{isbn_13}" if isbn_13 else None
        ),
        "subjects": work.get("subjects") or [],
        "page_count": edition.get("page_count"),
        "description": description if isinstance(description, str) else None,
    }
    await bundle.enrichment.enrich([book], bundle, tags=frozenset({"books"}))
    await bundle.cache.set_book_by_work(work_id, book)
    if isbn_13:
        await bundle.cache.set_book_by_isbn(isbn_13, book)
    return dict(book)


async def _resolve_edition(edition_id: str, bundle: ServiceBundle) -> dict[str, Any]:
    """Resolve a book by Open Library edition ID, checking cache first.

    Args:
        edition_id: Open Library edition ID (e.g. ``OL1429049M``).
        bundle: Service bundle with cache and openlibrary client.

    Returns:
        The book record, or ``{"error": "not_found"}`` if not found.
    """
    edition = await bundle.openlibrary.get_edition(edition_id)
    if edition is None:
        return {"error": "not_found", "identifier": edition_id}

    book: BookRecord = normalize_book(edition, source="edition")
    await enrich_authors_from_work(book, bundle)
    await bundle.enrichment.enrich([book], bundle, tags=frozenset({"books"}))
    isbn_13 = book.get("isbn_13")
    if isbn_13:
        await bundle.cache.set_book_by_isbn(isbn_13, book)
    work_id = book.get("openlibrary_work_id")
    if work_id:
        await bundle.cache.set_book_by_work(work_id, book)
    return dict(book)
