"""Google Books enricher for book records."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class GoogleBooksEnricher:
    """Enriches book records with preview data from Google Books.

    Looks up the book's ISBN in Google Books and fills the
    ``google_books_url`` and ``snippet`` fields on the record.

    Attributes:
        name: Enricher identifier for logging.
        phase: Execution order group (1 = after primary enrichers).
        tags: Labels used to filter enricher selection.
    """

    name: str = "google_books"
    phase: int = 1
    tags: frozenset[str] = frozenset({"books"})

    def can_enrich(self, record: dict[str, Any]) -> bool:
        """Return True when record has an ISBN but no google_books_url.

        Args:
            record: The book record dict to inspect.

        Returns:
            ``True`` if the record has an ISBN and google_books_url is
            absent or falsy.
        """
        if record.get("google_books_url"):
            return False
        return bool(record.get("isbn_13") or record.get("isbn_10"))

    async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
        """Fill google_books_url and snippet from Google Books.

        Extracts the ISBN from the record, checks the cache, falls back
        to the Google Books API, and sets ``record["google_books_url"]``
        and ``record["snippet"]`` from the result.

        All errors are caught and logged at DEBUG level so enrichment
        failures never propagate.

        Args:
            record: The book record dict to enrich in place.
            bundle: Service bundle providing cache and Google Books client.
        """
        isbn = record.get("isbn_13") or record.get("isbn_10")
        if not isbn:
            return
        try:
            cached = await bundle.cache.get_google_books(isbn)
            data = (
                cached
                if cached is not None
                else await bundle.google_books.search_by_isbn(isbn)
            )
            if data is None:
                return
            if cached is None:
                await bundle.cache.set_google_books(isbn, data)
            vol_info = data.get("volumeInfo") or {}
            preview_link = vol_info.get("previewLink")
            if preview_link:
                record["google_books_url"] = preview_link
            search_info = data.get("searchInfo") or {}
            snippet = search_info.get("textSnippet")
            if snippet:
                record["snippet"] = snippet
        except Exception:
            logger.debug("google_books_enrich_failed isbn=%s", isbn, exc_info=True)
