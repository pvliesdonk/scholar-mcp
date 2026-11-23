"""CrossRef enricher for paper records."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

import httpx

from ._rate_limiter import RateLimitedError

logger = logging.getLogger(__name__)


class CrossRefEnricher:
    """Enriches paper records with metadata from CrossRef.

    Looks up the paper's DOI in CrossRef and stores the full
    metadata response as ``crossref_metadata`` on the record.

    Attributes:
        name: Enricher identifier for logging.
        phase: Execution order group (0 = first).
        tags: Labels used to filter enricher selection.
    """

    name: str = "crossref"
    phase: int = 0
    tags: frozenset[str] = frozenset({"papers"})

    def can_enrich(self, record: dict[str, Any]) -> bool:
        """Return True when record has a DOI but no crossref_metadata.

        Args:
            record: The paper record dict to inspect.

        Returns:
            ``True`` if the record has a DOI and crossref_metadata is
            absent or falsy.
        """
        if record.get("crossref_metadata"):
            return False
        doi = (record.get("externalIds") or {}).get("DOI")
        return bool(doi)

    async def enrich(self, record: dict[str, Any], service: Any) -> None:
        """Fill crossref_metadata from CrossRef, using cache when available.

        Extracts the DOI from ``record["externalIds"]["DOI"]``, checks
        the cache, falls back to the CrossRef API, and sets
        ``record["crossref_metadata"]`` with the result.

        A throttled lookup (logged by the client), a transport error or a
        cache error leaves the record without CrossRef metadata. Any other
        exception propagates to the pipeline's own guard.

        Args:
            record: The paper record dict to enrich in place.
            service: Domain service providing cache and CrossRef client.
        """
        doi = (record.get("externalIds") or {}).get("DOI")
        if not doi:
            return
        try:
            cached = await service.cache.get_crossref(doi)
            cr_data = (
                cached if cached is not None else await service.crossref.get_by_doi(doi)
            )
            if cr_data is None:
                return
            if cached is None:
                await service.cache.set_crossref(doi, cr_data)
            record["crossref_metadata"] = cr_data
        except RateLimitedError:
            return
        except (httpx.HTTPError, sqlite3.Error, ValueError):
            logger.debug("crossref_enrich_failed doi=%s", doi, exc_info=True)
