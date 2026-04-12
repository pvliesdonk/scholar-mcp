"""Open Library enricher for paper records with ISBNs."""

from __future__ import annotations

import logging
from typing import Any

from ._book_enrichment import _enrich_one
from ._rate_limiter import RateLimitedError

logger = logging.getLogger(__name__)


class OpenLibraryEnricher:
    """Enriches paper records with book metadata from Open Library.

    Wraps :func:`_enrich_one` from ``_book_enrichment`` to satisfy the
    :class:`Enricher` protocol.  Catches all exceptions — including
    :class:`RateLimitedError` — so the enrichment pipeline can continue.

    Attributes:
        name: Enricher identifier for logging.
        phase: Execution order group (1 = after OpenAlex).
        tags: Labels used to filter enricher selection.
    """

    name: str = "openlibrary"
    phase: int = 1
    tags: frozenset[str] = frozenset({"papers"})

    def can_enrich(self, record: dict[str, Any]) -> bool:
        """Return True when record has an ISBN in externalIds.

        Args:
            record: The paper record dict to inspect.

        Returns:
            ``True`` if the record has an ISBN.
        """
        return bool((record.get("externalIds") or {}).get("ISBN"))

    async def enrich(self, record: dict[str, Any], bundle: Any) -> None:
        """Enrich record in-place with book metadata from Open Library.

        Delegates to :func:`_enrich_one` and catches all exceptions
        so enrichment failures never propagate.

        Args:
            record: The paper record dict to enrich in place.
            bundle: Service bundle providing cache and Open Library client.
        """
        try:
            await _enrich_one(record, bundle)
        except RateLimitedError:
            logger.debug(
                "openlibrary_rate_limited paper=%s",
                record.get("paperId"),
            )
        except Exception:
            logger.debug(
                "openlibrary_enrich_failed paper=%s",
                record.get("paperId"),
                exc_info=True,
            )
